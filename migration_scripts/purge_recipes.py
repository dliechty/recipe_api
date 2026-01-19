import sys
import os
sys.path.append(os.getcwd())

from app.db.session import SessionLocal
from app.models import Recipe, RecipeComponent, RecipeIngredient, Instruction, Ingredient, Comment

def purge_recipes():
    session = SessionLocal()
    try:
        print("Purging recipe data...")
        
        # Order matters for Foreign Keys
        
        # 0. Comments (depends on Recipe and User)
        deleted_c = session.query(Comment).delete()
        print(f"Deleted {deleted_c} Comments")

        # 1. RecipeIngredient (depends on Component and Ingredient)
        deleted_ri = session.query(RecipeIngredient).delete()
        print(f"Deleted {deleted_ri} RecipeIngredients")
        
        # 2. Instructions (depends on Recipe)
        deleted_ins = session.query(Instruction).delete()
        print(f"Deleted {deleted_ins} Instructions")
        
        # 3. RecipeComponent (depends on Recipe)
        deleted_rc = session.query(RecipeComponent).delete()
        print(f"Deleted {deleted_rc} RecipeComponents")
        
        # 4. Recipe (Root of recipe tree)
        deleted_r = session.query(Recipe).delete()
        print(f"Deleted {deleted_r} Recipes")
        
        # 5. Ingredient (Master list - clearing this for a full clean slate)
        deleted_i = session.query(Ingredient).delete()
        print(f"Deleted {deleted_i} Ingredients")

        session.commit()
        print("Purge complete.")
        
    except Exception as e:
        session.rollback()
        print(f"Error purging data: {e}")
    finally:
        session.close()

if __name__ == "__main__":
    purge_recipes()
