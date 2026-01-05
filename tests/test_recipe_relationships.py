
from fastapi.testclient import TestClient
from app import crud, schemas, models
from uuid import uuid4, UUID

def get_auth_headers(client: TestClient, db, email="user_rel@example.com", password="password"):
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

def test_recipe_children_exposed(client: TestClient, db):
    headers = get_auth_headers(client, db)

    # 1. Create Parent Recipe
    parent_data = {
        "core": {"name": "Parent Recipe", "yield_amount": 4},
        "times": {"prep_time_minutes": 10},
        "nutrition": {},
        "components": [],
        "instructions": []
    }
    parent_res = client.post("/recipes/", json=parent_data, headers=headers)
    assert parent_res.status_code == 200
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
    assert child_res.status_code == 200
    child_id = child_res.json()["core"]["id"]

    # 3. Manually link child to parent (since API might not expose parent_recipe_id setting on create yet)
    # We can use the DB directly
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


