from fastapi.testclient import TestClient
from app import crud, schemas


def get_auth_headers(
    client: TestClient, db, email, password="password", is_admin=False
):
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
        "instructions": [],
    }
    response = client.post("/recipes/", json=recipe_data, headers=headers)
    assert response.status_code == 201
    return response.json()


def test_create_and_read_comment(client, db):
    # 1. Create User and Recipe
    user_headers = get_auth_headers(client, db, email="commenter@example.com")
    recipe = create_dummy_recipe(client, user_headers)
    recipe_id = recipe["core"]["id"]

    # 2. Add Comment
    comment_data = {"text": "This is a tasty recipe!"}
    response = client.post(
        f"/recipes/{recipe_id}/comments", json=comment_data, headers=user_headers
    )
    assert response.status_code == 201
    created_comment = response.json()
    assert created_comment["text"] == "This is a tasty recipe!"
    assert created_comment["user"]["email"] == "commenter@example.com"

    # 3. Read Comments
    response = client.get(f"/recipes/{recipe_id}/comments", headers=user_headers)
    assert response.status_code == 200
    comments = response.json()
    assert len(comments) == 1
    assert comments[0]["text"] == "This is a tasty recipe!"


def test_update_comment_permissions(client, db):
    # 1. Create Owner and Recipe
    owner_headers = get_auth_headers(client, db, email="owner_comment@example.com")
    recipe = create_dummy_recipe(client, owner_headers)
    recipe_id = recipe["core"]["id"]

    # 2. Create Commenter and Comment
    commenter_headers = get_auth_headers(client, db, email="commenter2@example.com")
    comment_data = {"text": "Original comment"}
    res = client.post(
        f"/recipes/{recipe_id}/comments", json=comment_data, headers=commenter_headers
    )
    comment_id = res.json()["id"]

    # 3. Commenter updates own comment -> OK
    update_data = {"text": "Updated by owner"}
    res = client.put(
        f"/recipes/{recipe_id}/comments/{comment_id}",
        json=update_data,
        headers=commenter_headers,
    )
    assert res.status_code == 200
    assert res.json()["text"] == "Updated by owner"

    # 4. Another user tries to update -> Forbidden
    stranger_headers = get_auth_headers(client, db, email="stranger3@example.com")
    res = client.put(
        f"/recipes/{recipe_id}/comments/{comment_id}",
        json={"text": "Hacked"},
        headers=stranger_headers,
    )
    assert res.status_code == 403

    # 5. Recipe Owner tries to update -> Forbidden (unless admin)
    res = client.put(
        f"/recipes/{recipe_id}/comments/{comment_id}",
        json={"text": "Owner Override"},
        headers=owner_headers,
    )
    assert res.status_code == 403

    # 6. Admin with X-Admin-Mode updates -> OK
    admin_base_headers = get_auth_headers(
        client, db, email="admin_comment@example.com", is_admin=True
    )
    admin_headers = {**admin_base_headers, "X-Admin-Mode": "true"}
    res = client.put(
        f"/recipes/{recipe_id}/comments/{comment_id}",
        json={"text": "Admin Override"},
        headers=admin_headers,
    )
    assert res.status_code == 200
    assert res.json()["text"] == "Admin Override"


def test_delete_comment_permissions(client, db):
    # 1. Setup
    owner_headers = get_auth_headers(client, db, email="owner_del@example.com")
    recipe = create_dummy_recipe(client, owner_headers)
    recipe_id = recipe["core"]["id"]

    commenter_headers = get_auth_headers(client, db, email="commenter_del@example.com")
    res = client.post(
        f"/recipes/{recipe_id}/comments",
        json={"text": "To be deleted"},
        headers=commenter_headers,
    )
    comment_id = res.json()["id"]

    # 2. Stranger delete -> Forbidden
    stranger_headers = get_auth_headers(client, db, email="stranger_del@example.com")
    res = client.delete(
        f"/recipes/{recipe_id}/comments/{comment_id}", headers=stranger_headers
    )
    assert res.status_code == 403

    # 3. Recipe Owner delete -> Forbidden
    res = client.delete(
        f"/recipes/{recipe_id}/comments/{comment_id}", headers=owner_headers
    )
    assert res.status_code == 403

    # 4. Commenter delete -> OK
    # Re-create comment to delete it
    # Actually wait, let's test admin delete first on this one
    admin_base_headers = get_auth_headers(
        client, db, email="admin_del@example.com", is_admin=True
    )
    admin_headers = {**admin_base_headers, "X-Admin-Mode": "true"}
    res = client.delete(
        f"/recipes/{recipe_id}/comments/{comment_id}", headers=admin_headers
    )
    assert res.status_code == 204

    # 5. Verify deleted
    res = client.get(f"/recipes/{recipe_id}/comments", headers=owner_headers)
    assert len(res.json()) == 0

    # 6. Create another for commenter delete
    res = client.post(
        f"/recipes/{recipe_id}/comments",
        json={"text": "To be deleted by self"},
        headers=commenter_headers,
    )
    comment_id_2 = res.json()["id"]

    res = client.delete(
        f"/recipes/{recipe_id}/comments/{comment_id_2}", headers=commenter_headers
    )
    assert res.status_code == 204
