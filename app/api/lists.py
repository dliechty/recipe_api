"""
API routes for user-specific recipe lists.
"""

from typing import List
from fastapi import APIRouter, Depends, HTTPException, status, Query, Response, Request
from sqlalchemy.orm import Session
from uuid import UUID

from app.db.session import get_db
from app import models, schemas, crud
from app.api import auth
from app.filters import parse_filters

router = APIRouter()


@router.post(
    "/", response_model=schemas.RecipeList, status_code=status.HTTP_201_CREATED
)
def create_recipe_list(
    list_in: schemas.RecipeListCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_active_user),
):
    """
    Create a new recipe list for the current user.
    """
    db_list = crud.create_recipe_list(db, list_in, current_user.id)
    return db_list


@router.get("/", response_model=List[schemas.RecipeList])
def get_recipe_lists(
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
        "Valid fields: name, created_at, updated_at. Example: 'name,-created_at'",
    ),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_active_user),
):
    """
    Retrieve recipe lists with optional filtering and sorting.

    Regular users can only see their own lists. Admins can see all lists.

    **Filtering:** Use bracket notation `field[operator]=value` for filters.

    Operators: `eq`, `neq`, `gt`, `gte`, `lt`, `lte`, `in`, `like`.

    Filter fields: `id`, `name`, `created_at`, `updated_at`, `recipe_id`.

    Examples:
    - `?name[like]=favorites` - Lists with 'favorites' in name
    - `?recipe_id[eq]=<recipe_uuid>` - Lists containing a specific recipe

    **Sorting:** Use the `sort` parameter with comma-separated fields. Prefix with `-` for descending.

    Returns total count in `X-Total-Count` response header.
    """
    filters_list = parse_filters(request.query_params)

    # Non-admin users can only see their own lists
    user_id = None if current_user.is_admin else current_user.id

    lists, total_count = crud.get_recipe_lists(
        db,
        skip=skip,
        limit=limit,
        filters_list=filters_list,
        sort_by=sort,
        user_id=user_id,
    )
    response.headers["X-Total-Count"] = str(total_count)
    return lists


@router.get("/{list_id}", response_model=schemas.RecipeList)
def get_recipe_list(
    list_id: UUID,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_active_user),
):
    """
    Retrieve a specific recipe list by ID.
    Only the owner or an admin can view the list.
    """
    db_list = crud.get_recipe_list(db, list_id)
    if not db_list:
        raise HTTPException(status_code=404, detail="Recipe list not found")
    if db_list.user_id != current_user.id and not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Not authorized to view this list")
    return db_list


@router.put("/{list_id}", response_model=schemas.RecipeList)
def update_recipe_list(
    list_id: UUID,
    list_in: schemas.RecipeListUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_active_user),
):
    """
    Update a recipe list's name and/or description.
    Only the owner can update their list.
    """
    db_list = crud.get_recipe_list(db, list_id)
    if not db_list:
        raise HTTPException(status_code=404, detail="Recipe list not found")
    if db_list.user_id != current_user.id and not current_user.is_admin:
        raise HTTPException(
            status_code=403, detail="Not authorized to update this list"
        )

    updated_list = crud.update_recipe_list(db, list_id, list_in)
    return updated_list


@router.delete("/{list_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_recipe_list(
    list_id: UUID,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_active_user),
):
    """
    Delete a recipe list.
    Only the owner can delete their list.
    """
    db_list = crud.get_recipe_list(db, list_id)
    if not db_list:
        raise HTTPException(status_code=404, detail="Recipe list not found")
    if db_list.user_id != current_user.id and not current_user.is_admin:
        raise HTTPException(
            status_code=403, detail="Not authorized to delete this list"
        )

    crud.delete_recipe_list(db, list_id)
    return None


@router.post(
    "/{list_id}/recipes",
    response_model=schemas.RecipeListItem,
    status_code=status.HTTP_201_CREATED,
)
def add_recipe_to_list(
    list_id: UUID,
    recipe_in: schemas.RecipeListAddRecipe,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_active_user),
):
    """
    Add a recipe to a recipe list.
    Only the owner can add recipes to their list.
    """
    db_list = crud.get_recipe_list(db, list_id)
    if not db_list:
        raise HTTPException(status_code=404, detail="Recipe list not found")
    if db_list.user_id != current_user.id and not current_user.is_admin:
        raise HTTPException(
            status_code=403, detail="Not authorized to modify this list"
        )

    # Verify recipe exists
    recipe = crud.get_recipe(db, recipe_in.recipe_id)
    if not recipe:
        raise HTTPException(status_code=404, detail="Recipe not found")

    db_item = crud.add_recipe_to_list(db, list_id, recipe_in.recipe_id)
    return db_item


@router.delete("/{list_id}/recipes/{recipe_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_recipe_from_list(
    list_id: UUID,
    recipe_id: UUID,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_active_user),
):
    """
    Remove a recipe from a recipe list.
    Only the owner can remove recipes from their list.
    """
    db_list = crud.get_recipe_list(db, list_id)
    if not db_list:
        raise HTTPException(status_code=404, detail="Recipe list not found")
    if db_list.user_id != current_user.id and not current_user.is_admin:
        raise HTTPException(
            status_code=403, detail="Not authorized to modify this list"
        )

    # Check if recipe is in list
    db_item = crud.get_recipe_list_item(db, list_id, recipe_id)
    if not db_item:
        raise HTTPException(status_code=404, detail="Recipe not found in this list")

    crud.remove_recipe_from_list(db, list_id, recipe_id)
    return None
