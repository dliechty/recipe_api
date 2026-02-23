"""Tests for the X-Active-Household header and AuthContext household resolution."""

import json
import logging
import uuid

from app import models
from app.crud import get_password_hash


# --- Helpers ---


def create_test_user(db, email="test@example.com", is_admin=False):
    user = models.User(
        email=email,
        hashed_password=get_password_hash("testpassword"),
        is_admin=is_admin,
        is_active=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def get_auth_headers(client, email="test@example.com", password="testpassword"):
    response = client.post(
        "/auth/token", data={"username": email, "password": password}
    )
    token = response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def create_household(db, creator):
    household = models.Household(name="Test Household", created_by=creator.id)
    db.add(household)
    db.commit()
    db.refresh(household)
    return household


def add_membership(db, household, user, is_primary=False):
    membership = models.HouseholdMembership(
        household_id=household.id,
        user_id=user.id,
        is_primary=is_primary,
    )
    db.add(membership)
    db.commit()
    db.refresh(membership)
    return membership


# --- AuthContext Tests ---


class TestActiveHouseholdHeader:
    """Tests for X-Active-Household header processing in get_auth_context."""

    def test_valid_household_with_membership(self, db, client):
        """User who is a member of the household gets active_household set."""
        user = create_test_user(db, email="member@example.com")
        household = create_household(db, user)
        add_membership(db, household, user)
        headers = get_auth_headers(client, email="member@example.com")
        headers["X-Active-Household"] = str(household.id)

        response = client.get("/auth/context", headers=headers)

        assert response.status_code == 200
        data = response.json()
        assert data["active_household_id"] == str(household.id)

    def test_valid_household_without_membership_returns_403(self, db, client):
        """User who is NOT a member of the household gets 403."""
        owner = create_test_user(db, email="owner2@example.com")
        create_test_user(db, email="nonmember@example.com")
        household = create_household(db, owner)
        # owner is a member, non_member is not
        add_membership(db, household, owner)

        headers = get_auth_headers(client, email="nonmember@example.com")
        headers["X-Active-Household"] = str(household.id)

        response = client.get("/auth/context", headers=headers)

        assert response.status_code == 403
        assert "Not a member of this household" in response.json()["detail"]

    def test_invalid_uuid_is_ignored(self, db, client):
        """Invalid UUID in X-Active-Household is silently ignored."""
        create_test_user(db, email="user_invalid_uuid@example.com")
        headers = get_auth_headers(client, email="user_invalid_uuid@example.com")
        headers["X-Active-Household"] = "not-a-valid-uuid"

        response = client.get("/auth/context", headers=headers)

        assert response.status_code == 200
        data = response.json()
        assert data["active_household_id"] is None

    def test_unknown_household_uuid_is_ignored(self, db, client):
        """Valid UUID that doesn't match any household is silently ignored."""
        create_test_user(db, email="user_unknown_hh@example.com")
        headers = get_auth_headers(client, email="user_unknown_hh@example.com")
        headers["X-Active-Household"] = str(uuid.uuid4())

        response = client.get("/auth/context", headers=headers)

        assert response.status_code == 200
        data = response.json()
        assert data["active_household_id"] is None

    def test_admin_mode_bypasses_membership_check(self, db, client):
        """Admin mode allows access to household even without membership."""
        create_test_user(db, email="admin_bypass@example.com", is_admin=True)
        other_user = create_test_user(db, email="hh_owner3@example.com")
        household = create_household(db, other_user)
        add_membership(db, household, other_user)
        # admin is NOT a member

        headers = get_auth_headers(client, email="admin_bypass@example.com")
        headers["X-Admin-Mode"] = "true"
        headers["X-Active-Household"] = str(household.id)

        response = client.get("/auth/context", headers=headers)

        assert response.status_code == 200
        data = response.json()
        assert data["active_household_id"] == str(household.id)
        assert data["is_admin_mode"] is True

    def test_no_header_means_no_household(self, db, client):
        """When X-Active-Household is absent, active_household_id is None."""
        create_test_user(db, email="no_header@example.com")
        headers = get_auth_headers(client, email="no_header@example.com")

        response = client.get("/auth/context", headers=headers)

        assert response.status_code == 200
        data = response.json()
        assert data["active_household_id"] is None


# --- Logging Middleware Tests ---


class _LogCapture(logging.Handler):
    """Simple handler that captures log records for assertion."""

    def __init__(self):
        super().__init__()
        self.records: list[logging.LogRecord] = []

    def emit(self, record):
        self.records.append(record)


class TestLoggingMiddlewareHousehold:
    """Tests that active_household_id appears in structured log output."""

    def test_log_includes_household_id_when_set(self, db, client):
        """Structured log includes active_household_id when header is valid."""
        user = create_test_user(db, email="log_user@example.com")
        household = create_household(db, user)
        add_membership(db, household, user)
        headers = get_auth_headers(client, email="log_user@example.com")
        headers["X-Active-Household"] = str(household.id)

        from app.core.logging_middleware import (
            StructuredLoggingMiddleware,
            structured_logger,
        )

        capture = _LogCapture()
        structured_logger.addHandler(capture)
        original_rate = StructuredLoggingMiddleware.SAMPLE_RATE
        StructuredLoggingMiddleware.SAMPLE_RATE = 1.0  # Log everything
        try:
            client.get("/auth/context", headers=headers)
        finally:
            StructuredLoggingMiddleware.SAMPLE_RATE = original_rate
            structured_logger.removeHandler(capture)

        assert len(capture.records) > 0, "Expected at least one structured log entry"
        payload = json.loads(capture.records[-1].message)
        assert payload["active_household_id"] == str(household.id)

    def test_log_household_id_null_when_absent(self, db, client):
        """Structured log has active_household_id=null when header is absent."""
        create_test_user(db, email="log_user_no_hh@example.com")
        headers = get_auth_headers(client, email="log_user_no_hh@example.com")

        from app.core.logging_middleware import (
            StructuredLoggingMiddleware,
            structured_logger,
        )

        capture = _LogCapture()
        structured_logger.addHandler(capture)
        original_rate = StructuredLoggingMiddleware.SAMPLE_RATE
        StructuredLoggingMiddleware.SAMPLE_RATE = 1.0
        try:
            client.get("/auth/context", headers=headers)
        finally:
            StructuredLoggingMiddleware.SAMPLE_RATE = original_rate
            structured_logger.removeHandler(capture)

        assert len(capture.records) > 0, "Expected at least one structured log entry"
        payload = json.loads(capture.records[-1].message)
        assert payload["active_household_id"] is None
