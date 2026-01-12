import pytest
from uuid import UUID
from app import models, schemas
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from app.main import app
from app.core.config import settings
from app import crud

@pytest.fixture
def normal_user(db):
    user_data = schemas.UserCreate(
        email="mealuser@example.com",
        password="testpassword",
        first_name="Meal",
        last_name="User"
    )
    # Check if user exists to avoid unique constraint error if test re-runs (though DB is fresh per function usually)
    # But scope="function" fixture in conftest drops tables so it's fine.
    user = crud.create_user(db, user_data)
    return user

@pytest.fixture
def normal_user_token_headers(client, normal_user):
    login_res = client.post(
        "/auth/token",
        data={"username": normal_user.email, "password": "testpassword"},
    )
    token = login_res.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}

# Helper to create a recipe
def create_recipe(db: Session, user_id, name: str, category: str = "Dinner"):
    recipe = models.Recipe(
        name=name,
        owner_id=user_id,
        category=category,
        description="Test description",
        instructions=[],
        components=[]
    )
    db.add(recipe)
    db.commit()
    db.refresh(recipe)
    return recipe

def test_create_meal_template(client: TestClient, db: Session, normal_user_token_headers, normal_user):
    # 1. Create a recipe for DIRECT slot
    recipe = create_recipe(db, normal_user.id, "Direct Recipe")
    
    # 2. Create recipes for LIST slot
    r1 = create_recipe(db, normal_user.id, "List Recipe 1")
    r2 = create_recipe(db, normal_user.id, "List Recipe 2")
    
    # 3. Create Template Input
    template_data = {
        "name": "Test Template",
        "classification": None, #"Dinner",
        "slots": [
            {
                "strategy": "Direct",
                "recipe_id": str(recipe.id)
            },
            {
                "strategy": "List",
                "recipe_ids": [str(r1.id), str(r2.id)]
            },
            {
                "strategy": "Search",
                "search_criteria": [{"field": "category", "operator": "eq", "value": "Dinner"}]
            }
        ]
    }
    
    response = client.post(
        "/meals/templates",
        headers=normal_user_token_headers,
        json=template_data
    )
    
    assert response.status_code == 201
    data = response.json()
    assert data["name"] == "Test Template"
    assert len(data["slots"]) == 3
    
    # Verify DB persistence
    template_id = UUID(data["id"])
    db_template = db.query(models.MealTemplate).filter(models.MealTemplate.id == template_id).first()
    assert db_template is not None
    assert len(db_template.slots) == 3
    
    # Check slots types
    strategies = [s.strategy for s in db_template.slots]
    assert models.MealTemplateSlotStrategy.DIRECT in strategies
    assert models.MealTemplateSlotStrategy.LIST in strategies
    assert models.MealTemplateSlotStrategy.SEARCH in strategies

    # Check DIRECT slot persistence
    direct_slot = next(s for s in db_template.slots if s.strategy == models.MealTemplateSlotStrategy.DIRECT)
    assert direct_slot.recipe_id == recipe.id
    assert direct_slot.search_criteria is None
    assert len(direct_slot.recipes) == 0 # Should not have recipes for direct strategy

    # Check LIST slot persistence
    list_slot = next(s for s in db_template.slots if s.strategy == models.MealTemplateSlotStrategy.LIST)
    assert len(list_slot.recipes) == 2


