import urllib.error

import pytest

from migration_scripts.mealie_client import MealieClient


def _client():
    return MealieClient("https://mealie.example", "tok")


def test_get_or_create_category_uses_cache_and_creates_missing(monkeypatch):
    client = _client()
    calls = []

    def fake_request(method, path, body=None):
        calls.append((method, path, body))
        if method == "GET" and path.startswith("/api/organizers/categories"):
            return {"items": [{"id": "1", "name": "Soup", "slug": "soup"}]}
        if method == "POST" and path == "/api/organizers/categories":
            return {"id": "2", "name": body["name"], "slug": "dessert"}
        raise AssertionError(f"unexpected {method} {path}")

    monkeypatch.setattr(client, "_request", fake_request)

    # existing (case-insensitive) -> no POST, served from the single GET
    assert client.get_or_create_category("soup")["id"] == "1"
    # missing -> one POST
    assert client.get_or_create_category("Dessert")["id"] == "2"
    # second lookup of the new one is cached -> still only one POST total
    assert client.get_or_create_category("dessert")["id"] == "2"

    assert sum(1 for m, p, _ in calls if m == "POST") == 1
    assert sum(1 for m, p, _ in calls if m == "GET") == 1


def test_recipe_exists_true_false(monkeypatch):
    client = _client()

    def fake_request(method, path, body=None):
        if path.endswith("/exists-slug"):
            return {"slug": "exists-slug"}
        raise urllib.error.HTTPError(path, 404, "Not Found", {}, None)

    monkeypatch.setattr(client, "_request", fake_request)
    assert client.recipe_exists("exists-slug") is True
    assert client.recipe_exists("missing-slug") is False


def test_recipe_exists_reraises_non_404(monkeypatch):
    client = _client()

    def fake_request(method, path, body=None):
        raise urllib.error.HTTPError(path, 500, "Server Error", {}, None)

    monkeypatch.setattr(client, "_request", fake_request)
    with pytest.raises(urllib.error.HTTPError):
        client.recipe_exists("any")


def test_list_foods_unwraps_items(monkeypatch):
    client = _client()
    monkeypatch.setattr(client, "_request",
                        lambda m, p, b=None: {"items": [{"id": "1", "name": "Kale"}]})
    assert client.list_foods() == [{"id": "1", "name": "Kale"}]


def test_create_food_sends_label_id(monkeypatch):
    client = _client()
    seen = {}

    def fake(method, path, body=None):
        seen["call"] = (method, path, body)
        return {"id": "9", "name": body["name"]}

    monkeypatch.setattr(client, "_request", fake)
    out = client.create_food("Rau Sauce", label_id="lab1")
    assert out["id"] == "9"
    assert seen["call"] == ("POST", "/api/foods", {"name": "Rau Sauce", "labelId": "lab1"})


def test_create_food_omits_label_when_none(monkeypatch):
    client = _client()
    seen = {}
    monkeypatch.setattr(client, "_request",
                        lambda m, p, b=None: seen.setdefault("body", b) or {"id": "1", "name": b["name"]})
    client.create_food("Salt", label_id=None)
    assert seen["body"] == {"name": "Salt"}


def test_delete_recipe_true_false(monkeypatch):
    client = _client()

    def fake(method, path, body=None):
        if path.endswith("/gone"):
            raise urllib.error.HTTPError(path, 404, "Not Found", {}, None)
        return None

    monkeypatch.setattr(client, "_request", fake)
    assert client.delete_recipe("here") is True
    assert client.delete_recipe("gone") is False
