
from fastapi.testclient import TestClient

def get_auth_headers(client: TestClient, email="user@example.com", password="password"):
    # Register
    client.post(
        "/auth/users/",
        json={"email": email, "password": password},
    )
    # Login
    response = client.post(
        "/auth/token",
        data={"username": email, "password": password},
    )
    token = response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}

def test_create_recipe(client: TestClient, db):
    headers = get_auth_headers(client)
    recipe_data = {
        "name": "Pancakes",
        "prep_time_minutes": 10,
        "cook_time_minutes": 15,
        "servings": 4,
        "ingredients": [
            {"ingredient_name": "Flour", "quantity": 2, "unit": "cups"},
            {"ingredient_name": "Milk", "quantity": 1.5, "unit": "cups"}
        ],
        "instructions": [
            {"step_number": 1, "description": "Mix ingredients"},
            {"step_number": 2, "description": "Cook on pan"}
        ]
    }
    response = client.post("/recipes/", json=recipe_data, headers=headers)
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["name"] == "Pancakes"
    assert len(data["ingredients"]) == 2
    assert len(data["instructions"]) == 2

def test_read_recipes(client: TestClient, db):
    # Create a recipe first
    headers = get_auth_headers(client)
    recipe_data = {
        "name": "Toast",
        "prep_time_minutes": 1,
        "cook_time_minutes": 2,
        "servings": 1,
        "ingredients": [],
        "instructions": []
    }
    client.post("/recipes/", json=recipe_data, headers=headers)

    # Read
    response = client.get("/recipes/", headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert len(data) >= 1
    assert data[0]["name"] == "Toast"

def test_read_recipe_by_id(client: TestClient, db):
    headers = get_auth_headers(client)
    recipe_data = {
        "name": "Soup",
        "prep_time_minutes": 10,
        "cook_time_minutes": 20,
        "servings": 4,
        "ingredients": [],
        "instructions": []
    }
    create_res = client.post("/recipes/", json=recipe_data, headers=headers)
    recipe_id = create_res.json()["id"]

    response = client.get(f"/recipes/{recipe_id}", headers=headers)
    assert response.status_code == 200
    assert response.json()["name"] == "Soup"

def test_update_recipe(client: TestClient, db):
    headers = get_auth_headers(client)
    recipe_data = {
        "name": "Old Name",
        "prep_time_minutes": 5,
        "cook_time_minutes": 5,
        "servings": 1,
        "ingredients": [],
        "instructions": []
    }
    create_res = client.post("/recipes/", json=recipe_data, headers=headers)
    recipe_id = create_res.json()["id"]

    update_data = recipe_data.copy()
    update_data["name"] = "New Name"
    # Need to send ingredients/instructions even if empty for full update as per current schema/crud
    # If partial update is not supported by Pydantic schema, we send full.
    # checking schema, IngredientCreate etc are required in RecipeCreate.
    
    response = client.put(f"/recipes/{recipe_id}", json=update_data, headers=headers)
    assert response.status_code == 200
    assert response.json()["name"] == "New Name"

def test_delete_recipe(client: TestClient, db):
    headers = get_auth_headers(client)
    recipe_data = {
        "name": "To Delete",
        "prep_time_minutes": 5,
        "cook_time_minutes": 5,
        "servings": 1,
        "ingredients": [],
        "instructions": []
    }
    create_res = client.post("/recipes/", json=recipe_data, headers=headers)
    recipe_id = create_res.json()["id"]

    response = client.delete(f"/recipes/{recipe_id}", headers=headers)
    assert response.status_code == 200
    
    # Verify it's gone
    get_res = client.get(f"/recipes/{recipe_id}", headers=headers)
    assert get_res.status_code == 404
