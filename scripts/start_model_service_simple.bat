@echo off
REM Simple Windows batch file to start the model service
REM This is called from WSL to avoid complex escaping issues

echo ================================================
echo     Life Strands - Native Model Service        
echo     AMD 7900 XTX Vulkan GPU Acceleration       
echo ================================================
echo.

echo Working Directory: %CD%
echo Activating Python virtual environment...

REM Go back to root directory to activate environment
cd ..\..
call rocm_env\Scripts\activate.bat

if %ERRORLEVEL% neq 0 (
    echo ERROR: Failed to activate virtual environment
    echo Make sure rocm_env exists and is properly set up
    pause
    exit /b 1
)

echo Virtual environment activated
echo Starting native Windows model service...
echo.

REM Go back to model service directory
cd services\model-service
python main.py

echo.
echo Model service stopped. Press any key to close...
pause >nul