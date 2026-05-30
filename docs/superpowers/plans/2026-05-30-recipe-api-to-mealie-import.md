# recipe_api → Mealie Import Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A one-off script that reads the cleaned recipes from `recipe_api`'s SQLite DB and creates them in Mealie via its REST API.

**Architecture:** Three modules in `migration_scripts/` — a pure mapping layer (`mealie_mapping.py`, fully unit-tested), a thin stdlib-`urllib` Mealie API client (`mealie_client.py`), and a CLI orchestrator (`migrate_to_mealie.py`) that reuses `recipe_api`'s SQLAlchemy models/`SessionLocal`. The pure mapping functions are built TDD-first; the client is written against a live-verified API contract; the orchestrator ties them together with dry-run and idempotency.

**Tech Stack:** Python 3.11+, SQLAlchemy 2.x (existing models), stdlib `urllib`/`json`, pytest, uv.

**Reference spec:** `docs/superpowers/specs/2026-05-30-recipe-api-to-mealie-import-design.md`

---

## Files

| File | Action |
|---|---|
| `migration_scripts/mealie_mapping.py` | Create — pure transform functions (recipe_api model → Mealie payload) |
| `migration_scripts/mealie_client.py` | Create — stdlib-urllib Mealie REST client |
| `migration_scripts/migrate_to_mealie.py` | Create — CLI orchestrator |
| `tests/test_mealie_mapping.py` | Create — unit tests for the mapping layer |
| `tests/test_mealie_client.py` | Create — unit tests for client caching/existence logic |

**Run command (final):**
```bash
cd /mnt/fastdata/recipe_api
MEALIE_API_TOKEN=<token> uv run python -m migration_scripts.migrate_to_mealie --dry-run
```

All commands below run from `/mnt/fastdata/recipe_api`. All commits are in the
`recipe_api` repo.

---

## Task 1: Scaffold the mapping module and prove the test harness works

**Files:**
- Create: `migration_scripts/mealie_mapping.py`
- Create: `tests/test_mealie_mapping.py`

- [ ] **Step 1: Write a failing test for `slugify`**

Create `tests/test_mealie_mapping.py`:

```python
from migration_scripts.mealie_mapping import slugify


def test_slugify_lowercases_and_hyphenates():
    assert slugify("Mom's Apple Pie!") == "mom-s-apple-pie"


def test_slugify_collapses_and_strips_separators():
    assert slugify("  Beef   &  Broccoli  ") == "beef-broccoli"
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `uv run pytest tests/test_mealie_mapping.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'migration_scripts.mealie_mapping'`

- [ ] **Step 3: Implement `slugify`**

Create `migration_scripts/mealie_mapping.py`:

```python
"""Pure functions mapping recipe_api models to Mealie API payloads.

No I/O here — everything is unit-testable against in-memory model objects.
"""

import re


def slugify(name: str) -> str:
    """Mealie-style slug: lowercase, non-alphanumerics -> '-', collapsed, stripped."""
    s = (name or "").lower()
    s = re.sub(r"[^a-z0-9]+", "-", s)
    return s.strip("-")
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `uv run pytest tests/test_mealie_mapping.py -q`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add migration_scripts/mealie_mapping.py tests/test_mealie_mapping.py
git commit -m "feat(migrate): add slugify for Mealie import mapping"
```

---

## Task 2: Quantity and time formatters

**Files:**
- Modify: `migration_scripts/mealie_mapping.py`
- Modify: `tests/test_mealie_mapping.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/test_mealie_mapping.py`:

```python
from migration_scripts.mealie_mapping import format_quantity, format_time


def test_format_quantity_integer_drops_decimal():
    assert format_quantity(2.0) == "2"


def test_format_quantity_trims_trailing_zeros():
    assert format_quantity(0.5) == "0.5"
    assert format_quantity(0.333) == "0.333"


def test_format_quantity_zero_and_none_are_empty():
    assert format_quantity(0) == ""
    assert format_quantity(None) == ""


