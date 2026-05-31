"""Minimal Mealie REST client built on stdlib urllib (no extra deps)."""

import json
import urllib.error
import urllib.request


class MealieClient:
    def __init__(self, base_url: str, token: str):
        self.base = base_url.rstrip("/")
        self.token = token
        self._cat_cache = None
        self._tag_cache = None

    def _request(self, method: str, path: str, body=None):
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(
            f"{self.base}{path}",
            data=data,
            method=method,
            headers={
                "Authorization": f"Bearer {self.token}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
        )
        with urllib.request.urlopen(req) as resp:
            raw = resp.read()
            return json.loads(raw) if raw else None

    # --- recipes ---
    def recipe_exists(self, slug: str) -> bool:
        try:
            self._request("GET", f"/api/recipes/{slug}")
            return True
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                return False
            raise

    def create_recipe(self, name: str) -> str:
        return self._request("POST", "/api/recipes", {"name": name})

    def get_recipe(self, slug: str) -> dict:
        return self._request("GET", f"/api/recipes/{slug}")

    def update_recipe(self, slug: str, payload: dict) -> dict:
        return self._request("PUT", f"/api/recipes/{slug}", payload)

    # --- organizers ---
    def _load(self, kind: str) -> dict:
        resp = self._request("GET", f"/api/organizers/{kind}?perPage=-1")
        items = resp["items"] if isinstance(resp, dict) else resp
        return {item["name"].lower(): item for item in items}

    def _get_or_create(self, kind: str, cache_attr: str, name: str) -> dict:
        cache = getattr(self, cache_attr)
        if cache is None:
            cache = self._load(kind)
            setattr(self, cache_attr, cache)
        key = name.lower()
        if key not in cache:
            cache[key] = self._request("POST", f"/api/organizers/{kind}", {"name": name})
        return cache[key]

    def get_or_create_category(self, name: str) -> dict:
        return self._get_or_create("categories", "_cat_cache", name)

    def get_or_create_tag(self, name: str) -> dict:
        return self._get_or_create("tags", "_tag_cache", name)

    # --- foods / units / labels ---
    def _list(self, path: str) -> list:
        resp = self._request("GET", path)
        return resp["items"] if isinstance(resp, dict) else resp

    def list_foods(self) -> list:
        return self._list("/api/foods?perPage=-1")

    def list_units(self) -> list:
        return self._list("/api/units?perPage=-1")

    def list_labels(self) -> list:
        return self._list("/api/groups/labels?perPage=-1")

    def create_food(self, name: str, label_id: str = None) -> dict:
        body = {"name": name}
        if label_id:
            body["labelId"] = label_id
        return self._request("POST", "/api/foods", body)

    def update_food(self, food_id: str, payload: dict) -> dict:
        return self._request("PUT", f"/api/foods/{food_id}", payload)

    def create_unit(self, name: str) -> dict:
        return self._request("POST", "/api/units", {"name": name})

    def create_label(self, name: str) -> dict:
        return self._request("POST", "/api/groups/labels", {"name": name})

    # --- recipe deletion (for clean re-import) ---
    def delete_recipe(self, slug: str) -> bool:
        try:
            self._request("DELETE", f"/api/recipes/{slug}")
            return True
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                return False
            raise
