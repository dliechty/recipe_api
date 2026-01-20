# app/filters.py
from typing import List, Any
from sqlalchemy.orm import Query
from sqlalchemy import asc, desc, or_, case
from uuid import UUID
import re

from app import models

class Filter:
    def __init__(self, field: str, operator: str, value: Any):
        self.field = field
        self.operator = operator
        self.value = value

    def __repr__(self):
        return f"Filter({self.field} {self.operator} {self.value})"

ALLOWED_FIELDS = {
    'id': models.Recipe.id,
    'name': models.Recipe.name,
    'description': models.Recipe.description,
    'category': models.Recipe.category,
    'cuisine': models.Recipe.cuisine,
    'difficulty': models.Recipe.difficulty,
    'protein': models.Recipe.protein,
    'yield_amount': models.Recipe.yield_amount,
    'calories': models.Recipe.calories,
    'prep_time_minutes': models.Recipe.prep_time_minutes,
    'cook_time_minutes': models.Recipe.cook_time_minutes,
    'active_time_minutes': models.Recipe.active_time_minutes,
    'total_time_minutes': models.Recipe.total_time_minutes,
    # 'owner': models.User.email, # Special handling for relationships often needed
    # 'ingredients': 'ingredients', # Special handling
    # 'suitable_for_diet': 'suitable_for_diet' # Also special
}

SORT_FIELDS = {
    'created_at': models.Recipe.created_at,
    'updated_at': models.Recipe.updated_at,
    'name': models.Recipe.name,
    'calories': models.Recipe.calories,
    'total_time_minutes': models.Recipe.total_time_minutes,
    'difficulty': models.Recipe.difficulty,
    'category': models.Recipe.category,
    'cuisine': models.Recipe.cuisine,
    'prep_time_minutes': models.Recipe.prep_time_minutes,
    'cook_time_minutes': models.Recipe.cook_time_minutes,
    'active_time_minutes': models.Recipe.active_time_minutes,
    'yield_amount': models.Recipe.yield_amount,
    'protein': models.Recipe.protein,
}

MEAL_SORT_FIELDS = {
    'date': models.Meal.date,
    'classification': models.Meal.classification,
    'status': models.Meal.status,
    'created_at': models.Meal.created_at,
    'updated_at': models.Meal.updated_at,
    'name': models.Meal.name,
}

MEAL_TEMPLATE_SORT_FIELDS = {
    'created_at': models.MealTemplate.created_at,
    'updated_at': models.MealTemplate.updated_at,
    'name': models.MealTemplate.name,
    'classification': models.MealTemplate.classification,
}

# Allowed filter fields for Meals
ALLOWED_FIELDS_MEAL = {
    'id': models.Meal.id,
    'name': models.Meal.name,
    'status': models.Meal.status,
    'classification': models.Meal.classification,
    'date': models.Meal.date,
    'created_at': models.Meal.created_at,
    'updated_at': models.Meal.updated_at,
}

# Allowed filter fields for Meal Templates
ALLOWED_FIELDS_MEAL_TEMPLATE = {
    'id': models.MealTemplate.id,
    'name': models.MealTemplate.name,
    'classification': models.MealTemplate.classification,
    'created_at': models.MealTemplate.created_at,
    'updated_at': models.MealTemplate.updated_at,
}

def parse_filters(query_params: dict) -> List[Filter]:
    filters = []
    # Pattern to match field[operator]=value
    pattern = re.compile(r"^(\w+)\[(\w+)\]$")

    for key, value in query_params.items():
        match = pattern.match(key)
        if match:
            field, operator = match.groups()
            
            # Basic validation could happen here or during application
            filters.append(Filter(field, operator, value))
        elif key == "name" and "name[like]" not in query_params:
             # Support simple ?name=foo as alias for ?name[like]=foo logic if desired? 
             # Or strict adherence to bracket syntax?
             # User requested LHS brackets pattern. Stick to that mostly, but raw name= search is common.
             # User said: "Name (LIKE sub-string query)" and "LHS brackets pattern for query parameters"
             # Let's assume strict bracket usage is preferred but maybe accept name= as strict match?
             # Actually, user wants 'Text search (LIKE query for name)' supported.
             pass

    return filters

