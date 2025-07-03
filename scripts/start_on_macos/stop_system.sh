#!/bin/bash

# Script to stop all MB-Sparrow system services
echo "--- Stopping MB-Sparrow System ---"

# Function to kill processes gracefully
kill_service() {
    SERVICE_NAME=$1
    PORT=$2
    PATTERN=$3
    
    echo "Stopping $SERVICE_NAME..."
    
    # Try to kill by port
    if command -v lsof &> /dev/null && [ -n "$PORT" ]; then
        PIDS=$(lsof -t -i:$PORT 2>/dev/null || true)
        if [ -n "$PIDS" ]; then
            echo "  Killing $SERVICE_NAME processes on port $PORT: $PIDS"
            kill -TERM $PIDS 2>/dev/null || true
            sleep 2
            # Force kill if still running
            kill -9 $PIDS 2>/dev/null || true
        fi
    fi
    
    # Try to kill by pattern
    if [ -n "$PATTERN" ]; then
        PIDS=$(pgrep -f "$PATTERN" 2>/dev/null || true)
        if [ -n "$PIDS" ]; then
            echo "  Killing $SERVICE_NAME processes by pattern: $PIDS"
            kill -TERM $PIDS 2>/dev/null || true
            sleep 2
            # Force kill if still running
            kill -9 $PIDS 2>/dev/null || true
        fi
    fi
    
    echo "  $SERVICE_NAME stopped."
}

# Stop all services
kill_service "Backend (FastAPI)" "8000" "uvicorn.*app.main:app"
kill_service "Frontend (Next.js)" "3000" "next-server"
kill_service "FeedMe Celery Worker" "" "celery.*worker"

echo ""
echo "--- All services stopped ---"
echo "To restart the system, run: ./start_system.sh"