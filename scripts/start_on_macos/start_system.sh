#!/bin/bash

# Script to start both the backend and frontend of the MB-Sparrow application

# Exit on any error
set -e

# --- Project Root and Log Setup ---
ROOT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
echo "Project Root: $ROOT_DIR"

LOG_DIR="$ROOT_DIR/system_logs"
BACKEND_LOG_DIR="$LOG_DIR/backend"
FRONTEND_LOG_DIR="$LOG_DIR/frontend"

mkdir -p "$BACKEND_LOG_DIR"
mkdir -p "$FRONTEND_LOG_DIR"

# --- Environment bootstrap ---
ENV_FILE="${ENV_PATH_OVERRIDE:-$ROOT_DIR/.env.local}"
if [ -f "$ENV_FILE" ]; then
  echo "Loading environment variables from $ENV_FILE"
  set -a
  # shellcheck disable=SC1090
  source "$ENV_FILE"
  set +a
fi

# Optional: sync local env files from a source repo (local-only; not committed).
# Source can come from ENV_SOURCE_ROOT or .context/env_source_root.
if [ -z "${ENV_SOURCE_ROOT:-}" ] && [ -f "$ROOT_DIR/.context/env_source_root" ]; then
  ENV_SOURCE_ROOT=$(head -n 1 "$ROOT_DIR/.context/env_source_root" | tr -d '\r')
fi
if [ -n "${ENV_SOURCE_ROOT:-}" ] && [ -x "$ROOT_DIR/scripts/dev/sync_env.sh" ]; then
  echo "Syncing env files from $ENV_SOURCE_ROOT"
  "$ROOT_DIR/scripts/dev/sync_env.sh" "$ENV_SOURCE_ROOT"
fi

# --- Backend Setup ---
echo "--- Starting Backend Server ---"
cd "$ROOT_DIR"

VENV_DIR="$ROOT_DIR/venv"
VENV_PY="$VENV_DIR/bin/python"
VENV_PIP="$VENV_DIR/bin/pip"

# Export Python path to ensure local package resolution
export PYTHONPATH="$ROOT_DIR:${PYTHONPATH}"

# Fix for macOS forking safety (prevents segfaults with some libraries)
export OBJC_DISABLE_INITIALIZE_FORK_SAFETY=YES

# Helper to detect python version of venv
get_python_version() {
    "$1" -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}")' 2>/dev/null || echo "unknown"
}

# Create venv if missing or if RECREATE_VENV=true
if [ ! -x "$VENV_PY" ] || [ "${RECREATE_VENV:-false}" = "true" ]; then
    echo "(Re)creating Python virtual environment..."
    # Prefer python3.11 if available to match runtime.txt
    if command -v python3.11 >/dev/null 2>&1; then
        python3.11 -m venv "$VENV_DIR"
    else
        # Fallback to python3
        python3 -m venv "$VENV_DIR"
    fi
fi

# Verify venv python version matches runtime expectation if possible
RUNTIME_VER=$(sed -E 's/.*([0-9]+\.[0-9]+\.[0-9]+).*/\1/' "$ROOT_DIR/runtime.txt" 2>/dev/null || echo "")
VENV_VER=$(get_python_version "$VENV_PY")
if [ -n "$RUNTIME_VER" ] && [ "$VENV_VER" != "unknown" ] && [ "${VENV_VER%%.*}" != "${RUNTIME_VER%%.*}" ]; then
    echo "Warning: venv Python version ($VENV_VER) differs from runtime.txt ($RUNTIME_VER)."
    echo "Set RECREATE_VENV=true to rebuild with preferred interpreter."
fi

echo "Upgrading pip in venv..."
"$VENV_PY" -m pip install --upgrade pip

echo "Installing Python dependencies into venv..."
# Use locked requirements file if available (much faster - no resolver backtracking)
if [ -f "$ROOT_DIR/requirements-lock.txt" ]; then
    echo "Using locked requirements (fast install)..."
    "$VENV_PIP" install -r requirements-lock.txt 2>/dev/null || echo "Note: Some dependency warnings are expected"
else
    echo "No lock file found, using requirements.txt (may take longer)..."
    "$VENV_PIP" install -r requirements.txt 2>/dev/null || echo "Note: Some dependency warnings are expected due to google-generativeai compatibility"
    # Generate lock file for future fast installs
    echo "Generating requirements-lock.txt for future fast installs..."
    "$VENV_PIP" freeze > "$ROOT_DIR/requirements-lock.txt" 2>/dev/null || true