def apply_filters(query: Query, filters: List[Filter]) -> Query:
    for f in filters:
        
        # Special handling for Name
        if f.field == 'name':
            if f.operator == 'like':
                query = query.filter(models.Recipe.name.ilike(f"%{f.value}%"))
            elif f.operator == 'eq':
                query = query.filter(models.Recipe.name == f.value)
            continue
            
        # Special handling for Ingredients (List of strings?)
        # "array inclusion (in clause)"
        # This implies checking if recipe HAS one of these ingredients? 
        # Or has ALL?
        # User said: "array inclusion (in clause)" and "has all (and clause)"
        # Let's assume:
        # ingredients[in]=milk,eggs  -> Recipe has EITHER milk OR eggs (Any overlap)
        # ingredients[all]=milk,eggs -> Recipe has BOTH milk AND eggs (Subset)
        
        if f.field == 'ingredients':
            val_list = f.value.split(',')
            if f.operator == 'in':
                # Join with RecipeIngredient -> Ingredient
                query = query.join(models.RecipeComponent).join(models.RecipeIngredient).join(models.Ingredient)
                query = query.filter(models.Ingredient.name.in_(val_list))
                # Distinct needed because one recipe matches multiple times?
                # query = query.distinct() # Probably done at end or grouped
            elif f.operator == 'all':
                # For "ALL", we need multiple EXISTS or Having Count logic.
                # A simple way for "contains all ingredients":
                for ing in val_list:
                    # Aliased subquery or multiple joins? 
                    # Multiple joins is heavy but clear.
                    # Or:
                    query = query.filter(models.Recipe.components.any(
                        models.RecipeComponent.ingredients.any(
                           models.RecipeIngredient.ingredient.has(models.Ingredient.name == ing)
                        )
                    ))
            elif f.operator == 'like':
                 # Partial match on any ingredient
                 # Similar to 'in' but with ilike.
                 # Since it's 'like', usually implies ANY ingredient matches pattern.
                 # "chicken" -> matches "Chicken Breast", "Roast Chicken", etc.
                 query = query.join(models.RecipeComponent).join(models.RecipeIngredient).join(models.Ingredient)
                 query = query.filter(models.Ingredient.name.ilike(f"%{f.value}%"))
            continue

        if f.field == 'suitable_for_diet':
             # recipe.diets -> RecipeDiet -> diet_type
             # value is one or more enum strings
             val_list = f.value.split(',')
             if f.operator == 'in':
                 query = query.join(models.RecipeDiet)
                 query = query.filter(models.RecipeDiet.diet_type.in_(val_list))
             elif f.operator == 'eq': # Single value check
                 query = query.join(models.RecipeDiet)
                 query = query.filter(models.RecipeDiet.diet_type == f.value)
             continue
        
        if f.field == 'owner':
            # Search by owner email or id?
            # Assuming value is 'author' string which might be name or email?
            # User said: "Owner (author)"
            # Let's try matching on joined user email or name
            query = query.join(models.User)
            if f.operator == 'eq':
                 query = query.filter(or_(
                     models.User.email == f.value,
                     models.User.first_name == f.value, # risky if not unique
                     models.User.last_name == f.value
                 ))
            elif f.operator == 'like':
                query = query.filter(or_(
                     models.User.email.ilike(f"%{f.value}%"),
                     models.User.first_name.ilike(f"%{f.value}%"),
                     models.User.last_name.ilike(f"%{f.value}%")
                ))
            continue

        # Special handling for ID (UUID conversion)
        if f.field == 'id':
            from uuid import UUID
            if f.operator == 'in':
                val_list = [UUID(v) for v in f.value.split(',')]
                query = query.filter(models.Recipe.id.in_(val_list))
            elif f.operator == 'eq':
                query = query.filter(models.Recipe.id == UUID(f.value))
            continue

        # General Field Handling
        model_attr = ALLOWED_FIELDS.get(f.field)
        if not model_attr:
            continue # specific logging provided?

        if f.operator == 'eq':
            query = query.filter(model_attr == f.value)
        elif f.operator == 'neq':
            query = query.filter(model_attr != f.value)
        elif f.operator == 'gt':
            query = query.filter(model_attr > f.value)
        elif f.operator == 'gte':
            query = query.filter(model_attr >= f.value)
        elif f.operator == 'lt':
            query = query.filter(model_attr < f.value)
        elif f.operator == 'lte':
            query = query.filter(model_attr <= f.value)
        elif f.operator == 'in':
            vals = f.value.split(',')
            query = query.filter(model_attr.in_(vals))
        elif f.operator == 'like':
            query = query.filter(model_attr.ilike(f"%{f.value}%")) # Case insensitive default for 'like' in this context?

    return query


