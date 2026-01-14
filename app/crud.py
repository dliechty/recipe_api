# crud.py
# Contains the functions for Create, Read, Update, Delete (CRUD) operations.

import logging
import uuid
from sqlalchemy.orm import Session, joinedload, selectinload
from datetime import datetime, timezone
from passlib.context import CryptContext
from uuid import UUID

from app import schemas
from app import filters
from app import models


pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

from app.core.hashing import calculate_recipe_checksum

# Get a logger instance
logger = logging.getLogger(__name__)


def check_cycle(db: Session, child_id: UUID, parent_id: UUID):
    """
    Check if setting parent_id for child_id would create a cycle.
    Traverses up from parent_id. If we encounter child_id, it's a cycle.
    """
    if child_id == parent_id:
        raise ValueError("A recipe cannot be its own parent")
    
    current_id = parent_id
    while current_id:
        # Fetch parent
        # Optimization: We only need the parent_recipe_id of the current node
        parent_node = db.query(models.Recipe.parent_recipe_id).filter(models.Recipe.id == current_id).first()
        if not parent_node:
            break # Parent not found? connection broken or root reached if we consider query failure (unlikely for valid IDs)
        
        # parent_node is a named tuple or result row? .parent_recipe_id accessed directly?
        # query(Column) returns a Row. row[0] or row.parent_recipe_id
        pid = parent_node[0]
        
        if pid == child_id:
            raise ValueError("Cycle detected: This would make a recipe a descendant of its own child")
        
        current_id = pid



def verify_password(plain_password, hashed_password):
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password):
    return pwd_context.hash(password)


# --- User CRUD Functions ---
def get_user(db: Session, user_id: UUID): # Changed to UUID
    return db.query(models.User).filter(models.User.id == user_id).first()


def get_user_by_email(db: Session, email: str):
    return db.query(models.User).filter(models.User.email == email.lower()).first()


def get_users(db: Session, skip: int = 0, limit: int = 100):
    return db.query(models.User).offset(skip).limit(limit).all()


def get_active_users(db: Session, skip: int = 0, limit: int = 100):
    return db.query(models.User).filter(models.User.is_active == True).offset(skip).limit(limit).all()


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
    return db.query(models.UserRequest).filter(models.UserRequest.email == email.lower()).first()


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
            joinedload(models.Recipe.instructions),
            joinedload(models.Recipe.diets),
            selectinload(models.Recipe.variants)
        )
        .filter(models.Recipe.id == recipe_id)
        .first()
    )


def get_recipes(db: Session, skip: int = 0, limit: int = 100, filters_list: list = None, sort_by: str = None):
    """
    Retrieve a list of recipes with filtering and sorting.
    """
    logger.debug(f"Retrieving recipes skip={skip}, limit={limit}, filters={filters_list}, sort={sort_by}")
    
    query = db.query(models.Recipe)
    
    if filters_list:
        query = filters.apply_filters(query, filters_list)

    # Perform counting before pagination, but AFTER filtering
    total_count = query.distinct().count() # distinct important if joins were added by filters

    # Apply sorting
    query = filters.apply_sorting(query, sort_by)

    # Apply pagination
    recipes = query.offset(skip).limit(limit).all()
    
    return recipes, total_count

