from fastapi.testclient import TestClient
from datetime import datetime, timedelta
from app import crud, schemas


def get_auth_headers(
    client: TestClient, db, email="user_meal_sorting@example.com", password="password"
):
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


def test_meals_sorting(client: TestClient, db):
    headers = get_auth_headers(client, db)

    # Get user id
    user = crud.get_user_by_email(db, "user_meal_sorting@example.com")
    user_id = user.id

    # Create a recipe
    recipe_in = schemas.RecipeCreate(
        core=schemas.RecipeCoreCreate(name="Toast"),
        times=schemas.RecipeTimes(),
        nutrition=schemas.RecipeNutrition(),
        components=[],
        instructions=[],
    )
    recipe = crud.create_user_recipe(db, recipe_in, user_id)

    base_date = datetime.now()

    # Create 3 meals
    meals_data = [
        {
            "name": "Meal A",
            "status": "Draft",
            "classification": "Dinner",
            "date": (base_date + timedelta(days=2)).isoformat(),
        },
        {
            "name": "Meal B",
            "status": "Cooked",
            "classification": "Breakfast",
            "date": (base_date + timedelta(days=1)).isoformat(),
        },
        {
            "name": "Meal C",
            "status": "Scheduled",
            "classification": "Lunch",
            "date": (base_date + timedelta(days=3)).isoformat(),
        },
    ]

    for m in meals_data:
        # Create via API
        payload = {
            "name": m["name"],
            "status": m["status"],
            "classification": m["classification"],
            "date": m["date"],
            "items": [{"recipe_id": str(recipe.id)}],
        }
        res = client.post("/meals/", json=payload, headers=headers)
        assert res.status_code == 201

    # 1. Sort by Date Asc
    res = client.get("/meals/?sort=date", headers=headers)
    assert res.status_code == 200
    data = res.json()
    names = [m["name"] for m in data]
    assert names == ["Meal B", "Meal A", "Meal C"], (
        f"Expected B, A, C (Date Asc), got {names}"
    )

    # 2. Sort by Date Desc
    res = client.get("/meals/?sort=-date", headers=headers)
    data = res.json()
    names = [m["name"] for m in data]
    assert names == ["Meal C", "Meal A", "Meal B"], (
        f"Expected C, A, B (Date Desc), got {names}"
    )

    # 3. Sort by Classification (Asc)
    # Breakfast (B), Dinner (A), Lunch (C)
    res = client.get("/meals/?sort=classification", headers=headers)
    data = res.json()
    names = [m["name"] for m in data]
    assert names == ["Meal B", "Meal A", "Meal C"], (
        f"Expected B, A, C (Class Asc), got {names}"
    )

    # 4. Sort by Status (Asc)
    # Cooked (B), Draft (A), Scheduled (C)
    res = client.get("/meals/?sort=status", headers=headers)
    data = res.json()
    names = [m["name"] for m in data]
    assert names == ["Meal B", "Meal A", "Meal C"], (
        f"Expected B, A, C (Status Asc), got {names}"
    )

    # 5. Default Sort (Date Desc with NULL dates first)
    res = client.get("/meals/", headers=headers)
    data = res.json()
    names = [m["name"] for m in data]
    # Default is now Date Desc (with NULL dates at top, but none here)
    # Dates: Meal B (+1 day), Meal A (+2 days), Meal C (+3 days)
    # Descending: C (latest), A, B (earliest)
    assert names == ["Meal C", "Meal A", "Meal B"], (
        f"Expected C, A, B (Default Date Desc), got {names}"
    )
