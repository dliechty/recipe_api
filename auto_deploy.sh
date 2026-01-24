#!/bin/bash

# Configuration
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOG_FILE="${PROJECT_DIR}/deploy.log"

cd "$PROJECT_DIR" || exit 1

# Fetch latest changes without merging
git fetch origin

# Check if local is behind upstream
LOCAL=$(git rev-parse @)
REMOTE=$(git rev-parse @{u})

if [ "$LOCAL" != "$REMOTE" ]; then
    echo "$(date): Changes detected. Updating..." >> "$LOG_FILE"
    
    # Pull changes
    git pull >> "$LOG_FILE" 2>&1
    
    # Rebuild and restart container
    echo "$(date): Rebuilding containers..." >> "$LOG_FILE"
    docker compose up -d --build >> "$LOG_FILE" 2>&1
    
    # Prune old images to save space
    docker image prune -f >> "$LOG_FILE" 2>&1
    
    echo "$(date): Update complete." >> "$LOG_FILE"
else
    # Uncomment the line below if you want a log entry every time it checks (can get spammy)
    # echo "$(date): No changes detected." >> "$LOG_FILE"
    exit 0
fi
