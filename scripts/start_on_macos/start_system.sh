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

# --- Backend Setup ---
echo "--- Starting Backend Server ---"
cd "$ROOT_DIR"

# Create and activate Python virtual environment
if [ ! -d "venv" ]; then
    echo "Creating Python virtual environment..."
    python3 -m venv venv
fi

echo "Activating virtual environment..."
source venv/bin/activate

echo "Upgrading pip..."
python -m pip install --upgrade pip

echo "Installing Python dependencies..."
pip install -r requirements.txt 2>/dev/null || echo "Note: Some dependency warnings are expected due to google-generativeai compatibility"

# Function to kill processes on a given port
kill_process_on_port() {
    PORT=$1
    echo "Checking for existing processes on port $PORT..."
    if ! command -v lsof &> /dev/null; then
        echo "lsof command not found. Cannot check for running processes."
        return
    fi
    
    PIDS=$(lsof -t -i:$PORT 2>/dev/null || true)
    if [ -z "$PIDS" ]; then
        echo "No process found on port $PORT."
    else
        echo "Gracefully terminating processes on port $PORT: $PIDS"
        # First, try graceful shutdown with SIGTERM
        if kill -15 $PIDS 2>/dev/null; then
            echo "Sent SIGTERM to processes. Waiting for graceful shutdown..."
            sleep 3
            
            # Check if processes are still running
            REMAINING_PIDS=$(lsof -t -i:$PORT 2>/dev/null || true)
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

echo "Starting Uvicorn server in the background..."
uvicorn app.main:app --reload --port 8000 > "$BACKEND_LOG_DIR/backend.log" 2>&1 &
BACKEND_PID=$!
echo "Backend server started with PID: $BACKEND_PID"

echo "Verifying backend server startup..."
sleep 5 # Give it a moment to start
if ! ps -p $BACKEND_PID > /dev/null; then
    echo "Backend server failed to start. Check logs at $BACKEND_LOG_DIR/backend.log"
    exit 1
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
    
    # Kill any existing Celery workers
    echo "Checking for existing Celery workers..."
    if pgrep -f "celery.*worker" > /dev/null; then
        echo "Killing existing Celery workers..."
        pkill -f "celery.*worker" || true
        sleep 2
    fi
    
    # Start FeedMe Celery worker
    echo "Starting FeedMe Celery worker in the background..."
    python -m celery -A app.feedme.celery_app worker \
        --loglevel=info \
        --concurrency=2 \
        --queues=feedme_default,feedme_processing,feedme_embeddings,feedme_parsing,feedme_health \
        > "$CELERY_LOG_DIR/celery_worker.log" 2>&1 &
    CELERY_PID=$!
    echo "FeedMe Celery worker started with PID: $CELERY_PID"
    
    # Verify Celery worker startup
    echo "Verifying Celery worker startup..."
    sleep 3
    if ! ps -p $CELERY_PID > /dev/null; then
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
npm install --legacy-peer-deps

kill_process_on_port 3000

echo "Starting Next.js development server in the background..."
npm run dev > "$FRONTEND_LOG_DIR/frontend.log" 2>&1 &
FRONTEND_PID=$!
echo "Frontend server started with PID: $FRONTEND_PID"

echo "Verifying frontend server startup..."
sleep 10 # Give it more time as Next.js can be slow
if ! ps -p $FRONTEND_PID > /dev/null; then
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
