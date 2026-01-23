# api/recipes.py
# Handles all API endpoints related to recipes.

import logging
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.orm import Session
from typing import List, Any, Optional

# Import local modules
from app import crud
from app import schemas
from app import models
from app.db.session import get_db
from app.api.auth import get_current_active_user
from app.filters import parse_filters
from app.unit_conversion import (
    UnitSystem,
    convert_recipe_units,
    detect_recipe_unit_system,
)
from fastapi import Request


# Create an API router
router = APIRouter()

# Get a logger instance
logger = logging.getLogger(__name__)


@router.post("/", response_model=schemas.Recipe, status_code=status.HTTP_201_CREATED)
def create_recipe(
    recipe: schemas.RecipeCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user),
):
    """
    Create a new recipe for the currently authenticated user.
    """
    logger.debug(f"User {current_user.email} is creating a new recipe.")
    return crud.create_user_recipe(db=db, recipe=recipe, user_id=current_user.id)


@router.get("/", response_model=List[schemas.Recipe])
def read_recipes(
    request: Request,
    response: Response,
    skip: int = Query(
        default=0, ge=0, description="Number of records to skip for pagination"
    ),
    limit: int = Query(
        default=100,
        ge=1,
        le=1000,
        description="Maximum number of records to return (1-1000)",
    ),
    sort: str = Query(
        default=None,
        description="Comma-separated sort fields. Prefix with '-' for descending order. "
        "Valid fields: name, calories, total_time_minutes, difficulty, category, "
        "cuisine, prep_time_minutes, cook_time_minutes, active_time_minutes, "
        "yield_amount, protein, created_at, updated_at. Example: '-created_at,name'",
    ),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user),
):
    """
    Retrieve a list of all recipes with optional filtering and sorting.

    **Filtering:** Use bracket notation `field[operator]=value` for filters.

    Operators: `eq` (equals), `neq` (not equals), `gt`, `gte`, `lt`, `lte`, `in` (comma-separated list), `like` (case-insensitive substring), `all` (must match all values).

    Filter fields: `id`, `name`, `description`, `category`, `cuisine`, `difficulty`, `protein`, `yield_amount`, `calories`, `prep_time_minutes`, `cook_time_minutes`, `active_time_minutes`, `total_time_minutes`, `owner`, `ingredients`, `suitable_for_diet`.

    Examples:
    - `?name[like]=chicken` - Recipes with 'chicken' in name
    - `?difficulty[eq]=easy` - Easy recipes only
    - `?calories[gte]=200&calories[lte]=500` - Calories between 200-500
    - `?category[in]=breakfast,lunch` - Breakfast or lunch recipes
    - `?ingredients[all]=flour,eggs` - Recipes containing both flour AND eggs

    **Sorting:** Use the `sort` parameter with comma-separated fields. Prefix with `-` for descending.

    Returns total count in `X-Total-Count` response header.
    """
    filters_list = parse_filters(request.query_params)
    logger.debug(
        f"Fetching recipes with skip={skip}, limit={limit}, filters={filters_list}, sort={sort}"
    )
    recipes, total_count = crud.get_recipes(
        db, skip=skip, limit=limit, filters_list=filters_list, sort_by=sort
    )
    response.headers["X-Total-Count"] = str(total_count)
    return recipes


@router.get(
    "/meta/{field}", response_model=List[Any]
)  # Any because it could be string or dict? Pydantic might complain if List[Any] not generic enough.
def get_meta_values(
    field: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user),
):
    """
    Retrieve unique values for a specific field for metadata usage.
    """
    valid_fields = [
        "category",
        "cuisine",
        "difficulty",
        "suitable_for_diet",
        "owner",
        "protein",
    ]
    if field not in valid_fields:
        raise HTTPException(
            status_code=400, detail=f"Invalid meta field. Valid fields: {valid_fields}"
        )

    return crud.get_unique_values(db, field)


@router.get("/{recipe_id}", response_model=schemas.Recipe)
def read_recipe(
    recipe_id: UUID,
    scale: Optional[float] = Query(
        default=None,
        gt=0,
        description="Scale factor for ingredient quantities (must be > 0)",
    ),
    units: Optional[UnitSystem] = Query(
        default=None,
        description="Convert ingredient units to 'metric' (ml, g, cm) or 'imperial' (cups, oz, inches)",
    ),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user),
):
    """
    Retrieve a single recipe by its ID.

    The response includes a `unit_system` field indicating the predominant unit system
    used in the recipe's ingredients (metric or imperial).

    Optionally provide a `scale` parameter to multiply all ingredient quantities.
    For example, scale=2 doubles all quantities, scale=0.5 halves them.

    Optionally provide a `units` parameter to convert ingredient quantities:
    - 'metric': Convert to metric units (ml, g, cm)
    - 'imperial': Convert to imperial units (cups, oz, inches)
    """
    logger.debug(
        f"Fetching recipe with ID: {recipe_id}, scale: {scale}, units: {units}"
    )
    db_recipe = crud.get_recipe(db, recipe_id=recipe_id)
    if db_recipe is None:
        logger.warning(f"Recipe with ID {recipe_id} not found.")
        raise HTTPException(status_code=404, detail="Recipe not found")
    logger.debug(f"Recipe with ID {recipe_id} found: {db_recipe}")

    # Always convert to dict to add unit_system field
    response = schemas.Recipe.model_validate(db_recipe).model_dump(mode="json")

    # Apply scaling (if requested)
    if scale is not None and scale != 1.0:
        response = _apply_scale_factor(response, scale)

    # Apply unit conversion (if requested) and set unit_system
    if units is not None:
        response = convert_recipe_units(response, units)
        response["unit_system"] = units.value
    else:
        # Derive unit system from original ingredients
        all_ingredients = []
        for component in response.get("components", []):
            all_ingredients.extend(component.get("ingredients", []))
        response["unit_system"] = detect_recipe_unit_system(all_ingredients).value

    return response


