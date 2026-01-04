
from fastapi.testclient import TestClient

from app import crud, schemas

def get_auth_headers(client: TestClient, db, email="user@example.com", password="password"):
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
            "protein": "Dairy"
        },
        "times": {
            "prep_time_minutes": 10,
            "cook_time_minutes": 15
        },
        "nutrition": {
            "calories": 300
        },
        "components": [
            {
                "name": "Main",
                "ingredients": [
                    {"ingredient_name": "Flour", "quantity": 2, "unit": "cups"},
                    {"ingredient_name": "Milk", "quantity": 1.5, "unit": "cups"}
                ]
            }
        ],
        "instructions": [
            {"step_number": 1, "text": "Mix ingredients"},
            {"step_number": 2, "text": "Cook on pan"}
        ]
    }
    response = client.post("/recipes/", json=recipe_data, headers=headers)
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["core"]["name"] == "Pancakes"
    assert len(data["components"]) == 1
    assert len(data["components"][0]["ingredients"]) == 2
    assert len(data["instructions"]) == 2

def test_read_recipes(client: TestClient, db):
    # Create a recipe first
    headers = get_auth_headers(client, db)

    recipe_data = {
        "core": {"name": "Toast", "yield_amount": 1},
        "times": {"prep_time_minutes": 1},
        "nutrition": {},
        "components": [],
        "instructions": []
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
        "instructions": []
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
        "instructions": []
    }
    create_res = client.post("/recipes/", json=recipe_data, headers=headers)
    recipe_id = create_res.json()["core"]["id"]

    update_data = recipe_data.copy()
    update_data["core"]["name"] = "New Name"
    # Need to send all required fields. Pydantic schema validation!
    
    response = client.put(f"/recipes/{recipe_id}", json=update_data, headers=headers)
    assert response.status_code == 200
    assert response.json()["core"]["name"] == "New Name"

def test_delete_recipe(client: TestClient, db):
    headers = get_auth_headers(client, db)

    recipe_data = {
        "core": {"name": "To Delete"},
        "times": {},
        "nutrition": {},
        "components": [],
        "instructions": []
    }
    create_res = client.post("/recipes/", json=recipe_data, headers=headers)
    recipe_id = create_res.json()["core"]["id"]

    response = client.delete(f"/recipes/{recipe_id}", headers=headers)
    assert response.status_code == 200
    
    # Verify it's gone
    get_res = client.get(f"/recipes/{recipe_id}", headers=headers)
    assert get_res.status_code == 404
