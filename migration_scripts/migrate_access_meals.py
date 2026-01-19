import sys
import os
import pandas as pd
from typing import Optional
from datetime import datetime

# Add the project root to sys.path
sys.path.append(os.getcwd())

from app.db.session import SessionLocal
from app.models import (
    Recipe,
    MealTemplate,
    MealTemplateSlot,
    MealTemplateSlotStrategy,
    MealClassification,
    Meal,
    MealStatus,
    MealItem
)
from migration_scripts.utils import run_mdb_export, get_or_create_user, clean_text, DB_PATH

def map_classification(type_id: int) -> Optional[MealClassification]:
    # 1: Breakfast, 2: Lunch, 3: Dinner, 4: Appetizers, 5: Snack
    mapping = {
        1: MealClassification.BREAKFAST,
        2: MealClassification.LUNCH,
        3: MealClassification.DINNER,
        4: MealClassification.SNACK,
        5: MealClassification.SNACK
    }
    return mapping.get(type_id)

WILDCARD_MAP = {
    "<<random veggie>>": [{"field": "category", "operator": "eq", "value": "Vegetable"}],
    "<<random salad>>": [{"field": "category", "operator": "eq", "value": "Salad"}],
    "<<random bread>>": [{"field": "category", "operator": "eq", "value": "Bread"}],
    "<<random carb>>": [{"field": "category", "operator": "eq", "value": "Carb"}],
    "<<random dessert>>": [{"field": "category", "operator": "eq", "value": "Dessert"}],
    "<<random appetizer>>": [{"field": "category", "operator": "eq", "value": "Appetizer"}],
}

def migrate_meals():
    if not os.path.exists(DB_PATH):
        print(f"Database file not found at {DB_PATH}")
        sys.exit(1)

    print("Loading Access data...")
    df_recipes_old = run_mdb_export("tblRecipes")
    df_templates = run_mdb_export("tblMealTemplates")
    df_template_recipes = run_mdb_export("tblMealTemplateRecipes")
    df_menus = run_mdb_export("tblMenus")
    df_menu_recipes = run_mdb_export("tblMenuRecipes")

    session = SessionLocal()
    try:
        user = get_or_create_user(session)
        
        # 1. Build Recipe ID Map (Old ID -> New UUID)
        print("Building Recipe Map...")
        # Map Old ID -> Recipe Name
        old_id_to_name = {}
        for _, row in df_recipes_old.iterrows():
            old_id_to_name[row['Recipe_ID']] = row['Recipe_Name']
            
        # Map Recipe Name -> New UUID
        # Load all recipes from DB
        all_recipes = session.query(Recipe).all()
        name_to_uuid = {r.name: r.id for r in all_recipes}
        
        old_id_to_uuid = {}
        missing_recipes = 0
        for old_id, name in old_id_to_name.items():
            if name in name_to_uuid:
                old_id_to_uuid[old_id] = name_to_uuid[name]
            else:
                # print(f"Warning: Recipe '{name}' (ID: {old_id}) not found in new DB.")
                missing_recipes += 1
        
        print(f"Mapped {len(old_id_to_uuid)} recipes. Missing {missing_recipes} recipes.")

        # 2. Migrate Templates
        print(f"Migrating {len(df_templates)} Meal Templates...")
        
        # Map Template ID -> New UUID
        template_id_map = {}
        
        for _, row in df_templates.iterrows():
            old_id = row['Meal_Template_ID']
            name = clean_text(row['Meal_Template_Name'])
            if not name:
                # Use description if name is missing
                name = clean_text(row.get('Meal_Template_Description'))
            if not name:
                name = f"Template {old_id}"
                
            cls = map_classification(row.get('Meal_Type_ID'))
            
            template = MealTemplate(
                user_id=user.id,
                name=name,
                classification=cls
            )
            session.add(template)
            session.flush()
            template_id_map[old_id] = template.id
            
        # 3. Migrate Template Slots
        print(f"Migrating {len(df_template_recipes)} Template Slots...")
        for _, row in df_template_recipes.iterrows():
            old_tmpl_id = row['Meal_Template_ID']
            old_recipe_id = row['Recipe_ID']
            
            new_tmpl_id = template_id_map.get(old_tmpl_id)
            recipe_name = old_id_to_name.get(old_recipe_id)
            
            if not new_tmpl_id:
                continue

            # Check for Wildcard
            if recipe_name and recipe_name in WILDCARD_MAP:
                slot = MealTemplateSlot(
                    template_id=new_tmpl_id,
                    strategy=MealTemplateSlotStrategy.SEARCH,
                    search_criteria=WILDCARD_MAP[recipe_name]
                )
                session.add(slot)
                continue
            
            new_recipe_id = old_id_to_uuid.get(old_recipe_id)
            
            if new_recipe_id:
                slot = MealTemplateSlot(
                    template_id=new_tmpl_id,
                    strategy=MealTemplateSlotStrategy.DIRECT,
                    recipe_id=new_recipe_id
                )
                session.add(slot)
                
        # 4. Migrate Meals (Menus)
        # Only migrate meals that have at least one recipe link
        menu_ids_with_recipes = set(df_menu_recipes['Menu_ID'].unique())
        df_menus_with_recipes = df_menus[df_menus['Menu_ID'].isin(menu_ids_with_recipes)]

        skipped_meals = len(df_menus) - len(df_menus_with_recipes)
        print(f"Migrating {len(df_menus_with_recipes)} Meals (skipping {skipped_meals} with no recipes)...")

        # Map Menu ID -> New UUID
        meal_id_map = {}

        for _, row in df_menus_with_recipes.iterrows():
            old_id = row['Menu_ID']
            date_str = row['Menu_Date']
            
            meal_date = None
            try:
                # Format appears to be "MM/DD/YY HH:MM:SS" or similar
                meal_date = pd.to_datetime(date_str).to_pydatetime()
            except:
                pass
            
            cls = map_classification(row.get('Meal_Type_ID'))
            
            if meal_date is None:
                status = MealStatus.DRAFT
            elif meal_date < datetime.now():
                status = MealStatus.COOKED
            else:
                status = MealStatus.SCHEDULED
            
            # Name: e.g. "Dinner on 2023-04-24"
            name = f"{cls.value if cls else 'Meal'} on {meal_date.strftime('%Y-%m-%d') if meal_date else 'Unknown Date'}"
            
            meal = Meal(
                user_id=user.id,
                name=name,
                status=status,
                classification=cls,
                date=meal_date
            )
            session.add(meal)
            session.flush()
            meal_id_map[old_id] = meal.id
            
        # 5. Migrate Meal Items (Menu Recipes)
        print(f"Migrating {len(df_menu_recipes)} Meal Items...")
        for _, row in df_menu_recipes.iterrows():
            old_menu_id = row['Menu_ID']
            old_recipe_id = row['Recipe_ID']
            
            new_meal_id = meal_id_map.get(old_menu_id)
            new_recipe_id = old_id_to_uuid.get(old_recipe_id)
            
            if new_meal_id and new_recipe_id:
                item = MealItem(
                    meal_id=new_meal_id,
                    recipe_id=new_recipe_id
                )
                session.add(item)

        session.commit()
        print("Meal migration complete.")

    except Exception as e:
        print(f"Migration failed: {e}")
        session.rollback()
        raise
    finally:
        session.close()

if __name__ == "__main__":
    migrate_meals()
