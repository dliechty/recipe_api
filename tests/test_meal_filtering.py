"""Tests for meal and template filtering functionality."""
import pytest
from datetime import datetime, timedelta
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app import models, schemas, crud
from app.filters import (
    parse_filters,
    Filter,
    apply_meal_filters,
    apply_template_filters,
    apply_meal_sorting,
)


# --- Fixtures ---

@pytest.fixture
def filter_user(db):
    """Create a test user for filtering tests."""
    user_data = schemas.UserCreate(
        email="filteruser@example.com",
        password="testpassword",
        first_name="Filter",
        last_name="User"
    )
    return crud.create_user(db, user_data)


@pytest.fixture
def filter_user_headers(client, filter_user):
    """Get auth headers for the filter user."""
    login_res = client.post(
        "/auth/token",
        data={"username": filter_user.email, "password": "testpassword"},
    )
    token = login_res.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def create_recipe(db: Session, user_id, name: str, category: str = "Dinner"):
    """Helper to create a recipe."""
    recipe = models.Recipe(
        name=name,
        owner_id=user_id,
        category=category,
        description="Test description",
    )
    db.add(recipe)
    db.commit()
    db.refresh(recipe)
    return recipe


# --- Unit Tests for parse_filters ---

def test_parse_filters_meal_fields():
    """Test parsing filters for meal-specific fields."""
    params = {"status[eq]": "Draft", "classification[eq]": "Dinner"}
    filters = parse_filters(params)
    assert len(filters) == 2

    status_filter = next(f for f in filters if f.field == "status")
    assert status_filter.operator == "eq"
    assert status_filter.value == "Draft"

    class_filter = next(f for f in filters if f.field == "classification")
    assert class_filter.operator == "eq"
    assert class_filter.value == "Dinner"


def test_parse_filters_date_comparison():
    """Test parsing date comparison filters."""
    params = {"date[gte]": "2025-01-01", "date[lt]": "2025-02-01"}
    filters = parse_filters(params)
    assert len(filters) == 2

    gte_filter = next(f for f in filters if f.operator == "gte")
    assert gte_filter.field == "date"
    assert gte_filter.value == "2025-01-01"


def test_parse_filters_name_like():
    """Test parsing name like filter."""
    params = {"name[like]": "chicken"}
    filters = parse_filters(params)
    assert len(filters) == 1
    assert filters[0].field == "name"
    assert filters[0].operator == "like"
    assert filters[0].value == "chicken"


def test_parse_filters_num_slots():
    """Test parsing num_slots filter for templates."""
    params = {"num_slots[gt]": "2", "num_slots[lte]": "5"}
    filters = parse_filters(params)
    assert len(filters) == 2


# --- Unit Tests for apply_meal_filters ---

def test_apply_meal_filters_by_status(db: Session, filter_user):
    """Test filtering meals by status."""
    # Create meals with different statuses
    meal1 = models.Meal(
        user_id=filter_user.id,
        name="Draft Meal",
        status=models.MealStatus.DRAFT
    )
    meal2 = models.Meal(
        user_id=filter_user.id,
        name="Scheduled Meal",
        status=models.MealStatus.SCHEDULED
    )
    meal3 = models.Meal(
        user_id=filter_user.id,
        name="Cooked Meal",
        status=models.MealStatus.COOKED
    )
    db.add_all([meal1, meal2, meal3])
    db.commit()

    # Filter for Draft status
    query = db.query(models.Meal).filter(models.Meal.user_id == filter_user.id)
    filters_list = [Filter("status", "eq", "Draft")]
    query = apply_meal_filters(query, filters_list)
    results = query.all()

    assert len(results) == 1
    assert results[0].name == "Draft Meal"


def test_apply_meal_filters_by_classification(db: Session, filter_user):
    """Test filtering meals by classification."""
    meal1 = models.Meal(
        user_id=filter_user.id,
        name="Breakfast",
        classification=models.MealClassification.BREAKFAST
    )
    meal2 = models.Meal(
        user_id=filter_user.id,
        name="Dinner",
        classification=models.MealClassification.DINNER
    )
    db.add_all([meal1, meal2])
    db.commit()

    query = db.query(models.Meal).filter(models.Meal.user_id == filter_user.id)
    filters_list = [Filter("classification", "eq", "Dinner")]
    query = apply_meal_filters(query, filters_list)
    results = query.all()

    assert len(results) == 1
    assert results[0].name == "Dinner"


