"""Tests for household integration with the meal system (Phase 5)."""

from app.crud import get_password_hash
from app import models


# --- Helper Functions ---


def create_test_user(db, email, is_admin=False):
    user = models.User(
        email=email,
        hashed_password=get_password_hash("testpassword"),
        is_admin=is_admin,
        is_active=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def get_auth_headers(client, email, password="testpassword"):
    resp = client.post("/auth/token", data={"username": email, "password": password})
    token = resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def create_household_with_member(db, user):
    household = models.Household(name="Test Household", created_by=user.id)
    db.add(household)
    db.flush()
    membership = models.HouseholdMembership(household_id=household.id, user_id=user.id)
    db.add(membership)
    db.commit()
    db.refresh(household)
    return household


def create_recipe(db, user):
    recipe = models.Recipe(name="Test Recipe", owner_id=user.id)
    db.add(recipe)
    db.commit()
    db.refresh(recipe)
    return recipe


def create_template(db, user, recipe):
    template = models.MealTemplate(
        user_id=user.id,
        name="Test Template",
        classification=models.MealClassification.DINNER,
    )
    db.add(template)
    db.commit()
    db.refresh(template)
    slot = models.MealTemplateSlot(
        template_id=template.id,
        strategy=models.MealTemplateSlotStrategy.DIRECT,
        recipe_id=recipe.id,
    )
    db.add(slot)
    db.commit()
    # Compute and set slots_checksum
    from app.api.meals import compute_slots_checksum

    template.slots_checksum = compute_slots_checksum(template.slots)
    db.commit()
    db.refresh(template)
    return template


def create_meal(db, user, household=None, name="Test Meal"):
    meal = models.Meal(
        user_id=user.id,
        name=name,
        status=models.MealStatus.QUEUED,
        classification=models.MealClassification.DINNER,
        queue_position=1,
        household_id=household.id if household else None,
    )
    db.add(meal)
    db.commit()
    db.refresh(meal)
    return meal


# --- 1. Meal list scoping ---


class TestMealListScoping:
    def test_meals_without_household_visible_without_header(self, client, db):
        """Meals with no household_id are visible when no X-Active-Household header is set."""
        user = create_test_user(db, "listscope1@test.com")
        headers = get_auth_headers(client, "listscope1@test.com")
        meal = create_meal(db, user, household=None, name="Personal Meal")

        resp = client.get("/meals/", headers=headers)
        assert resp.status_code == 200
        meal_ids = [m["id"] for m in resp.json()]
        assert str(meal.id) in meal_ids

    def test_meals_with_household_visible_with_header(self, client, db):
        """Meals linked to a household are visible when that household header is set."""
        user = create_test_user(db, "listscope2@test.com")
        headers = get_auth_headers(client, "listscope2@test.com")
        household = create_household_with_member(db, user)
        meal = create_meal(db, user, household=household, name="Household Meal")

        headers["X-Active-Household"] = str(household.id)
        resp = client.get("/meals/", headers=headers)
        assert resp.status_code == 200
        meal_ids = [m["id"] for m in resp.json()]
        assert str(meal.id) in meal_ids

    def test_meals_with_household_not_visible_without_header(self, client, db):
        """Meals linked to a household are NOT visible when no household header is set."""
        user = create_test_user(db, "listscope3@test.com")
        headers = get_auth_headers(client, "listscope3@test.com")
        household = create_household_with_member(db, user)
        create_meal(db, user, household=household, name="Hidden Household Meal")
        personal_meal = create_meal(db, user, household=None, name="Visible Personal")

        resp = client.get("/meals/", headers=headers)
        assert resp.status_code == 200
        meal_ids = [m["id"] for m in resp.json()]
        assert str(personal_meal.id) in meal_ids
        # Household meal should not appear
        assert len(resp.json()) == 1

    def test_personal_meals_not_visible_with_household_header(self, client, db):
        """Personal meals (no household) are NOT visible when household header is set."""
        user = create_test_user(db, "listscope4@test.com")
        headers = get_auth_headers(client, "listscope4@test.com")
        household = create_household_with_member(db, user)
        create_meal(db, user, household=None, name="Personal Meal")
        hh_meal = create_meal(db, user, household=household, name="Household Meal")

        headers["X-Active-Household"] = str(household.id)
        resp = client.get("/meals/", headers=headers)
        assert resp.status_code == 200
        meal_ids = [m["id"] for m in resp.json()]
        assert str(hh_meal.id) in meal_ids
        assert len(resp.json()) == 1


# --- 2. Meal get scoping ---


class TestMealGetScoping:
    def test_get_meal_with_matching_household_header(self, client, db):
        """Can get a meal when the active household matches the meal's household."""
        user = create_test_user(db, "getscope1@test.com")
        headers = get_auth_headers(client, "getscope1@test.com")
        household = create_household_with_member(db, user)
        meal = create_meal(db, user, household=household)

        headers["X-Active-Household"] = str(household.id)
        resp = client.get(f"/meals/{meal.id}", headers=headers)
        assert resp.status_code == 200
        assert resp.json()["id"] == str(meal.id)

    def test_get_meal_fails_with_wrong_household_header(self, client, db):
        """Cannot get a meal when the active household does not match."""
        user = create_test_user(db, "getscope2@test.com")
        headers = get_auth_headers(client, "getscope2@test.com")
        household1 = create_household_with_member(db, user)
        household2 = models.Household(name="Other Household", created_by=user.id)
        db.add(household2)
        db.flush()
        membership2 = models.HouseholdMembership(
            household_id=household2.id, user_id=user.id
        )
        db.add(membership2)
        db.commit()
        db.refresh(household2)

        meal = create_meal(db, user, household=household1)

        headers["X-Active-Household"] = str(household2.id)
        resp = client.get(f"/meals/{meal.id}", headers=headers)
        assert resp.status_code == 403

    def test_get_personal_meal_with_household_header_fails(self, client, db):
        """Cannot get a personal meal (no household) when household header is set."""
        user = create_test_user(db, "getscope3@test.com")
        headers = get_auth_headers(client, "getscope3@test.com")
        household = create_household_with_member(db, user)
        meal = create_meal(db, user, household=None)

        headers["X-Active-Household"] = str(household.id)
        resp = client.get(f"/meals/{meal.id}", headers=headers)
        assert resp.status_code == 403


# --- 3. Meal create with household ---


class TestMealCreateWithHousehold:
    def test_create_meal_with_household_header(self, client, db):
        """Created meal gets household_id when X-Active-Household header is set."""
        user = create_test_user(db, "create1@test.com")
        headers = get_auth_headers(client, "create1@test.com")
        household = create_household_with_member(db, user)

        headers["X-Active-Household"] = str(household.id)
        resp = client.post(
            "/meals/",
            json={
                "name": "Household Dinner",
                "classification": "Dinner",
                "status": "Queued",
            },
            headers=headers,
        )
        assert resp.status_code == 201
        assert resp.json()["household_id"] == str(household.id)

    def test_create_meal_without_household_header(self, client, db):
        """Created meal has no household_id when no header is set."""
        create_test_user(db, "create2@test.com")
        headers = get_auth_headers(client, "create2@test.com")

        resp = client.post(
            "/meals/",
            json={
                "name": "Personal Dinner",
                "classification": "Dinner",
                "status": "Queued",
            },
            headers=headers,
        )
        assert resp.status_code == 201
        assert resp.json()["household_id"] is None


# --- 4. Meal generate with household ---


class TestMealGenerateWithHousehold:
    def test_generated_meals_have_household_id(self, client, db):
        """Generated meals get household_id when X-Active-Household header is set."""
        user = create_test_user(db, "generate1@test.com")
        headers = get_auth_headers(client, "generate1@test.com")
        household = create_household_with_member(db, user)
        recipe = create_recipe(db, user)
        create_template(db, user, recipe)

        headers["X-Active-Household"] = str(household.id)
        resp = client.post(
            "/meals/generate",
            json={"count": 1},
            headers=headers,
        )
        assert resp.status_code == 201
        meals = resp.json()
        assert len(meals) == 1
        assert meals[0]["household_id"] == str(household.id)

    def test_generated_meals_no_household_without_header(self, client, db):
        """Generated meals have no household_id when no header is set."""
        user = create_test_user(db, "generate2@test.com")
        headers = get_auth_headers(client, "generate2@test.com")
        recipe = create_recipe(db, user)
        create_template(db, user, recipe)

        resp = client.post(
            "/meals/generate",
            json={"count": 1},
            headers=headers,
        )
        assert resp.status_code == 201
        meals = resp.json()
        assert len(meals) == 1
        assert meals[0]["household_id"] is None


# --- 5. Template exclusion during generation ---


class TestTemplateExclusionDuringGeneration:
    def test_excluded_templates_skipped_during_generation(self, client, db):
        """Excluded templates are not used for generation with active household."""
        user = create_test_user(db, "exclude1@test.com")
        headers = get_auth_headers(client, "exclude1@test.com")
        household = create_household_with_member(db, user)

        recipe1 = models.Recipe(name="Recipe A", owner_id=user.id)
        recipe2 = models.Recipe(name="Recipe B", owner_id=user.id)
        db.add_all([recipe1, recipe2])
        db.commit()
        db.refresh(recipe1)
        db.refresh(recipe2)

        template1 = create_template(db, user, recipe1)
        # Create second template with different recipe (unique slot config)
        template2 = models.MealTemplate(
            user_id=user.id,
            name="Template B",
            classification=models.MealClassification.LUNCH,
        )
        db.add(template2)
        db.commit()
        db.refresh(template2)
        slot2 = models.MealTemplateSlot(
            template_id=template2.id,
            strategy=models.MealTemplateSlotStrategy.DIRECT,
            recipe_id=recipe2.id,
        )
        db.add(slot2)
        db.commit()
        from app.api.meals import compute_slots_checksum

        template2.slots_checksum = compute_slots_checksum(template2.slots)
        db.commit()
        db.refresh(template2)

        # Exclude template1 from this household
        exclusion = models.HouseholdTemplateExclusion(
            household_id=household.id, template_id=template1.id
        )
        db.add(exclusion)
        db.commit()

        headers["X-Active-Household"] = str(household.id)
        # Generate 2 meals - only template2 should be available
        resp = client.post(
            "/meals/generate",
            json={"count": 2},
            headers=headers,
        )
        assert resp.status_code == 201
        meals = resp.json()
        # Only 1 meal generated because only 1 template is available
        assert len(meals) == 1
        assert meals[0]["name"] == "Template B"

    def test_exclusion_not_applied_without_household(self, client, db):
        """Template exclusions are not applied when no household header is set."""
        user = create_test_user(db, "exclude2@test.com")
        headers = get_auth_headers(client, "exclude2@test.com")
        household = create_household_with_member(db, user)
        recipe = create_recipe(db, user)
        template = create_template(db, user, recipe)

        # Exclude the template from the household
        exclusion = models.HouseholdTemplateExclusion(
            household_id=household.id, template_id=template.id
        )
        db.add(exclusion)
        db.commit()

        # Generate without household header - template should still be available
        resp = client.post(
            "/meals/generate",
            json={"count": 1},
            headers=headers,
        )
        assert resp.status_code == 201
        meals = resp.json()
        assert len(meals) == 1


# --- 6. Household_id patching ---


class TestHouseholdIdPatching:
    def test_assign_meal_to_household(self, client, db):
        """Can assign a meal to a household the user is a member of."""
        user = create_test_user(db, "patch1@test.com")
        headers = get_auth_headers(client, "patch1@test.com")
        household = create_household_with_member(db, user)
        meal = create_meal(db, user, household=None)

        resp = client.put(
            f"/meals/{meal.id}",
            json={"household_id": str(household.id)},
            headers=headers,
        )
        assert resp.status_code == 200
        assert resp.json()["household_id"] == str(household.id)

    def test_unassign_meal_from_household(self, client, db):
        """Can set household_id to null to unassign a meal."""
        user = create_test_user(db, "patch2@test.com")
        headers = get_auth_headers(client, "patch2@test.com")
        household = create_household_with_member(db, user)
        meal = create_meal(db, user, household=household)

        resp = client.put(
            f"/meals/{meal.id}",
            json={"household_id": None},
            headers=headers,
        )
        assert resp.status_code == 200
        assert resp.json()["household_id"] is None

    def test_non_member_cannot_assign_to_household(self, client, db):
        """Cannot assign a meal to a household the user is not a member of."""
        user = create_test_user(db, "patch3@test.com")
        other_user = create_test_user(db, "patch3_other@test.com")
        headers = get_auth_headers(client, "patch3@test.com")
        # Create household with other_user as member, not our user
        household = models.Household(name="Other Household", created_by=other_user.id)
        db.add(household)
        db.flush()
        membership = models.HouseholdMembership(
            household_id=household.id, user_id=other_user.id
        )
        db.add(membership)
        db.commit()
        db.refresh(household)

        meal = create_meal(db, user, household=None)

        resp = client.put(
            f"/meals/{meal.id}",
            json={"household_id": str(household.id)},
            headers=headers,
        )
        assert resp.status_code == 403
        assert "Not a member of the target household" in resp.json()["detail"]

    def test_admin_can_assign_to_any_household(self, client, db):
        """Admin can assign a meal to any household without being a member."""
        admin = create_test_user(db, "patch4_admin@test.com", is_admin=True)
        other_user = create_test_user(db, "patch4_other@test.com")
        admin_headers = get_auth_headers(client, "patch4_admin@test.com")
        household = create_household_with_member(db, other_user)

        meal = create_meal(db, admin, household=None)

        admin_headers["X-Admin-Mode"] = "true"
        resp = client.put(
            f"/meals/{meal.id}",
            json={"household_id": str(household.id)},
            headers=admin_headers,
        )
        assert resp.status_code == 200
        assert resp.json()["household_id"] == str(household.id)
