import sys
import os
sys.path.append(os.getcwd())

from app.db.session import SessionLocal
from app.models import Recipe, RecipeComponent, RecipeIngredient, Instruction

def verify():
    session = SessionLocal()
    try:
        count = session.query(Recipe).count()
        print(f"Total Recipes in DB: {count}")
        
        # Check a specific recipe
        recipe = session.query(Recipe).filter(Recipe.name == "Lentil Soup").first()
        if recipe:
            print(f"\nVerifying Recipe: {recipe.name}")
            print(f"Description: {recipe.description}")
            print(f"Yield: {recipe.yield_amount} {recipe.yield_unit}")
            
            print(f"Components: {len(recipe.components)}")
            for comp in recipe.components:
                print(f"  - {comp.name}:")
                for ri in comp.ingredients:
                    print(f"    - {ri.quantity} {ri.unit} {ri.ingredient.name} ({ri.notes})")
            
            print(f"Instructions: {len(recipe.instructions)}")
            for step in recipe.instructions:
                print(f"  {step.step_number}. {step.text}")
        else:
            print("Lentil Soup not found!")

    finally:
        session.close()

if __name__ == "__main__":
    verify()
