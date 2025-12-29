# crud.py
# Contains the functions for Create, Read, Update, Delete (CRUD) operations.

import logging
import uuid
from sqlalchemy.orm import Session, joinedload
from datetime import datetime, timezone
from passlib.context import CryptContext
from uuid import UUID

from app import models
from app import schemas

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

from app.core.hashing import calculate_recipe_checksum

# Get a logger instance
logger = logging.getLogger(__name__)


def verify_password(plain_password, hashed_password):
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password):
    return pwd_context.hash(password)


# --- User CRUD Functions ---
def get_user(db: Session, user_id: UUID): # Changed to UUID
    return db.query(models.User).filter(models.User.id == user_id).first()


def get_user_by_email(db: Session, email: str):
    return db.query(models.User).filter(models.User.email == email).first()


def get_users(db: Session, skip: int = 0, limit: int = 100):
    return db.query(models.User).offset(skip).limit(limit).all()


def create_user(db: Session, user: schemas.UserCreate):
    hashed_password = get_password_hash(user.password)
    db_user = models.User(
        email=user.email, 
        hashed_password=hashed_password,
        first_name=user.first_name,
        last_name=user.last_name
    )
    db.add(db_user)
    db.commit()
    db.refresh(db_user)
    return db_user


def update_user(db: Session, user_id: UUID, user_update: schemas.UserUpdate):
    db_user = get_user(db, user_id)
    if not db_user:
        return None
    
    update_data = user_update.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(db_user, key, value)
    
    db.add(db_user)
    db.commit()
    db.refresh(db_user)
    return db_user


def delete_user(db: Session, user_id: UUID):
    db_user = get_user(db, user_id)
    if db_user:
        db.delete(db_user)
        db.commit()
    return db_user


def reset_user_password(db: Session, user_id: UUID, new_password: str):
    db_user = get_user(db, user_id)
    if not db_user:
        return None
    
    db_user.hashed_password = get_password_hash(new_password)
    db_user.is_first_login = True
    db.add(db_user)
    db.commit()
    db.refresh(db_user)
    return db_user


def change_password(db: Session, user_id: UUID, new_password: str):
    db_user = get_user(db, user_id)
    if not db_user:
        return None
    
    db_user.hashed_password = get_password_hash(new_password)
    db_user.is_first_login = False
    db.add(db_user)
    db.commit()
    db.refresh(db_user)
    return db_user


# --- User Request CRUD Functions ---

def get_user_request(db: Session, request_id: UUID):
    return db.query(models.UserRequest).filter(models.UserRequest.id == request_id).first()


def get_user_request_by_email(db: Session, email: str):
    return db.query(models.UserRequest).filter(models.UserRequest.email == email).first()


def get_user_requests(db: Session, skip: int = 0, limit: int = 100):
    return db.query(models.UserRequest).offset(skip).limit(limit).all()


def create_user_request(db: Session, request: schemas.UserRequestCreate):
    db_request = models.UserRequest(
        email=request.email,
        first_name=request.first_name,
        last_name=request.last_name
    )
    db.add(db_request)
    db.commit()
    db.refresh(db_request)
    return db_request


def delete_user_request(db: Session, request_id: UUID):
    db_request = get_user_request(db, request_id)
    if db_request:
        db.delete(db_request)
        db.commit()
    return db_request


# --- Recipe CRUD Functions ---
def get_recipe(db: Session, recipe_id: UUID): # Changed to UUID
    """
    Retrieve a single recipe with its related ingredients, instructions, and tags.
    Now also loads components.
    """
    logger.debug(f"Retrieving recipe with id {recipe_id}")
    return (
        db.query(models.Recipe)
        .options(
            joinedload(models.Recipe.components).joinedload(models.RecipeComponent.ingredients).joinedload(models.RecipeIngredient.ingredient),
            joinedload(models.Recipe.instructions)
        )
        .filter(models.Recipe.id == recipe_id)
        .first()
    )


def get_recipes(db: Session, skip: int = 0, limit: int = 100):
    """
    Retrieve a list of recipes.
    """
    logger.debug(f"Retrieving all recipes skipping {skip}, up to limit {limit}")
    return db.query(models.Recipe).offset(skip).limit(limit).all()