def get_unique_values(db: Session, field: str):
    """
    Retrieve unique values for a specific field for metadata usage.
    """
    if field == 'category':
        return [r[0] for r in db.query(models.Recipe.category).distinct().filter(models.Recipe.category != None).order_by(models.Recipe.category).all()]
    elif field == 'cuisine':
        return [r[0] for r in db.query(models.Recipe.cuisine).distinct().filter(models.Recipe.cuisine != None).order_by(models.Recipe.cuisine).all()]
    elif field == 'difficulty':
        return [r[0].value for r in db.query(models.Recipe.difficulty).distinct().filter(models.Recipe.difficulty != None).all()]
    elif field == 'suitable_for_diet':
        # Many-to-Many logic? No, RecipeDiet is a table
        return [r[0].value for r in db.query(models.RecipeDiet.diet_type).distinct().all()]
    elif field == 'owner':
         # Return list of dicts? or just names? 
         # Plan said "return user emails or names"
         # Let's return objects `{"id": uuid, "name": "First Last"}` or similar?
         # Simplest for now: List of names
         users = db.query(models.User).join(models.Recipe).distinct().all()
         return [{"id": u.id, "name": f"{u.first_name} {u.last_name}" if u.first_name else u.email} for u in users]
    elif field == 'protein':
        return [r[0] for r in db.query(models.Recipe.protein).distinct().filter(models.Recipe.protein != None).order_by(models.Recipe.protein).all()]
    
    return []



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
        version=1,
        parent_recipe_id=recipe.parent_recipe_id
    )
    db.add(db_recipe)
    db.flush()  # Get recipe ID without committing transaction

    # Handle Components and Ingredients
    for comp in recipe.components:
        db_component = models.RecipeComponent(
            name=comp.name,
            recipe_id=db_recipe.id
        )
        db.add(db_component)
        db.flush()  # Get component ID without committing transaction

        for idx, item in enumerate(comp.ingredients):
            # Find or create the master ingredient
            ingredient_name = item.item
            ingredient = db.query(models.Ingredient).filter(models.Ingredient.name == ingredient_name).first()
            if not ingredient:
                ingredient = models.Ingredient(name=ingredient_name)
                db.add(ingredient)
                db.flush()  # Get ingredient ID without committing transaction

            # Create the recipe-ingredient link
            recipe_ingredient = models.RecipeIngredient(
                component_id=db_component.id,
                ingredient_id=ingredient.id,
                quantity=item.quantity,
                unit=item.unit,
                notes=item.notes,
                order=idx
            )
            db.add(recipe_ingredient)

    # Handle Instructions
    for item in recipe.instructions:
        instruction = models.Instruction(
            recipe_id=db_recipe.id,
            step_number=item.step_number,
            text=item.text
        )
        db.add(instruction)

    # Handle Diets
    for diet in recipe.suitable_for_diet:
        recipe_diet = models.RecipeDiet(
            recipe_id=db_recipe.id,
            diet_type=diet
        )
        db.add(recipe_diet)

    # Single commit for the entire transaction
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
    
    # Handle parent_recipe_id update
    if recipe_update.parent_recipe_id is not None:
        # Check if it changed
        if db_recipe.parent_recipe_id != recipe_update.parent_recipe_id:
             check_cycle(db, recipe_id, recipe_update.parent_recipe_id)
             db_recipe.parent_recipe_id = recipe_update.parent_recipe_id
    elif recipe_update.parent_recipe_id is None and 'parent_recipe_id' in recipe_update.model_dump(exclude_unset=True):
         # Explicitly set to None?
         # Schema has default=None, checking if it was intentionally unset or just default.
         # Actually Pydantic v2 `exclude_unset=True` works if the field was passed.
         # But usually update schemas use Optional fields for everything. 
         # recipe_update is RecipeCreate which has required fields for core etc. 
         # But parent_recipe_id is Optional=None.
         # If user PUTs the whole object and leaves parent_recipe_id as null, we should probably clear it?
         # Yes, "Full replacement strategy"
         db_recipe.parent_recipe_id = None

    
    if db_recipe.checksum != new_checksum:
        db_recipe.version = (db_recipe.version or 1) + 1
        db_recipe.checksum = new_checksum

    for key, value in update_data.items():
        setattr(db_recipe, key, value)

    # Clear and replace components
    # Cascade delete should handle their ingredients
    db.query(models.RecipeComponent).filter(models.RecipeComponent.recipe_id == recipe_id).delete()

    for comp in recipe_update.components:
        db_component = models.RecipeComponent(
            name=comp.name,
            recipe_id=recipe_id
        )
        db.add(db_component)
        db.flush()  # Get component ID without committing transaction

        for idx, item in enumerate(comp.ingredients):
            ingredient_name = item.item
            ingredient = db.query(models.Ingredient).filter(models.Ingredient.name == ingredient_name).first()
            if not ingredient:
                ingredient = models.Ingredient(name=ingredient_name)
                db.add(ingredient)
                db.flush()  # Get ingredient ID without committing transaction

            recipe_ingredient = models.RecipeIngredient(
                component_id=db_component.id,
                ingredient_id=ingredient.id,
                quantity=item.quantity,
                unit=item.unit,
                notes=item.notes,
                order=idx
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

    # Clear and replace diets
    db.query(models.RecipeDiet).filter(models.RecipeDiet.recipe_id == recipe_id).delete()
    for diet in recipe_update.suitable_for_diet:
        recipe_diet = models.RecipeDiet(
            recipe_id=recipe_id,
            diet_type=diet
        )
        db.add(recipe_diet)

    # Single commit for the entire transaction
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


# --- Comment CRUD Functions ---

def get_comment(db: Session, comment_id: UUID):
    return db.query(models.Comment).filter(models.Comment.id == comment_id).first()


def get_comments(db: Session, recipe_id: UUID, skip: int = 0, limit: int = 100):
    """
    Retrieve comments for a specific recipe.
    """
    # Assuming we want to show latest first? 
    # Logic in User story didn't specify, but models has order_by desc(created_at).
    # Relationship loading usually respects that, but explicit query is safer if we access directly.
    return (
        db.query(models.Comment)
        .filter(models.Comment.recipe_id == recipe_id)
        .order_by(models.Comment.created_at.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )


def create_comment(db: Session, comment: schemas.CommentCreate, user_id: UUID, recipe_id: UUID):
    db_comment = models.Comment(
        text=comment.text,
        user_id=user_id,
        recipe_id=recipe_id
    )
    db.add(db_comment)
    db.commit()
    db.refresh(db_comment)
    return db_comment


def update_comment(db: Session, comment_id: UUID, comment_update: schemas.CommentUpdate):
    db_comment = get_comment(db, comment_id)
    if not db_comment:
        return None
    
    db_comment.text = comment_update.text
    # created_at/updated_at handles itself via onupdate in model?
    # actually only if we use server_onupdate. 
    # Our model says: updated_at = Column(DateTime, default=func.now(), onupdate=func.now())
    # So SQLAlchemy should handle it on flush.
    
    db.add(db_comment)
    db.commit()
    db.refresh(db_comment)
    return db_comment


def delete_comment(db: Session, comment_id: UUID):
    db_comment = get_comment(db, comment_id)
    if db_comment:
        db.delete(db_comment)
        db.commit()
    return db_comment