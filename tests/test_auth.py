
from fastapi.testclient import TestClient
from app import crud, schemas, models
from app.db.session import SessionLocal

def test_request_account_flow(client: TestClient, db):
    # 1. Request Account
    response = client.post(
        "/auth/request-account",
        json={"email": "newuser@example.com", "first_name": "New", "last_name": "User"},
    )
    assert response.status_code == 202
    assert response.json()["message"] == "Account request submitted"
    
    # 2. Duplicate Request
    response = client.post(
        "/auth/request-account",
        json={"email": "newuser@example.com", "first_name": "New", "last_name": "User"},
    )
    assert response.status_code == 200
    assert response.json()["message"] == "Request already pending"

    # 3. Create Admin User manually to approve
    admin_data = schemas.UserCreate(
        email="admin@example.com", 
        password="adminpass", 
        first_name="Admin", 
        last_name="User"
    )
    admin_user = crud.create_user(db, admin_data)
    admin_user.is_admin = True
    db.commit()
    
    # Login as Admin
    login_res = client.post(
        "/auth/token",
        data={"username": "admin@example.com", "password": "adminpass"},
    )
    token = login_res.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    
    # 4. List Pending Requests
    response = client.get("/auth/pending-requests", headers=headers)
    assert response.status_code == 200
    requests = response.json()
    assert len(requests) >= 1
    req_id = requests[0]["id"]
    
    # 5. Approve Request
    response = client.post(
        f"/auth/approve-request/{req_id}",
        headers=headers,
        json={"initial_password": "temppassword"}
    )
    assert response.status_code == 200
    user_data = response.json()
    assert user_data["email"] == "newuser@example.com"
    assert user_data["is_first_login"] == True
    
    # 6. Login as New User
    login_res = client.post(
        "/auth/token",
        data={"username": "newuser@example.com", "password": "temppassword"},
    )
    assert login_res.status_code == 200
    user_token = login_res.json()["access_token"]
    user_headers = {"Authorization": f"Bearer {user_token}"}
    
    # 7. Change Password
    response = client.post(
        "/auth/change-password",
        headers=user_headers,
        json={"old_password": "temppassword", "new_password": "newpassword123"}
    )
    assert response.status_code == 200
    
    # 8. Verify Login with New Password
    login_res = client.post(
        "/auth/token",
        data={"username": "newuser@example.com", "password": "newpassword123"},
    )
    assert login_res.status_code == 200


def test_admin_management_functions(client: TestClient, db):
    # Setup Admin
    admin_data = schemas.UserCreate(
        email="admin2@example.com", 
        password="adminpass", 
        first_name="Admin", 
        last_name="User"
    )
    admin = crud.create_user(db, admin_data)
    admin.is_admin = True
    db.commit()
    
    token = client.post(
        "/auth/token",
        data={"username": "admin2@example.com", "password": "adminpass"},
    ).json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    
    # Create Target User
    user_data = schemas.UserCreate(
        email="target@example.com", 
        password="oldpassword", 
        first_name="Target", 
        last_name="User"
    )
    target = crud.create_user(db, user_data)
    target_id = str(target.id)
    
    # 1. Edit User
    res = client.put(
        f"/auth/users/{target_id}",
        headers=headers,
        json={"first_name": "UpdatedTarget"}
    )
    assert res.status_code == 200
    assert res.json()["first_name"] == "UpdatedTarget"
    
    # 2. Reset User
    res = client.post(
        f"/auth/users/{target_id}/reset",
        headers=headers,
        json={"initial_password": "resetpassword"}
    )
    assert res.status_code == 200
    
    # Verify Reset (login with new password)
    res = client.post(
        "/auth/token",
        data={"username": "target@example.com", "password": "resetpassword"}
    )
    assert res.status_code == 200
    
    # 3. Delete User
    res = client.delete(f"/auth/users/{target_id}", headers=headers)
    assert res.status_code == 200
    
    # Verify Gone
    res = client.get(f"/auth/users/{target_id}", headers=headers)
    assert res.status_code == 404
