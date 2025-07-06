# models.py
# Defines the SQLAlchemy ORM models for the database tables.

from sqlalchemy import Boolean, Column, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship

# Import the Base class from our database configuration.
from database import Base

class User(Base):
    """
    User model for the 'users' table.
    """
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    is_active = Column(Boolean, default=True)

    # Establish a one-to-many relationship with the Recipe model.
    # 'back_populates' creates a two-way relationship.
    recipes = relationship("Recipe", back_populates="owner")


class Recipe(Base):
    """
    Recipe model for the 'recipes' table.
    """
    __tablename__ = "recipes"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String, index=True, nullable=False)
    description = Column(Text, nullable=True)
    ingredients = Column(Text, nullable=False) # Storing as a simple text block for now
    instructions = Column(Text, nullable=False)
    owner_id = Column(Integer, ForeignKey("users.id"))

    # Establish a many-to-one relationship with the User model.
    owner = relationship("User", back_populates="recipes")