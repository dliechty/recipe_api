import sys
import os

# Add the project root to sys.path
sys.path.append(os.getcwd())

from app.db.session import SessionLocal
from app.models import MealItem, Meal, MealTemplateSlot, MealTemplate, MealTemplateSlotRecipe
from sqlalchemy import text

def purge_meals():
    session = SessionLocal()
    try:
        print("Purging meal and template data...")
        
        # 1. MealItem (depends on Meal and MealTemplateSlot)
        deleted_mi = session.query(MealItem).delete()
        print(f"Deleted {deleted_mi} MealItems")

        # 2. Meal (depends on MealTemplate)
        deleted_m = session.query(Meal).delete()
        print(f"Deleted {deleted_m} Meals")
        
        # 3. MealTemplateSlotRecipe (Many-to-Many for LIST strategy)
        deleted_mtsr = session.query(MealTemplateSlotRecipe).delete()
        print(f"Deleted {deleted_mtsr} MealTemplateSlotRecipes")

        # 4. MealTemplateSlot (depends on MealTemplate)
        deleted_mts = session.query(MealTemplateSlot).delete()
        print(f"Deleted {deleted_mts} MealTemplateSlots")
        
        # 5. MealTemplate
        deleted_mt = session.query(MealTemplate).delete()
        print(f"Deleted {deleted_mt} MealTemplates")

        session.commit()
        print("Purge meals complete.")
        
    except Exception as e:
        session.rollback()
        print(f"Error purging meal data: {e}")
    finally:
        session.close()

if __name__ == "__main__":
    purge_meals()
