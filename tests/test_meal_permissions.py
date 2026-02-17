"""Tests for meal and template authorization.

Verifies that:
- Any authenticated user can read meals/templates (even ones they don't own)
- Only owner OR admin can update/delete meals/templates
- Non-owner, non-admin gets 403 when trying to update/delete
"""

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app import crud, schemas


def get_auth_headers(
    client: TestClient,
    db: Session,
    email: str,
    password: str = "password",
    is_admin: bool = False,
):
    """Create a user and return auth headers."""
    try:
        user_in = schemas.UserCreate(email=email, password=password)
        user = crud.create_user(db, user_in)
        if is_admin:
            user.is_admin = True
            db.add(user)
            db.commit()
    except Exception:
        user = crud.get_user_by_email(db, email=email)
        if user and is_admin != user.is_admin:
            user.is_admin = is_admin
            db.add(user)
            db.commit()

    response = client.post(
        "/auth/token",
        data={"username": email, "password": password},
    )
    token = response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def create_recipe(client: TestClient, headers: dict, name: str = "Test Recipe"):
    """Create a recipe and return its data."""
    recipe_data = {
        "core": {"name": name},
        "times": {},
        "nutrition": {},
        "components": [],
        "instructions": [],
    }
    response = client.post("/recipes/", json=recipe_data, headers=headers)
    assert response.status_code == 201
    return response.json()


def create_template(
    client: TestClient,
    headers: dict,
    name: str = "Test Template",
    recipe_id: str = None,
):
    """Create a meal template and return its data."""
    # If no recipe_id provided, create a recipe first
    if recipe_id is None:
        recipe = create_recipe(client, headers, name=f"Recipe for {name}")
        recipe_id = recipe["core"]["id"]

    template_data = {
        "name": name,
        "slots": [{"strategy": "Direct", "recipe_id": recipe_id}],
    }
    response = client.post("/meals/templates", json=template_data, headers=headers)
    assert response.status_code == 201
    return response.json()


def create_meal(
    client: TestClient, headers: dict, template_id: str, name: str = "Test Meal"
):
    """Generate a meal from a template and return its data."""
    response = client.post("/meals/generate", headers=headers, json={"count": 1})
    assert response.status_code == 201
    data = response.json()
    assert isinstance(data, list)
    assert len(data) == 1
    return data[0]


# =============================================================================
# Template Read Tests
# =============================================================================


def test_any_user_can_read_template_list(client: TestClient, db: Session):
    """Any authenticated user can list all templates."""
    owner_headers = get_auth_headers(client, db, email="tmpl_owner1@example.com")
    template = create_template(client, owner_headers, name="Owner Template")
    template_id = template["id"]

    other_headers = get_auth_headers(client, db, email="tmpl_other1@example.com")

    response = client.get("/meals/templates", headers=other_headers)
    assert response.status_code == 200

    template_ids = [t["id"] for t in response.json()]
    assert template_id in template_ids


def test_any_user_can_read_single_template(client: TestClient, db: Session):
    """Any authenticated user can read a specific template by ID."""
    owner_headers = get_auth_headers(client, db, email="tmpl_owner2@example.com")
    template = create_template(client, owner_headers, name="Readable Template")
    template_id = template["id"]

    other_headers = get_auth_headers(client, db, email="tmpl_other2@example.com")

    response = client.get(f"/meals/templates/{template_id}", headers=other_headers)
    assert response.status_code == 200
    assert response.json()["id"] == template_id
    assert response.json()["name"] == "Readable Template"


def test_user_generates_meal_from_own_templates(client: TestClient, db: Session):
    """A user generates meals from their own templates."""
    user_headers = get_auth_headers(client, db, email="tmpl_owner3@example.com")
    create_template(client, user_headers, name="My Template")

    response = client.post("/meals/generate", headers=user_headers, json={"count": 1})
    assert response.status_code == 201
    data = response.json()
    assert isinstance(data, list)
    assert len(data) == 1
    assert "My Template" in data[0]["name"]


# =============================================================================
# Template Update/Delete - Owner Tests
# =============================================================================


def test_owner_can_update_template(client: TestClient, db: Session):
    """Owner can update their own template."""
    owner_headers = get_auth_headers(client, db, email="tmpl_owner4@example.com")
    template = create_template(client, owner_headers)
    template_id = template["id"]

    update_data = {"name": "Updated Name"}
    response = client.put(
        f"/meals/templates/{template_id}", json=update_data, headers=owner_headers
    )

    assert response.status_code == 200
    assert response.json()["name"] == "Updated Name"