def test_format_time_minutes():
    assert format_time(30) == "30 minutes"


def test_format_time_zero_or_none_is_none():
    assert format_time(0) is None
    assert format_time(None) is None
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/test_mealie_mapping.py -q`
Expected: FAIL — `ImportError: cannot import name 'format_quantity'`

- [ ] **Step 3: Implement the formatters**

Append to `migration_scripts/mealie_mapping.py`:

```python
from typing import Optional


def format_quantity(quantity) -> str:
    """Render a quantity for display. 0/None -> '' (unmeasured, e.g. 'To Taste')."""
    if quantity is None or quantity == 0:
        return ""
    q = float(quantity)
    if q.is_integer():
        return str(int(q))
    return ("%f" % q).rstrip("0").rstrip(".")


def format_time(minutes: Optional[int]) -> Optional[str]:
    """Minutes -> 'N minutes'. 0/None -> None (Mealie omits empty times)."""
    if not minutes:
        return None
    return f"{int(minutes)} minutes"
```

- [ ] **Step 4: Run to verify pass**

Run: `uv run pytest tests/test_mealie_mapping.py -q`
Expected: PASS (all tests)

- [ ] **Step 5: Commit**

```bash
git add migration_scripts/mealie_mapping.py tests/test_mealie_mapping.py
git commit -m "feat(migrate): add quantity and time formatters"
```

---

## Task 3: Ingredient line builder and section-aware ingredient list

**Files:**
- Modify: `migration_scripts/mealie_mapping.py`
- Modify: `tests/test_mealie_mapping.py`

Background: `Recipe.components` is a list of `RecipeComponent` (e.g. "Main",
"Frosting"); each has `.ingredients` (a list of `RecipeIngredient` with `.quantity`,
`.unit`, `.notes`, `.order`, and `.ingredient.name`). Section titles are attached to
the first ingredient of each non-"Main" component.

- [ ] **Step 1: Write failing tests**

Append to `tests/test_mealie_mapping.py`:

```python
from types import SimpleNamespace

from migration_scripts.mealie_mapping import build_ingredient_line, build_ingredients


def _ri(quantity, unit, name, notes=None, order=0):
    return SimpleNamespace(
        quantity=quantity, unit=unit, notes=notes, order=order,
        ingredient=SimpleNamespace(name=name),
    )


def _component(name, ingredients):
    return SimpleNamespace(name=name, ingredients=ingredients)


def test_build_ingredient_line_full():
    assert build_ingredient_line(2.0, "cup", "Flour", "sifted") == "2 cup Flour, sifted"


def test_build_ingredient_line_to_taste_drops_zero_quantity():
    assert build_ingredient_line(0, "To Taste", "Salt", None) == "To Taste Salt"


def test_build_ingredients_single_main_component_has_no_title():
    recipe = SimpleNamespace(components=[
        _component("Main", [_ri(1.0, "cup", "Sugar", order=0)]),
    ])
    items = build_ingredients(recipe)
    assert items == [{"title": None, "note": "1 cup Sugar", "disableAmount": True, "quantity": None}]


def test_build_ingredients_titles_non_main_sections_on_first_line():
    recipe = SimpleNamespace(components=[
        _component("Main", [_ri(1.0, "cup", "Flour", order=1), _ri(2.0, None, "Eggs", order=0)]),
        _component("Frosting", [_ri(0.5, "cup", "Butter", order=0)]),
    ])
    items = build_ingredients(recipe)
    # ordered by .order within component; Main has no title; Frosting titled on first line
    assert items[0] == {"title": None, "note": "2 Eggs", "disableAmount": True, "quantity": None}
    assert items[1] == {"title": None, "note": "1 cup Flour", "disableAmount": True, "quantity": None}
    assert items[2] == {"title": "Frosting", "note": "0.5 cup Butter", "disableAmount": True, "quantity": None}
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/test_mealie_mapping.py -q`
Expected: FAIL — `ImportError: cannot import name 'build_ingredient_line'`

- [ ] **Step 3: Implement the builders**

Append to `migration_scripts/mealie_mapping.py`:

```python
def build_ingredient_line(quantity, unit, name, notes) -> str:
    """'{qty} {unit} {name}, {notes}' — empty parts dropped."""
    parts = [p for p in [format_quantity(quantity), unit, name] if p]
    line = " ".join(parts)
    if notes:
        line = f"{line}, {notes}"
    return line


