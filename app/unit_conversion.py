# unit_conversion.py
# Handles metric/imperial unit classification and conversion for recipe ingredients.
# Uses the pint library for accurate unit conversions.

from enum import Enum
from typing import Optional, Tuple

import pint

# Initialize the unit registry
ureg = pint.UnitRegistry()


class UnitSystem(str, Enum):
    """Unit system for recipe ingredients."""
    METRIC = "metric"
    IMPERIAL = "imperial"


# Mapping of common recipe unit strings to pint unit names
# This handles variations in how users might enter units
UNIT_ALIASES = {
    # Imperial volume
    "cup": "cup",
    "cups": "cup",
    "c": "cup",
    "tablespoon": "tablespoon",
    "tablespoons": "tablespoon",
    "tbsp": "tablespoon",
    "tbs": "tablespoon",
    "teaspoon": "teaspoon",
    "teaspoons": "teaspoon",
    "tsp": "teaspoon",
    "fluid ounce": "fluid_ounce",
    "fluid ounces": "fluid_ounce",
    "fl oz": "fluid_ounce",
    "floz": "fluid_ounce",
    "pint": "pint",
    "pints": "pint",
    "pt": "pint",
    "quart": "quart",
    "quarts": "quart",
    "qt": "quart",
    "gallon": "gallon",
    "gallons": "gallon",
    "gal": "gallon",

    # Imperial weight
    "ounce": "ounce",
    "ounces": "ounce",
    "oz": "ounce",
    "pound": "pound",
    "pounds": "pound",
    "lb": "pound",
    "lbs": "pound",

    # Imperial length
    "inch": "inch",
    "inches": "inch",
    "in": "inch",

    # Metric volume
    "milliliter": "milliliter",
    "milliliters": "milliliter",
    "ml": "milliliter",
    "liter": "liter",
    "liters": "liter",
    "litre": "liter",
    "litres": "liter",
    "l": "liter",

    # Metric weight
    "gram": "gram",
    "grams": "gram",
    "g": "gram",
    "kilogram": "kilogram",
    "kilograms": "kilogram",
    "kg": "kilogram",

    # Metric length
    "centimeter": "centimeter",
    "centimeters": "centimeter",
    "cm": "centimeter",
    "millimeter": "millimeter",
    "millimeters": "millimeter",
    "mm": "millimeter",
}

# Classification of units by system
IMPERIAL_UNITS = {
    "cup", "tablespoon", "teaspoon", "fluid_ounce", "pint", "quart", "gallon",
    "ounce", "pound", "inch"
}

METRIC_UNITS = {
    "milliliter", "liter", "gram", "kilogram", "centimeter", "millimeter"
}

# Unit type classification
VOLUME_UNITS = {"cup", "tablespoon", "teaspoon", "fluid_ounce", "pint", "quart", "gallon", "milliliter", "liter"}
WEIGHT_UNITS = {"ounce", "pound", "gram", "kilogram"}
LENGTH_UNITS = {"inch", "centimeter", "millimeter"}

# Preferred target units by type and system
PREFERRED_UNITS = {
    UnitSystem.METRIC: {
        "volume": "milliliter",
        "weight": "gram",
        "length": "centimeter",
    },
    UnitSystem.IMPERIAL: {
        "volume": "cup",
        "weight": "ounce",
        "length": "inch",
    },
}

# Display names for units (how they appear in output)
DISPLAY_NAMES = {
    "cup": "cup",
    "tablespoon": "tbsp",
    "teaspoon": "tsp",
    "fluid_ounce": "fl oz",
    "pint": "pint",
    "quart": "quart",
    "gallon": "gallon",
    "ounce": "oz",
    "pound": "lb",
    "inch": "inch",
    "milliliter": "ml",
    "liter": "l",
    "gram": "g",
    "kilogram": "kg",
    "centimeter": "cm",
    "millimeter": "mm",
}

# Thresholds for simplifying to larger units
SIMPLIFICATION_THRESHOLDS = {
    "milliliter": (1000, "liter"),
    "gram": (1000, "kilogram"),
    "millimeter": (10, "centimeter"),
}


def get_pint_unit(unit_str: str) -> Optional[str]:
    """
    Convert a unit string to its pint-compatible name.
    Returns None if unit is not recognized.
    """
    normalized = unit_str.lower().strip()
    return UNIT_ALIASES.get(normalized)