def test_apply_meal_filters_by_name_like(db: Session, filter_user):
    """Test filtering meals by name using LIKE."""
    meal1 = models.Meal(user_id=filter_user.id, name="Chicken Dinner")
    meal2 = models.Meal(user_id=filter_user.id, name="Beef Stew")
    meal3 = models.Meal(user_id=filter_user.id, name="Grilled Chicken")
    db.add_all([meal1, meal2, meal3])
    db.commit()

    query = db.query(models.Meal).filter(models.Meal.user_id == filter_user.id)
    filters_list = [Filter("name", "like", "chicken")]
    query = apply_meal_filters(query, filters_list)
    results = query.all()

    assert len(results) == 2
    names = [r.name for r in results]
    assert "Chicken Dinner" in names
    assert "Grilled Chicken" in names


def test_apply_meal_filters_by_date_range(db: Session, filter_user):
    """Test filtering meals by date range."""
    base_date = datetime(2025, 1, 15)
    meal1 = models.Meal(
        user_id=filter_user.id,
        name="Early Meal",
        date=base_date - timedelta(days=10)
    )
    meal2 = models.Meal(
        user_id=filter_user.id,
        name="Mid Meal",
        date=base_date
    )
    meal3 = models.Meal(
        user_id=filter_user.id,
        name="Late Meal",
        date=base_date + timedelta(days=10)
    )
    db.add_all([meal1, meal2, meal3])
    db.commit()

    query = db.query(models.Meal).filter(models.Meal.user_id == filter_user.id)
    # Filter for meals on or after Jan 10
    filters_list = [
        Filter("date", "gte", "2025-01-10"),
        Filter("date", "lte", "2025-01-20")
    ]
    query = apply_meal_filters(query, filters_list)
    results = query.all()

    assert len(results) == 1
    assert results[0].name == "Mid Meal"


def test_apply_meal_filters_compound(db: Session, filter_user):
    """Test applying multiple filters (AND logic)."""
    meal1 = models.Meal(
        user_id=filter_user.id,
        name="Draft Dinner",
        status=models.MealStatus.DRAFT,
        classification=models.MealClassification.DINNER
    )
    meal2 = models.Meal(
        user_id=filter_user.id,
        name="Scheduled Dinner",
        status=models.MealStatus.SCHEDULED,
        classification=models.MealClassification.DINNER
    )
    meal3 = models.Meal(
        user_id=filter_user.id,
        name="Draft Breakfast",
        status=models.MealStatus.DRAFT,
        classification=models.MealClassification.BREAKFAST
    )
    db.add_all([meal1, meal2, meal3])
    db.commit()

    query = db.query(models.Meal).filter(models.Meal.user_id == filter_user.id)
    filters_list = [
        Filter("status", "eq", "Draft"),
        Filter("classification", "eq", "Dinner")
    ]
    query = apply_meal_filters(query, filters_list)
    results = query.all()

    assert len(results) == 1
    assert results[0].name == "Draft Dinner"


def test_apply_meal_filters_by_recipe(db: Session, filter_user):
    """Test filtering meals by associated recipe."""
    recipe1 = create_recipe(db, filter_user.id, "Spaghetti")
    recipe2 = create_recipe(db, filter_user.id, "Salad")

    meal1 = models.Meal(user_id=filter_user.id, name="Italian Night")
    meal2 = models.Meal(user_id=filter_user.id, name="Healthy Night")
    db.add_all([meal1, meal2])
    db.commit()

    # Add recipe items
    item1 = models.MealItem(meal_id=meal1.id, recipe_id=recipe1.id)
    item2 = models.MealItem(meal_id=meal2.id, recipe_id=recipe2.id)
    db.add_all([item1, item2])
    db.commit()

    # Filter by recipe name
    query = db.query(models.Meal).filter(models.Meal.user_id == filter_user.id)
    filters_list = [Filter("recipe", "like", "Spag")]
    query = apply_meal_filters(query, filters_list)
    results = query.distinct().all()

    assert len(results) == 1
    assert results[0].name == "Italian Night"


