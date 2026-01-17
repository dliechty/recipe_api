from typing import List, Optional, Tuple, Any
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from sqlalchemy import func, desc, text
from uuid import UUID
import random
import json
import hashlib
from app.db.session import get_db
from app import models, schemas
from app.api import auth
from app import filters

router = APIRouter()


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
        if hasattr(slot, 'recipes') and slot.recipes is not None:
            # ORM object - get recipe IDs from the relationship
            recipe_ids = sorted(str(r.id) for r in slot.recipes)
        else:
            # Pydantic schema - use recipe_ids directly
            recipe_ids = sorted(str(rid) for rid in slot.recipe_ids) if slot.recipe_ids else []
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
    db: Session,
    slots: List[Any],
    exclude_template_id: Optional[UUID] = None
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

@router.post("/templates", response_model=schemas.MealTemplate, status_code=status.HTTP_201_CREATED)
def create_meal_template(
    template_in: schemas.MealTemplateCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_active_user)
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
            detail=f"A template with identical slots already exists: '{duplicate.name}' (created by {owner_name})"
        )

    # Create Template with checksum
    db_template = models.MealTemplate(
        user_id=current_user.id,
        name=template_in.name,
        classification=template_in.classification,
        slots_checksum=slots_checksum
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
            search_criteria=criteria_json
        )
        
        if slot_in.recipe_ids:
            recipes_list = db.query(models.Recipe).filter(models.Recipe.id.in_(slot_in.recipe_ids)).all()
            db_slot.recipes = recipes_list
            
        db.add(db_slot)
    
    db.commit()
    db.refresh(db_template)
    return db_template

@router.get("/templates", response_model=List[schemas.MealTemplate])
def get_meal_templates(
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_active_user)
):
    templates = db.query(models.MealTemplate).filter(models.MealTemplate.user_id == current_user.id).offset(skip).limit(limit).all()
    return templates

@router.get("/templates/{template_id}", response_model=schemas.MealTemplate)
def get_meal_template(
    template_id: UUID,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_active_user)
):
    template = db.query(models.MealTemplate).filter(models.MealTemplate.id == template_id, models.MealTemplate.user_id == current_user.id).first()
    if not template:
        raise HTTPException(status_code=404, detail="Meal template not found")
    return template

@router.put("/templates/{template_id}", response_model=schemas.MealTemplate)
def update_meal_template(
    template_id: UUID,
    template_in: schemas.MealTemplateUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_active_user)
):
    template = db.query(models.MealTemplate).filter(models.MealTemplate.id == template_id, models.MealTemplate.user_id == current_user.id).first()
    if not template:
        raise HTTPException(status_code=404, detail="Meal template not found")
    
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
    current_user: models.User = Depends(auth.get_current_active_user)
):
    template = db.query(models.MealTemplate).filter(models.MealTemplate.id == template_id, models.MealTemplate.user_id == current_user.id).first()
    if not template:
        raise HTTPException(status_code=404, detail="Meal template not found")
    
    db.delete(template)
    db.commit()
    return None

# --- Logic for Generation ---

def resolve_recipe_for_slot(db: Session, slot: models.MealTemplateSlot, user_id: UUID) -> Optional[models.Recipe]:
    if slot.strategy == models.MealTemplateSlotStrategy.DIRECT:
        return db.query(models.Recipe).filter(models.Recipe.id == slot.recipe_id).first()
        
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
                     filters_list.append(filters.Filter(
                         field=c.get('field'),
                         operator=c.get('operator'),
                         value=c.get('value')
                     ))
        
        if filters_list:
            query = filters.apply_filters(query, filters_list)
            
        # Optimization: Don't fetch all, just fetch one random
        # But we need to know count to pick random offset? 
        # Or order by random() which is db specific but usually works.
        match = query.order_by(func.random()).first()
        return match
        
    return None

# --- Meals ---

@router.post("/generate", response_model=schemas.Meal, status_code=status.HTTP_201_CREATED)
def generate_meal(
    template_id: UUID,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_active_user)
):
    template = db.query(models.MealTemplate).filter(models.MealTemplate.id == template_id, models.MealTemplate.user_id == current_user.id).first()
    if not template:
        raise HTTPException(status_code=404, detail="Meal template not found")
        
    # Create Meal
    db_meal = models.Meal(
        user_id=current_user.id,
        template_id=template.id,
        name=f"Generated {template.name}",
        status=models.MealStatus.PROPOSED,
        classification=template.classification
    )
    db.add(db_meal)
    db.commit()
    db.refresh(db_meal)
    
    # Process Slots
    for slot in template.slots:
        recipe = resolve_recipe_for_slot(db, slot, current_user.id)
        if recipe:
            meal_item = models.MealItem(
                meal_id=db_meal.id,
                slot_id=slot.id,
                recipe_id=recipe.id
            )
            db.add(meal_item)
            
    db.commit()
    db.refresh(db_meal)
    return db_meal

@router.post("/", response_model=schemas.Meal, status_code=status.HTTP_201_CREATED)
def create_meal(
    meal_in: schemas.MealCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_active_user)
):
    db_meal = models.Meal(
        user_id=current_user.id,
        template_id=meal_in.template_id,
        name=meal_in.name or "New Meal",
        status=meal_in.status,
        classification=meal_in.classification,
        date=meal_in.date
    )
    db.add(db_meal)
    db.commit()
    db.refresh(db_meal)
    
    for item_in in meal_in.items:
        db_item = models.MealItem(
            meal_id=db_meal.id,
            recipe_id=item_in.recipe_id
        )
        db.add(db_item)
        
    db.commit()
    db.refresh(db_meal)
    return db_meal

@router.get("/", response_model=List[schemas.Meal])
def get_meals(
    skip: int = 0,
    limit: int = 100,
    sort: str = Query(None),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_active_user)
):
    query = db.query(models.Meal).filter(models.Meal.user_id == current_user.id)
    query = filters.apply_sorting(query, sort, filters.MEAL_SORT_FIELDS, default_sort_col=models.Meal.date)
    meals = query.offset(skip).limit(limit).all()
    return meals

@router.get("/{meal_id}", response_model=schemas.Meal)
def get_meal(
    meal_id: UUID,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_active_user)
):
    meal = db.query(models.Meal).filter(models.Meal.id == meal_id, models.Meal.user_id == current_user.id).first()
    if not meal:
        raise HTTPException(status_code=404, detail="Meal not found")
    return meal

@router.put("/{meal_id}", response_model=schemas.Meal)
def update_meal(
    meal_id: UUID,
    meal_in: schemas.MealUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_active_user)
):
    meal = db.query(models.Meal).filter(models.Meal.id == meal_id, models.Meal.user_id == current_user.id).first()
    if not meal:
        raise HTTPException(status_code=404, detail="Meal not found")
        
    if meal_in.name is not None:
        meal.name = meal_in.name
    if meal_in.status is not None:
        meal.status = meal_in.status
    if meal_in.classification is not None:
        meal.classification = meal_in.classification
    if meal_in.date is not None:
        meal.date = meal_in.date
        
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
                recipe_id=item_in.recipe_id
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
    current_user: models.User = Depends(auth.get_current_active_user)
):
    meal = db.query(models.Meal).filter(models.Meal.id == meal_id, models.Meal.user_id == current_user.id).first()
    if not meal:
        raise HTTPException(status_code=404, detail="Meal not found")
    
    db.delete(meal)
    db.commit()
    return None
