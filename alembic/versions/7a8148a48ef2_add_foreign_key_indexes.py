"""add_foreign_key_indexes

Revision ID: 7a8148a48ef2
Revises: 40290659a1a3
Create Date: 2026-01-13 21:13:50.305692

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = '7a8148a48ef2'
down_revision: Union[str, Sequence[str], None] = '40290659a1a3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add indexes to foreign key columns for improved query performance."""
    # Recipe foreign keys
    op.create_index(op.f('ix_recipes_owner_id'), 'recipes', ['owner_id'], unique=False)
    op.create_index(op.f('ix_recipes_parent_recipe_id'), 'recipes', ['parent_recipe_id'], unique=False)

    # RecipeComponent foreign keys
    op.create_index(op.f('ix_recipe_components_recipe_id'), 'recipe_components', ['recipe_id'], unique=False)

    # RecipeIngredient foreign keys
    op.create_index(op.f('ix_recipe_ingredients_component_id'), 'recipe_ingredients', ['component_id'], unique=False)
    op.create_index(op.f('ix_recipe_ingredients_ingredient_id'), 'recipe_ingredients', ['ingredient_id'], unique=False)

    # Instruction foreign keys
    op.create_index(op.f('ix_instructions_recipe_id'), 'instructions', ['recipe_id'], unique=False)

    # Comment foreign keys
    op.create_index(op.f('ix_comments_recipe_id'), 'comments', ['recipe_id'], unique=False)
    op.create_index(op.f('ix_comments_user_id'), 'comments', ['user_id'], unique=False)

    # RecipeDiet foreign keys
    op.create_index(op.f('ix_recipe_diets_recipe_id'), 'recipe_diets', ['recipe_id'], unique=False)

    # MealTemplate foreign keys
    op.create_index(op.f('ix_meal_templates_user_id'), 'meal_templates', ['user_id'], unique=False)

    # MealTemplateSlot foreign keys
    op.create_index(op.f('ix_meal_template_slots_template_id'), 'meal_template_slots', ['template_id'], unique=False)
    op.create_index(op.f('ix_meal_template_slots_recipe_id'), 'meal_template_slots', ['recipe_id'], unique=False)

    # Meal foreign keys
    op.create_index(op.f('ix_meals_user_id'), 'meals', ['user_id'], unique=False)
    op.create_index(op.f('ix_meals_template_id'), 'meals', ['template_id'], unique=False)

    # MealItem foreign keys
    op.create_index(op.f('ix_meal_items_meal_id'), 'meal_items', ['meal_id'], unique=False)
    op.create_index(op.f('ix_meal_items_slot_id'), 'meal_items', ['slot_id'], unique=False)
    op.create_index(op.f('ix_meal_items_recipe_id'), 'meal_items', ['recipe_id'], unique=False)


def downgrade() -> None:
    """Remove foreign key indexes."""
    # MealItem foreign keys
    op.drop_index(op.f('ix_meal_items_recipe_id'), table_name='meal_items')
    op.drop_index(op.f('ix_meal_items_slot_id'), table_name='meal_items')
    op.drop_index(op.f('ix_meal_items_meal_id'), table_name='meal_items')

    # Meal foreign keys
    op.drop_index(op.f('ix_meals_template_id'), table_name='meals')
    op.drop_index(op.f('ix_meals_user_id'), table_name='meals')

    # MealTemplateSlot foreign keys
    op.drop_index(op.f('ix_meal_template_slots_recipe_id'), table_name='meal_template_slots')
    op.drop_index(op.f('ix_meal_template_slots_template_id'), table_name='meal_template_slots')

    # MealTemplate foreign keys
    op.drop_index(op.f('ix_meal_templates_user_id'), table_name='meal_templates')

    # RecipeDiet foreign keys
    op.drop_index(op.f('ix_recipe_diets_recipe_id'), table_name='recipe_diets')

    # Comment foreign keys
    op.drop_index(op.f('ix_comments_user_id'), table_name='comments')
    op.drop_index(op.f('ix_comments_recipe_id'), table_name='comments')

    # Instruction foreign keys
    op.drop_index(op.f('ix_instructions_recipe_id'), table_name='instructions')

    # RecipeIngredient foreign keys
    op.drop_index(op.f('ix_recipe_ingredients_ingredient_id'), table_name='recipe_ingredients')
    op.drop_index(op.f('ix_recipe_ingredients_component_id'), table_name='recipe_ingredients')

    # RecipeComponent foreign keys
    op.drop_index(op.f('ix_recipe_components_recipe_id'), table_name='recipe_components')

    # Recipe foreign keys
    op.drop_index(op.f('ix_recipes_parent_recipe_id'), table_name='recipes')
    op.drop_index(op.f('ix_recipes_owner_id'), table_name='recipes')
