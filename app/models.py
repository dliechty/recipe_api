# models.py
# Defines the SQLAlchemy ORM models for the database tables.

import uuid
from sqlalchemy import (
    Boolean, Column, ForeignKey, Integer, String, Text, Table, Numeric, Enum, DateTime, func, Float
)
from sqlalchemy.orm import relationship
from sqlalchemy.types import Uuid
from app.db.session import Base
import enum


class DifficultyLevel(str, enum.Enum):
    EASY = "Easy"
    MEDIUM = "Medium"
    HARD = "Hard"


class User(Base):
    """
    User model for the 'users' table.
    """
    __tablename__ = "users"

    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    email = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    is_active = Column(Boolean, default=True)

    first_name = Column(String, nullable=True)
    last_name = Column(String, nullable=True)
    is_admin = Column(Boolean, default=False)

    recipes = relationship("Recipe", back_populates="owner")


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
    
    yield_amount = Column(Float, nullable=True)
    yield_unit = Column(String, nullable=True)
    difficulty = Column(Enum(DifficultyLevel), nullable=True)
    cuisine = Column(String, nullable=True)
    category = Column(String, nullable=True)
    source = Column(String, nullable=True)
    source_url = Column(String, nullable=True)
    
    owner_id = Column(Uuid(as_uuid=True), ForeignKey("users.id"))

    # Times
    prep_time_minutes = Column(Integer, nullable=True)
    cook_time_minutes = Column(Integer, nullable=True)
    active_time_minutes = Column(Integer, nullable=True)
    total_time_minutes = Column(Integer, nullable=True)

    # Nutrition
    calories = Column(Integer, nullable=True)
    serving_size = Column(String, nullable=True)

    # Audit
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())
    version = Column(Integer, default=1)
    checksum = Column(String, nullable=True)
    parent_recipe_id = Column(Uuid(as_uuid=True), nullable=True)

    # Relationships
    owner = relationship("User", back_populates="recipes")
    
    components = relationship("RecipeComponent", back_populates="recipe", cascade="all, delete-orphan")
    
    instructions = relationship("Instruction", back_populates="recipe", cascade="all, delete-orphan")

    def __str__(self):
        return f"{self.id}: {self.name}, by {self.owner.email}"


class RecipeComponent(Base):
    """
    Grouping of ingredients (e.g. "Main", "Frosting").
    """
    __tablename__ = "recipe_components"
    
    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    name = Column(String, default="Main")
    recipe_id = Column(Uuid(as_uuid=True), ForeignKey("recipes.id"))
    
    recipe = relationship("Recipe", back_populates="components")
    ingredients = relationship("RecipeIngredient", back_populates="component", cascade="all, delete-orphan")


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
    
    component_id = Column(Uuid(as_uuid=True), ForeignKey("recipe_components.id"))
    ingredient_id = Column(Uuid(as_uuid=True), ForeignKey("ingredients.id"))
    
    quantity = Column(Numeric(10, 2), nullable=False)
    unit = Column(String, nullable=False)
    notes = Column(Text, nullable=True)

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
    recipe_id = Column(Uuid(as_uuid=True), ForeignKey("recipes.id"))

    recipe = relationship("Recipe", back_populates="instructions")