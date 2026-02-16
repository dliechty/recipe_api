# Implementation Plan: Meal Planning Enhancements

## Phase 1: Schema & Model Updates
Update data models, enums, and create the database migration for all new/changed fields.

- [ ] Task: Update MealStatus Enum and Meal Model
    - [ ] Replace `MealStatus` enum values: `DRAFT`/`SCHEDULED`/`COOKED` → `QUEUED`/`COOKED`/`CANCELLED`.
    - [ ] Rename `date` column to `scheduled_date` on `Meal` model.
    - [ ] Add `is_shopped` (Boolean, default `false`) to `Meal` model.
    - [ ] Add `queue_position` (Integer, nullable) to `Meal` model.
- [ ] Task: Add Recency Fields
    - [ ] Add `last_cooked_at` (DateTime, nullable) to `Recipe` model.
    - [ ] Add `last_used_at` (DateTime, nullable) to `MealTemplate` model.
- [ ] Task: Create and Run Alembic Migration
    - [ ] Generate migration for all schema changes.
    - [ ] Verify migration applies cleanly (upgrade and downgrade).
- [ ] Task: Update Pydantic Schemas
    - [ ] Update `MealStatus` references in schemas.
    - [ ] Rename `date` to `scheduled_date` in `MealBase`, `MealCreate`, `MealUpdate`, `Meal` schemas.
    - [ ] Add `is_shopped` and `queue_position` to meal schemas.
    - [ ] Add `last_cooked_at` to recipe response schemas.
    - [ ] Add `last_used_at` to meal template response schemas.
    - [ ] Update `MealScheduleRequest` schema if needed.
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

- [ ] Task: Update Meal CRUD Endpoints
    - [ ] Write tests for creating meals with `is_shopped`, `scheduled_date`, `queue_position`.
    - [ ] Write tests for updating `is_shopped` and `scheduled_date` independently.
    - [ ] Update `POST /meals`, `PUT /meals/{id}` to handle new fields.
- [ ] Task: Update Existing Meal Tests for Enum Changes
    - [ ] Update all existing test references from `DRAFT`/`SCHEDULED` to `QUEUED`/`CANCELLED`.
    - [ ] Ensure full test suite passes with the new enum values.
- [ ] Task: Conductor - User Manual Verification 'Phase 4: API Endpoint Updates' (Protocol in workflow.md)
