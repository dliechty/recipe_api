# Deployment Guide

This guide explains how to deploy the Recipe Management API on your home server using Docker and Docker Compose. This is the recommended approach as it encapsulates the application and its dependencies, ensuring consistent behavior.

## Prerequisites

- [Docker](https://docs.docker.com/get-docker/) installed on your server.
- [Docker Compose](https://docs.docker.com/compose/install/) installed (usually included with Docker Desktop/Engine).
- Git (to clone the repository).

## Quick Start

1. **Clone the Repository**
   ```bash
   git clone <your-repo-url>
   cd recipe_api
   ```

2. **Configure Environment**
   Create a `.env` file from the example:
   ```bash
   cp .env.example .env
   ```
   Edit `.env` and set a secure `SECRET_KEY`.
   ```bash
   # On Linux/standard setups, you can generate a key with:
   openssl rand -hex 32
   ```

3. **Start the Service**
   Run the application in the background:
   ```bash
   docker-compose up -d --build
   ```

4. **Verify Deployment**
   The API should now be accessible at `http://localhost:8000`.
   - Docs: [http://localhost:8000/docs](http://localhost:8000/docs)
   - OpenAPI: [http://localhost:8000/api/v1/openapi.json](http://localhost:8000/api/v1/openapi.json)

## Management

### Stopping the Service
```bash
docker-compose down
```

### Viewing Logs
```bash
docker-compose logs -f
```

### Updating the Application
Pull the latest changes and restart:
```bash
git pull
docker-compose up -d --build
```

### Database Persistence
The SQLite database is stored in a Docker volume named `database-data` mounted to `/app/db`. This ensures your recipes are saved even if you restart or rebuild the container.

To back up the database, you can copy the file from the volume or container:
```bash
docker cp recipe_api_app:/app/db/recipes.db ./backup_recipes.db
```

## Troubleshooting

- **Port Conflicts**: If port 8000 is already in use, edit `docker-compose.yml` and change the mapping (e.g., `"8080:8000"` to expose on port 8080).
- **Database Issues**: If you need to reset the database completely, run `docker-compose down -v` (WARNING: This deletes all data).
