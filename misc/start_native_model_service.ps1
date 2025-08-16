# Life Strands - Start Native Windows Model Service
# This script starts the model service natively on Windows for optimal GPU access

Write-Host "================================================================" -ForegroundColor Cyan
Write-Host "Life Strands - Native Windows Model Service Startup" -ForegroundColor Cyan  
Write-Host "================================================================" -ForegroundColor Cyan
Write-Host ""

# Check if virtual environment exists
if (-not (Test-Path "rocm_env\Scripts\Activate.ps1")) {
    Write-Host "❌ ROCm virtual environment not found!" -ForegroundColor Red
    Write-Host "   Run setup_windows_rocm.ps1 first to create the environment" -ForegroundColor Yellow
    Read-Host "Press Enter to exit"
    exit 1
}

Write-Host "🔄 Activating ROCm virtual environment..." -ForegroundColor Green
& "rocm_env\Scripts\Activate.ps1"

Write-Host "🔥 Setting ROCm environment variables for AMD 7900 XTX..." -ForegroundColor Yellow
$env:HIP_PLATFORM = "amd"
$env:HSA_OVERRIDE_GFX_VERSION = "11.0.0" 
$env:HIP_VISIBLE_DEVICES = "0"
$env:ROCR_VISIBLE_DEVICES = "0"

Write-Host "📁 Setting model service environment..." -ForegroundColor Blue
$env:MODELS_PATH = Join-Path $PWD "Models"
$env:REDIS_URL = "redis://localhost:6379"
$env:DATABASE_URL = "postgresql://lifestrands_user:lifestrands_password@localhost:5432/lifestrands"
$env:CHAT_MODEL = "Gryphe_Codex-24B-Small-3.2-Q6_K_L.gguf"
$env:SUMMARY_MODEL = "dphn.Dolphin-Mistral-24B-Venice-Edition.Q6_K.gguf"  
$env:EMBEDDING_MODEL = "all-MiniLM-L6-v2.F32.gguf"
$env:CHAT_CONTEXT_SIZE = "8192"
$env:SUMMARY_CONTEXT_SIZE = "4096"
$env:LOG_LEVEL = "INFO"

Write-Host ""
Write-Host "🌐 Model Service will be available at:" -ForegroundColor Magenta
Write-Host "   http://localhost:8001/status - Service status with GPU info" -ForegroundColor White
Write-Host "   http://localhost:8001/health - Health check" -ForegroundColor White
Write-Host "   http://localhost:8001/docs - API documentation" -ForegroundColor White
Write-Host "   http://localhost:8001/generate - Text generation" -ForegroundColor White
Write-Host "   http://localhost:8001/load-model - Load models" -ForegroundColor White
Write-Host "   http://localhost:8001/embeddings - Generate embeddings" -ForegroundColor White
Write-Host ""
Write-Host "🚀 Starting native model service with GPU acceleration..." -ForegroundColor Green
Write-Host "   Press Ctrl+C to stop the service" -ForegroundColor Yellow
Write-Host ""

try {
    python run_unified_model_service.py
}
catch {
    Write-Host "❌ Error starting model service: $_" -ForegroundColor Red
}
finally {
    Write-Host ""
    Write-Host "🛑 Model service stopped" -ForegroundColor Yellow
    Read-Host "Press Enter to exit"
}