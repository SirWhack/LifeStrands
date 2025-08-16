@echo off
REM Life Strands - Start Native Windows Model Service
REM This script starts the model service natively on Windows for optimal GPU access

echo ================================================================
echo Life Strands - Native Windows Model Service Startup
echo ================================================================
echo.

REM Check if virtual environment exists
if not exist "rocm_env\Scripts\activate.bat" (
    echo ❌ ROCm virtual environment not found!
    echo    Run setup_windows_rocm.ps1 first to create the environment
    pause
    exit /b 1
)

echo 🔄 Activating ROCm virtual environment...
call rocm_env\Scripts\activate.bat

echo 🔥 Setting ROCm environment variables for AMD 7900 XTX...
set HIP_PLATFORM=amd
set HSA_OVERRIDE_GFX_VERSION=11.0.0
set HIP_VISIBLE_DEVICES=0
set ROCR_VISIBLE_DEVICES=0

echo 📁 Setting model service environment...
set MODELS_PATH=%CD%\Models
set REDIS_URL=redis://localhost:6379
set DATABASE_URL=postgresql://lifestrands_user:lifestrands_password@localhost:5432/lifestrands
set CHAT_MODEL=Gryphe_Codex-24B-Small-3.2-Q6_K_L.gguf
set SUMMARY_MODEL=dphn.Dolphin-Mistral-24B-Venice-Edition.Q6_K.gguf
set EMBEDDING_MODEL=all-MiniLM-L6-v2.F32.gguf
set CHAT_CONTEXT_SIZE=8192
set SUMMARY_CONTEXT_SIZE=4096
set LOG_LEVEL=INFO

echo.
echo 🌐 Model Service will be available at:
echo    http://localhost:8001/status - Service status with GPU info
echo    http://localhost:8001/health - Health check  
echo    http://localhost:8001/docs - API documentation
echo    http://localhost:8001/generate - Text generation
echo    http://localhost:8001/load-model - Load models
echo    http://localhost:8001/embeddings - Generate embeddings
echo.
echo 🚀 Starting native model service with GPU acceleration...
echo    Press Ctrl+C to stop the service
echo.

python run_unified_model_service.py

echo.
echo 🛑 Model service stopped
pause