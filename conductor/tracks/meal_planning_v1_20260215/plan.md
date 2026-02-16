# Implementation Plan: Meal Planning Enhancements

## Phase 1: Foundation & Status Management
Focus on updating the data models and basic CRUD operations to support the new meal attributes.

- [ ] Task: Update Database Schema
    - [ ] Add `last_cooked_at` to `Recipe` model.
    - [ ] Update `MealStatus` enum with new states (`shopped-for`, `cooked`, etc.).
    - [ ] Add `priority` field to `Meal` or `Recipe` (TBD: Decide during implementation).
    - [ ] Create and run Alembic migration.
- [ ] Task: Update Schemas and CRUD for Meal Status
    - [ ] Write tests for updating meal status.
    - [ ] Update Pydantic schemas.
    - [ ] Implement CRUD logic for status transitions.
- [ ] Task: Conductor - User Manual Verification 'Phase 1: Foundation' (Protocol in workflow.md)

## Phase 2: Recency and Priority Logic
Implement the logic for tracking usage and calculating priority.

- [ ] Task: Track 'Last Cooked' automatically
    - [ ] Write tests to verify `last_cooked_at` updates when a meal is marked as `cooked`.
    - [ ] Implement the trigger logic in the CRUD/Service layer.
- [ ] Task: Implement Recipe Scoring Service
    - [ ] Write unit tests for the ranking algorithm.
    - [ ] Implement `get_recommended_recipes` logic.
- [ ] Task: Conductor - User Manual Verification 'Phase 2: Logic' (Protocol in workflow.md)

## Phase 3: Meal Generation & Scheduling
Expose the new capabilities through API endpoints.

- [ ] Task: Pending Meals Generation Endpoint
    - [ ] Write API tests for meal generation.
    - [ ] Implement `POST /api/meals/generate` to create a set of draft meals.
- [ ] Task: Scheduling Integration
    - [ ] Write tests for scheduling a pending meal.
    - [ ] Implement logic to assign dates to generated meals.
- [ ] Task: Conductor - User Manual Verification 'Phase 3: Generation' (Protocol in workflow.md)
