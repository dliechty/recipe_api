
from fastapi.testclient import TestClient
from app import crud, schemas, models, filters
import pytest

def get_auth_headers(client: TestClient, db, email="sorting_bug@example.com", password="password"):
    try:
        user_in = schemas.UserCreate(email=email, password=password)
        crud.create_user(db, user_in)
    except Exception:
        pass

    response = client.post(
        "/auth/token",
        data={"username": email, "password": password},
    )
    token = response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}

def create_recipe_with_fields(client, headers, name, category, cuisine):
    data = {
        "core": {
            "name": name, 
            "category": category,
            "cuisine": cuisine
        },
        "times": {},
        "nutrition": {},
        "components": [],
        "instructions": []
    }
    res = client.post("/recipes/", json=data, headers=headers)
    assert res.status_code == 200
    return res.json()

def test_sorting_failure(client: TestClient, db):
    headers = get_auth_headers(client, db)
    
    # Create 3 recipes with distinct category/cuisine
    # R1: Cat=C, Cuis=A
    # R2: Cat=A, Cuis=C
    # R3: Cat=B, Cuis=B
    
    create_recipe_with_fields(client, headers, "R1", "Dessert", "American")
    create_recipe_with_fields(client, headers, "R2", "Appetizer", "Chinese")
    create_recipe_with_fields(client, headers, "R3", "Beverage", "British")
    
    # Sort by Category (Asc) -> R2 (App), R3 (Bev), R1 (Des)
    res = client.get("/recipes/?sort=category", headers=headers)
    data = res.json()
    names = [r["core"]["name"] for r in data]
    # If sorting fails (defaults to ID or Name?), order might be R1, R2, R3 (insertion) or R2, R3, R1 (if sorted correctly)
    
    # We expect R2, R3, R1
    if names != ["R2", "R3", "R1"]:
        pytest.fail(f"Sorting by category failed. Expected ['R2', 'R3', 'R1'], got {names}")

    # Sort by Cuisine (Asc) -> R1 (Amer), R3 (Brit), R2 (Chin)
    res = client.get("/recipes/?sort=cuisine", headers=headers)
    data = res.json()
    names = [r["core"]["name"] for r in data]
    
    if names != ["R1", "R3", "R2"]:
        pytest.fail(f"Sorting by cuisine failed. Expected ['R1', 'R3', 'R2'], got {names}")
