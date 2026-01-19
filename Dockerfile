# Dockerfile

# 1. Use an official Python runtime as a parent image
FROM python:3.11-slim

# Copy uv from the official image
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# 2. Set the working directory in the container
WORKDIR /app

# 3. Copy the lockfile and pyproject.toml
COPY pyproject.toml uv.lock ./

# 4. Install the project's dependencies
RUN uv sync --frozen --no-install-project --no-dev

# 5. Copy the rest of the application's code into the container at /app
COPY . /app

# 6. Install the project itself
RUN uv sync --frozen --no-dev

RUN echo "alias migrate-access='apt update && apt install -y mdbtools && uv sync --no-dev --group migration && uv run python migration_scripts/master_migration.py purge-all && uv run python migration_scripts/master_migration.py migrate-all'" >> ~/.bashrc

# 7. Expose port 8000 to allow communication to the Uvicorn server
EXPOSE 8000

# 8. Define the command to run the application
# We use `uv run` to ensure the command runs within the virtual environment
CMD ["sh", "-c", "uv run --no-sync alembic upgrade head && uv run --no-sync uvicorn app.main:app --host 0.0.0.0 --port 8000"]