def test_owner_can_delete_template(client: TestClient, db: Session):
    """Owner can delete their own template."""
    owner_headers = get_auth_headers(client, db, email="tmpl_owner5@example.com")
    template = create_template(client, owner_headers)
    template_id = template["id"]

    response = client.delete(f"/meals/templates/{template_id}", headers=owner_headers)
    assert response.status_code == 204

    get_response = client.get(f"/meals/templates/{template_id}", headers=owner_headers)
    assert get_response.status_code == 404


# =============================================================================
# Template Update/Delete - Admin Tests
# =============================================================================


def test_admin_can_update_other_user_template(client: TestClient, db: Session):
    """Admin with X-Admin-Mode can update another user's template."""
    owner_headers = get_auth_headers(client, db, email="tmpl_owner6@example.com")
    template = create_template(client, owner_headers)
    template_id = template["id"]

    admin_base_headers = get_auth_headers(
        client, db, email="tmpl_admin1@example.com", is_admin=True
    )
    admin_headers = {**admin_base_headers, "X-Admin-Mode": "true"}

    update_data = {"name": "Admin Edited"}
    response = client.put(
        f"/meals/templates/{template_id}", json=update_data, headers=admin_headers
    )

    assert response.status_code == 200
    assert response.json()["name"] == "Admin Edited"


def test_admin_can_delete_other_user_template(client: TestClient, db: Session):
    """Admin with X-Admin-Mode can delete another user's template."""
    owner_headers = get_auth_headers(client, db, email="tmpl_owner7@example.com")
    template = create_template(client, owner_headers)
    template_id = template["id"]

    admin_base_headers = get_auth_headers(
        client, db, email="tmpl_admin2@example.com", is_admin=True
    )
    admin_headers = {**admin_base_headers, "X-Admin-Mode": "true"}

    response = client.delete(f"/meals/templates/{template_id}", headers=admin_headers)
    assert response.status_code == 204

    get_response = client.get(f"/meals/templates/{template_id}", headers=owner_headers)
    assert get_response.status_code == 404


# =============================================================================
# Template Update/Delete - Non-Owner Tests (403)
# =============================================================================


def test_non_owner_cannot_update_template(client: TestClient, db: Session):
    """Non-owner, non-admin cannot update another user's template."""
    owner_headers = get_auth_headers(client, db, email="tmpl_owner8@example.com")
    template = create_template(client, owner_headers)
    template_id = template["id"]

    stranger_headers = get_auth_headers(client, db, email="tmpl_stranger1@example.com")

    update_data = {"name": "Hacked"}
    response = client.put(
        f"/meals/templates/{template_id}", json=update_data, headers=stranger_headers
    )

    assert response.status_code == 403
    assert "Not authorized" in response.json()["detail"]


def test_non_owner_cannot_delete_template(client: TestClient, db: Session):
    """Non-owner, non-admin cannot delete another user's template."""
    owner_headers = get_auth_headers(client, db, email="tmpl_owner9@example.com")
    template = create_template(client, owner_headers)
    template_id = template["id"]

    stranger_headers = get_auth_headers(client, db, email="tmpl_stranger2@example.com")

    response = client.delete(
        f"/meals/templates/{template_id}", headers=stranger_headers
    )

    assert response.status_code == 403
    assert "Not authorized" in response.json()["detail"]


# =============================================================================
# Meal Read Tests
# =============================================================================


def test_owner_can_read_own_meal_list(client: TestClient, db: Session):
    """Owner can list their own meals; non-owners cannot see them."""
    owner_headers = get_auth_headers(client, db, email="meal_owner1@example.com")
    template = create_template(client, owner_headers, name="Meal Template 1")
    meal = create_meal(client, owner_headers, template["id"])
    meal_id = meal["id"]

    # Owner can see their own meal
    response = client.get("/meals/", headers=owner_headers)
    assert response.status_code == 200
    meal_ids = [m["id"] for m in response.json()]
    assert meal_id in meal_ids

    # Other user cannot see the owner's meal
    other_headers = get_auth_headers(client, db, email="meal_other1@example.com")
    response = client.get("/meals/", headers=other_headers)
    assert response.status_code == 200
    meal_ids = [m["id"] for m in response.json()]
    assert meal_id not in meal_ids


def test_non_owner_cannot_read_single_meal(client: TestClient, db: Session):
    """Non-owner cannot read another user's meal by ID (returns 403)."""
    owner_headers = get_auth_headers(client, db, email="meal_owner2@example.com")
    template = create_template(client, owner_headers, name="Meal Template 2")
    meal = create_meal(client, owner_headers, template["id"])
    meal_id = meal["id"]

    other_headers = get_auth_headers(client, db, email="meal_other2@example.com")

    response = client.get(f"/meals/{meal_id}", headers=other_headers)
    assert response.status_code == 403


