"""Tests for Household, HouseholdMembership, and HouseholdTemplateExclusion models."""

import uuid

import pytest
from sqlalchemy.exc import IntegrityError

from app.models import (
    Household,
    HouseholdMembership,
    HouseholdTemplateExclusion,
    Meal,
    MealTemplate,
    User,
)


def _create_user(db, email="test@example.com"):
    user = User(
        id=uuid.uuid4(),
        email=email,
        hashed_password="fakehash",
        is_admin=False,
        is_active=True,
    )
    db.add(user)
    db.flush()
    return user


def _create_household(db, user, name="Test Household"):
    household = Household(
        id=uuid.uuid4(),
        name=name,
        created_by=user.id,
    )
    db.add(household)
    db.flush()
    return household


def _create_template(db, user):
    template = MealTemplate(
        id=uuid.uuid4(),
        user_id=user.id,
        name="Test Template",
    )
    db.add(template)
    db.flush()
    return template


class TestHousehold:
    def test_create_household(self, db):
        user = _create_user(db)
        household = _create_household(db, user)

        assert household.id is not None
        assert household.name == "Test Household"
        assert household.created_by == user.id
        assert household.creator.id == user.id

    def test_household_timestamps(self, db):
        user = _create_user(db)
        household = _create_household(db, user)

        # created_at and updated_at are set by default func.now();
        # in SQLite with in-memory they may be None until commit,
        # but the columns exist on the model.
        assert hasattr(household, "created_at")
        assert hasattr(household, "updated_at")


class TestHouseholdMembership:
    def test_create_membership(self, db):
        user = _create_user(db)
        household = _create_household(db, user)

        membership = HouseholdMembership(
            id=uuid.uuid4(),
            household_id=household.id,
            user_id=user.id,
            is_primary=True,
        )
        db.add(membership)
        db.flush()

        assert membership.id is not None
        assert membership.household_id == household.id
        assert membership.user_id == user.id
        assert membership.is_primary is True
        assert membership.household.id == household.id
        assert membership.user.id == user.id

    def test_membership_default_is_primary_false(self, db):
        user = _create_user(db)
        household = _create_household(db, user)

        membership = HouseholdMembership(
            id=uuid.uuid4(),
            household_id=household.id,
            user_id=user.id,
        )
        db.add(membership)
        db.flush()

        assert membership.is_primary is False

    def test_membership_unique_constraint(self, db):
        user = _create_user(db)
        household = _create_household(db, user)

        m1 = HouseholdMembership(
            id=uuid.uuid4(),
            household_id=household.id,
            user_id=user.id,
        )
        db.add(m1)
        db.flush()

        m2 = HouseholdMembership(
            id=uuid.uuid4(),
            household_id=household.id,
            user_id=user.id,
        )
        db.add(m2)
        with pytest.raises(IntegrityError):
            db.flush()

    def test_household_memberships_relationship(self, db):
        user = _create_user(db)
        household = _create_household(db, user)

        membership = HouseholdMembership(
            id=uuid.uuid4(),
            household_id=household.id,
            user_id=user.id,
        )
        db.add(membership)
        db.flush()

        assert len(household.memberships) == 1
        assert household.memberships[0].user_id == user.id


class TestHouseholdTemplateExclusion:
    def test_create_exclusion(self, db):
        user = _create_user(db)
        household = _create_household(db, user)
        template = _create_template(db, user)

        exclusion = HouseholdTemplateExclusion(
            id=uuid.uuid4(),
            household_id=household.id,
            template_id=template.id,
        )
        db.add(exclusion)
        db.flush()

        assert exclusion.id is not None
        assert exclusion.household_id == household.id
        assert exclusion.template_id == template.id
        assert exclusion.household.id == household.id
        assert exclusion.template.id == template.id

    def test_exclusion_unique_constraint(self, db):
        user = _create_user(db)
        household = _create_household(db, user)
        template = _create_template(db, user)

        e1 = HouseholdTemplateExclusion(
            id=uuid.uuid4(),
            household_id=household.id,
            template_id=template.id,
        )
        db.add(e1)
        db.flush()

        e2 = HouseholdTemplateExclusion(
            id=uuid.uuid4(),
            household_id=household.id,
            template_id=template.id,
        )
        db.add(e2)
        with pytest.raises(IntegrityError):
            db.flush()

    def test_household_template_exclusions_relationship(self, db):
        user = _create_user(db)
        household = _create_household(db, user)
        template = _create_template(db, user)

        exclusion = HouseholdTemplateExclusion(
            id=uuid.uuid4(),
            household_id=household.id,
            template_id=template.id,
        )
        db.add(exclusion)
        db.flush()

        assert len(household.template_exclusions) == 1
        assert household.template_exclusions[0].template_id == template.id


class TestMealHouseholdId:
    def test_meal_has_household_id_column(self, db):
        """Verify the Meal model has a household_id column."""
        user = _create_user(db)

        meal = Meal(
            id=uuid.uuid4(),
            user_id=user.id,
            name="Test Meal",
        )
        db.add(meal)
        db.flush()

        # household_id should be nullable and default to None
        assert meal.household_id is None

    def test_meal_with_household(self, db):
        """Verify a Meal can be associated with a Household."""
        user = _create_user(db)
        household = _create_household(db, user)

        meal = Meal(
            id=uuid.uuid4(),
            user_id=user.id,
            name="Household Meal",
            household_id=household.id,
        )
        db.add(meal)
        db.flush()

        assert meal.household_id == household.id
        assert meal.household.id == household.id
