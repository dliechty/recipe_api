# api/auth.py
# Handles user authentication, registration, and token generation.

import logging
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from datetime import timedelta, datetime, timezone
from uuid import UUID

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


@router.get("/users/{user_id}", response_model=schemas.UserPublic)
def get_user_name(
    user_id: UUID, 
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user)
):
    """
    Get user public information (name) by ID.
    """
    db_user = crud.get_user(db, user_id=user_id)
    if db_user is None:
        raise HTTPException(status_code=404, detail="User not found")
    return db_user


@router.get("/users", response_model=list[schemas.UserPublic])
def list_active_users(
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user)
):
    """
    List all active users. Admin only.
    """
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Not authorized")
    return crud.get_active_users(db, skip=skip, limit=limit)


@router.post("/token", response_model=schemas.Token)
async def login(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
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


# --- New User Registration & Management Endpoints ---

from fastapi.responses import JSONResponse

@router.post("/request-account", status_code=status.HTTP_202_ACCEPTED)
def request_account(request: schemas.UserRequestCreate, db: Session = Depends(get_db)):
    """
    Submit a request for a new user account.
    """
    # Check if user already exists
    if crud.get_user_by_email(db, email=request.email):
        raise HTTPException(status_code=400, detail="Email already registered")
    
    # Check if request already exists
    if crud.get_user_request_by_email(db, email=request.email):
        return JSONResponse(status_code=200, content={"message": "Request already pending"})
    
    crud.create_user_request(db, request)
    return {"message": "Account request submitted"}


@router.get("/pending-requests", response_model=list[schemas.UserRequest])
def list_pending_requests(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user)
):
    """
    List all pending account requests. Admin only.
    """
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Not authorized")
    return crud.get_user_requests(db)


@router.post("/approve-request/{request_id}", response_model=schemas.User)
def approve_request(
    request_id: UUID,
    approval: schemas.ApproveRequest,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user)
):
    """
    Approve a pending account request and create the user. Admin only.
    """
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Not authorized")
    
    user_request = crud.get_user_request(db, request_id)
    if not user_request:
        raise HTTPException(status_code=404, detail="Request not found")
    
    # Create the user
    user_create = schemas.UserCreate(
        email=user_request.email,
        password=approval.initial_password,
        first_name=user_request.first_name,
        last_name=user_request.last_name
    )
    new_user = crud.create_user(db, user_create)
    
    # Set first login flag
    new_user.is_first_login = True
    db.add(new_user)
    
    # Delete the request
    crud.delete_user_request(db, request_id)
    db.commit() # Commit all changes including delete
    db.refresh(new_user)
    
    return new_user


@router.post("/change-password")
def change_password(
    password_data: schemas.PasswordChange,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user)
):
    """
    Change the current user's password.
    """
    if not crud.verify_password(password_data.old_password, current_user.hashed_password):
        raise HTTPException(status_code=400, detail="Incorrect old password")
    
    crud.change_password(db, current_user.id, password_data.new_password)
    return {"message": "Password updated successfully"}


@router.put("/users/{user_id}", response_model=schemas.UserPublic)
def update_user(
    user_id: UUID,
    user_update: schemas.UserUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user)
):
    """
    Update user profile. Users can update themselves; Admins can update anyone.
    """
    if user_id != current_user.id and not current_user.is_admin:
         raise HTTPException(status_code=403, detail="Not authorized")
    
    # Check if trying to update permissions
    if user_update.is_admin is not None:
        if not current_user.is_admin:
             raise HTTPException(status_code=403, detail="Only admins can promote users")
    
    updated_user = crud.update_user(db, user_id, user_update)
    if not updated_user:
        raise HTTPException(status_code=404, detail="User not found")
    return updated_user


@router.delete("/users/{user_id}")
def delete_user(
    user_id: UUID,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user)
):
    """
    Delete a user account. Admin only.
    """
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Not authorized")
    
    if crud.delete_user(db, user_id):
        return {"message": "User deleted"}
    raise HTTPException(status_code=404, detail="User not found")


@router.post("/users/{user_id}/reset")
def reset_user(
    user_id: UUID,
    approval: schemas.ApproveRequest, # Reusing schema for passing password
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user)
):
    """
    Reset a user's password and set is_first_login to True. Admin only.
    """
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Not authorized")
    
    user = crud.reset_user_password(db, user_id, approval.initial_password)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    return {"message": "User reset successfully"}
