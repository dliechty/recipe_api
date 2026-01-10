# Recipe API

API for recipe and meal planning written using FastAPI, SqlAlchemy, and Alembic.

## Development Setup

1. Create python virtual environment: `python3 -m venv .venv`
2. Activate virtual environment: `source .venv/bin/activate`
3. Install python dependencies: `pip install -r ./requirements.txt`
4. Run alembic migration: `alembic upgrade head`
5. Run the application: `uvicorn app.main:app --reload`
6. Connect to swagger API docs for testing: [http://localhost:8000/docs](http://localhost:8000/docs)

## Testing

Run the test suite using pytest:

```bash
pytest
```

## Deployment

For a detailed guide on deploying to a home server, please refer to [DEPLOYMENT.md](DEPLOYMENT.md).

### Docker

To run the application using Docker:

1. Create a `.env` file from the example:
   ```bash
   cp .env.example .env
   ```
2. Update the `.env` file with your secure settings (especially `SECRET_KEY`).
3. Build and run the container:
   ```bash
   docker compose up --build
   ```

### Manual Configuration

The application is configured using environment variables. Copy `.env.example` to `.env` and adjust the values:

- `PROJECT_NAME`: Name of the API.
- `SECRET_KEY`: **Critical**. Change this to a strong random string for production.
- `DATABASE_URL`: Database connection string.
- `CORS_ORIGINS`: List of allowed origins for frontend applications.

## Logging Level

Logging is controlled by the `logging.ini` file in the root directory.

To adjust the log level (e.g., from `DEBUG` to `INFO`):
1. Open `logging.ini`.
2. Locate the `[logger_root]` and `[logger_api]` sections.
3. Change the `level` value.

Example:
```ini
[logger_root]
level=INFO
```

## Admin Initial Setup

To create the initial Superuser account:

1. Configure `FIRST_SUPERUSER_EMAIL` and `FIRST_SUPERUSER_PASSWORD` in `.env` (required, password must be at least 12 characters).
2. Run the initialization script:

```bash
python3 -m app.initial_data
```

This will ensure a superuser exists. You can then log in and manage other users or requests.


## Generate OpenAPI Spec

To generate an updated `openapi.json` file reflecting the current API schema:

```bash
python3 generate_openapi.py
```

## Database Migrations (Alembic)

This project uses [Alembic](https://alembic.sqlalchemy.org) for database migrations.

### Creating Migrations

When you make changes to the existing models in `app/models`, you need to generate a new migration script:

```bash
alembic revision --autogenerate -m "Description of changes"
```

This will create a new file in `alembic/versions`. **Always review the generated script** to ensure it accurately reflects your intended changes.

### Applying Migrations

To apply pending migrations to your database (upgrade to the latest version):

```bash
alembic upgrade head
```

### Downgrading

If you need to revert the last migration:

```bash
alembic downgrade -1
```