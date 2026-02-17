# Track: Permission & Authorization Model

## Overview

Implement a correct, consistent, and testable authorization model across all three
primary resource domains: Meals, Meal Templates, and Recipes. Additionally,
introduce an admin operating-mode system that lets admins act as themselves (user
mode), as a full administrator, or as a specific user (impersonation mode) — all
signalled via request headers.

## Authorization Rules

### Meals (Strictly Private)
- Any authenticated user can **create** meals (always assigned to themselves).
- Only the **owner** of a meal can **view, update, or delete** it.
- An **admin in admin mode** can view, update, or delete **any** meal.
- An **admin in impersonation mode** sees and operates on the impersonated user's meals.

### Meal Templates (Shared Read)
- Any authenticated user can **view** any template.
- Only the **owner** can **update** or **delete** their template.
- An admin in admin mode can view, update, or delete **any** template.

### Recipes (Shared Read)
- Any authenticated user can **view** any recipe.
- Only the **owner** can **update** or **delete** their recipe.
- An admin in admin mode can view, update, or delete **any** recipe.
- Comment ownership rules mirror the same pattern (author or admin mode can update/delete).

## Admin Operating Modes

Admins authenticate normally and receive a standard JWT. The mode is selected
per-request via headers. Non-admins sending these headers receive 403.

| Mode | Header | Behaviour |
|---|---|---|
| **User mode** (default) | _(none)_ | Admin is scoped to their own data, same as any user |
| **Admin mode** | `X-Admin-Mode: true` | Full access to all resources |
| **Impersonation mode** | `X-Act-As-User: <user_uuid>` | Access scoped to target user's data; creates/updates owned by target |

Rules:
- `X-Act-As-User` takes precedence over `X-Admin-Mode` if both are sent.
- The target user for impersonation must exist and be active.
- Admins cannot impersonate other admins (security boundary).

## Technical Approach

### AuthContext
A new `AuthContext` dataclass encapsulates resolved permission state:
- `real_user` — the authenticated user (from JWT)
- `effective_user` — the user whose ownership rules apply (may differ in impersonation)
- `is_admin_mode` — whether full admin access is active (bypasses ownership checks)

### get_auth_context dependency
A FastAPI dependency that replaces `get_current_active_user` across all protected
endpoints. Reads the optional headers, validates them, resolves `effective_user`,
and returns an `AuthContext`.

### Ownership checks
All endpoints use `ctx.effective_user.id` for ownership comparisons and
`ctx.is_admin_mode` to bypass those checks when appropriate.

## Acceptance Criteria

- `GET /meals` returns only the effective user's meals (admin mode: all meals)
- `GET /meals/{id}` returns 403 if the effective user is not the owner (admin mode: allowed)
- Admin with no headers has user-scoped access (same as any regular user)
- Admin with `X-Admin-Mode: true` has full access to all resources
- Admin with `X-Act-As-User: <id>` has that user's scoped access
- Non-admins sending admin headers receive 403
- All scenarios covered by tests with >80% coverage
- README documents the authorization model

## Out of Scope
- Group/family sharing (planned feature, not this track)
- Role-based access beyond admin/user
- Audit logging of impersonation events
- Explicit duplicate endpoints (users duplicate via the standard creation endpoints)
