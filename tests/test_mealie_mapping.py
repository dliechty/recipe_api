from types import SimpleNamespace

from migration_scripts.mealie_mapping import (
    slugify,
    format_quantity,
    format_time,
    build_ingredient_line,
    build_ingredients,
    build_instructions,
    build_yield,
    tag_names,
    build_notes,
    should_skip_recipe,
)


def _ri(quantity, unit, name, notes=None, order=0):
    return SimpleNamespace(
        quantity=quantity, unit=unit, notes=notes, order=order,
        ingredient=SimpleNamespace(name=name),
    )


def _component(name, ingredients):
    return SimpleNamespace(name=name, ingredients=ingredients)


def test_slugify_lowercases_and_hyphenates():
    assert slugify("Mom's Apple Pie!") == "mom-s-apple-pie"


def test_slugify_collapses_and_strips_separators():
    assert slugify("  Beef   &  Broccoli  ") == "beef-broccoli"


def test_format_quantity_integer_drops_decimal():
    assert format_quantity(2.0) == "2"


def test_format_quantity_trims_trailing_zeros():
    assert format_quantity(0.5) == "0.5"
    assert format_quantity(0.333) == "0.333"


def test_format_quantity_zero_and_none_are_empty():
    assert format_quantity(0) == ""
    assert format_quantity(None) == ""


def test_format_time_minutes():
    assert format_time(30) == "30 minutes"


def test_format_time_zero_or_none_is_none():
    assert format_time(0) is None
    assert format_time(None) is None


def test_build_ingredient_line_full():
    assert build_ingredient_line(2.0, "cup", "Flour", "sifted") == "2 cup Flour, sifted"


def test_build_ingredient_line_to_taste_drops_zero_quantity():
    assert build_ingredient_line(0, "To Taste", "Salt", None) == "To Taste Salt"


def test_build_ingredients_single_main_component_has_no_title():
    recipe = SimpleNamespace(components=[
        _component("Main", [_ri(1.0, "cup", "Sugar", order=0)]),
    ])
    items = build_ingredients(recipe)
    assert items == [{"title": None, "note": "1 cup Sugar", "disableAmount": True, "quantity": None}]


def test_build_ingredients_titles_non_main_sections_on_first_line():
    recipe = SimpleNamespace(components=[
        _component("Main", [_ri(1.0, "cup", "Flour", order=1), _ri(2.0, None, "Eggs", order=0)]),
        _component("Frosting", [_ri(0.5, "cup", "Butter", order=0)]),
    ])
    items = build_ingredients(recipe)
    # ordered by .order within component; Main has no title; Frosting titled on first line
    assert items[0] == {"title": None, "note": "2 Eggs", "disableAmount": True, "quantity": None}
    assert items[1] == {"title": None, "note": "1 cup Flour", "disableAmount": True, "quantity": None}
    assert items[2] == {"title": "Frosting", "note": "0.5 cup Butter", "disableAmount": True, "quantity": None}


def test_build_instructions_sorted_by_step_number():
    recipe = SimpleNamespace(instructions=[
        SimpleNamespace(step_number=2, text="Bake"),
        SimpleNamespace(step_number=1, text="Mix"),
    ])
    assert build_instructions(recipe) == [{"text": "Mix"}, {"text": "Bake"}]


def test_build_yield_amount_and_unit():
    recipe = SimpleNamespace(yield_amount=4.0, yield_unit="servings")
    assert build_yield(recipe) == "4 servings"


def test_build_yield_unit_only():
    recipe = SimpleNamespace(yield_amount=None, yield_unit="1 loaf")
    assert build_yield(recipe) == "1 loaf"


def test_tag_names_collects_non_null_cuisine_protein_difficulty():
    recipe = SimpleNamespace(
        cuisine="Italian", protein="Chicken",
        difficulty=SimpleNamespace(value="Easy"),
    )
    assert tag_names(recipe) == ["Italian", "Chicken", "Easy"]


def test_tag_names_skips_nulls():
    recipe = SimpleNamespace(cuisine=None, protein="Beef", difficulty=None)
    assert tag_names(recipe) == ["Beef"]


def test_build_notes_includes_source_and_comments():
    recipe = SimpleNamespace(
        source="Grandma's cookbook",
        comments=[SimpleNamespace(text="Migrated Note:\n\nUse fresh basil")],
    )
    assert build_notes(recipe) == [
        {"title": "Source", "text": "Grandma's cookbook"},
        {"title": "Note", "text": "Migrated Note:\n\nUse fresh basil"},
    ]


def test_should_skip_meta_recipe():
    assert should_skip_recipe("<<Base Sauce>>") is True
    assert should_skip_recipe("Tomato Sauce") is False
