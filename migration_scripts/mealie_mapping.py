"""Pure functions mapping recipe_api models to Mealie API payloads.

No I/O here — everything is unit-testable against in-memory model objects.
"""

import csv
import re
from typing import Optional


def slugify(name: str) -> str:
    """Mealie-style slug: lowercase, non-alphanumerics -> '-', collapsed, stripped."""
    s = (name or "").lower()
    s = re.sub(r"[^a-z0-9]+", "-", s)
    return s.strip("-")


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


def build_instructions(recipe) -> list:
    steps = sorted(recipe.instructions, key=lambda i: i.step_number)
    return [{"text": s.text} for s in steps]


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


def _read_rows(path, required):
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
