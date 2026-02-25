"""Tests for the Households API endpoints."""

import uuid
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from app import models
from app.crud import get_password_hash


# --- Helpers ---


def create_test_user(
    db: Session,
    email: str = "household_test@example.com",
    is_admin: bool = False,
) -> models.User:
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


def get_auth_headers(
    client: TestClient, email: str, password: str = "testpassword"
) -> dict:
    response = client.post(
        "/auth/token", data={"username": email, "password": password}
    )
    token = response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def create_household_via_api(
    client: TestClient, headers: dict, name: str = "Test Household"
) -> dict:
    response = client.post("/households", json={"name": name}, headers=headers)
    assert response.status_code == 201
    return response.json()


def create_meal_template(db: Session, user_id) -> models.MealTemplate:
    template = models.MealTemplate(
        user_id=user_id,
        name="Test Template",
    )
    db.add(template)
    db.commit()
    db.refresh(template)
    return template


# --- Household CRUD Tests ---


class TestHouseholdCRUD:
    def test_create_household(self, client: TestClient, db: Session):
        user = create_test_user(db, email="hh_create@example.com")
        headers = get_auth_headers(client, user.email)
        data = create_household_via_api(client, headers, "My House")

        assert data["name"] == "My House"
        assert data["created_by"] == str(user.id)
        assert "id" in data

    def test_create_household_auto_membership(self, client: TestClient, db: Session):
        user = create_test_user(db, email="hh_automember@example.com")
        headers = get_auth_headers(client, user.email)
        hh = create_household_via_api(client, headers, "Auto Member House")

        # Check membership was created
        membership = (
            db.query(models.HouseholdMembership)
            .filter(
                models.HouseholdMembership.household_id == uuid.UUID(hh["id"]),
                models.HouseholdMembership.user_id == user.id,
            )
            .first()
        )
        assert membership is not None

    def test_list_households_member_only(self, client: TestClient, db: Session):
        user1 = create_test_user(db, email="hh_list1@example.com")
        user2 = create_test_user(db, email="hh_list2@example.com")
        h1 = get_auth_headers(client, user1.email)
        h2 = get_auth_headers(client, user2.email)

        create_household_via_api(client, h1, "House A")
        create_household_via_api(client, h2, "House B")

        # user1 should only see House A
        resp = client.get("/households", headers=h1)
        assert resp.status_code == 200
        names = [h["name"] for h in resp.json()]
        assert "House A" in names
        assert "House B" not in names

    def test_list_households_admin_sees_all(self, client: TestClient, db: Session):
        admin = create_test_user(db, email="hh_admin_list@example.com", is_admin=True)
        user = create_test_user(db, email="hh_regular_list@example.com")

        admin_headers = get_auth_headers(client, admin.email)
        user_headers = get_auth_headers(client, user.email)

        create_household_via_api(client, admin_headers, "Admin House")
        create_household_via_api(client, user_headers, "User House")

        resp = client.get(
            "/households",
            headers={**admin_headers, "X-Admin-Mode": "true"},
        )
        assert resp.status_code == 200
        names = [h["name"] for h in resp.json()]
        assert "Admin House" in names
        assert "User House" in names

    def test_get_household_as_member(self, client: TestClient, db: Session):
        user = create_test_user(db, email="hh_get@example.com")
        headers = get_auth_headers(client, user.email)
        hh = create_household_via_api(client, headers, "Get House")

        resp = client.get(f"/households/{hh['id']}", headers=headers)
        assert resp.status_code == 200
        assert resp.json()["name"] == "Get House"

    def test_get_household_non_member_forbidden(self, client: TestClient, db: Session):
        user1 = create_test_user(db, email="hh_get_owner@example.com")
        user2 = create_test_user(db, email="hh_get_other@example.com")
        h1 = get_auth_headers(client, user1.email)
        h2 = get_auth_headers(client, user2.email)

        hh = create_household_via_api(client, h1, "Private House")

        resp = client.get(f"/households/{hh['id']}", headers=h2)
        assert resp.status_code == 403

    def test_get_household_not_found(self, client: TestClient, db: Session):
        user = create_test_user(db, email="hh_get404@example.com")
        headers = get_auth_headers(client, user.email)

        resp = client.get(f"/households/{uuid.uuid4()}", headers=headers)
        assert resp.status_code == 404

    def test_rename_household_as_creator(self, client: TestClient, db: Session):
        user = create_test_user(db, email="hh_rename@example.com")
        headers = get_auth_headers(client, user.email)
        hh = create_household_via_api(client, headers, "Old Name")

        resp = client.patch(
            f"/households/{hh['id']}",
            json={"name": "New Name"},
            headers=headers,
        )
        assert resp.status_code == 200
        assert resp.json()["name"] == "New Name"

    def test_rename_household_as_admin(self, client: TestClient, db: Session):
        user = create_test_user(db, email="hh_rename_user@example.com")
        admin = create_test_user(db, email="hh_rename_admin@example.com", is_admin=True)
        user_headers = get_auth_headers(client, user.email)
        admin_headers = get_auth_headers(client, admin.email)

        hh = create_household_via_api(client, user_headers, "Rename Me")

        resp = client.patch(
            f"/households/{hh['id']}",
            json={"name": "Admin Renamed"},
            headers={**admin_headers, "X-Admin-Mode": "true"},
        )
        assert resp.status_code == 200
        assert resp.json()["name"] == "Admin Renamed"

    def test_rename_household_non_creator_forbidden(
        self, client: TestClient, db: Session
    ):
        user1 = create_test_user(db, email="hh_rename_creator@example.com")
        user2 = create_test_user(db, email="hh_rename_other@example.com")
        h1 = get_auth_headers(client, user1.email)
        h2 = get_auth_headers(client, user2.email)

        hh = create_household_via_api(client, h1, "No Touch")

        # user2 joins
        client.post(f"/households/{hh['id']}/join", headers=h2)

        resp = client.patch(
            f"/households/{hh['id']}",
            json={"name": "Hacked"},
            headers=h2,
        )
        assert resp.status_code == 403

    def test_delete_household(self, client: TestClient, db: Session):
        user = create_test_user(db, email="hh_delete@example.com")
        headers = get_auth_headers(client, user.email)
        hh = create_household_via_api(client, headers, "Delete Me")

        resp = client.delete(f"/households/{hh['id']}", headers=headers)
        assert resp.status_code == 204

        # Verify it's gone
        resp = client.get(f"/households/{hh['id']}", headers=headers)
        assert resp.status_code == 404

    def test_delete_household_soft_unlinks_meals(self, client: TestClient, db: Session):
        user = create_test_user(db, email="hh_delete_meal@example.com")
        headers = get_auth_headers(client, user.email)
        hh = create_household_via_api(client, headers, "Meal House")

        # Create a meal linked to this household
        meal = models.Meal(
            user_id=user.id,
            name="Linked Meal",
            household_id=uuid.UUID(hh["id"]),
        )
        db.add(meal)
        db.commit()
        db.refresh(meal)
        meal_id = meal.id

        # Delete household
        resp = client.delete(f"/households/{hh['id']}", headers=headers)
        assert resp.status_code == 204

        # Meal should still exist but household_id should be NULL
        db.expire_all()
        updated_meal = db.query(models.Meal).filter(models.Meal.id == meal_id).first()
        assert updated_meal is not None
        assert updated_meal.household_id is None


