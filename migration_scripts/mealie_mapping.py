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
