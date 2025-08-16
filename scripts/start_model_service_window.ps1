#!/usr/bin/env powershell

<#
.SYNOPSIS
    Start the Life Strands Model Service in a new terminal window
.DESCRIPTION
    This script starts the native Windows Vulkan model service in a separate 
    PowerShell terminal window that can be controlled independently.
.NOTES
    Requires Windows PowerShell and the model service environment to be set up.
#>

param(
    [string]$WorkingDirectory = (Split-Path -Parent (Split-Path -Parent $PSScriptRoot)),
    [string]$ServicePath = "services\model-service",
    [string]$Title = "Life Strands - Model Service (Vulkan GPU)",
    [switch]$Minimized = $false
)

# Set window title and colors for the new terminal
$windowTitle = $Title
$backgroundColor = "Black"
$foregroundColor = "Cyan"

# Build the command to run in the new window
$serviceFullPath = Join-Path $WorkingDirectory $ServicePath
$activateCommand = "cd '$serviceFullPath'"
$startCommand = "python main.py"

# Create the full command with proper error handling and logging
$fullCommand = @"
`$Host.UI.RawUI.WindowTitle = '$windowTitle'
`$Host.UI.RawUI.BackgroundColor = '$backgroundColor'
`$Host.UI.RawUI.ForegroundColor = '$foregroundColor'
Clear-Host

Write-Host "=================================================" -ForegroundColor Green
Write-Host "    Life Strands - Native Model Service        " -ForegroundColor Green  
Write-Host "    AMD 7900 XTX Vulkan GPU Acceleration       " -ForegroundColor Green
Write-Host "=================================================" -ForegroundColor Green
Write-Host ""
Write-Host "Working Directory: $serviceFullPath" -ForegroundColor Yellow
Write-Host "Starting native Windows model service..." -ForegroundColor Cyan
Write-Host ""

try {
    $activateCommand
    if (`$LASTEXITCODE -ne 0) {
        Write-Host "Failed to change directory" -ForegroundColor Red
        exit 1
    }
    
    Write-Host "Launching model service with Vulkan GPU support..." -ForegroundColor Green
    $startCommand
} catch {
    Write-Host "Error starting model service: `$_" -ForegroundColor Red
    Write-Host "Press any key to exit..." -ForegroundColor Yellow
    `$null = `$Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")
    exit 1
}

Write-Host ""
Write-Host "Model service stopped. Press any key to close this window..." -ForegroundColor Yellow
`$null = `$Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")
"@

# Determine window style
$windowStyle = if ($Minimized) { "Minimized" } else { "Normal" }

try {
    Write-Host "Starting Life Strands Model Service in new terminal..." -ForegroundColor Green
    Write-Host "Service Path: $serviceFullPath" -ForegroundColor Yellow
    Write-Host ""
    
    # Start new PowerShell window with the service
    $processArgs = @{
        FilePath = "powershell.exe"
        ArgumentList = @(
            "-NoExit",
            "-Command", 
            $fullCommand
        )
        WindowStyle = $windowStyle
        PassThru = $true
    }
    
    $process = Start-Process @processArgs
    
    if ($process) {
        Write-Host "✅ Model service terminal launched successfully!" -ForegroundColor Green
        Write-Host "   Process ID: $($process.Id)" -ForegroundColor Cyan
        Write-Host "   Window Title: $windowTitle" -ForegroundColor Cyan
        Write-Host ""
        Write-Host "The model service is starting in the new window..." -ForegroundColor Yellow
        Write-Host "Wait a few moments for GPU initialization and model loading." -ForegroundColor Yellow
        
        # Wait a moment for the service to start
        Start-Sleep -Seconds 3
        
        # Check if the service is responding
        Write-Host ""
        Write-Host "Checking service health..." -ForegroundColor Cyan
        
        $maxWaitTime = 30
        $waitTime = 0
        $serviceReady = $false
        
        while ($waitTime -lt $maxWaitTime -and -not $serviceReady) {
            try {
                $response = Invoke-WebRequest -Uri "http://localhost:8001/health" -TimeoutSec 2 -ErrorAction SilentlyContinue
                if ($response.StatusCode -eq 200) {
                    $serviceReady = $true
                    Write-Host "✅ Model service is ready and responding!" -ForegroundColor Green
                    break
                }
            } catch {
                # Service not ready yet, continue waiting
            }
            
            Write-Host "." -NoNewline -ForegroundColor Yellow
            Start-Sleep -Seconds 2
            $waitTime += 2
        }
        
        if (-not $serviceReady) {
            Write-Host ""
            Write-Host "⚠️  Service may still be starting. Check the model service window for details." -ForegroundColor Yellow
        }
        
        Write-Host ""
        Write-Host "Model service window is running. You can control it from there." -ForegroundColor Green
        
        return $process.Id
    } else {
        Write-Host "❌ Failed to start model service terminal" -ForegroundColor Red
        exit 1
    }
    
} catch {
    Write-Host "❌ Error launching model service: $_" -ForegroundColor Red
    Write-Host "Please start the model service manually:" -ForegroundColor Yellow
    Write-Host "   cd services\model-service" -ForegroundColor Cyan
    Write-Host "   python main.py" -ForegroundColor Cyan
    exit 1
}