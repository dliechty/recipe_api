
from fastapi.testclient import TestClient
from app import crud, schemas

def test_list_active_users(client: TestClient, db):
    # 1. Setup Admin
    admin_data = schemas.UserCreate(
        email="admin_list@example.com", 
        password="adminpass", 
        first_name="Admin", 
        last_name="List"
    )
    admin = crud.create_user(db, admin_data)
    admin.is_admin = True
    db.commit()
    
    admin_token = client.post(
        "/auth/token",
        data={"username": "admin_list@example.com", "password": "adminpass"},
    ).json()["access_token"]
    admin_headers = {"Authorization": f"Bearer {admin_token}"}
    
    # 2. Setup Active User
    active_user_data = schemas.UserCreate(
        email="active@example.com", 
        password="userpass", 
        first_name="Active", 
        last_name="User"
    )
    crud.create_user(db, active_user_data)
    
    # 3. Setup Inactive User
    inactive_user_data = schemas.UserCreate(
        email="inactive@example.com", 
        password="userpass", 
        first_name="Inactive", 
        last_name="User"
    )
    inactive_user = crud.create_user(db, inactive_user_data)
    inactive_user.is_active = False
    db.commit()
    
    # 4. Admin lists users
    response = client.get("/auth/users", headers=admin_headers)
    assert response.status_code == 200
    users = response.json()
    
    # Verify we got active users
    emails = [u["email"] for u in users]
    assert "active@example.com" in emails
    assert "admin_list@example.com" in emails
    
    # Verify we did NOT get inactive users
    assert "inactive@example.com" not in emails

def test_list_active_users_forbidden(client: TestClient, db):
    # 1. Setup Regular User
    user_data = schemas.UserCreate(
        email="normal_list@example.com", 
        password="userpass", 
        first_name="Normal", 
        last_name="List"
    )
    crud.create_user(db, user_data)
    
    user_token = client.post(
        "/auth/token",
        data={"username": "normal_list@example.com", "password": "userpass"},
    ).json()["access_token"]
    user_headers = {"Authorization": f"Bearer {user_token}"}
    
    # 2. Try to list users
    response = client.get("/auth/users", headers=user_headers)
    assert response.status_code == 403
