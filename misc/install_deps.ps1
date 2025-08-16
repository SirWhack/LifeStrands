#!/usr/bin/env powershell

<#
.SYNOPSIS
    Install dependencies for the Life Strands model service
.DESCRIPTION
    This script activates the rocm_env virtual environment and installs all required packages
#>

Write-Host "================================================" -ForegroundColor Cyan
Write-Host "    Life Strands Dependency Installation       " -ForegroundColor Cyan
Write-Host "================================================" -ForegroundColor Cyan
Write-Host ""

# Check if rocm_env exists, create if it doesn't
if (-not (Test-Path "rocm_env")) {
    Write-Host "Creating Python virtual environment..." -ForegroundColor Yellow
    try {
        python -m venv rocm_env
        Write-Host "✅ Virtual environment created: rocm_env" -ForegroundColor Green
    } catch {
        Write-Host "❌ Failed to create virtual environment: $_" -ForegroundColor Red
        Write-Host "Make sure Python is installed and accessible" -ForegroundColor Yellow
        exit 1
    }
} else {
    Write-Host "✅ Virtual environment found: rocm_env" -ForegroundColor Green
}

# Activate the environment
Write-Host ""
Write-Host "Activating virtual environment..." -ForegroundColor Yellow
try {
    & ".\rocm_env\Scripts\Activate.ps1"
    Write-Host "✅ Virtual environment activated" -ForegroundColor Green
} catch {
    Write-Host "❌ Failed to activate virtual environment: $_" -ForegroundColor Red
    exit 1
}

# Upgrade pip first
Write-Host ""
Write-Host "Upgrading pip..." -ForegroundColor Yellow
& python -m pip install --upgrade pip

# Install model service dependencies
Write-Host ""
Write-Host "Installing model service dependencies..." -ForegroundColor Yellow
if (Test-Path "services\model-service\requirements.txt") {
    & pip install -r services\model-service\requirements.txt
    if ($LASTEXITCODE -ne 0) {
        Write-Host "❌ Failed to install model service dependencies" -ForegroundColor Red
        exit 1
    }
    Write-Host "✅ Model service dependencies installed" -ForegroundColor Green
} else {
    Write-Host "⚠️  Model service requirements.txt not found" -ForegroundColor Yellow
}

# Install llama-cpp-python with Vulkan support if not already installed
Write-Host ""
Write-Host "Checking llama-cpp-python installation..." -ForegroundColor Yellow
try {
    & python -c "from llama_cpp import Llama"
    Write-Host "✅ llama-cpp-python is already installed" -ForegroundColor Green
} catch {
    Write-Host "Installing llama-cpp-python with Vulkan support..." -ForegroundColor Yellow
    Write-Host "This may take several minutes..." -ForegroundColor Yellow
    
    $env:CMAKE_ARGS = "-DGGML_VULKAN=ON"
    & pip install llama-cpp-python --force-reinstall --no-cache-dir --verbose
    
    if ($LASTEXITCODE -ne 0) {
        Write-Host "❌ Failed to install llama-cpp-python with Vulkan" -ForegroundColor Red
        Write-Host "You may need to install Vulkan SDK first" -ForegroundColor Yellow
        exit 1
    }
    Write-Host "✅ llama-cpp-python installed with Vulkan support" -ForegroundColor Green
}

# Verify installation
Write-Host ""
Write-Host "Verifying installation..." -ForegroundColor Yellow
$requiredPackages = @("fastapi", "uvicorn", "llama_cpp", "aiohttp")
$allInstalled = $true

foreach ($package in $requiredPackages) {
    try {
        $packageName = $package -replace "_", "-"
        & python -c "import $($package -replace '-', '_'); print('✅ $packageName: OK')"
        if ($LASTEXITCODE -eq 0) {
            Write-Host "✅ $packageName: Available" -ForegroundColor Green
        } else {
            Write-Host "❌ $packageName: Failed to import" -ForegroundColor Red
            $allInstalled = $false
        }
    } catch {
        Write-Host "❌ $packageName: Failed to import" -ForegroundColor Red
        $allInstalled = $false
    }
}

Write-Host ""
if ($allInstalled) {
    Write-Host "================================================" -ForegroundColor Green
    Write-Host "    Installation Complete!                     " -ForegroundColor Green
    Write-Host "================================================" -ForegroundColor Green
    Write-Host ""
    Write-Host "You can now start the system with:" -ForegroundColor Cyan
    Write-Host "  .\dev.ps1 dev-up" -ForegroundColor Green
    Write-Host ""
    Write-Host "Or verify the environment with:" -ForegroundColor Cyan
    Write-Host "  .\verify_env.ps1" -ForegroundColor Green
} else {
    Write-Host "================================================" -ForegroundColor Red
    Write-Host "    Installation Issues Detected               " -ForegroundColor Red
    Write-Host "================================================" -ForegroundColor Red
    Write-Host ""
    Write-Host "Some packages failed to install or import." -ForegroundColor Yellow
    Write-Host "Please check the error messages above." -ForegroundColor Yellow
}

Write-Host ""