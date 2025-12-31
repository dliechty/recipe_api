from fastapi.testclient import TestClient
from app import crud, schemas
from app.db.session import SessionLocal

def test_case_insensitive_email_flow(client: TestClient, db):
    # 1. Create User with Mixed Case Email
    mixed_case_email = "MixedCaseUser@Example.com"
    lowercase_email = mixed_case_email.lower()
    
    user_data = schemas.UserCreate(
        email=mixed_case_email, 
        password="testpassword", 
        first_name="Mixed", 
        last_name="Case"
    )
    # Direct CRUD creation first to test schema validator transparency if used (though crud uses simple model init, 
    # but schema usage in API is what matters mostly. Here we test if CRUD stores it as provided or if we rely on schema before CRUD)
    # Actually, CRUD takes schemas.UserCreate, so schema validator SHOULD run if we use the Pydantic model.
    # But wait, crud.create_user takes `user: schemas.UserCreate`, accesses `.email`.
    # Pydantic validator runs when creating the `schemas.UserCreate` instance.
    
    # So let's create via API to be sure we hit the full flow including Pydantic validation
    # Admin needed to create user? No, we have request account or admin create. 
    # Let's use request account for public flow or just use CRUD with a validated schema object.
    
    # Using CRUD with validated schema:
    user = crud.create_user(db, user_data)
    
    # Verify stored as lowercase
    assert user.email == lowercase_email
    
    # 2. Login with Lowercase Email
    login_res_lower = client.post(
        "/auth/token",
        data={"username": lowercase_email, "password": "testpassword"},
    )
    assert login_res_lower.status_code == 200
    
    # 3. Login with Mixed Case Email (should work because endpoint lowercases it)
    login_res_mixed = client.post(
        "/auth/token",
        data={"username": mixed_case_email, "password": "testpassword"},
    )
    assert login_res_mixed.status_code == 200
    
    # 4. Login with Uppercase Email
    login_res_upper = client.post(
        "/auth/token",
        data={"username": mixed_case_email.upper(), "password": "testpassword"},
    )
    assert login_res_upper.status_code == 200

def test_request_account_case_insensitive(client: TestClient, db):
    # Request with mixed case
    email = "RequestUser@Example.com"
    response = client.post(
        "/auth/request-account",
        json={"email": email, "first_name": "Req", "last_name": "User"},
    )
    assert response.status_code == 202
    
    # Check DB
    req = crud.get_user_request_by_email(db, email.lower())
    assert req is not None
    assert req.email == email.lower()
    
    # Try to request again with different case (should fail as duplicate)
    response = client.post(
        "/auth/request-account",
        json={"email": email.upper(), "first_name": "Req", "last_name": "User"},
    )
    # The endpoint returns 200 OK with "Request already pending" if it exists
    assert response.status_code == 200
    assert response.json()["message"] == "Request already pending"
