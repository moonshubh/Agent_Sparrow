#!/bin/bash

# Start Celery Worker for FeedMe Processing
echo "Starting FeedMe Celery Worker..."

# Set Python path to include the app directory
export PYTHONPATH="/Users/shubhpatel/Downloads/MB-Sparrow-main:$PYTHONPATH"

# Change to project directory
cd "/Users/shubhpatel/Downloads/MB-Sparrow-main"

# Start Celery worker
celery -A app.feedme.celery_app worker \
  --loglevel=info \
  --concurrency=2 \
  --hostname=feedme-worker@%h \
  --without-heartbeat \
  --without-gossip \
  --without-mingle