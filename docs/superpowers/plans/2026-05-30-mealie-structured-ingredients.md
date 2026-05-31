# Mealie Structured Ingredients Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Re-import the recipe_api recipes into Mealie with *structured* ingredients (food + unit + quantity references) so they can drive shopping lists, and fix yield→numeric-servings and prefixed tags along the way.

**Architecture:** A file-driven pipeline. A new exporter pulls Mealie's seeded foods/units/labels plus the distinct source foods/units. Claude generates two name-based review CSVs (`food_map.csv`, `unit_map.csv`). The importer loads those maps and, through an injected *resolver* that does create-or-fetch against the live Mealie API, rewrites each ingredient into a structured entry. All fuzzy matching is frozen in the CSVs; the apply step does zero guessing — unmapped values are a hard error.

**Tech Stack:** Python 3.11, stdlib `urllib` (Mealie client) + `csv`, SQLAlchemy (source models), pytest. No new dependencies.

---

## File Structure

- **`migration_scripts/mealie_client.py`** (modify) — add list/create foods, units, labels; `update_food`; `delete_recipe`. Pure HTTP, tested via the `_request` fake seam.
- **`migration_scripts/mealie_mapping.py`** (modify) — pure functions only. Add map loaders, structured-ingredient builders, the coverage guard, `build_servings`, prefixed `tag_names`; update `build_yield` and `recipe_to_payload`. No I/O, no client import.
- **`migration_scripts/export_mealie_seed.py`** (create) — Stage 1 exporter (live API + sqlite) writing JSON/CSV into `migration_scripts/seed/`.
- **`migration_scripts/migrate_to_mealie.py`** (modify) — the two resolvers (live + dry-run), `purge`/`import` subcommands, map loading, and the pre-import guard wiring.
- **`migration_scripts/food_map.csv` / `unit_map.csv`** (generated in Task 11) — the review artifacts.
- **`tests/test_mealie_client.py`** / **`tests/test_mealie_mapping.py`** (modify) — extend per task.

Resolver protocol used everywhere (duck-typed, no ABC):
- `resolve_unit(name) -> {"id":…, "name":…} | None`
- `resolve_food(name, action, label) -> {"id":…, "name":…}`

---

## Task 1: MealieClient — foods, units, labels, delete

**Files:**
- Modify: `migration_scripts/mealie_client.py`
- Test: `tests/test_mealie_client.py`

> NOTE: The labels endpoint is `/api/groups/labels` in Mealie v1/v2. Verify against the live instance during Task 11 (`curl -H "Authorization: Bearer $MEALIE_API_TOKEN" $MEALIE_URL/api/groups/labels?perPage=-1`). If it 404s, the alternative is `/api/labels`; update `list_labels`/`create_label` accordingly.

- [ ] **Step 1: Write failing tests**

Add to `tests/test_mealie_client.py`:

```python
def test_list_foods_unwraps_items(monkeypatch):
    client = _client()
    monkeypatch.setattr(client, "_request",
                        lambda m, p, b=None: {"items": [{"id": "1", "name": "Kale"}]})
    assert client.list_foods() == [{"id": "1", "name": "Kale"}]


def test_create_food_sends_label_id(monkeypatch):
    client = _client()
    seen = {}

    def fake(method, path, body=None):
        seen["call"] = (method, path, body)
        return {"id": "9", "name": body["name"]}

    monkeypatch.setattr(client, "_request", fake)
    out = client.create_food("Rau Sauce", label_id="lab1")
    assert out["id"] == "9"
    assert seen["call"] == ("POST", "/api/foods", {"name": "Rau Sauce", "labelId": "lab1"})


def test_create_food_omits_label_when_none(monkeypatch):
    client = _client()
    seen = {}
    monkeypatch.setattr(client, "_request",
                        lambda m, p, b=None: seen.setdefault("body", b) or {"id": "1", "name": b["name"]})
    client.create_food("Salt", label_id=None)
    assert seen["body"] == {"name": "Salt"}


def test_delete_recipe_true_false(monkeypatch):
    client = _client()

    def fake(method, path, body=None):
        if path.endswith("/gone"):
            raise urllib.error.HTTPError(path, 404, "Not Found", {}, None)
        return None

    monkeypatch.setattr(client, "_request", fake)
    assert client.delete_recipe("here") is True
    assert client.delete_recipe("gone") is False
```

- [ ] **Step 2: Run to verify they fail**

Run: `uv run pytest tests/test_mealie_client.py -k "list_foods or create_food or delete_recipe" -v`
Expected: FAIL — `AttributeError: 'MealieClient' object has no attribute 'list_foods'`

- [ ] **Step 3: Implement**

Append to `migration_scripts/mealie_client.py` (after the organizers block):

```python
    # --- foods / units / labels ---
    def _list(self, path: str) -> list:
        resp = self._request("GET", path)
        return resp["items"] if isinstance(resp, dict) else resp

    def list_foods(self) -> list:
        return self._list("/api/foods?perPage=-1")

    def list_units(self) -> list:
        return self._list("/api/units?perPage=-1")

    def list_labels(self) -> list:
        return self._list("/api/groups/labels?perPage=-1")

    def create_food(self, name: str, label_id: str = None) -> dict:
        body = {"name": name}
        if label_id:
            body["labelId"] = label_id
        return self._request("POST", "/api/foods", body)

    def update_food(self, food_id: str, payload: dict) -> dict:
        return self._request("PUT", f"/api/foods/{food_id}", payload)

    def create_unit(self, name: str) -> dict:
        return self._request("POST", "/api/units", {"name": name})

    def create_label(self, name: str) -> dict:
        return self._request("POST", "/api/groups/labels", {"name": name})

    # --- recipe deletion (for clean re-import) ---
    def delete_recipe(self, slug: str) -> bool:
        try:
            self._request("DELETE", f"/api/recipes/{slug}")
            return True
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                return False
            raise
```

- [ ] **Step 4: Run to verify pass**