fi

# Function to kill processes on a given port
kill_process_on_port() {
    PORT=$1
    echo "Checking for existing processes on port $PORT..."
    if ! command -v lsof &> /dev/null; then
        echo "lsof command not found. Cannot check for running processes."
        return
    fi
    
    PIDS=$(lsof -t -iTCP:$PORT -sTCP:LISTEN 2>/dev/null || true)
    if [ -z "$PIDS" ]; then
        echo "No process found on port $PORT."
    else
        echo "Gracefully terminating processes on port $PORT: $PIDS"
        # First, try graceful shutdown with SIGTERM
        if kill -15 $PIDS 2>/dev/null; then
            echo "Sent SIGTERM to processes. Waiting for graceful shutdown..."
            sleep 3
            
            # Check if processes are still running
            REMAINING_PIDS=$(lsof -t -iTCP:$PORT -sTCP:LISTEN 2>/dev/null || true)
            if [ -z "$REMAINING_PIDS" ]; then
                echo "Processes terminated gracefully."
            else
                echo "Some processes still running. Forcing termination with SIGKILL..."
                if kill -9 $REMAINING_PIDS 2>/dev/null; then
                    echo "Processes killed with SIGKILL."
                else
                    echo "Failed to kill processes on port $PORT. Manual intervention may be required."
                fi
            fi
        else
            echo "Failed to send SIGTERM. Trying SIGKILL directly..."
            if kill -9 $PIDS 2>/dev/null; then
                echo "Processes killed with SIGKILL."
            else
                echo "Failed to kill processes on port $PORT. Manual intervention may be required."
            fi
        fi
    fi
}

kill_process_on_port 8000

echo "Starting Uvicorn server in the background (venv python)..."
cd "$ROOT_DIR"
UVICORN_ARGS=(app.main:app --port 8000)
if [ "${ENABLE_UVICORN_RELOAD:-true}" = "true" ]; then
    UVICORN_ARGS+=(--reload)
fi
nohup "$VENV_PY" -m uvicorn "${UVICORN_ARGS[@]}" > "$BACKEND_LOG_DIR/backend.log" 2>&1 &
BACKEND_PID=$!
echo "Backend server started with PID: $BACKEND_PID"

verify_backend_pid() {
    sleep 5 # Give it a moment to start
    if ! kill -0 $BACKEND_PID 2>/dev/null; then
        return 1
    fi
    return 0
}

echo "Verifying backend server startup..."
if ! verify_backend_pid; then
    if [ "${ENABLE_UVICORN_RELOAD:-true}" = "true" ]; then
        echo "Reload mode failed. Retrying without --reload (watch permissions may be restricted)..."
        ENABLE_UVICORN_RELOAD=false
        UVICORN_ARGS=(app.main:app --port 8000)
        "$VENV_PY" -m uvicorn "${UVICORN_ARGS[@]}" > "$BACKEND_LOG_DIR/backend.log" 2>&1 &
        BACKEND_PID=$!
        echo "Backend server restarted with PID: $BACKEND_PID"
        if ! verify_backend_pid; then
            echo "Backend server failed to start. Check logs at $BACKEND_LOG_DIR/backend.log"
            exit 1
        fi
    else
        echo "Backend server failed to start. Check logs at $BACKEND_LOG_DIR/backend.log"
        exit 1
    fi
fi
if ! lsof -i :8000 -t >/dev/null; then
    echo "Backend server started but is not listening on port 8000. Check logs."
    exit 1
fi
echo "Backend server started successfully."


# --- FeedMe Celery Worker Setup ---
echo "--- Starting FeedMe Celery Worker ---"
cd "$ROOT_DIR"

# Check if Redis is running (required for Celery)
echo "Checking if Redis is running..."
if ! redis-cli ping > /dev/null 2>&1; then
    echo "Warning: Redis is not running. FeedMe Celery worker requires Redis."
    echo "Please start Redis with: brew services start redis (macOS) or sudo systemctl start redis (Linux)"
    echo "Continuing without Celery worker..."
