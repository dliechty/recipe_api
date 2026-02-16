from typing import List, Optional, Any
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, status, Query, Response, Request
from sqlalchemy.orm import Session
from sqlalchemy import func
from uuid import UUID
import random
import hashlib
from app.db.session import get_db
from app import models, schemas
from app.api import auth
from app import filters
from app.filters import parse_filters

router = APIRouter()

# Valid status transitions: only queued can transition to cooked or cancelled
VALID_STATUS_TRANSITIONS = {
    models.MealStatus.QUEUED: {models.MealStatus.COOKED, models.MealStatus.CANCELLED},
}


def compute_slot_signature(slot: Any) -> str:
    """
    Compute a canonical string representation of a slot for hashing.
    Works with both ORM MealTemplateSlot objects and MealTemplateSlotCreate schemas.
    """
    strategy = slot.strategy

    if strategy == models.MealTemplateSlotStrategy.DIRECT:
        return f"direct:{slot.recipe_id}"

    elif strategy == models.MealTemplateSlotStrategy.LIST:
        # Check if this is an ORM object (has recipes relationship) or Pydantic (has recipe_ids)
        if hasattr(slot, "recipes") and slot.recipes is not None:
            # ORM object - get recipe IDs from the relationship
            recipe_ids = sorted(str(r.id) for r in slot.recipes)
        else:
            # Pydantic schema - use recipe_ids directly
            recipe_ids = (
                sorted(str(rid) for rid in slot.recipe_ids) if slot.recipe_ids else []
            )
        return f"list:{','.join(recipe_ids)}"

    elif strategy == models.MealTemplateSlotStrategy.SEARCH:
        criteria = slot.search_criteria or []
        # Handle both ORM (list of dicts) and Pydantic (list of SearchCriterion)
        sorted_criteria = sorted(
            f"{c.get('field', '')}:{c.get('operator', '')}:{c.get('value', '')}"
            if isinstance(c, dict)
            else f"{c.field}:{c.operator}:{c.value}"
            for c in criteria
        )
        return f"search:{';'.join(sorted_criteria)}"

    return "unknown"


def compute_slots_checksum(slots: List[Any]) -> str:
    """
    Compute a SHA256 checksum for a list of slots.
    The checksum is order-independent (slots are sorted before hashing).
    """
    # Get canonical string for each slot and sort them for order independence
    slot_signatures = sorted(compute_slot_signature(slot) for slot in slots)
    # Join all signatures and compute SHA256
    combined = "|".join(slot_signatures)
    return hashlib.sha256(combined.encode()).hexdigest()


def find_duplicate_template(
    db: Session, slots: List[Any], exclude_template_id: Optional[UUID] = None
) -> Optional[models.MealTemplate]:
    """
    Find an existing template with identical slot configuration using checksum lookup.
    Returns the duplicate template if found, None otherwise.
    """
    checksum = compute_slots_checksum(slots)

    # Query by checksum (uses index for efficient lookup)
    query = db.query(models.MealTemplate).filter(
        models.MealTemplate.slots_checksum == checksum
    )
    if exclude_template_id:
        query = query.filter(models.MealTemplate.id != exclude_template_id)

    return query.first()


# --- Meal Templates ---


@router.post(
    "/templates",
    response_model=schemas.MealTemplate,
    status_code=status.HTTP_201_CREATED,
)
def create_meal_template(
    template_in: schemas.MealTemplateCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_active_user),
):
    # Compute checksum for duplicate detection
    slots_checksum = compute_slots_checksum(template_in.slots)

    # Check for duplicate slot configuration using indexed checksum lookup
    duplicate = find_duplicate_template(db, template_in.slots)
    if duplicate:
        owner_name = duplicate.user.email
        if duplicate.user.first_name:
            owner_name = duplicate.user.first_name
            if duplicate.user.last_name:
                owner_name = f"{duplicate.user.first_name} {duplicate.user.last_name}"
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"A template with identical slots already exists: '{duplicate.name}' (created by {owner_name})",
        )

    # Create Template with checksum
    db_template = models.MealTemplate(
        user_id=current_user.id,
        name=template_in.name,
        classification=template_in.classification,
        slots_checksum=slots_checksum,
    )
    db.add(db_template)
    db.commit()
    db.refresh(db_template)

    # Create Slots
    for slot_in in template_in.slots:
        # Debug removed

        # Convert SearchCriterion objects to dicts for JSON storage
        criteria_json = None
        if slot_in.search_criteria:
            criteria_json = [c.model_dump() for c in slot_in.search_criteria]

        db_slot = models.MealTemplateSlot(
            template_id=db_template.id,
            strategy=slot_in.strategy,
            recipe_id=slot_in.recipe_id,
            search_criteria=criteria_json,
        )

        if slot_in.recipe_ids:
            recipes_list = (
                db.query(models.Recipe)
                .filter(models.Recipe.id.in_(slot_in.recipe_ids))
                .all()
            )
            db_slot.recipes = recipes_list

        db.add(db_slot)

    db.commit()
    db.refresh(db_template)
    return db_template


