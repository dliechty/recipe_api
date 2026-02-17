# models.py
# Defines the SQLAlchemy ORM models for the database tables.

import uuid
from sqlalchemy import (
    Boolean,
    Column,
    ForeignKey,
    Integer,
    String,
    Text,
    Enum,
    DateTime,
    Date,
    func,
    Float,
    JSON,
)
from sqlalchemy.orm import relationship
from sqlalchemy.types import Uuid
from app.db.session import Base
import enum


class DifficultyLevel(str, enum.Enum):
    EASY = "Easy"
    MEDIUM = "Medium"
    HARD = "Hard"


class DietType(str, enum.Enum):
    DIABETIC = "diabetic"
    GLUTEN_FREE = "gluten-free"
    HALAL = "halal"
    HINDU = "hindu"
    KOSHER = "kosher"
    LOW_CALORIE = "low-calorie"
    LOW_FAT = "low-fat"
    LOW_LACTOSE = "low-lactose"
    LOW_SALT = "low-salt"
    VEGAN = "vegan"
    VEGETARIAN = "vegetarian"


class User(Base):
    """
    User model for the 'users' table.
    """

    __tablename__ = "users"

    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    email = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    first_name = Column(String, nullable=True)
    last_name = Column(String, nullable=True)
    is_admin = Column(Boolean, default=False)
    is_active = Column(Boolean, default=True, nullable=False)
    is_first_login = Column(Boolean, default=False)

    recipes = relationship("Recipe", back_populates="owner")
    comments = relationship("Comment", back_populates="user")
    recipe_lists = relationship(
        "RecipeList", back_populates="user", cascade="all, delete-orphan"
    )


class UserRequest(Base):
    """
    Model for pending user registration requests.
    """

    __tablename__ = "user_requests"

    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    email = Column(String, unique=True, index=True, nullable=False)
    first_name = Column(String, nullable=True)
    last_name = Column(String, nullable=True)
    created_at = Column(DateTime, default=func.now())


class Recipe(Base):
    """
    Recipe model for the 'recipes' table.
    """

    __tablename__ = "recipes"

    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)

    # Core fields
    name = Column(String, index=True, nullable=False)
    slug = Column(String, unique=True, index=True, nullable=True)
    description = Column(Text, nullable=True)

    yield_amount = Column(Float, nullable=True, index=True)
    yield_unit = Column(String, nullable=True)
    difficulty = Column(Enum(DifficultyLevel), nullable=True, index=True)
    cuisine = Column(String, nullable=True, index=True)
    category = Column(String, nullable=True, index=True)
    source = Column(String, nullable=True)
    protein = Column(String, nullable=True, index=True)
    source_url = Column(String, nullable=True)

    owner_id = Column(Uuid(as_uuid=True), ForeignKey("users.id"), index=True)

    # Times
    prep_time_minutes = Column(Integer, nullable=True, index=True)
    cook_time_minutes = Column(Integer, nullable=True, index=True)
    active_time_minutes = Column(Integer, nullable=True, index=True)
    total_time_minutes = Column(Integer, nullable=True, index=True)

    # Nutrition
    calories = Column(Integer, nullable=True, index=True)
    serving_size = Column(String, nullable=True)

    # Audit
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())
    version = Column(Integer, default=1)
    checksum = Column(String, nullable=True)
    last_cooked_at = Column(DateTime, nullable=True)

    parent_recipe_id = Column(
        Uuid(as_uuid=True), ForeignKey("recipes.id"), nullable=True, index=True
    )

    # Relationships
    parent = relationship("Recipe", remote_side=[id], backref="variants")
    owner = relationship("User", back_populates="recipes")

    components = relationship(
        "RecipeComponent", back_populates="recipe", cascade="all, delete-orphan"
    )

    instructions = relationship(
        "Instruction",
        back_populates="recipe",
        cascade="all, delete-orphan",
        order_by="Instruction.step_number",
    )

    comments = relationship(
        "Comment",
        back_populates="recipe",
        cascade="all, delete-orphan",
        order_by="desc(Comment.created_at)",
    )

    diets = relationship(
        "RecipeDiet", back_populates="recipe", cascade="all, delete-orphan"
    )

    def __str__(self):
        return f"{self.id}: {self.name}, by {self.owner.email}"


