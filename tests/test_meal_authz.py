"""Tests for meals authorization using AuthContext (X-Admin-Mode / X-Act-As-User).

Tests written FIRST (TDD) - these will fail until meals endpoints are migrated
to use get_auth_context instead of get_current_active_user.

Authorization rules being tested:
- Any authenticated user can CREATE meals (assigned to effective_user).
- Only the OWNER of a meal can VIEW, UPDATE, or DELETE it (user mode).
- An ADMIN in admin mode (is_admin_mode=True) can view/update/delete ANY meal.
- An ADMIN in impersonation mode sees and operates on the impersonated user's meals.
"""

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app import crud, schemas, models


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
    """Create a user (if not exists), set admin flag if needed, return (user, headers)."""
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


def create_recipe_direct(db: Session, user_id, name: str):
    """Create a recipe directly in the DB."""
    recipe = models.Recipe(
        name=name,
        owner_id=user_id,
        description="Test description",
        instructions=[],
        components=[],
    )
    db.add(recipe)
    db.commit()
    db.refresh(recipe)
    return recipe


def create_template_for_user(client: TestClient, headers: dict, name: str, recipe_id: str):
    """Create a meal template via the API."""
    template_data = {
        "name": name,
        "slots": [{"strategy": "Direct", "recipe_id": recipe_id}],
    }
    response = client.post("/meals/templates", json=template_data, headers=headers)
    assert response.status_code == 201, f"Template creation failed: {response.json()}"
    return response.json()


def create_meal_direct(db: Session, user_id, name: str = "Test Meal"):
    """Create a meal directly in the DB for a specific user."""
    meal = models.Meal(
        user_id=user_id,
        name=name,
        status=models.MealStatus.QUEUED,
        queue_position=1,
    )
    db.add(meal)
    db.commit()
    db.refresh(meal)
    return meal


# ---------------------------------------------------------------------------
# GET /meals - list filtering by ownership
# ---------------------------------------------------------------------------


def test_get_meals_user_mode_returns_only_own_meals(client: TestClient, db: Session):
    """GET /meals in user mode returns only the caller's meals."""
    user_a, headers_a = create_user_and_login(client, db, "authz_list_a@example.com")
    user_b, headers_b = create_user_and_login(client, db, "authz_list_b@example.com")

    meal_a = create_meal_direct(db, user_a.id, "User A Meal")
    meal_b = create_meal_direct(db, user_b.id, "User B Meal")

    response = client.get("/meals/", headers=headers_a)
    assert response.status_code == 200

    meal_ids = [m["id"] for m in response.json()]
    assert str(meal_a.id) in meal_ids, "User A should see their own meal"
    assert str(meal_b.id) not in meal_ids, "User A should NOT see User B's meal"


def test_get_meals_admin_mode_returns_all_meals(client: TestClient, db: Session):
    """GET /meals with X-Admin-Mode: true returns meals from all users."""
    user_a, headers_a = create_user_and_login(client, db, "authz_admin_list_a@example.com")
    user_b, _ = create_user_and_login(client, db, "authz_admin_list_b@example.com")
    admin, admin_base_headers = create_user_and_login(
        client, db, "authz_admin_list_admin@example.com", is_admin=True
    )
    admin_headers = {**admin_base_headers, "X-Admin-Mode": "true"}

    meal_a = create_meal_direct(db, user_a.id, "Admin List Meal A")
    meal_b = create_meal_direct(db, user_b.id, "Admin List Meal B")

    response = client.get("/meals/", headers=admin_headers)
    assert response.status_code == 200

    meal_ids = [m["id"] for m in response.json()]
    assert str(meal_a.id) in meal_ids, "Admin mode should see User A's meal"
    assert str(meal_b.id) in meal_ids, "Admin mode should see User B's meal"


def test_get_meals_act_as_user_returns_target_user_meals(client: TestClient, db: Session):
    """GET /meals with X-Act-As-User returns only the target user's meals."""
    user_a, _ = create_user_and_login(client, db, "authz_actaslist_a@example.com")
    user_b, _ = create_user_and_login(client, db, "authz_actaslist_b@example.com")
    admin, admin_base_headers = create_user_and_login(
        client, db, "authz_actaslist_admin@example.com", is_admin=True
    )
    impersonate_headers = {**admin_base_headers, "X-Act-As-User": str(user_a.id)}

    meal_a = create_meal_direct(db, user_a.id, "ActAs List Meal A")
    meal_b = create_meal_direct(db, user_b.id, "ActAs List Meal B")

    response = client.get("/meals/", headers=impersonate_headers)
    assert response.status_code == 200

    meal_ids = [m["id"] for m in response.json()]
    assert str(meal_a.id) in meal_ids, "Impersonation should see target user's meal"
    assert str(meal_b.id) not in meal_ids, "Impersonation should NOT see other user's meal"


# ---------------------------------------------------------------------------
# GET /meals/{id} - single meal ownership checks
# ---------------------------------------------------------------------------


