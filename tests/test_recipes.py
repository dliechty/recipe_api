from fastapi.testclient import TestClient

from app import crud, schemas


def get_auth_headers(
    client: TestClient, db, email="user@example.com", password="password"
):
    # Directly create user in DB
    try:
        user_in = schemas.UserCreate(email=email, password=password)
        crud.create_user(db, user_in)
    except Exception:
        # Ignore duplicate email errors if user already exists
        pass

    # Login
    response = client.post(
        "/auth/token",
        data={"username": email, "password": password},
    )
    token = response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def test_create_recipe(client: TestClient, db):
    headers = get_auth_headers(client, db)

    recipe_data = {
        "core": {
            "name": "Pancakes",
            "description": "Fluffy breakfast",
            "difficulty": "Easy",
            "yield_amount": 4,
            "protein": "Dairy",
        },
        "times": {"prep_time_minutes": 10, "cook_time_minutes": 15},
        "nutrition": {"calories": 300},
        "components": [
            {
                "name": "Main",
                "ingredients": [
                    {"ingredient_name": "Flour", "quantity": 2, "unit": "cups"},
                    {"ingredient_name": "Milk", "quantity": 1.5, "unit": "cups"},
                ],
            }
        ],
        "instructions": [
            {"step_number": 1, "text": "Mix ingredients"},
            {"step_number": 2, "text": "Cook on pan"},
        ],
        "suitable_for_diet": ["vegetarian", "low-calorie"],
    }
    response = client.post("/recipes/", json=recipe_data, headers=headers)
    assert response.status_code == 201, response.text
    data = response.json()
    assert data["core"]["name"] == "Pancakes"
    assert len(data["components"]) == 1
    assert len(data["components"][0]["ingredients"]) == 2
    assert len(data["instructions"]) == 2
    assert "vegetarian" in data["suitable_for_diet"]
    assert "low-calorie" in data["suitable_for_diet"]


def test_read_recipes(client: TestClient, db):
    # Create a recipe first
    headers = get_auth_headers(client, db)

    recipe_data = {
        "core": {"name": "Toast", "yield_amount": 1},
        "times": {"prep_time_minutes": 1},
        "nutrition": {},
        "components": [],
        "instructions": [],
    }
    client.post("/recipes/", json=recipe_data, headers=headers)

    # Read
    response = client.get("/recipes/", headers=headers)
    assert response.status_code == 200
    assert response.headers["X-Total-Count"]
    assert int(response.headers["X-Total-Count"]) >= 1
    data = response.json()
    assert len(data) >= 1
    assert data[0]["core"]["name"] == "Toast"


def test_read_recipe_by_id(client: TestClient, db):
    headers = get_auth_headers(client, db)

    recipe_data = {
        "core": {"name": "Soup", "yield_amount": 4},
        "times": {"prep_time_minutes": 10},
        "nutrition": {},
        "components": [],
        "instructions": [],
    }
    create_res = client.post("/recipes/", json=recipe_data, headers=headers)
    recipe_id = create_res.json()["core"]["id"]

    response = client.get(f"/recipes/{recipe_id}", headers=headers)
    assert response.status_code == 200
    assert response.json()["core"]["name"] == "Soup"


def test_update_recipe(client: TestClient, db):
    headers = get_auth_headers(client, db)

    recipe_data = {
        "core": {"name": "Old Name", "yield_amount": 1},
        "times": {"prep_time_minutes": 5},
        "nutrition": {},
        "components": [],
        "instructions": [],
    }
    create_res = client.post("/recipes/", json=recipe_data, headers=headers)
    recipe_id = create_res.json()["core"]["id"]

    update_data = recipe_data.copy()
    update_data["core"]["name"] = "New Name"
    update_data["suitable_for_diet"] = ["vegan"]
    # Need to send all required fields. Pydantic schema validation!

    response = client.put(f"/recipes/{recipe_id}", json=update_data, headers=headers)
    assert response.status_code == 200
    assert response.json()["core"]["name"] == "New Name"
    assert response.json()["suitable_for_diet"] == ["vegan"]


def test_delete_recipe(client: TestClient, db):
    headers = get_auth_headers(client, db)

    recipe_data = {
        "core": {"name": "To Delete"},
        "times": {},
        "nutrition": {},
        "components": [],
        "instructions": [],
    }
    create_res = client.post("/recipes/", json=recipe_data, headers=headers)
    recipe_id = create_res.json()["core"]["id"]

    response = client.delete(f"/recipes/{recipe_id}", headers=headers)
    assert response.status_code == 200

    # Verify it's gone
    get_res = client.get(f"/recipes/{recipe_id}", headers=headers)
    assert get_res.status_code == 404