# --- Membership Tests ---


class TestMembership:
    def test_join_household(self, client: TestClient, db: Session):
        user1 = create_test_user(db, email="hh_join_owner@example.com")
        user2 = create_test_user(db, email="hh_join_member@example.com")
        h1 = get_auth_headers(client, user1.email)
        h2 = get_auth_headers(client, user2.email)

        hh = create_household_via_api(client, h1, "Join Me")

        resp = client.post(f"/households/{hh['id']}/join", headers=h2)
        assert resp.status_code == 201
        assert resp.json()["user_id"] == str(user2.id)

    def test_double_join_conflict(self, client: TestClient, db: Session):
        user1 = create_test_user(db, email="hh_djoin_owner@example.com")
        user2 = create_test_user(db, email="hh_djoin_member@example.com")
        h1 = get_auth_headers(client, user1.email)
        h2 = get_auth_headers(client, user2.email)

        hh = create_household_via_api(client, h1, "Double Join")
        client.post(f"/households/{hh['id']}/join", headers=h2)

        resp = client.post(f"/households/{hh['id']}/join", headers=h2)
        assert resp.status_code == 409

    def test_creator_double_join_conflict(self, client: TestClient, db: Session):
        user = create_test_user(db, email="hh_creator_djoin@example.com")
        headers = get_auth_headers(client, user.email)
        hh = create_household_via_api(client, headers, "Creator Double")

        resp = client.post(f"/households/{hh['id']}/join", headers=headers)
        assert resp.status_code == 409

    def test_leave_household(self, client: TestClient, db: Session):
        user1 = create_test_user(db, email="hh_leave_owner@example.com")
        user2 = create_test_user(db, email="hh_leave_member@example.com")
        h1 = get_auth_headers(client, user1.email)
        h2 = get_auth_headers(client, user2.email)

        hh = create_household_via_api(client, h1, "Leave Me")
        client.post(f"/households/{hh['id']}/join", headers=h2)

        resp = client.delete(f"/households/{hh['id']}/leave", headers=h2)
        assert resp.status_code == 204

    def test_leave_not_a_member(self, client: TestClient, db: Session):
        user1 = create_test_user(db, email="hh_leavenm_owner@example.com")
        user2 = create_test_user(db, email="hh_leavenm_other@example.com")
        h1 = get_auth_headers(client, user1.email)
        h2 = get_auth_headers(client, user2.email)

        hh = create_household_via_api(client, h1, "Not A Member")

        resp = client.delete(f"/households/{hh['id']}/leave", headers=h2)
        assert resp.status_code == 404

    def test_list_members(self, client: TestClient, db: Session):
        user1 = create_test_user(db, email="hh_members_owner@example.com")
        user2 = create_test_user(db, email="hh_members_member@example.com")
        h1 = get_auth_headers(client, user1.email)
        h2 = get_auth_headers(client, user2.email)

        hh = create_household_via_api(client, h1, "Members House")
        client.post(f"/households/{hh['id']}/join", headers=h2)

        resp = client.get(f"/households/{hh['id']}/members", headers=h1)
        assert resp.status_code == 200
        members = resp.json()
        assert len(members) == 2
        user_ids = [m["user_id"] for m in members]
        assert str(user1.id) in user_ids
        assert str(user2.id) in user_ids

    def test_list_members_non_member_forbidden(self, client: TestClient, db: Session):
        user1 = create_test_user(db, email="hh_listmem_owner@example.com")
        user2 = create_test_user(db, email="hh_listmem_other@example.com")
        h1 = get_auth_headers(client, user1.email)
        h2 = get_auth_headers(client, user2.email)

        hh = create_household_via_api(client, h1, "No Peek")

        resp = client.get(f"/households/{hh['id']}/members", headers=h2)
        assert resp.status_code == 403

    def test_remove_member_as_creator(self, client: TestClient, db: Session):
        user1 = create_test_user(db, email="hh_remove_creator@example.com")
        user2 = create_test_user(db, email="hh_remove_target@example.com")
        h1 = get_auth_headers(client, user1.email)
        h2 = get_auth_headers(client, user2.email)

        hh = create_household_via_api(client, h1, "Remove House")
        client.post(f"/households/{hh['id']}/join", headers=h2)

        resp = client.delete(f"/households/{hh['id']}/members/{user2.id}", headers=h1)
        assert resp.status_code == 204

    def test_remove_member_as_admin(self, client: TestClient, db: Session):
        user = create_test_user(db, email="hh_rmadmin_user@example.com")
        admin = create_test_user(
            db, email="hh_rmadmin_admin@example.com", is_admin=True
        )
        user_headers = get_auth_headers(client, user.email)
        admin_headers = get_auth_headers(client, admin.email)

        hh = create_household_via_api(client, user_headers, "Admin Remove")

        # admin joins then removes user
        resp = client.delete(
            f"/households/{hh['id']}/members/{user.id}",
            headers={**admin_headers, "X-Admin-Mode": "true"},
        )
        assert resp.status_code == 204

    def test_non_creator_cannot_remove(self, client: TestClient, db: Session):
        user1 = create_test_user(db, email="hh_ncremove_owner@example.com")
        user2 = create_test_user(db, email="hh_ncremove_member@example.com")
        user3 = create_test_user(db, email="hh_ncremove_target@example.com")
        h1 = get_auth_headers(client, user1.email)
        h2 = get_auth_headers(client, user2.email)
        h3 = get_auth_headers(client, user3.email)

        hh = create_household_via_api(client, h1, "No Remove")
        client.post(f"/households/{hh['id']}/join", headers=h2)
        client.post(f"/households/{hh['id']}/join", headers=h3)

        # user2 tries to remove user3
        resp = client.delete(f"/households/{hh['id']}/members/{user3.id}", headers=h2)
        assert resp.status_code == 403

    def test_cannot_remove_self_via_members_endpoint(
        self, client: TestClient, db: Session
    ):
        user = create_test_user(db, email="hh_selfremove@example.com")
        headers = get_auth_headers(client, user.email)
        hh = create_household_via_api(client, headers, "Self Remove")

        resp = client.delete(
            f"/households/{hh['id']}/members/{user.id}", headers=headers
        )
        assert resp.status_code == 400


