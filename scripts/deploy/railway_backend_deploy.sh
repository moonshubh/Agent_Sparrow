#!/usr/bin/env bash
set -euo pipefail

# Deploy backend API to Railway using local code and .env values without printing secrets.
# Usage: scripts/deploy/railway_backend_deploy.sh [project_name]

PROJECT_NAME=${1:-positive-curiosity}
SERVICE_NAME=${SERVICE_NAME:-api}

ROOT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
cd "$ROOT_DIR"

echo "Linking current directory to Railway project: $PROJECT_NAME"
railway link --project "$PROJECT_NAME" >/dev/null 2>&1 || railway init --project "$PROJECT_NAME"

# Helper to read a key's value from .env safely
get_env_val() {
  local key="$1"
  if [ -f .env ]; then
    # Grep the first occurrence of KEY= and return the value part only
    local line
    line=$(grep -E "^${key}=" .env | head -n1 || true)
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

echo "Selecting service: $SERVICE_NAME (if exists)"
railway service "$SERVICE_NAME" >/dev/null 2>&1 || true

echo "Applying production security flags"
railway variables set FORCE_PRODUCTION_SECURITY=true ENABLE_AUTH_ENDPOINTS=true ENABLE_API_KEY_ENDPOINTS=true SKIP_AUTH=false ENABLE_LOCAL_AUTH_BYPASS=false ALLOWED_OAUTH_EMAIL_DOMAINS=getmailbird.com >/dev/null

echo "Importing Supabase and key variables from .env"
SB_URL=$(get_env_val SUPABASE_URL || true)
SB_ANON=$(get_env_val SUPABASE_ANON_KEY || true)
SB_SERVICE=$(get_env_val SUPABASE_SERVICE_KEY || true)
SB_JWT=$(get_env_val SUPABASE_JWT_SECRET || true)
GEMINI=$(get_env_val GEMINI_API_KEY || true)
TAVILY=$(get_env_val TAVILY_API_KEY || true)
OPENAI=$(get_env_val OPENAI_API_KEY || true)
ENC_SECRET=$(get_env_val API_KEY_ENCRYPTION_SECRET || true)

set_var SUPABASE_URL "$SB_URL"
set_var SUPABASE_ANON_KEY "$SB_ANON"
set_var SUPABASE_SERVICE_KEY "$SB_SERVICE"
set_var SUPABASE_JWT_SECRET "$SB_JWT"
set_var GEMINI_API_KEY "$GEMINI"
[ -n "$TAVILY" ] && set_var TAVILY_API_KEY "$TAVILY"
[ -n "$OPENAI" ] && set_var OPENAI_API_KEY "$OPENAI"
[ -n "$ENC_SECRET" ] && set_var API_KEY_ENCRYPTION_SECRET "$ENC_SECRET"

echo "Deploying API from local source (Dockerfile)"
railway up

echo "Backend deploy triggered. Once complete, copy the public domain and set it on the frontend as NEXT_PUBLIC_API_URL."
echo "Optionally, set CORS_ALLOW_ORIGINS to your frontend domain and redeploy:"
echo "  railway variables set CORS_ALLOW_ORIGINS=https://<frontend-domain> && railway up"

