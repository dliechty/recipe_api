"""Tests for queue positioning, meal generation pipeline, and new filtering (Phase 3)."""

import pytest
from uuid import UUID
from sqlalchemy.orm import Session

from app import models, schemas, crud


@pytest.fixture
def normal_user(db):
    user_data = schemas.UserCreate(
        email="queueuser@example.com",
        password="testpassword",
        first_name="Queue",
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


def create_recipe(db: Session, user_id, name: str, category: str = "Dinner"):
    recipe = models.Recipe(
        name=name,
        owner_id=user_id,
        category=category,
        description="Test",
        instructions=[],
        components=[],
    )
    db.add(recipe)
    db.commit()
    db.refresh(recipe)
    return recipe


def create_template_with_direct_slot(client, headers, db, user_id, name, recipe=None):
    """Helper to create a template with a single DIRECT slot."""
    if recipe is None:
        recipe = create_recipe(db, user_id, f"Recipe for {name}")
    template_data = {
        "name": name,
        "slots": [{"strategy": "Direct", "recipe_id": str(recipe.id)}],
    }
    resp = client.post("/meals/templates", headers=headers, json=template_data)
    assert resp.status_code == 201
    return resp.json()


# --- Queue Positioning Tests ---


class TestQueuePositioning:
    def test_auto_assign_queue_position_on_create(
        self, client, db, normal_user_token_headers, normal_user
    ):
        """Meals created without explicit queue_position get auto-assigned one."""
        recipe = create_recipe(db, normal_user.id, "QPR1")
        meal_data = {
            "name": "Meal 1",
            "items": [{"recipe_id": str(recipe.id)}],
        }
        resp = client.post("/meals/", headers=normal_user_token_headers, json=meal_data)
        assert resp.status_code == 201
        meal1 = resp.json()
        assert meal1["queue_position"] is not None

        # Second meal should get a higher position
        meal_data["name"] = "Meal 2"
        resp = client.post("/meals/", headers=normal_user_token_headers, json=meal_data)
        meal2 = resp.json()
        assert meal2["queue_position"] > meal1["queue_position"]

    def test_explicit_queue_position_respected(
        self, client, db, normal_user_token_headers, normal_user
    ):
        """If queue_position is explicitly provided, use it."""
        recipe = create_recipe(db, normal_user.id, "QPR2")
        meal_data = {
            "name": "Explicit Position",
            "queue_position": 42,
            "items": [{"recipe_id": str(recipe.id)}],
        }
        resp = client.post("/meals/", headers=normal_user_token_headers, json=meal_data)
        assert resp.status_code == 201
        assert resp.json()["queue_position"] == 42

    def test_update_queue_position(
        self, client, db, normal_user_token_headers, normal_user
    ):
        """Queue position can be updated via PUT."""
        recipe = create_recipe(db, normal_user.id, "QPR3")
        meal_data = {
            "name": "Reorder Me",
            "items": [{"recipe_id": str(recipe.id)}],
        }
        resp = client.post("/meals/", headers=normal_user_token_headers, json=meal_data)
        meal_id = resp.json()["id"]

        resp = client.put(
            f"/meals/{meal_id}",
            headers=normal_user_token_headers,
            json={"queue_position": 99},
        )
        assert resp.status_code == 200
        assert resp.json()["queue_position"] == 99


# --- Meal Generation Endpoint Tests ---


class TestMealGeneration:
    def test_generate_n_meals(self, client, db, normal_user_token_headers, normal_user):
        """Generate N meals from N different templates."""
        # Create 3 templates
        for i in range(3):
            create_template_with_direct_slot(
                client,
                normal_user_token_headers,
                db,
                normal_user.id,
                f"Template {i}",
            )

        resp = client.post(
            "/meals/generate",
            headers=normal_user_token_headers,
            json={"count": 3},
        )
        assert resp.status_code == 201
        data = resp.json()
        assert len(data) == 3

        # Each should be queued with a queue position
        for meal in data:
            assert meal["status"] == "Queued"
            assert meal["queue_position"] is not None

    def test_generate_with_scheduled_dates(
        self, client, db, normal_user_token_headers, normal_user
    ):
        """Generate meals with optional scheduled dates."""
        for i in range(2):
            create_template_with_direct_slot(
                client,
                normal_user_token_headers,
                db,
                normal_user.id,
                f"Sched Template {i}",
            )

        resp = client.post(
            "/meals/generate",
            headers=normal_user_token_headers,
            json={
                "count": 2,
                "scheduled_dates": ["2026-03-01", "2026-03-02"],
            },
        )
        assert resp.status_code == 201
        data = resp.json()
        assert len(data) == 2
        # Both should have scheduled dates
        assert data[0]["scheduled_date"] is not None
        assert data[1]["scheduled_date"] is not None

    def test_generate_fewer_templates_than_requested(
        self, client, db, normal_user_token_headers, normal_user
    ):
        """When user has fewer templates than requested count, generate what's available."""
        create_template_with_direct_slot(
            client,
            normal_user_token_headers,
            db,
            normal_user.id,
            "Only Template",
        )

        resp = client.post(
            "/meals/generate",
            headers=normal_user_token_headers,
            json={"count": 5},
        )
        assert resp.status_code == 201
        data = resp.json()
        # Should get at most the number of available templates
        assert len(data) >= 1
        assert len(data) <= 5

    def test_generate_updates_last_used_at(
        self, client, db, normal_user_token_headers, normal_user
    ):
        """Generation should update last_used_at on selected templates."""
        template = create_template_with_direct_slot(
            client,
            normal_user_token_headers,
            db,
            normal_user.id,
            "Track Usage",
        )
        template_id = template["id"]

        db_template = (
            db.query(models.MealTemplate)
            .filter(models.MealTemplate.id == UUID(template_id))
            .first()
        )
        assert db_template.last_used_at is None

        resp = client.post(
            "/meals/generate",
            headers=normal_user_token_headers,
            json={"count": 1},
        )
        assert resp.status_code == 201

        db.expire_all()
        db.refresh(db_template)
        assert db_template.last_used_at is not None

    def test_generate_assigns_sequential_queue_positions(
        self, client, db, normal_user_token_headers, normal_user
    ):
        """Generated meals should get sequential queue positions."""
        for i in range(3):
            create_template_with_direct_slot(
                client,
                normal_user_token_headers,
                db,
                normal_user.id,
                f"Seq Template {i}",
            )

        resp = client.post(
            "/meals/generate",
            headers=normal_user_token_headers,
            json={"count": 3},
        )
        assert resp.status_code == 201
        data = resp.json()
        positions = [m["queue_position"] for m in data]
        # Should be strictly increasing
        assert positions == sorted(positions)
        assert len(set(positions)) == len(positions)  # All unique

    def test_generate_weighted_prefers_stale_templates(
        self, client, db, normal_user_token_headers, normal_user
    ):
        """Templates with older/null last_used_at should be selected more often.

        Test the selection function directly for deterministic results,
        then verify integration through the API.
        """
        from datetime import datetime, timezone
        from app.api.meals import select_templates_weighted

        r1 = create_recipe(db, normal_user.id, "Fresh Recipe")
        r2 = create_recipe(db, normal_user.id, "Stale Recipe")

        create_template_with_direct_slot(
            client,
            normal_user_token_headers,
            db,
            normal_user.id,
            "Fresh Template",
            recipe=r1,
        )
        create_template_with_direct_slot(
            client,
            normal_user_token_headers,
            db,
            normal_user.id,
            "Stale Template",
            recipe=r2,
        )

        # Set up recency: one template used just now, one never used
        templates = (
            db.query(models.MealTemplate)
            .filter(models.MealTemplate.user_id == normal_user.id)
            .all()
        )
        fresh = next(t for t in templates if t.name == "Fresh Template")
        stale = next(t for t in templates if t.name == "Stale Template")
        fresh.last_used_at = datetime.now(timezone.utc)
        stale.last_used_at = None  # Never used
        db.commit()

        # Unit test: run selection 100 times, count picks
        pick_counts = {fresh.id: 0, stale.id: 0}
        for _ in range(100):
            selected = select_templates_weighted(templates, 1)
            pick_counts[selected[0].id] += 1

        # Stale template (weight=365 days) should be picked much more than fresh (weight=~0.01 days)
        assert pick_counts[stale.id] > pick_counts[fresh.id]

        # Integration: generate via API and verify it works
        resp = client.post(
            "/meals/generate",
            headers=normal_user_token_headers,
            json={"count": 2},
        )
        assert resp.status_code == 201
        data = resp.json()
        assert len(data) == 2

    def test_generate_no_templates_returns_empty(
        self, client, db, normal_user_token_headers, normal_user
    ):
        """If user has no templates, generation returns empty list."""
        resp = client.post(
            "/meals/generate",
            headers=normal_user_token_headers,
            json={"count": 3},
        )
        assert resp.status_code == 201
        assert resp.json() == []


# --- Filtering & Sorting Tests ---


class TestFilteringAndSorting:
    def test_filter_by_is_shopped(
        self, client, db, normal_user_token_headers, normal_user
    ):
        recipe = create_recipe(db, normal_user.id, "Filter Recipe")
        # Create shopped meal
        client.post(
            "/meals/",
            headers=normal_user_token_headers,
            json={
                "name": "Shopped Meal",
                "is_shopped": True,
                "items": [{"recipe_id": str(recipe.id)}],
            },
        )
        # Create unshopped meal
        client.post(
            "/meals/",
            headers=normal_user_token_headers,
            json={
                "name": "Unshopped Meal",
                "is_shopped": False,
                "items": [{"recipe_id": str(recipe.id)}],
            },
        )

        # Filter for shopped only
        resp = client.get(
            "/meals/?is_shopped[eq]=true",
            headers=normal_user_token_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert all(m["is_shopped"] is True for m in data)

    def test_sort_by_queue_position(
        self, client, db, normal_user_token_headers, normal_user
    ):
        recipe = create_recipe(db, normal_user.id, "Sort Recipe")
        # Create meals with different positions
        for pos in [3, 1, 2]:
            client.post(
                "/meals/",
                headers=normal_user_token_headers,
                json={
                    "name": f"Meal pos {pos}",
                    "queue_position": pos,
                    "items": [{"recipe_id": str(recipe.id)}],
                },
            )

        resp = client.get(
            "/meals/?sort=queue_position",
            headers=normal_user_token_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        positions = [
            m["queue_position"] for m in data if m["queue_position"] is not None
        ]
        assert positions == sorted(positions)
