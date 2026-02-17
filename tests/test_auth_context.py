"""Tests for the AuthContext dataclass and get_auth_context dependency.

Tests written FIRST (TDD) - these will fail until the implementation is done.
"""

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app import crud, schemas


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def create_user_and_login(
    client: TestClient,
    db: Session,
    email: str,
    password: str = "password",
    is_admin: bool = False,
):
    """Create a user, set admin flag if needed, and return (user, auth_headers)."""
    try:
        user_in = schemas.UserCreate(email=email, password=password)
        user = crud.create_user(db, user_in)
    except Exception:
        user = crud.get_user_by_email(db, email=email)

    if is_admin and not user.is_admin:
        user.is_admin = True
        db.add(user)
        db.commit()

    response = client.post(
        "/auth/token",
        data={"username": email, "password": password},
    )
    assert response.status_code == 200, f"Login failed for {email}: {response.json()}"
    token = response.json()["access_token"]
    return user, {"Authorization": f"Bearer {token}"}


def get_auth_context(client: TestClient, headers: dict) -> dict:
    """Call the debug endpoint that returns AuthContext info."""
    response = client.get("/auth/context", headers=headers)
    return response


# ---------------------------------------------------------------------------
# Test: regular user, no headers → effective_user == real_user, is_admin_mode == False
# ---------------------------------------------------------------------------


def test_regular_user_no_headers(client: TestClient, db: Session):
    """Regular user with no special headers gets user-scoped context."""
    user, headers = create_user_and_login(
        client, db, email="ctx_regular@example.com", is_admin=False
    )

    response = get_auth_context(client, headers)
    assert response.status_code == 200

    data = response.json()
    assert str(user.id) == data["real_user_id"]
    assert str(user.id) == data["effective_user_id"]
    assert data["is_admin_mode"] is False


# ---------------------------------------------------------------------------
# Test: admin, no headers → user-scoped (effective_user == admin, is_admin_mode == False)
# ---------------------------------------------------------------------------


def test_admin_no_headers_is_user_scoped(client: TestClient, db: Session):
    """Admin with no special headers is scoped to their own data."""
    admin, headers = create_user_and_login(
        client, db, email="ctx_admin_nohdr@example.com", is_admin=True
    )

    response = get_auth_context(client, headers)
    assert response.status_code == 200

    data = response.json()
    assert str(admin.id) == data["real_user_id"]
    assert str(admin.id) == data["effective_user_id"]
    assert data["is_admin_mode"] is False


# ---------------------------------------------------------------------------
# Test: admin + X-Admin-Mode: true → is_admin_mode == True
# ---------------------------------------------------------------------------


def test_admin_with_admin_mode_header(client: TestClient, db: Session):
    """Admin sending X-Admin-Mode: true gets admin mode."""
    admin, base_headers = create_user_and_login(
        client, db, email="ctx_admin_mode@example.com", is_admin=True
    )
    headers = {**base_headers, "X-Admin-Mode": "true"}

    response = get_auth_context(client, headers)
    assert response.status_code == 200

    data = response.json()
    assert str(admin.id) == data["real_user_id"]
    assert str(admin.id) == data["effective_user_id"]
    assert data["is_admin_mode"] is True


# ---------------------------------------------------------------------------
# Test: admin + X-Act-As-User: <valid_id> → effective_user == target user
# ---------------------------------------------------------------------------


def test_admin_impersonation_valid_user(client: TestClient, db: Session):
    """Admin sending X-Act-As-User with a valid non-admin user ID gets impersonation context."""
    admin, admin_headers = create_user_and_login(
        client, db, email="ctx_admin_impersonate@example.com", is_admin=True
    )
    target, _ = create_user_and_login(
        client, db, email="ctx_target_user@example.com", is_admin=False
    )
    headers = {**admin_headers, "X-Act-As-User": str(target.id)}

    response = get_auth_context(client, headers)
    assert response.status_code == 200

    data = response.json()
    assert str(admin.id) == data["real_user_id"]
    assert str(target.id) == data["effective_user_id"]
    assert data["is_admin_mode"] is False


