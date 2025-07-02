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

echo "Installing Python dependencies..."
pip install -r requirements.txt

echo "Starting Uvicorn server in the background..."
if lsof -i :8000 -t >/dev/null; then
    echo "Killing existing process on port 8000"
    lsof -t -i:8000 | xargs kill -9
fi
uvicorn app.main:app --reload --port 8000 > "$BACKEND_LOG_DIR/backend.log" 2>&1 &
BACKEND_PID=$!
echo "Backend server started with PID: $BACKEND_PID"
sleep 5

# --- Frontend Setup ---
echo "--- Starting Frontend Server ---"
FRONTEND_DIR="$ROOT_DIR/frontend"
cd "$FRONTEND_DIR"

echo "Installing Node.js dependencies..."
npm install --legacy-peer-deps

echo "Starting Next.js development server in the background..."
if lsof -i :3000 -t >/dev/null; then
    echo "Killing existing process on port 3000"
    lsof -t -i:3000 | xargs kill -9
fi
npm run dev > "$FRONTEND_LOG_DIR/frontend.log" 2>&1 &
FRONTEND_PID=$!
echo "Frontend server started with PID: $FRONTEND_PID"

echo "--- System is starting up! ---"
echo "Backend logs: $BACKEND_LOG_DIR/backend.log"
echo "Frontend logs: $FRONTEND_LOG_DIR/frontend.log"
echo "Backend available at http://localhost:8000"
echo "Frontend available at http://localhost:3000"

echo "To stop the servers, run: kill $BACKEND_PID $FRONTEND_PID"
