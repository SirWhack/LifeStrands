@echo off
REM Life Strands - Start Model Service in New Window
REM This script launches the native Windows model service in a separate terminal

setlocal enabledelayedexpansion

echo ================================================
echo     Life Strands - Starting Model Service     
echo     Native Windows Vulkan GPU Acceleration    
echo ================================================
echo.

REM Get the root directory (parent of scripts folder)
set "ROOT_DIR=%~dp0.."
set "SERVICE_DIR=%ROOT_DIR%\services\model-service"

echo Root Directory: %ROOT_DIR%
echo Service Directory: %SERVICE_DIR%
echo.

REM Check if service directory exists
if not exist "%SERVICE_DIR%" (
    echo ERROR: Model service directory not found: %SERVICE_DIR%
    echo Please ensure you're running this from the correct location.
    pause
    exit /b 1
)

echo Starting model service in new terminal window...

REM Start the model service in a new Command Prompt window
start "Life Strands - Model Service (Vulkan GPU)" /D "%SERVICE_DIR%" cmd /k "echo ================================================= & echo     Life Strands - Native Model Service         & echo     AMD 7900 XTX Vulkan GPU Acceleration        & echo ================================================= & echo. & echo Working Directory: %CD% & echo Starting native Windows model service... & echo. & python main.py"

if %ERRORLEVEL% neq 0 (
    echo ERROR: Failed to start model service window
    echo Please try starting manually:
    echo   cd services\model-service
    echo   python main.py
    pause
    exit /b 1
)

echo.
echo Model service terminal launched successfully!
echo.
echo Waiting for service to initialize...
timeout /t 3 /nobreak >nul

REM Check if service is responding
echo Checking service health...
for /l %%i in (1,1,15) do (
    curl -s http://localhost:8001/health >nul 2>&1
    if !ERRORLEVEL! equ 0 (
        echo SUCCESS: Model service is ready and responding!
        echo.
        echo The model service is now running in a separate window.
        echo You can control it from there.
        goto :success
    )
    echo|set /p="."
    timeout /t 2 /nobreak >nul
)

echo.
echo WARNING: Service may still be starting. Check the model service window for details.
echo.

:success
echo Model service window is running. You can monitor and control it from there.
echo.
exit /b 0