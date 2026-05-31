# Mealie Structured Ingredients (Parsing Migration) — Design

**Date:** 2026-05-30
**Status:** Approved
**Repo:** recipe_api (the importer lives here to reuse the SQLAlchemy models)

## Problem

The recipes are already in Mealie, imported by `migration_scripts/migrate_to_mealie.py`.
That importer flattened each ingredient into a single display string and set
`disableAmount: True` / `quantity: None`. As a result Mealie has no *structured*
ingredients (food + unit + quantity references), so the recipes cannot drive
shopping lists.

The fix is **not** to run Mealie's NLP ingredient parser. The `recipe_api` source
data is already structured — every `RecipeIngredient` row has separate `quantity`
(float), `unit` (string), `ingredient.name` (the food), and `notes` (prep words
like "Minced", "Optional"). The original import threw that structure away. We just
need to carry it through and **match** the source unit/food strings to Mealie's
pre-seeded units, foods, and labels.

The seeded Mealie food/unit/label set is reasonably comprehensive; existing recipes
should reuse those seeded values as much as possible. The goal is to avoid manually
editing 130+ recipes in the Mealie UI.

## Scope (from `recipes.db`)

- 131 recipes, 1,096 ingredient rows
- **50 distinct units** — ~15 common ones (Cup, Tbsp, Tsp, Piece, lb, Can…) cover
  almost everything; the rest are singletons
- **367 distinct food names** — mostly clean ("Kale", "Egg"), some messy
  ("Tomato Paste, 12 oz", "Chicken or Beef Broth", "Chipolte peppers in Adobo sauce")

The recipes in Mealie will be **wiped and re-imported** cleanly with structure
(chosen over in-place patching).

## Architecture — four-stage, file-driven pipeline

```
STAGE 1  EXPORT          STAGE 2  GENERATE        STAGE 3  REVIEW       STAGE 4  APPLY
─────────────────        ─────────────────        ────────────         ─────────────────
Pull seeded foods,   →   Claude reads both    →   User edits/approves → Re-import recipes
units, labels from       sides, writes            food_map.csv          into Mealie with
Mealie API.              food_map.csv +           & unit_map.csv        STRUCTURED
Pull distinct source     unit_map.csv             (one pass, ~370       ingredients, creating
foods + units from       (proposed matches,       rows, not 130         new foods/labels as
recipes.db.              labels, actions).        recipes).             the maps dictate.
```

Key properties:

- **The mapping files are the contract.** All fuzzy/semantic work happens in Stage 2
  (Claude) and is frozen by the Stage 3 review. Stage 4 is purely mechanical — it does
  no guessing, which makes it deterministic, testable, and re-runnable.
- This is a **one-time migration**, so Stage 2 is Claude doing the matching in a session
  and writing the files — no LLM API wired into the code.
- Stage 4 reuses the existing `migrate_to_mealie` create/update path; we swap out
  `build_ingredients` to emit structured entries and add a purge-then-reimport for the
  clean wipe.

## Stage 1 — Export

A new `export_mealie_seed.py` pulls from the Mealie API into `seed/`:

- `foods.json` (name, id, label) — `GET /api/foods?perPage=-1`
- `units.json` (name, abbreviation, id) — `GET /api/units?perPage=-1`
- `labels.json` (name, id) — `GET /api/groups/labels?perPage=-1`

And the distinct source values straight from `recipes.db`:

- distinct `ingredients.name` (367)
- distinct `recipe_ingredients.unit` (50)

Authentication uses the same `MEALIE_API_TOKEN` / `MEALIE_URL` env vars as the importer.

## Stage 2 — Generate the maps (Claude)

Claude reads the four exported lists in-session and writes `food_map.csv` +
`unit_map.csv`, applying:

- exact (case-insensitive) match first, then semantic/fuzzy match against seeded
  foods, normalizing typos and stripping size/packaging noise
  ("Tomato Paste, 12 oz" → "Tomato Paste");
- carry each matched food's existing seeded label; for unlabeled or `create` foods,
  propose a label preferring an existing seeded one, else a new one (flagged `new-label?`);
- mark anything uncertain in the `flags` column so review is a scan, not a line-by-line audit.

## Mapping file formats

Both files are **name-based, not ID-based** — the reviewer edits names, never UUIDs.
The apply step resolves names → IDs against a fresh export at run time (food/unit/label
names are unique in Mealie). Stale IDs cannot rot the files.

### `food_map.csv` — one row per distinct source food (~367)

| source_food | action | mealie_food | label | flags |
|---|---|---|---|---|
| Kale | match | Kale | Produce | |
| Chipolte peppers in Adobo sauce | match | Chipotle Peppers in Adobo | Canned Goods | typo-fixed |
| Tomato Paste, 12 oz | match | Tomato Paste | Canned Goods | size-stripped |
| Rau Marinara Sauce | create | Rau Marinara Sauce | Sauces | unmatched · new-label? |
| Sweet Baby Ray | match | BBQ Sauce | Condiments | low-confidence |

- **action**: `match` (use an existing seeded food) or `create` (no good match → make a new food).
- **mealie_food**: the target food's exact name. For `create`, the cleaned name to create.
- **label**: the shopping label. Pre-filled from the seeded food's existing label when it
  has one; otherwise a proposed label (preferring an existing seeded label, else a new one).
- **flags**: scannable review guide — `low-confidence`, `typo-fixed`, `size-stripped`,
  `unmatched`, `new-label?` (label not yet in the seed).

