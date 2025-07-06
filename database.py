# database.py
# Configures the database connection and session management using SQLAlchemy.

from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

# Define the database URL.
# For SQLite, it's "sqlite:///./your_database_name.db"
# The "./" indicates that the file is in the same directory.
SQLALCHEMY_DATABASE_URL = "sqlite:///./recipes.db"

# Create the SQLAlchemy engine.
# The 'connect_args' is needed only for SQLite to allow multithreading.
engine = create_engine(
    SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False}
)

# Create a SessionLocal class. Each instance of this class will be a database session.
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Create a Base class. Our ORM models will inherit from this class.
Base = declarative_base()

# Dependency to get a database session.
# This will be used in our API endpoints to get a session for database operations.
def get_db():
    """
    SQLAlchemy session generator.
    Yields a session and ensures it's closed afterward.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()