@router.get("/templates", response_model=List[schemas.MealTemplate])
def get_meal_templates(
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
        "Valid fields: name, classification, created_at, updated_at. Example: 'name,-created_at'",
    ),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_active_user),
):
    """
    Retrieve a list of meal templates with optional filtering and sorting.

    **Filtering:** Use bracket notation `field[operator]=value` for filters.

    Operators: `eq`, `neq`, `gt`, `gte`, `lt`, `lte`, `in`, `like`.

    Filter fields: `id`, `name`, `classification`, `created_at`, `updated_at`, `num_slots` (or `slots`), `recipe_id`, `owner` (or `created_by`).

    Examples:
    - `?name[like]=weekly` - Templates with 'weekly' in name
    - `?classification[eq]=dinner` - Dinner templates only
    - `?num_slots[gte]=3` - Templates with 3+ slots
    - `?recipe_id[eq]=<uuid>` - Templates containing specific recipe
    - `?recipe_id[in]=<uuid1>,<uuid2>` - Templates containing any of the specified recipes

    **Sorting:** Use the `sort` parameter with comma-separated fields. Prefix with `-` for descending.

    Returns total count in `X-Total-Count` response header.
    """
    query = db.query(models.MealTemplate)

    # Parse and apply filters
    filters_list = parse_filters(request.query_params)
    if filters_list:
        query = filters.apply_template_filters(query, filters_list)

    # Calculate total count after filtering but before pagination
    total_count = query.distinct().count()
    response.headers["X-Total-Count"] = str(total_count)

    query = filters.apply_sorting(
        query,
        sort,
        filters.MEAL_TEMPLATE_SORT_FIELDS,
        default_sort_col=models.MealTemplate.name,
    )
    templates = query.distinct().offset(skip).limit(limit).all()
    return templates


@router.get("/templates/{template_id}", response_model=schemas.MealTemplate)
def get_meal_template(
    template_id: UUID,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_active_user),
):
    template = (
        db.query(models.MealTemplate)
        .filter(models.MealTemplate.id == template_id)
        .first()
    )
    if not template:
        raise HTTPException(status_code=404, detail="Meal template not found")
    return template


@router.put("/templates/{template_id}", response_model=schemas.MealTemplate)
def update_meal_template(
    template_id: UUID,
    template_in: schemas.MealTemplateUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_active_user),
):
    template = (
        db.query(models.MealTemplate)
        .filter(models.MealTemplate.id == template_id)
        .first()
    )
    if not template:
        raise HTTPException(status_code=404, detail="Meal template not found")
    if template.user_id != current_user.id and not current_user.is_admin:
        raise HTTPException(
            status_code=403, detail="Not authorized to update this template"
        )

    if template_in.name is not None:
        template.name = template_in.name
    if template_in.classification is not None:
        template.classification = template_in.classification

    db.commit()
    db.refresh(template)
    return template


@router.delete("/templates/{template_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_meal_template(
    template_id: UUID,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_active_user),
):
    template = (
        db.query(models.MealTemplate)
        .filter(models.MealTemplate.id == template_id)
        .first()
    )
    if not template:
        raise HTTPException(status_code=404, detail="Meal template not found")
    if template.user_id != current_user.id and not current_user.is_admin:
        raise HTTPException(
            status_code=403, detail="Not authorized to delete this template"
        )

    db.delete(template)
    db.commit()
    return None


# --- Logic for Generation ---


