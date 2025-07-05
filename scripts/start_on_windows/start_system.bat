@echo off
REM Enhanced Windows batch script for MB-Sparrow system with FeedMe v2.0 support
REM Based on MacOS troubleshooting fixes for smooth Windows deployment

REM Exit on any error (best effort for batch)
setlocal enabledelayedexpansion

REM --- Project Root and Log Setup ---
REM Navigate up two directory levels from scripts/start_on_windows/ to project root
set "ROOT_DIR=%~dp0..\..\\"
echo Project Root: !ROOT_DIR!

set "LOG_DIR=!ROOT_DIR!system_logs"
set "BACKEND_LOG_DIR=!LOG_DIR!\backend"
set "FRONTEND_LOG_DIR=!LOG_DIR!\frontend"
set "CELERY_LOG_DIR=!LOG_DIR!\celery"

if not exist "!LOG_DIR!" mkdir "!LOG_DIR!"
if not exist "!BACKEND_LOG_DIR!" mkdir "!BACKEND_LOG_DIR!"
if not exist "!FRONTEND_LOG_DIR!" mkdir "!FRONTEND_LOG_DIR!"
if not exist "!CELERY_LOG_DIR!" mkdir "!CELERY_LOG_DIR!"

REM --- Backend Setup ---
echo.
echo --- Starting Backend Server ---
cd /d "!ROOT_DIR!"

REM Create and activate Python virtual environment
if not exist "venv" (
    echo Creating Python virtual environment...
    python -m venv venv
    if !errorlevel! neq 0 (
        echo Error: Failed to create virtual environment. Please ensure Python 3.10+ is installed.
        echo Try: python --version
        pause
        exit /b 1
    )
)

echo Activating virtual environment...
call venv\Scripts\activate
if !errorlevel! neq 0 (
    echo Error: Failed to activate virtual environment.
    pause
    exit /b 1
)

echo Installing Python dependencies...
REM Capture stderr to filter google-generativeai warnings while showing critical errors
set "TEMP_ERROR_FILE=%TEMP%\pip_errors_%RANDOM%.txt"
pip install -r requirements.txt 2>"%TEMP_ERROR_FILE%" || (
    REM Check if error file contains only expected google-generativeai warnings
    findstr /I "google-generativeai" "%TEMP_ERROR_FILE%" >nul
    if !errorlevel! equ 0 (
        echo Note: Some dependency warnings are expected due to google-generativeai compatibility
        echo Continuing with installation...
    ) else (
        echo Critical pip install errors detected:
        type "%TEMP_ERROR_FILE%"
        echo Please resolve these errors before continuing.
        del "%TEMP_ERROR_FILE%" 2>nul
        pause
        exit /b 1
    )
)
del "%TEMP_ERROR_FILE%" 2>nul

REM Verify critical dependencies are installed
echo Verifying critical dependencies...
python -c "import google.generativeai as genai; print('✓ google.generativeai imported successfully')" 2>nul || (
    echo Installing missing google-generativeai dependency...
    pip install google-generativeai
    if !errorlevel! neq 0 (
        echo Error: Failed to install google-generativeai. FeedMe processing will not work.
        pause
        exit /b 1
    )
)

python -c "from app.feedme.ai_extraction_engine import GemmaExtractionEngine; print('✓ FeedMe AI engine imports successfully')" 2>nul || (
    echo Warning: FeedMe AI extraction engine failed to import. Check dependencies.
)

REM Function to kill processes on port (Windows approach)
call :kill_process_on_port 8000 "Backend"

echo Starting Uvicorn server in the background...
start "MB-Sparrow-Backend" /min cmd /c "call venv\Scripts\activate && uvicorn app.main:app --reload --port 8000 >> "!BACKEND_LOG_DIR!\backend.log" 2>&1"

echo Verifying backend server startup...
timeout /t 5 /nobreak >nul
call :verify_port_listening 8000 "Backend server"
if !errorlevel! neq 0 (
    echo Backend server failed to start. Check logs at !BACKEND_LOG_DIR!\backend.log
    pause
    exit /b 1
)
echo ✓ Backend server started successfully.

REM --- FeedMe Celery Worker Setup ---
echo.
echo --- Starting FeedMe Celery Worker ---
cd /d "!ROOT_DIR!"

