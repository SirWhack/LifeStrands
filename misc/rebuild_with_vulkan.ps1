# PowerShell script to rebuild llama-cpp-python with Vulkan support for AMD 7900 XTX
Write-Host "=== Rebuilding llama-cpp-python with Vulkan Support ===" -ForegroundColor Green

# Set environment variables for Vulkan
$env:CMAKE_ARGS = "-DGGML_VULKAN=ON"

Write-Host "CMAKE_ARGS set to: $env:CMAKE_ARGS" -ForegroundColor Yellow

# Check if Vulkan SDK is available
Write-Host "Checking Vulkan SDK..." -ForegroundColor Cyan
try {
    $vulkanVersion = vulkaninfo --version 2>&1
    Write-Host "Vulkan SDK found: $vulkanVersion" -ForegroundColor Green
} catch {
    Write-Host "Warning: vulkaninfo not found in PATH" -ForegroundColor Red
    Write-Host "VULKAN_SDK environment variable: $env:VULKAN_SDK" -ForegroundColor Yellow
}

# Change to project directory
Set-Location "D:\AI\Life Strands v2"

# Activate virtual environment
Write-Host "Activating Python virtual environment..." -ForegroundColor Cyan
& ".\rocm_env\Scripts\Activate.ps1"

# Uninstall existing llama-cpp-python
Write-Host "Uninstalling existing llama-cpp-python..." -ForegroundColor Cyan
python -m pip uninstall llama-cpp-python -y

# Install with Vulkan support
Write-Host "Installing llama-cpp-python with Vulkan support..." -ForegroundColor Cyan
Write-Host "This may take 10-15 minutes..." -ForegroundColor Yellow

python -m pip install llama-cpp-python --force-reinstall --no-cache-dir --verbose

# Test the installation
Write-Host "Testing installation..." -ForegroundColor Cyan
python test_gpu.py

Write-Host "=== Build Complete ===" -ForegroundColor Green
Write-Host "Check the output above for 'GPU backend mentioned' or Vulkan references" -ForegroundColor Yellow