def test_get_meal_by_id_returns_403_for_non_owner(client: TestClient, db: Session):
    """GET /meals/{id} returns 403 when caller is not the owner in user mode."""
    owner, _ = create_user_and_login(client, db, "authz_get403_owner@example.com")
    _, other_headers = create_user_and_login(client, db, "authz_get403_other@example.com")

    meal = create_meal_direct(db, owner.id, "Owner Only Meal")

    response = client.get(f"/meals/{meal.id}", headers=other_headers)
    assert response.status_code == 403


def test_get_meal_by_id_admin_mode_returns_any_meal(client: TestClient, db: Session):
    """GET /meals/{id} with X-Admin-Mode: true can access any meal."""
    owner, _ = create_user_and_login(client, db, "authz_getadmin_owner@example.com")
    admin, admin_base_headers = create_user_and_login(
        client, db, "authz_getadmin_admin@example.com", is_admin=True
    )
    admin_headers = {**admin_base_headers, "X-Admin-Mode": "true"}

    meal = create_meal_direct(db, owner.id, "Admin Accessible Meal")

    response = client.get(f"/meals/{meal.id}", headers=admin_headers)
    assert response.status_code == 200
    assert response.json()["id"] == str(meal.id)


def test_get_meal_by_id_act_as_user_returns_target_meal(client: TestClient, db: Session):
    """GET /meals/{id} with X-Act-As-User can access target user's meal."""
    target, _ = create_user_and_login(client, db, "authz_getimpersonate_target@example.com")
    admin, admin_base_headers = create_user_and_login(
        client, db, "authz_getimpersonate_admin@example.com", is_admin=True
    )
    impersonate_headers = {**admin_base_headers, "X-Act-As-User": str(target.id)}

    meal = create_meal_direct(db, target.id, "Impersonated Target Meal")

    response = client.get(f"/meals/{meal.id}", headers=impersonate_headers)
    assert response.status_code == 200
    assert response.json()["id"] == str(meal.id)


def test_get_meal_by_id_owner_can_access_own_meal(client: TestClient, db: Session):
    """GET /meals/{id} succeeds for the meal owner in user mode."""
    owner, owner_headers = create_user_and_login(client, db, "authz_getowner@example.com")

    meal = create_meal_direct(db, owner.id, "My Own Meal")

    response = client.get(f"/meals/{meal.id}", headers=owner_headers)
    assert response.status_code == 200
    assert response.json()["id"] == str(meal.id)


# ---------------------------------------------------------------------------
# POST /meals - ownership assignment
# ---------------------------------------------------------------------------


def test_post_meal_assigns_to_effective_user(client: TestClient, db: Session):
    """POST /meals creates the meal owned by the caller (effective_user)."""
    user, headers = create_user_and_login(client, db, "authz_create_user@example.com")

    meal_data = {
        "name": "My New Meal",
        "status": "Queued",
        "items": [],
    }
    response = client.post("/meals/", json=meal_data, headers=headers)
    assert response.status_code == 201

    created = response.json()
    assert created["name"] == "My New Meal"

    # Verify in DB that the meal belongs to the user
    from uuid import UUID as _UUID
    meal_in_db = db.query(models.Meal).filter(
        models.Meal.id == _UUID(created["id"])
    ).first()
    assert meal_in_db is not None
    assert meal_in_db.user_id == user.id


def test_post_meal_impersonation_assigns_to_target_user(client: TestClient, db: Session):
    """POST /meals with X-Act-As-User assigns the meal to the target user, not the admin."""
    target, _ = create_user_and_login(client, db, "authz_create_target@example.com")
    admin, admin_base_headers = create_user_and_login(
        client, db, "authz_create_admin@example.com", is_admin=True
    )
    impersonate_headers = {**admin_base_headers, "X-Act-As-User": str(target.id)}

    meal_data = {
        "name": "Impersonated Meal Creation",
        "status": "Queued",
        "items": [],
    }
    response = client.post("/meals/", json=meal_data, headers=impersonate_headers)
    assert response.status_code == 201

    created = response.json()

    from uuid import UUID as _UUID
    meal_in_db = db.query(models.Meal).filter(
        models.Meal.id == _UUID(created["id"])
    ).first()
    assert meal_in_db is not None
    assert meal_in_db.user_id == target.id, "Meal should belong to target user, not admin"


# ---------------------------------------------------------------------------
# POST /meals/generate - template scoping
# ---------------------------------------------------------------------------


def test_generate_meals_scopes_templates_to_effective_user(client: TestClient, db: Session):
    """POST /meals/generate only uses templates belonging to the effective user."""
    user_a, headers_a = create_user_and_login(client, db, "authz_gen_a@example.com")
    user_b, headers_b = create_user_and_login(client, db, "authz_gen_b@example.com")

    # Create recipe and template for user A
    recipe_a = create_recipe_direct(db, user_a.id, "Gen Recipe A")
    create_template_for_user(client, headers_a, "Gen Template A", str(recipe_a.id))

    # User B tries to generate: should get no meals because they have no templates
    response = client.post("/meals/generate", json={"count": 5}, headers=headers_b)
    assert response.status_code == 201
    assert response.json() == [], "User B has no templates, should get empty result"


