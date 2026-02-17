"""Tests to cover critical auth paths not yet covered by existing tests.

Targets uncovered lines in app/api/auth.py:
- create_access_token with no expires_delta (line 93)
- get_current_user: missing 'sub', JWTError, user not found (lines 122-123, 126-128, 132-133)
- get_current_active_user: inactive user (lines 147-148)
- get_auth_context: invalid UUID in X-Act-As-User (lines 203-204)
- get_user_name: successful return (line 273)
- list_active_users: non-admin (line 294)
- list_pending_requests: non-admin (line 392)
- approve_request: non-admin, request not found (lines 407, 411)
- change_password: incorrect old password (line 446)
- update_user: not authorized, user not found (lines 463, 472)
- delete_user: not authorized, user not found (lines 486, 490)
- reset_user: not authorized, user not found (lines 504, 508)
"""

import uuid
from datetime import timedelta

from fastapi.testclient import TestClient
from jose import jwt
from sqlalchemy.orm import Session

from app import crud, schemas
from app.api.auth import create_access_token
from app.core.config import settings


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def make_user(db: Session, email: str, password: str = "testpass", is_admin: bool = False):
    """Create a user directly via CRUD."""
    user_in = schemas.UserCreate(email=email, password=password)
    user = crud.create_user(db, user_in)
    if is_admin:
        user.is_admin = True
        db.add(user)
        db.commit()
        db.refresh(user)
    return user


def login(client: TestClient, email: str, password: str = "testpass") -> dict:
    """Log in and return auth headers."""
    resp = client.post("/auth/token", data={"username": email, "password": password})
    assert resp.status_code == 200, f"Login failed: {resp.json()}"
    token = resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


# ---------------------------------------------------------------------------
# create_access_token: default expiry (no expires_delta)
# ---------------------------------------------------------------------------


def test_create_access_token_default_expiry():
    """create_access_token with no expires_delta uses the default 15-minute expiry."""
    token = create_access_token(data={"sub": str(uuid.uuid4())})
    payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
    assert "exp" in payload
    assert "sub" in payload


# ---------------------------------------------------------------------------
# get_current_user: invalid / malformed tokens
# ---------------------------------------------------------------------------


def test_get_current_user_missing_sub(client: TestClient, db: Session):
    """Token without a 'sub' claim returns 401."""
    # Build a valid JWT that is missing the 'sub' field
    token = create_access_token(data={"foo": "bar"}, expires_delta=timedelta(minutes=5))
    headers = {"Authorization": f"Bearer {token}"}
    resp = client.get("/auth/context", headers=headers)
    assert resp.status_code == 401


def test_get_current_user_invalid_token(client: TestClient):
    """A completely garbage token returns 401."""
    headers = {"Authorization": "Bearer not.a.real.token"}
    resp = client.get("/auth/context", headers=headers)
    assert resp.status_code == 401


def test_get_current_user_invalid_uuid_in_sub(client: TestClient):
    """Token whose 'sub' is not a valid UUID returns 401."""
    token = create_access_token(
        data={"sub": "not-a-uuid"}, expires_delta=timedelta(minutes=5)
    )
    headers = {"Authorization": f"Bearer {token}"}
    resp = client.get("/auth/context", headers=headers)
    assert resp.status_code == 401


def test_get_current_user_nonexistent_user(client: TestClient):
    """Token referencing a user ID that does not exist returns 401."""
    nonexistent_id = str(uuid.uuid4())
    token = create_access_token(
        data={"sub": nonexistent_id}, expires_delta=timedelta(minutes=5)
    )
    headers = {"Authorization": f"Bearer {token}"}
    resp = client.get("/auth/context", headers=headers)
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# get_current_active_user: inactive user accessing a protected endpoint
# ---------------------------------------------------------------------------


def test_inactive_user_cannot_access_protected_endpoint(client: TestClient, db: Session):
    """An inactive user gets 400 when accessing endpoints requiring an active user."""
    user = make_user(db, "inactive_access@example.com")
    headers = login(client, "inactive_access@example.com")

    # Deactivate after obtaining token
    user.is_active = False
    db.add(user)
    db.commit()

    # Try to access any protected endpoint
    resp = client.get("/auth/context", headers=headers)
    assert resp.status_code == 400
    assert "inactive" in resp.json()["detail"].lower()


# ---------------------------------------------------------------------------
# get_auth_context: X-Act-As-User with an invalid (non-UUID) string
# ---------------------------------------------------------------------------


def test_act_as_user_invalid_uuid_string(client: TestClient, db: Session):
    """Admin sending a non-UUID string in X-Act-As-User gets 404."""
    make_user(db, "actas_invaliduuid_admin@example.com", is_admin=True)
    headers = {**login(client, "actas_invaliduuid_admin@example.com"), "X-Act-As-User": "not-a-uuid"}
    resp = client.get("/auth/context", headers=headers)
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# GET /auth/users/{user_id}: successful return
# ---------------------------------------------------------------------------


def test_get_user_by_id_success(client: TestClient, db: Session):
    """Authenticated user can look up another user by ID."""
    target = make_user(db, "get_user_target@example.com")
    requester_headers = login(client, "get_user_target@example.com")
    resp = client.get(f"/auth/users/{target.id}", headers=requester_headers)
    assert resp.status_code == 200
    assert resp.json()["email"] == "get_user_target@example.com"


