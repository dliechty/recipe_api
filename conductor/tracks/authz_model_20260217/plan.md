# Plan: Permission & Authorization Model

## Phase 1: README Documentation [checkpoint: 4e1e97a]

- [x] Task: Update README with authorization model
    - [x] Add "Authorization Model" section documenting Meals (private), Templates/Recipes (shared read), and admin modes
    - [x] Document X-Admin-Mode and X-Act-As-User headers with examples
- [x] Task: Conductor - User Manual Verification 'Phase 1' (Protocol in workflow.md)

## Phase 2: AuthContext Infrastructure [checkpoint: 4e1e97a]

- [x] Task: Write failing tests for get_auth_context dependency
    - [x] Test: regular user, no headers → effective_user == real_user, is_admin_mode == False
    - [x] Test: admin, no headers → user-scoped (effective_user == admin, is_admin_mode == False)
    - [x] Test: admin + X-Admin-Mode: true → is_admin_mode == True
    - [x] Test: admin + X-Act-As-User: <valid_id> → effective_user == target user
    - [x] Test: admin + X-Act-As-User: <invalid_id> → 404
    - [x] Test: admin + X-Act-As-User: <admin_id> → 403 (cannot impersonate another admin)
    - [x] Test: non-admin + X-Admin-Mode: true → 403
    - [x] Test: non-admin + X-Act-As-User: <id> → 403
    - [x] Test: X-Act-As-User takes precedence over X-Admin-Mode when both present
- [x] Task: Implement AuthContext dataclass and get_auth_context dependency
    - [x] Define AuthContext dataclass (real_user, effective_user, is_admin_mode)
    - [x] Implement get_auth_context in app/api/auth.py
    - [x] Confirm all auth tests pass
- [x] Task: Conductor - User Manual Verification 'Phase 2' (Protocol in workflow.md)

## Phase 3: Meals Authorization [checkpoint: 4e1e97a]

- [x] Task: Write failing tests for meals authorization
    - [x] Test: GET /meals returns only owner's meals (user mode)
    - [x] Test: GET /meals with X-Admin-Mode returns all meals
    - [x] Test: GET /meals with X-Act-As-User returns target user's meals
    - [x] Test: GET /meals/{id} returns 403 when caller is not owner (user mode)
    - [x] Test: GET /meals/{id} with X-Admin-Mode returns any meal
    - [x] Test: GET /meals/{id} with X-Act-As-User returns target user's meal
    - [x] Test: POST /meals creates meal for effective_user (impersonation mode assigns to target)
    - [x] Test: POST /meals/generate scopes template selection to effective_user
    - [x] Test: PUT /meals/{id} still rejects wrong user, allows admin mode
    - [x] Test: DELETE /meals/{id} still rejects wrong user, allows admin mode
- [x] Task: Migrate meals endpoints to use AuthContext
    - [x] Replace get_current_active_user with get_auth_context in all meals routes
    - [x] Fix GET /meals to filter by effective_user.id (skip filter in admin mode)
    - [x] Fix GET /meals/{id} to check meal.user_id == ctx.effective_user.id or ctx.is_admin_mode
    - [x] Fix POST /meals to assign meal to effective_user.id
    - [x] Fix POST /meals/generate to scope template query to effective_user.id
    - [x] Fix PUT /meals/{id} and DELETE /meals/{id} to use ctx
    - [x] Confirm all meal tests pass
- [x] Task: Conductor - User Manual Verification 'Phase 3' (Protocol in workflow.md)

## Phase 4: Templates & Recipes Authorization [checkpoint: 4e1e97a]

- [x] Task: Write failing tests for templates and recipes authorization
    - [x] Test: GET /meals/templates — all users can view all templates
    - [x] Test: GET /meals/templates/{id} — all users can view any template
    - [x] Test: PUT /meals/templates/{id} — non-owner gets 403, owner succeeds, admin mode succeeds
    - [x] Test: DELETE /meals/templates/{id} — non-owner gets 403, owner succeeds, admin mode succeeds
    - [x] Test: GET /recipes — all users can view all recipes
    - [x] Test: GET /recipes/{id} — all users can view any recipe
    - [x] Test: PUT /recipes/{id} — non-owner gets 403, owner succeeds, admin mode succeeds
    - [x] Test: DELETE /recipes/{id} — non-owner gets 403, owner succeeds, admin mode succeeds
    - [x] Test: comment update/delete — author or admin mode only
- [x] Task: Migrate templates and recipes endpoints to use AuthContext
    - [x] Replace get_current_active_user with get_auth_context in all template routes
    - [x] Replace get_current_active_user with get_auth_context in all recipe routes
    - [x] Update ownership checks in update/delete to use ctx.effective_user.id and ctx.is_admin_mode
    - [x] Confirm all template and recipe tests pass
- [x] Task: Conductor - User Manual Verification 'Phase 4' (Protocol in workflow.md)

## Phase 5: Coverage, Spec & Final Validation [checkpoint: 4e1e97a]

- [x] Task: Verify full test coverage
    - [x] Run pytest --cov=app and confirm >80% coverage
    - [x] Address any uncovered auth paths
- [x] Task: Update OpenAPI spec
    - [x] Run generate_openapi.py to regenerate spec
- [x] Task: Conductor - User Manual Verification 'Phase 5' (Protocol in workflow.md)