def build_ingredients(recipe) -> list:
    """Mealie recipeIngredient entries (display strings, section titles)."""
    items = []
    for component in recipe.components:
        first = True
        for ri in sorted(component.ingredients, key=lambda x: x.order):
            line = build_ingredient_line(ri.quantity, ri.unit, ri.ingredient.name, ri.notes)
            title = component.name if (first and component.name and component.name != "Main") else None
            items.append({
                "title": title,
                "note": line,
                "disableAmount": True,
                "quantity": None,
            })
            first = False
    return items
```

- [ ] **Step 4: Run to verify pass**

Run: `uv run pytest tests/test_mealie_mapping.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add migration_scripts/mealie_mapping.py tests/test_mealie_mapping.py
git commit -m "feat(migrate): build section-aware Mealie ingredient list"
```

---

## Task 4: Instructions, yield, tags, and notes builders

**Files:**
- Modify: `migration_scripts/mealie_mapping.py`
- Modify: `tests/test_mealie_mapping.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/test_mealie_mapping.py`:

```python
from migration_scripts.mealie_mapping import (
    build_instructions, build_yield, tag_names, build_notes, should_skip_recipe,
)


def test_build_instructions_sorted_by_step_number():
    recipe = SimpleNamespace(instructions=[
        SimpleNamespace(step_number=2, text="Bake"),
        SimpleNamespace(step_number=1, text="Mix"),
    ])
    assert build_instructions(recipe) == [{"text": "Mix"}, {"text": "Bake"}]


def test_build_yield_amount_and_unit():
    recipe = SimpleNamespace(yield_amount=4.0, yield_unit="servings")
    assert build_yield(recipe) == "4 servings"


def test_build_yield_unit_only():
    recipe = SimpleNamespace(yield_amount=None, yield_unit="1 loaf")
    assert build_yield(recipe) == "1 loaf"


def test_tag_names_collects_non_null_cuisine_protein_difficulty():
    recipe = SimpleNamespace(
        cuisine="Italian", protein="Chicken",
        difficulty=SimpleNamespace(value="Easy"),
    )
    assert tag_names(recipe) == ["Italian", "Chicken", "Easy"]


def test_tag_names_skips_nulls():
    recipe = SimpleNamespace(cuisine=None, protein="Beef", difficulty=None)
    assert tag_names(recipe) == ["Beef"]


def test_build_notes_includes_source_and_comments():
    recipe = SimpleNamespace(
        source="Grandma's cookbook",
        comments=[SimpleNamespace(text="Migrated Note:\n\nUse fresh basil")],
    )
    assert build_notes(recipe) == [
        {"title": "Source", "text": "Grandma's cookbook"},
        {"title": "Note", "text": "Migrated Note:\n\nUse fresh basil"},
    ]


def test_should_skip_meta_recipe():
    assert should_skip_recipe("<<Base Sauce>>") is True
    assert should_skip_recipe("Tomato Sauce") is False
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/test_mealie_mapping.py -q`
Expected: FAIL — `ImportError: cannot import name 'build_instructions'`

- [ ] **Step 3: Implement the builders**

Append to `migration_scripts/mealie_mapping.py`:

```python
def build_instructions(recipe) -> list:
    steps = sorted(recipe.instructions, key=lambda i: i.step_number)
    return [{"text": s.text} for s in steps]


