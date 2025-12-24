
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