def get_unit_system(pint_unit: str) -> Optional[UnitSystem]:
    """
    Get the unit system for a pint unit name.
    Returns None if unit is not in either system.
    """
    if pint_unit in IMPERIAL_UNITS:
        return UnitSystem.IMPERIAL
    elif pint_unit in METRIC_UNITS:
        return UnitSystem.METRIC
    return None


def get_unit_type(pint_unit: str) -> Optional[str]:
    """
    Get the type of a unit (volume, weight, or length).
    Returns None if unit type is not recognized.
    """
    if pint_unit in VOLUME_UNITS:
        return "volume"
    elif pint_unit in WEIGHT_UNITS:
        return "weight"
    elif pint_unit in LENGTH_UNITS:
        return "length"
    return None


def get_unit_info(unit: str) -> Optional[Tuple[str, UnitSystem, str]]:
    """
    Get canonical name, unit system, and type for a unit.
    Returns None if unit is not recognized.
    """
    pint_unit = get_pint_unit(unit)
    if pint_unit is None:
        return None

    system = get_unit_system(pint_unit)
    unit_type = get_unit_type(pint_unit)

    if system is None or unit_type is None:
        return None

    return (pint_unit, system, unit_type)


def detect_recipe_unit_system(ingredients: list) -> UnitSystem:
    """
    Determine the predominant unit system used in a recipe's ingredients.
    Returns METRIC if majority of recognized units are metric,
    IMPERIAL if majority are imperial, or IMPERIAL as default.
    """
    metric_count = 0
    imperial_count = 0

    for ingredient in ingredients:
        unit = ingredient.get("unit", "")
        pint_unit = get_pint_unit(unit)
        if pint_unit:
            system = get_unit_system(pint_unit)
            if system == UnitSystem.METRIC:
                metric_count += 1
            elif system == UnitSystem.IMPERIAL:
                imperial_count += 1

    if metric_count > imperial_count:
        return UnitSystem.METRIC
    elif imperial_count > metric_count:
        return UnitSystem.IMPERIAL
    else:
        return UnitSystem.IMPERIAL


def convert_quantity(
    quantity: float,
    from_unit: str,
    target_system: UnitSystem
) -> Tuple[float, str]:
    """
    Convert a quantity from one unit to the target system using pint.
    Returns (converted_quantity, new_unit_display_name).
    If conversion is not possible, returns original quantity and unit.
    """
    pint_unit = get_pint_unit(from_unit)
    if pint_unit is None:
        return quantity, from_unit

    current_system = get_unit_system(pint_unit)
    if current_system is None or current_system == target_system:
        return quantity, from_unit

    unit_type = get_unit_type(pint_unit)
    if unit_type is None:
        return quantity, from_unit

    target_unit = PREFERRED_UNITS[target_system][unit_type]

    try:
        # Create pint quantity and convert
        source_qty = quantity * getattr(ureg, pint_unit)
        converted = source_qty.to(getattr(ureg, target_unit))
        converted_value = converted.magnitude

        # Apply simplification if quantity is large
        if target_unit in SIMPLIFICATION_THRESHOLDS:
            threshold, larger_unit = SIMPLIFICATION_THRESHOLDS[target_unit]
            if converted_value >= threshold:
                simplified = converted.to(getattr(ureg, larger_unit))
                converted_value = round(simplified.magnitude, 2)
                target_unit = larger_unit
            else:
                converted_value = round(converted_value, 2)
        else:
            converted_value = round(converted_value, 2)

        display_name = DISPLAY_NAMES.get(target_unit, target_unit)
        return converted_value, display_name

    except pint.DimensionalityError:
        # Can't convert between incompatible units
        return quantity, from_unit


def convert_recipe_units(recipe_dict: dict, target_system: UnitSystem) -> dict:
    """
    Convert all ingredient units in a recipe to the target unit system.
    Modifies and returns the recipe dictionary.
    """
    for component in recipe_dict.get("components", []):
        for ingredient in component.get("ingredients", []):
            quantity = ingredient.get("quantity", 0)
            unit = ingredient.get("unit", "")

            new_quantity, new_unit = convert_quantity(quantity, unit, target_system)
            ingredient["quantity"] = new_quantity
            ingredient["unit"] = new_unit

    return recipe_dict
