"""Pure functions mapping recipe_api models to Mealie API payloads.

No I/O here — everything is unit-testable against in-memory model objects.
"""

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
