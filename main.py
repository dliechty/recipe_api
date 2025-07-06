# main.py
# Main application file for the FastAPI recipe service.

from fastapi import FastAPI, Depends, HTTPException, status
from sqlalchemy.orm import Session
import uvicorn

# Import local modules
from database import engine, get_db
import models
import schemas
import crud
from api import auth, recipes

# Create all database tables
# This line creates the 'recipes.db' file and the tables within it if they don't exist.
models.Base.metadata.create_all(bind=engine)

# Initialize the FastAPI app
app = FastAPI(
    title="Recipe Management API",
    description="API for managing recipes, users, and meal plans.",
    version="1.0.0",
)

# Include API routers
# This makes the endpoints defined in the 'auth' and 'recipes' modules available.
app.include_router(auth.router, prefix="/auth", tags=["Authentication"])
app.include_router(recipes.router, prefix="/recipes", tags=["Recipes"])

@app.get("/", tags=["Root"])
async def read_root():
    """
    Root endpoint to check if the API is running.
    """
    return {"message": "Welcome to the Recipe Management API!"}

if __name__ == "__main__":
    # This block allows running the app directly with uvicorn for development.
    # In production, you would typically use a process manager like Gunicorn.
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
