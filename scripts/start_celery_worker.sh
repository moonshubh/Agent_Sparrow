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

# Ensure system logs directory exists
LOG_DIR="$PROJECT_ROOT/system_logs/celery"
mkdir -p "$LOG_DIR"

# Start Celery worker with memory optimization flags
# --max-tasks-per-child: Restart worker after 50 tasks to prevent memory accumulation
# --max-memory-per-child: Restart worker if memory exceeds 512MB (in KB)
celery -A app.feedme.celery_app worker \
  --loglevel=info \
  --concurrency=2 \
  --hostname=feedme-worker@%h \
  --without-heartbeat \
  --without-gossip \
  --without-mingle \
  --max-tasks-per-child=50 \
  --max-memory-per-child=524288 \
  > "$LOG_DIR/celery_worker.log" 2>&1 &

echo "Celery worker started. Logs: $LOG_DIR/celery_worker.log"