# --- Ingredient Scaling Tests ---


def test_read_recipe_with_scale_factor(client: TestClient, db):
    """Test that scale parameter correctly multiplies ingredient quantities."""
    headers = get_auth_headers(client, db)

    recipe_data = {
        "core": {"name": "Scaled Recipe", "yield_amount": 4},
        "times": {"prep_time_minutes": 10},
        "nutrition": {"calories": 200},
        "components": [
            {
                "name": "Main",
                "ingredients": [
                    {"ingredient_name": "Flour", "quantity": 2.0, "unit": "cups"},
                    {"ingredient_name": "Sugar", "quantity": 0.5, "unit": "cups"},
                ],
            }
        ],
        "instructions": [{"step_number": 1, "text": "Mix"}],
    }
    create_res = client.post("/recipes/", json=recipe_data, headers=headers)
    recipe_id = create_res.json()["core"]["id"]

    # Test scale=2 (double)
    response = client.get(f"/recipes/{recipe_id}?scale=2", headers=headers)
    assert response.status_code == 200
    data = response.json()

    # Verify quantities are doubled
    ingredients = data["components"][0]["ingredients"]
    assert ingredients[0]["quantity"] == 4.0  # 2 * 2
    assert ingredients[1]["quantity"] == 1.0  # 0.5 * 2

    # Verify yield_amount is also scaled
    assert data["core"]["yield_amount"] == 8  # 4 * 2


def test_read_recipe_with_scale_half(client: TestClient, db):
    """Test that scale=0.5 halves ingredient quantities."""
    headers = get_auth_headers(client, db)

    recipe_data = {
        "core": {"name": "Half Recipe", "yield_amount": 4},
        "times": {},
        "nutrition": {},
        "components": [
            {
                "name": "Main",
                "ingredients": [
                    {"ingredient_name": "Butter", "quantity": 1.0, "unit": "cup"},
                ],
            }
        ],
        "instructions": [],
    }
    create_res = client.post("/recipes/", json=recipe_data, headers=headers)
    recipe_id = create_res.json()["core"]["id"]

    response = client.get(f"/recipes/{recipe_id}?scale=0.5", headers=headers)
    assert response.status_code == 200
    data = response.json()

    assert data["components"][0]["ingredients"][0]["quantity"] == 0.5
    assert data["core"]["yield_amount"] == 2


def test_read_recipe_scale_one_unchanged(client: TestClient, db):
    """Test that scale=1 returns quantities unchanged."""
    headers = get_auth_headers(client, db)

    recipe_data = {
        "core": {"name": "No Change Recipe"},
        "times": {},
        "nutrition": {},
        "components": [
            {
                "name": "Main",
                "ingredients": [
                    {"ingredient_name": "Salt", "quantity": 1.5, "unit": "tsp"},
                ],
            }
        ],
        "instructions": [],
    }
    create_res = client.post("/recipes/", json=recipe_data, headers=headers)
    recipe_id = create_res.json()["core"]["id"]

    response = client.get(f"/recipes/{recipe_id}?scale=1", headers=headers)
    assert response.status_code == 200
    data = response.json()

    assert data["components"][0]["ingredients"][0]["quantity"] == 1.5


def test_read_recipe_no_scale_unchanged(client: TestClient, db):
    """Test that omitting scale parameter returns original quantities."""
    headers = get_auth_headers(client, db)

    recipe_data = {
        "core": {"name": "Default Recipe"},
        "times": {},
        "nutrition": {},
        "components": [
            {
                "name": "Main",
                "ingredients": [
                    {"ingredient_name": "Pepper", "quantity": 0.25, "unit": "tsp"},
                ],
            }
        ],
        "instructions": [],
    }
    create_res = client.post("/recipes/", json=recipe_data, headers=headers)
    recipe_id = create_res.json()["core"]["id"]

    response = client.get(f"/recipes/{recipe_id}", headers=headers)
    assert response.status_code == 200
    data = response.json()

    assert data["components"][0]["ingredients"][0]["quantity"] == 0.25


def test_read_recipe_scale_zero_rejected(client: TestClient, db):
    """Test that scale=0 is rejected with 422."""
    headers = get_auth_headers(client, db)

    recipe_data = {
        "core": {"name": "Zero Scale Recipe"},
        "times": {},
        "nutrition": {},
        "components": [],
        "instructions": [],
    }
    create_res = client.post("/recipes/", json=recipe_data, headers=headers)
    recipe_id = create_res.json()["core"]["id"]

    response = client.get(f"/recipes/{recipe_id}?scale=0", headers=headers)
    assert response.status_code == 422


