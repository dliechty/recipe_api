# models.py
# Defines the SQLAlchemy ORM models for the database tables.

from sqlalchemy import (
    Boolean, Column, ForeignKey, Integer, String, Text, Table, Numeric
)
from sqlalchemy.orm import relationship
from database import Base

# Association Table for Recipe and Tag (Many-to-Many)
recipe_tag_association = Table(
    'recipe_tag', Base.metadata,
    Column('recipe_id', Integer, ForeignKey('recipes.id'), primary_key=True),
    Column('tag_id', Integer, ForeignKey('tags.id'), primary_key=True)
)


class User(Base):
    """
    User model for the 'users' table.
    """
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    is_active = Column(Boolean, default=True)

    recipes = relationship("Recipe", back_populates="owner")


class Recipe(Base):
    """
    Recipe model for the 'recipes' table.
    This model is now normalized.
    """
    __tablename__ = "recipes"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, index=True, nullable=False)
    description = Column(Text, nullable=True)
    prep_time_minutes = Column(Integer)
    cook_time_minutes = Column(Integer)
    servings = Column(Integer)
    source = Column(String, nullable=True)
    owner_id = Column(Integer, ForeignKey("users.id"))

    owner = relationship("User", back_populates="recipes")

    # Relationships to new normalized tables
    ingredients = relationship("RecipeIngredient", back_populates="recipe", cascade="all, delete-orphan")
    instructions = relationship("Instruction", back_populates="recipe", cascade="all, delete-orphan")
    tags = relationship("Tag", secondary=recipe_tag_association, back_populates="recipes")


class Ingredient(Base):
    """
    Master list of ingredients.
    """
    __tablename__ = "ingredients"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, index=True, nullable=False)


class RecipeIngredient(Base):
    """
    Association object between Recipe and Ingredient.
    """
    __tablename__ = "recipe_ingredients"
    id = Column(Integer, primary_key=True, index=True)
    recipe_id = Column(Integer, ForeignKey("recipes.id"))
    ingredient_id = Column(Integer, ForeignKey("ingredients.id"))
    quantity = Column(Numeric(10, 2), nullable=False)
    unit = Column(String, nullable=False)

    recipe = relationship("Recipe", back_populates="ingredients")
    ingredient = relationship("Ingredient")


class Instruction(Base):
    """
    An instruction step for a recipe.
    """
    __tablename__ = "instructions"
    id = Column(Integer, primary_key=True, index=True)
    step_number = Column(Integer, nullable=False)
    description = Column(Text, nullable=False)
    recipe_id = Column(Integer, ForeignKey("recipes.id"))

    recipe = relationship("Recipe", back_populates="instructions")


class Tag(Base):
    """
    A tag for categorizing recipes.
    """
    __tablename__ = "tags"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, index=True, nullable=False)

    recipes = relationship("Recipe", secondary=recipe_tag_association, back_populates="tags")