def resolve_recipe_for_slot(
    db: Session, slot: models.MealTemplateSlot, user_id: UUID
) -> Optional[models.Recipe]:
    if slot.strategy == models.MealTemplateSlotStrategy.DIRECT:
        return (
            db.query(models.Recipe).filter(models.Recipe.id == slot.recipe_id).first()
        )

    elif slot.strategy == models.MealTemplateSlotStrategy.LIST:
        # Pick random from the list
        # Pick random
        if not slot.recipes:
            return None
        return random.choice(slot.recipes)

    elif slot.strategy == models.MealTemplateSlotStrategy.SEARCH:
        # Build query based on criteria
        criteria = slot.search_criteria or []
        query = db.query(models.Recipe)

        # Criteria is expected to be a list of dicts that can be parsed into Filters
        filters_list = []
        if isinstance(criteria, list):
            for c in criteria:
                # Assuming c is a dict like {'field': 'x', 'operator': 'eq', 'value': 'y'}
                if isinstance(c, dict):
                    filters_list.append(
                        filters.Filter(
                            field=c.get("field"),
                            operator=c.get("operator"),
                            value=c.get("value"),
                        )
                    )

        if filters_list:
            query = filters.apply_filters(query, filters_list)

        # Optimization: Don't fetch all, just fetch one random
        # But we need to know count to pick random offset?
        # Or order by random() which is db specific but usually works.
        match = query.order_by(func.random()).first()
        return match

    return None


# --- Meals ---


@router.post(
    "/generate", response_model=schemas.Meal, status_code=status.HTTP_201_CREATED
)
def generate_meal(
    template_id: UUID,
    schedule_request: Optional[schemas.MealScheduleRequest] = None,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_active_user),
):
    template = (
        db.query(models.MealTemplate)
        .filter(models.MealTemplate.id == template_id)
        .first()
    )
    if not template:
        raise HTTPException(status_code=404, detail="Meal template not found")

    # Determine scheduled_date from schedule request
    meal_date = None
    if schedule_request and schedule_request.scheduled_date:
        meal_date = schedule_request.scheduled_date

    # Create Meal
    db_meal = models.Meal(
        user_id=current_user.id,
        template_id=template.id,
        name=f"Generated {template.name}",
        status=models.MealStatus.QUEUED,
        classification=template.classification,
        scheduled_date=meal_date,
    )
    db.add(db_meal)

    # Update template last_used_at
    template.last_used_at = datetime.now(timezone.utc)

    db.commit()
    db.refresh(db_meal)

    # Process Slots
    for slot in template.slots:
        recipe = resolve_recipe_for_slot(db, slot, current_user.id)
        if recipe:
            meal_item = models.MealItem(
                meal_id=db_meal.id, slot_id=slot.id, recipe_id=recipe.id
            )
            db.add(meal_item)

    db.commit()
    db.refresh(db_meal)
    return db_meal


@router.post("/", response_model=schemas.Meal, status_code=status.HTTP_201_CREATED)
def create_meal(
    meal_in: schemas.MealCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_active_user),
):
    db_meal = models.Meal(
        user_id=current_user.id,
        template_id=meal_in.template_id,
        name=meal_in.name or "New Meal",
        status=meal_in.status,
        classification=meal_in.classification,
        scheduled_date=meal_in.scheduled_date,
        is_shopped=meal_in.is_shopped,
        queue_position=meal_in.queue_position,
    )
    db.add(db_meal)
    db.commit()
    db.refresh(db_meal)

    for item_in in meal_in.items:
        db_item = models.MealItem(meal_id=db_meal.id, recipe_id=item_in.recipe_id)
        db.add(db_item)

    db.commit()
    db.refresh(db_meal)
    return db_meal


