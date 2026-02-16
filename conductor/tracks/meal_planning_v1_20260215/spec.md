# Track Specification: Meal Planning Enhancements

## Overview
This track evolves the meal planning capabilities of the Recipe API. Key improvements include a multi-dimensional meal status model, recency-aware recipe and template tracking, and a flexible queue-based meal generation system with optional scheduling.

## Functional Requirements

### 1. Meal Status Tracking (Multi-Dimensional)
Meals have three independent status dimensions:

- **Lifecycle Status** (`status` field, enum):
    - `queued` — Default state when a meal is generated or created. The meal is upcoming and has not yet been cooked.
    - `cooked` — The user has cooked this meal. It becomes historical.
    - `cancelled` — The user decided not to cook this meal.

- **Scheduling** (`scheduled_date` field, nullable DateTime):
    - Scheduling is optional. Users may work from a simple queue of upcoming meals without assigning dates.
    - When set, represents the date the user intends to cook the meal.
    - The scheduled date is non-binding and can be changed at any time.

- **Shopping Status** (`is_shopped` field, boolean, default `false`):
    - Indicates whether the user has already purchased ingredients for this meal.
    - Supports filtering the shopping list to only unshopped queued meals.

### 2. Recency Awareness
- **Recipe:** Add `last_cooked_at` (DateTime, nullable) to the `Recipe` model. Updated automatically when any meal containing that recipe transitions to `cooked`.
- **Meal Template:** Add `last_used_at` (DateTime, nullable) to the `MealTemplate` model. Updated automatically when a meal is generated from that template.
- These fields support future features for automatic meal/recipe selection that favors variety.

### 3. Meal Queue & Generation
- Generating meals is conceptualized as appending an arbitrary number of new meals to a user's **ordered queue** of upcoming (queued) meals.
- The queue is ordered by a `queue_position` (integer) field, allowing users to reorder upcoming meals.
- Generated meals start with `status=queued`, `is_shopped=false`, and optionally a `scheduled_date`.
- The generation endpoint accepts a count and optionally a list of scheduled dates.

### 4. Scheduling
- Scheduling a meal means setting or updating its `scheduled_date`.
- A dedicated endpoint or the existing update endpoint can be used to assign/change/clear a date.
- Scheduling does not change the lifecycle status.

## Technical Requirements

### Schema Updates
- **`Recipe` table:** Add `last_cooked_at` (DateTime, nullable).
- **`MealTemplate` table:** Add `last_used_at` (DateTime, nullable).
- **`Meal` table:**
    - Update `MealStatus` enum: replace `DRAFT`/`SCHEDULED`/`COOKED` with `QUEUED`/`COOKED`/`CANCELLED`.
    - Rename `date` to `scheduled_date` for clarity.
    - Add `is_shopped` (Boolean, default `false`).
    - Add `queue_position` (Integer, nullable) for ordering within the queue.

### CRUD Enhancements
- Meal status transitions: `queued` → `cooked` (triggers `last_cooked_at` update on recipes), `queued` → `cancelled`.
- Automatic `last_used_at` update on `MealTemplate` when a meal is generated from it.
- Filtering meals by `is_shopped`, `status`, and `scheduled_date` range.

### Generation Logic
- Template selection uses a weighted random pipeline: **filter → weight → select**.
- **Filter:** Retrieves all eligible user templates. Designed to support future exclusion filters.
- **Weight:** Computes per-template weights based on recency (`last_used_at`). Templates never used or used longest ago receive higher weight. Designed as a composable system to support future weight factors (e.g., user favorites).
- **Select:** Weighted random selection of N templates without replacement.
- For each selected template, generate one meal by resolving recipes per slot strategy (existing logic).
- Accept a count parameter and optional scheduled dates.
- Assign sequential `queue_position` values after existing queued meals.

## User Stories
- As a home cook, I want to see which recipes I haven't made in a while so I can maintain variety in our family meals.
- As a home cook, I want to mark a meal as "shopped for" so my shopping list only shows what I still need to buy.
- As a home cook, I want a queue of upcoming meals that I can optionally schedule to specific dates.
- As a home cook, I want to generate a batch of meals and add them to my queue without committing to a calendar.
- As a home cook, I want to mark a meal as cooked or cancel it if plans change.

## Out of Scope
- **Priority/preference system:** May be added in a future track.
- **Automatic recipe selection based on recency:** The recency fields are being added now to support this in a future track; the selection algorithm itself is out of scope.
- **Shopping list generation:** Only the `is_shopped` flag is in scope; building a full ingredient shopping list is not.
