@echo off
REM MB-Sparrow Windows Environment Test Script
setlocal enabledelayedexpansion

echo ========================================
echo   MB-Sparrow Environment Test
echo ========================================
echo.

set "PASS_COUNT=0"
set "FAIL_COUNT=0"

REM Test Python
echo [1/6] Testing Python installation...
python --version >nul 2>&1
if !errorlevel! equ 0 (
    python --version
    echo ✓ Python is installed and accessible
    set /a PASS_COUNT+=1
) else (
    echo ✗ Python not found - install from https://python.org
    set /a FAIL_COUNT+=1
)
echo.

REM Test Python version
echo [2/6] Testing Python version (3.10+ required)...
for /f "tokens=2" %%i in ('python --version 2^>^&1') do set "PYTHON_VERSION=%%i"
if defined PYTHON_VERSION (
    echo Python version: !PYTHON_VERSION!
    echo ✓ Python version check passed
    set /a PASS_COUNT+=1
) else (
    echo ✗ Could not determine Python version
    set /a FAIL_COUNT+=1
)
echo.

REM Test Node.js
echo [3/6] Testing Node.js installation...
node --version >nul 2>&1
if !errorlevel! equ 0 (
    node --version
    npm --version
    echo ✓ Node.js and npm are installed and accessible
    set /a PASS_COUNT+=1
) else (
    echo ✗ Node.js not found - install from https://nodejs.org
    set /a FAIL_COUNT+=1
)
echo.

REM Test Redis
echo [4/6] Testing Redis connection...
redis-cli ping >nul 2>&1
if !errorlevel! equ 0 (
    echo Redis response: PONG
    echo ✓ Redis is running and accessible
    set /a PASS_COUNT+=1
) else (
    echo ⚠ Redis not found/running - FeedMe background processing will be disabled
    echo   Install from: https://github.com/tporadowski/redis/releases
    echo   Or use Docker: docker run --name redis -p 6379:6379 -d redis
    set /a FAIL_COUNT+=1
)
echo.

REM Test Git
echo [5/6] Testing Git installation...
git --version >nul 2>&1
if !errorlevel! equ 0 (
    git --version
    echo ✓ Git is installed and accessible
    set /a PASS_COUNT+=1
) else (
    echo ✗ Git not found - install from https://git-scm.com
    set /a FAIL_COUNT+=1
)
echo.

REM Test ports availability
echo [6/6] Testing port availability...
netstat -aon | findstr ":8000" | findstr "LISTENING" >nul
if !errorlevel! neq 0 (
    echo ✓ Port 8000 available for backend
    set "PORT_8000=OK"
) else (
    echo ⚠ Port 8000 is in use - will be cleared during startup
    set "PORT_8000=IN_USE"
)

netstat -aon | findstr ":3000" | findstr "LISTENING" >nul
if !errorlevel! neq 0 (
    echo ✓ Port 3000 available for frontend
    set "PORT_3000=OK"
) else (
    echo ⚠ Port 3000 is in use - will be cleared during startup
    set "PORT_3000=IN_USE"
)

if "!PORT_8000!" == "OK" if "!PORT_3000!" == "OK" (
    set /a PASS_COUNT+=1
) else (
    set /a FAIL_COUNT+=1
)
echo.

REM Summary
echo ========================================
echo           Test Summary
echo ========================================
echo Tests passed: !PASS_COUNT!/6
echo Tests failed: !FAIL_COUNT!/6
echo.

if !FAIL_COUNT! equ 0 (
    echo 🎉 Environment ready! You can run start_system.bat
    echo.
    echo Next steps:
    echo 1. Ensure you have a .env file with your GEMINI_API_KEY
    echo 2. Run start_system.bat to start all services
    echo 3. Access the application at http://localhost:3000
) else (
    echo ⚠ Some issues detected. Please fix the failing tests above.
    echo.
    if !FAIL_COUNT! lss 3 (
        echo 💡 You can still run the system, but some features may not work.
        echo   Redis is optional - system will work without background processing.
    ) else (
        echo ❌ Critical issues detected. Please install missing dependencies.
    )
)

echo.
echo For detailed setup instructions, see: WINDOWS_SETUP.md
echo For troubleshooting help, check the logs after running start_system.bat
pause