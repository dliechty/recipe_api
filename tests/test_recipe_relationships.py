from fastapi.testclient import TestClient
from app import crud, schemas, models
from uuid import uuid4, UUID
import pytest

# --- Helpers ---

def get_auth_headers(client: TestClient, db, email_prefix="user_rel", password="password"):
    email = f"{email_prefix}_{uuid4()}@example.com"
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
    # parent_recipe_id in create might not be supported directly in all schema versions, 
    # but let's assume it is or we patch it if needed. 
    # Based on test_circular_dependency it seems supported in the payload or at least handled.
    res = client.post("/recipes/", json=data, headers=headers)
    assert res.status_code == 201
    return res.json()["core"]["id"]

def update_recipe_parent(client, headers, recipe_id, parent_id):
    data = {
        "core": {"name": "Updated Name"},
        "times": {},
        "nutrition": {},
        "components": [],
        "instructions": [],
        "parent_recipe_id": parent_id
    }
    return client.put(f"/recipes/{recipe_id}", json=data, headers=headers)

# --- Tests ---

def test_recipe_children_exposed(client: TestClient, db):
    headers = get_auth_headers(client, db, "user_children")

    # 1. Create Parent Recipe
    parent_data = {
        "core": {"name": "Parent Recipe", "yield_amount": 4},
        "times": {"prep_time_minutes": 10},
        "nutrition": {},
        "components": [],
        "instructions": []
    }
    parent_res = client.post("/recipes/", json=parent_data, headers=headers)
    assert parent_res.status_code == 201
    parent_id = parent_res.json()["core"]["id"]

    # 2. Create Child Recipe
    child_data = {
        "core": {"name": "Child Recipe", "yield_amount": 2},
        "times": {"prep_time_minutes": 5},
        "nutrition": {},
        "components": [],
        "instructions": []
    }
    child_res = client.post("/recipes/", json=child_data, headers=headers)
    assert child_res.status_code == 201
    child_id = child_res.json()["core"]["id"]

    # 3. Manually link child to parent (if API create doesn't support it yet, mimicking test_recipe_relationships original behavior)
    # The original test used direct DB manipulation, which is rigorous for verifying the read-side.
    db_child = crud.get_recipe(db, UUID(child_id))
    db_child.parent_recipe_id = UUID(parent_id)
    db.commit()
    db.refresh(db_child)

    # 4. Fetch Parent and verify children_ids
    response = client.get(f"/recipes/{parent_id}", headers=headers)
    assert response.status_code == 200
    data = response.json()
    
    assert "variant_recipe_ids" in data
    assert child_id in data["variant_recipe_ids"]
    assert len(data["variant_recipe_ids"]) == 1

    # 5. Fetch Child and verify parent_recipe_id is top level
    child_resp = client.get(f"/recipes/{child_id}", headers=headers)
    assert child_resp.status_code == 200
    c_data = child_resp.json()
    assert "parent_recipe_id" in c_data
    assert c_data["parent_recipe_id"] == parent_id

def test_circular_dependency(client: TestClient, db):
    headers = get_auth_headers(client, db, "user_loops")

    # 1. Create A
    id_a = create_recipe(client, headers, "Recipe A")
    
    # 2. Create B with parent A
    # If create_recipe passes parent_id in JSON and API respects it:
    id_b = create_recipe(client, headers, "Recipe B", parent_id=id_a)
    
    # Verify B has parent A (via API support check)
    # If create logic in API doesn't handle parent_id, this might fail unless we patch it like above. 
    # `test_circular_dependency.py` seemed to assume it works.
    res = client.get(f"/recipes/{id_b}", headers=headers)
    
    # If API doesn't support setting parent on create, we might need to update it or set it manually.
    # But `test_circular_dependency` called `create_recipe(..., parent_id=id_a)`.
    # Let's verify if `create_recipe` in that file did anything special?
    # It just passed it in json. So we assume API supports it or the test was relying on it.
    
    if res.json().get("parent_recipe_id") != id_a:
        # Fallback if create endpoint ignores it (though validation usually is on update mainly for cycles)
        # But we need the structure A <- B to test the cycle.
        db_b = crud.get_recipe(db, UUID(id_b))
        db_b.parent_recipe_id = UUID(id_a)
        db.commit()
    
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
    
    # Ensure structure is correct
    db_c = crud.get_recipe(db, UUID(id_c))
    if str(db_c.parent_recipe_id) != id_b:
         db_c.parent_recipe_id = UUID(id_b)
         db.commit()

    res = update_recipe_parent(client, headers, id_a, id_c)
    assert res.status_code == 400
    assert "Cycle detected" in res.json()["detail"]
