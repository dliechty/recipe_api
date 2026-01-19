import pytest
from unittest.mock import patch, MagicMock
import pandas as pd
from app.models import Recipe, Meal, MealTemplate, Ingredient, User, MealStatus, MealClassification
from migration_scripts import purge_recipes, purge_meals, migrate_access_recipes, migrate_access_meals

# Mock Session Factory
class MockSession:
    def __init__(self, real_session):
        self.real_session = real_session
    
    def add(self, obj):
        self.real_session.add(obj)
        
    def flush(self):
        self.real_session.flush()
        
    def commit(self):
        self.real_session.flush() # simulate commit by flushing
        
    def close(self):
        pass # Do nothing
        
    def query(self, *args, **kwargs):
        return self.real_session.query(*args, **kwargs)
        
    def rollback(self):
        self.real_session.rollback()
        
    def delete(self, instance):
        self.real_session.delete(instance)

@pytest.fixture
def mock_session_local(db):
    return lambda: MockSession(db)

def test_purge_recipes(db, mock_session_local):
    # Setup data
    user = User(email="test@example.com", hashed_password="pw", is_active=True)
    db.add(user)
    db.commit()
    
    recipe = Recipe(name="Test Recipe", owner_id=user.id)
    db.add(recipe)
    db.commit()
    
    assert db.query(Recipe).count() == 1
    
    with patch('migration_scripts.purge_recipes.SessionLocal', side_effect=mock_session_local):
        purge_recipes.purge_recipes()
        
    assert db.query(Recipe).count() == 0

def test_purge_meals(db, mock_session_local):
    # Setup data
    user = User(email="test@example.com", hashed_password="pw", is_active=True)
    db.add(user)
    db.commit()
    
    template = MealTemplate(name="Test Template", user_id=user.id)
    db.add(template)
    db.commit()
    
    meal = Meal(name="Test Meal", user_id=user.id, template_id=template.id)
    db.add(meal)
    db.commit()
    
    assert db.query(Meal).count() == 1
    assert db.query(MealTemplate).count() == 1
    
    with patch('migration_scripts.purge_meals.SessionLocal', side_effect=mock_session_local):
        purge_meals.purge_meals()
        
    assert db.query(Meal).count() == 0
    assert db.query(MealTemplate).count() == 0

def test_migrate_recipes(db, mock_session_local):
    # Setup User
    user = User(email="admin@example.com", hashed_password="pw", is_admin=True, is_active=True)
    db.add(user)
    db.commit()
    
    # Mock DataFrames
    df_recipes = pd.DataFrame([
        {
            'Recipe_ID': 1, 'Recipe_Name': 'Test Recipe', 'Recipe_Description': 'Desc', 
            'Recipe_Servings': 4, 'Recipe_Prep_Time': '10min', 'Recipe_Cook_Time': '20min',
            'Complexity_Level_ID': 1, 'Recipe_Type_ID': 1, 'Food_Category_ID': 1,
            'Recipe_Source_ID': 1, 'Recipe_Calories': 500
        }
    ])
    
    df_ingredients = pd.DataFrame([{'Ingredient_ID': 1, 'Ingredient': 'Salt'}])
    df_recipe_ingredients = pd.DataFrame([
        {'Recipe_ID': 1, 'Ingredient_ID': 1, 'Amount_ID': 1, 'Unit_ID': 1, 'Preparation_ID': 1}
    ])
    df_steps = pd.DataFrame([
        {'Recipe_ID': 1, 'Recipe_Step_Num': 1, 'Recipe_Step': 'Do it', 'Recipe_Step_Comment': None}
    ])
    
    # Lookups
    df_amounts = pd.DataFrame([{'Amount_ID': 1, 'Amount_Value': 1.0}])
    df_units = pd.DataFrame([{'Unit_ID': 1, 'Unit': 'tsp'}])
    df_preparations = pd.DataFrame([{'Preparation_ID': 1, 'Preparation': 'chopped'}])
    df_complexity = pd.DataFrame([{'Complexity_Level_ID': 1, 'Complexity_Level_Description': 'Simple'}])
    df_categories = pd.DataFrame([{'Food_Category_ID': 1, 'Food_Category': 'Meat'}])
    df_types = pd.DataFrame([{'Recipe_Type_ID': 1, 'Recipe_Type': 'Dinner'}])
    df_sources = pd.DataFrame([{'Recipe_Source_ID': 1, 'Recipe_Source': 'Mom'}])
    df_notes = pd.DataFrame(columns=['Recipe_ID', 'Recipe_Note_Num', 'Recipe_Note'])

    def mock_run_mdb_export(table_name):
        if table_name == 'tblRecipes': return df_recipes
        if table_name == 'tblIngredients': return df_ingredients
        if table_name == 'tblRecipeIngredients': return df_recipe_ingredients
        if table_name == 'tblRecipeSteps': return df_steps
        if table_name == 'tblAmounts': return df_amounts
        if table_name == 'tblUnits': return df_units
        if table_name == 'tblPreparations': return df_preparations
        if table_name == 'tblComplexityLevels': return df_complexity
        if table_name == 'tblFoodCategories': return df_categories
        if table_name == 'tblRecipeTypes': return df_types
        if table_name == 'tblRecipeSources': return df_sources
        if table_name == 'tblRecipeNotes': return df_notes
        return pd.DataFrame()

    with patch('migration_scripts.migrate_access_recipes.SessionLocal', side_effect=mock_session_local), \
         patch('migration_scripts.migrate_access_recipes.run_mdb_export', side_effect=mock_run_mdb_export), \
         patch('os.path.exists', return_value=True):
        
        migrate_access_recipes.migrate_recipes()
        
    recipe = db.query(Recipe).filter(Recipe.name == "Test Recipe").first()
    assert recipe is not None
    assert recipe.description == "Desc"
    assert recipe.prep_time_minutes == 10
    assert len(recipe.components) == 1
    assert len(recipe.components[0].ingredients) == 1
    assert recipe.components[0].ingredients[0].ingredient.name == "Salt"

