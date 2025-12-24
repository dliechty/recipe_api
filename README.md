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

## Generate OpenAPI Spec

To generate an updated `openapi.json` file reflecting the current API schema:

```bash
python3 generate_openapi.py
```