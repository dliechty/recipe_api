import csv
import io
import os
import subprocess
import sys
from io import StringIO
from typing import Dict, List, Optional, Tuple
import re
import uuid

import pandas as pd
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

# Add the current directory to sys.path to make imports work
sys.path.append(os.getcwd())

from app.db.session import SessionLocal, engine
from app.models import (
    Recipe,
    RecipeComponent,
    Ingredient,
    RecipeIngredient,
    Instruction,
    User,
    DifficultyLevel,
    Comment,
)

# Database path
DB_PATH = "migrate_data/Recipes.accdb"

def run_mdb_export(table_name: str) -> pd.DataFrame:
    """Exports a table from the Access database to a Pandas DataFrame."""
    print(f"Exporting {table_name}...")
    try:
        # Run mdb-export
        result = subprocess.run(
            ["mdb-export", DB_PATH, table_name],
            capture_output=True,
            text=True,
            check=True
        )
        # Parse CSV output into DataFrame
        return pd.read_csv(StringIO(result.stdout))
    except subprocess.CalledProcessError as e:
        print(f"Error exporting {table_name}: {e}")
        print(e.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Error processing {table_name}: {e}")
        sys.exit(1)

def get_or_create_user(session: Session, email: str = "admin@example.com") -> User:
    """Gets an existing user or returns the first admin user."""
    user = session.query(User).filter(User.email == email).first()
    if user:
        return user
    
    # Fallback to any admin
    user = session.query(User).filter(User.is_admin == True).first()
    if user:
        print(f"User {email} not found. Using admin: {user.email}")
        return user
        
    print("No users found. Please create a user first.")
    sys.exit(1)

def clean_text(text):
    if pd.isna(text):
        return None
    s = str(text).strip()
    return s if s else None

def map_difficulty(complexity_id: int, complexity_map: Dict[int, str]) -> Optional[DifficultyLevel]:
    desc = complexity_map.get(complexity_id)
    if not desc:
        return None
    desc_lower = desc.lower()
    if "simple" in desc_lower:
        return DifficultyLevel.EASY
    if "basic" in desc_lower or "moderate" in desc_lower:
        return DifficultyLevel.MEDIUM
    if "difficult" in desc_lower or "complex" in desc_lower:
        return DifficultyLevel.HARD
    return DifficultyLevel.MEDIUM

def parse_time_minutes(time_str: str) -> Optional[int]:
    """Parses time strings like '10min', '1hr 30min', '5 mn' into total minutes."""
    if not isinstance(time_str, str):
        return None
    
    s = time_str.lower().strip()
    if not s:
        return None

    # Regex for number and unit
    p_hour = r'(?:h|hr|hrs|hour|hours)'
    p_min = r'(?:m|mn|min|mins|minute|minutes)'
    
    # Pattern: number followed optionally by space, then unit
    pattern = re.compile(f'(\\d+(?:\\.\\d+)?)\s*({p_hour}|{p_min})')
    
    matches = pattern.findall(s)
    
    total_minutes = 0
    match_found = False
    
    for val, unit in matches:
        match_found = True
        try:
            v = float(val)
            if any(h in unit for h in ['h', 'hour']):
                total_minutes += v * 60
            else:
                total_minutes += v
        except ValueError:
            pass
            
    if match_found:
        return int(total_minutes)
    
    # Try parsing just as number if regex failed
    try:
        return int(float(s))
    except:
        return None

def should_skip_recipe(name: str) -> bool:
    """Checks if a recipe name indicates it's a meta-recipe (<<name>>)."""
    if not name:
        return False
    s = name.strip()
    return s.startswith("<<") and s.endswith(">>")


def normalize_ingredient(quantity: float, unit: str) -> Tuple[float, str]:
    """
    Normalizes ingredient quantity and unit.
    specifically maps 0 quantity 'As Needed' to 'To Taste'.
    """
    if quantity == 0 and unit and unit.lower() in ["as needed", "as desired"]:
        return 0, "To Taste"
    return quantity, unit


def map_protein(category_id: int, category_map: Dict[int, str]) -> Optional[str]:
    """Maps Food Category ID to Protein string, with exclusions."""
    if pd.isna(category_id):
        return None
    
    category_name = category_map.get(category_id)
    if not category_name:
        return None
        
    # Exclusion list
    exclusions = ["Grain", "Vegetable", "Fruit", "Other"]
    if category_name in exclusions:
        return None
        
    return category_name


def fix_ingredient_precision(qty_val: float) -> float:
    """
    Fixes precision issues from Access migration.
    Converts .33 -> .333
    Converts .66 -> .666
    Converts .12 -> .125
    """
    if isinstance(qty_val, float):
        s_val = str(qty_val)
        if s_val.endswith('.33'):
            return float(s_val + '3')
        elif s_val.endswith('.66'):
            return float(s_val + '6')
        elif s_val.endswith('.12'):
            return float(s_val + '5')
    return qty_val


def migrate():
    if not os.path.exists(DB_PATH):
        print(f"Database file not found at {DB_PATH}")
        sys.exit(1)

    # 1. Load Data
    df_recipes = run_mdb_export("tblRecipes")
    df_ingredients = run_mdb_export("tblIngredients")
    df_recipe_ingredients = run_mdb_export("tblRecipeIngredients")
    df_steps = run_mdb_export("tblRecipeSteps")
    
    # Lookups
    df_amounts = run_mdb_export("tblAmounts")
    df_units = run_mdb_export("tblUnits")
    df_preparations = run_mdb_export("tblPreparations")
    df_complexity = run_mdb_export("tblComplexityLevels")
    df_complexity = run_mdb_export("tblComplexityLevels")
    df_categories = run_mdb_export("tblFoodCategories")
    df_types = run_mdb_export("tblRecipeTypes")
    df_sources = run_mdb_export("tblRecipeSources")
    df_notes = run_mdb_export("tblRecipeNotes")

    # 2. Prepare Maps
    # Amount ID -> Value/Desc
    amount_map = {}
    for _, row in df_amounts.iterrows():
        # Prefer value, then Amount string
        val = row.get('Amount_Value')
        if pd.notna(val):
             amount_map[row['Amount_ID']] = val
        else:
             amount_map[row['Amount_ID']] = row['Amount']

    # Unit ID -> Name
    unit_map = df_units.set_index('Unit_ID')['Unit'].to_dict()
    
    # Prep ID -> Name
    prep_map = df_preparations.set_index('Preparation_ID')['Preparation'].to_dict()
    
    # Complexity ID -> Description
    complexity_map = df_complexity.set_index('Complexity_Level_ID')['Complexity_Level_Description'].to_dict()
    
    # Category ID -> Name (Mapped to Protein)
    food_category_map = df_categories.set_index('Food_Category_ID')['Food_Category'].to_dict() if not df_categories.empty else {}
    
    # Type ID -> Name (New Category)
    type_map = df_types.set_index('Recipe_Type_ID')['Recipe_Type'].to_dict() if not df_types.empty else {}

    # Source ID -> Name
    source_map = df_sources.set_index('Recipe_Source_ID')['Recipe_Source'].to_dict() if not df_sources.empty else {}

    # Ingredient ID -> Name
    ingredient_map = df_ingredients.set_index('Ingredient_ID')['Ingredient'].to_dict()

    session = SessionLocal()
    try:
        user = get_or_create_user(session)
        
        # Track ingredients to avoid duplicates
        # Name -> Ingredient Object
        existing_ingredients = {ing.name.lower(): ing for ing in session.query(Ingredient).all()}
        
        print(f"Found {len(df_recipes)} recipes to migrate.")

        for _, row in df_recipes.iterrows():
            recipe_id_old = row['Recipe_ID']
            name = row['Recipe_Name']
            
            # Check if recipe exists
            existing_recipe = session.query(Recipe).filter(Recipe.name == name).first()
            if existing_recipe:
                print(f"Skipping existing recipe: {name}")
                continue

            if should_skip_recipe(name):
                print(f"Skipping meta-recipe: {name}")
                continue


            print(f"Migrating: {name}")

            # Create Recipe
            recipe = Recipe(
                name=name,
                description=clean_text(row.get('Recipe_Description')),
                yield_amount=pd.to_numeric(row.get('Recipe_Servings'), errors='coerce'),
                yield_unit="servings",
                difficulty=map_difficulty(row.get('Complexity_Level_ID'), complexity_map),
                category=type_map.get(row.get('Recipe_Type_ID')),
                protein=map_protein(row.get('Food_Category_ID'), food_category_map),

                prep_time_minutes=parse_time_minutes(row.get('Recipe_Prep_Time')),
                cook_time_minutes=parse_time_minutes(row.get('Recipe_Cook_Time')),
                calories=pd.to_numeric(row.get('Recipe_Calories'), errors='coerce'),
                owner_id=user.id,
                source=source_map.get(row.get('Recipe_Source_ID'))
            )
            
            # Calculate Total Time
            p = recipe.prep_time_minutes or 0
            c = recipe.cook_time_minutes or 0
            if p > 0 or c > 0:
                recipe.total_time_minutes = p + c

            session.add(recipe)
            session.flush() # Get ID

            # Create Main Component
            component = RecipeComponent(name="Main", recipe_id=recipe.id)
            session.add(component)
            session.flush()

            # Process Ingredients
            # Filter ingredients for this recipe
            recipe_ings = df_recipe_ingredients[df_recipe_ingredients['Recipe_ID'] == recipe_id_old]
            
            for idx, (_, ing_row) in enumerate(recipe_ings.iterrows()):
                ing_id_old = ing_row['Ingredient_ID']
                ing_name = ingredient_map.get(ing_id_old, "Unknown Ingredient")
                
                # Get or Create Ingredient Master
                db_ingredient = existing_ingredients.get(ing_name.lower())
                if not db_ingredient:
                    db_ingredient = Ingredient(name=ing_name)
                    session.add(db_ingredient)
                    session.flush()
                    existing_ingredients[ing_name.lower()] = db_ingredient
                
                # Resolving Quantity/Unit
                amt_id = ing_row.get('Amount_ID')
                unit_id = ing_row.get('Unit_ID')
                prep_id = ing_row.get('Preparation_ID')
                
                qty_val = 0
                qty_note = ""
                
                raw_amt = amount_map.get(amt_id)
                if isinstance(raw_amt, (int, float)):
                    qty_val = raw_amt
                else:
                    try:
                        qty_val = float(raw_amt)
                    except:
                        # If amount is text like "1-2", default 1 and put in notes
                        qty_val = 1
                        qty_note = f"Amount: {raw_amt}"
                
                # Fix precision for .33, .66, and .12 to be .333, .666, and .125
                qty_val = fix_ingredient_precision(qty_val)

                unit_name = unit_map.get(unit_id, "")
                
                # Normalize Ingredient (Handle 'As Needed' -> 'To Taste')
                qty_val, unit_name = normalize_ingredient(qty_val, unit_name)
                prep_text = prep_map.get(prep_id)
                
                final_notes = []
                if qty_note: final_notes.append(qty_note)
                if prep_text: final_notes.append(prep_text)
                
                ri = RecipeIngredient(
                    component_id=component.id,
                    ingredient_id=db_ingredient.id,
                    quantity=qty_val,
                    unit=unit_name,
                    notes=", ".join(final_notes) if final_notes else None,
                    order=idx
                )
                session.add(ri)

            # Process Steps
            recipe_steps = df_steps[df_steps['Recipe_ID'] == recipe_id_old].sort_values('Recipe_Step_Num')
            for _, step_row in recipe_steps.iterrows():
                
                text = clean_text(step_row['Recipe_Step'])
                comment = clean_text(step_row.get('Recipe_Step_Comment'))
                
                full_text = text
                if comment:
                    full_text = f"{text} ({comment})"
                
                if not full_text:
                    continue

                instruction = Instruction(
                    step_number=int(step_row['Recipe_Step_Num']),
                    text=full_text,
                    recipe_id=recipe.id
                )

                session.add(instruction)

            # Process Notes as Comments
            recipe_notes = df_notes[df_notes['Recipe_ID'] == recipe_id_old].sort_values('Recipe_Note_Num')
            
            migrated_notes = []
            for _, note_row in recipe_notes.iterrows():
                note_text = clean_text(note_row.get('Recipe_Note'))
                if note_text:
                    migrated_notes.append(note_text)
            
            if migrated_notes:
                combined_notes = "\n".join(migrated_notes)
                comment = Comment(
                    text=f"Migrated Note:\n\n{combined_notes}",
                    user_id=user.id,
                    recipe_id=recipe.id
                )
                session.add(comment)

            session.commit()
            print(f"Migrated {name} successfully.")

    except Exception as e:
        print(f"Migration failed: {e}")
        session.rollback()
        raise
    finally:
        session.close()

if __name__ == "__main__":
    migrate()