def test_migrate_meals(db, mock_session_local):
    from app.models import MealTemplateSlotStrategy
    # Setup User and Recipe
    user = User(email="admin@example.com", hashed_password="pw", is_admin=True, is_active=True)
    db.add(user)
    
    recipe = Recipe(name="Test Recipe", owner_id=user.id)
    db.add(recipe)
    db.commit()
    
    # Mock DataFrames
    df_recipes_old = pd.DataFrame([
        {'Recipe_ID': 101, 'Recipe_Name': 'Test Recipe'},
        {'Recipe_ID': 999, 'Recipe_Name': '<<random veggie>>'}
    ])
    
    df_templates = pd.DataFrame([
        {
            'Meal_Template_ID': 5, 'Meal_Type_ID': 3, 'Meal_Template_Name': 'Test Template'
        }
    ])
    
    df_template_recipes = pd.DataFrame([
        {'Meal_Template_Recipe_ID': 1, 'Meal_Template_ID': 5, 'Recipe_ID': 101},
        {'Meal_Template_Recipe_ID': 2, 'Meal_Template_ID': 5, 'Recipe_ID': 999}
    ])
    
    df_menus = pd.DataFrame([
        {'Menu_ID': 50, 'Menu_Date': '01/01/2026', 'Meal_Type_ID': 3, 'Menu_Status_ID': 1}
    ])
    
    df_menu_recipes = pd.DataFrame([
        {'Menu_Recipe_ID': 1, 'Menu_ID': 50, 'Recipe_ID': 101}
    ])

    def mock_run_mdb_export(table_name):
        if table_name == 'tblRecipes': return df_recipes_old
        if table_name == 'tblMealTemplates': return df_templates
        if table_name == 'tblMealTemplateRecipes': return df_template_recipes
        if table_name == 'tblMenus': return df_menus
        if table_name == 'tblMenuRecipes': return df_menu_recipes
        return pd.DataFrame()

    with patch('migration_scripts.migrate_access_meals.SessionLocal', side_effect=mock_session_local), \
         patch('migration_scripts.migrate_access_meals.run_mdb_export', side_effect=mock_run_mdb_export), \
         patch('os.path.exists', return_value=True):
         
        migrate_access_meals.migrate_meals()
        
    template = db.query(MealTemplate).filter(MealTemplate.name == "Test Template").first()
    assert template is not None
    assert template.classification == MealClassification.DINNER
    assert len(template.slots) == 2
    
    # Check slots
    direct_slot = next(s for s in template.slots if s.strategy == MealTemplateSlotStrategy.DIRECT)
    search_slot = next(s for s in template.slots if s.strategy == MealTemplateSlotStrategy.SEARCH)
    
    assert direct_slot.recipe.name == "Test Recipe"
    assert search_slot.search_criteria == [{"field": "category", "operator": "eq", "value": "Vegetable"}]
    
    meal = db.query(Meal).first()
    assert meal is not None
    assert meal.classification == MealClassification.DINNER
    assert meal.status == MealStatus.COOKED
    assert len(meal.items) == 1
    assert meal.items[0].recipe.name == "Test Recipe"
