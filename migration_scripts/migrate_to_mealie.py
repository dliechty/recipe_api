"""Import recipe_api recipes into Mealie.

Usage:
    # preview without touching Mealie
    uv run python -m migration_scripts.migrate_to_mealie import --dry-run

    # wipe previously-imported recipes, then import with structured ingredients
    MEALIE_API_TOKEN=<token> uv run python -m migration_scripts.migrate_to_mealie purge
    MEALIE_API_TOKEN=<token> uv run python -m migration_scripts.migrate_to_mealie import
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

    def _assign_label_if_missing(self, key, food, label):
        """Assign the proposed label to a food that has none (at most once)."""
        if not food.get("label") and label:
            label_id = self._label_id(label)
            food = self.client.update_food(food["id"], {**food, "labelId": label_id})
            food["label"] = food.get("label") or {"id": label_id}
            self._foods[key] = food
        return food

    def resolve_food(self, name, action, label):
        key = name.lower()
        food = self._foods.get(key)
        if action == "match":
            if food is None:
                raise KeyError(f"food '{name}' not in Mealie; fix food_map.csv")
            food = self._assign_label_if_missing(key, food, label)
        else:  # create
            if food is None:
                food = self.client.create_food(name, self._label_id(label))
                self._foods[key] = food
            else:
                food = self._assign_label_if_missing(key, food, label)
        return {"id": food["id"], "name": food["name"]}


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


def purge_recipes(client, recipes):
    deleted = 0
    for recipe in recipes:
        if client.delete_recipe(m.slugify(recipe.name)):
            deleted += 1
            print(f"Deleted: {recipe.name}")
    return deleted


DEFAULT_FOOD_MAP = os.path.join(os.path.dirname(__file__), "food_map.csv")
DEFAULT_UNIT_MAP = os.path.join(os.path.dirname(__file__), "unit_map.csv")


def _build_client():
    token = os.environ.get("MEALIE_API_TOKEN")
    if not token:
        raise SystemExit("MEALIE_API_TOKEN is required")
    base = os.environ.get("MEALIE_URL", "https://recipes.qwertyshoe.com")
    return MealieClient(base, token)


def run_purge(args):
    client = _build_client()
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
            client = _build_client()
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

    p_purge = sub.add_parser("purge", help="delete previously imported recipes by slug (destructive; no dry-run)")
    p_purge.set_defaults(func=run_purge)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
