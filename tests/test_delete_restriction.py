from fastapi.testclient import TestClient
from app import crud, schemas
from uuid import uuid4, UUID


def get_auth_headers(
    client: TestClient, db, email_prefix="user_del", password="password"
):
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


def test_delete_recipe_with_variants_fails(client: TestClient, db):
    headers = get_auth_headers(client, db)

    # 1. Create Parent Recipe
    parent_data = {
        "core": {"name": "Parent Recipe"},
        "times": {},
        "nutrition": {},
        "components": [],
        "instructions": [],
    }
    parent_res = client.post("/recipes/", json=parent_data, headers=headers)
    assert parent_res.status_code == 201
    parent_id = parent_res.json()["core"]["id"]

    # 2. Create Variant (Child) Recipe
    child_data = {
        "core": {"name": "Child Recipe"},
        "times": {},
        "nutrition": {},
        "components": [],
        "instructions": [],
        "parent_recipe_id": parent_id,
    }
    # Note: Using json=child_data assuming the schema supports parent_recipe_id on create.
    # If not supported, we'd need to link it manually, but previous analysis suggests it works or is expected.
    child_res = client.post("/recipes/", json=child_data, headers=headers)
    assert child_res.status_code == 201
    child_res.json()["core"]["id"]

    # Verify relationship exists
    db_parent = crud.get_recipe(db, UUID(parent_id))
    assert len(db_parent.variants) == 1

    # 3. Attempt to delete Parent
    delete_res = client.delete(f"/recipes/{parent_id}", headers=headers)

    # Expected behavior: 400 Bad Request
    # Current behavior (likely): 200 OK

    assert delete_res.status_code == 400, (
        f"Expected 400, got {delete_res.status_code}. Response: {delete_res.text}"
    )
    assert "variants" in delete_res.json()["detail"].lower()

    # Verify Parent still exists
    chk_res = client.get(f"/recipes/{parent_id}", headers=headers)
    assert chk_res.status_code == 200
