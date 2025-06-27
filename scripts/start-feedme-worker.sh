#!/bin/bash
# FeedMe v2.0 Phase 2: Start Celery Worker for Development
# Usage: ./scripts/start-feedme-worker.sh

set -e

echo "🚀 Starting FeedMe v2.0 Celery Worker..."

# Check if Redis is running
if ! redis-cli ping > /dev/null 2>&1; then
    echo "❌ Redis is not running. Please start Redis first:"
    echo "   brew services start redis  # macOS"
    echo "   sudo systemctl start redis  # Linux"
    echo "   docker run -d -p 6379:6379 redis:7-alpine  # Docker"
    exit 1
fi

echo "✅ Redis is running"

# Set environment variables
export FEEDME_ASYNC_PROCESSING=true
export FEEDME_CELERY_BROKER=${FEEDME_CELERY_BROKER:-redis://localhost:6379/1}
export FEEDME_RESULT_BACKEND=${FEEDME_RESULT_BACKEND:-redis://localhost:6379/2}

# Navigate to project root
cd "$(dirname "$0")/.."

# Check if required modules are available
echo "🔍 Checking Python dependencies..."
python -c "import celery, redis, bs4; print('✅ All dependencies available')" || {
    echo "❌ Missing dependencies. Please install:"
    echo "   pip install celery[redis] beautifulsoup4"
    exit 1
}

# Set Python path to ensure modules are found
export PYTHONPATH="$(pwd):$PYTHONPATH"

# Start Celery worker
echo "🔄 Starting Celery worker..."
celery -A app.feedme.celery_app worker \
    --loglevel=info \
    --concurrency=2 \
    --queues=feedme_default,feedme_processing,feedme_embeddings,feedme_parsing,feedme_health \
    --without-heartbeat \
    --without-gossip \
    --without-mingle

echo "✅ FeedMe Celery worker started successfully!"