# --- Unit Tests for apply_meal_sorting ---

def test_apply_meal_sorting_default_nulls_first(db: Session, filter_user):
    """Test that default sorting puts NULL dates first."""
    base_date = datetime(2025, 1, 15)
    meal1 = models.Meal(user_id=filter_user.id, name="With Date 1", date=base_date)
    meal2 = models.Meal(user_id=filter_user.id, name="No Date")  # NULL date
    meal3 = models.Meal(user_id=filter_user.id, name="With Date 2", date=base_date + timedelta(days=5))
    db.add_all([meal1, meal2, meal3])
    db.commit()

    query = db.query(models.Meal).filter(models.Meal.user_id == filter_user.id)
    query = apply_meal_sorting(query, None)  # Default sort
    results = query.all()

    # NULL date should be first, then dates descending
    assert results[0].name == "No Date"
    assert results[1].name == "With Date 2"  # Later date
    assert results[2].name == "With Date 1"  # Earlier date


def test_apply_meal_sorting_explicit_date(db: Session, filter_user):
    """Test explicit date sorting uses normal null handling."""
    base_date = datetime(2025, 1, 15)
    meal1 = models.Meal(user_id=filter_user.id, name="Early", date=base_date)
    meal2 = models.Meal(user_id=filter_user.id, name="Late", date=base_date + timedelta(days=5))
    db.add_all([meal1, meal2])
    db.commit()

    query = db.query(models.Meal).filter(models.Meal.user_id == filter_user.id)
    query = apply_meal_sorting(query, "-date")  # Explicit descending
    results = query.all()

    assert results[0].name == "Late"
    assert results[1].name == "Early"


# --- Unit Tests for apply_template_filters ---

def test_apply_template_filters_by_name(db: Session, filter_user):
    """Test filtering templates by name."""
    template1 = models.MealTemplate(user_id=filter_user.id, name="Quick Breakfast")
    template2 = models.MealTemplate(user_id=filter_user.id, name="Weekend Dinner")
    db.add_all([template1, template2])
    db.commit()

    query = db.query(models.MealTemplate).filter(models.MealTemplate.user_id == filter_user.id)
    filters_list = [Filter("name", "like", "breakfast")]
    query = apply_template_filters(query, filters_list)
    results = query.all()

    assert len(results) == 1
    assert results[0].name == "Quick Breakfast"


def test_apply_template_filters_by_classification(db: Session, filter_user):
    """Test filtering templates by classification."""
    template1 = models.MealTemplate(
        user_id=filter_user.id,
        name="Breakfast Template",
        classification=models.MealClassification.BREAKFAST
    )
    template2 = models.MealTemplate(
        user_id=filter_user.id,
        name="Dinner Template",
        classification=models.MealClassification.DINNER
    )
    db.add_all([template1, template2])
    db.commit()

    query = db.query(models.MealTemplate).filter(models.MealTemplate.user_id == filter_user.id)
    filters_list = [Filter("classification", "eq", "Breakfast")]
    query = apply_template_filters(query, filters_list)
    results = query.all()

    assert len(results) == 1
    assert results[0].name == "Breakfast Template"


def test_apply_template_filters_by_num_slots(db: Session, filter_user):
    """Test filtering templates by number of slots."""
    template1 = models.MealTemplate(user_id=filter_user.id, name="Single Slot")
    template2 = models.MealTemplate(user_id=filter_user.id, name="Multi Slot")
    db.add_all([template1, template2])
    db.commit()

    # Add slots
    slot1 = models.MealTemplateSlot(
        template_id=template1.id,
        strategy=models.MealTemplateSlotStrategy.SEARCH
    )
    slot2a = models.MealTemplateSlot(
        template_id=template2.id,
        strategy=models.MealTemplateSlotStrategy.SEARCH
    )
    slot2b = models.MealTemplateSlot(
        template_id=template2.id,
        strategy=models.MealTemplateSlotStrategy.SEARCH
    )
    slot2c = models.MealTemplateSlot(
        template_id=template2.id,
        strategy=models.MealTemplateSlotStrategy.SEARCH
    )
    db.add_all([slot1, slot2a, slot2b, slot2c])
    db.commit()

    # Filter for templates with more than 2 slots
    query = db.query(models.MealTemplate).filter(models.MealTemplate.user_id == filter_user.id)
    filters_list = [Filter("num_slots", "gt", "2")]
    query = apply_template_filters(query, filters_list)
    results = query.all()

    assert len(results) == 1
    assert results[0].name == "Multi Slot"


