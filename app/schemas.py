# schemas.py
# Defines the Pydantic models (schemas) for data validation and serialization.

from pydantic import BaseModel, EmailStr
from typing import List, Optional
from decimal import Decimal


# --- Ingredient Schemas ---
class IngredientBase(BaseModel):
    name: str


class IngredientCreate(IngredientBase):
    pass


class Ingredient(IngredientBase):
    id: int

    class Config:
        from_attributes = True


# --- RecipeIngredient Schemas ---
class RecipeIngredientBase(BaseModel):
    ingredient_name: str
    quantity: Decimal
    unit: str
    notes: Optional[str] = None


class RecipeIngredientCreate(RecipeIngredientBase):
    pass


class RecipeIngredient(BaseModel):
    id: int
    ingredient: Ingredient
    quantity: Decimal
    unit: str
    notes: Optional[str] = None

    class Config:
        from_attributes = True


# --- Instruction Schemas ---
class InstructionBase(BaseModel):
    step_number: int
    description: str


class InstructionCreate(InstructionBase):
    pass


class Instruction(InstructionBase):
    id: int

    class Config:
        from_attributes = True


# --- Tag Schemas ---
class TagBase(BaseModel):
    name: str


class TagCreate(TagBase):
    pass


class Tag(TagBase):
    id: int

    class Config:
        from_attributes = True


# --- Recipe Schemas ---
class RecipeBase(BaseModel):
    name: str
    description: Optional[str] = None
    prep_time_minutes: int
    cook_time_minutes: int
    servings: int
    source: Optional[str] = None

    def __str__(self):
        return self.name


class RecipeCreate(RecipeBase):
    ingredients: List[RecipeIngredientCreate]
    instructions: List[InstructionCreate]
    tags: List[str] = []


class Recipe(RecipeBase):
    id: int
    owner_id: int
    ingredients: List[RecipeIngredient] = []
    instructions: List[Instruction] = []
    tags: List[Tag] = []

    def __str__(self):
        return f"{self.id}: {self.name}, by owner with id {self.owner_id}"

    class Config:
        from_attributes = True


# --- User Schemas ---
class UserBase(BaseModel):
    email: EmailStr


class UserCreate(UserBase):
    password: str


class User(UserBase):
    id: int
    is_active: bool
    recipes: List[Recipe] = []

    class Config:
        from_attributes = True


# --- Token Schemas for Authentication ---
class Token(BaseModel):
    access_token: str
    token_type: str


class TokenData(BaseModel):
    email: Optional[str] = None