### `unit_map.csv` — one row per distinct source unit (~50)

| source_unit | mealie_unit | flags |
|---|---|---|
| Cup | cup | |
| Tbsp | tablespoon | |
| To Taste | (none) | to-taste |
| Piece | (none) | food-only |
| Can | can | |
| Shot | (none) | unmatched |

- **mealie_unit**: the seeded unit name, or `(none)` for "no unit" (food-only ingredients
  like *3 eggs*).
- Special flags drive apply behavior: `to-taste` → quantity cleared, `disableAmount` on,
  note set to "to taste"; `(none)` → structured food + quantity but no unit.

## Stage 4 — Apply the maps

`build_ingredients` is rewritten to consult the two maps (loaded once) plus a fresh seed
export, producing structured Mealie ingredient entries instead of display strings:

- **unit** → resolved via `unit_map`; `(none)` leaves unit null.
- **food** → resolved via `food_map`; `match` looks up the id, `create` makes the food
  (idempotent: create-or-fetch) and assigns its label, creating the label if missing.
- **quantity** → the source float as-is; `disableAmount: False` so amounts count toward
  shopping lists.
- **note** → source `notes` ("Minced", "Optional").
- **`to-taste` / quantity 0** → quantity null, `disableAmount: True`, note "to taste".
- **originalText** → the old flattened display string, preserved for traceability.
- Component section titles keep today's behavior (title on the component's first ingredient).

New foods/labels are created **once**, cached in-process, so 1,096 rows don't hammer the
API. The apply step does **zero guessing** — anything not resolvable from the maps is a
hard error pointing back to the file, never a silent skip.

## Re-import flow (CLI)

A new explicit verb structure on `migrate_to_mealie`:

- `purge` — deletes the recipes we previously imported (by slug); leaves foods/units/labels
  untouched.
- `import` — the existing create+update path, now emitting structured ingredients.
- `--dry-run` works end-to-end: loads the maps, prints structured ingredient counts and any
  unresolved rows, without touching Mealie.

A **guard** runs before any import: if a source food or unit isn't present in the maps
(e.g. a recipe added after the maps were generated), it aborts with the exact missing
values to add — never a partial import.

## Recipe metadata: yield/servings and tags

Alongside the ingredient work, two recipe-level mappings are corrected. These are
pure-function changes in `mealie_mapping.py` and need no review files.

### Yield → numeric servings

Today `build_yield` always emits a text yield ("4 servings"), which lands in Mealie's
free-text yield field. In the source, `yield_unit` is `"servings"` for **all 131
recipes** and `yield_amount` holds the count.

Rule: when `yield_unit` is empty or `"servings"`, put `yield_amount` into Mealie's
numeric **servings** field and emit no yield text. Only fall back to a text yield for a
genuinely non-servings unit (e.g. "loaf"). With the current data this yields a clean
numeric servings count every time.

The exact Mealie field name is confirmed during implementation — recent Mealie splits a
numeric `recipeServings` from the text `recipeYield` (with `recipeYieldQuantity`); older
versions only have the text `recipeYield`.

### Tags → prefixed by source field

Today `tag_names` flattens `cuisine`, `protein`, and `difficulty` into bare tags with no
way to tell them apart. Replace this with a small `field → prefix` config so each tag
carries its origin:

| source field | prefix | example | data today |
|---|---|---|---|
| `protein` | `Protein:` | `Protein: Beef` | 73 recipes populated |
| `difficulty` | `Difficulty:` | `Difficulty: Medium` (enum title-cased) | nearly all `Medium` |
| `cuisine` | `Cuisine:` | `Cuisine: …` | null for all 131 (rule dormant) |
| `recipe_diets` | `Diet:` | `Diet: …` | table empty (rule dormant) |

- Null/empty fields emit no tag.
- `difficulty` is a `DifficultyLevel` enum (`MEDIUM/EASY/HARD`) rendered title-cased.
- `category` is **unchanged** — it stays mapped to Mealie's dedicated `recipeCategory`
  organizer, not converted to a tag.

The prefixed tag names are run through the existing `get_or_create_tag` path, so Mealie
creates `Protein: Beef` etc. as needed.

## Testing

Matches the repo's pytest + pure-function style:

- `mealie_mapping` stays pure and unit-tested: feed in-memory ingredient rows + small fake
  maps, assert the structured payload (matched food id, unit id, `disableAmount`, to-taste
  handling, create action, note passthrough).
- Map-loader tests: malformed CSV, unknown action, missing column → clear errors.
- Apply-resolution tests with a fake `MealieClient` (no network): assert create-or-fetch is
  called once per new food/label and cached thereafter.
- `export_mealie_seed` and live HTTP paths are covered by the existing `MealieClient` test
  seam (fake client), consistent with `test_mealie_client.py`.

## Deliverables

1. `export_mealie_seed.py` — Stage 1 exporter.
2. Generated `food_map.csv` + `unit_map.csv` — reviewed by the user in Stage 3.
3. Rewritten structured `build_ingredients` + map loader/resolver in `mealie_mapping.py`.
4. `purge` / `import` CLI verbs on `migrate_to_mealie.py` with a pre-import guard.
5. Rewritten `build_yield` (numeric servings) and `tag_names` (prefixed tags) in
   `mealie_mapping.py`.
6. Tests for mapping, loading, apply-resolution, yield/servings, and prefixed tags.

The only manual work is one review pass over two files.
