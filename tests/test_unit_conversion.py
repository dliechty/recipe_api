"""Tests for metric/imperial unit conversion functionality."""

import pytest
from fastapi.testclient import TestClient

from app import crud, schemas
from app.unit_conversion import (
    UnitSystem,
    get_unit_info,
    detect_recipe_unit_system,
    convert_quantity,
    convert_recipe_units,
)


# --- Unit Conversion Module Tests ---

class TestGetUnitInfo:
    """Tests for the get_unit_info function."""

    def test_imperial_volume_units(self):
        """Test recognition of imperial volume units."""
        assert get_unit_info("cup") == ("cup", UnitSystem.IMPERIAL, "volume")
        assert get_unit_info("cups") == ("cup", UnitSystem.IMPERIAL, "volume")
        assert get_unit_info("tbsp") == ("tablespoon", UnitSystem.IMPERIAL, "volume")
        assert get_unit_info("tsp") == ("teaspoon", UnitSystem.IMPERIAL, "volume")
        assert get_unit_info("fl oz") == ("fluid_ounce", UnitSystem.IMPERIAL, "volume")

    def test_imperial_weight_units(self):
        """Test recognition of imperial weight units."""
        assert get_unit_info("oz") == ("ounce", UnitSystem.IMPERIAL, "weight")
        assert get_unit_info("ounce") == ("ounce", UnitSystem.IMPERIAL, "weight")
        assert get_unit_info("lb") == ("pound", UnitSystem.IMPERIAL, "weight")
        assert get_unit_info("pound") == ("pound", UnitSystem.IMPERIAL, "weight")

    def test_metric_volume_units(self):
        """Test recognition of metric volume units."""
        assert get_unit_info("ml") == ("milliliter", UnitSystem.METRIC, "volume")
        assert get_unit_info("milliliter") == ("milliliter", UnitSystem.METRIC, "volume")
        assert get_unit_info("l") == ("liter", UnitSystem.METRIC, "volume")
        assert get_unit_info("liter") == ("liter", UnitSystem.METRIC, "volume")

    def test_metric_weight_units(self):
        """Test recognition of metric weight units."""
        assert get_unit_info("g") == ("gram", UnitSystem.METRIC, "weight")
        assert get_unit_info("gram") == ("gram", UnitSystem.METRIC, "weight")
        assert get_unit_info("kg") == ("kilogram", UnitSystem.METRIC, "weight")
        assert get_unit_info("kilogram") == ("kilogram", UnitSystem.METRIC, "weight")

    def test_case_insensitive(self):
        """Test that unit recognition is case-insensitive."""
        assert get_unit_info("CUP") == ("cup", UnitSystem.IMPERIAL, "volume")
        assert get_unit_info("ML") == ("milliliter", UnitSystem.METRIC, "volume")
        assert get_unit_info("Gram") == ("gram", UnitSystem.METRIC, "weight")

    def test_unknown_unit(self):
        """Test that unknown units return None."""
        assert get_unit_info("slice") is None
        assert get_unit_info("pinch") is None
        assert get_unit_info("whole") is None
        assert get_unit_info("") is None


class TestDetectRecipeUnitSystem:
    """Tests for detecting the predominant unit system in a recipe."""

    def test_mostly_imperial(self):
        """Test recipe with mostly imperial units."""
        ingredients = [
            {"unit": "cups", "quantity": 2},
            {"unit": "tbsp", "quantity": 1},
            {"unit": "oz", "quantity": 4},
            {"unit": "slice", "quantity": 2},  # Unknown, not counted
        ]
        assert detect_recipe_unit_system(ingredients) == UnitSystem.IMPERIAL

    def test_mostly_metric(self):
        """Test recipe with mostly metric units."""
        ingredients = [
            {"unit": "ml", "quantity": 200},
            {"unit": "g", "quantity": 500},
            {"unit": "kg", "quantity": 1},
            {"unit": "pinch", "quantity": 1},  # Unknown, not counted
        ]
        assert detect_recipe_unit_system(ingredients) == UnitSystem.METRIC

    def test_mixed_units_imperial_majority(self):
        """Test recipe with mixed units, imperial majority."""
        ingredients = [
            {"unit": "cups", "quantity": 2},
            {"unit": "ml", "quantity": 100},
            {"unit": "tbsp", "quantity": 3},
        ]
        assert detect_recipe_unit_system(ingredients) == UnitSystem.IMPERIAL

    def test_equal_units_defaults_imperial(self):
        """Test recipe with equal metric/imperial units defaults to imperial."""
        ingredients = [
            {"unit": "cups", "quantity": 1},
            {"unit": "ml", "quantity": 100},
        ]
        assert detect_recipe_unit_system(ingredients) == UnitSystem.IMPERIAL

    def test_no_recognized_units_defaults_imperial(self):
        """Test recipe with no recognized units defaults to imperial."""
        ingredients = [
            {"unit": "slice", "quantity": 2},
            {"unit": "whole", "quantity": 1},
        ]
        assert detect_recipe_unit_system(ingredients) == UnitSystem.IMPERIAL

    def test_empty_ingredients(self):
        """Test empty ingredients list defaults to imperial."""
        assert detect_recipe_unit_system([]) == UnitSystem.IMPERIAL