def apply_sorting(query: Query, sort_param: str, sort_fields_map: dict = None, default_sort_col=None) -> Query:
    if sort_fields_map is None:
        sort_fields_map = SORT_FIELDS

    if not sort_param:
        if default_sort_col is not None:
            return query.order_by(default_sort_col)
        return query.order_by(models.Recipe.id) # Default consistent sort for recipes

    sort_fields = sort_param.split(',')
    for field in sort_fields:
        field = field.strip()
        direction = asc
        if field.startswith('-'):
            direction = desc
            field = field[1:]

        model_attr = sort_fields_map.get(field)
        if model_attr is not None:
            query = query.order_by(direction(model_attr))

    return query


def apply_meal_filters(query: Query, filters: List[Filter]) -> Query:
    """Apply filters to a Meal query."""
    for f in filters:
        # Special handling for Name
        if f.field == 'name':
            if f.operator == 'like':
                query = query.filter(models.Meal.name.ilike(f"%{f.value}%"))
            elif f.operator == 'eq':
                query = query.filter(models.Meal.name == f.value)
            continue

        # Special handling for ID (UUID conversion)
        if f.field == 'id':
            if f.operator == 'in':
                val_list = [UUID(v) for v in f.value.split(',')]
                query = query.filter(models.Meal.id.in_(val_list))
            elif f.operator == 'eq':
                query = query.filter(models.Meal.id == UUID(f.value))
            continue

        # Special handling for created_by/owner (filter by user)
        if f.field == 'created_by' or f.field == 'owner':
            query = query.join(models.User, models.Meal.user_id == models.User.id)
            if f.operator == 'eq':
                query = query.filter(or_(
                    models.User.email == f.value,
                    models.User.first_name == f.value,
                    models.User.last_name == f.value
                ))
            elif f.operator == 'like':
                query = query.filter(or_(
                    models.User.email.ilike(f"%{f.value}%"),
                    models.User.first_name.ilike(f"%{f.value}%"),
                    models.User.last_name.ilike(f"%{f.value}%")
                ))
            continue

        # Special handling for recipe (filter by associated recipe)
        if f.field == 'recipe':
            # Join through MealItem to Recipe
            query = query.join(models.MealItem, models.Meal.id == models.MealItem.meal_id)
            query = query.join(models.Recipe, models.MealItem.recipe_id == models.Recipe.id)
            if f.operator == 'eq':
                # Match by recipe ID
                try:
                    recipe_uuid = UUID(f.value)
                    query = query.filter(models.Recipe.id == recipe_uuid)
                except ValueError:
                    # If not a valid UUID, try matching by name
                    query = query.filter(models.Recipe.name == f.value)
            elif f.operator == 'like':
                query = query.filter(models.Recipe.name.ilike(f"%{f.value}%"))
            elif f.operator == 'in':
                # Support comma-separated recipe IDs
                try:
                    val_list = [UUID(v) for v in f.value.split(',')]
                    query = query.filter(models.Recipe.id.in_(val_list))
                except ValueError:
                    # If not valid UUIDs, try matching by names
                    val_list = [v.strip() for v in f.value.split(',')]
                    query = query.filter(models.Recipe.name.in_(val_list))
            continue

        # General Field Handling
        model_attr = ALLOWED_FIELDS_MEAL.get(f.field)
        if not model_attr:
            continue

        if f.operator == 'eq':
            query = query.filter(model_attr == f.value)
        elif f.operator == 'neq':
            query = query.filter(model_attr != f.value)
        elif f.operator == 'gt':
            query = query.filter(model_attr > f.value)
        elif f.operator == 'gte':
            query = query.filter(model_attr >= f.value)
        elif f.operator == 'lt':
            query = query.filter(model_attr < f.value)
        elif f.operator == 'lte':
            query = query.filter(model_attr <= f.value)
        elif f.operator == 'in':
            vals = f.value.split(',')
            query = query.filter(model_attr.in_(vals))
        elif f.operator == 'like':
            query = query.filter(model_attr.ilike(f"%{f.value}%"))

    return query


