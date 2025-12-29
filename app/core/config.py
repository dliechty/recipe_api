
from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import List

class Settings(BaseSettings):
    PROJECT_NAME: str = "Recipe Management API"
    ROOT_PATH: str = ""
    API_V1_STR: str = "/api/v1"
    SECRET_KEY: str = "your-super-secret-key"  # Default for dev, override in prod
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    ALGORITHM: str = "HS256"

    FIRST_SUPERUSER_EMAIL: str = "admin@example.com"
    FIRST_SUPERUSER_PASSWORD: str = "admin123"
    
    # Database
    DATABASE_URL: str = "sqlite:///./db/recipes.db"

    # CORS
    # In production, you would handle this more robustly, possibly parsing a comma-separated string
    CORS_ORIGINS: List[str] = [
        "http://localhost:5173", 
        "http://localhost:3000"
    ]

    model_config = SettingsConfigDict(case_sensitive=True, env_file=".env")

settings = Settings()
