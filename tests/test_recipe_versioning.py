
from fastapi.testclient import TestClient
from tests.test_recipes import get_auth_headers

def test_recipe_versioning_logic(client: TestClient, db):
    headers = get_auth_headers(client, db, email="version_tester@example.com")

    
    # 1. Create Recipe
    recipe_data = {
        "core": {"name": "Version Test", "description": "v1"},
        "times": {},
        "nutrition": {},
        "components": [{"name": "Main", "ingredients": [{"ingredient_name": "Sugar", "quantity": 100, "unit": "g"}]}],
        "instructions": [{"step_number": 1, "text": "Mix"}]
    }
    
    create_resp = client.post("/recipes/", json=recipe_data, headers=headers)
    assert create_resp.status_code == 201
    recipe = create_resp.json()
    recipe_id = recipe["core"]["id"]

    # Verify initial version
    assert recipe["audit"]["version"] == 1
    
    # 2. Idempotent Update (Same Content)
    update_data = recipe_data.copy()
    # Ensure we strictly copy the data structure as expected by update endpoint
    # The update endpoint expects RecipeCreate schema, which matches our recipe_data structure
    
    update_resp = client.put(f"/recipes/{recipe_id}", json=update_data, headers=headers)
    assert update_resp.status_code == 200
    updated_recipe = update_resp.json()
    
    # Verify version did NOT increment
    assert updated_recipe["audit"]["version"] == 1
    
    # 3. Content Update (Change Name)
    update_data["core"]["name"] = "Version Test V2"
    update_resp_v2 = client.put(f"/recipes/{recipe_id}", json=update_data, headers=headers)
    assert update_resp_v2.status_code == 200
    updated_recipe_v2 = update_resp_v2.json()
    
    # Verify version incremented
    assert updated_recipe_v2["audit"]["version"] == 2
    
    # 4. Content Update (Change Ingredient Quantity)
    update_data["components"][0]["ingredients"][0]["quantity"] = 200
    update_resp_v3 = client.put(f"/recipes/{recipe_id}", json=update_data, headers=headers)
    assert update_resp_v3.status_code == 200
    updated_recipe_v3 = update_resp_v3.json()
    
    
    # 5. Timestamp Verification
    recipe_v3_datetime = updated_recipe_v3["audit"]["updated_at"]
    assert recipe_v3_datetime is not None
    
    # Update with Explicit Timestamp
    # Using a fake future date to verify explicit set works
    future_time = "2099-01-01T12:00:00Z"
    update_data["audit"] = {"updated_at": future_time}
    update_resp_v4 = client.put(f"/recipes/{recipe_id}", json=update_data, headers=headers)
    assert update_resp_v4.status_code == 200
    updated_recipe_v4 = update_resp_v4.json()
    
    # Verify explicit timestamp was respected
    # Note: Pydantic might normalize format, so we check startswith or parse
    assert updated_recipe_v4["audit"]["updated_at"].startswith("2099-01-01")

from datetime import datetime, timezone, timedelta

def test_timestamp_behavior(client: TestClient, db):
    headers = get_auth_headers(client, db, email="time_tester@example.com")

    
    # 1. Create Recipe (Default Timestamps)
    recipe_data = {
        "core": {"name": "Time Test", "description": "Checking clocks"},
        "times": {},
        "nutrition": {},
        "components": [],
        "instructions": []
    }
    
    start_time = datetime.now(timezone.utc)
    create_resp = client.post("/recipes/", json=recipe_data, headers=headers)
    assert create_resp.status_code == 201
    recipe = create_resp.json()
    recipe_id = recipe["core"]["id"]

    created_at = recipe["audit"]["created_at"]
    updated_at = recipe["audit"]["updated_at"]
    
    assert created_at is not None
    assert updated_at is not None
    
    # Parse times
    parsed_created = datetime.fromisoformat(created_at.replace('Z', '+00:00'))
    if parsed_created.tzinfo is None:
        parsed_created = parsed_created.replace(tzinfo=timezone.utc)
        
    assert start_time - timedelta(minutes=1) < parsed_created < start_time + timedelta(minutes=1)
    
    # 2. Update Recipe (Implicit Update Time)
    import time
    time.sleep(1.1) 
    
    update_data = recipe_data.copy()
    update_data["core"]["name"] = "Time Test Updated"
    
    update_resp = client.put(f"/recipes/{recipe_id}", json=update_data, headers=headers)
    assert update_resp.status_code == 200
    updated_recipe = update_resp.json()
    
    new_created_at = updated_recipe["audit"]["created_at"]
    new_updated_at = updated_recipe["audit"]["updated_at"]
    
    # created_at should NOT change
    assert new_created_at == created_at
    # updated_at SHOULD change
    assert new_updated_at != updated_at
    assert new_updated_at > updated_at

    # 3. Explicit Creation Timestamps
    explicit_created = "2020-01-01T10:00:00+00:00"
    explicit_updated = "2020-01-01T11:00:00+00:00"
    
    recipe_data_explicit = recipe_data.copy()
    recipe_data_explicit["audit"] = {
        "created_at": explicit_created,
        "updated_at": explicit_updated
    }
    
    create_resp_2 = client.post("/recipes/", json=recipe_data_explicit, headers=headers)
    assert create_resp_2.status_code == 201
    recipe_2 = create_resp_2.json()
    
    assert recipe_2["audit"]["created_at"].startswith(explicit_created.split('+')[0])
    assert recipe_2["audit"]["updated_at"].startswith(explicit_updated.split('+')[0])
    
    # 4. Explicit Update Timestamp
    future_time = "2100-01-01T00:00:00+00:00"
    update_data_explicit = update_data.copy()
    update_data_explicit["audit"] = {"updated_at": future_time}
    
    update_resp_explicit = client.put(f"/recipes/{recipe_id}", json=update_data_explicit, headers=headers)
    assert update_resp_explicit.status_code == 200
    updated_explicit = update_resp_explicit.json()
    
    assert updated_explicit["audit"]["updated_at"].startswith(future_time.split('+')[0])
