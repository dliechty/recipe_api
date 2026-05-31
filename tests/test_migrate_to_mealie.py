import pytest
from types import SimpleNamespace

from migration_scripts.migrate_to_mealie import (
    MealieRefResolver,
    DryRunResolver,
    purge_recipes,
    import_recipe,
)


class _Client:
    def __init__(self):
        self.created_foods, self.created_labels, self.updated = [], [], []

    def list_foods(self):
        return [{"id": "f1", "name": "Kale", "label": {"name": "Produce"}},
                {"id": "f2", "name": "Salt", "label": None}]

    def list_units(self):
        return [{"id": "u1", "name": "cup"}]

    def list_labels(self):
        return [{"id": "l1", "name": "Produce"}]

    def create_label(self, name):
        lab = {"id": f"l-{name}", "name": name}
        self.created_labels.append(name)
        return lab

    def create_food(self, name, label_id=None):
        food = {"id": f"f-{name}", "name": name, "label": {"id": label_id}}
        self.created_foods.append((name, label_id))
        return food

    def update_food(self, food_id, payload):
        self.updated.append(food_id)
        return {**payload, "id": food_id}


def test_resolve_unit_existing_and_none():
    r = MealieRefResolver(_Client())
    assert r.resolve_unit("cup") == {"id": "u1", "name": "cup"}
    assert r.resolve_unit("") is None
    assert r.resolve_unit("(none)") is None


def test_resolve_unit_missing_raises():
    r = MealieRefResolver(_Client())
    with pytest.raises(KeyError, match="unit"):
        r.resolve_unit("furlong")


def test_resolve_food_match_existing():
    r = MealieRefResolver(_Client())
    assert r.resolve_food("Kale", "match", "Produce") == {"id": "f1", "name": "Kale"}


def test_resolve_food_match_missing_raises():
    r = MealieRefResolver(_Client())
    with pytest.raises(KeyError, match="food"):
        r.resolve_food("Unicorn", "match", "")


def test_resolve_food_match_assigns_missing_label():
    client = _Client()
    r = MealieRefResolver(client)
    r.resolve_food("Salt", "match", "Pantry")  # Salt has no label -> update + new label
    assert client.created_labels == ["Pantry"]
    assert client.updated == ["f2"]


def test_resolve_food_create_makes_food_and_caches():
    client = _Client()
    r = MealieRefResolver(client)
    a = r.resolve_food("Rau Sauce", "create", "Sauces")
    b = r.resolve_food("Rau Sauce", "create", "Sauces")
    assert a == b
    assert client.created_foods == [("Rau Sauce", "l-Sauces")]   # created once
    assert client.created_labels == ["Sauces"]


def test_dry_run_resolver_returns_name_stubs():
    r = DryRunResolver()
    assert r.resolve_unit("cup") == {"name": "cup"}
    assert r.resolve_unit("") is None
    assert r.resolve_food("Kale", "match", "Produce") == {"name": "Kale"}


def test_resolve_food_create_existing_assigns_missing_label():
    client = _Client()
    r = MealieRefResolver(client)
    # "Salt" already exists with label None; create action should assign the label, not recreate
    r.resolve_food("Salt", "create", "Pantry")
    assert client.created_foods == []         # not recreated
    assert client.created_labels == ["Pantry"]
    assert client.updated == ["f2"]


def test_resolve_food_create_existing_with_label_no_update():
    client = _Client()
    r = MealieRefResolver(client)
    # "Kale" already exists WITH a label; no update, no create
    assert r.resolve_food("Kale", "create", "Produce") == {"id": "f1", "name": "Kale"}
    assert client.created_foods == []
    assert client.updated == []


def test_resolve_food_label_assigned_at_most_once():
    client = _Client()
    r = MealieRefResolver(client)
    r.resolve_food("Salt", "match", "Pantry")
    r.resolve_food("Salt", "match", "Pantry")   # second call must NOT update again
    assert client.updated == ["f2"]


def test_dry_run_resolver_none_sentinel_unit():
    assert DryRunResolver().resolve_unit("(none)") is None


def _recipe():
    ing = SimpleNamespace(quantity=1.0, unit="cup", notes=None, order=0,
                          ingredient=SimpleNamespace(name="Flour"))
    return SimpleNamespace(
        name="Bread", description="", yield_amount=2.0, yield_unit="servings",
        prep_time_minutes=None, cook_time_minutes=None, total_time_minutes=None,
        source_url=None, source=None, calories=None,
        cuisine=None, protein=None, difficulty=None, diets=[],
        category=None, comments=[],
        components=[SimpleNamespace(name="Main", ingredients=[ing])],
        instructions=[],
    )


def test_purge_recipes_deletes_each_slug():
    deleted = []

    class C:
        def delete_recipe(self, slug):
            deleted.append(slug)
            return True

    assert purge_recipes(C(), [_recipe()]) == 1
    assert deleted == ["bread"]


def test_import_recipe_dry_run_builds_structured(capsys):
    fm = {"flour": {"mealie_food": "Flour", "action": "match", "label": "", "flags": ""}}
    um = {"cup": {"mealie_unit": "cup", "flags": ""}}
    result = import_recipe(None, _recipe(), True, True, fm, um, DryRunResolver())
    assert result == "created"
    assert "Bread" in capsys.readouterr().out
