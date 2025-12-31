
from fastapi.testclient import TestClient
from app import crud, schemas

def get_auth_headers(client: TestClient, db, email="test_ordering@example.com", password="password"):
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

def test_instruction_ordering_repro(client: TestClient, db):
    headers = get_auth_headers(client, db)

    # 1. Create a recipe with instructions deliberately out of order in the list?
    # Actually, the API processes them in order of the list usually.
    # To simulate the DB returning them out of order, we rely on the fact that without order_by,
    # the DB might return them in insertion order or arbitrary order.
    # Explicitly inserting them essentially guarantees insertion order matches list order if we aren't careful.
    
    # However, if we edit the recipe or if the DB decides otherwise, it might be wrong.
    # A better test might be to rely on the fact that `step_number` dictates the order, not the insertion order.
    # But `crud.create_user_recipe` inserts them in the order provided in the list.
    
    # Let's try to create a recipe, then manually mangle the order in the DB if possible, or just create them with step numbers that don't match insertion order (though crud might just insert them as is).
    
    recipe_data = {
        "core": {"name": "Ordering Test", "yield_amount": 1},
        "times": {},
        "nutrition": {},
        "components": [],
        "instructions": [
            {"step_number": 2, "text": "Step 2"},
            {"step_number": 1, "text": "Step 1"},
            {"step_number": 3, "text": "Step 3"}
        ]
    }
    
    # If the API returns them in the order they were inserted, they will come back [2, 1, 3] which is WRONG for display.
    # We want them [1, 2, 3].
    
    create_res = client.post("/recipes/", json=recipe_data, headers=headers)
    assert create_res.status_code == 200
    recipe_id = create_res.json()["core"]["id"]
    
    # Read back
    response = client.get(f"/recipes/{recipe_id}", headers=headers)
    assert response.status_code == 200
    data = response.json()
    
    instructions = data["instructions"]
    assert len(instructions) == 3
    
    # Verify order matches step_number
    step_numbers = [i["step_number"] for i in instructions]
    
    # This assertion ensures that the API returns them sorted by step_number, NOT by insertion order.
    # If it fails (returns [2, 1, 3]), then we have reproduced the issue.
    assert step_numbers == [1, 2, 3], f"Expected [1, 2, 3] but got {step_numbers}"
