
import pytest
from unittest.mock import patch, MagicMock
import pandas as pd
from datetime import datetime
from app.models import Recipe, Meal, MealStatus, MealClassification, User
from migration_scripts import migrate_access_meals

# Mock Session Factory (copied from test_migration_scripts.py)
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

def test_migrate_meals_status_logic(db, mock_session_local):
    # Setup User and Recipe
    user = User(email="admin@example.com", hashed_password="pw", is_admin=True, is_active=True)
    db.add(user)
    
    recipe = Recipe(name="Test Recipe", owner_id=user.id)
    db.add(recipe)
    db.commit()
    
    # Mock DataFrames
    # We only care about menus and menu recipes for this test
    
    df_recipes_old = pd.DataFrame([
        {'Recipe_ID': 101, 'Recipe_Name': 'Test Recipe'}
    ])
    
    df_templates = pd.DataFrame([])
    df_template_recipes = pd.DataFrame([])
    
    # Define 3 meals: Past, Future, None
    df_menus = pd.DataFrame([
        # Past -> COOKED
        {'Menu_ID': 1, 'Menu_Date': '01/01/2025', 'Meal_Type_ID': 3, 'Menu_Status_ID': 1},
        # Future -> SCHEDULED
        {'Menu_ID': 2, 'Menu_Date': '01/01/2027', 'Meal_Type_ID': 3, 'Menu_Status_ID': 1},
        # None -> DRAFT
        {'Menu_ID': 3, 'Menu_Date': None, 'Meal_Type_ID': 3, 'Menu_Status_ID': 1}
    ])
    
    df_menu_recipes = pd.DataFrame([
        {'Menu_Recipe_ID': 1, 'Menu_ID': 1, 'Recipe_ID': 101},
        {'Menu_Recipe_ID': 2, 'Menu_ID': 2, 'Recipe_ID': 101},
        {'Menu_Recipe_ID': 3, 'Menu_ID': 3, 'Recipe_ID': 101}
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
    
    # Verify statuses
    # 1. Past
    meal_past = db.query(Meal).filter(Meal.name.like("%Unknown Date%") == False).filter(Meal.date < datetime.now()).first()
    # Or just iterate by ID order if we can rely on insertion order, but better filter by date or assume count
    
    meals = db.query(Meal).all()
    # Sort by creation or something to match inputs? 
    # The loop iterates df_menus.
    
    # Retrieve based on expected dates
    # We used '01/01/2025' for past
    meal_past = [m for m in meals if m.date and m.date.year == 2025][0]
    assert meal_past.status == MealStatus.COOKED
    
    # We used '01/01/2027' for future
    meal_future = [m for m in meals if m.date and m.date.year == 2027][0]
    assert meal_future.status == MealStatus.SCHEDULED
    
    # We used None for draft
    meal_draft = [m for m in meals if m.date is None][0]
    assert meal_draft.status == MealStatus.DRAFT