# --- Template Exclusion Tests ---


class TestTemplateExclusions:
    def test_list_disabled_templates_empty(self, client: TestClient, db: Session):
        user = create_test_user(db, email="hh_excl_list@example.com")
        headers = get_auth_headers(client, user.email)
        hh = create_household_via_api(client, headers, "Exclusion House")

        resp = client.get(
            f"/households/{hh['id']}/disabled-templates",
            headers=headers,
        )
        assert resp.status_code == 200
        assert resp.json() == []

    def test_disable_template(self, client: TestClient, db: Session):
        user = create_test_user(db, email="hh_excl_add@example.com")
        headers = get_auth_headers(client, user.email)
        hh = create_household_via_api(client, headers, "Disable House")

        template = create_meal_template(db, user.id)

        resp = client.post(
            f"/households/{hh['id']}/disabled-templates",
            json={"template_id": str(template.id)},
            headers=headers,
        )
        assert resp.status_code == 201
        assert resp.json()["template_id"] == str(template.id)

    def test_double_disable_conflict(self, client: TestClient, db: Session):
        user = create_test_user(db, email="hh_excl_double@example.com")
        headers = get_auth_headers(client, user.email)
        hh = create_household_via_api(client, headers, "Double Disable")

        template = create_meal_template(db, user.id)

        client.post(
            f"/households/{hh['id']}/disabled-templates",
            json={"template_id": str(template.id)},
            headers=headers,
        )

        resp = client.post(
            f"/households/{hh['id']}/disabled-templates",
            json={"template_id": str(template.id)},
            headers=headers,
        )
        assert resp.status_code == 409

    def test_disable_nonexistent_template(self, client: TestClient, db: Session):
        user = create_test_user(db, email="hh_excl_notempl@example.com")
        headers = get_auth_headers(client, user.email)
        hh = create_household_via_api(client, headers, "No Template")

        resp = client.post(
            f"/households/{hh['id']}/disabled-templates",
            json={"template_id": str(uuid.uuid4())},
            headers=headers,
        )
        assert resp.status_code == 404

    def test_re_enable_template(self, client: TestClient, db: Session):
        user = create_test_user(db, email="hh_excl_enable@example.com")
        headers = get_auth_headers(client, user.email)
        hh = create_household_via_api(client, headers, "Enable House")

        template = create_meal_template(db, user.id)

        client.post(
            f"/households/{hh['id']}/disabled-templates",
            json={"template_id": str(template.id)},
            headers=headers,
        )

        resp = client.delete(
            f"/households/{hh['id']}/disabled-templates/{template.id}",
            headers=headers,
        )
        assert resp.status_code == 204

        # Verify it's removed
        resp = client.get(
            f"/households/{hh['id']}/disabled-templates",
            headers=headers,
        )
        assert resp.json() == []

    def test_re_enable_not_found(self, client: TestClient, db: Session):
        user = create_test_user(db, email="hh_excl_nf@example.com")
        headers = get_auth_headers(client, user.email)
        hh = create_household_via_api(client, headers, "Not Found Enable")

        resp = client.delete(
            f"/households/{hh['id']}/disabled-templates/{uuid.uuid4()}",
            headers=headers,
        )
        assert resp.status_code == 404

    def test_non_member_cannot_manage_exclusions(self, client: TestClient, db: Session):
        user1 = create_test_user(db, email="hh_excl_nm_owner@example.com")
        user2 = create_test_user(db, email="hh_excl_nm_other@example.com")
        h1 = get_auth_headers(client, user1.email)
        h2 = get_auth_headers(client, user2.email)

        hh = create_household_via_api(client, h1, "No Access Exclusions")
        template = create_meal_template(db, user1.id)

        # Non-member cannot list
        resp = client.get(f"/households/{hh['id']}/disabled-templates", headers=h2)
        assert resp.status_code == 403

        # Non-member cannot disable
        resp = client.post(
            f"/households/{hh['id']}/disabled-templates",
            json={"template_id": str(template.id)},
            headers=h2,
        )
        assert resp.status_code == 403

        # Non-member cannot re-enable
        resp = client.delete(
            f"/households/{hh['id']}/disabled-templates/{template.id}",
            headers=h2,
        )
        assert resp.status_code == 403


