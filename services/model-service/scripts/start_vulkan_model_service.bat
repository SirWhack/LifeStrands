@echo off
REM Life Strands - Start Native Windows Model Service with Vulkan
REM This script starts the model service natively on Windows with Vulkan GPU acceleration

echo ================================================================
echo Life Strands - Native Windows Model Service (Vulkan)
echo ================================================================
echo.

REM Navigate to project root (two levels up from scripts folder)
cd ..\..\..

REM Check if virtual environment exists
if not exist "rocm_env\Scripts\activate.bat" (
    echo ❌ Virtual environment not found!
    echo    Create environment and rebuild llama-cpp-python with Vulkan:
    echo    ./rebuild_with_vulkan.ps1
    pause
    exit /b 1
)

echo 🔄 Activating virtual environment...
call rocm_env\Scripts\activate.bat

echo 🔥 Setting Vulkan environment variables...
REM Vulkan-specific environment (no ROCm variables needed)
REM Let Vulkan auto-detect devices

echo 📁 Setting model service environment...
set MODELS_PATH=%CD%\Models
set REDIS_URL=redis://localhost:6379
set DATABASE_URL=postgresql://lifestrands_user:lifestrands_password@localhost:5432/lifestrands
set CHAT_MODEL=Gryphe_Codex-24B-Small-3.2-Q6_K_L.gguf
set SUMMARY_MODEL=dphn.Dolphin-Mistral-24B-Venice-Edition.Q6_K.gguf
set EMBEDDING_MODEL=all-MiniLM-L6-v2.F32.gguf
set CHAT_CONTEXT_SIZE=8192
set SUMMARY_CONTEXT_SIZE=4096
set LOG_LEVEL=DEBUG

echo 🔍 Checking Vulkan setup...
vulkaninfo --summary >nul 2>&1
if %errorlevel% equ 0 (
    echo ✅ Vulkan runtime detected
) else (
    echo ⚠️  Vulkan runtime check failed - continuing anyway
)

echo.
echo 🌐 Model Service will be available at:
echo    http://localhost:8001/status - Service status with GPU info
echo    http://localhost:8001/health - Health check  
echo    http://localhost:8001/docs - API documentation
echo    http://localhost:8001/generate - Text generation
echo    http://localhost:8001/load-model - Load models
echo    http://localhost:8001/embeddings - Generate embeddings
echo.
echo 🚀 Starting model service with Vulkan GPU acceleration...
echo    Press Ctrl+C to stop the service
echo.

cd services\model-service
python main.py

echo.
echo 🛑 Model service stopped
pause