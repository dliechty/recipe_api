from types import SimpleNamespace

from migration_scripts.mealie_mapping import (
    slugify,
    format_quantity,
    format_time,
    build_ingredient_line,
    build_structured_ingredient,
    build_structured_ingredients,
    build_instructions,
    build_servings,
    build_yield,
    tag_names,
    build_notes,
    should_skip_recipe,
    recipe_to_payload,
    load_food_map,
    load_unit_map,
    missing_map_entries,
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


class _FakeResolver:
    def resolve_unit(self, name):
        return {"id": f"u-{name}", "name": name} if name else None

    def resolve_food(self, name, action, label):
        return {"id": f"f-{name}", "name": name, "_action": action, "_label": label}


def test_structured_ingredient_normal_amount():
    ri = _ri(2.0, "cup", "Flour", "sifted", order=0)
    entry = build_structured_ingredient(
        ri, {"id": "u1", "name": "cup"}, {"id": "f1", "name": "Flour"}, None, to_taste=False)
    assert entry == {
        "title": None, "note": "sifted", "quantity": 2.0,
        "unit": {"id": "u1", "name": "cup"}, "food": {"id": "f1", "name": "Flour"},
        "disableAmount": False, "originalText": "2 cup Flour, sifted",
    }


def test_structured_ingredient_to_taste():
    ri = _ri(0, "To Taste", "Salt", None, order=0)
    entry = build_structured_ingredient(ri, None, {"id": "f2", "name": "Salt"}, None, to_taste=True)
    assert entry["quantity"] is None
    assert entry["disableAmount"] is True
    assert entry["unit"] is None
    assert entry["note"] == "to taste"
    assert entry["food"] == {"id": "f2", "name": "Salt"}


def test_structured_ingredients_resolves_maps_and_titles_sections():
    recipe = SimpleNamespace(components=[
        _component("Main", [_ri(1.0, "cup", "Flour", order=1), _ri(2.0, None, "Eggs", order=0)]),
        _component("Frosting", [_ri(0.5, "cup", "Butter", order=0)]),
    ])
    food_map = {n.lower(): {"mealie_food": n, "action": "match", "label": "", "flags": ""}
                for n in ("Flour", "Eggs", "Butter")}
    unit_map = {"cup": {"mealie_unit": "cup", "flags": ""}, "": {"mealie_unit": "", "flags": ""}}
    items = build_structured_ingredients(recipe, food_map, unit_map, _FakeResolver())
    assert items[0]["title"] is None and items[0]["food"]["name"] == "Eggs"
    assert items[0]["unit"] is None          # None source unit -> no unit
    assert items[1]["food"]["name"] == "Flour"
    assert items[2]["title"] == "Frosting"   # non-Main section titled on first line


def test_build_instructions_sorted_by_step_number():
    recipe = SimpleNamespace(instructions=[
        SimpleNamespace(step_number=2, text="Bake"),
        SimpleNamespace(step_number=1, text="Mix"),
    ])
    assert build_instructions(recipe) == [{"text": "Mix"}, {"text": "Bake"}]


def test_build_servings_from_servings_unit():
    recipe = SimpleNamespace(yield_amount=4.0, yield_unit="servings")
    assert build_servings(recipe) == 4.0


def test_build_servings_empty_unit_counts_as_servings():
    recipe = SimpleNamespace(yield_amount=6.0, yield_unit=None)
    assert build_servings(recipe) == 6.0


def test_build_servings_none_for_non_servings_unit():
    recipe = SimpleNamespace(yield_amount=1.0, yield_unit="loaf")
    assert build_servings(recipe) is None


def test_build_yield_empty_when_servings():
    recipe = SimpleNamespace(yield_amount=4.0, yield_unit="servings")
    assert build_yield(recipe) == ""


def test_build_yield_text_for_non_servings():
    recipe = SimpleNamespace(yield_amount=1.0, yield_unit="loaf")
    assert build_yield(recipe) == "1 loaf"


def test_tag_names_prefixes_each_field():
    recipe = SimpleNamespace(
        cuisine="Italian", protein="Chicken",
        difficulty=SimpleNamespace(value="Easy"), diets=[],
    )
    assert tag_names(recipe) == ["Cuisine: Italian", "Protein: Chicken", "Difficulty: Easy"]


def test_tag_names_skips_nulls():
    recipe = SimpleNamespace(cuisine=None, protein="Beef", difficulty=None, diets=[])
    assert tag_names(recipe) == ["Protein: Beef"]


def test_tag_names_includes_diets_dormant_when_empty():
    recipe = SimpleNamespace(
        cuisine=None, protein=None, difficulty=None,
        diets=[SimpleNamespace(diet_type=SimpleNamespace(value="vegan"))],
    )
    assert tag_names(recipe) == ["Diet: vegan"]


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


def _sample_recipe():
    return SimpleNamespace(
        name="Tomato Soup",
        description="Warm and simple",
        yield_amount=4.0, yield_unit="servings",
        prep_time_minutes=10, cook_time_minutes=20, total_time_minutes=30,
        source_url="https://example.com/soup", source="Family recipe",
        calories=180,
        cuisine="Italian", protein=None, difficulty=SimpleNamespace(value="Easy"),
        diets=[],
        components=[_component("Main", [_ri(1.0, "can", "Tomatoes", order=0)])],
        instructions=[SimpleNamespace(step_number=1, text="Simmer")],
        comments=[],
    )


def test_recipe_to_payload_maps_all_fields():
    recipe = _sample_recipe()
    shell = {"id": "abc", "slug": "tomato-soup", "name": "Tomato Soup", "nutrition": {}}
    cat_refs = [{"id": "c1", "name": "Soup", "slug": "soup"}]
    tag_refs = [{"id": "t1", "name": "Cuisine: Italian", "slug": "cuisine-italian"}]
    food_map = {"tomatoes": {"mealie_food": "Tomatoes", "action": "match", "label": "", "flags": ""}}
    unit_map = {"can": {"mealie_unit": "can", "flags": ""}}

    payload = recipe_to_payload(recipe, shell, cat_refs, tag_refs, food_map, unit_map, _FakeResolver())

    assert payload["id"] == "abc"
    assert payload["recipeServings"] == 4.0
    assert payload["recipeYield"] == ""
    assert payload["prepTime"] == "10 minutes"
    assert payload["performTime"] == "20 minutes"
    assert payload["totalTime"] == "30 minutes"
    assert payload["description"] == "Warm and simple"
    assert payload["orgURL"] == "https://example.com/soup"
    assert payload["recipeIngredient"][0]["food"]["name"] == "Tomatoes"
    assert payload["recipeIngredient"][0]["disableAmount"] is False
    assert payload["recipeInstructions"] == [{"text": "Simmer"}]
    assert payload["recipeCategory"] == cat_refs
    assert payload["tags"] == tag_refs
    assert payload["nutrition"]["calories"] == "180"
    assert payload["notes"] == [{"title": "Source", "text": "Family recipe"}]


def _write_csv(tmp_path, name, header, rows):
    import csv
    path = tmp_path / name
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(header)
        writer.writerows(rows)
    return str(path)


def test_load_food_map_parses_rows(tmp_path):
    path = _write_csv(
        tmp_path, "food_map.csv",
        ["source_food", "action", "mealie_food", "label", "flags"],
        [["Kale", "match", "Kale", "Produce", ""],
         ["Rau Sauce", "create", "Rau Sauce", "Sauces", "unmatched"]],
    )
    fm = load_food_map(path)
    assert fm["kale"] == {"mealie_food": "Kale", "action": "match", "label": "Produce", "note": "", "flags": ""}
    assert fm["rau sauce"]["action"] == "create"


def test_load_food_map_rejects_bad_action(tmp_path):
    path = _write_csv(
        tmp_path, "food_map.csv",
        ["source_food", "action", "mealie_food", "label", "flags"],
        [["Kale", "guess", "Kale", "Produce", ""]],
    )
    import pytest
    with pytest.raises(ValueError, match="bad action"):
        load_food_map(path)


def test_load_food_map_rejects_missing_column(tmp_path):
    path = _write_csv(tmp_path, "food_map.csv",
                      ["source_food", "action", "mealie_food"], [["Kale", "match", "Kale"]])
    import pytest
    with pytest.raises(ValueError, match="missing columns"):
        load_food_map(path)


def test_load_unit_map_treats_none_token_as_empty(tmp_path):
    path = _write_csv(
        tmp_path, "unit_map.csv",
        ["source_unit", "mealie_unit", "flags"],
        [["Cup", "cup", ""], ["To Taste", "(none)", "to-taste"]],
    )
    um = load_unit_map(path)
    assert um["cup"] == {"mealie_unit": "cup", "flags": ""}
    assert um["to taste"] == {"mealie_unit": "", "flags": "to-taste"}


def test_load_food_map_handles_comma_in_food_name(tmp_path):
    path = _write_csv(
        tmp_path, "food_map.csv",
        ["source_food", "action", "mealie_food", "label", "flags"],
        [["Tomato Paste, 12 oz", "match", "Tomato Paste", "Canned Goods", "size-stripped"]],
    )
    fm = load_food_map(path)
    assert fm["tomato paste, 12 oz"]["mealie_food"] == "Tomato Paste"


def test_structured_ingredient_zero_quantity_not_to_taste():
    ri = _ri(0, "cup", "Sugar", None, order=0)
    entry = build_structured_ingredient(ri, {"id": "u1"}, {"id": "f1"}, None, to_taste=False)
    assert entry["quantity"] is None
    assert entry["disableAmount"] is True


def test_structured_ingredient_to_taste_preserves_existing_note():
    ri = _ri(0, "To Taste", "Pepper", "freshly ground", order=0)
    entry = build_structured_ingredient(ri, None, {"id": "f3", "name": "Pepper"}, None, to_taste=True)
    assert entry["note"] == "freshly ground"   # existing note kept, not overwritten with "to taste"
    assert entry["disableAmount"] is True


def test_missing_map_entries_reports_unmapped():
    recipe = SimpleNamespace(components=[
        _component("Main", [_ri(1.0, "cup", "Flour", order=0), _ri(2.0, "Shot", "Rum", order=1)]),
    ])
    food_map = {"flour": {"mealie_food": "Flour", "action": "match", "label": "", "flags": ""}}
    unit_map = {"cup": {"mealie_unit": "cup", "flags": ""}}
    foods, units = missing_map_entries([recipe], food_map, unit_map)
    assert foods == ["Rum"]
    assert units == ["Shot"]


def test_missing_map_entries_empty_when_covered():
    recipe = SimpleNamespace(components=[_component("Main", [_ri(1.0, "cup", "Flour", order=0)])])
    food_map = {"flour": {"mealie_food": "Flour", "action": "match", "label": "", "flags": ""}}
    unit_map = {"cup": {"mealie_unit": "cup", "flags": ""}}
    assert missing_map_entries([recipe], food_map, unit_map) == ([], [])


def test_load_food_map_reads_optional_note_column(tmp_path):
    path = _write_csv(
        tmp_path, "food_map.csv",
        ["source_food", "action", "mealie_food", "label", "note", "flags"],
        [["Dijon Mustard, coarse grained", "match", "dijon mustard", "Condiments", "coarse grained", "semantic"]],
    )
    fm = load_food_map(path)
    assert fm["dijon mustard, coarse grained"]["note"] == "coarse grained"


def test_load_food_map_note_defaults_empty_when_column_absent(tmp_path):
    path = _write_csv(
        tmp_path, "food_map.csv",
        ["source_food", "action", "mealie_food", "label", "flags"],
        [["Kale", "match", "Kale", "Produce", ""]],
    )
    fm = load_food_map(path)
    assert fm["kale"]["note"] == ""


def test_structured_ingredient_appends_extra_note():
    ri = _ri(2.0, "cup", "Flour", "sifted", order=0)
    entry = build_structured_ingredient(
        ri, {"id": "u1"}, {"id": "f1"}, None, to_taste=False, extra_note="King Arthur")
    assert entry["note"] == "sifted, King Arthur"


def test_structured_ingredient_extra_note_only():
    ri = _ri(1.0, "tbsp", "Dijon Mustard", None, order=0)
    entry = build_structured_ingredient(
        ri, {"id": "u1"}, {"id": "f1"}, None, to_taste=False, extra_note="coarse grained")
    assert entry["note"] == "coarse grained"


def test_structured_ingredients_threads_food_map_note():
    recipe = SimpleNamespace(components=[
        SimpleNamespace(name="Main", ingredients=[_ri(1.0, "can", "Broth", "low sodium", order=0)]),
    ])
    food_map = {"broth": {"mealie_food": "broth", "action": "match", "label": "", "note": "Swanson's", "flags": ""}}
    unit_map = {"can": {"mealie_unit": "can", "flags": ""}}
    items = build_structured_ingredients(recipe, food_map, unit_map, _FakeResolver())
    assert items[0]["note"] == "low sodium, Swanson's"
