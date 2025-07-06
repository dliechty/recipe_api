# Recipe API
API for recipe and meal planning written using FastAPI, SqlAlchemy, and Alembic.

## Development Setup

1. Create python virtual environment: `python3 -m venv .venv`
2. Activate virtual environment: `source .venv/bin/activate`
3. Install python dependencies: `pip install -r ./requirements.txt`
4. Run alembic migration: `alembic upgrade head`
5. Run main file: `python3 main.py`

## Run dockerized container

`docker compose up --build`
