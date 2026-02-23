# Spec: Households

## Overview

Add a "household" concept to enable collaborative meal planning. A household is a named
group that users can join. When a user activates a household context (via a request header),
meal visibility and meal generation are scoped to that household, and template availability
reflects household-level preferences.

## Functional Requirements

### FR-1: Household Model

- A `Household` has: `id` (UUID), `name` (string), `created_by` (FK → User),
  `created_at`, `updated_at`.
- Any authenticated user can create a household.
- Only the household creator or an admin can rename or delete a household.
- Deleting a household sets `household_id` to NULL on all linked meals (soft-unlink).

### FR-2: Household Membership

- A `HouseholdMembership` join table links users to households: `household_id`,
  `user_id`, `is_primary` (bool), `joined_at`.
- Any authenticated user can join any household (by ID or name search).
- Any member can leave a household themselves.
- Only the household creator or an admin can remove another member.
- A user can mark one of their memberships as `is_primary`. This is purely a
  client-readable preference; it does not automatically activate that household
  server-side.
- Admins can assign and unassign any user to/from any household.

### FR-3: Active Household Context (Request Header)

- Clients communicate the active household via the `X-Active-Household: <household_id>`
  request header.
- If the header is absent or contains an invalid/unknown UUID, the API behaves exactly
  as today (user sees their own meals; all templates treated as enabled).
- If the header is present and valid, the server validates that the requesting user is a
  member of that household. If not, return `403 Forbidden`.
- The active household header influences the three behaviours described in FR-4, FR-5,
  and FR-6.

### FR-4: Meal Visibility

- The `Meal` model gains a nullable `household_id` (FK → Household).
- Without `X-Active-Household`: the user sees only meals they created that have
  `household_id IS NULL` — existing behaviour unchanged.
- With `X-Active-Household`: the user sees all meals linked to that household,
  regardless of who created them.

### FR-5: Meal Creation & Generation

- When a meal is created or generated while `X-Active-Household` is set, it is
  automatically linked to that household (`household_id` = active household).
- Meals created without the header have `household_id = NULL` (personal meals).
- An existing meal with any `household_id` value (including NULL) can be reassigned via
  a PATCH to the meal. Only the meal's creator or an admin may reassign it.
- A meal can be unassigned from a household (set back to NULL) the same way.
- When reassigning, the target household must be one the requesting user is a member of
  (or the user must be an admin).

### FR-6: Meal Template Exclusions per Household

- A `HouseholdTemplateExclusion` table links households to disabled templates:
  `household_id`, `template_id`.
- Any household member can add or remove template exclusions for their household.
- Without `X-Active-Household`: all templates are treated as enabled (existing behaviour).
- With `X-Active-Household`: excluded templates are omitted from meal generation for
  that household.
- Templates remain globally available; exclusions are per-household only.

### FR-7: Authorization Summary

| Action                               | Who can perform it                  |
|--------------------------------------|-------------------------------------|
| Create household                     | Any authenticated user              |
| Rename / delete household            | Household creator or admin          |
| Join a household                     | Any authenticated user              |
| Leave a household                    | The member themselves               |
| Remove another member                | Household creator or admin          |
| Assign / unassign any user (admin)   | Admin only                          |
| Set primary household                | The user themselves                 |
| Enable / disable templates           | Any household member                |
| List all households                  | Admin only (users list their own)   |
| Assign / unassign a meal's household | Meal creator or admin               |

### FR-8: Documentation

- Update the project README with a dedicated "Households" section that covers:
  - What a household is and its purpose
  - How to create, join, and leave a household
  - How to use the `X-Active-Household` header
  - How household context affects meal visibility and generation
  - How to manage the primary household preference
  - How template exclusions work per household
- Regenerate the OpenAPI spec (`generate_openapi.py`) after all API changes are complete.

## API Endpoints

### Households
- `POST   /households`       — Create
- `GET    /households`       — List (own memberships; admin: all)
- `GET    /households/{id}`  — Get detail
- `PATCH  /households/{id}`  — Rename (creator/admin)
- `DELETE /households/{id}`  — Delete (creator/admin)

### Membership
- `POST   /households/{id}/join`               — Join
- `DELETE /households/{id}/leave`              — Leave
- `GET    /households/{id}/members`            — List members
- `DELETE /households/{id}/members/{user_id}`  — Remove member (creator/admin)
- `PATCH  /users/me/primary-household`         — Set primary household

### Template Exclusions
- `GET    /households/{id}/disabled-templates`             — List
- `POST   /households/{id}/disabled-templates`             — Disable a template
- `DELETE /households/{id}/disabled-templates/{tmpl_id}`  — Re-enable a template

### Meal Household Assignment
- `PUT  /meals/{id}` — Existing update endpoint; `household_id` becomes a patchable
  field (nullable UUID). Accepts the household ID to assign, or `null` to unassign.

## Non-Functional Requirements

- The `X-Active-Household` header must be added to the CORS `allow_headers` list.
- Household membership must be validated on every request that uses the header
  (no caching of membership state server-side).
- All new endpoints must follow existing auth/RBAC patterns (`AuthContext`).
- The `StructuredLoggingMiddleware` wide-event log payload must include
  `active_household_id` (the validated UUID from the `X-Active-Household` header, or
  `null` when not present) on every sampled log event. The auth context dependency is
  responsible for writing this value to `request.state` so the middleware can read it
  without re-parsing the header.

## Acceptance Criteria

- [ ] A user can create, rename (if creator), and delete (if creator) a household.
- [ ] A user can join and leave a household freely.
- [ ] A creator or admin can remove any member from a household.
- [ ] A user can mark one household as primary.
- [ ] Passing `X-Active-Household` with a valid household the user belongs to scopes
      meal reads to that household.
- [ ] Meals created/generated with `X-Active-Household` set are linked to that household.
- [ ] Without the header, existing meal visibility behaviour is unchanged.
- [ ] A meal can be assigned to or unassigned from a household via PUT.
- [ ] Any member can disable/enable templates for the household.
- [ ] Disabled templates are excluded from meal generation when the household is active.
- [ ] Admins can manage all households and memberships unconditionally.
- [ ] The README contains a clear "Households" section describing the feature.
- [ ] The OpenAPI spec is regenerated and reflects all new and modified endpoints.
- [ ] Every sampled structured log event includes `active_household_id`.

## Out of Scope

- Household-level recipe sharing or recipe visibility scoping.
- Real-time notifications for household events.
- Household-level roles beyond creator / member.
- Automatic activation of the primary household (the client is responsible for reading it
  and sending the header).
