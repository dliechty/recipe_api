# api/auth.py
# Handles user authentication, registration, and token generation.

import logging
from fastapi import APIRouter, Depends, HTTPException, status, Request
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from datetime import timedelta, datetime, timezone
from uuid import UUID

from jose import JWTError, jwt
from slowapi import Limiter
from slowapi.util import get_remote_address

# Import local modules
from app import crud
from app import schemas
from app import models
from app.db.session import get_db
from app.core.config import settings

# Rate limiter instance (uses same key function as main app)
# Disabled during testing (when DATABASE_URL contains 'test')
import os
_is_testing = "test" in os.environ.get("DATABASE_URL", "").lower()
limiter = Limiter(key_func=get_remote_address, enabled=not _is_testing)

# --- Account Lockout Configuration ---
# In-memory storage for failed login attempts (for single-server deployments)
# For distributed systems, use Redis or database storage instead
from collections import defaultdict
from threading import Lock

MAX_FAILED_ATTEMPTS = 5
LOCKOUT_DURATION_MINUTES = 15

_failed_attempts: dict[str, list[datetime]] = defaultdict(list)
_failed_attempts_lock = Lock()


def _clean_old_attempts(email: str) -> None:
    """Remove failed attempts older than the lockout duration."""
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=LOCKOUT_DURATION_MINUTES)
    _failed_attempts[email] = [t for t in _failed_attempts[email] if t > cutoff]


def _is_account_locked(email: str) -> bool:
    """Check if account is locked due to too many failed attempts."""
    with _failed_attempts_lock:
        _clean_old_attempts(email)
        return len(_failed_attempts[email]) >= MAX_FAILED_ATTEMPTS


def _record_failed_attempt(email: str) -> None:
    """Record a failed login attempt."""
    with _failed_attempts_lock:
        _clean_old_attempts(email)
        _failed_attempts[email].append(datetime.now(timezone.utc))


def _clear_failed_attempts(email: str) -> None:
    """Clear failed attempts on successful login."""
    with _failed_attempts_lock:
        _failed_attempts[email] = []

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
        user_id_str: str = payload.get("sub")
        if user_id_str is None:
            logger.error("Could not verify user id")
            raise credentials_exception
        user_id = UUID(user_id_str)
        token_data = schemas.TokenData(id=user_id)
    except (JWTError, ValueError):
        logger.error("Invalid Auth Token or User ID")
        raise credentials_exception

    user = crud.get_user(db, user_id=token_data.id)
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
@limiter.limit("5/minute")  # Limit login attempts to prevent brute force
async def login(request: Request, form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    """
    Endpoint to log in a user and get an access token.
    Rate limited to 5 attempts per minute per IP address.
    Account is locked for 15 minutes after 5 failed attempts.
    """
    email = form_data.username.lower()

    # Check if account is locked
    if _is_account_locked(email):
        logger.warning(f"Login attempt for locked account: {email}")
        raise HTTPException(
            status_code=status.HTTP_423_LOCKED,
            detail=f"Account temporarily locked due to too many failed attempts. Try again in {LOCKOUT_DURATION_MINUTES} minutes.",
        )

    user = crud.get_user_by_email(db, email=email)
    if not user or not crud.verify_password(form_data.password, user.hashed_password):
        # Record failed attempt
        _record_failed_attempt(email)
        logger.warning(f"Failed login attempt for: {email}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Successful login - clear failed attempts
    _clear_failed_attempts(email)

    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": str(user.id)}, expires_delta=access_token_expires
    )
    return {"access_token": access_token, "token_type": "bearer"}


# --- New User Registration & Management Endpoints ---

from fastapi.responses import JSONResponse

@router.post("/request-account", status_code=status.HTTP_202_ACCEPTED)
@limiter.limit("3/minute")  # Limit account requests to prevent abuse
def request_account(request: Request, account_request: schemas.UserRequestCreate, db: Session = Depends(get_db)):
    """
    Submit a request for a new user account.
    Rate limited to 3 requests per minute per IP address.

    Note: Always returns 202 Accepted to prevent user enumeration attacks.
    The same response is returned whether or not the email is already registered.
    """
    # Check if user already exists or request already pending
    # We still perform these checks but don't reveal the result to the user
    user_exists = crud.get_user_by_email(db, email=account_request.email) is not None
    request_exists = crud.get_user_request_by_email(db, email=account_request.email) is not None

    # Only create a new request if email is not already registered or pending
    if not user_exists and not request_exists:
        crud.create_user_request(db, account_request)

    # Always return the same response to prevent enumeration
    return {"message": "If this email is not already registered, an account request has been submitted"}


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
