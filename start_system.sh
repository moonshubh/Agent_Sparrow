#!/bin/bash

# Script to start both the backend and frontend of the MB-Sparrow application

# Exit on any error
set -e

# --- Project Root and Log Setup ---
ROOT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"
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

echo "Installing Python dependencies..."
pip install -r requirements.txt

# Function to kill processes on a given port
kill_process_on_port() {
    PORT=$1
    echo "Checking for existing processes on port $PORT..."
    if ! command -v lsof &> /dev/null; then
        echo "lsof command not found. Cannot check for running processes."
        return
    fi
    
    PIDS=$(lsof -t -i:$PORT 2>/dev/null)
    if [ -z "$PIDS" ]; then
        echo "No process found on port $PORT."
    else
        echo "Killing processes on port $PORT: $PIDS"
        if ! kill -9 $PIDS; then
            echo "Failed to kill processes on port $PORT. Manual intervention may be required."
        else
            echo "Processes killed successfully."
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
echo "Backend available at http://localhost:8000"
echo "Frontend available at http://localhost:3000"

echo "To stop the servers, run: kill $BACKEND_PID $FRONTEND_PID"