class RecipeComponent(Base):
    """
    Grouping of ingredients (e.g. "Main", "Frosting").
    """

    __tablename__ = "recipe_components"

    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    name = Column(String, default="Main")
    recipe_id = Column(Uuid(as_uuid=True), ForeignKey("recipes.id"), index=True)

    recipe = relationship("Recipe", back_populates="components")
    ingredients = relationship(
        "RecipeIngredient",
        back_populates="component",
        cascade="all, delete-orphan",
        order_by="RecipeIngredient.order",
    )


class Ingredient(Base):
    """
    Master list of ingredients.
    """

    __tablename__ = "ingredients"
    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    name = Column(String, unique=True, index=True, nullable=False)


class RecipeIngredient(Base):
    """
    Association object between RecipeComponent and Ingredient.
    """

    __tablename__ = "recipe_ingredients"
    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)

    component_id = Column(
        Uuid(as_uuid=True), ForeignKey("recipe_components.id"), index=True
    )
    ingredient_id = Column(Uuid(as_uuid=True), ForeignKey("ingredients.id"), index=True)

    quantity = Column(Float, nullable=False)
    unit = Column(String, nullable=False)
    notes = Column(Text, nullable=True)
    order = Column(Integer, default=0, nullable=False)

    component = relationship("RecipeComponent", back_populates="ingredients")
    ingredient = relationship("Ingredient")


class Instruction(Base):
    """
    An instruction step for a recipe.
    """

    __tablename__ = "instructions"
    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    step_number = Column(Integer, nullable=False)
    text = Column(Text, nullable=False)
    recipe_id = Column(Uuid(as_uuid=True), ForeignKey("recipes.id"), index=True)

    recipe = relationship("Recipe", back_populates="instructions")


class Comment(Base):
    """
    Comments on recipes.
    """

    __tablename__ = "comments"
    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    recipe_id = Column(
        Uuid(as_uuid=True), ForeignKey("recipes.id"), nullable=False, index=True
    )
    user_id = Column(
        Uuid(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True
    )
    text = Column(Text, nullable=False)
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())

    recipe = relationship("Recipe", back_populates="comments")
    user = relationship("User", back_populates="comments")


class RecipeDiet(Base):
    """
    Dietary suitabilities for a recipe.
    """

    __tablename__ = "recipe_diets"
    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    recipe_id = Column(
        Uuid(as_uuid=True), ForeignKey("recipes.id"), nullable=False, index=True
    )
    diet_type = Column(Enum(DietType), nullable=False)

    recipe = relationship("Recipe", back_populates="diets")


class MealClassification(str, enum.Enum):
    BREAKFAST = "Breakfast"
    BRUNCH = "Brunch"
    LUNCH = "Lunch"
    DINNER = "Dinner"
    SNACK = "Snack"


class MealStatus(str, enum.Enum):
    QUEUED = "Queued"
    COOKED = "Cooked"
    CANCELLED = "Cancelled"


class MealTemplateSlotStrategy(str, enum.Enum):
    DIRECT = "Direct"
    LIST = "List"
    SEARCH = "Search"


class MealTemplate(Base):
    """
    Template for generating meals.
    """

    __tablename__ = "meal_templates"

    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    user_id = Column(
        Uuid(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True
    )
    name = Column(String, nullable=False)
    classification = Column(Enum(MealClassification), nullable=True)
    slots_checksum = Column(String(64), nullable=True, index=True)
    last_used_at = Column(DateTime, nullable=True)

    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())

    user = relationship("User")
    slots = relationship(
        "MealTemplateSlot", back_populates="template", cascade="all, delete-orphan"
    )


