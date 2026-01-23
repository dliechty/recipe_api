# main.py
# Main application file for the FastAPI recipe service.

import logging.config
import os
from fastapi import FastAPI, Request
import uvicorn
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

# Import the CORS middleware
from fastapi.middleware.cors import CORSMiddleware

# Rate limiting
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

# Import local modules
from app.db.session import engine
from app import models
from app.api import auth, recipes, meals, lists
from app.core.config import settings
from app.core.logging_middleware import StructuredLoggingMiddleware

# Initialize rate limiter - uses client IP address for rate limit key
# Disabled during testing (when DATABASE_URL contains 'test')
_is_testing = "test" in os.environ.get("DATABASE_URL", "").lower()
limiter = Limiter(key_func=get_remote_address, enabled=not _is_testing)

# Load logging configuration
logging.config.fileConfig("logging.ini", disable_existing_loggers=False)

# Get the logger instance
logger = logging.getLogger(__name__)


# Create all database tables
# This line creates the 'recipes.db' file and the tables within it if they don't exist.
models.Base.metadata.create_all(bind=engine)

# Initialize the FastAPI app
app = FastAPI(
    title=settings.PROJECT_NAME,
    description="API for managing recipes, users, and meal plans.",
    version="1.0.0",
    root_path=settings.ROOT_PATH,
    openapi_url=f"{settings.API_V1_STR}/openapi.json",
)

# Add rate limiter to app state and register exception handler
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# --- Add Structured Logging Middleware ---
app.add_middleware(StructuredLoggingMiddleware)
# --- End of Structured Logging Middleware ---

# --- Add CORS Middleware ---
# Origins loaded from settings

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,  # Allows specified origins
    allow_credentials=True,  # Allows cookies to be included in requests
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],  # Explicit HTTP methods
    allow_headers=["Authorization", "Content-Type", "Accept"],  # Explicit headers
    expose_headers=["X-Total-Count"],  # Expose custom headers
)

# --- End of CORS Middleware Section ---

# --- Security Headers Middleware ---


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Add security headers to all responses."""

    async def dispatch(self, request: Request, call_next):
        response: Response = await call_next(request)
        # Prevent clickjacking
        response.headers["X-Frame-Options"] = "DENY"
        # Prevent MIME type sniffing
        response.headers["X-Content-Type-Options"] = "nosniff"
        # Enable XSS filter in browsers
        response.headers["X-XSS-Protection"] = "1; mode=block"
        # Control referrer information
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        # Content Security Policy - restrict resource loading
        if settings.ENVIRONMENT in ["development", "testing"]:
            # Relaxed to allow FastAPI Swagger UI assets
            response.headers["Content-Security-Policy"] = (
                "default-src 'self'; "
                "img-src 'self' data: https://fastapi.tiangolo.com; "
                "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
                "script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net"
            )
        else:
            response.headers["Content-Security-Policy"] = "default-src 'self'"
        return response


app.add_middleware(SecurityHeadersMiddleware)

# --- End of Security Headers Middleware ---

# Include API routers
# This makes the endpoints defined in the 'auth' and 'recipes' modules available.
app.include_router(auth.router, prefix="/auth", tags=["Authentication"])
app.include_router(recipes.router, prefix="/recipes", tags=["Recipes"])
app.include_router(meals.router, prefix="/meals", tags=["Meals"])
app.include_router(lists.router, prefix="/lists", tags=["Recipe Lists"])


@app.get("/", tags=["Root"])
async def read_root():
    """
    Root endpoint to check if the API is running.
    """
    logger.debug("Root endpoint accessed")
    return {"message": "Welcome to the Recipe Management API!"}


if __name__ == "__main__":
    # This block allows running the app directly with uvicorn for development.
    # In production, you would typically use a process manager like Gunicorn.
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