class TestConvertQuantity:
    """Tests for the convert_quantity function."""

    def test_cup_to_ml(self):
        """Test converting cups to milliliters."""
        quantity, unit = convert_quantity(1, "cup", UnitSystem.METRIC)
        assert unit == "ml"
        assert abs(quantity - 236.59) < 0.1  # ~236.588 ml per cup

    def test_cups_to_ml_large(self):
        """Test converting many cups to liters (simplification)."""
        quantity, unit = convert_quantity(5, "cups", UnitSystem.METRIC)
        assert unit == "l"  # Should simplify to liters
        assert abs(quantity - 1.18) < 0.1  # ~1.183 liters

    def test_ml_to_cups(self):
        """Test converting milliliters to cups."""
        quantity, unit = convert_quantity(236.588, "ml", UnitSystem.IMPERIAL)
        assert unit == "cup"
        assert abs(quantity - 1.0) < 0.01

    def test_gram_to_oz(self):
        """Test converting grams to ounces."""
        quantity, unit = convert_quantity(100, "g", UnitSystem.IMPERIAL)
        assert unit == "oz"
        assert abs(quantity - 3.5) < 0.1  # ~3.527 oz

    def test_oz_to_gram(self):
        """Test converting ounces to grams."""
        quantity, unit = convert_quantity(4, "oz", UnitSystem.METRIC)
        assert unit == "g"
        assert abs(quantity - 113.4) < 0.1  # ~113.4 g

    def test_lb_to_gram(self):
        """Test converting pounds to grams."""
        quantity, unit = convert_quantity(1, "lb", UnitSystem.METRIC)
        assert unit == "g"
        assert abs(quantity - 453.59) < 0.1

    def test_lb_to_kg_large(self):
        """Test converting many pounds to kg (simplification)."""
        quantity, unit = convert_quantity(5, "lb", UnitSystem.METRIC)
        assert unit == "kg"  # Should simplify to kg
        assert abs(quantity - 2.27) < 0.1

    def test_unknown_unit_unchanged(self):
        """Test that unknown units are returned unchanged."""
        quantity, unit = convert_quantity(2, "slice", UnitSystem.METRIC)
        assert unit == "slice"
        assert quantity == 2

    def test_same_system_unchanged(self):
        """Test that units already in target system are unchanged."""
        quantity, unit = convert_quantity(2, "cups", UnitSystem.IMPERIAL)
        assert unit == "cups"  # Original unit preserved
        assert quantity == 2


