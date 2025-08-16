@echo off
REM Life Strands Development Commands - Windows Native
REM Run this from PowerShell or Command Prompt for easy Windows development

setlocal enabledelayedexpansion

if "%1"=="" goto help
if "%1"=="help" goto help
if "%1"=="dev-up" goto dev-up
if "%1"=="dev-down" goto dev-down
if "%1"=="model-start" goto model-start
if "%1"=="model-stop" goto model-stop
if "%1"=="logs" goto logs
if "%1"=="status" goto status
if "%1"=="health" goto health
goto help

:help
echo ================================================
echo     Life Strands Development Commands        
echo     Windows Native Edition                    
echo ================================================
echo.
echo Available commands:
echo   dev.bat dev-up       Start all services (Docker + Native Model)
echo   dev.bat dev-down     Stop all services
echo   dev.bat model-start  Start only model service in new window
echo   dev.bat model-stop   Stop only model service
echo   dev.bat logs         Show Docker service logs
echo   dev.bat status       Show system status
echo   dev.bat health       Check all service health
echo.
echo Examples:
echo   dev.bat dev-up       # Start everything
echo   dev.bat dev-down     # Stop everything
echo   dev.bat status       # Check what's running
echo.
goto end

:dev-up
echo ================================================
echo     Starting Life Strands System             
echo     Windows Native + Docker Services          
echo ================================================
echo.

echo Step 1: Starting native Windows model service...
call :model-start-internal

echo.
echo Step 2: Starting Docker services...
docker-compose -f docker-compose.native-model.yml up -d

if %ERRORLEVEL% neq 0 (
    echo ERROR: Failed to start Docker services
    echo Make sure Docker is running and try again
    goto end
)

echo.
echo Step 3: Waiting for services to be ready...
timeout /t 5 /nobreak >nul

echo.
echo ================================================
echo     Life Strands System Started Successfully  
echo ================================================
echo.
echo Available services:
echo   Gateway API:       http://localhost:8000
echo   Model Service:     http://localhost:8001 (Native Vulkan)
echo   Chat Service:      http://localhost:8002
echo   NPC Service:       http://localhost:8003
echo   Summary Service:   http://localhost:8004
echo   Monitor Service:   http://localhost:8005
echo.
echo   Chat Interface:    http://localhost:3001
echo   Admin Dashboard:   http://localhost:3002
echo.
echo Use 'dev.bat logs' to monitor startup logs
echo Use 'dev.bat status' to check service health
echo.
goto end

:dev-down
echo ================================================
echo     Stopping Life Strands System             
echo ================================================
echo.

echo Step 1: Stopping native model service...
call :model-stop-internal

echo.
echo Step 2: Stopping Docker services...
docker-compose -f docker-compose.native-model.yml down

echo.
echo ✅ All services stopped successfully
echo.
goto end

:model-start
call :model-start-internal
goto end

:model-start-internal
echo Starting native Windows model service in new terminal...

REM Check if service directory exists
if not exist "services\model-service\main.py" (
    echo ERROR: Model service not found at services\model-service\main.py
    echo Make sure you're running this from the Life Strands root directory
    exit /b 1
)

REM Start the model service in a new window with virtual environment
start "Life Strands - Model Service (Vulkan GPU)" cmd /k "cd /d \"%~dp0\" & echo ================================================= & echo     Life Strands - Native Model Service         & echo     AMD 7900 XTX Vulkan GPU Acceleration        & echo ================================================= & echo. & echo Working Directory: %CD% & echo Activating Python virtual environment... & call rocm_env\Scripts\activate.bat & echo Virtual environment activated & echo Starting native Windows model service... & echo. & cd services\model-service & python main.py"

if %ERRORLEVEL% neq 0 (
    echo ERROR: Failed to start model service
    echo Make sure Python is installed and accessible
    exit /b 1
)

echo ✅ Model service terminal launched successfully!
echo.
echo Waiting for service to initialize...
timeout /t 3 /nobreak >nul

REM Check if service is responding
echo Checking service health...
for /l %%i in (1,1,15) do (
    curl -s http://localhost:8001/health >nul 2>&1
    if !ERRORLEVEL! equ 0 (
        echo ✅ Model service is ready and responding!
        goto model-start-success
    )
    echo|set /p="."
    timeout /t 2 /nobreak >nul
)

