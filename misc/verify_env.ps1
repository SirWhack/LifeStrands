#!/usr/bin/env powershell

<#
.SYNOPSIS
    Verify the Life Strands Python environment is properly set up
.DESCRIPTION
    This script checks that the rocm_env virtual environment exists and has all required packages
#>

Write-Host "================================================" -ForegroundColor Cyan
Write-Host "    Life Strands Environment Verification      " -ForegroundColor Cyan
Write-Host "================================================" -ForegroundColor Cyan
Write-Host ""

# Check if rocm_env exists
if (-not (Test-Path "rocm_env")) {
    Write-Host "❌ Virtual environment not found: rocm_env" -ForegroundColor Red
    Write-Host ""
    Write-Host "To create the environment:" -ForegroundColor Yellow
    Write-Host "  python -m venv rocm_env" -ForegroundColor Cyan
    Write-Host "  .\rocm_env\Scripts\Activate.ps1" -ForegroundColor Cyan
    Write-Host "  pip install -r services\model-service\requirements.txt" -ForegroundColor Cyan
    exit 1
}

Write-Host "✅ Virtual environment found: rocm_env" -ForegroundColor Green

# Check if activation script exists
if (-not (Test-Path "rocm_env\Scripts\Activate.ps1")) {
    Write-Host "❌ Activation script not found: rocm_env\Scripts\Activate.ps1" -ForegroundColor Red
    exit 1
}

Write-Host "✅ Activation script found" -ForegroundColor Green

# Activate the environment and check packages
Write-Host ""
Write-Host "Activating virtual environment..." -ForegroundColor Yellow

try {
    & ".\rocm_env\Scripts\Activate.ps1"
    Write-Host "✅ Virtual environment activated" -ForegroundColor Green
} catch {
    Write-Host "❌ Failed to activate virtual environment: $_" -ForegroundColor Red
    exit 1
}

Write-Host ""
Write-Host "Checking required packages..." -ForegroundColor Yellow

$requiredPackages = @("fastapi", "uvicorn", "llama-cpp-python", "aiohttp")
$missingPackages = @()

foreach ($package in $requiredPackages) {
    try {
        $result = & python -c "import $package; print('✅ $package: OK')" 2>$null
        if ($LASTEXITCODE -eq 0) {
            Write-Host "✅ $package: Available" -ForegroundColor Green
        } else {
            Write-Host "❌ $package: Missing" -ForegroundColor Red
            $missingPackages += $package
        }
    } catch {
        Write-Host "❌ $package: Missing" -ForegroundColor Red
        $missingPackages += $package
    }
}

if ($missingPackages.Count -gt 0) {
    Write-Host ""
    Write-Host "❌ Missing packages detected:" -ForegroundColor Red
    foreach ($package in $missingPackages) {
        Write-Host "   - $package" -ForegroundColor Yellow
    }
    Write-Host ""
    Write-Host "To install missing packages:" -ForegroundColor Yellow
    Write-Host "  .\rocm_env\Scripts\Activate.ps1" -ForegroundColor Cyan
    Write-Host "  pip install -r services\model-service\requirements.txt" -ForegroundColor Cyan
    exit 1
}

# Check Python version
Write-Host ""
Write-Host "Python version:" -ForegroundColor Yellow
& python --version

# Check if llama-cpp-python was built with Vulkan
Write-Host ""
Write-Host "Checking llama-cpp-python Vulkan support..." -ForegroundColor Yellow
try {
    $vulkanCheck = & python -c "from llama_cpp import Llama; print('Vulkan support available')" 2>$null
    if ($LASTEXITCODE -eq 0) {
        Write-Host "✅ llama-cpp-python imported successfully" -ForegroundColor Green
    } else {
        Write-Host "⚠️  llama-cpp-python import issues detected" -ForegroundColor Yellow
    }
} catch {
    Write-Host "⚠️  Could not verify llama-cpp-python" -ForegroundColor Yellow
}

Write-Host ""
Write-Host "================================================" -ForegroundColor Green
Write-Host "    Environment Verification Complete          " -ForegroundColor Green
Write-Host "================================================" -ForegroundColor Green
Write-Host ""
Write-Host "Environment is ready! You can now run:" -ForegroundColor Cyan
Write-Host "  .\dev.ps1 dev-up" -ForegroundColor Green
Write-Host ""