def test_apply_template_filters_by_recipe_direct(db: Session, filter_user):
    """Test filtering templates by associated recipe (DIRECT slot)."""
    recipe1 = create_recipe(db, filter_user.id, "Target Recipe")
    recipe2 = create_recipe(db, filter_user.id, "Other Recipe")

    template1 = models.MealTemplate(user_id=filter_user.id, name="Has Target")
    template2 = models.MealTemplate(user_id=filter_user.id, name="Has Other")
    db.add_all([template1, template2])
    db.commit()

    slot1 = models.MealTemplateSlot(
        template_id=template1.id,
        strategy=models.MealTemplateSlotStrategy.DIRECT,
        recipe_id=recipe1.id
    )
    slot2 = models.MealTemplateSlot(
        template_id=template2.id,
        strategy=models.MealTemplateSlotStrategy.DIRECT,
        recipe_id=recipe2.id
    )
    db.add_all([slot1, slot2])
    db.commit()

    # Filter by recipe ID
    query = db.query(models.MealTemplate).filter(models.MealTemplate.user_id == filter_user.id)
    filters_list = [Filter("recipe", "eq", str(recipe1.id))]
    query = apply_template_filters(query, filters_list)
    results = query.distinct().all()

    assert len(results) == 1
    assert results[0].name == "Has Target"


# --- API Integration Tests ---

def test_api_filter_meals_by_status(client: TestClient, db: Session, filter_user_headers, filter_user):
    """Test filtering meals by status via API."""
    # Create meals
    for status in ["Draft", "Scheduled", "Cooked"]:
        payload = {"name": f"{status} Meal", "status": status, "items": []}
        client.post("/meals/", json=payload, headers=filter_user_headers)

    # Filter for Draft
    response = client.get("/meals/?status[eq]=Draft", headers=filter_user_headers)
    assert response.status_code == 200
    data = response.json()

    assert len(data) == 1
    assert data[0]["name"] == "Draft Meal"


def test_api_filter_meals_by_classification(client: TestClient, db: Session, filter_user_headers, filter_user):
    """Test filtering meals by classification via API."""
    for cls in ["Breakfast", "Lunch", "Dinner"]:
        payload = {"name": f"{cls} Meal", "classification": cls, "items": []}
        client.post("/meals/", json=payload, headers=filter_user_headers)

    response = client.get("/meals/?classification[eq]=Dinner", headers=filter_user_headers)
    assert response.status_code == 200
    data = response.json()

    assert len(data) == 1
    assert data[0]["name"] == "Dinner Meal"


def test_api_filter_meals_by_name_like(client: TestClient, db: Session, filter_user_headers, filter_user):
    """Test filtering meals by name using LIKE via API."""
    payloads = [
        {"name": "Chicken Parmesan", "items": []},
        {"name": "Beef Tacos", "items": []},
        {"name": "Roast Chicken", "items": []},
    ]
    for p in payloads:
        client.post("/meals/", json=p, headers=filter_user_headers)

    response = client.get("/meals/?name[like]=chicken", headers=filter_user_headers)
    assert response.status_code == 200
    data = response.json()

    assert len(data) == 2
    names = [m["name"] for m in data]
    assert "Chicken Parmesan" in names
    assert "Roast Chicken" in names


def test_api_filter_meals_by_date(client: TestClient, db: Session, filter_user_headers, filter_user):
    """Test filtering meals by date range via API."""
    payloads = [
        {"name": "Jan 10 Meal", "date": "2025-01-10T12:00:00", "items": []},
        {"name": "Jan 15 Meal", "date": "2025-01-15T12:00:00", "items": []},
        {"name": "Jan 20 Meal", "date": "2025-01-20T12:00:00", "items": []},
    ]
    for p in payloads:
        client.post("/meals/", json=p, headers=filter_user_headers)

    # Filter for meals between Jan 12 and Jan 18
    response = client.get(
        "/meals/?date[gte]=2025-01-12&date[lte]=2025-01-18",
        headers=filter_user_headers
    )
    assert response.status_code == 200
    data = response.json()

    assert len(data) == 1
    assert data[0]["name"] == "Jan 15 Meal"


