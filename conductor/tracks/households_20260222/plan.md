# Plan: Households

## Phase 1: Data Models & Database Migration

- [ ] Task: Write failing tests for Household, HouseholdMembership, and HouseholdTemplateExclusion ORM models
- [ ] Task: Add `Household`, `HouseholdMembership`, and `HouseholdTemplateExclusion` models to `app/models.py`
- [ ] Task: Add nullable `household_id` FK column to the `Meal` model in `app/models.py`
- [ ] Task: Generate Alembic migration for new models and `Meal.household_id`
- [ ] Task: Conductor - User Manual Verification 'Phase 1: Data Models & Database Migration' (Protocol in workflow.md)

## Phase 2: Pydantic Schemas

- [ ] Task: Write failing tests for Household, HouseholdMembership, and HouseholdTemplateExclusion schemas
- [ ] Task: Add household schemas (`HouseholdCreate`, `HouseholdUpdate`, `Household`, `HouseholdMember`, `HouseholdTemplateExclusion`) to `app/schemas.py`
- [ ] Task: Update `MealUpdate` schema to include optional nullable `household_id` field
- [ ] Task: Update `Meal` response schema to include `household_id`
- [ ] Task: Conductor - User Manual Verification 'Phase 2: Pydantic Schemas' (Protocol in workflow.md)

## Phase 3: Active Household Context

- [ ] Task: Write failing tests for `X-Active-Household` header parsing and membership validation in `AuthContext`
- [ ] Task: Add `X-Active-Household` to CORS `allow_headers` in `app/main.py`
- [ ] Task: Extend `AuthContext` / `get_auth_context` in `app/api/auth.py` to parse the `X-Active-Household` header, validate membership, expose `active_household` on the context, and write `active_household_id` to `request.state`
- [ ] Task: Write failing tests for `active_household_id` appearing in structured log wide-event payloads (present when header set, null when absent)
- [ ] Task: Update `StructuredLoggingMiddleware` in `app/core/logging_middleware.py` to read `active_household_id` from `request.state` and include it in the log payload
- [ ] Task: Conductor - User Manual Verification 'Phase 3: Active Household Context' (Protocol in workflow.md)

## Phase 4: Household API Endpoints

- [ ] Task: Write failing tests for household CRUD endpoints (create, list, get, rename, delete) including authorization rules
- [ ] Task: Implement household CRUD endpoints in new file `app/api/households.py`
- [ ] Task: Write failing tests for membership endpoints (join, leave, list members, remove member, set primary household)
- [ ] Task: Implement membership endpoints in `app/api/households.py`
- [ ] Task: Write failing tests for template exclusion endpoints (list disabled, disable, re-enable)
- [ ] Task: Implement template exclusion endpoints in `app/api/households.py`
- [ ] Task: Register the households router in `app/main.py`
- [ ] Task: Conductor - User Manual Verification 'Phase 4: Household API Endpoints' (Protocol in workflow.md)

## Phase 5: Meal Integration

- [ ] Task: Write failing tests for meal list/get scoping by active household context (header present vs absent)
- [ ] Task: Update `get_meals` and `get_meal` in `app/api/meals.py` to scope by active household when the header is set
- [ ] Task: Write failing tests for auto-linking meals to active household on create and generate
- [ ] Task: Update `create_meal` and `generate_meals` to set `household_id` from `AuthContext.active_household`
- [ ] Task: Write failing tests for household template exclusion filtering during meal generation
- [ ] Task: Update `generate_meals` to filter out templates excluded by the active household
- [ ] Task: Write failing tests for patching `household_id` on an existing meal (assign, unassign, authorization)
- [ ] Task: Update `update_meal` in `app/api/meals.py` to support patching `household_id`
- [ ] Task: Conductor - User Manual Verification 'Phase 5: Meal Integration' (Protocol in workflow.md)

## Phase 6: Documentation

- [ ] Task: Update `README.md` with a dedicated "Households" section covering: concept overview, creating/joining/leaving, the `X-Active-Household` header, meal visibility and generation behaviour, primary household preference, and template exclusions
- [ ] Task: Regenerate OpenAPI spec by running `generate_openapi.py`
- [ ] Task: Conductor - User Manual Verification 'Phase 6: Documentation' (Protocol in workflow.md)
