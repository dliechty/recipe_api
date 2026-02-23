"""Tests for household-related Pydantic schemas."""

from datetime import datetime
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.schemas import (
    Household,
    HouseholdCreate,
    HouseholdMember,
    HouseholdTemplateExclusion,
    HouseholdTemplateExclusionCreate,
    HouseholdUpdate,
    Meal,
    MealUpdate,
    PrimaryHouseholdUpdate,
    UserPublic,
)


class TestHouseholdCreate:
    def test_valid(self):
        schema = HouseholdCreate(name="My Household")
        assert schema.name == "My Household"

    def test_requires_name(self):
        with pytest.raises(ValidationError):
            HouseholdCreate()


class TestHouseholdUpdate:
    def test_name_optional(self):
        schema = HouseholdUpdate()
        assert schema.name is None

    def test_with_name(self):
        schema = HouseholdUpdate(name="Updated Name")
        assert schema.name == "Updated Name"


class TestHousehold:
    def test_from_attributes(self):
        now = datetime.now()
        uid = uuid4()
        creator = uuid4()

        class FakeHousehold:
            id = uid
            name = "Test Household"
            created_by = creator
            created_at = now
            updated_at = now

        schema = Household.model_validate(FakeHousehold(), from_attributes=True)
        assert schema.id == uid
        assert schema.name == "Test Household"
        assert schema.created_by == creator
        assert schema.created_at == now
        assert schema.updated_at == now

    def test_from_dict(self):
        now = datetime.now()
        uid = uuid4()
        creator = uuid4()
        schema = Household(
            id=uid,
            name="Test",
            created_by=creator,
            created_at=now,
            updated_at=now,
        )
        assert schema.id == uid


class TestHouseholdMember:
    def test_from_attributes(self):
        now = datetime.now()
        member_id = uuid4()
        the_user_id = uuid4()

        class FakeUser:
            id = the_user_id
            email = "test@example.com"
            first_name = "Test"
            last_name = "User"
            is_first_login = False
            is_admin = False

        fake_user = FakeUser()

        class FakeMember:
            id = member_id
            user_id = the_user_id
            user = fake_user
            is_primary = True
            joined_at = now

        schema = HouseholdMember.model_validate(FakeMember(), from_attributes=True)
        assert schema.id == member_id
        assert schema.user_id == the_user_id
        assert schema.is_primary is True
        assert schema.joined_at == now
        assert isinstance(schema.user, UserPublic)
        assert schema.user.email == "test@example.com"


class TestHouseholdTemplateExclusion:
    def test_from_attributes(self):
        eid = uuid4()
        hid = uuid4()
        tid = uuid4()

        class FakeExclusion:
            id = eid
            household_id = hid
            template_id = tid

        schema = HouseholdTemplateExclusion.model_validate(
            FakeExclusion(), from_attributes=True
        )
        assert schema.id == eid
        assert schema.household_id == hid
        assert schema.template_id == tid

    def test_create(self):
        tid = uuid4()
        schema = HouseholdTemplateExclusionCreate(template_id=tid)
        assert schema.template_id == tid


class TestMealUpdateHouseholdId:
    def test_default_none(self):
        schema = MealUpdate()
        assert schema.household_id is None

    def test_accepts_uuid(self):
        hid = uuid4()
        schema = MealUpdate(household_id=hid)
        assert schema.household_id == hid

    def test_explicit_none(self):
        schema = MealUpdate(household_id=None)
        assert schema.household_id is None

    def test_in_model_fields_set_when_provided(self):
        hid = uuid4()
        schema = MealUpdate(household_id=hid)
        assert "household_id" in schema.model_fields_set

    def test_not_in_model_fields_set_when_omitted(self):
        schema = MealUpdate(name="dinner")
        assert "household_id" not in schema.model_fields_set


class TestMealResponseHouseholdId:
    def test_default_none(self):
        now = datetime.now()
        schema = Meal(
            id=uuid4(),
            user_id=uuid4(),
            created_at=now,
            updated_at=now,
            items=[],
        )
        assert schema.household_id is None

    def test_with_household_id(self):
        now = datetime.now()
        hid = uuid4()
        schema = Meal(
            id=uuid4(),
            user_id=uuid4(),
            household_id=hid,
            created_at=now,
            updated_at=now,
            items=[],
        )
        assert schema.household_id == hid


class TestPrimaryHouseholdUpdate:
    def test_default_none(self):
        schema = PrimaryHouseholdUpdate()
        assert schema.household_id is None

    def test_with_uuid(self):
        hid = uuid4()
        schema = PrimaryHouseholdUpdate(household_id=hid)
        assert schema.household_id == hid

    def test_explicit_none(self):
        schema = PrimaryHouseholdUpdate(household_id=None)
        assert schema.household_id is None
