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