Run: `uv run pytest tests/test_mealie_client.py -v`
Expected: PASS (all, including the pre-existing tests)

- [ ] **Step 5: Commit**

```bash
git add migration_scripts/mealie_client.py tests/test_mealie_client.py
git commit -m "feat(mealie): add foods/units/labels and delete_recipe client methods"
```

---

## Task 2: Seed exporter

**Files:**
- Create: `migration_scripts/export_mealie_seed.py`
- Test: `tests/test_export_mealie_seed.py`

The exporter writes five files to `migration_scripts/seed/`: `foods.json`, `units.json`, `labels.json` (from Mealie), and `source_foods.txt`, `source_units.txt` (distinct values from `recipes.db`). Keep DB access and file writing in small functions so they test without network or a real DB.

- [ ] **Step 1: Write failing tests**

Create `tests/test_export_mealie_seed.py`:

```python
import json

from migration_scripts.export_mealie_seed import (
    distinct_source_values,
    write_seed,
)


class _FakeClient:
    def list_foods(self):
        return [{"id": "1", "name": "Kale", "label": {"name": "Produce"}}]

    def list_units(self):
        return [{"id": "u1", "name": "cup", "abbreviation": "c"}]

    def list_labels(self):
        return [{"id": "l1", "name": "Produce"}]


def test_distinct_source_values_dedupes_and_sorts():
    rows = [("Kale", "Cup"), ("kale", "cup"), ("Egg", "Piece")]
    foods, units = distinct_source_values(rows)
    assert foods == ["Egg", "Kale", "kale"]   # case-sensitive distinct, sorted
    assert units == ["Cup", "Piece", "cup"]


def test_write_seed_writes_all_files(tmp_path):
    write_seed(_FakeClient(), [("Kale", "Cup")], tmp_path)
    assert json.loads((tmp_path / "foods.json").read_text())[0]["name"] == "Kale"
    assert json.loads((tmp_path / "units.json").read_text())[0]["name"] == "cup"
    assert json.loads((tmp_path / "labels.json").read_text())[0]["name"] == "Produce"
    assert (tmp_path / "source_foods.txt").read_text().splitlines() == ["Kale"]
    assert (tmp_path / "source_units.txt").read_text().splitlines() == ["Cup"]
```

- [ ] **Step 2: Run to verify they fail**

Run: `uv run pytest tests/test_export_mealie_seed.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'migration_scripts.export_mealie_seed'`

- [ ] **Step 3: Implement**

Create `migration_scripts/export_mealie_seed.py`:

```python
"""Stage 1: export Mealie's seeded foods/units/labels + distinct source foods/units.

Usage:
    MEALIE_API_TOKEN=<token> uv run python -m migration_scripts.export_mealie_seed
"""

import json
import os
import sys
from pathlib import Path

sys.path.append(os.getcwd())

from app.db.session import SessionLocal
from app.models import Ingredient, RecipeIngredient
from migration_scripts.mealie_client import MealieClient

SEED_DIR = Path(__file__).parent / "seed"


def distinct_source_values(rows):
    """rows: iterable of (food_name, unit). Return (sorted distinct foods, units)."""
    foods = sorted({f for f, _ in rows if f})
    units = sorted({u for _, u in rows if u})
    return foods, units


def load_source_rows(session):
    return (
        session.query(Ingredient.name, RecipeIngredient.unit)
        .join(RecipeIngredient, RecipeIngredient.ingredient_id == Ingredient.id)
        .all()
    )


def write_seed(client, rows, out_dir: Path):
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "foods.json").write_text(json.dumps(client.list_foods(), indent=2))
    (out_dir / "units.json").write_text(json.dumps(client.list_units(), indent=2))
    (out_dir / "labels.json").write_text(json.dumps(client.list_labels(), indent=2))
    foods, units = distinct_source_values(rows)
    (out_dir / "source_foods.txt").write_text("\n".join(foods) + "\n")
    (out_dir / "source_units.txt").write_text("\n".join(units) + "\n")


def main():
    token = os.environ.get("MEALIE_API_TOKEN")
    if not token:
        raise SystemExit("MEALIE_API_TOKEN is required")
    base = os.environ.get("MEALIE_URL", "https://recipes.qwertyshoe.com")
    client = MealieClient(base, token)
    session = SessionLocal()
    try:
        rows = load_source_rows(session)
    finally:
        session.close()
    write_seed(client, rows, SEED_DIR)
    print(f"Wrote seed export to {SEED_DIR} ({len(rows)} source ingredient rows)")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run to verify pass**

Run: `uv run pytest tests/test_export_mealie_seed.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add migration_scripts/export_mealie_seed.py tests/test_export_mealie_seed.py
git commit -m "feat(mealie): add seed exporter for foods/units/labels + source values"
```

---

## Task 3: Yield → numeric servings

**Files:**
- Modify: `migration_scripts/mealie_mapping.py`
- Test: `tests/test_mealie_mapping.py`

- [ ] **Step 1: Write/replace failing tests**

In `tests/test_mealie_mapping.py`, add `build_servings` to the import list from `migration_scripts.mealie_mapping`. Replace the two existing `build_yield` tests with:

```python
def test_build_servings_from_servings_unit():
    recipe = SimpleNamespace(yield_amount=4.0, yield_unit="servings")
    assert build_servings(recipe) == 4.0


def test_build_servings_empty_unit_counts_as_servings():
    recipe = SimpleNamespace(yield_amount=6.0, yield_unit=None)
    assert build_servings(recipe) == 6.0


def test_build_servings_none_for_non_servings_unit():
    recipe = SimpleNamespace(yield_amount=1.0, yield_unit="loaf")
    assert build_servings(recipe) is None


def test_build_yield_empty_when_servings():
    recipe = SimpleNamespace(yield_amount=4.0, yield_unit="servings")
    assert build_yield(recipe) == ""