# --- Primary Household Tests ---


class TestPrimaryHousehold:
    def test_set_primary_household(self, client: TestClient, db: Session):
        user = create_test_user(db, email="hh_primary@example.com")
        headers = get_auth_headers(client, user.email)
        hh = create_household_via_api(client, headers, "Primary House")

        resp = client.patch(
            "/users/me/primary-household",
            json={"household_id": hh["id"]},
            headers=headers,
        )
        assert resp.status_code == 200
        assert resp.json()["message"] == "Primary household updated"

        # Verify in DB
        membership = (
            db.query(models.HouseholdMembership)
            .filter(
                models.HouseholdMembership.household_id == uuid.UUID(hh["id"]),
                models.HouseholdMembership.user_id == user.id,
            )
            .first()
        )
        assert membership.is_primary is True

    def test_clear_primary_household(self, client: TestClient, db: Session):
        user = create_test_user(db, email="hh_clear_primary@example.com")
        headers = get_auth_headers(client, user.email)
        hh = create_household_via_api(client, headers, "Clear Primary")

        # Set primary first
        client.patch(
            "/users/me/primary-household",
            json={"household_id": hh["id"]},
            headers=headers,
        )

        # Clear
        resp = client.patch(
            "/users/me/primary-household",
            json={"household_id": None},
            headers=headers,
        )
        assert resp.status_code == 200
        assert resp.json()["message"] == "Primary household cleared"

        # Verify
        db.expire_all()
        membership = (
            db.query(models.HouseholdMembership)
            .filter(
                models.HouseholdMembership.household_id == uuid.UUID(hh["id"]),
                models.HouseholdMembership.user_id == user.id,
            )
            .first()
        )
        assert membership.is_primary is False

    def test_set_primary_not_a_member(self, client: TestClient, db: Session):
        user1 = create_test_user(db, email="hh_primary_nm_owner@example.com")
        user2 = create_test_user(db, email="hh_primary_nm_other@example.com")
        h1 = get_auth_headers(client, user1.email)
        h2 = get_auth_headers(client, user2.email)

        hh = create_household_via_api(client, h1, "Not My House")

        resp = client.patch(
            "/users/me/primary-household",
            json={"household_id": hh["id"]},
            headers=h2,
        )
        assert resp.status_code == 403

    def test_set_primary_switches_between_households(
        self, client: TestClient, db: Session
    ):
        user = create_test_user(db, email="hh_primary_switch@example.com")
        headers = get_auth_headers(client, user.email)
        hh1 = create_household_via_api(client, headers, "House 1")
        hh2 = create_household_via_api(client, headers, "House 2")

        # Set first as primary
        client.patch(
            "/users/me/primary-household",
            json={"household_id": hh1["id"]},
            headers=headers,
        )

        # Switch to second
        client.patch(
            "/users/me/primary-household",
            json={"household_id": hh2["id"]},
            headers=headers,
        )

        db.expire_all()
        m1 = (
            db.query(models.HouseholdMembership)
            .filter(
                models.HouseholdMembership.household_id == uuid.UUID(hh1["id"]),
                models.HouseholdMembership.user_id == user.id,
            )
            .first()
        )
        m2 = (
            db.query(models.HouseholdMembership)
            .filter(
                models.HouseholdMembership.household_id == uuid.UUID(hh2["id"]),
                models.HouseholdMembership.user_id == user.id,
            )
            .first()
        )
        assert m1.is_primary is False
        assert m2.is_primary is True