def test_api_filter_meals_by_recipe(client: TestClient, db: Session, filter_user_headers, filter_user):
    """Test filtering meals by associated recipe via API."""
    # Create recipes
    recipe1 = create_recipe(db, filter_user.id, "Lasagna")
    recipe2 = create_recipe(db, filter_user.id, "Soup")

    # Create meals with those recipes
    payload1 = {"name": "Italian Night", "items": [{"recipe_id": str(recipe1.id)}]}
    payload2 = {"name": "Comfort Food", "items": [{"recipe_id": str(recipe2.id)}]}
    client.post("/meals/", json=payload1, headers=filter_user_headers)
    client.post("/meals/", json=payload2, headers=filter_user_headers)

    # Filter by recipe name
    response = client.get("/meals/?recipe[like]=lasag", headers=filter_user_headers)
    assert response.status_code == 200
    data = response.json()

    assert len(data) == 1
    assert data[0]["name"] == "Italian Night"


def test_api_filter_meals_compound(client: TestClient, db: Session, filter_user_headers, filter_user):
    """Test compound filtering via API."""
    payloads = [
        {"name": "Draft Dinner", "status": "Draft", "classification": "Dinner", "items": []},
        {"name": "Scheduled Dinner", "status": "Scheduled", "classification": "Dinner", "items": []},
        {"name": "Draft Breakfast", "status": "Draft", "classification": "Breakfast", "items": []},
    ]
    for p in payloads:
        client.post("/meals/", json=p, headers=filter_user_headers)

    response = client.get(
        "/meals/?status[eq]=Draft&classification[eq]=Dinner",
        headers=filter_user_headers
    )
    assert response.status_code == 200
    data = response.json()

    assert len(data) == 1
    assert data[0]["name"] == "Draft Dinner"


def test_api_filter_meals_id_collection(client: TestClient, db: Session, filter_user_headers, filter_user):
    """Test filtering meals by multiple IDs."""
    ids = []
    for name in ["Meal A", "Meal B", "Meal C"]:
        res = client.post(
            "/meals/",
            json={"name": name, "items": []},
            headers=filter_user_headers
        )
        ids.append(res.json()["id"])

    # Filter for first and third meal
    query_ids = f"{ids[0]},{ids[2]}"
    response = client.get(f"/meals/?id[in]={query_ids}", headers=filter_user_headers)
    assert response.status_code == 200
    data = response.json()

    assert len(data) == 2
    returned_ids = [m["id"] for m in data]
    assert ids[0] in returned_ids
    assert ids[2] in returned_ids
    assert ids[1] not in returned_ids


def test_api_meals_default_sort_nulls_first(client: TestClient, db: Session, filter_user_headers, filter_user):
    """Test that default meal sorting puts NULL dates first."""
    payloads = [
        {"name": "With Date 1", "date": "2025-01-10T12:00:00", "items": []},
        {"name": "No Date", "items": []},  # NULL date
        {"name": "With Date 2", "date": "2025-01-20T12:00:00", "items": []},
    ]
    for p in payloads:
        client.post("/meals/", json=p, headers=filter_user_headers)

    # Default sort (no sort param)
    response = client.get("/meals/", headers=filter_user_headers)
    assert response.status_code == 200
    data = response.json()

    # NULL date should be first, then dates descending
    assert data[0]["name"] == "No Date"
    assert data[1]["name"] == "With Date 2"
    assert data[2]["name"] == "With Date 1"


def test_api_meals_explicit_sort_normal_behavior(client: TestClient, db: Session, filter_user_headers, filter_user):
    """Test that explicit sort uses normal null handling."""
    payloads = [
        {"name": "Early", "date": "2025-01-10T12:00:00", "items": []},
        {"name": "Late", "date": "2025-01-20T12:00:00", "items": []},
    ]
    for p in payloads:
        client.post("/meals/", json=p, headers=filter_user_headers)

    # Explicit ascending sort
    response = client.get("/meals/?sort=date", headers=filter_user_headers)
    data = response.json()

    names = [m["name"] for m in data]
    assert names.index("Early") < names.index("Late")