REM Check if Redis is running (required for Celery)
echo Checking if Redis is running...
redis-cli ping >nul 2>&1
if !errorlevel! neq 0 (
    echo.
    echo Warning: Redis is not running. FeedMe Celery worker requires Redis.
    echo Please install and start Redis:
    echo   1. Download Redis from: https://github.com/tporadowski/redis/releases
    echo   2. Install and start the Redis service
    echo   3. Or use Docker: docker run --name redis -p 6379:6379 -d redis
    echo.
    echo Continuing without Celery worker...
    set "CELERY_STARTED=false"
) else (
    echo ✓ Redis is running, starting FeedMe Celery worker...
    
    REM Kill any existing Celery workers
    echo Checking for existing Celery workers...
    tasklist /FI "IMAGENAME eq python.exe" /FO CSV | findstr "celery" >nul 2>&1
    if !errorlevel! equ 0 (
        echo Killing existing Celery workers...
        taskkill /F /IM python.exe /FI "WINDOWTITLE eq *celery*" >nul 2>&1
        timeout /t 2 /nobreak >nul
    )
    
    REM Start FeedMe Celery worker
    echo Starting FeedMe Celery worker in the background...
    start "MB-Sparrow-FeedMe-Worker" /min cmd /c "call venv\Scripts\activate && python -m celery -A app.feedme.celery_app worker --loglevel=info --concurrency=2 --queues=feedme_default,feedme_processing,feedme_embeddings,feedme_parsing,feedme_health >> "!CELERY_LOG_DIR!\celery_worker.log" 2>&1"
    
    REM Verify Celery worker startup
    echo Verifying Celery worker startup...
    timeout /t 3 /nobreak >nul
    tasklist /FI "IMAGENAME eq python.exe" /FO CSV | findstr "celery" >nul 2>&1
    if !errorlevel! neq 0 (
        echo Warning: Celery worker may have failed to start. Check logs at !CELERY_LOG_DIR!\celery_worker.log
        echo FeedMe background processing will not be available.
        set "CELERY_STARTED=false"
    ) else (
        echo ✓ FeedMe Celery worker started successfully.
        set "CELERY_STARTED=true"
    )
)

REM --- Frontend Setup ---
echo.
echo --- Starting Frontend Server ---
set "FRONTEND_DIR=!ROOT_DIR!frontend"
cd /d "!FRONTEND_DIR!"

REM Check if Node.js is available
node --version >nul 2>&1
if !errorlevel! neq 0 (
    echo Error: Node.js is not installed or not in PATH.
    echo Please install Node.js 18+ from: https://nodejs.org/
    pause
    exit /b 1
)

echo Installing Node.js dependencies...
call npm install --legacy-peer-deps
if !errorlevel! neq 0 (
    echo Error: Failed to install Node.js dependencies.
    echo Try running: npm cache clean --force
    pause
    exit /b 1
)

call :kill_process_on_port 3000 "Frontend"

echo Starting Next.js development server in the background...
start "MB-Sparrow-Frontend" /min cmd /c "npm run dev >> "!FRONTEND_LOG_DIR!\frontend.log" 2>&1"

echo Verifying frontend server startup...
timeout /t 10 /nobreak >nul
call :verify_port_listening 3000 "Frontend server"
if !errorlevel! neq 0 (
    echo Frontend server failed to start. Check logs at !FRONTEND_LOG_DIR!\frontend.log
    pause
    exit /b 1
)
echo ✓ Frontend server started successfully.

REM --- System Startup Complete ---
echo.
echo ========================================
echo     MB-Sparrow System Started!
echo ========================================
echo.
echo Services available:
echo   • Backend API: http://localhost:8000
echo   • Frontend UI: http://localhost:3000
echo   • FeedMe v2.0: http://localhost:3000/feedme
if "!CELERY_STARTED!" == "true" (
    echo   • FeedMe Processing: ✓ Active ^(Gemma 3 27b AI extraction^)
) else (
    echo   • FeedMe Processing: ✗ Inactive ^(background processing disabled^)
)
echo.
echo Logs location:
echo   • Backend: !BACKEND_LOG_DIR!\backend.log
echo   • Frontend: !FRONTEND_LOG_DIR!\frontend.log
if "!CELERY_STARTED!" == "true" (
    echo   • Celery Worker: !CELERY_LOG_DIR!\celery_worker.log
)
echo.
echo To stop all services, run: stop_system.bat
echo To view logs in real-time, use: Get-Content -Wait ^<log_file^> in PowerShell
echo.
echo System ready for use!
pause
goto :eof

REM --- Functions ---

:kill_process_on_port
set "PORT=%~1"
set "SERVICE_NAME=%~2"
echo Checking for existing processes on port !PORT!...

set "PID="
for /f "tokens=5" %%a in ('netstat -aon ^| findstr ":!PORT!" ^| findstr "LISTENING"') do (
    set "PID=%%a"
)

if defined PID (
    echo Killing !SERVICE_NAME! process !PID! on port !PORT!...
    taskkill /F /PID !PID! >nul 2>&1
    if !errorlevel! neq 0 (
        echo Warning: Failed to kill process !PID!. Manual intervention may be required.
    ) else (
        echo ✓ Process !PID! killed successfully.
    )
    timeout /t 2 /nobreak >nul
) else (
    echo No process found on port !PORT!.
)
goto :eof

:verify_port_listening
set "PORT=%~1"
set "SERVICE_NAME=%~2"
netstat -aon | findstr ":!PORT!" | findstr "LISTENING" >nul
if !errorlevel! neq 0 (
    echo !SERVICE_NAME! started but is not listening on port !PORT!. Check logs.
    exit /b 1
)
goto :eof