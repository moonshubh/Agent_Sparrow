#!/bin/bash

# Production Startup Script for Agent Sparrow Frontend 2.0
# This script ensures both backend and frontend services are running correctly

set -e

# Color codes for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Get script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(dirname "$SCRIPT_DIR")"

echo -e "${GREEN}=== Agent Sparrow Production Startup ===${NC}"
echo "Root directory: $ROOT_DIR"

# Function to check if a port is in use
check_port() {
    local port=$1
    if lsof -Pi :$port -sTCP:LISTEN -t >/dev/null 2>&1; then
        return 0
    else
        return 1
    fi
}

# Function to wait for service
wait_for_service() {
    local url=$1
    local service_name=$2
    local max_attempts=30
    local attempt=1

    echo -n "Waiting for $service_name to be ready"
    while [ $attempt -le $max_attempts ]; do
        if curl -s -o /dev/null -w "%{http_code}" "$url" 2>/dev/null | grep -q "200\|404"; then
            echo -e " ${GREEN}✓${NC}"
            return 0
        fi
        echo -n "."
        sleep 1
        attempt=$((attempt + 1))
    done
    echo -e " ${RED}✗${NC}"
    return 1
}

# Check if backend is already running
echo -e "\n${YELLOW}1. Checking Backend Service${NC}"
if check_port 8000; then
    echo -e "Backend is already running on port 8000 ${GREEN}✓${NC}"

    # Verify it's responding
    if curl -s -o /dev/null -w "%{http_code}" http://localhost:8000/api/v1/feedme/health 2>/dev/null | grep -q "200"; then
        echo -e "Backend health check passed ${GREEN}✓${NC}"
    else
        echo -e "${YELLOW}Warning: Backend is running but health check failed${NC}"
        echo "You may need to restart the backend service"
    fi
else
    echo -e "${RED}Backend is NOT running${NC}"
    echo "Starting backend service..."

    cd "$ROOT_DIR"

    # Check for virtual environment
    if [ ! -d "venv" ]; then
        echo "Creating Python virtual environment..."
        python3 -m venv venv
    fi

    # Install dependencies
    echo "Installing backend dependencies..."
    ./venv/bin/pip install -q --upgrade pip
    ./venv/bin/pip install -q -r requirements.txt 2>/dev/null || {
        echo -e "${YELLOW}Some dependency warnings are normal${NC}"
    }

    # Start backend
    echo "Starting backend service..."

    # Use project system_logs folder structure by default
    LOG_DIR="${ROOT_DIR}/system_logs"
    BACKEND_LOG_DIR="${LOG_DIR}/backend"
    FRONTEND_LOG_DIR="${LOG_DIR}/frontend"
    mkdir -p "${BACKEND_LOG_DIR}" "${FRONTEND_LOG_DIR}"
    LOG_FILE="${BACKEND_LOG_DIR}/backend.log"

    # Start backend and write logs into system_logs/backend/backend.log
    nohup ./venv/bin/python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 > "${LOG_FILE}" 2>&1 &
    BACKEND_PID=$!

    # Wait for backend to be ready
    if wait_for_service "http://localhost:8000/api/v1/feedme/health" "Backend"; then
        echo -e "Backend started successfully (PID: $BACKEND_PID) ${GREEN}✓${NC}"
    else
        echo -e "${RED}Failed to start backend service${NC}"
        echo "Check logs at: ${LOG_FILE}"
        exit 1
    fi
fi

# Check if frontend is already running
echo -e "\n${YELLOW}2. Checking Frontend Service${NC}"
if check_port 3000; then
    echo -e "Frontend is already running on port 3000 ${GREEN}✓${NC}"
else
    echo -e "${RED}Frontend is NOT running${NC}"
    echo "Starting frontend service..."

    cd "$ROOT_DIR/frontend"

    # Install dependencies
    echo "Installing frontend dependencies..."
    npm install --legacy-peer-deps --silent

    # Build for production
    echo "Building frontend for production..."
    npm run build

    # Start frontend
    echo "Starting frontend service..."
    # Start frontend and write logs into system_logs/frontend/frontend.log
    nohup npm run start > "${FRONTEND_LOG_DIR}/frontend.log" 2>&1 &
    FRONTEND_PID=$!

    # Wait for frontend to be ready
    if wait_for_service "http://localhost:3000" "Frontend"; then
        echo -e "Frontend started successfully (PID: $FRONTEND_PID) ${GREEN}✓${NC}"
    else
        echo -e "${RED}Failed to start frontend service${NC}"
        echo "Check logs at: ${FRONTEND_LOG_DIR}/frontend.log"
        exit 1
    fi
fi

# Check Supabase connectivity
echo -e "\n${YELLOW}3. Checking Supabase Connection${NC}"
SUPABASE_URL=$(grep NEXT_PUBLIC_SUPABASE_URL "$ROOT_DIR/frontend/.env.local" | cut -d '=' -f2)
if [ -n "$SUPABASE_URL" ]; then
    if curl -s -o /dev/null -w "%{http_code}" "$SUPABASE_URL" 2>/dev/null | grep -q "200\|404"; then
        echo -e "Supabase is reachable at: $SUPABASE_URL ${GREEN}✓${NC}"
    else
        echo -e "${YELLOW}Warning: Cannot reach Supabase at $SUPABASE_URL${NC}"
        echo "Please check your Supabase configuration and network connection"
    fi
else
    echo -e "${YELLOW}Warning: NEXT_PUBLIC_SUPABASE_URL not configured${NC}"
    echo "Supabase features may not work properly"
fi

# Final status
echo -e "\n${GREEN}=== System Status ===${NC}"
echo -e "Backend API:  http://localhost:8000 ${GREEN}✓${NC}"
echo -e "Frontend UI:  http://localhost:3000 ${GREEN}✓${NC}"
echo -e "FeedMe App:   http://localhost:3000/feedme-revamped ${GREEN}✓${NC}"

# Health monitoring
echo -e "\n${YELLOW}=== Health Monitoring ===${NC}"
echo "The application includes automatic backend health monitoring."
echo "If the backend goes down, users will see helpful error messages."
echo ""
echo "To manually check backend health:"
echo "  curl http://localhost:8000/api/v1/feedme/health"
echo ""
echo "To view logs:"
echo "  Backend:  tail -f ${BACKEND_LOG_DIR}/backend.log"
echo "  Frontend: tail -f ${FRONTEND_LOG_DIR}/frontend.log"

echo -e "\n${GREEN}System is ready for production use!${NC}"