def test_api_filter_templates_by_name(client: TestClient, db: Session, filter_user_headers, filter_user):
    """Test filtering templates by name via API."""
    recipe = create_recipe(db, filter_user.id, "Test Recipe")

    templates = [
        {"name": "Quick Breakfast", "slots": [{"strategy": "Direct", "recipe_id": str(recipe.id)}]},
        {"name": "Weekend Dinner", "slots": [{"strategy": "Direct", "recipe_id": str(recipe.id)}]},
    ]
    for t in templates:
        client.post("/meals/templates", json=t, headers=filter_user_headers)

    response = client.get("/meals/templates?name[like]=breakfast", headers=filter_user_headers)
    assert response.status_code == 200
    data = response.json()

    assert len(data) == 1
    assert data[0]["name"] == "Quick Breakfast"


def test_api_filter_templates_by_classification(client: TestClient, db: Session, filter_user_headers, filter_user):
    """Test filtering templates by classification via API."""
    # Create different recipes to avoid duplicate slot detection
    recipe1 = create_recipe(db, filter_user.id, "Breakfast Recipe")
    recipe2 = create_recipe(db, filter_user.id, "Dinner Recipe")

    templates = [
        {"name": "Breakfast Template", "classification": "Breakfast", "slots": [{"strategy": "Direct", "recipe_id": str(recipe1.id)}]},
        {"name": "Dinner Template", "classification": "Dinner", "slots": [{"strategy": "Direct", "recipe_id": str(recipe2.id)}]},
    ]
    for t in templates:
        res = client.post("/meals/templates", json=t, headers=filter_user_headers)
        assert res.status_code == 201, f"Failed to create template: {res.json()}"

    response = client.get("/meals/templates?classification[eq]=Dinner", headers=filter_user_headers)
    assert response.status_code == 200
    data = response.json()

    assert len(data) == 1
    assert data[0]["name"] == "Dinner Template"


def test_api_filter_templates_by_num_slots_gt(client: TestClient, db: Session, filter_user_headers, filter_user):
    """Test filtering templates by number of slots (greater than) via API."""
    recipe = create_recipe(db, filter_user.id, "Slot Recipe")

    # Single slot template
    template1 = {
        "name": "Single Slot Template",
        "slots": [{"strategy": "Direct", "recipe_id": str(recipe.id)}]
    }
    client.post("/meals/templates", json=template1, headers=filter_user_headers)

    # Multi slot template
    template2 = {
        "name": "Multi Slot Template",
        "slots": [
            {"strategy": "Direct", "recipe_id": str(recipe.id)},
            {"strategy": "Search", "search_criteria": [{"field": "category", "operator": "eq", "value": "Dinner"}]},
            {"strategy": "Search", "search_criteria": [{"field": "difficulty", "operator": "eq", "value": "Easy"}]},
        ]
    }
    client.post("/meals/templates", json=template2, headers=filter_user_headers)

    # Filter for templates with > 2 slots
    response = client.get("/meals/templates?num_slots[gt]=2", headers=filter_user_headers)
    assert response.status_code == 200
    data = response.json()

    assert len(data) == 1
    assert data[0]["name"] == "Multi Slot Template"


def test_api_filter_templates_by_num_slots_lte(client: TestClient, db: Session, filter_user_headers, filter_user):
    """Test filtering templates by number of slots (less than or equal) via API."""
    recipe = create_recipe(db, filter_user.id, "Slot Recipe LTE")

    # Two slot template
    template1 = {
        "name": "Two Slot Template",
        "slots": [
            {"strategy": "Direct", "recipe_id": str(recipe.id)},
            {"strategy": "Search", "search_criteria": [{"field": "category", "operator": "eq", "value": "Dinner"}]},
        ]
    }
    client.post("/meals/templates", json=template1, headers=filter_user_headers)

    # Five slot template
    template2 = {
        "name": "Five Slot Template",
        "slots": [
            {"strategy": "Direct", "recipe_id": str(recipe.id)},
            {"strategy": "Search", "search_criteria": [{"field": "category", "operator": "eq", "value": "Dinner"}]},
            {"strategy": "Search", "search_criteria": [{"field": "category", "operator": "eq", "value": "Lunch"}]},
            {"strategy": "Search", "search_criteria": [{"field": "difficulty", "operator": "eq", "value": "Easy"}]},
            {"strategy": "Search", "search_criteria": [{"field": "difficulty", "operator": "eq", "value": "Medium"}]},
        ]
    }
    client.post("/meals/templates", json=template2, headers=filter_user_headers)

    # Filter for templates with <= 2 slots
    response = client.get("/meals/templates?num_slots[lte]=2", headers=filter_user_headers)
    assert response.status_code == 200
    data = response.json()

    assert len(data) == 1
    assert data[0]["name"] == "Two Slot Template"


