# Life Strands - Start Native Windows Model Service with Vulkan
# This script starts the model service natively on Windows with Vulkan GPU acceleration

Write-Host "================================================================" -ForegroundColor Cyan
Write-Host "Life Strands - Native Windows Model Service (Vulkan)" -ForegroundColor Cyan  
Write-Host "================================================================" -ForegroundColor Cyan
Write-Host ""

# Navigate to project root
$projectRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
Set-Location $projectRoot

# Check if virtual environment exists
if (-not (Test-Path "rocm_env\Scripts\Activate.ps1")) {
    Write-Host "[ERROR] Virtual environment not found!" -ForegroundColor Red
    Write-Host "   Run setup script first:" -ForegroundColor Yellow
    Write-Host "   .\setup_model_service_windows.ps1" -ForegroundColor Yellow
    Read-Host "Press Enter to exit"
    exit 1
}

Write-Host "[INFO] Activating virtual environment..." -ForegroundColor Green
& "rocm_env\Scripts\Activate.ps1"

Write-Host "[INFO] Setting Vulkan environment variables..." -ForegroundColor Yellow
# Vulkan-specific environment (no ROCm variables needed)
$env:VK_ICD_FILENAMES = ""  # Let system auto-detect
$env:VULKAN_SDK = $env:VULKAN_SDK  # Preserve if set

Write-Host "[INFO] Setting model service environment..." -ForegroundColor Blue
$env:MODELS_PATH = "D:\AI\Life Strands v2\Models"
$env:REDIS_URL = "redis://localhost:6379"
$env:DATABASE_URL = "postgresql://lifestrands_user:lifestrands_password@localhost:5432/lifestrands"
$env:CHAT_MODEL = "Gryphe_Codex-24B-Small-3.2-Q6_K_L.gguf"
$env:SUMMARY_MODEL = "dphn.Dolphin-Mistral-24B-Venice-Edition.Q6_K.gguf"  
$env:EMBEDDING_MODEL = "all-MiniLM-L6-v2.F32.gguf"
$env:CHAT_CONTEXT_SIZE = "8192"
$env:SUMMARY_CONTEXT_SIZE = "4096"
$env:LOG_LEVEL = "DEBUG"

# Check Vulkan availability
Write-Host "[INFO] Checking Vulkan setup..." -ForegroundColor Cyan
try {
    $vulkanInfo = vulkaninfo --summary 2>&1
    if ($LASTEXITCODE -eq 0) {
        Write-Host "[SUCCESS] Vulkan runtime detected" -ForegroundColor Green
    } else {
        Write-Host "[WARNING] Vulkan runtime check failed - continuing anyway" -ForegroundColor Yellow
    }
} catch {
    Write-Host "[WARNING] vulkaninfo not found - continuing anyway" -ForegroundColor Yellow
}

Write-Host ""
Write-Host "[INFO] Model Service will be available at:" -ForegroundColor Magenta
Write-Host "   http://localhost:8001/status - Service status with GPU info" -ForegroundColor White
Write-Host "   http://localhost:8001/health - Health check" -ForegroundColor White
Write-Host "   http://localhost:8001/docs - API documentation" -ForegroundColor White
Write-Host "   http://localhost:8001/generate - Text generation" -ForegroundColor White
Write-Host "   http://localhost:8001/load-model - Load models" -ForegroundColor White
Write-Host "   http://localhost:8001/embeddings - Generate embeddings" -ForegroundColor White
Write-Host ""
Write-Host "[STARTING] Model service with Vulkan GPU acceleration..." -ForegroundColor Green
Write-Host "   Press Ctrl+C to stop the service" -ForegroundColor Yellow
Write-Host ""

try {
    Set-Location "services\model-service"
    python main.py
}
catch {
    Write-Host "[ERROR] Error starting model service: $_" -ForegroundColor Red
}
finally {
    Write-Host ""
    Write-Host "[STOPPED] Model service stopped" -ForegroundColor Yellow
    Read-Host "Press Enter to exit"
}