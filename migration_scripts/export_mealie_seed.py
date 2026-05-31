"""Stage 1: export Mealie's seeded foods/units/labels + distinct source foods/units.

Usage:
    MEALIE_API_TOKEN=<token> uv run python -m migration_scripts.export_mealie_seed
"""

import json
import os
import sys
from pathlib import Path

sys.path.append(os.getcwd())

from app.db.session import SessionLocal  # noqa: E402
from app.models import Ingredient, RecipeIngredient  # noqa: E402
from migration_scripts.mealie_client import MealieClient  # noqa: E402

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