def test_read_recipe_scale_negative_rejected(client: TestClient, db):
    """Test that negative scale values are rejected with 422."""
    headers = get_auth_headers(client, db)

    recipe_data = {
        "core": {"name": "Negative Scale Recipe"},
        "times": {},
        "nutrition": {},
        "components": [],
        "instructions": [],
    }
    create_res = client.post("/recipes/", json=recipe_data, headers=headers)
    recipe_id = create_res.json()["core"]["id"]

    response = client.get(f"/recipes/{recipe_id}?scale=-1", headers=headers)
    assert response.status_code == 422


def test_read_recipe_scale_large_value(client: TestClient, db):
    """Test that large scale values work correctly."""
    headers = get_auth_headers(client, db)

    recipe_data = {
        "core": {"name": "Large Scale Recipe"},
        "times": {},
        "nutrition": {},
        "components": [
            {
                "name": "Main",
                "ingredients": [
                    {"ingredient_name": "Water", "quantity": 1.0, "unit": "cup"},
                ],
            }
        ],
        "instructions": [],
    }
    create_res = client.post("/recipes/", json=recipe_data, headers=headers)
    recipe_id = create_res.json()["core"]["id"]

    response = client.get(f"/recipes/{recipe_id}?scale=100", headers=headers)
    assert response.status_code == 200
    data = response.json()

    assert data["components"][0]["ingredients"][0]["quantity"] == 100.0


def test_read_recipe_scale_multiple_components(client: TestClient, db):
    """Test scaling works across multiple components."""
    headers = get_auth_headers(client, db)

    recipe_data = {
        "core": {"name": "Multi-Component Recipe"},
        "times": {},
        "nutrition": {},
        "components": [
            {
                "name": "Dough",
                "ingredients": [
                    {"ingredient_name": "Flour", "quantity": 3.0, "unit": "cups"},
                ],
            },
            {
                "name": "Filling",
                "ingredients": [
                    {"ingredient_name": "Cheese", "quantity": 2.0, "unit": "cups"},
                    {"ingredient_name": "Spinach", "quantity": 1.0, "unit": "cup"},
                ],
            },
        ],
        "instructions": [],
    }
    create_res = client.post("/recipes/", json=recipe_data, headers=headers)
    recipe_id = create_res.json()["core"]["id"]

    response = client.get(f"/recipes/{recipe_id}?scale=3", headers=headers)
    assert response.status_code == 200
    data = response.json()

    assert data["components"][0]["ingredients"][0]["quantity"] == 9.0
    assert data["components"][1]["ingredients"][0]["quantity"] == 6.0
    assert data["components"][1]["ingredients"][1]["quantity"] == 3.0


def test_read_recipe_scale_preserves_other_fields(client: TestClient, db):
    """Test that scaling preserves non-quantity fields."""
    headers = get_auth_headers(client, db)

    recipe_data = {
        "core": {"name": "Preserved Fields Recipe", "difficulty": "Medium"},
        "times": {"prep_time_minutes": 30, "cook_time_minutes": 45},
        "nutrition": {"calories": 500},
        "components": [
            {
                "name": "Main",
                "ingredients": [
                    {
                        "ingredient_name": "Onion",
                        "quantity": 1.0,
                        "unit": "whole",
                        "notes": "diced",
                    },
                ],
            }
        ],
        "instructions": [{"step_number": 1, "text": "Dice the onion"}],
        "suitable_for_diet": ["vegan"],
    }
    create_res = client.post("/recipes/", json=recipe_data, headers=headers)
    recipe_id = create_res.json()["core"]["id"]

    response = client.get(f"/recipes/{recipe_id}?scale=2", headers=headers)
    assert response.status_code == 200
    data = response.json()

    # Quantity is scaled
    assert data["components"][0]["ingredients"][0]["quantity"] == 2.0

    # Other fields are preserved
    assert data["components"][0]["ingredients"][0]["unit"] == "whole"
    assert data["components"][0]["ingredients"][0]["notes"] == "diced"
    assert data["components"][0]["ingredients"][0]["item"] == "Onion"
    assert data["core"]["difficulty"] == "Medium"
    assert data["times"]["prep_time_minutes"] == 30  # Not scaled
    assert data["nutrition"]["calories"] == 500  # Not scaled
    assert data["instructions"][0]["text"] == "Dice the onion"
    assert "vegan" in data["suitable_for_diet"]