def create_user_recipe(db: Session, recipe: schemas.RecipeCreate, user_id: UUID): # user_id is UUID
    """
    Create a new recipe and its associated ingredients, instructions.
    """
    logger.debug(f"Creating recipe: {recipe}")
    
    # Extract data from nested schema groups
    core_data = recipe.core.model_dump()
    # Remove owner_id from core_data (handled by user_id arg) or verify match?
    # We'll use user_id argument as the authoritative source
    if 'owner_id' in core_data:
        del core_data['owner_id']
    if 'id' in core_data: # If ID is provided (bad practice usually for create, but if it is..)
        del core_data['id'] # Let DB/Model generate uuid

    times_data = recipe.times.model_dump()
    nutrition_data = recipe.nutrition.model_dump()
    audit_data = recipe.audit.model_dump(exclude_unset=True) if recipe.audit else {}
    
    # Explicit timestamp logic
    if 'created_at' not in audit_data:
        audit_data['created_at'] = datetime.now(timezone.utc)
    if 'updated_at' not in audit_data:
        audit_data['updated_at'] = datetime.now(timezone.utc)

    # Calculate Checksum
    checksum = calculate_recipe_checksum(recipe.model_dump(exclude={'audit'}))

    # Merge all flat fields
    recipe_kwargs = {**core_data, **times_data, **nutrition_data, **audit_data}
    
    # Create the main recipe object
    db_recipe = models.Recipe(
        **recipe_kwargs,
        owner_id=user_id,
        checksum=checksum,
        version=1
    )
    db.add(db_recipe)
    db.commit()
    db.refresh(db_recipe)

    # Handle Components and Ingredients
    for comp in recipe.components:
        db_component = models.RecipeComponent(
            name=comp.name,
            recipe_id=db_recipe.id
        )
        db.add(db_component)
        db.commit() # Commit to get ID
        
        for item in comp.ingredients:
            # Find or create the master ingredient
             # item.item is the name due to our schema mapping? No, schema says `item`
            ingredient_name = item.item 
            ingredient = db.query(models.Ingredient).filter(models.Ingredient.name == ingredient_name).first()
            if not ingredient:
                ingredient = models.Ingredient(name=ingredient_name)
                db.add(ingredient)
                db.commit()

            # Create the recipe-ingredient link
            recipe_ingredient = models.RecipeIngredient(
                component_id=db_component.id,
                ingredient_id=ingredient.id,
                quantity=item.quantity,
                unit=item.unit,
                notes=item.notes
            )
            db.add(recipe_ingredient)

    # Handle Instructions
    for item in recipe.instructions:
        instruction = models.Instruction(
            recipe_id=db_recipe.id,
            step_number=item.step_number,
            text=item.text # usage of 'text' field
        )
        db.add(instruction)

    db.commit()
    db.refresh(db_recipe)
    return db_recipe


def update_recipe(db: Session, recipe_id: UUID, recipe_update: schemas.RecipeCreate):
    """
    Update an existing recipe. 
    Full replacement strategy for sub-resources is simplest for this complexity.
    """
    logger.debug(f"Updating recipe {recipe_id} with: {recipe_update}")
    db_recipe = get_recipe(db, recipe_id)
    if not db_recipe:
        return None

    # Merge updates
    core_data = recipe_update.core.model_dump(exclude={'id', 'owner_id'}) 
    times_data = recipe_update.times.model_dump()
    nutrition_data = recipe_update.nutrition.model_dump()
    
    audit_data = recipe_update.audit.model_dump(exclude_unset=True) if recipe_update.audit else {}
    if 'updated_at' not in audit_data:
        audit_data['updated_at'] = datetime.now(timezone.utc)

    update_data = {**core_data, **times_data, **nutrition_data, **audit_data}
    
    # Calculate new checksum
    new_checksum = calculate_recipe_checksum(recipe_update.model_dump(exclude={'audit'}))
    
    if db_recipe.checksum != new_checksum:
        db_recipe.version = (db_recipe.version or 1) + 1
        db_recipe.checksum = new_checksum

    for key, value in update_data.items():
        setattr(db_recipe, key, value)

    # Clear and replace components
    # We might need to delete existing components
    # Cascade delete should handle their ingredients
    db.query(models.RecipeComponent).filter(models.RecipeComponent.recipe_id == recipe_id).delete()
    
    for comp in recipe_update.components:
        db_component = models.RecipeComponent(
            name=comp.name,
            recipe_id=recipe_id
        )
        db.add(db_component)
        db.commit() # Need ID
        
        for item in comp.ingredients:
            ingredient_name = item.item
            ingredient = db.query(models.Ingredient).filter(models.Ingredient.name == ingredient_name).first()
            if not ingredient:
                ingredient = models.Ingredient(name=ingredient_name)
                db.add(ingredient)
                db.commit()

            recipe_ingredient = models.RecipeIngredient(
                component_id=db_component.id,
                ingredient_id=ingredient.id,
                quantity=item.quantity,
                unit=item.unit,
                notes=item.notes
            )
            db.add(recipe_ingredient)

    # Clear and replace instructions
    db.query(models.Instruction).filter(models.Instruction.recipe_id == recipe_id).delete()
    for item in recipe_update.instructions:
        instruction = models.Instruction(
            recipe_id=recipe_id,
            step_number=item.step_number,
            text=item.text
        )
        db.add(instruction)

    db.commit()
    db.refresh(db_recipe)
    return db_recipe


def delete_recipe(db: Session, recipe_id: UUID):
    """
    Delete a recipe from the database.
    The cascade option in the model will handle deleting related items.
    """
    db_recipe = get_recipe(db, recipe_id)
    if db_recipe:
        logger.debug(f"Deleting recipe {recipe_id}")
        db.delete(db_recipe)
        db.commit()
    else:
        logger.debug(f"Recipe {recipe_id} not found - nothing to delete")
    return db_recipe