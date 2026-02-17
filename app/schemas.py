# schemas.py
# Defines the Pydantic models (schemas) for data validation and serialization.

from pydantic import (
    BaseModel,
    EmailStr,
    ConfigDict,
    Field,
    model_validator,
    field_validator,
)
from typing import List, Optional, Any
from uuid import UUID
from datetime import datetime, date
from app.models import (
    DifficultyLevel,
    DietType,
    MealClassification,
    MealStatus,
    MealTemplateSlotStrategy,
)
from app.unit_conversion import UnitSystem

# --- Search Criteria Validation ---

# Fields allowed in search criteria (must match filters.py ALLOWED_FIELDS + special fields)
ALLOWED_SEARCH_FIELDS = {
    "id",
    "name",
    "description",
    "category",
    "cuisine",
    "difficulty",
    "protein",
    "yield_amount",
    "calories",
    "prep_time_minutes",
    "cook_time_minutes",
    "active_time_minutes",
    "total_time_minutes",
    "ingredients",
    "suitable_for_diet",
    "owner",
}

# Valid operators for search criteria
ALLOWED_SEARCH_OPERATORS = {"eq", "neq", "gt", "gte", "lt", "lte", "in", "like", "all"}


class SearchCriterion(BaseModel):
    """A single search criterion for meal template SEARCH strategy."""

    field: str
    operator: str
    value: str | int | float

    @field_validator("field")
    @classmethod
    def validate_field(cls, v: str) -> str:
        if v not in ALLOWED_SEARCH_FIELDS:
            raise ValueError(
                f"Invalid search field '{v}'. Allowed fields: {sorted(ALLOWED_SEARCH_FIELDS)}"
            )
        return v

    @field_validator("operator")
    @classmethod
    def validate_operator(cls, v: str) -> str:
        if v not in ALLOWED_SEARCH_OPERATORS:
            raise ValueError(
                f"Invalid operator '{v}'. Allowed operators: {sorted(ALLOWED_SEARCH_OPERATORS)}"
            )
        return v

    @field_validator("value")
    @classmethod
    def validate_value(cls, v: str | int | float) -> str:
        # Convert to string for consistent storage and filtering
        str_val = str(v)
        if not str_val or not str_val.strip():
            raise ValueError("Search criterion value cannot be empty")
        return str_val


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
    item: str = Field(
        ..., alias="ingredient_name"
    )  # Map "item" in JSON to ingredient_name logic
    notes: Optional[str] = None


class RecipeIngredientCreate(RecipeIngredientBase):
    pass


