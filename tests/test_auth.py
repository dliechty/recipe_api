
from fastapi.testclient import TestClient
from app import crud, schemas

def test_create_user(client: TestClient, db):
    response = client.post(
        "/auth/users/",
        json={"email": "test@example.com", "password": "password123"},
    )
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["email"] == "test@example.com"
    assert "id" in data

def test_create_existing_user(client: TestClient, db):
    # First create
    client.post(
        "/auth/users/",
        json={"email": "duplicate@example.com", "password": "password123"},
    )
    # Second create
    response = client.post(
        "/auth/users/",
        json={"email": "duplicate@example.com", "password": "password123"},
    )
    assert response.status_code == 400
    assert response.json()["detail"] == "Email already registered"

def test_login_user(client: TestClient, db):
    # Create user first
    client.post(
        "/auth/users/",
        json={"email": "login@example.com", "password": "password123"},
    )
    
    # Login
    response = client.post(
        "/auth/token",
        data={"username": "login@example.com", "password": "password123"},
    )
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"

def test_login_wrong_password(client: TestClient, db):
    client.post(
        "/auth/users/",
        json={"email": "wrongpass@example.com", "password": "password123"},
    )
    response = client.post(
        "/auth/token",
        data={"username": "wrongpass@example.com", "password": "wrongpassword"},
    )
    assert response.status_code == 401
    assert response.json()["detail"] == "Incorrect email or password"

def test_get_user_public_info(client: TestClient, db):
    # 1. Create a user
    email = "public_info@example.com"
    password = "password123"
    client.post(
        "/auth/users/",
        json={
            "email": email, 
            "password": password,
            "first_name": "Public",
            "last_name": "User"
        },
    )
    
    # 2. Login
    login_res = client.post(
        "/auth/token",
        data={"username": email, "password": password},
    )
    token = login_res.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    
    # Get user ID from login or by fetching me? 
    # Or just fetch list? We don't have list endpoint for users publicly.
    # We can get the ID from the create response if we capture it.
    
    # Let's re-create capture
    # Actually, we can just use the login token to get "me" if we had a /me endpoint, 
    # but we only added /auth/users/{user_id}.
    # We need the ID.
    
    # Re-doing the flow cleanly:
    
    # 1. Create
    create_res = client.post(
        "/auth/users/",
        json={
            "email": "public_info_2@example.com", 
            "password": password,
            "first_name": "Public",
            "last_name": "User"
        },
    )
    user_id = create_res.json()["id"]
    
    # 2. Login
    login_res = client.post(
        "/auth/token",
        data={"username": "public_info_2@example.com", "password": password},
    )
    token = login_res.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    
    # 3. Get Info
    response = client.get(f"/auth/users/{user_id}", headers=headers)
    assert response.status_code == 200
    data = response.json()
    
    # 4. Verify Fields
    assert data["email"] == "public_info_2@example.com"
    assert data["first_name"] == "Public"
    assert data["last_name"] == "User"
    assert "id" in data
    
    # 5. Verify Exclusions
    assert "password" not in data
    assert "hashed_password" not in data
    assert "is_active" not in data # UserPublic didn't include this
    assert "is_admin" not in data # UserPublic didn't include this
