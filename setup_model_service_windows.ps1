# Life Strands - Setup Windows Model Service Environment
# This script sets up the virtual environment and dependencies for the model service

Write-Host "================================================================" -ForegroundColor Cyan
Write-Host "Life Strands - Windows Model Service Environment Setup" -ForegroundColor Cyan  
Write-Host "================================================================" -ForegroundColor Cyan
Write-Host ""

# Check if Python is available
try {
    $pythonVersion = python --version 2>&1
    Write-Host "[INFO] Python found: $pythonVersion" -ForegroundColor Green
} catch {
    Write-Host "[ERROR] Python not found! Please install Python 3.8+ first." -ForegroundColor Red
    Read-Host "Press Enter to exit"
    exit 1
}

# Check if we're in the right directory
if (-not (Test-Path "services\model-service")) {
    Write-Host "[ERROR] Please run this script from the project root directory" -ForegroundColor Red
    Write-Host "Current directory: $(Get-Location)" -ForegroundColor Yellow
    Read-Host "Press Enter to exit"
    exit 1
}

Write-Host "[INFO] Setting up virtual environment..." -ForegroundColor Blue

# Check if environment already exists and is properly configured
if (Test-Path "rocm_env") {
    Write-Host "[INFO] Virtual environment already exists" -ForegroundColor Yellow
    $rebuild = Read-Host "Do you want to rebuild it? (y/N)"
    if ($rebuild -notlike "y*") {
        Write-Host "[INFO] Using existing environment. Testing setup..." -ForegroundColor Green
        & "rocm_env\Scripts\Activate.ps1"
        python services\model-service\scripts\check_vulkan_build.py
        Read-Host "Press Enter to exit"
        exit 0
    } else {
        Write-Host "[INFO] Removing existing virtual environment..." -ForegroundColor Yellow
        Remove-Item -Recurse -Force "rocm_env"
    }
}

# Create new virtual environment
Write-Host "[INFO] Creating virtual environment..." -ForegroundColor Green
python -m venv rocm_env

# Activate virtual environment
Write-Host "[INFO] Activating virtual environment..." -ForegroundColor Green
& "rocm_env\Scripts\Activate.ps1"

# Upgrade pip
Write-Host "[INFO] Upgrading pip..." -ForegroundColor Blue
python -m pip install --upgrade pip

# Install llama-cpp-python with Vulkan support
Write-Host "[INFO] Installing llama-cpp-python with Vulkan support..." -ForegroundColor Magenta
Write-Host "This may take several minutes..." -ForegroundColor Yellow
$env:CMAKE_ARGS = "-DGGML_VULKAN=ON"
pip install llama-cpp-python --force-reinstall --no-cache-dir --verbose

# Install other dependencies
Write-Host "[INFO] Installing other dependencies..." -ForegroundColor Blue
pip install -r services\model-service\requirements.txt --force-reinstall

# Additional dependencies that might be needed
Write-Host "[INFO] Installing additional dependencies..." -ForegroundColor Blue
pip install asyncio-mqtt websockets pynvml

Write-Host ""
Write-Host "[SUCCESS] Setup completed!" -ForegroundColor Green
Write-Host ""
Write-Host "Next steps:" -ForegroundColor Cyan
Write-Host "1. Ensure your Models directory contains the GGUF files:" -ForegroundColor White
Write-Host "   - Models\Gryphe_Codex-24B-Small-3.2-Q6_K_L.gguf" -ForegroundColor White
Write-Host "   - Models\dphn.Dolphin-Mistral-24B-Venice-Edition.Q6_K.gguf" -ForegroundColor White
Write-Host "   - Models\all-MiniLM-L6-v2.F32.gguf" -ForegroundColor White
Write-Host ""
Write-Host "2. Test the setup:" -ForegroundColor White
Write-Host "   cd services\model-service\scripts" -ForegroundColor White
Write-Host "   python test_vulkan_setup.py" -ForegroundColor White
Write-Host ""
Write-Host "3. Start the service:" -ForegroundColor White
Write-Host "   .\scripts\start_vulkan_model_service.ps1" -ForegroundColor White
Write-Host ""

Read-Host "Press Enter to exit"