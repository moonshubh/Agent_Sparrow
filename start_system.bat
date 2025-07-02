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

REM Create and activate Python virtual environment
if not exist "venv" (
    echo Creating Python virtual environment...
    python -m venv venv
    if %errorlevel% neq 0 (
        echo Failed to create virtual environment. Exiting.
        exit /b 1
    )
)

echo Activating virtual environment...
call venv\Scripts\activate

echo Installing Python dependencies...
pip install -r requirements.txt
if %errorlevel% neq 0 (
    echo Failed to install Python dependencies. Exiting.
    exit /b 1
)

echo Killing existing process on port 8000...
set "PID_8000="
for /f "tokens=5" %%a in ('netstat -aon ^| findstr ":8000"') do (
    set PID_8000=%%a
)

if defined PID_8000 (
    echo Killing process %PID_8000% on port 8000...
    taskkill /F /PID %PID_8000%
    if %errorlevel% neq 0 (
        echo Failed to kill process %PID_8000%. It may require manual intervention.
    ) else (
        echo Process %PID_8000% killed successfully.
    )
) else (
    echo No process found on port 8000.
)

echo Starting Uvicorn server in the background...
start "Backend" /b uvicorn app.main:app --reload --port 8000 > "%BACKEND_LOG_DIR%\backend.log" 2>&1

echo Verifying backend server startup...
timeout /t 5 >nul
netstat -aon | findstr ":8000" | findstr "LISTENING" >nul
if %errorlevel% neq 0 (
    echo Backend server failed to start. Check logs at %BACKEND_LOG_DIR%\backend.log
    exit /b 1
) else (
    echo Backend server started successfully.
)

REM --- Frontend Setup ---
echo --- Starting Frontend Server ---
set "FRONTEND_DIR=%ROOT_DIR%frontend"
cd /d "%FRONTEND_DIR%"

echo Installing Node.js dependencies...
call npm install --legacy-peer-deps
if %errorlevel% neq 0 (
    echo Failed to install Node.js dependencies. Exiting.
    exit /b 1
)

echo Killing existing process on port 3000...
set "PID_3000="
for /f "tokens=5" %%a in ('netstat -aon ^| findstr ":3000"') do (
    set PID_3000=%%a
)

if defined PID_3000 (
    echo Killing process %PID_3000% on port 3000...
    taskkill /F /PID %PID_3000%
    if %errorlevel% neq 0 (
        echo Failed to kill process %PID_3000%. It may require manual intervention.
    ) else (
        echo Process %PID_3000% killed successfully.
    )
) else (
    echo No process found on port 3000.
)

echo Starting Next.js development server in the background...
start "Frontend" /b npm run dev > "%FRONTEND_LOG_DIR%\frontend.log" 2>&1

echo Verifying frontend server startup...
timeout /t 10 >nul
netstat -aon | findstr ":3000" | findstr "LISTENING" >nul
if %errorlevel% neq 0 (
    echo Frontend server failed to start. Check logs at %FRONTEND_LOG_DIR%\frontend.log
    exit /b 1
) else (
    echo Frontend server started successfully.
)

echo --- System is starting up! ---
echo Backend logs: %BACKEND_LOG_DIR%\backend.log
echo Frontend logs: %FRONTEND_LOG_DIR%\frontend.log
echo Backend available at http://localhost:8000
echo Frontend available at http://localhost:3000
echo.
echo To stop the servers, you will need to manually find and kill the 'uvicorn' and 'node' processes using Task Manager.