def test_generate_meals_impersonation_scopes_to_target(client: TestClient, db: Session):
    """POST /meals/generate with X-Act-As-User uses target user's templates."""
    target, target_headers = create_user_and_login(
        client, db, "authz_gen_target@example.com"
    )
    admin, admin_base_headers = create_user_and_login(
        client, db, "authz_gen_admin@example.com", is_admin=True
    )
    impersonate_headers = {**admin_base_headers, "X-Act-As-User": str(target.id)}

    # Create recipe and template for target user
    recipe_t = create_recipe_direct(db, target.id, "Gen Target Recipe")
    create_template_for_user(client, target_headers, "Gen Target Template", str(recipe_t.id))

    # Admin impersonates target and generates: should use target's templates
    response = client.post("/meals/generate", json={"count": 1}, headers=impersonate_headers)
    assert response.status_code == 201
    meals = response.json()
    assert len(meals) == 1, "Should generate 1 meal from target's template"

    # Verify the generated meal belongs to target user
    from uuid import UUID as _UUID
    meal_in_db = db.query(models.Meal).filter(
        models.Meal.id == _UUID(meals[0]["id"])
    ).first()
    assert meal_in_db.user_id == target.id, "Generated meal should belong to target user"


# ---------------------------------------------------------------------------
# PUT /meals/{id} - update authorization
# ---------------------------------------------------------------------------


def test_put_meal_rejects_non_owner(client: TestClient, db: Session):
    """PUT /meals/{id} returns 403 for non-owner in user mode."""
    owner, _ = create_user_and_login(client, db, "authz_put403_owner@example.com")
    _, other_headers = create_user_and_login(client, db, "authz_put403_other@example.com")

    meal = create_meal_direct(db, owner.id, "Owner Update Meal")

    response = client.put(
        f"/meals/{meal.id}",
        json={"name": "Hacked Name"},
        headers=other_headers,
    )
    assert response.status_code == 403


def test_put_meal_admin_mode_allows_any_meal(client: TestClient, db: Session):
    """PUT /meals/{id} with X-Admin-Mode: true can update any meal."""
    owner, _ = create_user_and_login(client, db, "authz_putadmin_owner@example.com")
    admin, admin_base_headers = create_user_and_login(
        client, db, "authz_putadmin_admin@example.com", is_admin=True
    )
    admin_headers = {**admin_base_headers, "X-Admin-Mode": "true"}

    meal = create_meal_direct(db, owner.id, "Admin Update Target")

    response = client.put(
        f"/meals/{meal.id}",
        json={"name": "Admin Updated Name"},
        headers=admin_headers,
    )
    assert response.status_code == 200
    assert response.json()["name"] == "Admin Updated Name"


def test_put_meal_owner_can_update_own_meal(client: TestClient, db: Session):
    """PUT /meals/{id} succeeds for the meal owner."""
    owner, owner_headers = create_user_and_login(
        client, db, "authz_putowner@example.com"
    )

    meal = create_meal_direct(db, owner.id, "My Meal To Update")

    response = client.put(
        f"/meals/{meal.id}",
        json={"name": "My Updated Meal"},
        headers=owner_headers,
    )
    assert response.status_code == 200
    assert response.json()["name"] == "My Updated Meal"


# ---------------------------------------------------------------------------
# DELETE /meals/{id} - delete authorization
# ---------------------------------------------------------------------------


def test_delete_meal_rejects_non_owner(client: TestClient, db: Session):
    """DELETE /meals/{id} returns 403 for non-owner in user mode."""
    owner, _ = create_user_and_login(client, db, "authz_del403_owner@example.com")
    _, other_headers = create_user_and_login(client, db, "authz_del403_other@example.com")

    meal = create_meal_direct(db, owner.id, "Owner Delete Meal")

    response = client.delete(f"/meals/{meal.id}", headers=other_headers)
    assert response.status_code == 403


def test_delete_meal_admin_mode_allows_any_meal(client: TestClient, db: Session):
    """DELETE /meals/{id} with X-Admin-Mode: true can delete any meal."""
    owner, _ = create_user_and_login(client, db, "authz_deladmin_owner@example.com")
    admin, admin_base_headers = create_user_and_login(
        client, db, "authz_deladmin_admin@example.com", is_admin=True
    )
    admin_headers = {**admin_base_headers, "X-Admin-Mode": "true"}

    meal = create_meal_direct(db, owner.id, "Admin Delete Target")

    response = client.delete(f"/meals/{meal.id}", headers=admin_headers)
    assert response.status_code == 204

    # Confirm it's gone
    get_response = client.get(f"/meals/{meal.id}", headers=admin_headers)
    assert get_response.status_code == 404


def test_delete_meal_owner_can_delete_own_meal(client: TestClient, db: Session):
    """DELETE /meals/{id} succeeds for the meal owner."""
    owner, owner_headers = create_user_and_login(
        client, db, "authz_delowner@example.com"
    )

    meal = create_meal_direct(db, owner.id, "My Meal To Delete")

    response = client.delete(f"/meals/{meal.id}", headers=owner_headers)
    assert response.status_code == 204
