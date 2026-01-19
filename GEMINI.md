# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Recipe API - A REST API for recipe and meal planning built with FastAPI, SQLAlchemy, and Alembic. Uses SQLite database with JWT authentication.

## Common Commands

```bash
# Development
uvicorn app.main:app --reload          # Run dev server (http://localhost:8000/docs)

# Testing
pytest                                  # Run all tests
pytest tests/test_api.py               # Run specific test file
pytest tests/test_api.py::test_name    # Run single test

# Database Migrations
alembic upgrade head                              # Apply all migrations
alembic revision --autogenerate -m "description"  # Create new migration
alembic downgrade -1                              # Revert last migration

# Linting
ruff check .                                      # Run linter
ruff check --fix .                                # Run linter and fix issues
ruff format .                                     # Format code

# Utilities
python3 -m app.initial_data            # Create initial superuser
python3 generate_openapi.py            # Generate OpenAPI spec

# Data Migration (from MS Access)
python3 migration_scripts/master_migration.py migrate-all      # Migrate recipes then meals
python3 migration_scripts/master_migration.py migrate-recipes  # Migrate only recipes
python3 migration_scripts/master_migration.py migrate-meals    # Migrate only meals
python3 migration_scripts/master_migration.py purge-all        # Purge meals then recipes
python3 migration_scripts/master_migration.py purge-recipes    # Purge only recipes
python3 migration_scripts/master_migration.py purge-meals      # Purge only meals
```

## Development Workflow

Before committing any changes, ensure the following steps are completed:
1. **Linting**: Run `ruff check .` to identify issues. Use `ruff check --fix .` to auto-fix where possible. All linting issues must be addressed.
2. **Testing**: Run the full test suite with `pytest`. Ensure all tests pass before proceeding with a commit.

## Migration Scripts

The `migration_scripts/` directory contains tools for migrating data from a legacy Microsoft Access database.

**Prerequisites:**
- Place the Access database at `migrate_data/Recipes.accdb`
- Install `mdbtools` (`apt install mdbtools` on Ubuntu/Debian)
- Ensure a user exists in the database (recipes/meals will be assigned to first admin user)

**Scripts:**
- `master_migration.py` - CLI entry point for all migration/purge operations
- `migrate_access_recipes.py` - Imports recipes, components, ingredients, instructions, and comments
- `migrate_access_meals.py` - Imports meal templates, slots, meals, and meal items
- `purge_recipes.py` - Deletes all recipe data (respects FK order)
- `purge_meals.py` - Deletes all meal data (respects FK order)
- `utils.py` - Shared utilities (`mdb-export` wrapper, user lookup, text cleaning)

**Migration Order:**
- Migrate: Recipes first (meals depend on recipe IDs)
- Purge: Meals first (meals depend on recipes)

## Architecture

**Layered Structure:**
- `app/api/` - Route handlers (auth.py, recipes.py, meals.py)
- `app/core/` - Configuration, hashing, logging middleware
- `app/db/` - Database session management
- `app/models.py` - SQLAlchemy ORM models
- `app/schemas.py` - Pydantic validation schemas
- `app/crud.py` - Database CRUD operations
- `app/filters.py` - Query filtering/sorting logic

**Key Patterns:**
- FastAPI dependency injection for DB sessions (`get_db()`) and auth (`get_current_active_user()`)
- UUID primary keys (not auto-increment)
- Pydantic v2 for request/response validation
- Alembic manages all schema migrations in `alembic/versions/`

**Domain Models:**
- User: Authentication with account lockout (5 failed attempts = 15-min lockout)
- Recipe: Components, ingredients, instructions, comments, versioning with SHA256 checksums
- MealPlanning: Meal templates with slot strategies (Direct, List, Search)

**Middleware Stack:**
- StructuredLoggingMiddleware - JSON logging with tail sampling
- SecurityHeadersMiddleware - CSP, X-Frame-Options, HSTS
- CORSMiddleware - Configurable origins
- RateLimiter - Per-IP rate limiting via slowapi

**Query System:**
- Filtering operators: eq, neq, gt, gte, lt, lte, in, like, all
- Multi-field sorting
- Pagination with skip/limit

## Configuration

Environment variables in `.env` (copy from `.env.example`):
- `SECRET_KEY` - Required, 32+ chars, validated against insecure defaults
- `FIRST_SUPERUSER_EMAIL` / `FIRST_SUPERUSER_PASSWORD` - Required for initial setup
- `DATABASE_URL` - Default: `sqlite:///./db/recipes.db`
- `CORS_ORIGINS` - JSON list format

Logging levels configured in `logging.ini`.

## Testing Notes

Tests use an in-memory SQLite database configured in `tests/conftest.py`. Rate limiting is disabled during tests.
