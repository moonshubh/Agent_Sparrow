@echo off
REM Batch script to start both the backend and frontend of the MB-Sparrow application on Windows

REM --- Project Root and Log Setup ---
set "ROOT_DIR=%~dp0"
echo Project Root: %ROOT_DIR%

set "LOG_DIR=%ROOT_DIR%system_logs"
set "BACKEND_LOG_DIR=%LOG_DIR%\backend"
set "FRONTEND_LOG_DIR=%LOG_DIR%\frontend"

if not exist "%LOG_DIR%" mkdir "%LOG_DIR%"
if not exist "%BACKEND_LOG_DIR%" mkdir "%BACKEND_LOG_DIR%"
if not exist "%FRONTEND_LOG_DIR%" mkdir "%FRONTEND_LOG_DIR%"

REM --- Backend Setup ---
echo --- Starting Backend Server ---
cd /d "%ROOT_DIR%"

echo Installing Python dependencies...
pip install -r requirements.txt

echo Starting Uvicorn server in the background...
REM Find and kill any existing server on port 8000
for /f "tokens=5" %%a in ('netstat -aon ^| findstr :8000') do (
    echo Killing existing process %%a on port 8000
    taskkill /F /PID %%a
)

start "Backend" /b uvicorn app.main:app --reload --port 8000 > "%BACKEND_LOG_DIR%\backend.log" 2>&1
echo Backend server started.
timeout /t 5 >nul

REM --- Frontend Setup ---
echo --- Starting Frontend Server ---
set "FRONTEND_DIR=%ROOT_DIR%frontend"
cd /d "%FRONTEND_DIR%"

echo Installing Node.js dependencies...
call npm install --legacy-peer-deps

echo Starting Next.js development server in the background...
REM Find and kill any existing server on port 3000
for /f "tokens=5" %%a in ('netstat -aon ^| findstr :3000') do (
    echo Killing existing process %%a on port 3000
    taskkill /F /PID %%a
)

start "Frontend" /b npm run dev > "%FRONTEND_LOG_DIR%\frontend.log" 2>&1
echo Frontend server started.

echo --- System is starting up! ---
echo Backend logs: %BACKEND_LOG_DIR%\backend.log
echo Frontend logs: %FRONTEND_LOG_DIR%\frontend.log
echo Backend available at http://localhost:8000
echo Frontend available at http://localhost:3000
echo.
echo To stop the servers, you will need to manually find and kill the 'uvicorn' and 'node' processes using Task Manager.
