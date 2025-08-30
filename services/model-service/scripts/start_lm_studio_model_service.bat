@echo off
echo ================================
echo Life Strands Model Service
echo LM Studio Backend Mode
echo ================================

REM Navigate to model service directory
cd /d "%~dp0\.."

REM Set LM Studio mode
set LM_STUDIO_MODE=true
set MOCK_MODE=false

REM Set LM Studio connection details
set LM_STUDIO_BASE_URL=http://localhost:1234

echo Starting Model Service with LM Studio backend...
echo LM Studio URL: %LM_STUDIO_BASE_URL%
echo.

REM Install required dependencies if needed
echo Checking dependencies...
pip install aiohttp > nul 2>&1

REM Start the service
echo Starting FastAPI server on port 8001...
python main.py

pause