#!/bin/bash

# Start Celery Worker for FeedMe Processing
echo "Starting FeedMe Celery Worker..."

# Get the directory where this script is located
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$SCRIPT_DIR"

# Set Python path to include the app directory
export PYTHONPATH="$PROJECT_ROOT:$PYTHONPATH"

# Change to project directory
cd "$PROJECT_ROOT"

# Start Celery worker
celery -A app.feedme.celery_app worker \
  --loglevel=info \
  --concurrency=2 \
  --hostname=feedme-worker@%h \
  --without-heartbeat \
  --without-gossip \
  --without-mingle