class TestConvertRecipeUnits:
    """Tests for the convert_recipe_units function."""

    def test_convert_imperial_to_metric(self):
        """Test converting a recipe from imperial to metric."""
        recipe = {
            "components": [
                {
                    "name": "Main",
                    "ingredients": [
                        {"quantity": 2, "unit": "cups", "item": "Flour"},
                        {"quantity": 1, "unit": "oz", "item": "Butter"},
                    ]
                }
            ]
        }
        result = convert_recipe_units(recipe, UnitSystem.METRIC)

        # Flour: 2 cups -> ~473 ml
        assert result["components"][0]["ingredients"][0]["unit"] == "ml"
        assert abs(result["components"][0]["ingredients"][0]["quantity"] - 473.18) < 0.1

        # Butter: 1 oz -> ~28.35 g
        assert result["components"][0]["ingredients"][1]["unit"] == "g"
        assert abs(result["components"][0]["ingredients"][1]["quantity"] - 28.35) < 0.1

    def test_convert_metric_to_imperial(self):
        """Test converting a recipe from metric to imperial."""
        recipe = {
            "components": [
                {
                    "name": "Main",
                    "ingredients": [
                        {"quantity": 500, "unit": "ml", "item": "Water"},
                        {"quantity": 100, "unit": "g", "item": "Sugar"},
                    ]
                }
            ]
        }
        result = convert_recipe_units(recipe, UnitSystem.IMPERIAL)

        # Water: 500 ml -> ~2.1 cups
        assert result["components"][0]["ingredients"][0]["unit"] == "cup"
        assert abs(result["components"][0]["ingredients"][0]["quantity"] - 2.12) < 0.1

        # Sugar: 100 g -> ~3.5 oz
        assert result["components"][0]["ingredients"][1]["unit"] == "oz"
        assert abs(result["components"][0]["ingredients"][1]["quantity"] - 3.5) < 0.1

    def test_unknown_units_preserved(self):
        """Test that unknown units are preserved in conversion."""
        recipe = {
            "components": [
                {
                    "name": "Main",
                    "ingredients": [
                        {"quantity": 2, "unit": "slice", "item": "Bread"},
                        {"quantity": 1, "unit": "cups", "item": "Milk"},
                    ]
                }
            ]
        }
        result = convert_recipe_units(recipe, UnitSystem.METRIC)

        # Slice should be unchanged
        assert result["components"][0]["ingredients"][0]["unit"] == "slice"
        assert result["components"][0]["ingredients"][0]["quantity"] == 2

        # Cups should be converted
        assert result["components"][0]["ingredients"][1]["unit"] == "ml"


# --- API Endpoint Tests ---

def get_auth_headers(client: TestClient, db, email="unitconvert@example.com", password="password"):
    """Helper to get authentication headers."""
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


