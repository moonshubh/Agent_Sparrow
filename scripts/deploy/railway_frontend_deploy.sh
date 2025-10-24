#!/usr/bin/env bash
set -euo pipefail

# Deploy frontend to Railway using local code and frontend/.env.local values without printing secrets.
# Usage: scripts/deploy/railway_frontend_deploy.sh [project_name] [backend_api_url]

PROJECT_NAME=${1:-positive-curiosity}
API_URL=${2:-}

FRONTEND_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")/../../frontend" && pwd)
cd "$FRONTEND_DIR"

echo "Linking frontend directory to Railway project: $PROJECT_NAME"
railway link --project "$PROJECT_NAME" >/dev/null 2>&1 || railway init --project "$PROJECT_NAME"

# Helper to read a key's value from frontend/.env.local safely
get_env_val() {
  local key="$1"
  if [ -f .env.local ]; then
    local line
    line=$(grep -E "^${key}=" .env.local | head -n1 || true)
    if [ -n "$line" ]; then
      echo "${line#*=}"
      return 0
    fi
  fi
  return 1
}

set_var() {
  local key="$1"; shift
  local val="$1"; shift || true
  if [ -n "$val" ]; then
    echo "Setting $key"
    railway variables set "$key=$val" >/dev/null
  else
    echo "Skipping $key (no value)"
  fi
}

echo "Importing Supabase vars from frontend/.env.local"
SB_URL=$(get_env_val NEXT_PUBLIC_SUPABASE_URL || true)
SB_ANON=$(get_env_val NEXT_PUBLIC_SUPABASE_ANON_KEY || true)

set_var NEXT_PUBLIC_SUPABASE_URL "$SB_URL"
set_var NEXT_PUBLIC_SUPABASE_ANON_KEY "$SB_ANON"

echo "Enforcing OAuth-only and Mailbird domain on frontend"
railway variables set NEXT_PUBLIC_ENABLE_OAUTH=true NEXT_PUBLIC_LOCAL_AUTH_BYPASS=false NEXT_PUBLIC_ALLOWED_EMAIL_DOMAIN=getmailbird.com >/dev/null

if [ -n "$API_URL" ]; then
  set_var NEXT_PUBLIC_API_URL "$API_URL"
else
  echo "NOTE: Backend API URL not provided. After backend deploy, run:"
  echo "  cd frontend && railway variables set NEXT_PUBLIC_API_URL=https://<backend-domain> && railway up"
fi

echo "Deploying frontend from local source"
railway up

echo "Frontend deploy triggered. Once complete, copy the frontend domain and set:"
echo "  cd frontend && railway variables set NEXT_PUBLIC_AUTH_REDIRECT_URL=https://<frontend-domain>/auth/callback && railway up"

