
import pytest
from typing import Generator
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# It is important to set environment variables before importing app modules
import os
os.environ["DATABASE_URL"] = "sqlite:///./test.db"

from app.db.session import Base, get_db
from app.main import app

# Create a test database
SQLALCHEMY_DATABASE_URL = "sqlite:///./test.db"
engine = create_engine(
    SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False}
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

@pytest.fixture(scope="session", autouse=True)
def db_engine():
    # Create tables
    Base.metadata.create_all(bind=engine)
    yield engine
    # Drop tables
    Base.metadata.drop_all(bind=engine)
    os.remove("./test.db")

@pytest.fixture(scope="function")
def db(db_engine) -> Generator:
    connection = db_engine.connect()
    transaction = connection.begin()
    session = TestingSessionLocal(bind=connection)
    yield session
    session.close()
    transaction.rollback()
    connection.close()

@pytest.fixture(scope="module")
def client() -> Generator:
    with TestClient(app) as c:
        yield c
