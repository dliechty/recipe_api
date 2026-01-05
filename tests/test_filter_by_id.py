
from fastapi.testclient import TestClient
from app import crud, schemas, models
from uuid import uuid4

def get_auth_headers(client: TestClient, db, email="user_filter_id@example.com", password="password"):
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

def test_filter_by_id_collection(client: TestClient, db):
    headers = get_auth_headers(client, db)

    # Create 3 recipes
    def create_simple_recipe(name):
        data = {
            "core": {"name": name},
            "times": {},
            "nutrition": {},
            "components": [],
            "instructions": []
        }
        res = client.post("/recipes/", json=data, headers=headers)
        return res.json()["core"]["id"]

    id1 = create_simple_recipe("Recipe 1")
    id2 = create_simple_recipe("Recipe 2")
    id3 = create_simple_recipe("Recipe 3")

    # Filter for ID 1 and 3
    query_ids = f"{id1},{id3}"
    # Use URL encoding brackets if client doesn't automatically? 
    # FastAPI TestClient handles params well usually, but we need specific format "id[in]=..."
    
    # Passing params directly as valid URL string
    response = client.get(f"/recipes/?id[in]={query_ids}", headers=headers)
    
    assert response.status_code == 200
    data = response.json()
    
    assert len(data) == 2
    
    returned_ids = [r["core"]["id"] for r in data]
    assert id1 in returned_ids
    assert id3 in returned_ids
    assert id2 not in returned_ids