def test_api_filter_templates_by_recipe(client: TestClient, db: Session, filter_user_headers, filter_user):
    """Test filtering templates by associated recipe via API."""
    recipe1 = create_recipe(db, filter_user.id, "Target Recipe For Template")
    recipe2 = create_recipe(db, filter_user.id, "Other Recipe For Template")

    template1 = {
        "name": "Has Target",
        "slots": [{"strategy": "Direct", "recipe_id": str(recipe1.id)}]
    }
    template2 = {
        "name": "Has Other",
        "slots": [{"strategy": "Direct", "recipe_id": str(recipe2.id)}]
    }
    client.post("/meals/templates", json=template1, headers=filter_user_headers)
    client.post("/meals/templates", json=template2, headers=filter_user_headers)

    # Filter by recipe ID
    response = client.get(
        f"/meals/templates?recipe[eq]={recipe1.id}",
        headers=filter_user_headers
    )
    assert response.status_code == 200
    data = response.json()

    assert len(data) == 1
    assert data[0]["name"] == "Has Target"


def test_api_filter_templates_by_recipe_like(client: TestClient, db: Session, filter_user_headers, filter_user):
    """Test filtering templates by recipe name using LIKE via API."""
    recipe1 = create_recipe(db, filter_user.id, "Chicken Casserole")
    recipe2 = create_recipe(db, filter_user.id, "Beef Stew")

    template1 = {
        "name": "Chicken Template",
        "slots": [{"strategy": "Direct", "recipe_id": str(recipe1.id)}]
    }
    template2 = {
        "name": "Beef Template",
        "slots": [{"strategy": "Direct", "recipe_id": str(recipe2.id)}]
    }
    client.post("/meals/templates", json=template1, headers=filter_user_headers)
    client.post("/meals/templates", json=template2, headers=filter_user_headers)

    # Filter by recipe name using LIKE
    response = client.get("/meals/templates?recipe[like]=chicken", headers=filter_user_headers)
    assert response.status_code == 200
    data = response.json()

    assert len(data) == 1
    assert data[0]["name"] == "Chicken Template"


def test_api_filter_templates_by_recipe_list_slot(client: TestClient, db: Session, filter_user_headers, filter_user):
    """Test filtering templates by recipe in a LIST slot via API."""
    recipe1 = create_recipe(db, filter_user.id, "List Target Recipe")
    recipe2 = create_recipe(db, filter_user.id, "List Other Recipe")
    recipe3 = create_recipe(db, filter_user.id, "Unrelated Recipe")

    template1 = {
        "name": "Template With List Slot",
        "slots": [{"strategy": "List", "recipe_ids": [str(recipe1.id), str(recipe2.id)]}]
    }
    template2 = {
        "name": "Template Without Target",
        "slots": [{"strategy": "Direct", "recipe_id": str(recipe3.id)}]
    }
    client.post("/meals/templates", json=template1, headers=filter_user_headers)
    client.post("/meals/templates", json=template2, headers=filter_user_headers)

    # Filter by recipe ID that's in a LIST slot
    response = client.get(
        f"/meals/templates?recipe[eq]={recipe1.id}",
        headers=filter_user_headers
    )
    assert response.status_code == 200
    data = response.json()

    assert len(data) == 1
    assert data[0]["name"] == "Template With List Slot"