@router.get("/", response_model=List[schemas.Meal])
def get_meals(
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
        "Valid fields: scheduled_date, classification, status, created_at, updated_at, name, queue_position. "
        "Default: scheduled_date descending with unscheduled (null) dates first. Example: '-scheduled_date,name'",
    ),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_active_user),
):
    """
    Retrieve a list of meals with optional filtering and sorting.

    **Filtering:** Use bracket notation `field[operator]=value` for filters.

    Operators: `eq`, `neq`, `gt`, `gte`, `lt`, `lte`, `in`, `like`.

    Filter fields: `id`, `name`, `status`, `classification`, `scheduled_date`, `is_shopped`, `created_at`, `updated_at`, `recipe_id`, `owner` (or `created_by`).

    Examples:
    - `?name[like]=weekly` - Meals with 'weekly' in name
    - `?status[eq]=Queued` - Queued meals only
    - `?scheduled_date[gte]=2024-01-01&scheduled_date[lte]=2024-01-31` - Meals in January 2024
    - `?recipe_id[eq]=<uuid>` - Meals containing specific recipe
    - `?recipe_id[in]=<uuid1>,<uuid2>` - Meals containing any of the specified recipes
    - `?classification[in]=breakfast,lunch` - Breakfast or lunch meals

    **Sorting:** Use the `sort` parameter with comma-separated fields. Prefix with `-` for descending.

    Returns total count in `X-Total-Count` response header.
    """
    query = db.query(models.Meal)

    # Parse and apply filters
    filters_list = parse_filters(request.query_params)
    if filters_list:
        query = filters.apply_meal_filters(query, filters_list)

    # Calculate total count after filtering but before pagination
    total_count = query.distinct().count()
    response.headers["X-Total-Count"] = str(total_count)

    # Apply sorting - use special meal sorting that puts null dates first on default
    query = filters.apply_meal_sorting(query, sort)
    meals = query.distinct().offset(skip).limit(limit).all()
    return meals


@router.get("/{meal_id}", response_model=schemas.Meal)
def get_meal(
    meal_id: UUID,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_active_user),
):
    meal = db.query(models.Meal).filter(models.Meal.id == meal_id).first()
    if not meal:
        raise HTTPException(status_code=404, detail="Meal not found")
    return meal


@router.put("/{meal_id}", response_model=schemas.Meal)
def update_meal(
    meal_id: UUID,
    meal_in: schemas.MealUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_active_user),
):
    meal = db.query(models.Meal).filter(models.Meal.id == meal_id).first()
    if not meal:
        raise HTTPException(status_code=404, detail="Meal not found")
    if meal.user_id != current_user.id and not current_user.is_admin:
        raise HTTPException(
            status_code=403, detail="Not authorized to update this meal"
        )

    if meal_in.name is not None:
        meal.name = meal_in.name
    if meal_in.status is not None:
        # Validate status transition
        if meal_in.status != meal.status:
            allowed = VALID_STATUS_TRANSITIONS.get(meal.status, set())
            if meal_in.status not in allowed:
                raise HTTPException(
                    status_code=400,
                    detail=f"Invalid status transition from '{meal.status.value}' to '{meal_in.status.value}'",
                )

            # Side effect: update last_cooked_at on recipes when transitioning to cooked
            if meal_in.status == models.MealStatus.COOKED:
                now = datetime.now(timezone.utc)
                for item in meal.items:
                    recipe = db.query(models.Recipe).filter(models.Recipe.id == item.recipe_id).first()
                    if recipe:
                        recipe.last_cooked_at = now

        meal.status = meal_in.status
    if meal_in.classification is not None:
        meal.classification = meal_in.classification
    if meal_in.scheduled_date is not None:
        meal.scheduled_date = meal_in.scheduled_date
    if meal_in.is_shopped is not None:
        meal.is_shopped = meal_in.is_shopped
    if meal_in.queue_position is not None:
        meal.queue_position = meal_in.queue_position

    if meal_in.items is not None:
        # Clear existing items
        # We need to manually remove them or use cascade. Cascade is set on relationship, so removing from list might work if we were using purely ORM list manipulation,
        # but explicit delete is safer for clarity or if we just want to replace the collection.
        # Actually, with SQLAlchemy relationship cascade="all, delete-orphan", clearing the list usually works.
        # Let's try clearing the list first.
        meal.items.clear()

        # Add new items
        for item_in in meal_in.items:
            db_item = models.MealItem(
                meal_id=meal.id,
                recipe_id=item_in.recipe_id,
                # Note: slot_id is lost/reset to None for these manual updates as per plan
            )
            meal.items.append(db_item)

    db.commit()
    db.refresh(meal)
    return meal


@router.delete("/{meal_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_meal(
    meal_id: UUID,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_active_user),
):
    meal = db.query(models.Meal).filter(models.Meal.id == meal_id).first()
    if not meal:
        raise HTTPException(status_code=404, detail="Meal not found")
    if meal.user_id != current_user.id and not current_user.is_admin:
        raise HTTPException(
            status_code=403, detail="Not authorized to delete this meal"
        )

    db.delete(meal)
    db.commit()
    return None
