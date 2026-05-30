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
