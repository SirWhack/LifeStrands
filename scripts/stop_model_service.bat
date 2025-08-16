@echo off
REM Life Strands - Stop Model Service
REM This script stops the native Windows model service

setlocal enabledelayedexpansion

echo ================================================
echo     Stopping Life Strands Model Service       
echo ================================================
echo.

REM First try graceful shutdown via API
echo Attempting graceful shutdown...
curl -s -X POST http://localhost:8001/shutdown >nul 2>&1
if %ERRORLEVEL% equ 0 (
    echo SUCCESS: Model service shutdown successfully via API
    timeout /t 2 /nobreak >nul
    goto :end
)

echo API shutdown failed, proceeding with process termination...
echo.

REM Find and kill process on port 8001
echo Finding model service process on port 8001...

for /f "tokens=5" %%i in ('netstat -ano ^| findstr ":8001.*LISTENING"') do (
    set "PID=%%i"
    echo Found model service process: PID !PID!
    
    REM Try graceful termination first
    echo Attempting graceful termination...
    taskkill /PID !PID! >nul 2>&1
    
    timeout /t 3 /nobreak >nul
    
    REM Check if still running, force kill if necessary
    tasklist /FI "PID eq !PID!" 2>nul | find "!PID!" >nul
    if !ERRORLEVEL! equ 0 (
        echo Forcing process termination...
        taskkill /F /PID !PID! >nul 2>&1
    )
    
    echo SUCCESS: Model service stopped successfully
    goto :cleanup
)

echo WARNING: No process found listening on port 8001

:cleanup
echo.
echo Checking for any remaining model service processes...

REM Kill any remaining Python processes running model service
for /f "tokens=2" %%i in ('tasklist /FI "IMAGENAME eq python.exe" /FO CSV ^| findstr "python.exe"') do (
    set "PID=%%~i"
    wmic process where "ProcessId=!PID!" get CommandLine /value 2>nul | findstr "model-service.*main.py" >nul
    if !ERRORLEVEL! equ 0 (
        echo Found model service Python process: PID !PID!
        taskkill /F /PID !PID! >nul 2>&1
        if !ERRORLEVEL! equ 0 (
            echo SUCCESS: Terminated Python process: PID !PID!
        ) else (
            echo ERROR: Failed to terminate process: PID !PID!
        )
    )
)

:end
echo.
echo Model service shutdown complete.
echo.
exit /b 0