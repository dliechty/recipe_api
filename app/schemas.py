# schemas.py
# Defines the Pydantic models (schemas) for data validation and serialization.

from pydantic import BaseModel, EmailStr, ConfigDict, Field, model_validator
from typing import List, Optional, Any
from decimal import Decimal
from uuid import UUID
from datetime import datetime
from app.models import DifficultyLevel

# --- Basic Enums/Types ---

# --- Ingredient Schemas ---
class IngredientBase(BaseModel):
    name: str

class IngredientCreate(IngredientBase):
    pass

class Ingredient(IngredientBase):
    id: UUID
    model_config = ConfigDict(from_attributes=True)

# --- RecipeIngredient (Component Item) Schemas ---
class RecipeIngredientBase(BaseModel):
    quantity: float
    unit: str
    item: str = Field(..., alias="ingredient_name") # Map "item" in JSON to ingredient_name logic
    notes: Optional[str] = None

class RecipeIngredientCreate(RecipeIngredientBase):
    pass

class RecipeIngredient(BaseModel):
    quantity: float
    unit: str
    item: str
    notes: Optional[str] = None

    @model_validator(mode='before')
    @classmethod
    def map_ingredient_name(cls, data: Any) -> Any:
        if hasattr(data, "ingredient"):
            return {
                "quantity": data.quantity,
                "unit": data.unit,
                "item": data.ingredient.name,
                "notes": data.notes
            }
        return data

    model_config = ConfigDict(from_attributes=True)

# --- Component Schemas ---
class ComponentBase(BaseModel):
    name: str

class ComponentCreate(ComponentBase):
    ingredients: List[RecipeIngredientCreate]

class Component(ComponentBase):
    ingredients: List[RecipeIngredient]

    model_config = ConfigDict(from_attributes=True)

# --- Instruction Schemas ---
class InstructionBase(BaseModel):
    step_number: int
    text: str

class InstructionCreate(InstructionBase):
    pass

class Instruction(InstructionBase):
    model_config = ConfigDict(from_attributes=True)

# --- User Schemas ---
class UserBase(BaseModel):
    email: EmailStr

class UserCreate(UserBase):
    password: str

class User(UserBase):
    id: UUID
    is_active: bool
    model_config = ConfigDict(from_attributes=True)

# --- Nested Recipe Groups ---

class RecipeCoreBase(BaseModel):
    name: str
    slug: Optional[str] = None
    description_short: Optional[str] = None
    description_long: Optional[str] = None
    yield_amount: Optional[float] = None
    yield_unit: Optional[str] = None
    difficulty: Optional[DifficultyLevel] = None
    cuisine: Optional[str] = None
    category: Optional[str] = None
    source: Optional[str] = None
    source_url: Optional[str] = None

class RecipeCoreCreate(RecipeCoreBase):
    pass

class RecipeCore(RecipeCoreBase):
    id: UUID
    owner_id: UUID

class RecipeTimes(BaseModel):
    prep_time_minutes: Optional[int] = None
    cook_time_minutes: Optional[int] = None
    active_time_minutes: Optional[int] = None
    total_time_minutes: Optional[int] = None

class RecipeNutrition(BaseModel):
    calories: Optional[int] = None
    serving_size: Optional[str] = None

class RecipeAudit(BaseModel):
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    version: Optional[int] = None
    parent_recipe_id: Optional[UUID] = None

# --- Main Recipe Schemas ---

class RecipeCreate(BaseModel):
    core: RecipeCoreCreate
    times: RecipeTimes
    nutrition: RecipeNutrition
    # audit is usually server-managed
    audit: Optional[RecipeAudit] = None 
    components: List[ComponentCreate]
    instructions: List[InstructionCreate]


class Recipe(BaseModel):
    core: RecipeCore
    times: RecipeTimes
    components: List[Component]
    instructions: List[Instruction]
    nutrition: RecipeNutrition
    audit: RecipeAudit

    @model_validator(mode='before')
    @classmethod
    def transform_from_orm(cls, data: Any) -> Any:
        if hasattr(data, "id"):  # Is an ORM object
            return {
                "core": {
                    "id": data.id,
                    "name": data.name,
                    "slug": data.slug,
                    "description_short": data.description_short,
                    "description_long": data.description_long,
                    "yield_amount": data.yield_amount,
                    "yield_unit": data.yield_unit,
                    "difficulty": data.difficulty,
                    "cuisine": data.cuisine,
                    "category": data.category,
                    "source": data.source,
                    "source_url": data.source_url,
                    "owner_id": data.owner_id,
                },
                "times": {
                    "prep_time_minutes": data.prep_time_minutes,
                    "cook_time_minutes": data.cook_time_minutes,
                    "active_time_minutes": data.active_time_minutes,
                    "total_time_minutes": data.total_time_minutes,
                },
                "nutrition": {
                    "calories": data.calories,
                    "serving_size": data.serving_size,
                },
                "audit": {
                    "created_at": data.created_at,
                    "updated_at": data.updated_at,
                    "version": data.version,
                    "parent_recipe_id": data.parent_recipe_id,
                },
                "components": data.components,
                "instructions": data.instructions,
            }
        return data

    model_config = ConfigDict(from_attributes=True)


# --- Token Schemas ---
class Token(BaseModel):
    access_token: str
    token_type: str

class TokenData(BaseModel):
    email: Optional[str] = None