def test_generate_meal(client: TestClient, db: Session, normal_user_token_headers, normal_user):
    # Setup Data
    r_direct = create_recipe(db, normal_user.id, "Direct One")
    r_list1 = create_recipe(db, normal_user.id, "List One")
    r_search = create_recipe(db, normal_user.id, "Search One", category="Special")
    
    # Create Template via API to ensure proper setup
    template_data = {
        "name": "Gen Template",
        "slots": [
            {
                "strategy": "Direct",
                "recipe_id": str(r_direct.id)
            },
            {
                "strategy": "List",
                "recipe_ids": [str(r_list1.id)]
            },
            {
                "strategy": "Search",
                "search_criteria": [{"field": "category", "operator": "eq", "value": "Special"}]
            }
        ]
    }
    
    create_res = client.post(
        "/meals/templates",
        headers=normal_user_token_headers,
        json=template_data
    )
    assert create_res.status_code == 201
    template_id = create_res.json()["id"]
    
    # Generate Meal
    gen_res = client.post(
        f"/meals/generate?template_id={template_id}",
        headers=normal_user_token_headers
    )
    
    assert gen_res.status_code == 201
    data = gen_res.json()
    assert data["status"] == "Proposed"
    assert "Generated" in data["name"]
    
    # Should have 3 items
    assert len(data["items"]) == 3
    
    # Verify items match expected structure
    # We can't easily verify which item came from which slot in the flat list without more logic,
    # but we can check if the recipe IDs are present.
    item_recipe_ids = [item["recipe_id"] for item in data["items"]]
    assert str(r_direct.id) in item_recipe_ids
    assert str(r_list1.id) in item_recipe_ids
    assert str(r_search.id) in item_recipe_ids

def test_meal_crud(client: TestClient, db: Session, normal_user_token_headers, normal_user):
    # Create Meal Manual
    r = create_recipe(db, normal_user.id, "Manual Meal Recipe")
    
    meal_data = {
        "name": "My Manual Meal",
        "status": "Scheduled",
        "classification": "Lunch",
        "items": [{"recipe_id": str(r.id)}]
    }
    
    # Create
    res = client.post(
        "/meals/",
        headers=normal_user_token_headers,
        json=meal_data
    )
    assert res.status_code == 201
    meal_id = res.json()["id"]
    
    # Get List
    res = client.get("/meals/", headers=normal_user_token_headers)
    assert res.status_code == 200
    assert len(res.json()) >= 1
    
    # Update
    update_data = {"status": "Cooked"}
    res = client.put(
        f"/meals/{meal_id}",
        headers=normal_user_token_headers,
        json=update_data
    )
    assert res.status_code == 200
    assert res.json()["status"] == "Cooked"
    
    # Delete
    res = client.delete(f"/meals/{meal_id}", headers=normal_user_token_headers)
    assert res.status_code == 204
    
    # Verify Delete
    res = client.get(f"/meals/{meal_id}", headers=normal_user_token_headers)
    assert res.status_code == 404


def test_generate_meal_complex_filters(client: TestClient, db: Session, normal_user_token_headers, normal_user):
    # Setup Recipes
    # Target: Medium difficulty, < 30 mins
    target_recipe = create_recipe(db, normal_user.id, "Target Recipe")
    target_recipe.difficulty = models.DifficultyLevel.MEDIUM
    target_recipe.total_time_minutes = 20
    db.add(target_recipe)
    
    # Noise 1: Easy, < 30 mins
    noise1 = create_recipe(db, normal_user.id, "Noise 1")
    noise1.difficulty = models.DifficultyLevel.EASY
    noise1.total_time_minutes = 20
    db.add(noise1)
    
    # Noise 2: Medium, > 30 mins
    noise2 = create_recipe(db, normal_user.id, "Noise 2")
    noise2.difficulty = models.DifficultyLevel.MEDIUM
    noise2.total_time_minutes = 60
    db.add(noise2)
    
    db.commit()
    
    # Create Template
    template_data = {
        "name": "Complex Filter Template",
        "slots": [
            {
                "strategy": "Search",
                "search_criteria": [
                    {"field": "difficulty", "operator": "eq", "value": "Medium"},
                    {"field": "total_time_minutes", "operator": "lt", "value": 30}
                ]
            }
        ]
    }
    
    create_res = client.post(
        "/meals/templates",
        headers=normal_user_token_headers,
        json=template_data
    )
    assert create_res.status_code == 201
    template_id = create_res.json()["id"]
    
    # Generate Meal
    gen_res = client.post(
        f"/meals/generate?template_id={template_id}",
        headers=normal_user_token_headers
    )
    
    assert gen_res.status_code == 201
    data = gen_res.json()
    
    # Should find exactly the target recipe
    generated_item = data["items"][0]
    assert generated_item["recipe_id"] == str(target_recipe.id)


