# recipe_api → Mealie Recipe Import — Design

**Date:** 2026-05-30
**Status:** Approved
**Repo:** recipe_api (the importer lives here to reuse the SQLAlchemy models)

## Overview

Write a new one-off importer that copies the recipes from `recipe_api`'s SQLite
database into Mealie (running at `https://recipes.qwertyshoe.com`) via Mealie's
REST API. This mirrors what `migration_scripts/migrate_access_recipes.py` did for
the original MS Access data, but the destination is now Mealie instead of the
custom app.

The cleaned `recipe_api` DB is the source of truth, so all the prior Access cleanup
(difficulty mapping, time parsing, quantity precision fixes, "As Needed" → "To
Taste", meta-recipe skipping) is already baked in and is **not** re-implemented.

## Component

`migration_scripts/migrate_to_mealie.py`, run with:

```bash
uv run python -m migration_scripts.migrate_to_mealie [--dry-run] [--skip-existing]
```

It reuses `app.models` and `app.db.session.SessionLocal` for clean joins, mirroring
the structure of the existing `migrate_access_recipes.py`.

## Data access

The live `recipes.db` is root-owned inside the Docker volume
(`/mnt/fastdata/docker_data/volumes/recipe_api_database-data/_data/recipes.db`).
At implementation time the operator copies it to the path `DATABASE_URL` already
points at:

```bash
sudo cp /mnt/fastdata/docker_data/volumes/recipe_api_database-data/_data/recipes.db \
        /mnt/fastdata/recipe_api/db/recipes.db
sudo chown $USER:$USER /mnt/fastdata/recipe_api/db/recipes.db
```

The script opens the DB **read-only** and never writes back. The old container
stays stopped.

## Mealie API client

A small `httpx`-based client (httpx is already a dependency).

- **Auth:** long-lived Mealie API token via `MEALIE_API_TOKEN` (Bearer). Base URL
  via `MEALIE_URL` (default `https://recipes.qwertyshoe.com`).
- **Per recipe:**
  1. `POST /api/recipes` `{"name": <name>}` → returns the new slug.
  2. `GET /api/recipes/{slug}` → fetch the created shell.
  3. `PUT /api/recipes/{slug}` → write the fully-mapped recipe.
- **Organizers:** categories and tags are looked up / created once via
  `/api/organizers/categories` and `/api/organizers/tags`, cached in memory by
  lowercased name, then attached to recipes by reference (id/name/slug).

All recipes are imported into the account/household tied to the API token
(single-user import — no owner mapping).

## Field mapping

| recipe_api source | Mealie target |
|---|---|
| `name`, `description` | `name`, `description` |
| `yield_amount` + `yield_unit` | `recipeYield` (e.g. `"4 servings"`) |
| `prep_time_minutes` | `prepTime` (e.g. `"30 minutes"`) |
| `cook_time_minutes` | `performTime` |
| `total_time_minutes` | `totalTime` |
| `components` → `recipe_ingredients` | `recipeIngredient` list of display strings, `disableAmount: true`; the component name (e.g. `Frosting`) is set as `title` on the first ingredient of each group |
| `instructions` (by `step_number`) | `recipeInstructions` (ordered `{text}`) |
| `category` | recipe **category** (created if missing) |
| `cuisine`, `protein`, `difficulty` | **tags** — each non-null becomes a tag (created if missing) |
| `calories` | `nutrition.calories` |
| migrated notes (`Comment` rows) + non-URL `source` name | recipe **notes** (`Source: …` line plus migrated note text) |
| `source_url` | `orgURL` |

### Ingredient display string

Each ingredient line is built as `"{quantity} {unit} {ingredient.name}"` with notes
appended as `", {notes}"` when present. Quantity is formatted to drop trailing
zeros (e.g. `2.0` → `2`, `0.5` → `0.5`). The whole string goes in the ingredient's
`note` field with `disableAmount: true`. Section grouping is preserved by setting
`title` on the first ingredient of each component.

### Skips

Meta-recipes whose name matches `<<...>>` are skipped, mirroring
`should_skip_recipe` in the original script.

## Behavior, errors, idempotency

- **Idempotent:** before creating, the script derives the candidate slug by
  slugifying the recipe name (Mealie's own rule: lowercase, non-alphanumerics → `-`)
  and `GET /api/recipes/{slug}`; a 200 means it already exists. With
  `--skip-existing` (default on) it skips it. Re-runs are safe. (If Mealie's actual
  slug ever diverges from the derived one, the worst case is a duplicate, not data
  loss.)
- **`--dry-run`:** builds and logs payloads (plus one full sample) without calling
  Mealie's write endpoints.
- **Resilient:** each recipe runs in its own `try/except`; failures are logged and
  skipped, and a summary (`created` / `skipped` / `failed`) prints at the end.

## Testing (TDD)

Unit tests in `recipe_api/tests/` for the **pure** transform functions, written
before the implementation:

- ingredient display-string builder (quantity formatting, notes, section title)
- time formatter (minutes → `"N minutes"`, `None` handling)
- full recipe → Mealie payload mapper, against sample `Recipe` model objects

The Mealie HTTP client is mocked; **no live API calls in tests**. The existing
pytest suite continues to pass.

## Verification

1. `--dry-run` prints the recipe count and a sample payload that looks correct.
2. A real run imports into Mealie; spot-check several recipes in the Mealie UI:
   ingredient sections, ordered steps, tags, category, calories, and notes.

## Out of scope (YAGNI)

- Meal plans, meal templates, households, recipe lists, comments-as-comments
  (only migrated *notes* are carried, into recipe notes).
- Multi-user / owner mapping.
- Recipe images (the source has none).
- Structured Mealie food/unit entities (ingredients are display strings).
