# crud.py
# Contains the functions for Create, Read, Update, Delete (CRUD) operations.

import logging
from sqlalchemy.orm import Session, joinedload
from passlib.context import CryptContext

import models
import schemas

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# Get a logger instance
logger = logging.getLogger(__name__)


def verify_password(plain_password, hashed_password):
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password):
    return pwd_context.hash(password)


# --- User CRUD Functions ---
def get_user(db: Session, user_id: int):
    return db.query(models.User).filter(models.User.id == user_id).first()


def get_user_by_email(db: Session, email: str):
    return db.query(models.User).filter(models.User.email == email).first()


def get_users(db: Session, skip: int = 0, limit: int = 100):
    return db.query(models.User).offset(skip).limit(limit).all()


def create_user(db: Session, user: schemas.UserCreate):
    hashed_password = get_password_hash(user.password)
    db_user = models.User(email=user.email, hashed_password=hashed_password)
    db.add(db_user)
    db.commit()
    db.refresh(db_user)
    return db_user


# --- Recipe CRUD Functions ---
def get_recipe(db: Session, recipe_id: int):
    """
    Retrieve a single recipe with its related ingredients, instructions, and tags.
    """
    logger.debug(f"Retrieving recipe with id {recipe_id}")
    return (
        db.query(models.Recipe)
        .options(
            joinedload(models.Recipe.ingredients).joinedload(models.RecipeIngredient.ingredient),
            joinedload(models.Recipe.instructions),
            joinedload(models.Recipe.tags)
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


def create_user_recipe(db: Session, recipe: schemas.RecipeCreate, user_id: int):
    """
    Create a new recipe and its associated ingredients, instructions, and tags.
    """
    logger.debug(f"Creating recipe: {recipe}")
    # Create the main recipe object
    db_recipe = models.Recipe(
        name=recipe.name,
        description=recipe.description,
        prep_time_minutes=recipe.prep_time_minutes,
        cook_time_minutes=recipe.cook_time_minutes,
        servings=recipe.servings,
        source=recipe.source,
        owner_id=user_id
    )
    db.add(db_recipe)
    db.commit()  # Commit to get the recipe ID

    # Handle Ingredients
    for item in recipe.ingredients:
        # Find or create the master ingredient
        ingredient = db.query(models.Ingredient).filter(models.Ingredient.name == item.ingredient_name).first()
        if not ingredient:
            ingredient = models.Ingredient(name=item.ingredient_name)
            db.add(ingredient)
            db.commit()

        # Create the recipe-ingredient link
        recipe_ingredient = models.RecipeIngredient(
            recipe_id=db_recipe.id,
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
            description=item.description
        )
        db.add(instruction)

    # Handle Tags
    for tag_name in recipe.tags:
        tag = db.query(models.Tag).filter(models.Tag.name == tag_name).first()
        if not tag:
            tag = models.Tag(name=tag_name)
            db.add(tag)
            db.commit()
        db_recipe.tags.append(tag)

    db.commit()
    db.refresh(db_recipe)
    return db_recipe


def update_recipe(db: Session, recipe_id: int, recipe_update: schemas.RecipeCreate):
    """
    Update an existing recipe. This function replaces the recipe's details,
    ingredients, instructions, and tags with the new data provided.
    """
    logger.debug(f"Updating recipe {recipe_id} with: {recipe_update}")
    db_recipe = get_recipe(db, recipe_id)
    if not db_recipe:
        return None

    logger.debug(f"Recipe {recipe_id} prior to update: {db_recipe}")

    # 1. Update the base recipe fields
    update_data = recipe_update.model_dump(exclude={'ingredients', 'instructions', 'tags'})
    for key, value in update_data.items():
        setattr(db_recipe, key, value)

    # 2. Clear and replace instructions
    db.query(models.Instruction).filter(models.Instruction.recipe_id == recipe_id).delete()
    for item in recipe_update.instructions:
        instruction = models.Instruction(
            recipe_id=recipe_id,
            step_number=item.step_number,
            description=item.description
        )
        db.add(instruction)

    # 3. Clear and replace ingredients
    db.query(models.RecipeIngredient).filter(models.RecipeIngredient.recipe_id == recipe_id).delete()
    for item in recipe_update.ingredients:
        ingredient = db.query(models.Ingredient).filter(models.Ingredient.name == item.ingredient_name).first()
        if not ingredient:
            ingredient = models.Ingredient(name=item.ingredient_name)
            db.add(ingredient)
            db.commit()
            db.refresh(ingredient)

        recipe_ingredient = models.RecipeIngredient(
            recipe_id=recipe_id,
            ingredient_id=ingredient.id,
            quantity=item.quantity,
            unit=item.unit
        )
        db.add(recipe_ingredient)

    # 4. Clear and replace tags
    db_recipe.tags.clear()
    for tag_name in recipe_update.tags:
        tag = db.query(models.Tag).filter(models.Tag.name == tag_name).first()
        if not tag:
            tag = models.Tag(name=tag_name)
            db.add(tag)
            db.commit()
            db.refresh(tag)
        db_recipe.tags.append(tag)

    db.commit()
    db.refresh(db_recipe)
    return db_recipe


def delete_recipe(db: Session, recipe_id: int):
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