class RecipeIngredient(BaseModel):
    quantity: float
    unit: str
    item: str
    notes: Optional[str] = None
    order: int = 0

    @model_validator(mode="before")
    @classmethod
    def map_ingredient_name(cls, data: Any) -> Any:
        if hasattr(data, "ingredient"):
            return {
                "quantity": data.quantity,
                "unit": data.unit,
                "item": data.ingredient.name,
                "notes": data.notes,
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
    first_name: Optional[str] = None
    last_name: Optional[str] = None

    @field_validator("email")
    @classmethod
    def lowercase_email(cls, v: str) -> str:
        return v.lower()


class UserCreate(UserBase):
    password: str


class User(UserBase):
    id: UUID
    is_active: bool
    is_admin: bool = False
    is_first_login: bool = False
    model_config = ConfigDict(from_attributes=True)


class UserPublic(BaseModel):
    id: UUID
    email: EmailStr
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    is_first_login: bool = False  # Useful for UI to redirect to change password
    is_admin: bool = False
    model_config = ConfigDict(from_attributes=True)


class UserUpdate(BaseModel):
    email: Optional[EmailStr] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    is_admin: Optional[bool] = None

    @field_validator("email")
    @classmethod
    def lowercase_email(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        return v.lower()


class PasswordChange(BaseModel):
    old_password: str
    new_password: str


# --- User Request Schemas ---
class UserRequestBase(BaseModel):
    email: EmailStr
    first_name: Optional[str] = None
    last_name: Optional[str] = None

    @field_validator("email")
    @classmethod
    def lowercase_email(cls, v: str) -> str:
        return v.lower()


class UserRequestCreate(UserRequestBase):
    pass


class UserRequest(UserRequestBase):
    id: UUID
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)


class ApproveRequest(BaseModel):
    initial_password: str


# --- Nested Recipe Groups ---


class RecipeCoreBase(BaseModel):
    name: str
    slug: Optional[str] = None
    description: Optional[str] = None
    yield_amount: Optional[float] = None
    yield_unit: Optional[str] = None
    difficulty: Optional[DifficultyLevel] = None
    cuisine: Optional[str] = None
    category: Optional[str] = None
    source: Optional[str] = None
    source_url: Optional[str] = None
    protein: Optional[str] = None


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
    checksum: Optional[str] = None
    last_cooked_at: Optional[datetime] = None


# --- Main Recipe Schemas ---


class RecipeCreate(BaseModel):
    core: RecipeCoreCreate
    times: RecipeTimes
    nutrition: RecipeNutrition
    # audit is usually server-managed
    audit: Optional[RecipeAudit] = None
    components: List[ComponentCreate]
    instructions: List[InstructionCreate]
    suitable_for_diet: List[DietType] = []
    parent_recipe_id: Optional[UUID] = None


class Recipe(BaseModel):
    core: RecipeCore
    times: RecipeTimes
    components: List[Component]
    instructions: List[Instruction]
    nutrition: RecipeNutrition
    suitable_for_diet: List[DietType]
    variant_recipe_ids: List[UUID]
    parent_recipe_id: Optional[UUID] = None
    audit: RecipeAudit
    unit_system: Optional[UnitSystem] = None

    @model_validator(mode="before")
    @classmethod
    def transform_from_orm(cls, data: Any) -> Any:
        if hasattr(data, "id"):  # Is an ORM object
            return {
                "core": {
                    "id": data.id,
                    "name": data.name,
                    "slug": data.slug,
                    "description": data.description,
                    "yield_amount": data.yield_amount,
                    "yield_unit": data.yield_unit,
                    "difficulty": data.difficulty,
                    "cuisine": data.cuisine,
                    "category": data.category,
                    "source": data.source,
                    "source_url": data.source_url,
                    "protein": data.protein,
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
                    "checksum": data.checksum,
                    "last_cooked_at": data.last_cooked_at,
                },
                "components": data.components,
                "instructions": data.instructions,
                "suitable_for_diet": [d.diet_type for d in data.diets]
                if data.diets
                else [],
                "variant_recipe_ids": [v.id for v in data.variants]
                if data.variants
                else [],
                "parent_recipe_id": data.parent_recipe_id,
            }
        return data

    model_config = ConfigDict(from_attributes=True)


# --- Token Schemas ---
class Token(BaseModel):
    access_token: str
    token_type: str


class TokenData(BaseModel):
    id: Optional[UUID] = None


# --- Comment Schemas ---


class CommentBase(BaseModel):
    text: str


class CommentCreate(CommentBase):
    pass


class CommentUpdate(CommentBase):
    pass


class Comment(CommentBase):
    id: UUID
    recipe_id: UUID
    user_id: UUID
    user: UserPublic  # Embed basic user info
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


# --- Meal Template Schemas ---


class MealTemplateSlotBase(BaseModel):
    strategy: MealTemplateSlotStrategy
    recipe_id: Optional[UUID] = None
    recipe_ids: Optional[List[UUID]] = None
    search_criteria: Optional[List[SearchCriterion]] = None

    @model_validator(mode="after")
    def validate_slot_strategy(self):
        if self.strategy == MealTemplateSlotStrategy.DIRECT and not self.recipe_id:
            raise ValueError("recipe_id is required for DIRECT strategy")
        if (
            self.strategy == MealTemplateSlotStrategy.SEARCH
            and not self.search_criteria
        ):
            raise ValueError("search_criteria is required for SEARCH strategy")
        if self.strategy == MealTemplateSlotStrategy.LIST and not self.recipe_ids:
            raise ValueError("recipe_ids is required for LIST strategy")
        return self


class MealTemplateSlotCreate(MealTemplateSlotBase):
    pass


class MealTemplateSlot(MealTemplateSlotBase):
    id: UUID
    template_id: UUID
    recipes: List[RecipeCore] = []  # For LIST strategy, handled via association

    @model_validator(mode="before")
    @classmethod
    def load_list_recipes(cls, data: Any) -> Any:
        if hasattr(data, "strategy") and data.strategy == MealTemplateSlotStrategy.LIST:
            # Pydantic will handle the list serialization if we just pass the object
            # But we might want schema for the recipes in the list?
            # For now, let's keep it simple.
            pass
        return data

    model_config = ConfigDict(from_attributes=True)


class MealTemplateBase(BaseModel):
    name: str
    classification: Optional[MealClassification] = None


class MealTemplateCreate(MealTemplateBase):
    slots: List[MealTemplateSlotCreate]


class MealTemplateUpdate(BaseModel):
    name: Optional[str] = None
    classification: Optional[MealClassification] = None
    # Updating slots is complex, might handle separately or replacement


class MealTemplate(MealTemplateBase):
    id: UUID
    user_id: UUID
    last_used_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime
    slots: List[MealTemplateSlot]

    model_config = ConfigDict(from_attributes=True)


# --- Meal Schemas ---


class MealItemBase(BaseModel):
    recipe_id: UUID


class MealItem(MealItemBase):
    id: UUID
    meal_id: UUID
    slot_id: Optional[UUID] = None
    # We could embed the full recipe here if needed

    model_config = ConfigDict(from_attributes=True)


class MealBase(BaseModel):
    name: Optional[str] = None
    status: MealStatus = MealStatus.QUEUED
    classification: Optional[MealClassification] = None
    scheduled_date: Optional[date] = None
    is_shopped: bool = False
    queue_position: Optional[int] = None


class MealCreate(MealBase):
    template_id: Optional[UUID] = None
    items: List[MealItemBase] = []


class MealUpdate(BaseModel):
    name: Optional[str] = None
    status: Optional[MealStatus] = None
    classification: Optional[MealClassification] = None
    scheduled_date: Optional[date] = None
    is_shopped: Optional[bool] = None
    queue_position: Optional[int] = None
    items: Optional[List[MealItemBase]] = None


class Meal(MealBase):
    id: UUID
    user_id: UUID
    template_id: Optional[UUID] = None
    created_at: datetime
    updated_at: datetime
    items: List[MealItem]

    model_config = ConfigDict(from_attributes=True)


# --- Meal Generation/Duplication Schemas ---


class MealScheduleRequest(BaseModel):
    """Optional scheduling parameters for meal generation or duplication."""

    scheduled_date: Optional[date] = None


class TemplateFilter(BaseModel):
    """A single filter criterion for template selection during generation."""

    field: str
    operator: str
    value: str


class MealGenerateRequest(BaseModel):
    """Request to generate multiple meals from user's templates."""

    count: int
    scheduled_dates: Optional[List[date]] = None
    template_filter: Optional[List[TemplateFilter]] = None


# --- Recipe List Schemas ---


class RecipeListItemBase(BaseModel):
    recipe_id: UUID


class RecipeListItem(RecipeListItemBase):
    id: UUID
    recipe_list_id: UUID
    added_at: datetime

    model_config = ConfigDict(from_attributes=True)


class RecipeListBase(BaseModel):
    name: str
    description: Optional[str] = None


class RecipeListCreate(RecipeListBase):
    pass


class RecipeListUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None


class RecipeList(RecipeListBase):
    id: UUID
    user_id: UUID
    created_at: datetime
    updated_at: datetime
    items: List[RecipeListItem] = []

    model_config = ConfigDict(from_attributes=True)


class RecipeListAddRecipe(BaseModel):
    recipe_id: UUID


class RecipeListRemoveRecipe(BaseModel):
    recipe_id: UUID