def test_build_yield_text_for_non_servings():
    recipe = SimpleNamespace(yield_amount=1.0, yield_unit="loaf")
    assert build_yield(recipe) == "1 loaf"
```

- [ ] **Step 2: Run to verify they fail**

Run: `uv run pytest tests/test_mealie_mapping.py -k "servings or build_yield" -v`
Expected: FAIL — `ImportError: cannot import name 'build_servings'`

- [ ] **Step 3: Implement**

In `migration_scripts/mealie_mapping.py`, replace the existing `build_yield` function with:

```python
def build_servings(recipe):
    """Return a numeric servings count when the yield is a servings count, else None."""
    unit = (recipe.yield_unit or "").strip().lower()
    if unit in ("", "servings", "serving") and recipe.yield_amount:
        return float(recipe.yield_amount)
    return None


def build_yield(recipe) -> str:
    """Text yield, only for genuinely non-servings units (else '' — servings is numeric)."""
    if build_servings(recipe) is not None:
        return ""
    amount = format_quantity(recipe.yield_amount)
    unit = recipe.yield_unit or ""
    return " ".join(p for p in [amount, unit] if p).strip()
```

- [ ] **Step 4: Run to verify pass**

Run: `uv run pytest tests/test_mealie_mapping.py -k "servings or build_yield" -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add migration_scripts/mealie_mapping.py tests/test_mealie_mapping.py
git commit -m "feat(mealie): map yield to numeric servings"
```

---

## Task 4: Prefixed tags

**Files:**
- Modify: `migration_scripts/mealie_mapping.py`
- Test: `tests/test_mealie_mapping.py`

- [ ] **Step 1: Replace failing tests**

In `tests/test_mealie_mapping.py`, replace the two existing `tag_names` tests with:

```python
def test_tag_names_prefixes_each_field():
    recipe = SimpleNamespace(
        cuisine="Italian", protein="Chicken",
        difficulty=SimpleNamespace(value="Easy"), diets=[],
    )
    assert tag_names(recipe) == ["Cuisine: Italian", "Protein: Chicken", "Difficulty: Easy"]


def test_tag_names_skips_nulls():
    recipe = SimpleNamespace(cuisine=None, protein="Beef", difficulty=None, diets=[])
    assert tag_names(recipe) == ["Protein: Beef"]


def test_tag_names_includes_diets_dormant_when_empty():
    recipe = SimpleNamespace(
        cuisine=None, protein=None, difficulty=None,
        diets=[SimpleNamespace(diet_type=SimpleNamespace(value="vegan"))],
    )
    assert tag_names(recipe) == ["Diet: vegan"]
```

- [ ] **Step 2: Run to verify they fail**

Run: `uv run pytest tests/test_mealie_mapping.py -k "tag_names" -v`
Expected: FAIL — assertion error (bare names, no prefixes)

- [ ] **Step 3: Implement**

In `migration_scripts/mealie_mapping.py`, replace the existing `tag_names` function with:

```python
FIELD_PREFIXES = (("cuisine", "Cuisine"), ("protein", "Protein"), ("difficulty", "Difficulty"))


def _enum_value(value) -> str:
    return (value.value if hasattr(value, "value") else str(value)).strip()


def tag_names(recipe) -> list:
    """Prefixed tags by origin field: 'Protein: Beef', 'Difficulty: Medium', etc."""
    names = []
    for attr, prefix in FIELD_PREFIXES:
        value = getattr(recipe, attr, None)
        if not value:
            continue
        raw = _enum_value(value)
        if raw:
            names.append(f"{prefix}: {raw}")
    for diet in getattr(recipe, "diets", None) or []:
        raw = _enum_value(diet.diet_type) if getattr(diet, "diet_type", None) else ""
        if raw:
            names.append(f"Diet: {raw}")
    return names
```

- [ ] **Step 4: Run to verify pass**

Run: `uv run pytest tests/test_mealie_mapping.py -k "tag_names" -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add migration_scripts/mealie_mapping.py tests/test_mealie_mapping.py
git commit -m "feat(mealie): prefix tags by source field (Protein/Difficulty/Cuisine/Diet)"
```

---

## Task 5: Map loaders

**Files:**
- Modify: `migration_scripts/mealie_mapping.py`
- Test: `tests/test_mealie_mapping.py`

- [ ] **Step 1: Write failing tests**

Add `load_food_map, load_unit_map` to the import list. Add tests:

```python
def _write_csv(tmp_path, name, header, rows):
    path = tmp_path / name
    lines = [",".join(header)] + [",".join(r) for r in rows]
    path.write_text("\n".join(lines) + "\n")
    return str(path)


def test_load_food_map_parses_rows(tmp_path):
    path = _write_csv(
        tmp_path, "food_map.csv",
        ["source_food", "action", "mealie_food", "label", "flags"],
        [["Kale", "match", "Kale", "Produce", ""],
         ["Rau Sauce", "create", "Rau Sauce", "Sauces", "unmatched"]],
    )
    fm = load_food_map(path)
    assert fm["kale"] == {"mealie_food": "Kale", "action": "match", "label": "Produce", "flags": ""}
    assert fm["rau sauce"]["action"] == "create"


def test_load_food_map_rejects_bad_action(tmp_path):
    path = _write_csv(
        tmp_path, "food_map.csv",
        ["source_food", "action", "mealie_food", "label", "flags"],
        [["Kale", "guess", "Kale", "Produce", ""]],
    )
    import pytest
    with pytest.raises(ValueError, match="bad action"):
        load_food_map(path)


def test_load_food_map_rejects_missing_column(tmp_path):
    path = _write_csv(tmp_path, "food_map.csv",
                      ["source_food", "action", "mealie_food"], [["Kale", "match", "Kale"]])
    import pytest
    with pytest.raises(ValueError, match="missing columns"):
        load_food_map(path)


