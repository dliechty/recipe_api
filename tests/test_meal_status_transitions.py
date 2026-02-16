"""Tests for meal status transitions and recency tracking (Phase 2)."""

import pytest
from uuid import UUID
from sqlalchemy.orm import Session

from app import models, schemas, crud


@pytest.fixture
def normal_user(db):
    user_data = schemas.UserCreate(
        email="statususer@example.com",
        password="testpassword",
        first_name="Status",
        last_name="User",
    )
    return crud.create_user(db, user_data)


@pytest.fixture
def normal_user_token_headers(client, normal_user):
    login_res = client.post(
        "/auth/token",
        data={"username": normal_user.email, "password": "testpassword"},
    )
    token = login_res.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def create_recipe(db: Session, user_id, name: str):
    recipe = models.Recipe(
        name=name,
        owner_id=user_id,
        description="Test",
        instructions=[],
        components=[],
    )
    db.add(recipe)
    db.commit()
    db.refresh(recipe)
    return recipe


def create_meal_with_recipes(db: Session, client, headers, user_id, recipes):
    """Helper to create a meal with recipe items via the API."""
    meal_data = {
        "name": "Test Meal",
        "items": [{"recipe_id": str(r.id)} for r in recipes],
    }
    response = client.post("/meals/", headers=headers, json=meal_data)
    assert response.status_code == 201
    return response.json()


# --- Status Transition Tests ---


class TestValidStatusTransitions:
    def test_queued_to_cooked(self, client, db, normal_user_token_headers, normal_user):
        recipe = create_recipe(db, normal_user.id, "Pasta")
        meal = create_meal_with_recipes(
            db, client, normal_user_token_headers, normal_user.id, [recipe]
        )

        response = client.put(
            f"/meals/{meal['id']}",
            headers=normal_user_token_headers,
            json={"status": "Cooked"},
        )
        assert response.status_code == 200
        assert response.json()["status"] == "Cooked"

    def test_queued_to_cancelled(
        self, client, db, normal_user_token_headers, normal_user
    ):
        recipe = create_recipe(db, normal_user.id, "Salad")
        meal = create_meal_with_recipes(
            db, client, normal_user_token_headers, normal_user.id, [recipe]
        )

        response = client.put(
            f"/meals/{meal['id']}",
            headers=normal_user_token_headers,
            json={"status": "Cancelled"},
        )
        assert response.status_code == 200
        assert response.json()["status"] == "Cancelled"


class TestInvalidStatusTransitions:
    def test_cooked_to_queued(self, client, db, normal_user_token_headers, normal_user):
        recipe = create_recipe(db, normal_user.id, "Soup")
        meal = create_meal_with_recipes(
            db, client, normal_user_token_headers, normal_user.id, [recipe]
        )

        # First transition to cooked
        client.put(
            f"/meals/{meal['id']}",
            headers=normal_user_token_headers,
            json={"status": "Cooked"},
        )

        # Attempt to go back to queued
        response = client.put(
            f"/meals/{meal['id']}",
            headers=normal_user_token_headers,
            json={"status": "Queued"},
        )
        assert response.status_code == 400
        assert "transition" in response.json()["detail"].lower()

    def test_cooked_to_cancelled(
        self, client, db, normal_user_token_headers, normal_user
    ):
        recipe = create_recipe(db, normal_user.id, "Stew")
        meal = create_meal_with_recipes(
            db, client, normal_user_token_headers, normal_user.id, [recipe]
        )

        client.put(
            f"/meals/{meal['id']}",
            headers=normal_user_token_headers,
            json={"status": "Cooked"},
        )

        response = client.put(
            f"/meals/{meal['id']}",
            headers=normal_user_token_headers,
            json={"status": "Cancelled"},
        )
        assert response.status_code == 400

    def test_cancelled_to_cooked(
        self, client, db, normal_user_token_headers, normal_user
    ):
        recipe = create_recipe(db, normal_user.id, "Tacos")
        meal = create_meal_with_recipes(
            db, client, normal_user_token_headers, normal_user.id, [recipe]
        )

        client.put(
            f"/meals/{meal['id']}",
            headers=normal_user_token_headers,
            json={"status": "Cancelled"},
        )

        response = client.put(
            f"/meals/{meal['id']}",
            headers=normal_user_token_headers,
            json={"status": "Cooked"},
        )
        assert response.status_code == 400

    def test_cancelled_to_queued(
        self, client, db, normal_user_token_headers, normal_user
    ):
        recipe = create_recipe(db, normal_user.id, "Curry")
        meal = create_meal_with_recipes(
            db, client, normal_user_token_headers, normal_user.id, [recipe]
        )

        client.put(
            f"/meals/{meal['id']}",
            headers=normal_user_token_headers,
            json={"status": "Cancelled"},
        )

        response = client.put(
            f"/meals/{meal['id']}",
            headers=normal_user_token_headers,
            json={"status": "Queued"},
        )
        assert response.status_code == 400


