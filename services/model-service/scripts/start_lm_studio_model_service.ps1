Write-Host "================================" -ForegroundColor Green
Write-Host "Life Strands Model Service" -ForegroundColor Green
Write-Host "LM Studio Backend Mode" -ForegroundColor Green
Write-Host "================================" -ForegroundColor Green

# Navigate to model service directory
Set-Location (Split-Path -Parent $PSScriptRoot)

# Set LM Studio mode
$env:LM_STUDIO_MODE = "true"
$env:MOCK_MODE = "false"

# Set LM Studio connection details
$env:LM_STUDIO_BASE_URL = "http://localhost:1234"

Write-Host "Starting Model Service with LM Studio backend..." -ForegroundColor Yellow
Write-Host "LM Studio URL: $env:LM_STUDIO_BASE_URL" -ForegroundColor Cyan
Write-Host ""

# Check if LM Studio is running
try {
    $response = Invoke-WebRequest -Uri "$env:LM_STUDIO_BASE_URL/v1/models" -TimeoutSec 5 -ErrorAction Stop
    $models = ($response.Content | ConvertFrom-Json).data
    Write-Host "✅ LM Studio detected with $($models.Count) models:" -ForegroundColor Green
    foreach ($model in $models) {
        Write-Host "  - $($model.id)" -ForegroundColor Cyan
    }
} catch {
    Write-Host "⚠️  Warning: Cannot connect to LM Studio at $env:LM_STUDIO_BASE_URL" -ForegroundColor Yellow
    Write-Host "   Make sure LM Studio is running on port 1234" -ForegroundColor Yellow
}

Write-Host ""

# Install required dependencies if needed
Write-Host "Checking dependencies..." -ForegroundColor Yellow
try {
    python -c "import aiohttp" 2>$null
    if ($LASTEXITCODE -ne 0) {
        Write-Host "Installing aiohttp..." -ForegroundColor Yellow
        pip install aiohttp
    }
} catch {
    Write-Host "Installing aiohttp..." -ForegroundColor Yellow
    pip install aiohttp
}

# Start the service
Write-Host "Starting FastAPI server on port 8001..." -ForegroundColor Green
python main.py