def test_load_unit_map_treats_none_token_as_empty(tmp_path):
    path = _write_csv(
        tmp_path, "unit_map.csv",
        ["source_unit", "mealie_unit", "flags"],
        [["Cup", "cup", ""], ["To Taste", "(none)", "to-taste"]],
    )
    um = load_unit_map(path)
    assert um["cup"] == {"mealie_unit": "cup", "flags": ""}
    assert um["to taste"] == {"mealie_unit": "", "flags": "to-taste"}
```

- [ ] **Step 2: Run to verify they fail**

Run: `uv run pytest tests/test_mealie_mapping.py -k "food_map or unit_map" -v`
Expected: FAIL — `ImportError: cannot import name 'load_food_map'`

- [ ] **Step 3: Implement**

Add to the top of `migration_scripts/mealie_mapping.py` (`import csv` near the existing `import re`), then add:

```python
def _read_rows(path, required):
    import csv
    with open(path, newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        fields = set(reader.fieldnames or [])
        missing = required - fields
        if missing:
            raise ValueError(f"{path}: missing columns: {sorted(missing)}")
        return list(reader)


def load_food_map(path) -> dict:
    out = {}
    for row in _read_rows(path, {"source_food", "action", "mealie_food", "label", "flags"}):
        action = (row["action"] or "").strip().lower()
        if action not in ("match", "create"):
            raise ValueError(f"{path}: bad action '{row['action']}' for '{row['source_food']}'")
        out[(row["source_food"] or "").strip().lower()] = {
            "mealie_food": (row["mealie_food"] or "").strip(),
            "action": action,
            "label": (row["label"] or "").strip(),
            "flags": (row["flags"] or "").strip(),
        }
    return out


def load_unit_map(path) -> dict:
    out = {}
    for row in _read_rows(path, {"source_unit", "mealie_unit", "flags"}):
        unit = (row["mealie_unit"] or "").strip()
        if unit == "(none)":
            unit = ""
        out[(row["source_unit"] or "").strip().lower()] = {
            "mealie_unit": unit,
            "flags": (row["flags"] or "").strip(),
        }
    return out
```

(Remove the local `import csv` inside `_read_rows` if you added `import csv` at module top — keep only one.)

- [ ] **Step 4: Run to verify pass**

Run: `uv run pytest tests/test_mealie_mapping.py -k "food_map or unit_map" -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add migration_scripts/mealie_mapping.py tests/test_mealie_mapping.py
git commit -m "feat(mealie): add food_map/unit_map CSV loaders with validation"
```

---

## Task 6: Structured ingredient builders

**Files:**
- Modify: `migration_scripts/mealie_mapping.py`
- Test: `tests/test_mealie_mapping.py`

This replaces the old `build_ingredients` (display strings) with `build_structured_ingredients` (food/unit/quantity refs). Keep `build_ingredient_line` — it now produces `originalText`.

- [ ] **Step 1: Replace failing tests**

In `tests/test_mealie_mapping.py`: change the import line to drop `build_ingredients` and add `build_structured_ingredient, build_structured_ingredients`. Delete the two old `test_build_ingredients_*` tests. Add a fake resolver and new tests:

```python
class _FakeResolver:
    def resolve_unit(self, name):
        return {"id": f"u-{name}", "name": name} if name else None

    def resolve_food(self, name, action, label):
        return {"id": f"f-{name}", "name": name, "_action": action, "_label": label}


def test_structured_ingredient_normal_amount():
    ri = _ri(2.0, "cup", "Flour", "sifted", order=0)
    entry = build_structured_ingredient(
        ri, {"id": "u1", "name": "cup"}, {"id": "f1", "name": "Flour"}, None, to_taste=False)
    assert entry == {
        "title": None, "note": "sifted", "quantity": 2.0,
        "unit": {"id": "u1", "name": "cup"}, "food": {"id": "f1", "name": "Flour"},
        "disableAmount": False, "originalText": "2 cup Flour, sifted",
    }


def test_structured_ingredient_to_taste():
    ri = _ri(0, "To Taste", "Salt", None, order=0)
    entry = build_structured_ingredient(ri, None, {"id": "f2", "name": "Salt"}, None, to_taste=True)
    assert entry["quantity"] is None
    assert entry["disableAmount"] is True
    assert entry["unit"] is None
    assert entry["note"] == "to taste"
    assert entry["food"] == {"id": "f2", "name": "Salt"}


def test_structured_ingredients_resolves_maps_and_titles_sections():
    recipe = SimpleNamespace(components=[
        _component("Main", [_ri(1.0, "cup", "Flour", order=1), _ri(2.0, None, "Eggs", order=0)]),
        _component("Frosting", [_ri(0.5, "cup", "Butter", order=0)]),
    ])
    food_map = {n.lower(): {"mealie_food": n, "action": "match", "label": "", "flags": ""}
                for n in ("Flour", "Eggs", "Butter")}
    unit_map = {"cup": {"mealie_unit": "cup", "flags": ""}, "": {"mealie_unit": "", "flags": ""}}
    items = build_structured_ingredients(recipe, food_map, unit_map, _FakeResolver())
    assert items[0]["title"] is None and items[0]["food"]["name"] == "Eggs"
    assert items[0]["unit"] is None          # None source unit -> no unit
    assert items[1]["food"]["name"] == "Flour"
    assert items[2]["title"] == "Frosting"   # non-Main section titled on first line
```

- [ ] **Step 2: Run to verify they fail**

Run: `uv run pytest tests/test_mealie_mapping.py -k "structured" -v`
Expected: FAIL — `ImportError: cannot import name 'build_structured_ingredient'`

- [ ] **Step 3: Implement**

In `migration_scripts/mealie_mapping.py`, remove the old `build_ingredients` function and add:

```python
def build_structured_ingredient(ri, unit_ref, food_ref, title, to_taste) -> dict:
    """One Mealie structured ingredient. to_taste / zero-quantity -> unmeasured."""
    note = ri.notes or ""
    if to_taste or not ri.quantity:
        quantity = None
        disable_amount = True
        if to_taste and not note:
            note = "to taste"
    else:
        quantity = float(ri.quantity)
        disable_amount = False
    return {
        "title": title,
        "note": note,
        "quantity": quantity,
        "unit": unit_ref,
        "food": food_ref,
        "disableAmount": disable_amount,
        "originalText": build_ingredient_line(ri.quantity, ri.unit, ri.ingredient.name, ri.notes),
    }


def build_structured_ingredients(recipe, food_map, unit_map, resolver) -> list:
    """Structured Mealie ingredients, resolving food/unit refs via `resolver`.

    Assumes every source food/unit is present in the maps (see missing_map_entries).
    """
    items = []
    for component in recipe.components:
        first = True
        for ri in sorted(component.ingredients, key=lambda x: x.order):
            fm = food_map[ri.ingredient.name.strip().lower()]
            um = unit_map[(ri.unit or "").strip().lower()]
            unit_ref = resolver.resolve_unit(um["mealie_unit"])
            food_ref = resolver.resolve_food(fm["mealie_food"], fm["action"], fm["label"])
            to_taste = "to-taste" in um["flags"]
            title = component.name if (first and component.name and component.name != "Main") else None
            items.append(build_structured_ingredient(ri, unit_ref, food_ref, title, to_taste))
            first = False
    return items
```

- [ ] **Step 4: Run to verify pass**

Run: `uv run pytest tests/test_mealie_mapping.py -k "structured" -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add migration_scripts/mealie_mapping.py tests/test_mealie_mapping.py
git commit -m "feat(mealie): build structured ingredients from review maps"
```

---

## Task 7: Coverage guard

**Files:**
- Modify: `migration_scripts/mealie_mapping.py`
- Test: `tests/test_mealie_mapping.py`

- [ ] **Step 1: Write failing test**

Add `missing_map_entries` to the import list. Add:

```python
def test_missing_map_entries_reports_unmapped():
    recipe = SimpleNamespace(components=[
        _component("Main", [_ri(1.0, "cup", "Flour", order=0), _ri(2.0, "Shot", "Rum", order=1)]),
    ])
    food_map = {"flour": {"mealie_food": "Flour", "action": "match", "label": "", "flags": ""}}
    unit_map = {"cup": {"mealie_unit": "cup", "flags": ""}}
    foods, units = missing_map_entries([recipe], food_map, unit_map)
    assert foods == ["Rum"]
    assert units == ["Shot"]


def test_missing_map_entries_empty_when_covered():
    recipe = SimpleNamespace(components=[_component("Main", [_ri(1.0, "cup", "Flour", order=0)])])
    food_map = {"flour": {"mealie_food": "Flour", "action": "match", "label": "", "flags": ""}}
    unit_map = {"cup": {"mealie_unit": "cup", "flags": ""}}
    assert missing_map_entries([recipe], food_map, unit_map) == ([], [])
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/test_mealie_mapping.py -k "missing_map_entries" -v`
Expected: FAIL — `ImportError: cannot import name 'missing_map_entries'`

- [ ] **Step 3: Implement**

Add to `migration_scripts/mealie_mapping.py`:

```python
def missing_map_entries(recipes, food_map, unit_map):
    """Return (sorted unmapped food names, sorted unmapped unit names) across all recipes."""
    foods, units = set(), set()
    for recipe in recipes:
        for component in recipe.components:
            for ri in component.ingredients:
                if ri.ingredient.name.strip().lower() not in food_map:
                    foods.add(ri.ingredient.name)
                if (ri.unit or "").strip().lower() not in unit_map:
                    units.add(ri.unit or "")
    return sorted(foods), sorted(units)
```

- [ ] **Step 4: Run to verify pass**

Run: `uv run pytest tests/test_mealie_mapping.py -k "missing_map_entries" -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add migration_scripts/mealie_mapping.py tests/test_mealie_mapping.py
git commit -m "feat(mealie): add map coverage guard"
```

---

## Task 8: recipe_to_payload — servings + structured ingredients

**Files:**
- Modify: `migration_scripts/mealie_mapping.py`
- Test: `tests/test_mealie_mapping.py`

- [ ] **Step 1: Update the failing test**

In `tests/test_mealie_mapping.py`, update `_sample_recipe()` to add `diets=[]`, and update `test_recipe_to_payload_maps_all_fields` to pass maps + a fake resolver and assert structured output:

```python
def test_recipe_to_payload_maps_all_fields():
    recipe = _sample_recipe()
    shell = {"id": "abc", "slug": "tomato-soup", "name": "Tomato Soup", "nutrition": {}}
    cat_refs = [{"id": "c1", "name": "Soup", "slug": "soup"}]
    tag_refs = [{"id": "t1", "name": "Cuisine: Italian", "slug": "cuisine-italian"}]
    food_map = {"tomatoes": {"mealie_food": "Tomatoes", "action": "match", "label": "", "flags": ""}}
    unit_map = {"can": {"mealie_unit": "can", "flags": ""}}

    payload = recipe_to_payload(recipe, shell, cat_refs, tag_refs, food_map, unit_map, _FakeResolver())

    assert payload["id"] == "abc"
    assert payload["recipeServings"] == 4.0
    assert payload["recipeYield"] == ""
    assert payload["prepTime"] == "10 minutes"
    assert payload["recipeIngredient"][0]["food"]["name"] == "Tomatoes"
    assert payload["recipeIngredient"][0]["disableAmount"] is False
    assert payload["recipeCategory"] == cat_refs
    assert payload["tags"] == tag_refs
    assert payload["nutrition"]["calories"] == "180"
    assert payload["notes"] == [{"title": "Source", "text": "Family recipe"}]
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/test_mealie_mapping.py -k "recipe_to_payload" -v`
Expected: FAIL — `TypeError: recipe_to_payload() takes 4 positional arguments but 7 were given`

- [ ] **Step 3: Implement**

In `migration_scripts/mealie_mapping.py`, replace `recipe_to_payload` with:

```python
def recipe_to_payload(recipe, shell, category_refs, tag_refs, food_map, unit_map, resolver) -> dict:
    """Merge mapped fields onto the Mealie shell returned by create/get."""
    payload = dict(shell)
    payload["name"] = recipe.name
    payload["description"] = recipe.description or ""
    servings = build_servings(recipe)
    payload["recipeServings"] = servings if servings is not None else 0
    payload["recipeYield"] = build_yield(recipe)
    payload["prepTime"] = format_time(recipe.prep_time_minutes)
    payload["performTime"] = format_time(recipe.cook_time_minutes)
    payload["totalTime"] = format_time(recipe.total_time_minutes)
    payload["orgURL"] = recipe.source_url
    payload["recipeIngredient"] = build_structured_ingredients(recipe, food_map, unit_map, resolver)
    payload["recipeInstructions"] = build_instructions(recipe)
    payload["recipeCategory"] = category_refs
    payload["tags"] = tag_refs

    nutrition = dict(payload.get("nutrition") or {})
    if recipe.calories:
        nutrition["calories"] = str(recipe.calories)
    payload["nutrition"] = nutrition

    payload["notes"] = build_notes(recipe)
    return payload
```

- [ ] **Step 4: Run full mapping suite**

Run: `uv run pytest tests/test_mealie_mapping.py -v`
Expected: PASS (whole file)

- [ ] **Step 5: Commit**

```bash
git add migration_scripts/mealie_mapping.py tests/test_mealie_mapping.py
git commit -m "feat(mealie): recipe_to_payload emits servings + structured ingredients"
```

---

## Task 9: Resolvers (live + dry-run)

**Files:**
- Modify: `migration_scripts/migrate_to_mealie.py`
- Test: `tests/test_migrate_to_mealie.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_migrate_to_mealie.py`:

```python
import pytest

from migration_scripts.migrate_to_mealie import MealieRefResolver, DryRunResolver


class _Client:
    def __init__(self):
        self.created_foods, self.created_labels, self.updated = [], [], []

    def list_foods(self):
        return [{"id": "f1", "name": "Kale", "label": {"name": "Produce"}},
                {"id": "f2", "name": "Salt", "label": None}]

    def list_units(self):
        return [{"id": "u1", "name": "cup"}]

    def list_labels(self):
        return [{"id": "l1", "name": "Produce"}]

    def create_label(self, name):
        lab = {"id": f"l-{name}", "name": name}
        self.created_labels.append(name)
        return lab

    def create_food(self, name, label_id=None):
        food = {"id": f"f-{name}", "name": name, "label": {"id": label_id}}
        self.created_foods.append((name, label_id))
        return food

    def update_food(self, food_id, payload):
        self.updated.append(food_id)
        return {**payload, "id": food_id}


def test_resolve_unit_existing_and_none():
    r = MealieRefResolver(_Client())
    assert r.resolve_unit("cup") == {"id": "u1", "name": "cup"}
    assert r.resolve_unit("") is None
    assert r.resolve_unit("(none)") is None


def test_resolve_unit_missing_raises():
    r = MealieRefResolver(_Client())
    with pytest.raises(KeyError, match="unit"):
        r.resolve_unit("furlong")


def test_resolve_food_match_existing():
    r = MealieRefResolver(_Client())
    assert r.resolve_food("Kale", "match", "Produce") == {"id": "f1", "name": "Kale"}


def test_resolve_food_match_missing_raises():
    r = MealieRefResolver(_Client())
    with pytest.raises(KeyError, match="food"):
        r.resolve_food("Unicorn", "match", "")


def test_resolve_food_match_assigns_missing_label():
    client = _Client()
    r = MealieRefResolver(client)
    r.resolve_food("Salt", "match", "Pantry")  # Salt has no label -> update + new label
    assert client.created_labels == ["Pantry"]
    assert client.updated == ["f2"]


def test_resolve_food_create_makes_food_and_caches():
    client = _Client()
    r = MealieRefResolver(client)
    a = r.resolve_food("Rau Sauce", "create", "Sauces")
    b = r.resolve_food("Rau Sauce", "create", "Sauces")
    assert a == b
    assert client.created_foods == [("Rau Sauce", "l-Sauces")]   # created once
    assert client.created_labels == ["Sauces"]


def test_dry_run_resolver_returns_name_stubs():
    r = DryRunResolver()
    assert r.resolve_unit("cup") == {"name": "cup"}
    assert r.resolve_unit("") is None
    assert r.resolve_food("Kale", "match", "Produce") == {"name": "Kale"}
```

- [ ] **Step 2: Run to verify they fail**

Run: `uv run pytest tests/test_migrate_to_mealie.py -v`
Expected: FAIL — `ImportError: cannot import name 'MealieRefResolver'`

- [ ] **Step 3: Implement**

In `migration_scripts/migrate_to_mealie.py`, add after the imports:

```python
class DryRunResolver:
    """No-I/O resolver: returns name-only stubs so dry-run can build payloads."""

    def resolve_unit(self, name):
        if not name or name == "(none)":
            return None
        return {"name": name}

    def resolve_food(self, name, action, label):
        return {"name": name}


class MealieRefResolver:
    """Resolves mapped food/unit names to Mealie refs, creating foods/labels as needed.

    Loads the live foods/units/labels once and caches every lookup, so the 1,096
    ingredient rows create each new food/label at most once.
    """

    def __init__(self, client):
        self.client = client
        self._foods = {f["name"].lower(): f for f in client.list_foods()}
        self._units = {u["name"].lower(): u for u in client.list_units()}
        self._labels = {lab["name"].lower(): lab for lab in client.list_labels()}

    def _label_id(self, label):
        if not label:
            return None
        key = label.lower()
        if key not in self._labels:
            self._labels[key] = self.client.create_label(label)
        return self._labels[key]["id"]

    def resolve_unit(self, name):
        if not name or name == "(none)":
            return None
        unit = self._units.get(name.lower())
        if unit is None:
            raise KeyError(f"unit '{name}' not in Mealie; fix unit_map.csv")
        return {"id": unit["id"], "name": unit["name"]}

    def resolve_food(self, name, action, label):
        key = name.lower()
        food = self._foods.get(key)
        if action == "match":
            if food is None:
                raise KeyError(f"food '{name}' not in Mealie; fix food_map.csv")
            if not food.get("label") and label:
                label_id = self._label_id(label)
                food = self.client.update_food(food["id"], {**food, "labelId": label_id})
                self._foods[key] = food
        else:  # create
            if food is None:
                food = self.client.create_food(name, self._label_id(label))
                self._foods[key] = food
        return {"id": food["id"], "name": food["name"]}
```

- [ ] **Step 4: Run to verify pass**

Run: `uv run pytest tests/test_migrate_to_mealie.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add migration_scripts/migrate_to_mealie.py tests/test_migrate_to_mealie.py
git commit -m "feat(mealie): add live + dry-run ref resolvers"
```

---

## Task 10: purge / import subcommands + guard wiring

**Files:**
- Modify: `migration_scripts/migrate_to_mealie.py`
- Test: `tests/test_migrate_to_mealie.py`

The orchestrator gains two verbs, loads the maps, runs the guard before importing, and threads `food_map`/`unit_map`/`resolver` into `recipe_to_payload`.

- [ ] **Step 1: Write failing tests**

Add to `tests/test_migrate_to_mealie.py`:

```python
from types import SimpleNamespace
from migration_scripts.migrate_to_mealie import purge_recipes, import_recipe


def _recipe():
    ing = SimpleNamespace(quantity=1.0, unit="cup", notes=None, order=0,
                          ingredient=SimpleNamespace(name="Flour"))
    return SimpleNamespace(
        name="Bread", description="", yield_amount=2.0, yield_unit="servings",
        prep_time_minutes=None, cook_time_minutes=None, total_time_minutes=None,
        source_url=None, source=None, calories=None,
        cuisine=None, protein=None, difficulty=None, diets=[],
        category=None, comments=[],
        components=[SimpleNamespace(name="Main", ingredients=[ing])],
        instructions=[],
    )


def test_purge_recipes_deletes_each_slug():
    deleted = []

    class C:
        def delete_recipe(self, slug):
            deleted.append(slug)
            return True

    assert purge_recipes(C(), [_recipe()]) == 1
    assert deleted == ["bread"]


def test_import_recipe_dry_run_builds_structured(capsys):
    fm = {"flour": {"mealie_food": "Flour", "action": "match", "label": "", "flags": ""}}
    um = {"cup": {"mealie_unit": "cup", "flags": ""}}
    result = import_recipe(None, _recipe(), True, True, fm, um, DryRunResolver())
    assert result == "created"
    assert "Bread" in capsys.readouterr().out
```

- [ ] **Step 2: Run to verify they fail**

Run: `uv run pytest tests/test_migrate_to_mealie.py -k "purge or dry_run_builds" -v`
Expected: FAIL — `ImportError: cannot import name 'purge_recipes'`

- [ ] **Step 3: Implement**

Rewrite `migration_scripts/migrate_to_mealie.py`'s `import_recipe`, add `purge_recipes`, and replace `main` with subcommand handling. Update the module imports to add the mapping helpers and `Ingredient` if needed.

Replace `import_recipe` with:

```python
def import_recipe(client, recipe, dry_run, skip_existing, food_map, unit_map, resolver):
    slug = m.slugify(recipe.name)
    if not dry_run and skip_existing and client.recipe_exists(slug):
        return "skipped"

    cats, tags = resolve_refs(client, recipe, dry_run)

    if dry_run:
        payload = m.recipe_to_payload(
            recipe, {"slug": slug, "name": recipe.name}, cats, tags, food_map, unit_map, resolver)
        print(f"[dry-run] {recipe.name} -> {slug} "
              f"({len(payload['recipeIngredient'])} ingredients, "
              f"{len(payload['recipeInstructions'])} steps, "
              f"servings={payload['recipeServings']}, tags={[t['name'] for t in tags]})")
        return "created"

    new_slug = client.create_recipe(recipe.name)
    shell = client.get_recipe(new_slug)
    payload = m.recipe_to_payload(recipe, shell, cats, tags, food_map, unit_map, resolver)
    client.update_recipe(new_slug, payload)
    return "created"
```

Add:

```python
def purge_recipes(client, recipes):
    deleted = 0
    for recipe in recipes:
        if client.delete_recipe(m.slugify(recipe.name)):
            deleted += 1
            print(f"Deleted: {recipe.name}")
    return deleted


DEFAULT_FOOD_MAP = os.path.join(os.path.dirname(__file__), "food_map.csv")
DEFAULT_UNIT_MAP = os.path.join(os.path.dirname(__file__), "unit_map.csv")
```

Replace `main` with:

```python
def _build_client(args):
    token = os.environ.get("MEALIE_API_TOKEN")
    if not token:
        raise SystemExit("MEALIE_API_TOKEN is required")
    base = os.environ.get("MEALIE_URL", "https://recipes.qwertyshoe.com")
    return MealieClient(base, token)


def run_purge(args):
    client = _build_client(args)
    session = SessionLocal()
    try:
        recipes = load_recipes(session)
        count = purge_recipes(client, recipes)
    finally:
        session.close()
    print(f"\nDone. deleted={count}")
    return 0


def run_import(args):
    food_map = m.load_food_map(args.food_map)
    unit_map = m.load_unit_map(args.unit_map)

    session = SessionLocal()
    try:
        recipes = load_recipes(session)
        missing_foods, missing_units = m.missing_map_entries(recipes, food_map, unit_map)
        if missing_foods or missing_units:
            print("ABORT: maps do not cover all source values.")
            if missing_foods:
                print(f"  Missing foods ({len(missing_foods)}): {missing_foods}")
            if missing_units:
                print(f"  Missing units ({len(missing_units)}): {missing_units}")
            return 1

        if args.dry_run:
            resolver = DryRunResolver()
            client = None
        else:
            client = _build_client(args)
            resolver = MealieRefResolver(client)

        print(f"Found {len(recipes)} recipes.")
        counts = {"created": 0, "skipped": 0, "failed": 0}
        for recipe in recipes:
            if m.should_skip_recipe(recipe.name):
                print(f"Skipping meta-recipe: {recipe.name}")
                counts["skipped"] += 1
                continue
            try:
                result = import_recipe(client, recipe, args.dry_run, args.skip_existing,
                                       food_map, unit_map, resolver)
                counts[result] += 1
                if result == "skipped":
                    print(f"Already in Mealie, skipping: {recipe.name}")
            except Exception as exc:  # noqa: BLE001 - keep going, report at end
                counts["failed"] += 1
                print(f"FAILED {recipe.name}: {exc}")
    finally:
        session.close()

    print(f"\nDone. created={counts['created']} skipped={counts['skipped']} failed={counts['failed']}")
    return 1 if counts["failed"] else 0


def main(argv=None):
    parser = argparse.ArgumentParser(description="Import recipe_api recipes into Mealie")
    sub = parser.add_subparsers(dest="command", required=True)

    p_import = sub.add_parser("import", help="import recipes with structured ingredients")
    p_import.add_argument("--dry-run", action="store_true", help="map and print without calling Mealie")
    p_import.add_argument("--no-skip-existing", dest="skip_existing", action="store_false",
                          help="import even if a recipe with the same slug already exists")
    p_import.add_argument("--food-map", default=DEFAULT_FOOD_MAP)
    p_import.add_argument("--unit-map", default=DEFAULT_UNIT_MAP)
    p_import.set_defaults(skip_existing=True, func=run_import)

    p_purge = sub.add_parser("purge", help="delete previously imported recipes by slug")
    p_purge.set_defaults(func=run_purge)

    args = parser.parse_args(argv)
    return args.func(args)
```

Ensure the module still imports `argparse`, `os`, `sys`, `SessionLocal`, `MealieClient`, and `mealie_mapping as m` (already present).

- [ ] **Step 4: Run the whole suite + lint**

Run: `uv run pytest && uv run ruff check .`
Expected: all tests PASS, ruff clean.

- [ ] **Step 5: Commit**

```bash
git add migration_scripts/migrate_to_mealie.py tests/test_migrate_to_mealie.py
git commit -m "feat(mealie): add purge/import subcommands with map guard"
```

---

## Task 11: Operational run — generate maps, review, re-import

This task is interactive (live Mealie + Claude), not coded. No TDD loop.

- [ ] **Step 1: Export the seed**

```bash
MEALIE_API_TOKEN=<token> uv run python -m migration_scripts.export_mealie_seed
```
Confirm `migration_scripts/seed/` now has `foods.json`, `units.json`, `labels.json`, `source_foods.txt`, `source_units.txt`. Verify the labels endpoint worked (non-empty `labels.json`); if it failed, apply the Task 1 note and re-run.

- [ ] **Step 2: Claude generates the maps**

Ask Claude (this session or a fresh one) to read the five seed files and write `migration_scripts/food_map.csv` (columns: `source_food,action,mealie_food,label,flags`) and `migration_scripts/unit_map.csv` (columns: `source_unit,mealie_unit,flags`), following the matching rules in the design doc (exact → semantic/fuzzy, typo/size normalization, carry existing labels, propose labels for unlabeled/created foods, `(none)` for food-only/`to-taste` units, scannable `flags`).

- [ ] **Step 3: Human review**

Open both CSVs. Skim the `flags` column first (`low-confidence`, `unmatched`, `new-label?`, `typo-fixed`). Fix any wrong `mealie_food`, `action`, or `label`. Confirm every `(none)` unit and every `to-taste` flag.

- [ ] **Step 4: Dry run**

```bash
uv run python -m migration_scripts.migrate_to_mealie import --dry-run
```
Expected: prints one line per recipe with ingredient/step counts, `servings=…`, and prefixed tags; no ABORT. If it ABORTs with missing foods/units, add those rows to the maps and repeat.

- [ ] **Step 5: Wipe and re-import**

```bash
MEALIE_API_TOKEN=<token> uv run python -m migration_scripts.migrate_to_mealie purge
MEALIE_API_TOKEN=<token> uv run python -m migration_scripts.migrate_to_mealie import --no-skip-existing
```
Expected: `deleted=131` then `created=… failed=0`.

- [ ] **Step 6: Spot-check in Mealie**

Open 3-4 recipes in the Mealie UI. Confirm: ingredients show structured food + unit + quantity (amounts enabled), "to taste" items are unmeasured, servings is a number, and tags read `Protein: …` / `Difficulty: …`. Open a shopping list and confirm foods group under their labels.

- [ ] **Step 7: Commit the maps**

```bash
git add migration_scripts/food_map.csv migration_scripts/unit_map.csv
git commit -m "chore(mealie): add reviewed food/unit mapping files"
```

---

## Self-Review Notes

- **Spec coverage:** export (T2) · Claude-generated name-based maps (T5 loaders, T11 generation) · structured ingredients with to-taste/originalText (T6) · create-or-fetch foods+labels, cached, label assignment for unlabeled matches (T9) · zero-guess hard-error guard (T7, T10) · purge+import verbs with dry-run (T10) · yield→servings (T3) · prefixed tags incl. dormant Diet (T4) · category unchanged (left as-is in `resolve_refs`). All covered.
- **`seed/` directory:** generated output; add `migration_scripts/seed/` to `.gitignore` during T2 if you don't want the JSON committed (optional — not required by the plan).
- **Mealie field/endpoint verification:** `recipeServings` (T8) and `/api/groups/labels` (T1) are confirmed live in T11 step 1/4 before the destructive re-import.