# ---------------------------------------------------------------------------
# Test: admin + X-Act-As-User: <invalid_id> → 404
# ---------------------------------------------------------------------------


def test_admin_impersonation_invalid_user(client: TestClient, db: Session):
    """Admin sending X-Act-As-User with a non-existent user ID gets 404."""
    _, admin_headers = create_user_and_login(
        client, db, email="ctx_admin_bad_impersonate@example.com", is_admin=True
    )
    nonexistent_id = "00000000-0000-0000-0000-000000000000"
    headers = {**admin_headers, "X-Act-As-User": nonexistent_id}

    response = get_auth_context(client, headers)
    assert response.status_code == 404


# ---------------------------------------------------------------------------
# Test: admin + X-Act-As-User: <admin_id> → 403 (cannot impersonate another admin)
# ---------------------------------------------------------------------------


def test_admin_cannot_impersonate_another_admin(client: TestClient, db: Session):
    """Admin cannot impersonate another admin user."""
    _, admin_headers = create_user_and_login(
        client, db, email="ctx_admin_impersonate_admin@example.com", is_admin=True
    )
    other_admin, _ = create_user_and_login(
        client, db, email="ctx_other_admin@example.com", is_admin=True
    )
    headers = {**admin_headers, "X-Act-As-User": str(other_admin.id)}

    response = get_auth_context(client, headers)
    assert response.status_code == 403


# ---------------------------------------------------------------------------
# Test: non-admin + X-Admin-Mode: true → 403
# ---------------------------------------------------------------------------


def test_non_admin_cannot_use_admin_mode_header(client: TestClient, db: Session):
    """Non-admin user sending X-Admin-Mode: true gets 403."""
    _, user_headers = create_user_and_login(
        client, db, email="ctx_nonadmin_adminmode@example.com", is_admin=False
    )
    headers = {**user_headers, "X-Admin-Mode": "true"}

    response = get_auth_context(client, headers)
    assert response.status_code == 403


# ---------------------------------------------------------------------------
# Test: non-admin + X-Act-As-User: <id> → 403
# ---------------------------------------------------------------------------


def test_non_admin_cannot_use_act_as_user_header(client: TestClient, db: Session):
    """Non-admin user sending X-Act-As-User header gets 403."""
    _, user_headers = create_user_and_login(
        client, db, email="ctx_nonadmin_actasuser@example.com", is_admin=False
    )
    target, _ = create_user_and_login(
        client, db, email="ctx_nonadmin_actasuser_target@example.com", is_admin=False
    )
    headers = {**user_headers, "X-Act-As-User": str(target.id)}

    response = get_auth_context(client, headers)
    assert response.status_code == 403


# ---------------------------------------------------------------------------
# Test: X-Act-As-User takes precedence over X-Admin-Mode when both present
# ---------------------------------------------------------------------------


def test_act_as_user_takes_precedence_over_admin_mode(client: TestClient, db: Session):
    """When both X-Act-As-User and X-Admin-Mode are sent, X-Act-As-User takes precedence."""
    admin, admin_headers = create_user_and_login(
        client, db, email="ctx_admin_both_headers@example.com", is_admin=True
    )
    target, _ = create_user_and_login(
        client, db, email="ctx_both_headers_target@example.com", is_admin=False
    )
    headers = {
        **admin_headers,
        "X-Admin-Mode": "true",
        "X-Act-As-User": str(target.id),
    }

    response = get_auth_context(client, headers)
    assert response.status_code == 200

    data = response.json()
    # X-Act-As-User takes precedence → effective_user is target, not admin_mode
    assert str(admin.id) == data["real_user_id"]
    assert str(target.id) == data["effective_user_id"]
    assert data["is_admin_mode"] is False
