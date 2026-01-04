# app/filters.py
from typing import List, Optional, Any, Tuple
from fastapi import Query as FastAPIQuery, HTTPException
from sqlalchemy.orm import Query
from sqlalchemy import asc, desc, or_, and_, text
from datetime import timedelta
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


def apply_sorting(query: Query, sort_param: str) -> Query:
    if not sort_param:
        return query.order_by(models.Recipe.id) # Default consistent sort?

    sort_fields = sort_param.split(',')
    for field in sort_fields:
        field = field.strip()
        direction = asc
        if field.startswith('-'):
            direction = desc
            field = field[1:]
        
        model_attr = SORT_FIELDS.get(field)
        if model_attr is not None:
            query = query.order_by(direction(model_attr))
    
    return query