def test_api_filter_templates_id_collection(client: TestClient, db: Session, filter_user_headers, filter_user):
    """Test filtering templates by multiple IDs."""
    # Create different recipes to avoid duplicate slot detection
    recipes = [create_recipe(db, filter_user.id, f"Collection Recipe {i}") for i in range(3)]

    ids = []
    for i, name in enumerate(["Template A", "Template B", "Template C"]):
        res = client.post(
            "/meals/templates",
            json={"name": name, "slots": [{"strategy": "Direct", "recipe_id": str(recipes[i].id)}]},
            headers=filter_user_headers
        )
        assert res.status_code == 201, f"Failed to create template: {res.json()}"
        ids.append(res.json()["id"])

    # Filter for first and third template
    query_ids = f"{ids[0]},{ids[2]}"
    response = client.get(f"/meals/templates?id[in]={query_ids}", headers=filter_user_headers)
    assert response.status_code == 200
    data = response.json()

    assert len(data) == 2
    returned_ids = [t["id"] for t in data]
    assert ids[0] in returned_ids
    assert ids[2] in returned_ids
    assert ids[1] not in returned_ids


def test_api_meals_total_count_header_with_filter(client: TestClient, db: Session, filter_user_headers, filter_user):
    """Test that X-Total-Count header reflects filtered count."""
    # Create 5 meals, 3 Draft, 2 Scheduled
    for i in range(3):
        client.post("/meals/", json={"name": f"Draft {i}", "status": "Draft", "items": []}, headers=filter_user_headers)
    for i in range(2):
        client.post("/meals/", json={"name": f"Scheduled {i}", "status": "Scheduled", "items": []}, headers=filter_user_headers)

    # Get all meals
    response = client.get("/meals/", headers=filter_user_headers)
    assert response.headers.get("X-Total-Count") == "5"

    # Get only Draft meals
    response = client.get("/meals/?status[eq]=Draft", headers=filter_user_headers)
    assert response.headers.get("X-Total-Count") == "3"


def test_api_templates_total_count_header_with_filter(client: TestClient, db: Session, filter_user_headers, filter_user):
    """Test that X-Total-Count header reflects filtered count for templates."""
    # Create different recipes to avoid duplicate slot detection
    recipes = [create_recipe(db, filter_user.id, f"Count Recipe {i}") for i in range(4)]

    # Create 4 templates, 2 Breakfast, 2 Dinner (each with different recipes)
    for i in range(2):
        res = client.post("/meals/templates", json={
            "name": f"Breakfast {i}",
            "classification": "Breakfast",
            "slots": [{"strategy": "Direct", "recipe_id": str(recipes[i].id)}]
        }, headers=filter_user_headers)
        assert res.status_code == 201, f"Failed to create template: {res.json()}"
    for i in range(2):
        res = client.post("/meals/templates", json={
            "name": f"Dinner {i}",
            "classification": "Dinner",
            "slots": [{"strategy": "Direct", "recipe_id": str(recipes[i + 2].id)}]
        }, headers=filter_user_headers)
        assert res.status_code == 201, f"Failed to create template: {res.json()}"

    # Get all templates
    response = client.get("/meals/templates", headers=filter_user_headers)
    assert response.headers.get("X-Total-Count") == "4"

    # Get only Breakfast templates
    response = client.get("/meals/templates?classification[eq]=Breakfast", headers=filter_user_headers)
    assert response.headers.get("X-Total-Count") == "2"


def test_api_meals_pagination_with_filter(client: TestClient, db: Session, filter_user_headers, filter_user):
    """Test pagination works correctly with filters."""
    # Create 10 Draft meals
    for i in range(10):
        client.post("/meals/", json={"name": f"Draft {i}", "status": "Draft", "items": []}, headers=filter_user_headers)
    # Create 2 Scheduled meals
    for i in range(2):
        client.post("/meals/", json={"name": f"Scheduled {i}", "status": "Scheduled", "items": []}, headers=filter_user_headers)

    # Get first page of Draft meals (limit 5)
    response = client.get("/meals/?status[eq]=Draft&skip=0&limit=5", headers=filter_user_headers)
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 5
    assert response.headers.get("X-Total-Count") == "10"

    # Get second page
    response = client.get("/meals/?status[eq]=Draft&skip=5&limit=5", headers=filter_user_headers)
    data = response.json()
    assert len(data) == 5
