
from fastapi.testclient import TestClient
from app import crud, schemas, models
from uuid import uuid4

def get_auth_headers(client: TestClient, db, email="user_loops@example.com", password="password"):
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

def create_recipe(client, headers, name, parent_id=None):
    data = {
        "core": {"name": name},
        "times": {},
        "nutrition": {},
        "components": [],
        "instructions": [],
        "parent_recipe_id": parent_id
    }
    res = client.post("/recipes/", json=data, headers=headers)
    assert res.status_code == 200
    return res.json()["core"]["id"]

def update_recipe_parent(client, headers, recipe_id, parent_id):
    # Need to fetch existing first to keep other fields? 
    # Or just send minimal update since we can replace with defaults?
    # Our update logic replaces sub-fields. Core fields are required in Schema usually?
    # No, RecipeCreate used for update has defaults in Pydantic? 
    # RecipeCreateCore has required fields "name".
    # Check schema again. RecipeCoreCreate(RecipeCoreBase). Base has name: str.
    # So we need to provide name.
    
    data = {
        "core": {"name": "Updated Name"},
        "times": {},
        "nutrition": {},
        "components": [],
        "instructions": [],
        "parent_recipe_id": parent_id
    }
    return client.put(f"/recipes/{recipe_id}", json=data, headers=headers)

def test_circular_dependency(client: TestClient, db):
    headers = get_auth_headers(client, db)

    # 1. Create A
    id_a = create_recipe(client, headers, "Recipe A")
    
    # 2. Create B with parent A
    id_b = create_recipe(client, headers, "Recipe B", parent_id=id_a)
    
    # Verify B has parent A
    res = client.get(f"/recipes/{id_b}", headers=headers)
    assert res.json()["parent_recipe_id"] == id_a
    
    # 3. Try to update A to have parent B (Cycle: A->B->A)
    res = update_recipe_parent(client, headers, id_a, id_b)
    assert res.status_code == 400
    assert "Cycle detected" in res.json()["detail"]
    
    # 4. Try to update A to have parent A (Self loop)
    res = update_recipe_parent(client, headers, id_a, id_a)
    assert res.status_code == 400
    assert "own parent" in res.json()["detail"]
    
    # 5. Transitive: Create C -> B. Then A -> C.
    # Structure: A <- B <- C.
    # If we set A.parent = C, then C -> B -> A -> C.
    id_c = create_recipe(client, headers, "Recipe C", parent_id=id_b)
    
    res = update_recipe_parent(client, headers, id_a, id_c)
    assert res.status_code == 400
    assert "Cycle detected" in res.json()["detail"]