else
    echo "Redis is running, starting FeedMe Celery worker..."
    
    # Create Celery log directory
    CELERY_LOG_DIR="$LOG_DIR/celery"
    mkdir -p "$CELERY_LOG_DIR"

    # Celery worker starts a lightweight health server (for Railway worker checks).
    # Avoid port collisions with the FastAPI backend when running everything locally.
    CELERY_HEALTH_PORT="${CELERY_HEALTH_PORT:-8001}"
    kill_process_on_port "$CELERY_HEALTH_PORT"
    
    # Kill any existing Celery workers
    echo "Checking for existing Celery workers..."
    if pgrep -f "celery.*worker" > /dev/null; then
        echo "Killing existing Celery workers..."
        pkill -f "celery.*worker" || true
        sleep 2
    fi
    
    # Start FeedMe Celery worker
    echo "Starting FeedMe Celery worker in the background (venv python)..."
    nohup env HEALTH_PORT="$CELERY_HEALTH_PORT" "$VENV_PY" -m celery -A app.feedme.celery_app worker \
        --loglevel=info \
        --concurrency=2 \
        --queues=feedme_default,feedme_processing,feedme_embeddings,feedme_parsing,feedme_health \
        > "$CELERY_LOG_DIR/celery_worker.log" 2>&1 &
    CELERY_PID=$!
    echo "FeedMe Celery worker started with PID: $CELERY_PID"
    
    # Verify Celery worker startup
    echo "Verifying Celery worker startup..."
    sleep 3
    if ! kill -0 $CELERY_PID 2>/dev/null; then
        echo "Warning: Celery worker failed to start. Check logs at $CELERY_LOG_DIR/celery_worker.log"
        echo "FeedMe background processing will not be available."
        CELERY_PID=""
    else
        echo "FeedMe Celery worker started successfully."
    fi
fi


# --- Frontend Setup ---
echo "--- Starting Frontend Server ---"
FRONTEND_DIR="$ROOT_DIR/frontend"
cd "$FRONTEND_DIR"

echo "Installing Node.js dependencies..."
pnpm install

kill_process_on_port 3000

echo "Starting Next.js development server in the background..."
# Some Next.js/Turbopack setups exit early when launched without a TTY.
# Use `script` to allocate a pseudo-tty when available.
if command -v script >/dev/null 2>&1; then
    nohup script -q /dev/null pnpm run dev > "$FRONTEND_LOG_DIR/frontend.log" 2>&1 &
else
    nohup pnpm run dev > "$FRONTEND_LOG_DIR/frontend.log" 2>&1 &
fi
FRONTEND_PID=$!
echo "Frontend server started with PID: $FRONTEND_PID"

echo "Verifying frontend server startup..."
sleep 10 # Give it more time as Next.js can be slow
if ! kill -0 $FRONTEND_PID 2>/dev/null; then
    echo "Frontend server failed to start. Check logs at $FRONTEND_LOG_DIR/frontend.log"
    exit 1
fi
if ! lsof -i :3000 -t >/dev/null; then
    echo "Frontend server started but is not listening on port 3000. Check logs."
    exit 1
fi
echo "Frontend server started successfully."


echo "--- System is starting up! ---"
echo "Backend logs: $BACKEND_LOG_DIR/backend.log"
echo "Frontend logs: $FRONTEND_LOG_DIR/frontend.log"
if [ -n "$CELERY_PID" ]; then
    echo "Celery worker logs: $CELERY_LOG_DIR/celery_worker.log"
fi
echo ""
echo "Services available:"
echo "  Backend API: http://localhost:8000"
echo "  Frontend UI: http://localhost:3000"
echo "  FeedMe v2.0: http://localhost:3000/feedme"
if [ -n "$CELERY_PID" ]; then
    echo "  FeedMe Processing: ✅ Active (Gemma 3 27b AI extraction)"
else
    echo "  FeedMe Processing: ❌ Inactive (background processing disabled)"
fi

# Build the kill command with all running service PIDs
KILL_PIDS="$BACKEND_PID $FRONTEND_PID"
if [ -n "$CELERY_PID" ]; then
    KILL_PIDS="$KILL_PIDS $CELERY_PID"
fi

echo "To stop all services, run: kill $KILL_PIDS"

# Also show individual service PIDs for granular control
echo ""
echo "Service PIDs:"
echo "  Backend (FastAPI): $BACKEND_PID"
echo "  Frontend (Next.js): $FRONTEND_PID"
if [ -n "$CELERY_PID" ]; then
    echo "  FeedMe Worker (Celery): $CELERY_PID"
fi