def build_yield(recipe) -> str:
    amount = format_quantity(recipe.yield_amount)
    unit = recipe.yield_unit or ""
    return " ".join(p for p in [amount, unit] if p).strip()


def tag_names(recipe) -> list:
    names = []
    for value in (recipe.cuisine, recipe.protein, recipe.difficulty):
        if value:
            names.append(value.value if hasattr(value, "value") else str(value))
    return names


def build_notes(recipe) -> list:
    notes = []
    if recipe.source:
        notes.append({"title": "Source", "text": recipe.source})
    for comment in recipe.comments:
        if comment.text:
            notes.append({"title": "Note", "text": comment.text})
    return notes


def should_skip_recipe(name: str) -> bool:
    """Meta-recipes are wrapped in << >> (mirrors migrate_access_recipes.py)."""
    if not name:
        return False
    s = name.strip()
    return s.startswith("<<") and s.endswith(">>")
```

- [ ] **Step 4: Run to verify pass**

Run: `uv run pytest tests/test_mealie_mapping.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add migration_scripts/mealie_mapping.py tests/test_mealie_mapping.py
git commit -m "feat(migrate): add instructions, yield, tags, notes builders"
```

---

## Task 5: Full recipe → Mealie payload mapper

**Files:**
- Modify: `migration_scripts/mealie_mapping.py`
- Modify: `tests/test_mealie_mapping.py`

`recipe_to_payload` merges everything into the shell Mealie returned from create,
then overwrites fields. Category and tag references (already-resolved Mealie
organizer dicts) are passed in so this function stays pure.

- [ ] **Step 1: Write failing test**

Append to `tests/test_mealie_mapping.py`:

```python
from migration_scripts.mealie_mapping import recipe_to_payload


def _sample_recipe():
    return SimpleNamespace(
        name="Tomato Soup",
        description="Warm and simple",
        yield_amount=4.0, yield_unit="servings",
        prep_time_minutes=10, cook_time_minutes=20, total_time_minutes=30,
        source_url="https://example.com/soup", source="Family recipe",
        calories=180,
        cuisine="Italian", protein=None, difficulty=SimpleNamespace(value="Easy"),
        components=[_component("Main", [_ri(1.0, "can", "Tomatoes", order=0)])],
        instructions=[SimpleNamespace(step_number=1, text="Simmer")],
        comments=[],
    )


def test_recipe_to_payload_maps_all_fields():
    recipe = _sample_recipe()
    shell = {"id": "abc", "slug": "tomato-soup", "name": "Tomato Soup", "nutrition": {}}
    cat_refs = [{"id": "c1", "name": "Soup", "slug": "soup"}]
    tag_refs = [{"id": "t1", "name": "Italian", "slug": "italian"}]

    payload = recipe_to_payload(recipe, shell, cat_refs, tag_refs)

    assert payload["id"] == "abc"  # shell fields preserved
    assert payload["description"] == "Warm and simple"
    assert payload["recipeYield"] == "4 servings"
    assert payload["prepTime"] == "10 minutes"
    assert payload["performTime"] == "20 minutes"
    assert payload["totalTime"] == "30 minutes"
    assert payload["orgURL"] == "https://example.com/soup"
    assert payload["recipeIngredient"] == [
        {"title": None, "note": "1 can Tomatoes", "disableAmount": True, "quantity": None}
    ]
    assert payload["recipeInstructions"] == [{"text": "Simmer"}]
    assert payload["recipeCategory"] == cat_refs
    assert payload["tags"] == tag_refs
    assert payload["nutrition"]["calories"] == "180"
    assert payload["notes"] == [{"title": "Source", "text": "Family recipe"}]
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/test_mealie_mapping.py -q`
Expected: FAIL — `ImportError: cannot import name 'recipe_to_payload'`

- [ ] **Step 3: Implement the mapper**

Append to `migration_scripts/mealie_mapping.py`:

```python
def recipe_to_payload(recipe, shell: dict, category_refs: list, tag_refs: list) -> dict:
    """Merge mapped fields onto the Mealie shell returned by create/get."""
    payload = dict(shell)
    payload["name"] = recipe.name
    payload["description"] = recipe.description or ""
    payload["recipeYield"] = build_yield(recipe)
    payload["prepTime"] = format_time(recipe.prep_time_minutes)
    payload["performTime"] = format_time(recipe.cook_time_minutes)
    payload["totalTime"] = format_time(recipe.total_time_minutes)
    payload["orgURL"] = recipe.source_url
    payload["recipeIngredient"] = build_ingredients(recipe)
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

