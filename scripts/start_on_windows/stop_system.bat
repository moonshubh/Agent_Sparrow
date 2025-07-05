@echo off
REM Enhanced Windows batch script to stop all MB-Sparrow system services
setlocal enabledelayedexpansion

echo ========================================
echo    Stopping MB-Sparrow System
echo ========================================
echo.

REM Function to kill services gracefully
call :kill_service "Backend (FastAPI)" "8000" "uvicorn.*app.main:app"
call :kill_service "Frontend (Next.js)" "3000" "npm.*run.*dev"
call :kill_service "FeedMe Celery Worker" "" "celery.*worker"

echo.
echo ========================================
echo    All services stopped
echo ========================================
echo.
echo To restart the system, run: start_system.bat
pause
goto :eof

REM --- Functions ---

:kill_service
set "SERVICE_NAME=%~1"
set "PORT=%~2"
set "PATTERN=%~3"

echo Stopping %SERVICE_NAME%...

REM Try to kill by port if specified
if not "%PORT%" == "" (
    set "PID="
    for /f "tokens=5" %%a in ('netstat -aon ^| findstr ":%PORT%" ^| findstr "LISTENING"') do (
        set "PID=%%a"
    )
    
    if defined PID (
        echo   Killing %SERVICE_NAME% process !PID! on port %PORT%...
        taskkill /F /PID !PID! >nul 2>&1
        if !errorlevel! neq 0 (
            echo   Warning: Failed to kill process !PID!.
        ) else (
            echo   ✓ Process !PID! killed successfully.
        )
        timeout /t 2 /nobreak >nul
    )
)

REM Try to kill by process pattern
if not "%PATTERN%" == "" (
    if "%PATTERN%" == "uvicorn.*app.main:app" (
        REM Kill uvicorn processes
        tasklist /FI "IMAGENAME eq python.exe" /FO CSV | findstr "uvicorn" >nul 2>&1
        if !errorlevel! equ 0 (
            echo   Killing uvicorn processes...
            taskkill /F /IM python.exe /FI "WINDOWTITLE eq *uvicorn*" >nul 2>&1
            taskkill /F /IM python.exe /FI "COMMANDLINE eq *uvicorn*" >nul 2>&1
        )
    )
    
    if "%PATTERN%" == "npm.*run.*dev" (
        REM Kill npm and node processes
        tasklist /FI "IMAGENAME eq node.exe" /FO CSV | findstr "node" >nul 2>&1
        if !errorlevel! equ 0 (
            echo   Killing Node.js processes...
            taskkill /F /IM node.exe >nul 2>&1
            taskkill /F /IM npm.cmd >nul 2>&1
        )
    )
    
    if "%PATTERN%" == "celery.*worker" (
        REM Kill celery worker processes
        tasklist /FI "IMAGENAME eq python.exe" /FO CSV | findstr "celery" >nul 2>&1
        if !errorlevel! equ 0 (
            echo   Killing Celery worker processes...
            taskkill /F /IM python.exe /FI "WINDOWTITLE eq *celery*" >nul 2>&1
        )
    )
)

echo   %SERVICE_NAME% stopped.
goto :eof