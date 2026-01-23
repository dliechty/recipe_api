from fastapi.testclient import TestClient
from app import crud, schemas
from uuid import uuid4

# --- Helper Functions ---


def get_auth_headers(
    client: TestClient, db, email="user_sorting@example.com", password="password"
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


def create_recipe_with_fields(client, headers, name, category, cuisine):
    data = {
        "core": {"name": name, "category": category, "cuisine": cuisine},
        "times": {},
        "nutrition": {},
        "components": [],
        "instructions": [],
    }
    res = client.post("/recipes/", json=data, headers=headers)
    assert res.status_code == 201
    return res.json()


# --- Tests ---


def test_recipes_sorted_by_name(db):
    """
    Test that crud.get_recipes correctly sorts by name.
    """
    # Create a test user
    # Use a unique email to avoid collision if DB clean failed or parallel
    email = f"sorting_tester_{uuid4()}@example.com"
    user_in = schemas.UserCreate(
        email=email, password="password", first_name="Sorting", last_name="Tester"
    )
    user = crud.create_user(db, user_in)

    # Create recipes in non-alphabetical order
    recipes_data = ["Zucchini Bread", "Apple Pie", "Banana Cake"]

    for name in recipes_data:
        recipe_in = schemas.RecipeCreate(
            core=schemas.RecipeCoreCreate(name=name),
            times=schemas.RecipeTimes(),
            nutrition=schemas.RecipeNutrition(),
            components=[schemas.ComponentCreate(name="Main", ingredients=[])],
            instructions=[],
        )
        crud.create_user_recipe(db=db, recipe=recipe_in, user_id=user.id)

    # Retrieve recipes
    recipes, _ = crud.get_recipes(db=db, skip=0, limit=100, sort_by="name")

    # Check if they are sorted
    # We should filter by this user or just check that among the returned ones, these specific ones are ordered relative to each other?
    # get_recipes returns all. But we can assume for this test we check the ones we created if we want to be strict,
    # but strictly speaking `sort_by="name"` should return everything sorted by name.

    recipe_names = [recipe.name for recipe in recipes]

    # We expect our 3 to be present and in order relative to each other.
    # Simpler: just assert that the whole list is sorted.
    assert recipe_names == sorted(recipe_names), (
        "Recipes should be sorted by name alphabetically"
    )

    # Also verify our specific ones are there
    for name in recipes_data:
        assert name in recipe_names


def test_instruction_ordering_repro(client: TestClient, db):
    """
    Test that instructions are returned in the correct order (by step_number).
    """
    headers = get_auth_headers(client, db, email="order_instr@example.com")

    recipe_data = {
        "core": {"name": "Ordering Test", "yield_amount": 1},
        "times": {},
        "nutrition": {},
        "components": [],
        "instructions": [
            {"step_number": 2, "text": "Step 2"},
            {"step_number": 1, "text": "Step 1"},
            {"step_number": 3, "text": "Step 3"},
        ],
    }

    create_res = client.post("/recipes/", json=recipe_data, headers=headers)
    assert create_res.status_code == 201
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
    assert step_numbers == [1, 2, 3], f"Expected [1, 2, 3] but got {step_numbers}"


def test_multi_field_sorting(client: TestClient, db):
    """
    Test sorting by category and cuisine via API.
    """
    headers = get_auth_headers(client, db, email="sorting_bug_multi@example.com")

    # Create 3 recipes with distinct category/cuisine
    # R1: Cat=C, Cuis=A
    # R2: Cat=A, Cuis=C
    # R3: Cat=B, Cuis=B

    create_recipe_with_fields(client, headers, "R1", "Dessert", "American")
    create_recipe_with_fields(client, headers, "R2", "Appetizer", "Chinese")
    create_recipe_with_fields(client, headers, "R3", "Beverage", "British")

    # Sort by Category (Asc) -> R2 (App), R3 (Bev), R1 (Des)
    res = client.get("/recipes/?sort=category", headers=headers)
    data = res.json()

    # Filter to only the ones we created to avoid noise from other tests
    target_names = {"R1", "R2", "R3"}
    filtered_data = [r for r in data if r["core"]["name"] in target_names]
    names = [r["core"]["name"] for r in filtered_data]

    # We expect R2, R3, R1
    expected = ["R2", "R3", "R1"]
    assert names == expected, (
        f"Sorting by category failed. Expected {expected}, got {names}"
    )

    # Sort by Cuisine (Asc) -> R1 (Amer), R3 (Brit), R2 (Chin)
    res = client.get("/recipes/?sort=cuisine", headers=headers)
    data = res.json()

    filtered_data = [r for r in data if r["core"]["name"] in target_names]
    names = [r["core"]["name"] for r in filtered_data]

    expected = ["R1", "R3", "R2"]
    assert names == expected, (
        f"Sorting by cuisine failed. Expected {expected}, got {names}"
    )