def _apply_scale_factor(recipe_dict: dict, scale: float) -> dict:
    """
    Apply scaling factor to ingredient quantities and yield_amount in a recipe dict.
    """
    # Scale yield_amount
    if recipe_dict["core"]["yield_amount"] is not None:
        recipe_dict["core"]["yield_amount"] *= scale

    # Scale ingredient quantities
    for component in recipe_dict["components"]:
        for ingredient in component["ingredients"]:
            ingredient["quantity"] *= scale

    return recipe_dict


@router.put("/{recipe_id}", response_model=schemas.Recipe)
def update_recipe(
    recipe_id: UUID,
    recipe: schemas.RecipeCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user),
):
    """
    Update a recipe. Only the owner of the recipe can perform this action.
    """
    logger.debug(f"User {current_user.email} is updating recipe with ID: {recipe_id}")
    db_recipe = crud.get_recipe(db, recipe_id=recipe_id)
    if db_recipe is None:
        logger.warning(f"Recipe with ID {recipe_id} not found for update.")
        raise HTTPException(status_code=404, detail="Recipe not found")
    if db_recipe.owner_id != current_user.id and not current_user.is_admin:
        logger.error(
            f"User {current_user.email} is not authorized to update recipe with ID: {recipe_id}"
        )
        raise HTTPException(
            status_code=403, detail="Not authorized to update this recipe"
        )

    try:
        updated_recipe = crud.update_recipe(
            db=db, recipe_id=recipe_id, recipe_update=recipe
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return updated_recipe


@router.delete("/{recipe_id}", response_model=schemas.Recipe)
def delete_recipe(
    recipe_id: UUID,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user),
):
    """
    Delete a recipe. Only the owner of the recipe can perform this action.
    """
    logger.debug(f"User {current_user.email} is deleting recipe with ID: {recipe_id}")
    db_recipe = crud.get_recipe(db, recipe_id=recipe_id)
    if db_recipe is None:
        logger.warning(f"Recipe with ID: {recipe_id} not found for deletion.")
        raise HTTPException(status_code=404, detail="Recipe not found")
    if db_recipe.owner_id != current_user.id and not current_user.is_admin:
        logger.error(
            f"User {current_user.email} is not authorized to delete recipe with ID: {recipe_id}"
        )
        raise HTTPException(
            status_code=403, detail="Not authorized to delete this recipe"
        )

    if db_recipe.variants:
        raise HTTPException(
            status_code=400,
            detail="Cannot delete recipe with existing variants. Please delete or reassign variants first.",
        )

    return crud.delete_recipe(db=db, recipe_id=recipe_id)


# --- Comment Endpoints ---


@router.post(
    "/{recipe_id}/comments",
    response_model=schemas.Comment,
    status_code=status.HTTP_201_CREATED,
)
def create_comment(
    recipe_id: UUID,
    comment: schemas.CommentCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user),
):
    """
    Add a comment to a recipe.
    """
    # Verify recipe exists
    db_recipe = crud.get_recipe(db, recipe_id=recipe_id)
    if not db_recipe:
        raise HTTPException(status_code=404, detail="Recipe not found")

    return crud.create_comment(
        db=db, comment=comment, user_id=current_user.id, recipe_id=recipe_id
    )


@router.get("/{recipe_id}/comments", response_model=List[schemas.Comment])
def read_comments(
    recipe_id: UUID,
    skip: int = Query(
        default=0, ge=0, description="Number of records to skip for pagination"
    ),
    limit: int = Query(
        default=100,
        ge=1,
        le=1000,
        description="Maximum number of records to return (1-1000)",
    ),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user),
):
    """
    Get comments for a recipe.
    """
    # Verify recipe exists
    db_recipe = crud.get_recipe(db, recipe_id=recipe_id)
    if not db_recipe:
        raise HTTPException(status_code=404, detail="Recipe not found")

    return crud.get_comments(db=db, recipe_id=recipe_id, skip=skip, limit=limit)


@router.put("/{recipe_id}/comments/{comment_id}", response_model=schemas.Comment)
def update_comment(
    recipe_id: UUID,
    comment_id: UUID,
    comment_update: schemas.CommentUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user),
):
    """
    Update a comment. Only the author of the comment or an admin can update it.
    """
    db_comment = crud.get_comment(db, comment_id=comment_id)
    if not db_comment:
        raise HTTPException(status_code=404, detail="Comment not found")

    if db_comment.recipe_id != recipe_id:
        raise HTTPException(
            status_code=400, detail="Comment does not belong to this recipe"
        )

    if db_comment.user_id != current_user.id and not current_user.is_admin:
        raise HTTPException(
            status_code=403, detail="Not authorized to update this comment"
        )

    return crud.update_comment(
        db=db, comment_id=comment_id, comment_update=comment_update
    )


@router.delete(
    "/{recipe_id}/comments/{comment_id}", status_code=status.HTTP_204_NO_CONTENT
)
def delete_comment(
    recipe_id: UUID,
    comment_id: UUID,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user),
):
    """
    Delete a comment. Only the author of the comment or an admin can delete it.
    """
    db_comment = crud.get_comment(db, comment_id=comment_id)
    if not db_comment:
        raise HTTPException(status_code=404, detail="Comment not found")

    if db_comment.recipe_id != recipe_id:
        raise HTTPException(
            status_code=400, detail="Comment does not belong to this recipe"
        )

    if db_comment.user_id != current_user.id and not current_user.is_admin:
        raise HTTPException(
            status_code=403, detail="Not authorized to delete this comment"
        )

    crud.delete_comment(db=db, comment_id=comment_id)
    return None
