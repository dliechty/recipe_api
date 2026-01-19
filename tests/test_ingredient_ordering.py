
from tests.test_recipe_permissions import get_auth_headers

def test_create_recipe_preserves_order(client, db):
    # Setup
    headers = get_auth_headers(client, db, email="order_test@example.com")
    
    # Create Valid Recipe with ingredients in specific order
    recipe_data = {
        "core": {"name": "Ordered Salad"},
        "times": {},
        "nutrition": {},
        "components": [
            {
                "name": "Main",
                "ingredients": [
                    {"quantity": 1, "unit": "cup", "ingredient_name": "Lettuce"},
                    {"quantity": 2, "unit": "tbsp", "ingredient_name": "Dressing"},
                    {"quantity": 3, "unit": "slice", "ingredient_name": "Tomato"}
                ]
            }
        ],
        "instructions": []
    }
    
    # Action
    response = client.post("/recipes/", json=recipe_data, headers=headers)
    assert response.status_code == 201
    created_recipe = response.json()
    
    # Verify
    ingredients = created_recipe["components"][0]["ingredients"]
    assert len(ingredients) == 3, f"Expected 3 ingredients, got {len(ingredients)}"
    assert ingredients[0]["item"] == "Lettuce"
    assert ingredients[1]["item"] == "Dressing"
    assert ingredients[2]["item"] == "Tomato"
    
    # Double check by fetching again to ensure DB persistence order
    recipe_id = created_recipe["core"]["id"]
    get_res = client.get(f"/recipes/{recipe_id}", headers=headers)
    items = [i["item"] for i in get_res.json()["components"][0]["ingredients"]]
    assert items == ["Lettuce", "Dressing", "Tomato"]

def test_update_recipe_reorders_ingredients(client, db):
    # Setup
    headers = get_auth_headers(client, db, email="order_update@example.com")
    
    # Create initial recipe
    recipe_data = {
        "core": {"name": "Reorder Salad"},
        "times": {},
        "nutrition": {},
        "components": [
            {
                "name": "Main",
                "ingredients": [
                    {"quantity": 1, "unit": "cup", "ingredient_name": "B"},
                    {"quantity": 1, "unit": "cup", "ingredient_name": "A"}
                ]
            }
        ],
        "instructions": []
    }
    create_res = client.post("/recipes/", json=recipe_data, headers=headers)
    recipe_id = create_res.json()["core"]["id"]
    
    # Verify initial order
    assert create_res.json()["components"][0]["ingredients"][0]["item"] == "B"
    assert create_res.json()["components"][0]["ingredients"][1]["item"] == "A"
    
    # Action: Update with swapped order
    update_data = recipe_data.copy()
    update_data["components"] = [
        {
            "name": "Main",
            "ingredients": [
                {"quantity": 1, "unit": "cup", "ingredient_name": "A"},
                {"quantity": 1, "unit": "cup", "ingredient_name": "B"}
            ]
        }
    ]
    
    response = client.put(f"/recipes/{recipe_id}", json=update_data, headers=headers)
    assert response.status_code == 200
    updated_recipe = response.json()
    
    # Verify new order
    ingredients = updated_recipe["components"][0]["ingredients"]
    assert ingredients[0]["item"] == "A"
    assert ingredients[1]["item"] == "B"
