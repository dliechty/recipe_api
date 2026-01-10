from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from sqlalchemy import func, desc, text
from uuid import UUID
import random
from app.db.session import get_db
from app import models, schemas
from app.api import auth

router = APIRouter()

# --- Meal Templates ---

@router.post("/templates", response_model=schemas.MealTemplate, status_code=status.HTTP_201_CREATED)
def create_meal_template(
    template_in: schemas.MealTemplateCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_active_user)
):
    # Create Template
    db_template = models.MealTemplate(
        user_id=current_user.id,
        name=template_in.name,
        classification=template_in.classification
    )
    db.add(db_template)
    db.commit()
    db.refresh(db_template)
    
    # Create Slots
    for slot_in in template_in.slots:
        print(f"DEBUG: slot_in.strategy type: {type(slot_in.strategy)}, value: {slot_in.strategy}")
        db_slot = models.MealTemplateSlot(
            template_id=db_template.id,
            strategy=slot_in.strategy,
            recipe_id=slot_in.recipe_id,
            search_criteria=slot_in.search_criteria
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
        criteria = slot.search_criteria or {}
        query = db.query(models.Recipe)
        
        # Example criteria support (expand as needed)
        if criteria.get("category"):
            query = query.filter(models.Recipe.category == criteria["category"])
        if criteria.get("cuisine"):
             query = query.filter(models.Recipe.cuisine == criteria["cuisine"])
        if criteria.get("difficulty"):
            query = query.filter(models.Recipe.difficulty == criteria["difficulty"])
            
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
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_active_user)
):
    meals = db.query(models.Meal).filter(models.Meal.user_id == current_user.id).offset(skip).limit(limit).all()
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
        
    # Not handling item updates here for brevity, usually separate endpoints or nested logic
    
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