def apply_meal_sorting(query: Query, sort_param: str, nulls_first_on_default: bool = True) -> Query:
    """
    Apply sorting to a Meal query.

    By default (no sort param), sorts by date descending with NULL dates at the top.
    When an explicit sort param is provided, normal sorting behavior is used.
    """
    if not sort_param:
        # Default sort: date descending, but with NULL dates at the top
        if nulls_first_on_default:
            # Use CASE to put NULLs first: CASE WHEN date IS NULL THEN 0 ELSE 1 END, then date DESC
            query = query.order_by(
                case((models.Meal.date.is_(None), 0), else_=1),
                desc(models.Meal.date)
            )
        else:
            query = query.order_by(desc(models.Meal.date))
        return query

    # Explicit sort parameter provided - use normal sorting behavior
    sort_fields = sort_param.split(',')
    for field in sort_fields:
        field = field.strip()
        direction = asc
        if field.startswith('-'):
            direction = desc
            field = field[1:]

        model_attr = MEAL_SORT_FIELDS.get(field)
        if model_attr is not None:
            query = query.order_by(direction(model_attr))

    return query


def apply_template_filters(query: Query, filters: List[Filter]) -> Query:
    """Apply filters to a MealTemplate query."""
    for f in filters:
        # Special handling for Name
        if f.field == 'name':
            if f.operator == 'like':
                query = query.filter(models.MealTemplate.name.ilike(f"%{f.value}%"))
            elif f.operator == 'eq':
                query = query.filter(models.MealTemplate.name == f.value)
            continue

        # Special handling for ID (UUID conversion)
        if f.field == 'id':
            if f.operator == 'in':
                val_list = [UUID(v) for v in f.value.split(',')]
                query = query.filter(models.MealTemplate.id.in_(val_list))
            elif f.operator == 'eq':
                query = query.filter(models.MealTemplate.id == UUID(f.value))
            continue

        # Special handling for created_by/owner (filter by user)
        if f.field == 'created_by' or f.field == 'owner':
            query = query.join(models.User, models.MealTemplate.user_id == models.User.id)
            if f.operator == 'eq':
                query = query.filter(or_(
                    models.User.email == f.value,
                    models.User.first_name == f.value,
                    models.User.last_name == f.value
                ))
            elif f.operator == 'like':
                query = query.filter(or_(
                    models.User.email.ilike(f"%{f.value}%"),
                    models.User.first_name.ilike(f"%{f.value}%"),
                    models.User.last_name.ilike(f"%{f.value}%")
                ))
            continue

        # Special handling for num_slots (number of slots)
        if f.field == 'num_slots' or f.field == 'slots':
            from sqlalchemy import func
            # Subquery to count slots per template
            slot_count = func.count(models.MealTemplateSlot.id)
            if f.operator == 'eq':
                query = query.join(models.MealTemplateSlot).group_by(models.MealTemplate.id).having(slot_count == int(f.value))
            elif f.operator == 'gt':
                query = query.join(models.MealTemplateSlot).group_by(models.MealTemplate.id).having(slot_count > int(f.value))
            elif f.operator == 'gte':
                query = query.join(models.MealTemplateSlot).group_by(models.MealTemplate.id).having(slot_count >= int(f.value))
            elif f.operator == 'lt':
                query = query.join(models.MealTemplateSlot).group_by(models.MealTemplate.id).having(slot_count < int(f.value))
            elif f.operator == 'lte':
                query = query.join(models.MealTemplateSlot).group_by(models.MealTemplate.id).having(slot_count <= int(f.value))
            continue

        # Special handling for recipe (filter by associated recipe in slots)
        if f.field == 'recipe':
            # Templates can have recipes via DIRECT slots (recipe_id) or LIST slots (recipes relationship)
            # Join through MealTemplateSlot
            query = query.join(models.MealTemplateSlot, models.MealTemplate.id == models.MealTemplateSlot.template_id)

            if f.operator == 'eq':
                try:
                    recipe_uuid = UUID(f.value)
                    # Check both direct recipe_id and list recipes (via association table)
                    query = query.outerjoin(
                        models.MealTemplateSlotRecipe,
                        models.MealTemplateSlot.id == models.MealTemplateSlotRecipe.slot_id
                    ).filter(or_(
                        models.MealTemplateSlot.recipe_id == recipe_uuid,
                        models.MealTemplateSlotRecipe.recipe_id == recipe_uuid
                    ))
                except ValueError:
                    # If not a valid UUID, try matching by recipe name
                    query = query.outerjoin(
                        models.Recipe,
                        models.MealTemplateSlot.recipe_id == models.Recipe.id
                    ).outerjoin(
                        models.MealTemplateSlotRecipe,
                        models.MealTemplateSlot.id == models.MealTemplateSlotRecipe.slot_id
                    ).filter(models.Recipe.name == f.value)
            elif f.operator == 'like':
                # For LIKE, we need to join to Recipe table to search by name
                # This gets complex because recipes can be linked via direct or list slots
                from sqlalchemy.orm import aliased
                DirectRecipe = aliased(models.Recipe)
                query = query.outerjoin(
                    DirectRecipe,
                    models.MealTemplateSlot.recipe_id == DirectRecipe.id
                ).outerjoin(
                    models.MealTemplateSlotRecipe,
                    models.MealTemplateSlot.id == models.MealTemplateSlotRecipe.slot_id
                ).outerjoin(
                    models.Recipe,
                    models.MealTemplateSlotRecipe.recipe_id == models.Recipe.id
                ).filter(or_(
                    DirectRecipe.name.ilike(f"%{f.value}%"),
                    models.Recipe.name.ilike(f"%{f.value}%")
                ))
            elif f.operator == 'in':
                try:
                    val_list = [UUID(v) for v in f.value.split(',')]
                    query = query.outerjoin(
                        models.MealTemplateSlotRecipe,
                        models.MealTemplateSlot.id == models.MealTemplateSlotRecipe.slot_id
                    ).filter(or_(
                        models.MealTemplateSlot.recipe_id.in_(val_list),
                        models.MealTemplateSlotRecipe.recipe_id.in_(val_list)
                    ))
                except ValueError:
                    pass  # Invalid UUIDs, skip filter
            continue

        # General Field Handling
        model_attr = ALLOWED_FIELDS_MEAL_TEMPLATE.get(f.field)
        if not model_attr:
            continue

        if f.operator == 'eq':
            query = query.filter(model_attr == f.value)
        elif f.operator == 'neq':
            query = query.filter(model_attr != f.value)
        elif f.operator == 'gt':
            query = query.filter(model_attr > f.value)
        elif f.operator == 'gte':
            query = query.filter(model_attr >= f.value)
        elif f.operator == 'lt':
            query = query.filter(model_attr < f.value)
        elif f.operator == 'lte':
            query = query.filter(model_attr <= f.value)
        elif f.operator == 'in':
            vals = f.value.split(',')
            query = query.filter(model_attr.in_(vals))
        elif f.operator == 'like':
            query = query.filter(model_attr.ilike(f"%{f.value}%"))

    return query