- [ ] **Step 4: Run to verify pass**

Run: `uv run pytest tests/test_mealie_mapping.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add migration_scripts/mealie_mapping.py tests/test_mealie_mapping.py
git commit -m "feat(migrate): add full recipe-to-Mealie payload mapper"
```

---

## Task 6: Verify the Mealie API contract live (before building the client)

This task confirms the exact request/response shapes against the running Mealie so
the client (Task 7) matches reality. **No file changes** — it records findings.

- [ ] **Step 1: Generate a Mealie API token**

In Mealie (`https://recipes.qwertyshoe.com`), log in as admin → **profile / Manage
Your API Tokens** → create a token named `recipe-import`. Copy it. Export it:

```bash
export MEALIE_API_TOKEN=<paste-token>
export MEALIE_URL=https://recipes.qwertyshoe.com
```

- [ ] **Step 2: Confirm auth and the create→get→update shapes**

```bash
# create returns the new slug (a JSON string)
curl -s -X POST "$MEALIE_URL/api/recipes" \
  -H "Authorization: Bearer $MEALIE_API_TOKEN" -H "Content-Type: application/json" \
  -d '{"name":"ZZ Import Probe"}'; echo

# fetch the shell
curl -s "$MEALIE_URL/api/recipes/zz-import-probe" \
  -H "Authorization: Bearer $MEALIE_API_TOKEN" | python3 -m json.tool | head -40
```

Expected: the POST prints `"zz-import-probe"` (a quoted slug string). The GET prints
a recipe object including keys `id`, `slug`, `name`, `recipeIngredient`,
`recipeInstructions`, `recipeYield`, `prepTime`, `performTime`, `totalTime`,
`orgURL`, `recipeCategory`, `tags`, `nutrition`, `notes`.

**Record any key-name differences** (e.g. `orgURL` casing) — if a field name
differs from what the mapper writes, fix the constant in `mealie_mapping.py` and its
test before continuing.

- [ ] **Step 3: Confirm organizer endpoints and clean up the probe**

```bash
# list categories (note the response wrapper: {"items":[...]} vs bare list)
curl -s "$MEALIE_URL/api/organizers/categories?perPage=-1" \
  -H "Authorization: Bearer $MEALIE_API_TOKEN" | python3 -m json.tool | head -20

# create a category (returns {id,name,slug})
curl -s -X POST "$MEALIE_URL/api/organizers/categories" \
  -H "Authorization: Bearer $MEALIE_API_TOKEN" -H "Content-Type: application/json" \
  -d '{"name":"ZZ Probe Cat"}'; echo

# delete the probe recipe and probe category in the UI (or via DELETE) so they don't linger
curl -s -X DELETE "$MEALIE_URL/api/recipes/zz-import-probe" \
  -H "Authorization: Bearer $MEALIE_API_TOKEN" -o /dev/null -w "delete: %{http_code}\n"
```

Expected: categories list is an object with an `items` array; category create returns
an object with `id`, `name`, `slug`; recipe delete returns `200`. **Record whether
the categories list is `{"items":[...]}` or a bare list** — Task 7's `_categories()`
must match.

---

## Task 7: Mealie API client

**Files:**
- Create: `migration_scripts/mealie_client.py`
- Create: `tests/test_mealie_client.py`