# --- Recency Tracking: last_cooked_at ---


class TestLastCookedAt:
    def test_last_cooked_at_updates_on_cooked(
        self, client, db, normal_user_token_headers, normal_user
    ):
        """When a meal transitions to cooked, all its recipes get last_cooked_at updated."""
        r1 = create_recipe(db, normal_user.id, "Recipe A")
        r2 = create_recipe(db, normal_user.id, "Recipe B")
        assert r1.last_cooked_at is None
        assert r2.last_cooked_at is None

        meal = create_meal_with_recipes(
            db, client, normal_user_token_headers, normal_user.id, [r1, r2]
        )

        # Transition to cooked
        response = client.put(
            f"/meals/{meal['id']}",
            headers=normal_user_token_headers,
            json={"status": "Cooked"},
        )
        assert response.status_code == 200

        # Verify recipes got updated
        db.expire_all()
        db.refresh(r1)
        db.refresh(r2)
        assert r1.last_cooked_at is not None
        assert r2.last_cooked_at is not None

    def test_last_cooked_at_not_updated_on_cancelled(
        self, client, db, normal_user_token_headers, normal_user
    ):
        """When a meal is cancelled, recipes should NOT get last_cooked_at updated."""
        recipe = create_recipe(db, normal_user.id, "Recipe C")
        meal = create_meal_with_recipes(
            db, client, normal_user_token_headers, normal_user.id, [recipe]
        )

        response = client.put(
            f"/meals/{meal['id']}",
            headers=normal_user_token_headers,
            json={"status": "Cancelled"},
        )
        assert response.status_code == 200

        db.expire_all()
        db.refresh(recipe)
        assert recipe.last_cooked_at is None

    def test_last_cooked_at_updates_to_latest(
        self, client, db, normal_user_token_headers, normal_user
    ):
        """If a recipe is in multiple meals, each cooked transition updates last_cooked_at."""
        recipe = create_recipe(db, normal_user.id, "Recipe D")

        # First meal
        meal1 = create_meal_with_recipes(
            db, client, normal_user_token_headers, normal_user.id, [recipe]
        )
        client.put(
            f"/meals/{meal1['id']}",
            headers=normal_user_token_headers,
            json={"status": "Cooked"},
        )
        db.expire_all()
        db.refresh(recipe)
        first_cooked = recipe.last_cooked_at

        # Second meal with same recipe
        meal2 = create_meal_with_recipes(
            db, client, normal_user_token_headers, normal_user.id, [recipe]
        )
        client.put(
            f"/meals/{meal2['id']}",
            headers=normal_user_token_headers,
            json={"status": "Cooked"},
        )
        db.expire_all()
        db.refresh(recipe)
        assert recipe.last_cooked_at >= first_cooked


# --- Recency Tracking: last_used_at ---


class TestLastUsedAt:
    def test_last_used_at_updates_on_generate(
        self, client, db, normal_user_token_headers, normal_user
    ):
        """When a meal is generated from a template, template.last_used_at is updated."""
        recipe = create_recipe(db, normal_user.id, "Gen Recipe")

        # Create template
        template_data = {
            "name": "Gen Template",
            "slots": [{"strategy": "Direct", "recipe_id": str(recipe.id)}],
        }
        resp = client.post(
            "/meals/templates", headers=normal_user_token_headers, json=template_data
        )
        assert resp.status_code == 201
        template_id = resp.json()["id"]

        # Verify initially null
        db_template = (
            db.query(models.MealTemplate)
            .filter(models.MealTemplate.id == UUID(template_id))
            .first()
        )
        assert db_template.last_used_at is None

        # Generate meal
        resp = client.post(
            "/meals/generate",
            headers=normal_user_token_headers,
            json={"count": 1},
        )
        assert resp.status_code == 201

        db.expire_all()
        db.refresh(db_template)
        assert db_template.last_used_at is not None

    def test_last_used_at_updates_each_generation(
        self, client, db, normal_user_token_headers, normal_user
    ):
        """Each generation updates last_used_at to a newer timestamp."""
        recipe = create_recipe(db, normal_user.id, "Gen Recipe 2")

        template_data = {
            "name": "Gen Template 2",
            "slots": [{"strategy": "Direct", "recipe_id": str(recipe.id)}],
        }
        resp = client.post(
            "/meals/templates", headers=normal_user_token_headers, json=template_data
        )
        template_id = resp.json()["id"]

        # First generation
        client.post(
            "/meals/generate",
            headers=normal_user_token_headers,
            json={"count": 1},
        )
        db_template = (
            db.query(models.MealTemplate)
            .filter(models.MealTemplate.id == UUID(template_id))
            .first()
        )
        db.refresh(db_template)
        first_used = db_template.last_used_at

        # Second generation
        client.post(
            "/meals/generate",
            headers=normal_user_token_headers,
            json={"count": 1},
        )
        db.expire_all()
        db.refresh(db_template)
        assert db_template.last_used_at >= first_used
