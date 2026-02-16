# Implementation Plan: Meal Planning Enhancements

## Phase 1: Schema & Model Updates
Update data models, enums, and create the database migration for all new/changed fields.

- [x] Task: Update MealStatus Enum and Meal Model `33a49b8`
    - [x] Replace `MealStatus` enum values: `DRAFT`/`SCHEDULED`/`COOKED` → `QUEUED`/`COOKED`/`CANCELLED`.
    - [x] Rename `date` column to `scheduled_date` on `Meal` model.
    - [x] Add `is_shopped` (Boolean, default `false`) to `Meal` model.
    - [x] Add `queue_position` (Integer, nullable) to `Meal` model.
- [x] Task: Add Recency Fields `33a49b8`
    - [x] Add `last_cooked_at` (DateTime, nullable) to `Recipe` model.
    - [x] Add `last_used_at` (DateTime, nullable) to `MealTemplate` model.
- [x] Task: Create and Run Alembic Migration `33a49b8`
    - [x] Generate migration for all schema changes.
    - [x] Verify migration applies cleanly (upgrade and downgrade).
- [x] Task: Update Pydantic Schemas `33a49b8`
    - [x] Update `MealStatus` references in schemas.
    - [x] Rename `date` to `scheduled_date` in `MealBase`, `MealCreate`, `MealUpdate`, `Meal` schemas.
    - [x] Add `is_shopped` and `queue_position` to meal schemas.
    - [x] Add `last_cooked_at` to recipe response schemas.
    - [x] Add `last_used_at` to meal template response schemas.
    - [x] Update `MealScheduleRequest` schema if needed.
- [ ] Task: Conductor - User Manual Verification 'Phase 1: Schema & Model Updates' (Protocol in workflow.md)

## Phase 2: Status Transitions & Recency Tracking
Implement the business logic for meal lifecycle transitions and automatic recency updates.

- [ ] Task: Implement Meal Status Transitions
    - [ ] Write tests for valid transitions: `queued` → `cooked`, `queued` → `cancelled`.
    - [ ] Write tests for invalid transitions (e.g., `cooked` → `queued`, `cancelled` → `cooked`).
    - [ ] Implement transition validation in CRUD/service layer.
- [ ] Task: Auto-Update Recipe `last_cooked_at`
    - [ ] Write tests verifying `last_cooked_at` updates on all recipes in a meal when status transitions to `cooked`.
    - [ ] Implement the trigger logic in the meal update CRUD operation.
- [ ] Task: Auto-Update MealTemplate `last_used_at`
    - [ ] Write tests verifying `last_used_at` updates when a meal is generated from a template.
    - [ ] Implement the trigger logic in the meal generation flow.
- [ ] Task: Conductor - User Manual Verification 'Phase 2: Status Transitions & Recency Tracking' (Protocol in workflow.md)

## Phase 3: Queue Management & Meal Generation
Implement the queue ordering system and update the generation endpoint.

- [ ] Task: Implement Queue Positioning
    - [ ] Write tests for `queue_position` assignment on meal creation (manual and generated).
    - [ ] Write tests for queue reordering (updating positions).
    - [ ] Implement queue position logic: new meals get position after last queued meal.
- [ ] Task: Update Meal Generation Endpoint
    - [ ] Write tests for generating N meals (selects N templates via weighted random, one meal per template).
    - [ ] Write tests for weighted selection (templates with older/null `last_used_at` are more likely to be selected, but not deterministic).
    - [ ] Write tests for generation with and without scheduled dates.
    - [ ] Write tests for edge cases (e.g., user has fewer templates than requested count).
    - [ ] Update `POST /generate` to accept `count` and optional `scheduled_dates` list (remove single `template_id` requirement).
    - [ ] Implement template selection pipeline:
        - [ ] **Filter phase:** Retrieve eligible templates for the user (extensible for future exclusion filters).
        - [ ] **Weighting phase:** Compute per-template weights based on recency (older/null `last_used_at` = higher weight). Design as a composable system so additional weight factors can be added later.
        - [ ] **Selection phase:** Weighted random selection of N templates (without replacement).
    - [ ] Generate one meal per selected template, resolving recipes per slot strategy.
    - [ ] Assign sequential `queue_position` values to generated meals.
    - [ ] Update `last_used_at` on each selected template.
- [ ] Task: Update Meal Filtering & Sorting
    - [ ] Write tests for filtering by `is_shopped`, `status`, and `scheduled_date` range.
    - [ ] Write tests for sorting by `queue_position`.
    - [ ] Update query filtering logic to support new fields.
- [ ] Task: Conductor - User Manual Verification 'Phase 3: Queue Management & Meal Generation' (Protocol in workflow.md)

## Phase 4: API Endpoint Updates
Ensure all existing endpoints handle the new fields correctly and update responses.

- [x] Task: Update Meal CRUD Endpoints `33a49b8`
    - [x] Write tests for creating meals with `is_shopped`, `scheduled_date`, `queue_position`.
    - [x] Write tests for updating `is_shopped` and `scheduled_date` independently.
    - [x] Update `POST /meals`, `PUT /meals/{id}` to handle new fields.
- [x] Task: Update Existing Meal Tests for Enum Changes `33a49b8`
    - [x] Update all existing test references from `DRAFT`/`SCHEDULED` to `QUEUED`/`CANCELLED`.
    - [x] Ensure full test suite passes with the new enum values.
- [ ] Task: Conductor - User Manual Verification 'Phase 4: API Endpoint Updates' (Protocol in workflow.md)
