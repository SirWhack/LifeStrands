@echo off
echo ====================================
echo Starting Mock Model Service
echo ====================================

cd /d "%~dp0\.."

REM Set mock mode environment variable
set MOCK_MODE=true
set ENABLE_GPU=false

echo Mock mode enabled - no GPU resources required
echo Starting lightweight model service with canned responses...
echo.

REM Start the mock service
python main_mock.py

echo.
echo Mock Model Service stopped
pause