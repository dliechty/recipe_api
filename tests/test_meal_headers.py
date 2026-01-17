import pytest
from uuid import UUID
from app import models, schemas
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from app import crud

@pytest.fixture
def normal_user(db):
    user_data = schemas.UserCreate(
        email="headeruser@example.com",
        password="testpassword",
        first_name="Header",
        last_name="User"
    )
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

def test_meal_template_pagination_header(client: TestClient, db: Session, normal_user_token_headers, normal_user):
    # Create 3 templates
    for i in range(3):
        # Create a unique recipe for each template to ensure slots are unique
        # otherwise duplicate detection will prevent creation
        recipe_i = create_recipe(db, normal_user.id, f"Header Recipe {i}")
        
        template_data = {
            "name": f"Template {i}",
            "slots": [
                {
                    "strategy": "Direct",
                    "recipe_id": str(recipe_i.id)
                }
            ]
        }
        res = client.post("/meals/templates", headers=normal_user_token_headers, json=template_data)
        assert res.status_code == 201

    # Get Templates
    res = client.get("/meals/templates", headers=normal_user_token_headers)
    assert res.status_code == 200
    assert "X-Total-Count" in res.headers
    assert res.headers["X-Total-Count"] == "3"
    
    # Test Pagination doesn't affect total count
    res = client.get("/meals/templates?limit=1", headers=normal_user_token_headers)
    assert res.status_code == 200
    assert len(res.json()) == 1
    assert res.headers["X-Total-Count"] == "3"

def test_meal_pagination_header(client: TestClient, db: Session, normal_user_token_headers, normal_user):
    # Create a recipe
    recipe = create_recipe(db, normal_user.id, "Meal Header Recipe")
    
    # Create template
    template_data = {
        "name": "Meal Gen Template",
        "slots": [
            {
                "strategy": "Direct",
                "recipe_id": str(recipe.id)
            }
        ]
    }
    res = client.post("/meals/templates", headers=normal_user_token_headers, json=template_data)
    template_id = res.json()["id"]
    
    # Create 4 meals
    for i in range(4):
        meal_data = {
            "name": f"Meal {i}",
            "template_id": template_id,
            "status": "Scheduled",
            "items": []
        }
        res = client.post("/meals/", headers=normal_user_token_headers, json=meal_data)
        assert res.status_code == 201
        
    # Get Meals
    res = client.get("/meals/", headers=normal_user_token_headers)
    assert res.status_code == 200
    assert "X-Total-Count" in res.headers
    assert res.headers["X-Total-Count"] == "4"
    
    # Test Pagination
    res = client.get("/meals/?limit=2", headers=normal_user_token_headers)
    assert res.status_code == 200
    assert len(res.json()) == 2
    assert res.headers["X-Total-Count"] == "4"
