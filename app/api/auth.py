# api/auth.py
# Handles user authentication, registration, and token generation.

import logging
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from datetime import timedelta, datetime, timezone

from jose import JWTError, jwt

# Import local modules
from app import crud
from app import schemas
from app import models
from app.db.session import get_db
from app.core.config import settings

# --- Configuration for JWT ---
# Loaded from settings

# OAuth2 scheme definition
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="auth/token")

# Create an API router
router = APIRouter()

# Get a logger instance
logger = logging.getLogger(__name__)



# --- Utility Functions for JWT ---

def create_access_token(data: dict, expires_delta: timedelta | None = None):
    """
    Creates a new JWT access token.
    """
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(minutes=15)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)
    return encoded_jwt


# --- Dependency for Getting Current User ---

async def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)):
    """
    Decodes the JWT token to get the current user.
    This function is a dependency that can be used to protect endpoints.
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        email: str = payload.get("sub")
        if email is None:
            logger.error("Could not verify email")
            raise credentials_exception
        token_data = schemas.TokenData(email=email)
    except JWTError:
        logger.error("Invalid Auth Token")
        raise credentials_exception

    user = crud.get_user_by_email(db, email=token_data.email)
    if user is None:
        logger.error("Could not find user")
        raise credentials_exception
    logger.debug(f"Found user: {user.email}")
    return user


async def get_current_active_user(current_user: models.User = Depends(get_current_user)):
    """
    Checks if the current user is active.
    """
    if not current_user.is_active:
        logger.warning(f"User {current_user.email} is inactive")
        raise HTTPException(status_code=400, detail="Inactive user")
    return current_user


# --- Authentication Endpoints ---

@router.post("/users/", response_model=schemas.User)
def create_user(user: schemas.UserCreate, db: Session = Depends(get_db)):
    """
    Endpoint to register a new user.
    """
    db_user = crud.get_user_by_email(db, email=user.email)
    if db_user:
        logger.warning(f"User {db_user.email} already registered")
        raise HTTPException(status_code=400, detail="Email already registered")
    return crud.create_user(db=db, user=user)


@router.post("/token", response_model=schemas.Token)
async def login_for_access_token(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    """
    Endpoint to log in a user and get an access token.
    """
    user = crud.get_user_by_email(db, email=form_data.username)
    if not user or not crud.verify_password(form_data.password, user.hashed_password):
        logger.warning("Incorrect password")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": user.email}, expires_delta=access_token_expires
    )
    return {"access_token": access_token, "token_type": "bearer"}