The low-level `_request` is the only thing that touches the network, so tests mock
it. Adjust `_categories`/`_tags` unwrapping to match the Task 6 finding (the code
below assumes the `{"items":[...]}` wrapper, which is Mealie's default).

- [ ] **Step 1: Write failing tests**

Create `tests/test_mealie_client.py`:

```python
import urllib.error

import pytest

from migration_scripts.mealie_client import MealieClient


def _client():
    return MealieClient("https://mealie.example", "tok")


def test_get_or_create_category_uses_cache_and_creates_missing(monkeypatch):
    client = _client()
    calls = []

    def fake_request(method, path, body=None):
        calls.append((method, path, body))
        if method == "GET" and path.startswith("/api/organizers/categories"):
            return {"items": [{"id": "1", "name": "Soup", "slug": "soup"}]}
        if method == "POST" and path == "/api/organizers/categories":
            return {"id": "2", "name": body["name"], "slug": "dessert"}
        raise AssertionError(f"unexpected {method} {path}")

    monkeypatch.setattr(client, "_request", fake_request)

    # existing (case-insensitive) -> no POST, served from the single GET
    assert client.get_or_create_category("soup")["id"] == "1"
    # missing -> one POST
    assert client.get_or_create_category("Dessert")["id"] == "2"
    # second lookup of the new one is cached -> still only one POST total
    assert client.get_or_create_category("dessert")["id"] == "2"

    assert sum(1 for m, p, _ in calls if m == "POST") == 1
    assert sum(1 for m, p, _ in calls if m == "GET") == 1


def test_recipe_exists_true_false(monkeypatch):
    client = _client()

    def fake_request(method, path, body=None):
        if path.endswith("/exists-slug"):
            return {"slug": "exists-slug"}
        raise urllib.error.HTTPError(path, 404, "Not Found", {}, None)

    monkeypatch.setattr(client, "_request", fake_request)
    assert client.recipe_exists("exists-slug") is True
    assert client.recipe_exists("missing-slug") is False


def test_recipe_exists_reraises_non_404(monkeypatch):
    client = _client()

    def fake_request(method, path, body=None):
        raise urllib.error.HTTPError(path, 500, "Server Error", {}, None)

    monkeypatch.setattr(client, "_request", fake_request)
    with pytest.raises(urllib.error.HTTPError):
        client.recipe_exists("any")
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/test_mealie_client.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'migration_scripts.mealie_client'`

- [ ] **Step 3: Implement the client**

Create `migration_scripts/mealie_client.py`:

```python
"""Minimal Mealie REST client built on stdlib urllib (no extra deps)."""

import json
import urllib.error
import urllib.request


class MealieClient:
    def __init__(self, base_url: str, token: str):
        self.base = base_url.rstrip("/")
        self.token = token
        self._cat_cache = None
        self._tag_cache = None

    def _request(self, method: str, path: str, body=None):
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(
            f"{self.base}{path}",
            data=data,
            method=method,
            headers={
                "Authorization": f"Bearer {self.token}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
        )
        with urllib.request.urlopen(req) as resp:
            raw = resp.read()
            return json.loads(raw) if raw else None

    # --- recipes ---
    def recipe_exists(self, slug: str) -> bool:
        try:
            self._request("GET", f"/api/recipes/{slug}")
            return True
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                return False
            raise

    def create_recipe(self, name: str) -> str:
        return self._request("POST", "/api/recipes", {"name": name})

    def get_recipe(self, slug: str) -> dict:
        return self._request("GET", f"/api/recipes/{slug}")

    def update_recipe(self, slug: str, payload: dict) -> dict:
        return self._request("PUT", f"/api/recipes/{slug}", payload)

    # --- organizers ---
    def _load(self, kind: str) -> dict:
        resp = self._request("GET", f"/api/organizers/{kind}?perPage=-1")
        items = resp["items"] if isinstance(resp, dict) else resp
        return {item["name"].lower(): item for item in items}

    def _get_or_create(self, kind: str, cache_attr: str, name: str) -> dict:
        cache = getattr(self, cache_attr)
        if cache is None:
            cache = self._load(kind)
            setattr(self, cache_attr, cache)
        key = name.lower()
        if key not in cache:
            cache[key] = self._request("POST", f"/api/organizers/{kind}", {"name": name})
        return cache[key]

    def get_or_create_category(self, name: str) -> dict:
        return self._get_or_create("categories", "_cat_cache", name)

    def get_or_create_tag(self, name: str) -> dict:
        return self._get_or_create("tags", "_tag_cache", name)
```

- [ ] **Step 4: Run to verify pass**

Run: `uv run pytest tests/test_mealie_client.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add migration_scripts/mealie_client.py tests/test_mealie_client.py
git commit -m "feat(migrate): add urllib-based Mealie API client"
```

---

## Task 8: CLI orchestrator

**Files:**
- Create: `migration_scripts/migrate_to_mealie.py`

Ties it together: read DB via `SessionLocal` (eager-loading relationships), map each
recipe, resolve category/tag refs through the client, and create→get→update in
Mealie. Supports `--dry-run` (no network) and `--skip-existing` (default on).

- [ ] **Step 1: Implement the orchestrator**

Create `migration_scripts/migrate_to_mealie.py`:

```python
"""Import recipe_api recipes into Mealie.

Usage:
    MEALIE_API_TOKEN=<token> uv run python -m migration_scripts.migrate_to_mealie \
        [--dry-run] [--no-skip-existing]
"""

import argparse
import os
import sys

from sqlalchemy.orm import joinedload

sys.path.append(os.getcwd())

from app.db.session import SessionLocal
from app.models import Recipe, RecipeComponent, RecipeIngredient
from migration_scripts.mealie_client import MealieClient
from migration_scripts import mealie_mapping as m


def load_recipes(session):
    return (
        session.query(Recipe)
        .options(
            joinedload(Recipe.components)
            .joinedload(RecipeComponent.ingredients)
            .joinedload(RecipeIngredient.ingredient),
            joinedload(Recipe.instructions),
            joinedload(Recipe.comments),
        )
        .all()
    )


def resolve_refs(client, recipe, dry_run):
    """Return (category_refs, tag_refs) as Mealie organizer dicts (or name stubs in dry-run)."""
    cats, tags = [], []
    if recipe.category:
        cats.append({"name": recipe.category} if dry_run
                    else client.get_or_create_category(recipe.category))
    for name in m.tag_names(recipe):
        tags.append({"name": name} if dry_run else client.get_or_create_tag(name))
    return cats, tags


def import_recipe(client, recipe, dry_run, skip_existing):
    slug = m.slugify(recipe.name)
    if not dry_run and skip_existing and client.recipe_exists(slug):
        return "skipped"

    cats, tags = resolve_refs(client, recipe, dry_run)

    if dry_run:
        payload = m.recipe_to_payload(recipe, {"slug": slug, "name": recipe.name}, cats, tags)
        print(f"[dry-run] {recipe.name} -> {slug} "
              f"({len(payload['recipeIngredient'])} ingredients, "
              f"{len(payload['recipeInstructions'])} steps, tags={[t['name'] for t in tags]})")
        return "created"

    new_slug = client.create_recipe(recipe.name)
    shell = client.get_recipe(new_slug)
    payload = m.recipe_to_payload(recipe, shell, cats, tags)
    client.update_recipe(new_slug, payload)
    return "created"


def main(argv=None):
    parser = argparse.ArgumentParser(description="Import recipe_api recipes into Mealie")
    parser.add_argument("--dry-run", action="store_true", help="map and print without calling Mealie")
    parser.add_argument("--no-skip-existing", dest="skip_existing", action="store_false",
                        help="import even if a recipe with the same slug already exists")
    parser.set_defaults(skip_existing=True)
    args = parser.parse_args(argv)

    client = None
    if not args.dry_run:
        token = os.environ.get("MEALIE_API_TOKEN")
        if not token:
            parser.error("MEALIE_API_TOKEN is required unless --dry-run")
        base = os.environ.get("MEALIE_URL", "https://recipes.qwertyshoe.com")
        client = MealieClient(base, token)

    counts = {"created": 0, "skipped": 0, "failed": 0}
    session = SessionLocal()
    try:
        recipes = load_recipes(session)
        print(f"Found {len(recipes)} recipes.")
        for recipe in recipes:
            if m.should_skip_recipe(recipe.name):
                print(f"Skipping meta-recipe: {recipe.name}")
                counts["skipped"] += 1
                continue
            try:
                result = import_recipe(client, recipe, args.dry_run, args.skip_existing)
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


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 2: Verify the module imports and `--help` works**

Run: `uv run python -m migration_scripts.migrate_to_mealie --help`
Expected: argparse help text listing `--dry-run` and `--no-skip-existing`. No import errors.

- [ ] **Step 3: Run the full test suite to confirm nothing regressed**

Run: `uv run pytest -q`
Expected: all tests pass (existing suite + the new mapping/client tests).

- [ ] **Step 4: Commit**

```bash
git add migration_scripts/migrate_to_mealie.py
git commit -m "feat(migrate): add Mealie import CLI orchestrator"
```

---

## Task 9: Stage the database and dry-run

**Files:** none (operational)

- [ ] **Step 1: Copy the live DB to the readable path**

```bash
sudo cp /mnt/fastdata/docker_data/volumes/recipe_api_database-data/_data/recipes.db \
        /mnt/fastdata/recipe_api/db/recipes.db
sudo chown "$USER:$USER" /mnt/fastdata/recipe_api/db/recipes.db
ls -la /mnt/fastdata/recipe_api/db/recipes.db
```

Expected: `recipes.db` exists and is owned by you. `DATABASE_URL` in `.env` already
points at `sqlite:///./db/recipes.db`, so no config change is needed.

- [ ] **Step 2: Dry-run and sanity-check the counts**

```bash
uv run python -m migration_scripts.migrate_to_mealie --dry-run
```

Expected: `Found N recipes.` followed by one `[dry-run] <name> -> <slug> (...)` line
per recipe, then a summary. Confirm N looks right and a few lines show sensible
ingredient/step counts and tags. Investigate any recipe that prints 0 ingredients or
0 steps unexpectedly (likely a relationship not loaded or empty source data).

---

## Task 10: Live import and verify in Mealie

**Files:** none (operational)

- [ ] **Step 1: Run the import**

```bash
export MEALIE_API_TOKEN=<token-from-Task-6>
export MEALIE_URL=https://recipes.qwertyshoe.com
uv run python -m migration_scripts.migrate_to_mealie
```

Expected: a summary `created=N skipped=0 failed=0` (skipped>0 only if some already
existed). Any `FAILED <name>: <error>` lines identify specific recipes to inspect.

- [ ] **Step 2: Spot-check in the Mealie UI**

Open `https://recipes.qwertyshoe.com` and inspect 3–4 imported recipes covering
different shapes (one multi-section, one with tags + category, one with calories +
notes). Verify:
- ingredient lines render correctly and section headers (e.g. "Frosting") appear
- instruction steps are in order
- category and tags are attached
- calories show under nutrition; notes show the source/notes text
- prep/cook/total times are populated

- [ ] **Step 3: Re-run to confirm idempotency**

```bash
uv run python -m migration_scripts.migrate_to_mealie
```

Expected: summary shows `created=0 skipped=N` — every recipe is detected as already
present, proving re-runs are safe.

- [ ] **Step 4: Final commit (docs only, if any notes were added)**

If Task 6 required field-name fixes or you added a short README note, commit them:

```bash
git add -A
git commit -m "docs(migrate): record Mealie import run notes"
```

(If there are no changes, skip this step.)