# =============================================================================
# Meal Update/Delete - Owner Tests
# =============================================================================


def test_owner_can_update_meal(client: TestClient, db: Session):
    """Owner can update their own meal."""
    owner_headers = get_auth_headers(client, db, email="meal_owner3@example.com")
    template = create_template(client, owner_headers, name="Meal Template 3")
    meal = create_meal(client, owner_headers, template["id"])
    meal_id = meal["id"]

    update_data = {"name": "Updated Meal Name"}
    response = client.put(f"/meals/{meal_id}", json=update_data, headers=owner_headers)

    assert response.status_code == 200
    assert response.json()["name"] == "Updated Meal Name"


def test_owner_can_delete_meal(client: TestClient, db: Session):
    """Owner can delete their own meal."""
    owner_headers = get_auth_headers(client, db, email="meal_owner4@example.com")
    template = create_template(client, owner_headers, name="Meal Template 4")
    meal = create_meal(client, owner_headers, template["id"])
    meal_id = meal["id"]

    response = client.delete(f"/meals/{meal_id}", headers=owner_headers)
    assert response.status_code == 204

    get_response = client.get(f"/meals/{meal_id}", headers=owner_headers)
    assert get_response.status_code == 404


# =============================================================================
# Meal Update/Delete - Admin Tests
# =============================================================================


def test_admin_can_update_other_user_meal(client: TestClient, db: Session):
    """Admin with X-Admin-Mode can update another user's meal."""
    owner_headers = get_auth_headers(client, db, email="meal_owner5@example.com")
    template = create_template(client, owner_headers, name="Meal Template 5")
    meal = create_meal(client, owner_headers, template["id"])
    meal_id = meal["id"]

    admin_base_headers = get_auth_headers(
        client, db, email="meal_admin1@example.com", is_admin=True
    )
    admin_headers = {**admin_base_headers, "X-Admin-Mode": "true"}

    update_data = {"name": "Admin Edited Meal"}
    response = client.put(f"/meals/{meal_id}", json=update_data, headers=admin_headers)

    assert response.status_code == 200
    assert response.json()["name"] == "Admin Edited Meal"


def test_admin_can_delete_other_user_meal(client: TestClient, db: Session):
    """Admin with X-Admin-Mode can delete another user's meal."""
    owner_headers = get_auth_headers(client, db, email="meal_owner6@example.com")
    template = create_template(client, owner_headers, name="Meal Template 6")
    meal = create_meal(client, owner_headers, template["id"])
    meal_id = meal["id"]

    admin_base_headers = get_auth_headers(
        client, db, email="meal_admin2@example.com", is_admin=True
    )
    admin_headers = {**admin_base_headers, "X-Admin-Mode": "true"}

    response = client.delete(f"/meals/{meal_id}", headers=admin_headers)
    assert response.status_code == 204

    # Use admin mode to verify it's gone (owner also can't read it since it's deleted)
    admin_get_response = client.get(f"/meals/{meal_id}", headers=admin_headers)
    assert admin_get_response.status_code == 404


# =============================================================================
# Meal Update/Delete - Non-Owner Tests (403)
# =============================================================================


def test_non_owner_cannot_update_meal(client: TestClient, db: Session):
    """Non-owner, non-admin cannot update another user's meal."""
    owner_headers = get_auth_headers(client, db, email="meal_owner7@example.com")
    template = create_template(client, owner_headers, name="Meal Template 7")
    meal = create_meal(client, owner_headers, template["id"])
    meal_id = meal["id"]

    stranger_headers = get_auth_headers(client, db, email="meal_stranger1@example.com")

    update_data = {"name": "Hacked Meal"}
    response = client.put(
        f"/meals/{meal_id}", json=update_data, headers=stranger_headers
    )

    assert response.status_code == 403
    assert "Not authorized" in response.json()["detail"]


def test_non_owner_cannot_delete_meal(client: TestClient, db: Session):
    """Non-owner, non-admin cannot delete another user's meal."""
    owner_headers = get_auth_headers(client, db, email="meal_owner8@example.com")
    template = create_template(client, owner_headers, name="Meal Template 8")
    meal = create_meal(client, owner_headers, template["id"])
    meal_id = meal["id"]

    stranger_headers = get_auth_headers(client, db, email="meal_stranger2@example.com")

    response = client.delete(f"/meals/{meal_id}", headers=stranger_headers)

    assert response.status_code == 403
    assert "Not authorized" in response.json()["detail"]
