"""Tests for meal plan generation and management."""
import pytest
from datetime import datetime, timedelta
from uuid import UUID
from app import models, schemas, crud
from app.services import meal_planning
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session


@pytest.fixture
def normal_user(db):
    user_data = schemas.UserCreate(
        email="planuser@example.com",
        password="testpassword",
        first_name="Plan",
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


def create_recipe(
    db: Session,
    user_id,
    name: str,
    category: str = "Dinner",
    protein: str = None,
    cuisine: str = None,
    difficulty: models.DifficultyLevel = None,
    total_time_minutes: int = None
):
    """Helper to create a recipe with various attributes."""
    recipe = models.Recipe(
        name=name,
        owner_id=user_id,
        category=category,
        protein=protein,
        cuisine=cuisine,
        difficulty=difficulty,
        total_time_minutes=total_time_minutes,
        description="Test description",
        instructions=[],
        components=[]
    )
    db.add(recipe)
    db.commit()
    db.refresh(recipe)
    return recipe


def create_cooked_meal(
    db: Session,
    user_id,
    recipe,
    cooked_date: datetime
):
    """Helper to create a meal with COOKED status for freshness testing."""
    meal = models.Meal(
        user_id=user_id,
        name=f"Cooked {recipe.name}",
        status=models.MealStatus.COOKED,
        classification=models.MealClassification.DINNER,
        date=cooked_date
    )
    db.add(meal)
    db.commit()
    db.refresh(meal)

    item = models.MealItem(
        meal_id=meal.id,
        recipe_id=recipe.id
    )
    db.add(item)
    db.commit()
    return meal


class TestMealPlanCreation:
    """Tests for meal plan creation and generation."""

    def test_create_meal_plan_basic(
        self, client: TestClient, db: Session,
        normal_user_token_headers, normal_user
    ):
        """Test creating a basic meal plan."""
        # Create some recipes
        r1 = create_recipe(db, normal_user.id, "Recipe 1")
        r2 = create_recipe(db, normal_user.id, "Recipe 2")
        r3 = create_recipe(db, normal_user.id, "Recipe 3")

        plan_data = {
            "start_date": "2026-01-20T00:00:00",
            "end_date": "2026-01-22T00:00:00",
            "meals_per_day": {"Dinner": 1}
        }

        response = client.post(
            "/meals/plans",
            headers=normal_user_token_headers,
            json=plan_data
        )

        assert response.status_code == 201
        data = response.json()
        assert data["status"] == "Draft"
        assert "Week of Jan 20, 2026" in data["name"]
        assert len(data["meals"]) == 3  # 3 days * 1 meal

    def test_create_meal_plan_multiple_meals_per_day(
        self, client: TestClient, db: Session,
        normal_user_token_headers, normal_user
    ):
        """Test creating a plan with multiple meals per day."""
        for i in range(5):
            create_recipe(db, normal_user.id, f"Recipe {i}")

        plan_data = {
            "start_date": "2026-01-20T00:00:00",
            "end_date": "2026-01-21T00:00:00",
            "meals_per_day": {"Lunch": 1, "Dinner": 1}
        }

        response = client.post(
            "/meals/plans",
            headers=normal_user_token_headers,
            json=plan_data
        )

        assert response.status_code == 201
        data = response.json()
        # 2 days * 2 meals = 4
        assert len(data["meals"]) == 4

    def test_create_meal_plan_with_custom_name(
        self, client: TestClient, db: Session,
        normal_user_token_headers, normal_user
    ):
        """Test creating a plan with a custom name."""
        create_recipe(db, normal_user.id, "Recipe 1")

        plan_data = {
            "name": "My Custom Plan",
            "start_date": "2026-01-20T00:00:00",
            "end_date": "2026-01-20T00:00:00",
            "meals_per_day": {"Dinner": 1}
        }

        response = client.post(
            "/meals/plans",
            headers=normal_user_token_headers,
            json=plan_data
        )

        assert response.status_code == 201
        assert response.json()["name"] == "My Custom Plan"

    def test_create_meal_plan_with_pinned_meals(
        self, client: TestClient, db: Session,
        normal_user_token_headers, normal_user
    ):
        """Test creating a plan with pinned meals."""
        pinned_recipe = create_recipe(db, normal_user.id, "Pinned Recipe")
        other_recipe = create_recipe(db, normal_user.id, "Other Recipe")

        plan_data = {
            "start_date": "2026-01-20T00:00:00",
            "end_date": "2026-01-21T00:00:00",
            "meals_per_day": {"Dinner": 1},
            "pinned_meals": [
                {
                    "date": "2026-01-20T00:00:00",
                    "classification": "Dinner",
                    "recipe_id": str(pinned_recipe.id)
                }
            ]
        }

        response = client.post(
            "/meals/plans",
            headers=normal_user_token_headers,
            json=plan_data
        )

        assert response.status_code == 201
        data = response.json()
        meals = data["meals"]

        # Find the pinned meal
        pinned_meal = next(
            m for m in meals
            if m["date"].startswith("2026-01-20")
        )
        assert pinned_meal["pinned"] is True

    def test_create_meal_plan_invalid_date_range(
        self, client: TestClient, db: Session,
        normal_user_token_headers, normal_user
    ):
        """Test that end_date before start_date is rejected."""
        plan_data = {
            "start_date": "2026-01-22T00:00:00",
            "end_date": "2026-01-20T00:00:00",
            "meals_per_day": {"Dinner": 1}
        }

        response = client.post(
            "/meals/plans",
            headers=normal_user_token_headers,
            json=plan_data
        )

        assert response.status_code == 422

    def test_create_meal_plan_invalid_classification(
        self, client: TestClient, db: Session,
        normal_user_token_headers, normal_user
    ):
        """Test that invalid meal classification is rejected."""
        plan_data = {
            "start_date": "2026-01-20T00:00:00",
            "end_date": "2026-01-20T00:00:00",
            "meals_per_day": {"InvalidMeal": 1}
        }

        response = client.post(
            "/meals/plans",
            headers=normal_user_token_headers,
            json=plan_data
        )

        assert response.status_code == 422


class TestMealPlanConstraints:
    """Tests for meal plan constraints."""

    def test_constraint_max_difficulty(
        self, client: TestClient, db: Session,
        normal_user_token_headers, normal_user
    ):
        """Test that max_difficulty constraint filters recipes."""
        easy_recipe = create_recipe(
            db, normal_user.id, "Easy Recipe",
            difficulty=models.DifficultyLevel.EASY
        )
        hard_recipe = create_recipe(
            db, normal_user.id, "Hard Recipe",
            difficulty=models.DifficultyLevel.HARD
        )

        plan_data = {
            "start_date": "2026-01-20T00:00:00",
            "end_date": "2026-01-20T00:00:00",
            "meals_per_day": {"Dinner": 1},
            "config": {
                "constraints": {
                    "max_difficulty": "Easy"
                }
            }
        }

        response = client.post(
            "/meals/plans",
            headers=normal_user_token_headers,
            json=plan_data
        )

        assert response.status_code == 201
        meals = response.json()["meals"]
        if meals and meals[0]["items"]:
            # Should only select easy recipe
            assert meals[0]["items"][0]["recipe_id"] == str(easy_recipe.id)

    def test_constraint_max_total_time(
        self, client: TestClient, db: Session,
        normal_user_token_headers, normal_user
    ):
        """Test that max_total_time_minutes constraint filters recipes."""
        quick_recipe = create_recipe(
            db, normal_user.id, "Quick Recipe",
            total_time_minutes=30
        )
        slow_recipe = create_recipe(
            db, normal_user.id, "Slow Recipe",
            total_time_minutes=120
        )

        plan_data = {
            "start_date": "2026-01-20T00:00:00",
            "end_date": "2026-01-20T00:00:00",
            "meals_per_day": {"Dinner": 1},
            "config": {
                "constraints": {
                    "max_total_time_minutes": 60
                }
            }
        }

        response = client.post(
            "/meals/plans",
            headers=normal_user_token_headers,
            json=plan_data
        )

        assert response.status_code == 201
        meals = response.json()["meals"]
        if meals and meals[0]["items"]:
            assert meals[0]["items"][0]["recipe_id"] == str(quick_recipe.id)

    def test_constraint_excluded_proteins(
        self, client: TestClient, db: Session,
        normal_user_token_headers, normal_user
    ):
        """Test that excluded_proteins constraint filters recipes."""
        chicken_recipe = create_recipe(
            db, normal_user.id, "Chicken Dish",
            protein="Chicken"
        )
        beef_recipe = create_recipe(
            db, normal_user.id, "Beef Dish",
            protein="Beef"
        )

        plan_data = {
            "start_date": "2026-01-20T00:00:00",
            "end_date": "2026-01-20T00:00:00",
            "meals_per_day": {"Dinner": 1},
            "config": {
                "constraints": {
                    "excluded_proteins": ["Chicken"]
                }
            }
        }

        response = client.post(
            "/meals/plans",
            headers=normal_user_token_headers,
            json=plan_data
        )

        assert response.status_code == 201
        meals = response.json()["meals"]
        if meals and meals[0]["items"]:
            # Should only select beef recipe
            assert meals[0]["items"][0]["recipe_id"] == str(beef_recipe.id)


class TestFreshnessScoring:
    """Tests for the freshness scoring algorithm."""

    def test_freshness_prefers_uncooked_recipes(
        self, client: TestClient, db: Session,
        normal_user_token_headers, normal_user
    ):
        """Test that recipes not recently cooked are preferred."""
        # Create two recipes
        fresh_recipe = create_recipe(db, normal_user.id, "Fresh Recipe")
        stale_recipe = create_recipe(db, normal_user.id, "Stale Recipe")

        # Mark stale_recipe as cooked yesterday
        yesterday = datetime.now() - timedelta(days=1)
        create_cooked_meal(db, normal_user.id, stale_recipe, yesterday)

        plan_data = {
            "start_date": "2026-01-20T00:00:00",
            "end_date": "2026-01-20T00:00:00",
            "meals_per_day": {"Dinner": 1},
            "config": {
                "scoring_weights": {
                    "freshness_weight": 0.9,
                    "variety_weight": 0.0,
                    "random_weight": 0.1
                }
            }
        }

        response = client.post(
            "/meals/plans",
            headers=normal_user_token_headers,
            json=plan_data
        )

        assert response.status_code == 201
        meals = response.json()["meals"]
        if meals and meals[0]["items"]:
            # Fresh recipe should be preferred
            assert meals[0]["items"][0]["recipe_id"] == str(fresh_recipe.id)

    def test_freshness_score_calculation(self, db: Session, normal_user):
        """Test the freshness score calculation directly."""
        recipe = create_recipe(db, normal_user.id, "Test Recipe")

        # Never cooked = 1.0
        score = meal_planning.calculate_freshness_score(
            recipe.id, {}, freshness_window_days=30
        )
        assert score == 1.0

        # Cooked 15 days ago = 0.5
        cooked_date = datetime.now() - timedelta(days=15)
        score = meal_planning.calculate_freshness_score(
            recipe.id, {recipe.id: cooked_date}, freshness_window_days=30
        )
        assert 0.4 <= score <= 0.6

        # Cooked 30+ days ago = 1.0
        old_date = datetime.now() - timedelta(days=35)
        score = meal_planning.calculate_freshness_score(
            recipe.id, {recipe.id: old_date}, freshness_window_days=30
        )
        assert score == 1.0


class TestVarietyScoring:
    """Tests for the variety scoring algorithm."""

    def test_variety_penalizes_same_protein(self, db: Session, normal_user):
        """Test that same protein reduces variety score."""
        chicken1 = create_recipe(
            db, normal_user.id, "Chicken 1", protein="Chicken"
        )
        chicken2 = create_recipe(
            db, normal_user.id, "Chicken 2", protein="Chicken"
        )

        score = meal_planning.calculate_variety_score(
            chicken2, [chicken1]
        )
        # Should have penalty for same protein (0.4)
        assert score <= 0.6

    def test_variety_penalizes_same_cuisine(self, db: Session, normal_user):
        """Test that same cuisine reduces variety score."""
        italian1 = create_recipe(
            db, normal_user.id, "Italian 1", cuisine="Italian"
        )
        italian2 = create_recipe(
            db, normal_user.id, "Italian 2", cuisine="Italian"
        )

        score = meal_planning.calculate_variety_score(
            italian2, [italian1]
        )
        # Should have penalty for same cuisine (0.25)
        assert score <= 0.75

    def test_variety_prefers_different_attributes(self, db: Session, normal_user):
        """Test that different attributes get high variety score."""
        chicken_italian = create_recipe(
            db, normal_user.id, "Chicken Italian",
            protein="Chicken", cuisine="Italian", category="Pasta"
        )
        beef_mexican = create_recipe(
            db, normal_user.id, "Beef Mexican",
            protein="Beef", cuisine="Mexican", category="Tacos"
        )

        score = meal_planning.calculate_variety_score(
            beef_mexican, [chicken_italian]
        )
        # Should have high variety (no penalties)
        assert score == 1.0


class TestMealPlanManagement:
    """Tests for meal plan CRUD operations."""

    def test_list_meal_plans(
        self, client: TestClient, db: Session,
        normal_user_token_headers, normal_user
    ):
        """Test listing meal plans."""
        create_recipe(db, normal_user.id, "Recipe")

        # Create two plans
        for i in range(2):
            client.post(
                "/meals/plans",
                headers=normal_user_token_headers,
                json={
                    "name": f"Plan {i}",
                    "start_date": "2026-01-20T00:00:00",
                    "end_date": "2026-01-20T00:00:00",
                    "meals_per_day": {"Dinner": 1}
                }
            )

        response = client.get(
            "/meals/plans",
            headers=normal_user_token_headers
        )

        assert response.status_code == 200
        assert len(response.json()) == 2
        assert "X-Total-Count" in response.headers

    def test_get_meal_plan(
        self, client: TestClient, db: Session,
        normal_user_token_headers, normal_user
    ):
        """Test getting a single meal plan."""
        create_recipe(db, normal_user.id, "Recipe")

        create_response = client.post(
            "/meals/plans",
            headers=normal_user_token_headers,
            json={
                "start_date": "2026-01-20T00:00:00",
                "end_date": "2026-01-20T00:00:00",
                "meals_per_day": {"Dinner": 1}
            }
        )
        plan_id = create_response.json()["id"]

        response = client.get(
            f"/meals/plans/{plan_id}",
            headers=normal_user_token_headers
        )

        assert response.status_code == 200
        assert response.json()["id"] == plan_id

    def test_get_meal_plan_not_found(
        self, client: TestClient, db: Session,
        normal_user_token_headers
    ):
        """Test getting a non-existent meal plan."""
        fake_id = "00000000-0000-0000-0000-000000000000"
        response = client.get(
            f"/meals/plans/{fake_id}",
            headers=normal_user_token_headers
        )

        assert response.status_code == 404

    def test_update_meal_plan(
        self, client: TestClient, db: Session,
        normal_user_token_headers, normal_user
    ):
        """Test updating a meal plan."""
        create_recipe(db, normal_user.id, "Recipe")

        create_response = client.post(
            "/meals/plans",
            headers=normal_user_token_headers,
            json={
                "start_date": "2026-01-20T00:00:00",
                "end_date": "2026-01-20T00:00:00",
                "meals_per_day": {"Dinner": 1}
            }
        )
        plan_id = create_response.json()["id"]

        response = client.put(
            f"/meals/plans/{plan_id}",
            headers=normal_user_token_headers,
            json={"name": "Updated Name"}
        )

        assert response.status_code == 200
        assert response.json()["name"] == "Updated Name"

    def test_delete_meal_plan(
        self, client: TestClient, db: Session,
        normal_user_token_headers, normal_user
    ):
        """Test deleting a meal plan."""
        create_recipe(db, normal_user.id, "Recipe")

        create_response = client.post(
            "/meals/plans",
            headers=normal_user_token_headers,
            json={
                "start_date": "2026-01-20T00:00:00",
                "end_date": "2026-01-20T00:00:00",
                "meals_per_day": {"Dinner": 1}
            }
        )
        plan_id = create_response.json()["id"]

        response = client.delete(
            f"/meals/plans/{plan_id}",
            headers=normal_user_token_headers
        )

        assert response.status_code == 204

        # Verify deletion
        get_response = client.get(
            f"/meals/plans/{plan_id}",
            headers=normal_user_token_headers
        )
        assert get_response.status_code == 404


class TestMealPlanFinalization:
    """Tests for meal plan finalization."""

    def test_finalize_meal_plan(
        self, client: TestClient, db: Session,
        normal_user_token_headers, normal_user
    ):
        """Test finalizing a meal plan."""
        create_recipe(db, normal_user.id, "Recipe")

        create_response = client.post(
            "/meals/plans",
            headers=normal_user_token_headers,
            json={
                "start_date": "2026-01-20T00:00:00",
                "end_date": "2026-01-20T00:00:00",
                "meals_per_day": {"Dinner": 1}
            }
        )
        plan_id = create_response.json()["id"]

        response = client.post(
            f"/meals/plans/{plan_id}/finalize",
            headers=normal_user_token_headers
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "Finalized"
        # All meals should be SCHEDULED
        for meal in data["meals"]:
            assert meal["status"] == "Scheduled"

    def test_cannot_modify_finalized_plan(
        self, client: TestClient, db: Session,
        normal_user_token_headers, normal_user
    ):
        """Test that finalized plans cannot be modified."""
        create_recipe(db, normal_user.id, "Recipe")

        create_response = client.post(
            "/meals/plans",
            headers=normal_user_token_headers,
            json={
                "start_date": "2026-01-20T00:00:00",
                "end_date": "2026-01-20T00:00:00",
                "meals_per_day": {"Dinner": 1}
            }
        )
        plan_id = create_response.json()["id"]

        # Finalize
        client.post(
            f"/meals/plans/{plan_id}/finalize",
            headers=normal_user_token_headers
        )

        # Try to update
        response = client.put(
            f"/meals/plans/{plan_id}",
            headers=normal_user_token_headers,
            json={"name": "New Name"}
        )

        assert response.status_code == 400


class TestMealRegeneration:
    """Tests for regenerating individual meals."""

    def test_regenerate_meal(
        self, client: TestClient, db: Session,
        normal_user_token_headers, normal_user
    ):
        """Test regenerating a single meal."""
        r1 = create_recipe(db, normal_user.id, "Recipe 1")
        r2 = create_recipe(db, normal_user.id, "Recipe 2")

        create_response = client.post(
            "/meals/plans",
            headers=normal_user_token_headers,
            json={
                "start_date": "2026-01-20T00:00:00",
                "end_date": "2026-01-20T00:00:00",
                "meals_per_day": {"Dinner": 1}
            }
        )
        plan_id = create_response.json()["id"]
        meal_id = create_response.json()["meals"][0]["id"]
        original_recipe_id = create_response.json()["meals"][0]["items"][0]["recipe_id"]

        response = client.post(
            f"/meals/plans/{plan_id}/meals/{meal_id}/regenerate",
            headers=normal_user_token_headers
        )

        assert response.status_code == 200
        # Should have a different recipe (or same if only one available)
        new_recipe_id = response.json()["items"][0]["recipe_id"]
        # With only 2 recipes, it should select the other one
        assert new_recipe_id != original_recipe_id

    def test_cannot_regenerate_pinned_meal(
        self, client: TestClient, db: Session,
        normal_user_token_headers, normal_user
    ):
        """Test that pinned meals cannot be regenerated."""
        recipe = create_recipe(db, normal_user.id, "Recipe")

        create_response = client.post(
            "/meals/plans",
            headers=normal_user_token_headers,
            json={
                "start_date": "2026-01-20T00:00:00",
                "end_date": "2026-01-20T00:00:00",
                "meals_per_day": {"Dinner": 1},
                "pinned_meals": [{
                    "date": "2026-01-20T00:00:00",
                    "classification": "Dinner",
                    "recipe_id": str(recipe.id)
                }]
            }
        )
        plan_id = create_response.json()["id"]
        meal_id = create_response.json()["meals"][0]["id"]

        response = client.post(
            f"/meals/plans/{plan_id}/meals/{meal_id}/regenerate",
            headers=normal_user_token_headers
        )

        assert response.status_code == 400
        assert "pinned" in response.json()["detail"].lower()

    def test_cannot_regenerate_in_finalized_plan(
        self, client: TestClient, db: Session,
        normal_user_token_headers, normal_user
    ):
        """Test that meals in finalized plans cannot be regenerated."""
        create_recipe(db, normal_user.id, "Recipe")

        create_response = client.post(
            "/meals/plans",
            headers=normal_user_token_headers,
            json={
                "start_date": "2026-01-20T00:00:00",
                "end_date": "2026-01-20T00:00:00",
                "meals_per_day": {"Dinner": 1}
            }
        )
        plan_id = create_response.json()["id"]
        meal_id = create_response.json()["meals"][0]["id"]

        # Finalize
        client.post(
            f"/meals/plans/{plan_id}/finalize",
            headers=normal_user_token_headers
        )

        response = client.post(
            f"/meals/plans/{plan_id}/meals/{meal_id}/regenerate",
            headers=normal_user_token_headers
        )

        assert response.status_code == 400
        assert "finalized" in response.json()["detail"].lower()


class TestMealPinning:
    """Tests for pinning and unpinning meals."""

    def test_pin_meal(
        self, client: TestClient, db: Session,
        normal_user_token_headers, normal_user
    ):
        """Test pinning a meal."""
        create_recipe(db, normal_user.id, "Recipe")

        create_response = client.post(
            "/meals/plans",
            headers=normal_user_token_headers,
            json={
                "start_date": "2026-01-20T00:00:00",
                "end_date": "2026-01-20T00:00:00",
                "meals_per_day": {"Dinner": 1}
            }
        )
        plan_id = create_response.json()["id"]
        meal_id = create_response.json()["meals"][0]["id"]

        response = client.post(
            f"/meals/plans/{plan_id}/meals/{meal_id}/pin",
            headers=normal_user_token_headers
        )

        assert response.status_code == 200
        assert response.json()["pinned"] is True

    def test_pin_meal_with_recipe_swap(
        self, client: TestClient, db: Session,
        normal_user_token_headers, normal_user
    ):
        """Test pinning a meal and swapping to a specific recipe."""
        r1 = create_recipe(db, normal_user.id, "Recipe 1")
        r2 = create_recipe(db, normal_user.id, "Recipe 2")

        create_response = client.post(
            "/meals/plans",
            headers=normal_user_token_headers,
            json={
                "start_date": "2026-01-20T00:00:00",
                "end_date": "2026-01-20T00:00:00",
                "meals_per_day": {"Dinner": 1}
            }
        )
        plan_id = create_response.json()["id"]
        meal_id = create_response.json()["meals"][0]["id"]
        original_recipe_id = create_response.json()["meals"][0]["items"][0]["recipe_id"]

        # Determine which recipe to swap to
        swap_to = r2.id if str(r1.id) == original_recipe_id else r1.id

        response = client.post(
            f"/meals/plans/{plan_id}/meals/{meal_id}/pin?recipe_id={swap_to}",
            headers=normal_user_token_headers
        )

        assert response.status_code == 200
        assert response.json()["pinned"] is True
        assert response.json()["items"][0]["recipe_id"] == str(swap_to)

    def test_unpin_meal(
        self, client: TestClient, db: Session,
        normal_user_token_headers, normal_user
    ):
        """Test unpinning a meal."""
        recipe = create_recipe(db, normal_user.id, "Recipe")

        create_response = client.post(
            "/meals/plans",
            headers=normal_user_token_headers,
            json={
                "start_date": "2026-01-20T00:00:00",
                "end_date": "2026-01-20T00:00:00",
                "meals_per_day": {"Dinner": 1},
                "pinned_meals": [{
                    "date": "2026-01-20T00:00:00",
                    "classification": "Dinner",
                    "recipe_id": str(recipe.id)
                }]
            }
        )
        plan_id = create_response.json()["id"]
        meal_id = create_response.json()["meals"][0]["id"]

        response = client.post(
            f"/meals/plans/{plan_id}/meals/{meal_id}/unpin",
            headers=normal_user_token_headers
        )

        assert response.status_code == 200
        assert response.json()["pinned"] is False


class TestMealPlanScores:
    """Tests for meal plan scoring endpoint."""

    def test_get_meal_plan_with_scores(
        self, client: TestClient, db: Session,
        normal_user_token_headers, normal_user
    ):
        """Test getting a meal plan with scoring information."""
        create_recipe(db, normal_user.id, "Recipe")

        create_response = client.post(
            "/meals/plans",
            headers=normal_user_token_headers,
            json={
                "start_date": "2026-01-20T00:00:00",
                "end_date": "2026-01-20T00:00:00",
                "meals_per_day": {"Dinner": 1}
            }
        )
        plan_id = create_response.json()["id"]

        response = client.get(
            f"/meals/plans/{plan_id}/scores",
            headers=normal_user_token_headers
        )

        assert response.status_code == 200
        data = response.json()
        assert "meals" in data
        if data["meals"]:
            meal_with_score = data["meals"][0]
            assert "freshness_score" in meal_with_score
            assert "variety_score" in meal_with_score
            assert "combined_score" in meal_with_score


class TestScoringWeightsValidation:
    """Tests for scoring weights validation."""

    def test_invalid_weights_sum(
        self, client: TestClient, db: Session,
        normal_user_token_headers, normal_user
    ):
        """Test that weights not summing to 1.0 are rejected."""
        create_recipe(db, normal_user.id, "Recipe")

        plan_data = {
            "start_date": "2026-01-20T00:00:00",
            "end_date": "2026-01-20T00:00:00",
            "meals_per_day": {"Dinner": 1},
            "config": {
                "scoring_weights": {
                    "freshness_weight": 0.5,
                    "variety_weight": 0.5,
                    "random_weight": 0.5  # Total = 1.5
                }
            }
        }

        response = client.post(
            "/meals/plans",
            headers=normal_user_token_headers,
            json=plan_data
        )

        assert response.status_code == 422

    def test_valid_weights(
        self, client: TestClient, db: Session,
        normal_user_token_headers, normal_user
    ):
        """Test that valid weights are accepted."""
        create_recipe(db, normal_user.id, "Recipe")

        plan_data = {
            "start_date": "2026-01-20T00:00:00",
            "end_date": "2026-01-20T00:00:00",
            "meals_per_day": {"Dinner": 1},
            "config": {
                "scoring_weights": {
                    "freshness_weight": 0.6,
                    "variety_weight": 0.3,
                    "random_weight": 0.1
                }
            }
        }

        response = client.post(
            "/meals/plans",
            headers=normal_user_token_headers,
            json=plan_data
        )

        assert response.status_code == 201
