#!/usr/bin/env bash
set -euo pipefail

# Set up Redis and a Celery worker service on Railway.
# Usage:
#   scripts/deploy/railway_redis_and_worker.sh [project_name] [redis_url (optional)]

PROJECT_NAME=${1:-positive-curiosity}
REDIS_URL_INPUT=${2:-}

ROOT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)

echo "Linking to project: $PROJECT_NAME"
cd "$ROOT_DIR"
railway link --project "$PROJECT_NAME" >/dev/null 2>&1 || railway init --project "$PROJECT_NAME"

echo "Adding Redis plugin (if not already present)"
railway add redis || true

REDIS_URL="$REDIS_URL_INPUT"
if [ -z "$REDIS_URL" ]; then
  echo "Please open the Redis service in Railway and copy the REDIS_URL."
  echo "Then re-run this script as:"
  echo "  scripts/deploy/railway_redis_and_worker.sh $PROJECT_NAME REDIS_URL_HERE"
  exit 0
fi

echo "Configuring API service with Redis broker/backends"
railway service api >/dev/null 2>&1 || true
railway variables set REDIS_URL="$REDIS_URL" FEEDME_CELERY_BROKER="${REDIS_URL}/1" FEEDME_RESULT_BACKEND="${REDIS_URL}/2" >/dev/null
echo "Redeploying API to pick up Redis settings"
railway up

echo "Creating/Configuring Celery worker service (manual Start Command step)"
echo "Option A (recommended): In Railway UI, create a new service from this repo and set Start Command to:"
echo "  celery -A app.feedme.celery_app worker -Q feedme_default,feedme_processing,feedme_embeddings,feedme_health -O fair -l info --concurrency=2"
echo "Then set the same variables on the worker service: SUPABASE_URL, SUPABASE_ANON_KEY, SUPABASE_SERVICE_KEY, SUPABASE_JWT_SECRET, GEMINI_API_KEY, API_KEY_ENCRYPTION_SECRET, REDIS_URL, FEEDME_CELERY_BROKER, FEEDME_RESULT_BACKEND"

echo "Option B (CLI assist):"
echo "  1) railway init --project $PROJECT_NAME (create/select new service)"
echo "  2) railway service feedme-worker (rename/select)"
echo "  3) railway variables set SUPABASE_URL=... SUPABASE_ANON_KEY=... SUPABASE_SERVICE_KEY=... SUPABASE_JWT_SECRET=... GEMINI_API_KEY=... API_KEY_ENCRYPTION_SECRET=... REDIS_URL=$REDIS_URL FEEDME_CELERY_BROKER=${REDIS_URL}/1 FEEDME_RESULT_BACKEND=${REDIS_URL}/2"
echo "  4) In the UI, set Start Command to the Celery command above and deploy"

echo "To verify Celery availability, call the API /health endpoint; it reports a celery component if healthy."

