from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from uuid import uuid4
import pytest

from app.filters import parse_filters, Filter
from app.api.recipes import read_recipes
from app import models, crud, schemas
from app.db.session import SessionLocal

# --- Unit Tests ---

def test_parse_filters_simple():
    params = {"category[eq]": "Dinner", "calories[lt]": "500"}
    filters = parse_filters(params)
    assert len(filters) == 2
    f1 = next(f for f in filters if f.field == "category")
    assert f1.operator == "eq"
    assert f1.value == "Dinner"
    
    f2 = next(f for f in filters if f.field == "calories")
    assert f2.operator == "lt"
    assert f2.value == "500"

def test_parse_filters_list():
    params = {"ingredients[in]": "milk,eggs"}
    filters = parse_filters(params)
    assert len(filters) == 1
    assert filters[0].field == "ingredients"
    assert filters[0].operator == "in"
    assert filters[0].value == "milk,eggs"

def test_parse_filters_invalid_format():
    params = {"invalid_param": "value"}
    filters = parse_filters(params)
    assert len(filters) == 0

# --- Integration Tests (using DB) ---

# --- Integration Tests (using DB) ---


def test_filter_recipes_by_name(db: Session):
    # Setup data (assuming DB might be empty or pre-populated, better to create temp data)
    # For now, relying on existing data or creating specific items
    # Let's create a recipe
    user = crud.get_user_by_email(db, "test@example.com")
    if not user:
         # Create dummy user if needed, or skip if no auth fixture handy here
         pass 

    # We will just test the crude query generation -> execution path
    # by ensuring it doesn't crash and returns a list (even if empty)
    
    filters_list = [Filter("name", "like", "Chicken")]
    recipes, _ = crud.get_recipes(db, filters_list=filters_list)
    assert isinstance(recipes, list)

def test_filter_recipes_by_time(db: Session):
    # Test all time fields
    filters_list = [
        Filter("total_time_minutes", "lt", 60),
        Filter("prep_time_minutes", "lt", 30),
        Filter("cook_time_minutes", "lt", 30),
        # Active time might be null for some, so gt 0 checks existence
        Filter("active_time_minutes", "gte", 0) 
    ]
    recipes, _ = crud.get_recipes(db, filters_list=filters_list)
    assert isinstance(recipes, list)

def test_sort_recipes(db: Session):
    recipes, _ = crud.get_recipes(db, sort_by="-created_at")
    assert isinstance(recipes, list)
    # If we had data, we could verify order. 
    # Checking for no SQL error is a good first step.

def test_compound_filters(db: Session):
    # category=Dinner AND calories < 1000
    filters_list = [
        Filter("category", "eq", "Dinner"),
        Filter("calories", "lt", 1000)
    ]
    recipes, _ = crud.get_recipes(db, filters_list=filters_list)
    assert isinstance(recipes, list)

def test_meta_endpoints(db: Session):
    vals = crud.get_unique_values(db, "category")
    assert isinstance(vals, list)
    
    vals_prot = crud.get_unique_values(db, "protein")
    assert isinstance(vals_prot, list)


# --- API / Client Tests ---

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