def test_invalid_search_criteria_rejected(client: TestClient, db: Session, normal_user_token_headers, normal_user):
    """Test that invalid search criteria fields and operators are rejected."""

    # Test invalid field
    invalid_field_data = {
        "name": "Invalid Field Template",
        "slots": [
            {
                "strategy": "Search",
                "search_criteria": [
                    {"field": "invalid_field", "operator": "eq", "value": "test"}
                ]
            }
        ]
    }
    response = client.post(
        "/meals/templates",
        headers=normal_user_token_headers,
        json=invalid_field_data
    )
    assert response.status_code == 422
    assert "invalid_field" in response.text.lower() or "Invalid search field" in response.text

    # Test invalid operator
    invalid_operator_data = {
        "name": "Invalid Operator Template",
        "slots": [
            {
                "strategy": "Search",
                "search_criteria": [
                    {"field": "category", "operator": "invalid_op", "value": "test"}
                ]
            }
        ]
    }
    response = client.post(
        "/meals/templates",
        headers=normal_user_token_headers,
        json=invalid_operator_data
    )
    assert response.status_code == 422
    assert "invalid_op" in response.text.lower() or "Invalid operator" in response.text

    # Test empty value
    empty_value_data = {
        "name": "Empty Value Template",
        "slots": [
            {
                "strategy": "Search",
                "search_criteria": [
                    {"field": "category", "operator": "eq", "value": ""}
                ]
            }
        ]
    }
    response = client.post(
        "/meals/templates",
        headers=normal_user_token_headers,
        json=empty_value_data
    )
    assert response.status_code == 422
    assert "empty" in response.text.lower() or "value" in response.text.lower()


def test_update_meal_items(client: TestClient, db: Session, normal_user_token_headers, normal_user):
    # Setup
    r1 = create_recipe(db, normal_user.id, "Recipe 1")
    r2 = create_recipe(db, normal_user.id, "Recipe 2")
    r3 = create_recipe(db, normal_user.id, "Recipe 3")
    
    # Create valid meal
    meal_data = {
        "name": "Update Items Test",
        "items": [{"recipe_id": str(r1.id)}]
    }
    create_res = client.post("/meals/", headers=normal_user_token_headers, json=meal_data)
    meal_id = create_res.json()["id"]
    
    # 1. Replace Items
    update_data = {
        "items": [
            {"recipe_id": str(r2.id)},
            {"recipe_id": str(r3.id)}
        ]
    }
    res = client.put(f"/meals/{meal_id}", headers=normal_user_token_headers, json=update_data)
    assert res.status_code == 200
    data = res.json()
    assert len(data["items"]) == 2
    ids = [item["recipe_id"] for item in data["items"]]
    assert str(r2.id) in ids
    assert str(r3.id) in ids
    assert str(r1.id) not in ids
    
    # 2. Clear Items
    update_data = {"items": []}
    res = client.put(f"/meals/{meal_id}", headers=normal_user_token_headers, json=update_data)
    assert res.status_code == 200
    assert len(res.json()["items"]) == 0
    
    # 3. Partial Update (no items field) should keep existing
    # Add one back first
    client.put(f"/meals/{meal_id}", headers=normal_user_token_headers, json={"items": [{"recipe_id": str(r1.id)}]})
    
    update_data = {"name": "Renamed Meal"} # No items field
    res = client.put(f"/meals/{meal_id}", headers=normal_user_token_headers, json=update_data)
    assert res.status_code == 200
    assert res.json()["name"] == "Renamed Meal"
    assert len(res.json()["items"]) == 1
    assert res.json()["items"][0]["recipe_id"] == str(r1.id)