class MealTemplateSlotRecipe(Base):
    """
    Association table for the LIST strategy in meal template slots.
    """

    __tablename__ = "meal_template_slot_recipes"

    slot_id = Column(
        Uuid(as_uuid=True), ForeignKey("meal_template_slots.id"), primary_key=True
    )
    recipe_id = Column(Uuid(as_uuid=True), ForeignKey("recipes.id"), primary_key=True)


class MealTemplateSlot(Base):
    """
    A slot within a meal template.
    """

    __tablename__ = "meal_template_slots"

    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    template_id = Column(
        Uuid(as_uuid=True), ForeignKey("meal_templates.id"), nullable=False, index=True
    )

    strategy = Column(Enum(MealTemplateSlotStrategy), nullable=False)

    # For DIRECT strategy
    recipe_id = Column(
        Uuid(as_uuid=True), ForeignKey("recipes.id"), nullable=True, index=True
    )

    # For SEARCH strategy
    search_criteria = Column(JSON, nullable=True)

    template = relationship("MealTemplate", back_populates="slots")
    recipe = relationship("Recipe")  # For DIRECT strategy

    # For LIST strategy
    recipes = relationship("Recipe", secondary="meal_template_slot_recipes")

    @property
    def recipe_ids(self):
        if self.recipes:
            return [r.id for r in self.recipes]
        return []


class Meal(Base):
    """
    A specific instance of a meal, potentially generated from a template.
    """

    __tablename__ = "meals"

    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    user_id = Column(
        Uuid(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True
    )
    template_id = Column(
        Uuid(as_uuid=True), ForeignKey("meal_templates.id"), nullable=True, index=True
    )

    name = Column(String, nullable=True)
    status = Column(Enum(MealStatus), default=MealStatus.QUEUED, nullable=False)
    classification = Column(Enum(MealClassification), nullable=True)
    scheduled_date = Column(Date, nullable=True)
    is_shopped = Column(Boolean, default=False, nullable=False)
    queue_position = Column(Integer, nullable=True)

    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())

    user = relationship("User")
    template = relationship("MealTemplate")
    items = relationship(
        "MealItem", back_populates="meal", cascade="all, delete-orphan"
    )


class MealItem(Base):
    """
    A specific item (recipe) within a meal. asd
    """

    __tablename__ = "meal_items"

    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    meal_id = Column(
        Uuid(as_uuid=True), ForeignKey("meals.id"), nullable=False, index=True
    )
    slot_id = Column(
        Uuid(as_uuid=True),
        ForeignKey("meal_template_slots.id"),
        nullable=True,
        index=True,
    )
    recipe_id = Column(
        Uuid(as_uuid=True), ForeignKey("recipes.id"), nullable=False, index=True
    )

    meal = relationship("Meal", back_populates="items")
    slot = relationship("MealTemplateSlot")
    recipe = relationship("Recipe")


class RecipeList(Base):
    """
    User-specific recipe list (e.g., "Favorites", "Want to Cook", "Cooked").
    """

    __tablename__ = "recipe_lists"

    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    user_id = Column(
        Uuid(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True
    )
    name = Column(String, nullable=False)
    description = Column(Text, nullable=True)

    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())

    user = relationship("User", back_populates="recipe_lists")
    items = relationship(
        "RecipeListItem", back_populates="recipe_list", cascade="all, delete-orphan"
    )

    @property
    def recipe_ids(self):
        if self.items:
            return [item.recipe_id for item in self.items]
        return []


class RecipeListItem(Base):
    """
    Association table linking recipes to recipe lists.
    """

    __tablename__ = "recipe_list_items"

    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    recipe_list_id = Column(
        Uuid(as_uuid=True), ForeignKey("recipe_lists.id"), nullable=False, index=True
    )
    recipe_id = Column(
        Uuid(as_uuid=True), ForeignKey("recipes.id"), nullable=False, index=True
    )
    added_at = Column(DateTime, default=func.now())

    recipe_list = relationship("RecipeList", back_populates="items")
    recipe = relationship("Recipe")