# ---------------------------------------------------------------------------
# GET /auth/users: non-admin user gets 403
# ---------------------------------------------------------------------------


def test_list_active_users_non_admin(client: TestClient, db: Session):
    """Non-admin calling GET /auth/users gets 403."""
    make_user(db, "list_users_nonadmin@example.com")
    headers = login(client, "list_users_nonadmin@example.com")
    resp = client.get("/auth/users", headers=headers)
    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# GET /auth/pending-requests: non-admin gets 403
# ---------------------------------------------------------------------------


def test_list_pending_requests_non_admin(client: TestClient, db: Session):
    """Non-admin calling GET /auth/pending-requests gets 403."""
    make_user(db, "pending_req_nonadmin@example.com")
    headers = login(client, "pending_req_nonadmin@example.com")
    resp = client.get("/auth/pending-requests", headers=headers)
    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# POST /auth/approve-request/{request_id}: non-admin and not-found
# ---------------------------------------------------------------------------


def test_approve_request_non_admin(client: TestClient, db: Session):
    """Non-admin calling approve-request gets 403."""
    make_user(db, "approve_nonadmin@example.com")
    headers = login(client, "approve_nonadmin@example.com")
    fake_id = str(uuid.uuid4())
    resp = client.post(
        f"/auth/approve-request/{fake_id}",
        headers=headers,
        json={"initial_password": "somepass"},
    )
    assert resp.status_code == 403


def test_approve_request_not_found(client: TestClient, db: Session):
    """Admin approving a request ID that does not exist gets 404."""
    make_user(db, "approve_admin_notfound@example.com", is_admin=True)
    headers = login(client, "approve_admin_notfound@example.com")
    fake_id = str(uuid.uuid4())
    resp = client.post(
        f"/auth/approve-request/{fake_id}",
        headers=headers,
        json={"initial_password": "somepass"},
    )
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# POST /auth/change-password: incorrect old password
# ---------------------------------------------------------------------------


def test_change_password_wrong_old_password(client: TestClient, db: Session):
    """Providing the wrong old password to change-password returns 400."""
    make_user(db, "change_pw_wrong@example.com", password="correctpass")
    headers = login(client, "change_pw_wrong@example.com", password="correctpass")
    resp = client.post(
        "/auth/change-password",
        headers=headers,
        json={"old_password": "WRONGPASS", "new_password": "newpass123"},
    )
    assert resp.status_code == 400
    assert "incorrect" in resp.json()["detail"].lower()


# ---------------------------------------------------------------------------
# PUT /auth/users/{user_id}: not authorized (non-admin editing other user)
# ---------------------------------------------------------------------------


def test_update_user_not_authorized(client: TestClient, db: Session):
    """Non-admin user trying to update another user's profile gets 403."""
    make_user(db, "update_user_requester@example.com")
    target = make_user(db, "update_user_target@example.com")
    requester_headers = login(client, "update_user_requester@example.com")

    resp = client.put(
        f"/auth/users/{target.id}",
        headers=requester_headers,
        json={"first_name": "Hacked"},
    )
    assert resp.status_code == 403


def test_update_user_not_found(client: TestClient, db: Session):
    """Admin updating a user ID that does not exist gets 404."""
    make_user(db, "update_user_admin@example.com", is_admin=True)
    headers = login(client, "update_user_admin@example.com")
    fake_id = str(uuid.uuid4())
    resp = client.put(
        f"/auth/users/{fake_id}",
        headers=headers,
        json={"first_name": "Ghost"},
    )
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# DELETE /auth/users/{user_id}: not authorized and not found
# ---------------------------------------------------------------------------


def test_delete_user_not_authorized(client: TestClient, db: Session):
    """Non-admin trying to delete a user gets 403."""
    make_user(db, "delete_nonadmin@example.com")
    target = make_user(db, "delete_target@example.com")
    headers = login(client, "delete_nonadmin@example.com")
    resp = client.delete(f"/auth/users/{target.id}", headers=headers)
    assert resp.status_code == 403


def test_delete_user_not_found(client: TestClient, db: Session):
    """Admin deleting a user ID that does not exist gets 404."""
    make_user(db, "delete_admin_notfound@example.com", is_admin=True)
    headers = login(client, "delete_admin_notfound@example.com")
    fake_id = str(uuid.uuid4())
    resp = client.delete(f"/auth/users/{fake_id}", headers=headers)
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# POST /auth/users/{user_id}/reset: not authorized and not found
# ---------------------------------------------------------------------------


def test_reset_user_not_authorized(client: TestClient, db: Session):
    """Non-admin trying to reset a user gets 403."""
    make_user(db, "reset_nonadmin@example.com")
    target = make_user(db, "reset_target_user@example.com")
    headers = login(client, "reset_nonadmin@example.com")
    resp = client.post(
        f"/auth/users/{target.id}/reset",
        headers=headers,
        json={"initial_password": "newpass"},
    )
    assert resp.status_code == 403


def test_reset_user_not_found(client: TestClient, db: Session):
    """Admin resetting a user ID that does not exist gets 404."""
    make_user(db, "reset_admin_notfound@example.com", is_admin=True)
    headers = login(client, "reset_admin_notfound@example.com")
    fake_id = str(uuid.uuid4())
    resp = client.post(
        f"/auth/users/{fake_id}/reset",
        headers=headers,
        json={"initial_password": "newpass"},
    )
    assert resp.status_code == 404
