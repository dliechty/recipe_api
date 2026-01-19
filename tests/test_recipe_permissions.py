
from fastapi.testclient import TestClient
from app import crud, schemas

def get_auth_headers(client: TestClient, db, email, password="password", is_admin=False):
    # Directly create user in DB
    try:
        user_in = schemas.UserCreate(email=email, password=password)
        user = crud.create_user(db, user_in)
        if is_admin:
            user.is_admin = True
            db.add(user)
            db.commit()
    except Exception:
        # If user exists, update admin status just in case
        user = crud.get_user_by_email(db, email=email)
        if user and is_admin != user.is_admin:
            user.is_admin = is_admin
            db.add(user)
            db.commit()

    # Login
    response = client.post(
        "/auth/token",
        data={"username": email, "password": password},
    )
    token = response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}

def create_dummy_recipe(client, headers, name="Test Recipe"):
    recipe_data = {
        "core": {"name": name},
        "times": {},
        "nutrition": {},
        "components": [],
        "instructions": []
    }
    response = client.post("/recipes/", json=recipe_data, headers=headers)
    assert response.status_code == 201
    return response.json()

def test_admin_can_update_other_user_recipe(client, db):
    # 1. Create User A (Owner)
    owner_headers = get_auth_headers(client, db, email="owner@example.com")
    recipe = create_dummy_recipe(client, owner_headers)
    recipe_id = recipe["core"]["id"]

    # 2. Create Admin User
    admin_headers = get_auth_headers(client, db, email="admin@example.com", is_admin=True)

    # 3. Admin tries to update
    update_data = {
        "core": {"name": "Admin Edited"},
        "times": {},
        "nutrition": {},
        "components": [],
        "instructions": []
    }
    response = client.put(f"/recipes/{recipe_id}", json=update_data, headers=admin_headers)
    
    # 4. Assert Success
    assert response.status_code == 200
    assert response.json()["core"]["name"] == "Admin Edited"

def test_admin_can_delete_other_user_recipe(client, db):
    # 1. Create User A (Owner)
    owner_headers = get_auth_headers(client, db, email="owner2@example.com")
    recipe = create_dummy_recipe(client, owner_headers)
    recipe_id = recipe["core"]["id"]

    # 2. Create Admin User
    admin_headers = get_auth_headers(client, db, email="admin2@example.com", is_admin=True)

    # 3. Admin tries to delete
    response = client.delete(f"/recipes/{recipe_id}", headers=admin_headers)
    
    # 4. Assert Success
    assert response.status_code == 200
    
    # Verify deletion
    get_res = client.get(f"/recipes/{recipe_id}", headers=owner_headers)
    assert get_res.status_code == 404

def test_non_owner_cannot_update(client, db):
    # 1. Create User A (Owner)
    owner_headers = get_auth_headers(client, db, email="owner3@example.com")
    recipe = create_dummy_recipe(client, owner_headers)
    recipe_id = recipe["core"]["id"]

    # 2. Create User B (Stranger)
    stranger_headers = get_auth_headers(client, db, email="stranger@example.com")

    # 3. Stranger tries to update
    update_data = {
        "core": {"name": "Hacked"},
        "times": {},
        "nutrition": {},
        "components": [],
        "instructions": []
    }
    response = client.put(f"/recipes/{recipe_id}", json=update_data, headers=stranger_headers)
    
    # 4. Assert Failure
    assert response.status_code == 403

def test_non_owner_cannot_delete(client, db):
    # 1. Create User A (Owner)
    owner_headers = get_auth_headers(client, db, email="owner4@example.com")
    recipe = create_dummy_recipe(client, owner_headers)
    recipe_id = recipe["core"]["id"]

    # 2. Create User B (Stranger)
    stranger_headers = get_auth_headers(client, db, email="stranger2@example.com")

    # 3. Stranger tries to delete
    response = client.delete(f"/recipes/{recipe_id}", headers=stranger_headers)
    
    # 4. Assert Failure
    assert response.status_code == 403
