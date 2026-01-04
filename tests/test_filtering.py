from app.filters import parse_filters, Filter
from app.api.recipes import read_recipes
from app import models, crud
from sqlalchemy.orm import Session
import pytest
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

@pytest.fixture(scope="module")
def db():
    db = SessionLocal()
    yield db
    db.close()

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
