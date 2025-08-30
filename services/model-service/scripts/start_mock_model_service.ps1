# Mock Model Service Startup Script (PowerShell)

Write-Host "====================================" -ForegroundColor Cyan
Write-Host "Starting Mock Model Service" -ForegroundColor Cyan  
Write-Host "====================================" -ForegroundColor Cyan

# Navigate to model service directory
Set-Location (Join-Path $PSScriptRoot "..")

# Set mock mode environment variables
$env:MOCK_MODE = "true"
$env:ENABLE_GPU = "false"

Write-Host "Mock mode enabled - no GPU resources required" -ForegroundColor Green
Write-Host "Starting lightweight model service with canned responses..." -ForegroundColor Yellow
Write-Host ""

try {
    # Start the mock service
    python main_mock.py
}
catch {
    Write-Host "Error starting mock service: $_" -ForegroundColor Red
}
finally {
    Write-Host ""
    Write-Host "Mock Model Service stopped" -ForegroundColor Yellow
    Read-Host "Press Enter to continue..."
}