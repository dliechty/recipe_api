
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import field_validator
from typing import List, Optional

# Known insecure default values that must not be used
_INSECURE_SECRET_KEYS = {
    "your-super-secret-key",
    "change_this_to_a_secure_key_for_development_only",
    "secret",
    "changeme",
}

_INSECURE_PASSWORDS = {
    "admin123",
    "password",
    "123456",
    "admin",
    "changeme",
}

class Settings(BaseSettings):
    PROJECT_NAME: str = "Recipe Management API"
    ROOT_PATH: str = ""
    API_V1_STR: str = "/api/v1"
    SECRET_KEY: str  # Required - must be set via environment variable
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    ALGORITHM: str = "HS256"

    @field_validator("SECRET_KEY")
    @classmethod
    def validate_secret_key(cls, v: str) -> str:
        if not v:
            raise ValueError("SECRET_KEY must be set")
        if v in _INSECURE_SECRET_KEYS:
            raise ValueError(
                "SECRET_KEY is set to a known insecure default. "
                "Please generate a secure random key (e.g., openssl rand -hex 32)"
            )
        if len(v) < 32:
            raise ValueError(
                "SECRET_KEY must be at least 32 characters long for security"
            )
        return v

    FIRST_SUPERUSER_EMAIL: Optional[str] = None
    FIRST_SUPERUSER_PASSWORD: Optional[str] = None
    FIRST_SUPERUSER_FIRST_NAME: str = "Admin"
    FIRST_SUPERUSER_LAST_NAME: str = "User"

    @field_validator("FIRST_SUPERUSER_EMAIL")
    @classmethod
    def validate_superuser_email(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        if v == "admin@example.com":
            raise ValueError(
                "FIRST_SUPERUSER_EMAIL cannot be the default 'admin@example.com'. "
                "Please set a real email address."
            )
        return v

    @field_validator("FIRST_SUPERUSER_PASSWORD")
    @classmethod
    def validate_superuser_password(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        if v in _INSECURE_PASSWORDS:
            raise ValueError(
                "FIRST_SUPERUSER_PASSWORD is set to a known insecure default. "
                "Please use a strong password (min 12 characters recommended)."
            )
        if len(v) < 12:
            raise ValueError(
                "FIRST_SUPERUSER_PASSWORD must be at least 12 characters long"
            )
        return v

    # Database
    DATABASE_URL: str = "sqlite:///./db/recipes.db"

    # Environment
    ENVIRONMENT: str = "production"

    # CORS
    # In production, you would handle this more robustly, possibly parsing a comma-separated string
    CORS_ORIGINS: List[str] = [
        "http://localhost:5173", 
        "http://localhost:3000"
    ]

    model_config = SettingsConfigDict(case_sensitive=True, env_file=".env")

settings = Settings()
