# crud.py
# Contains the functions for Create, Read, Update, Delete (CRUD) operations.

from sqlalchemy.orm import Session
from passlib.context import CryptContext

# Import local modules
import models
import schemas

# Setup password hashing context
# We use bcrypt as the hashing algorithm.
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def verify_password(plain_password, hashed_password):
    """Verifies a plain password against a hashed one."""
    return pwd_context.verify(plain_password, hashed_password)

def get_password_hash(password):
    """Hashes a plain password."""
    return pwd_context.hash(password)


# --- User CRUD Functions ---

def get_user(db: Session, user_id: int):
    """
    Retrieve a single user by their ID.
    """
    return db.query(models.User).filter(models.User.id == user_id).first()

def get_user_by_email(db: Session, email: str):
    """
    Retrieve a single user by their email address.
    """
    return db.query(models.User).filter(models.User.email == email).first()

def get_users(db: Session, skip: int = 0, limit: int = 100):
    """
    Retrieve a list of users with pagination.
    """
    return db.query(models.User).offset(skip).limit(limit).all()

def create_user(db: Session, user: schemas.UserCreate):
    """
    Create a new user in the database.
    Hashes the password before storing.
    """
    hashed_password = get_password_hash(user.password)
    db_user = models.User(email=user.email, hashed_password=hashed_password)
    db.add(db_user)
    db.commit()
    db.refresh(db_user)
    return db_user


# --- Recipe CRUD Functions ---

def get_recipes(db: Session, skip: int = 0, limit: int = 100):
    """
    Retrieve a list of recipes with pagination.
    """
    return db.query(models.Recipe).offset(skip).limit(limit).all()

def create_user_recipe(db: Session, recipe: schemas.RecipeCreate, user_id: int):
    """
    Create a new recipe associated with a specific user.
    """
    db_recipe = models.Recipe(**recipe.model_dump(), owner_id=user_id)
    db.add(db_recipe)
    db.commit()
    db.refresh(db_recipe)
    return db_recipe

def get_recipe(db: Session, recipe_id: int):
    """
    Retrieve a single recipe by its ID.
    """
    return db.query(models.Recipe).filter(models.Recipe.id == recipe_id).first()

def update_recipe(db: Session, recipe_id: int, recipe_update: schemas.RecipeCreate):
    """
    Update an existing recipe.
    """
    db_recipe = get_recipe(db, recipe_id)
    if db_recipe:
        update_data = recipe_update.model_dump(exclude_unset=True)
        for key, value in update_data.items():
            setattr(db_recipe, key, value)
        db.commit()
        db.refresh(db_recipe)
    return db_recipe

def delete_recipe(db: Session, recipe_id: int):
    """
    Delete a recipe from the database.
    """
    db_recipe = get_recipe(db, recipe_id)
    if db_recipe:
        db.delete(db_recipe)
        db.commit()
    return db_recipe