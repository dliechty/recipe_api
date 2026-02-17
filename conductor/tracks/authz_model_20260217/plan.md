# Plan: Permission & Authorization Model

## Phase 1: README Documentation [checkpoint: TBD]

- [ ] Task: Update README with authorization model
    - [ ] Add "Authorization Model" section documenting Meals (private), Templates/Recipes (shared read), and admin modes
    - [ ] Document X-Admin-Mode and X-Act-As-User headers with examples
- [ ] Task: Conductor - User Manual Verification 'Phase 1' (Protocol in workflow.md)

## Phase 2: AuthContext Infrastructure [checkpoint: TBD]

- [ ] Task: Write failing tests for get_auth_context dependency
    - [ ] Test: regular user, no headers → effective_user == real_user, is_admin_mode == False
    - [ ] Test: admin, no headers → user-scoped (effective_user == admin, is_admin_mode == False)
    - [ ] Test: admin + X-Admin-Mode: true → is_admin_mode == True
    - [ ] Test: admin + X-Act-As-User: <valid_id> → effective_user == target user
    - [ ] Test: admin + X-Act-As-User: <invalid_id> → 404
    - [ ] Test: admin + X-Act-As-User: <admin_id> → 403 (cannot impersonate another admin)
    - [ ] Test: non-admin + X-Admin-Mode: true → 403
    - [ ] Test: non-admin + X-Act-As-User: <id> → 403
    - [ ] Test: X-Act-As-User takes precedence over X-Admin-Mode when both present
- [ ] Task: Implement AuthContext dataclass and get_auth_context dependency
    - [ ] Define AuthContext dataclass (real_user, effective_user, is_admin_mode)
    - [ ] Implement get_auth_context in app/api/auth.py
    - [ ] Confirm all auth tests pass
- [ ] Task: Conductor - User Manual Verification 'Phase 2' (Protocol in workflow.md)

## Phase 3: Meals Authorization [checkpoint: TBD]

- [ ] Task: Write failing tests for meals authorization
    - [ ] Test: GET /meals returns only owner's meals (user mode)
    - [ ] Test: GET /meals with X-Admin-Mode returns all meals
    - [ ] Test: GET /meals with X-Act-As-User returns target user's meals
    - [ ] Test: GET /meals/{id} returns 403 when caller is not owner (user mode)
    - [ ] Test: GET /meals/{id} with X-Admin-Mode returns any meal
    - [ ] Test: GET /meals/{id} with X-Act-As-User returns target user's meal
    - [ ] Test: POST /meals creates meal for effective_user (impersonation mode assigns to target)
    - [ ] Test: POST /meals/generate scopes template selection to effective_user
    - [ ] Test: PUT /meals/{id} still rejects wrong user, allows admin mode
    - [ ] Test: DELETE /meals/{id} still rejects wrong user, allows admin mode
- [ ] Task: Migrate meals endpoints to use AuthContext
    - [ ] Replace get_current_active_user with get_auth_context in all meals routes
    - [ ] Fix GET /meals to filter by effective_user.id (skip filter in admin mode)
    - [ ] Fix GET /meals/{id} to check meal.user_id == ctx.effective_user.id or ctx.is_admin_mode
    - [ ] Fix POST /meals to assign meal to effective_user.id
    - [ ] Fix POST /meals/generate to scope template query to effective_user.id
    - [ ] Fix PUT /meals/{id} and DELETE /meals/{id} to use ctx
    - [ ] Confirm all meal tests pass
- [ ] Task: Conductor - User Manual Verification 'Phase 3' (Protocol in workflow.md)

## Phase 4: Templates & Recipes Authorization [checkpoint: TBD]

- [ ] Task: Write failing tests for templates and recipes authorization
    - [ ] Test: GET /meals/templates — all users can view all templates
    - [ ] Test: GET /meals/templates/{id} — all users can view any template
    - [ ] Test: PUT /meals/templates/{id} — non-owner gets 403, owner succeeds, admin mode succeeds
    - [ ] Test: DELETE /meals/templates/{id} — non-owner gets 403, owner succeeds, admin mode succeeds
    - [ ] Test: GET /recipes — all users can view all recipes
    - [ ] Test: GET /recipes/{id} — all users can view any recipe
    - [ ] Test: PUT /recipes/{id} — non-owner gets 403, owner succeeds, admin mode succeeds
    - [ ] Test: DELETE /recipes/{id} — non-owner gets 403, owner succeeds, admin mode succeeds
    - [ ] Test: comment update/delete — author or admin mode only
- [ ] Task: Migrate templates and recipes endpoints to use AuthContext
    - [ ] Replace get_current_active_user with get_auth_context in all template routes
    - [ ] Replace get_current_active_user with get_auth_context in all recipe routes
    - [ ] Update ownership checks in update/delete to use ctx.effective_user.id and ctx.is_admin_mode
    - [ ] Confirm all template and recipe tests pass
- [ ] Task: Conductor - User Manual Verification 'Phase 4' (Protocol in workflow.md)

## Phase 5: Coverage, Spec & Final Validation [checkpoint: TBD]

- [ ] Task: Verify full test coverage
    - [ ] Run pytest --cov=app and confirm >80% coverage
    - [ ] Address any uncovered auth paths
- [ ] Task: Update OpenAPI spec
    - [ ] Run generate_openapi.py to regenerate spec
- [ ] Task: Conductor - User Manual Verification 'Phase 5' (Protocol in workflow.md)
