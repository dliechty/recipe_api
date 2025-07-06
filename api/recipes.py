# api/recipes.py
# Handles all API endpoints related to recipes.

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List

# Import local modules
import crud
import schemas
import models
from database import get_db
from api.auth import get_current_active_user

# Create an API router
router = APIRouter()


@router.post("/", response_model=schemas.Recipe)
def create_recipe(
        recipe: schemas.RecipeCreate,
        db: Session = Depends(get_db),
        current_user: models.User = Depends(get_current_active_user)
):
    """
    Create a new recipe for the currently authenticated user.
    """
    return crud.create_user_recipe(db=db, recipe=recipe, user_id=current_user.id)


@router.get("/", response_model=List[schemas.Recipe])
def read_recipes(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    """
    Retrieve a list of all recipes. This endpoint is public.
    """
    recipes = crud.get_recipes(db, skip=skip, limit=limit)
    return recipes


@router.get("/{recipe_id}", response_model=schemas.Recipe)
def read_recipe(recipe_id: int, db: Session = Depends(get_db)):
    """
    Retrieve a single recipe by its ID. This endpoint is public.
    """
    db_recipe = crud.get_recipe(db, recipe_id=recipe_id)
    if db_recipe is None:
        raise HTTPException(status_code=404, detail="Recipe not found")
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
    db_recipe = crud.get_recipe(db, recipe_id=recipe_id)
    if db_recipe is None:
        raise HTTPException(status_code=404, detail="Recipe not found")
    if db_recipe.owner_id != current_user.id:
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
    db_recipe = crud.get_recipe(db, recipe_id=recipe_id)
    if db_recipe is None:
        raise HTTPException(status_code=404, detail="Recipe not found")
    if db_recipe.owner_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not authorized to delete this recipe")

    return crud.delete_recipe(db=db, recipe_id=recipe_id)