echo.
echo ⚠️  Service may still be starting. Check the model service window for details.

:model-start-success
echo.
echo Model service is running in a separate window.
exit /b 0

:model-stop
call :model-stop-internal
goto end

:model-stop-internal
echo Stopping native Windows model service...

REM Try graceful shutdown first
curl -s -X POST http://localhost:8001/shutdown >nul 2>&1
if %ERRORLEVEL% equ 0 (
    echo ✅ Model service shutdown successfully via API
    timeout /t 2 /nobreak >nul
    exit /b 0
)

echo API shutdown failed, proceeding with process termination...

REM Find and kill process on port 8001
for /f "tokens=5" %%i in ('netstat -ano ^| findstr ":8001.*LISTENING"') do (
    set "PID=%%i"
    echo Found model service process: PID !PID!
    
    REM Try graceful termination first
    taskkill /PID !PID! >nul 2>&1
    timeout /t 3 /nobreak >nul
    
    REM Check if still running, force kill if necessary
    tasklist /FI "PID eq !PID!" 2>nul | find "!PID!" >nul
    if !ERRORLEVEL! equ 0 (
        echo Forcing process termination...
        taskkill /F /PID !PID! >nul 2>&1
    )
    
    echo ✅ Model service stopped successfully
    exit /b 0
)

echo ⚠️  No process found listening on port 8001
exit /b 0

:logs
echo ================================================
echo     Life Strands Docker Service Logs         
echo ================================================
echo.
docker-compose -f docker-compose.native-model.yml logs -f
goto end

:status
echo ================================================
echo     Life Strands System Status                
echo ================================================
echo.

echo Docker Services:
docker-compose -f docker-compose.native-model.yml ps
echo.

echo Native Model Service:
curl -s http://localhost:8001/health >nul 2>&1
if %ERRORLEVEL% equ 0 (
    echo ✅ Model service: Running (http://localhost:8001)
) else (
    echo ❌ Model service: Not running
)

echo.
echo Service Health Check:
curl -s http://localhost:8000/health >nul 2>&1 && echo ✅ Gateway: Healthy || echo ❌ Gateway: Unhealthy
curl -s http://localhost:8001/health >nul 2>&1 && echo ✅ Model: Healthy || echo ❌ Model: Unhealthy
curl -s http://localhost:8002/health >nul 2>&1 && echo ✅ Chat: Healthy || echo ❌ Chat: Unhealthy
curl -s http://localhost:8003/health >nul 2>&1 && echo ✅ NPC: Healthy || echo ❌ NPC: Unhealthy
curl -s http://localhost:8004/health >nul 2>&1 && echo ✅ Summary: Healthy || echo ❌ Summary: Unhealthy
curl -s http://localhost:8005/health >nul 2>&1 && echo ✅ Monitor: Healthy || echo ❌ Monitor: Unhealthy

goto end

:health
echo ================================================
echo     Life Strands Health Check                 
echo ================================================
echo.

echo Checking all services...
echo.

set /a healthy=0
set /a total=6

curl -s http://localhost:8000/health >nul 2>&1 && (echo ✅ Gateway Service: Healthy & set /a healthy+=1) || echo ❌ Gateway Service: Unhealthy
curl -s http://localhost:8001/health >nul 2>&1 && (echo ✅ Model Service: Healthy & set /a healthy+=1) || echo ❌ Model Service: Unhealthy  
curl -s http://localhost:8002/health >nul 2>&1 && (echo ✅ Chat Service: Healthy & set /a healthy+=1) || echo ❌ Chat Service: Unhealthy
curl -s http://localhost:8003/health >nul 2>&1 && (echo ✅ NPC Service: Healthy & set /a healthy+=1) || echo ❌ NPC Service: Unhealthy
curl -s http://localhost:8004/health >nul 2>&1 && (echo ✅ Summary Service: Healthy & set /a healthy+=1) || echo ❌ Summary Service: Unhealthy
curl -s http://localhost:8005/health >nul 2>&1 && (echo ✅ Monitor Service: Healthy & set /a healthy+=1) || echo ❌ Monitor Service: Unhealthy

echo.
echo System Health: !healthy!/!total! services healthy

if !healthy! equ !total! (
    echo ✅ All services are running perfectly!
) else (
    echo ⚠️  Some services need attention
)

goto end

:end
echo.