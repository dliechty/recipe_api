# schemas.py
# Defines the Pydantic models (schemas) for data validation and serialization.

from pydantic import BaseModel, EmailStr
from typing import List, Optional

# --- Recipe Schemas ---

class RecipeBase(BaseModel):
    """
    Base schema for a recipe, containing common attributes.
    """
    title: str
    description: Optional[str] = None
    ingredients: str
    instructions: str

class RecipeCreate(RecipeBase):
    """
    Schema used for creating a new recipe. Inherits from RecipeBase.
    """
    pass

class Recipe(RecipeBase):
    """
    Schema for returning a recipe from the API.
    Includes the id and owner_id from the database model.
    """
    id: int
    owner_id: int

    class Config:
        """
        Pydantic's configuration class.
        'from_attributes = True' allows Pydantic to read the data from ORM models.
        """
        from_attributes = True


# --- User Schemas ---

class UserBase(BaseModel):
    """
    Base schema for a user, with the email address.
    """
    email: EmailStr

class UserCreate(UserBase):
    """
    Schema for creating a new user. Includes the password.
    """
    password: str

class User(UserBase):
    """
    Schema for returning a user from the API.
    Excludes the password for security. Includes related recipes.
    """
    id: int
    is_active: bool
    recipes: List[Recipe] = []

    class Config:
        from_attributes = True


# --- Token Schemas for Authentication ---

class Token(BaseModel):
    """
    Schema for the access token returned upon successful login.
    """
    access_token: str
    token_type: str

class TokenData(BaseModel):
    """
    Schema for the data contained within a JWT token.
    """
    email: Optional[str] = None