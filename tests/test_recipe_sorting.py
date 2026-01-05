
# tests/test_recipe_sorting.py
import pytest
from app import crud, schemas, models
from app.api.recipes import read_recipes

def test_recipes_sorted_by_name(db):
    # Create a test user
    user_in = schemas.UserCreate(
        email="sorting_tester@example.com",
        password="password",
        first_name="Sorting",
        last_name="Tester"
    )
    user = crud.create_user(db, user_in)

    # Create recipes in non-alphabetical order
    recipes_data = [
        "Zucchini Bread",
        "Apple Pie",
        "Banana Cake"
    ]
    
    for name in recipes_data:
        recipe_in = schemas.RecipeCreate(
            core=schemas.RecipeCoreCreate(name=name),
            times=schemas.RecipeTimes(),
            nutrition=schemas.RecipeNutrition(),
            components=[schemas.ComponentCreate(name="Main", ingredients=[])],
            instructions=[]
        )
        crud.create_user_recipe(db=db, recipe=recipe_in, user_id=user.id)
        
    # Retrieve recipes
    recipes, _ = crud.get_recipes(db=db, skip=0, limit=100, sort_by="name")
    
    # Check if they are sorted
    recipe_names = [recipe.name for recipe in recipes]
    assert recipe_names == ["Apple Pie", "Banana Cake", "Zucchini Bread"]