class TestRecipeUnitConversionAPI:
    """Tests for the recipe API unit conversion parameter."""

    def test_read_recipe_with_metric_units(self, client: TestClient, db):
        """Test retrieving recipe with metric unit conversion."""
        headers = get_auth_headers(client, db)

        recipe_data = {
            "core": {"name": "Unit Test Recipe"},
            "times": {},
            "nutrition": {},
            "components": [
                {
                    "name": "Main",
                    "ingredients": [
                        {"ingredient_name": "Flour", "quantity": 2, "unit": "cups"},
                        {"ingredient_name": "Butter", "quantity": 4, "unit": "oz"},
                    ]
                }
            ],
            "instructions": []
        }
        create_res = client.post("/recipes/", json=recipe_data, headers=headers)
        recipe_id = create_res.json()["core"]["id"]

        response = client.get(f"/recipes/{recipe_id}?units=metric", headers=headers)
        assert response.status_code == 200
        data = response.json()

        # Check that flour is converted to ml
        flour = data["components"][0]["ingredients"][0]
        assert flour["unit"] == "ml"
        assert abs(flour["quantity"] - 473.18) < 1

        # Check that butter is converted to g
        butter = data["components"][0]["ingredients"][1]
        assert butter["unit"] == "g"
        assert abs(butter["quantity"] - 113.4) < 1

        # unit_system should reflect the target system after conversion
        assert data["unit_system"] == "metric"

    def test_read_recipe_with_imperial_units(self, client: TestClient, db):
        """Test retrieving recipe with imperial unit conversion."""
        headers = get_auth_headers(client, db)

        recipe_data = {
            "core": {"name": "Metric Recipe"},
            "times": {},
            "nutrition": {},
            "components": [
                {
                    "name": "Main",
                    "ingredients": [
                        {"ingredient_name": "Water", "quantity": 500, "unit": "ml"},
                        {"ingredient_name": "Sugar", "quantity": 100, "unit": "g"},
                    ]
                }
            ],
            "instructions": []
        }
        create_res = client.post("/recipes/", json=recipe_data, headers=headers)
        recipe_id = create_res.json()["core"]["id"]

        response = client.get(f"/recipes/{recipe_id}?units=imperial", headers=headers)
        assert response.status_code == 200
        data = response.json()

        # Check that water is converted to cups
        water = data["components"][0]["ingredients"][0]
        assert water["unit"] == "cup"
        assert abs(water["quantity"] - 2.12) < 0.1

        # Check that sugar is converted to oz
        sugar = data["components"][0]["ingredients"][1]
        assert sugar["unit"] == "oz"
        assert abs(sugar["quantity"] - 3.5) < 0.1

        # unit_system should reflect the target system after conversion
        assert data["unit_system"] == "imperial"

    def test_read_recipe_no_units_parameter(self, client: TestClient, db):
        """Test that omitting units parameter keeps original units and includes unit_system."""
        headers = get_auth_headers(client, db)

        recipe_data = {
            "core": {"name": "Default Units Recipe"},
            "times": {},
            "nutrition": {},
            "components": [
                {
                    "name": "Main",
                    "ingredients": [
                        {"ingredient_name": "Milk", "quantity": 1.5, "unit": "cups"},
                    ]
                }
            ],
            "instructions": []
        }
        create_res = client.post("/recipes/", json=recipe_data, headers=headers)
        recipe_id = create_res.json()["core"]["id"]

        response = client.get(f"/recipes/{recipe_id}", headers=headers)
        assert response.status_code == 200
        data = response.json()

        milk = data["components"][0]["ingredients"][0]
        assert milk["unit"] == "cups"
        assert milk["quantity"] == 1.5

        # Check that unit_system is included and derived correctly
        assert data["unit_system"] == "imperial"

    def test_read_recipe_unit_system_metric(self, client: TestClient, db):
        """Test that unit_system is correctly derived as metric."""
        headers = get_auth_headers(client, db)

        recipe_data = {
            "core": {"name": "Metric Recipe For System"},
            "times": {},
            "nutrition": {},
            "components": [
                {
                    "name": "Main",
                    "ingredients": [
                        {"ingredient_name": "Water", "quantity": 500, "unit": "ml"},
                        {"ingredient_name": "Sugar", "quantity": 100, "unit": "g"},
                    ]
                }
            ],
            "instructions": []
        }
        create_res = client.post("/recipes/", json=recipe_data, headers=headers)
        recipe_id = create_res.json()["core"]["id"]

        response = client.get(f"/recipes/{recipe_id}", headers=headers)
        assert response.status_code == 200
        data = response.json()

        # Recipe uses metric units, so unit_system should be metric
        assert data["unit_system"] == "metric"

    def test_read_recipe_unit_system_imperial(self, client: TestClient, db):
        """Test that unit_system is correctly derived as imperial."""
        headers = get_auth_headers(client, db)

        recipe_data = {
            "core": {"name": "Imperial Recipe For System"},
            "times": {},
            "nutrition": {},
            "components": [
                {
                    "name": "Main",
                    "ingredients": [
                        {"ingredient_name": "Flour", "quantity": 2, "unit": "cups"},
                        {"ingredient_name": "Butter", "quantity": 4, "unit": "oz"},
                    ]
                }
            ],
            "instructions": []
        }
        create_res = client.post("/recipes/", json=recipe_data, headers=headers)
        recipe_id = create_res.json()["core"]["id"]

        response = client.get(f"/recipes/{recipe_id}", headers=headers)
        assert response.status_code == 200
        data = response.json()

        # Recipe uses imperial units, so unit_system should be imperial
        assert data["unit_system"] == "imperial"

    def test_read_recipe_scale_and_units_combined(self, client: TestClient, db):
        """Test combining scale and unit conversion parameters."""
        headers = get_auth_headers(client, db)

        recipe_data = {
            "core": {"name": "Scale and Convert Recipe", "yield_amount": 4},
            "times": {},
            "nutrition": {},
            "components": [
                {
                    "name": "Main",
                    "ingredients": [
                        {"ingredient_name": "Flour", "quantity": 1, "unit": "cup"},
                    ]
                }
            ],
            "instructions": []
        }
        create_res = client.post("/recipes/", json=recipe_data, headers=headers)
        recipe_id = create_res.json()["core"]["id"]

        # Scale by 2 and convert to metric
        response = client.get(f"/recipes/{recipe_id}?scale=2&units=metric", headers=headers)
        assert response.status_code == 200
        data = response.json()

        # 1 cup * 2 = 2 cups -> ~473.18 ml
        flour = data["components"][0]["ingredients"][0]
        assert flour["unit"] == "ml"
        assert abs(flour["quantity"] - 473.18) < 1

        # Yield should also be scaled
        assert data["core"]["yield_amount"] == 8

    def test_invalid_units_parameter(self, client: TestClient, db):
        """Test that invalid units parameter returns 422."""
        headers = get_auth_headers(client, db)

        recipe_data = {
            "core": {"name": "Invalid Units Recipe"},
            "times": {},
            "nutrition": {},
            "components": [],
            "instructions": []
        }
        create_res = client.post("/recipes/", json=recipe_data, headers=headers)
        recipe_id = create_res.json()["core"]["id"]

        response = client.get(f"/recipes/{recipe_id}?units=invalid", headers=headers)
        assert response.status_code == 422

    def test_unknown_units_preserved_in_conversion(self, client: TestClient, db):
        """Test that non-convertible units are preserved."""
        headers = get_auth_headers(client, db)

        recipe_data = {
            "core": {"name": "Mixed Units Recipe"},
            "times": {},
            "nutrition": {},
            "components": [
                {
                    "name": "Main",
                    "ingredients": [
                        {"ingredient_name": "Bread", "quantity": 2, "unit": "slice"},
                        {"ingredient_name": "Butter", "quantity": 1, "unit": "tbsp"},
                    ]
                }
            ],
            "instructions": []
        }
        create_res = client.post("/recipes/", json=recipe_data, headers=headers)
        recipe_id = create_res.json()["core"]["id"]

        response = client.get(f"/recipes/{recipe_id}?units=metric", headers=headers)
        assert response.status_code == 200
        data = response.json()

        # Slice should remain unchanged
        bread = data["components"][0]["ingredients"][0]
        assert bread["unit"] == "slice"
        assert bread["quantity"] == 2

        # Tablespoon should be converted
        butter = data["components"][0]["ingredients"][1]
        assert butter["unit"] == "ml"
        assert abs(butter["quantity"] - 14.79) < 0.1

    def test_multiple_components_conversion(self, client: TestClient, db):
        """Test unit conversion across multiple recipe components."""
        headers = get_auth_headers(client, db)

        recipe_data = {
            "core": {"name": "Multi-Component Recipe"},
            "times": {},
            "nutrition": {},
            "components": [
                {
                    "name": "Dough",
                    "ingredients": [
                        {"ingredient_name": "Flour", "quantity": 3, "unit": "cups"},
                    ]
                },
                {
                    "name": "Filling",
                    "ingredients": [
                        {"ingredient_name": "Cheese", "quantity": 8, "unit": "oz"},
                    ]
                }
            ],
            "instructions": []
        }
        create_res = client.post("/recipes/", json=recipe_data, headers=headers)
        recipe_id = create_res.json()["core"]["id"]

        response = client.get(f"/recipes/{recipe_id}?units=metric", headers=headers)
        assert response.status_code == 200
        data = response.json()

        # Check dough component
        flour = data["components"][0]["ingredients"][0]
        assert flour["unit"] == "ml"
        assert abs(flour["quantity"] - 709.76) < 1

        # Check filling component
        cheese = data["components"][1]["ingredients"][0]
        assert cheese["unit"] == "g"
        assert abs(cheese["quantity"] - 226.8) < 1

    def test_large_quantity_simplification(self, client: TestClient, db):
        """Test that large quantities are simplified to larger units."""
        headers = get_auth_headers(client, db)

        recipe_data = {
            "core": {"name": "Large Quantity Recipe"},
            "times": {},
            "nutrition": {},
            "components": [
                {
                    "name": "Main",
                    "ingredients": [
                        {"ingredient_name": "Water", "quantity": 8, "unit": "cups"},
                    ]
                }
            ],
            "instructions": []
        }
        create_res = client.post("/recipes/", json=recipe_data, headers=headers)
        recipe_id = create_res.json()["core"]["id"]

        response = client.get(f"/recipes/{recipe_id}?units=metric", headers=headers)
        assert response.status_code == 200
        data = response.json()

        # 8 cups -> ~1.89 liters (should simplify to liters)
        water = data["components"][0]["ingredients"][0]
        assert water["unit"] == "l"
        assert abs(water["quantity"] - 1.89) < 0.1
