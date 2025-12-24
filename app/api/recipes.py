# api/recipes.py
# Handles all API endpoints related to recipes.

import logging
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List

# Import local modules
# Import local modules
from app import crud
from app import schemas
from app import models
from app.db.session import get_db
from app.api.auth import get_current_active_user

# Create an API router
router = APIRouter()

# Get a logger instance
logger = logging.getLogger(__name__)


@router.post("/", response_model=schemas.Recipe)
def create_recipe(
        recipe: schemas.RecipeCreate,
        db: Session = Depends(get_db),
        current_user: models.User = Depends(get_current_active_user)
):
    """
    Create a new recipe for the currently authenticated user.
    """
    logger.debug(f"User {current_user.email} is creating a new recipe.")
    return crud.create_user_recipe(db=db, recipe=recipe, user_id=current_user.id)


@router.get("/", response_model=List[schemas.Recipe])
def read_recipes(
        skip: int = 0,
        limit: int = 100,
        db: Session = Depends(get_db),
        current_user: models.User = Depends(get_current_active_user)
):
    """
    Retrieve a list of all recipes.
    """
    logger.debug(f"Fetching all recipes with skip={skip}, limit={limit}.")
    recipes = crud.get_recipes(db, skip=skip, limit=limit)
    return recipes


@router.get("/{recipe_id}", response_model=schemas.Recipe)
def read_recipe(
        recipe_id: int,
        db: Session = Depends(get_db),
        current_user: models.User = Depends(get_current_active_user)
):
    """
    Retrieve a single recipe by its ID.
    """
    logger.debug(f"Fetching recipe with ID: {recipe_id}")
    db_recipe = crud.get_recipe(db, recipe_id=recipe_id)
    if db_recipe is None:
        logger.warning(f"Recipe with ID {recipe_id} not found.")
        raise HTTPException(status_code=404, detail="Recipe not found")
    logger.debug(f"Recipe with ID {recipe_id} found: {db_recipe}")
    return db_recipe


@router.put("/{recipe_id}", response_model=schemas.Recipe)
def update_recipe(
        recipe_id: int,
        recipe: schemas.RecipeCreate,
        db: Session = Depends(get_db),
        current_user: models.User = Depends(get_current_active_user)
):
    """
    Update a recipe. Only the owner of the recipe can perform this action.
    """
    logger.debug(f"User {current_user.email} is updating recipe with ID: {recipe_id}")
    db_recipe = crud.get_recipe(db, recipe_id=recipe_id)
    if db_recipe is None:
        logger.warning(f"Recipe with ID {recipe_id} not found for update.")
        raise HTTPException(status_code=404, detail="Recipe not found")
    if db_recipe.owner_id != current_user.id:
        logger.error(f"User {current_user.email} is not authorized to update recipe with ID: {recipe_id}")
        raise HTTPException(status_code=403, detail="Not authorized to update this recipe")

    return crud.update_recipe(db=db, recipe_id=recipe_id, recipe_update=recipe)


@router.delete("/{recipe_id}", response_model=schemas.Recipe)
def delete_recipe(
        recipe_id: int,
        db: Session = Depends(get_db),
        current_user: models.User = Depends(get_current_active_user)
):
    """
    Delete a recipe. Only the owner of the recipe can perform this action.
    """
    logger.debug(f"User {current_user.email} is deleting recipe with ID: {recipe_id}")
    db_recipe = crud.get_recipe(db, recipe_id=recipe_id)
    if db_recipe is None:
        logger.warning(f"Recipe with ID: {recipe_id} not found for deletion.")
        raise HTTPException(status_code=404, detail="Recipe not found")
    if db_recipe.owner_id != current_user.id:
        logger.error(f"User {current_user.email} is not authorized to delete recipe with ID: {recipe_id}")
        raise HTTPException(status_code=403, detail="Not authorized to delete this recipe")

    return crud.delete_recipe(db=db, recipe_id=recipe_id)