#!/usr/bin/env powershell

<#
.SYNOPSIS
    Life Strands Development Commands - Windows Native PowerShell
.DESCRIPTION
    Run this from PowerShell for easy Windows development with the Life Strands system.
    Manages both Docker services and the native Windows Vulkan model service.
.EXAMPLE
    .\dev.ps1 dev-up
    .\dev.ps1 dev-down
    .\dev.ps1 model-start
#>

param(
    [Parameter(Position=0)]
    [ValidateSet("help", "setup-model", "dev-up", "dev-down", "model-start", "model-stop", "logs", "status", "health", "restart", "docker-restart", "rebuild")]
    [string]$Command = "help",
    
    [Parameter(Position=1)]
    [string]$ServiceName
)

function Setup-ModelService {
    Write-Host "================================================" -ForegroundColor Cyan
    Write-Host "    Life Strands Model Service Setup         " -ForegroundColor Cyan
    Write-Host "    Vulkan GPU Acceleration Environment      " -ForegroundColor Cyan
    Write-Host "================================================" -ForegroundColor Cyan
    Write-Host ""
    
    Write-Host "Running Windows model service environment setup..." -ForegroundColor Yellow
    
    # Check if setup script exists
    if (-not (Test-Path "setup_model_service_windows.ps1")) {
        Write-Host "ERROR: Setup script not found: setup_model_service_windows.ps1" -ForegroundColor Red
        Write-Host "Make sure you're running this from the Life Strands root directory" -ForegroundColor Yellow
        return $false
    }
    
    try {
        # Run the setup script
        & ".\setup_model_service_windows.ps1"
        
        Write-Host ""
        Write-Host "✅ Model service setup completed!" -ForegroundColor Green
        Write-Host "You can now run: .\dev.ps1 dev-up" -ForegroundColor Cyan
        return $true
    }
    catch {
        Write-Host "❌ Error during setup: $_" -ForegroundColor Red
        return $false
    }
}

function Show-Help {
    Write-Host "================================================" -ForegroundColor Cyan
    Write-Host "    Life Strands Development Commands        " -ForegroundColor Cyan
    Write-Host "    Windows Native PowerShell Edition        " -ForegroundColor Cyan
    Write-Host "================================================" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "Available commands:" -ForegroundColor Yellow
    Write-Host "  .\dev.ps1 setup-model  Setup model service environment (run first time)" -ForegroundColor Cyan
    Write-Host "  .\dev.ps1 dev-up       Start all services (Docker + Native Model)" -ForegroundColor Green
    Write-Host "  .\dev.ps1 dev-down     Stop all services" -ForegroundColor Red
    Write-Host "  .\dev.ps1 model-start  Start only model service in new window" -ForegroundColor Blue
    Write-Host "  .\dev.ps1 model-stop   Stop only model service" -ForegroundColor Red
    Write-Host "  .\dev.ps1 logs         Show Docker service logs" -ForegroundColor Gray
    Write-Host "  .\dev.ps1 status       Show system status" -ForegroundColor Yellow
    Write-Host "  .\dev.ps1 health       Check all service health" -ForegroundColor Magenta
    Write-Host ""
    Write-Host "Examples:" -ForegroundColor Yellow
    Write-Host "  .\dev.ps1 dev-up       # Start everything" -ForegroundColor Cyan
    Write-Host "  .\dev.ps1 dev-down     # Stop everything" -ForegroundColor Cyan
    Write-Host "  .\dev.ps1 status       # Check what's running" -ForegroundColor Cyan
}

function Start-ModelService {
    Write-Host "Starting native Windows model service in new terminal..." -ForegroundColor Cyan
    
    # Check if service directory exists
    if (-not (Test-Path "services\model-service\main.py")) {
        Write-Host "ERROR: Model service not found at services\model-service\main.py" -ForegroundColor Red
        Write-Host "Make sure you're running this from the Life Strands root directory" -ForegroundColor Yellow
        return $false
    }
    
    # Check if virtual environment exists
    if (-not (Test-Path "rocm_env\Scripts\Activate.ps1")) {
        Write-Host "ERROR: Virtual environment not found!" -ForegroundColor Red
        Write-Host "Run setup first: .\dev.ps1 setup-model" -ForegroundColor Yellow
        return $false
    }
    
    # Use the proper Vulkan startup script
    try {
        $currentDir = Get-Location
        $startInfo = @{
            FilePath = "powershell.exe"
            ArgumentList = @(
                "-ExecutionPolicy", "Bypass",
                "-NoExit",
                "-Command", 
                "cd '$currentDir'; & '.\services\model-service\scripts\start_vulkan_model_service.ps1'"
            )
            WindowStyle = "Normal"
            PassThru = $true
        }
        
        $process = Start-Process @startInfo
        
        if ($process) {
            Write-Host "✅ Model service terminal launched successfully!" -ForegroundColor Green
            Write-Host "   Process ID: $($process.Id)" -ForegroundColor Cyan
            Write-Host ""
            
            Write-Host "Waiting for service to initialize..." -ForegroundColor Yellow
            Start-Sleep -Seconds 3
            
            # Check if service is responding
            Write-Host "Checking service health..." -ForegroundColor Cyan
            
            $maxAttempts = 15
            $attempt = 0
            $serviceReady = $false
            
            while ($attempt -lt $maxAttempts -and -not $serviceReady) {
                try {
                    $response = Invoke-WebRequest -Uri "http://localhost:8001/health" -TimeoutSec 2 -ErrorAction SilentlyContinue
                    if ($response.StatusCode -eq 200) {
                        $serviceReady = $true
                        Write-Host "✅ Model service is ready and responding!" -ForegroundColor Green
                        break
                    }
                } catch {
                    # Service not ready yet
                }
                
                Write-Host "." -NoNewline -ForegroundColor Yellow
                Start-Sleep -Seconds 2
                $attempt++
            }
            
            if (-not $serviceReady) {
                Write-Host ""
                Write-Host "⚠️  Service may still be starting. Check the model service window for details." -ForegroundColor Yellow
            }
            
            Write-Host ""
            Write-Host "Model service is running in a separate window." -ForegroundColor Green
            return $true
        }
    } catch {
        Write-Host "❌ Failed to start model service: $_" -ForegroundColor Red
        return $false
    }
}

function Stop-ModelService {
    Write-Host "Stopping native Windows model service..." -ForegroundColor Cyan
    
    # Try graceful shutdown first
    try {
        $response = Invoke-WebRequest -Uri "http://localhost:8001/shutdown" -Method POST -TimeoutSec 5 -ErrorAction SilentlyContinue
        if ($response.StatusCode -eq 200) {
            Write-Host "✅ Model service shutdown successfully via API" -ForegroundColor Green
            Start-Sleep -Seconds 2
            return $true
        }
    } catch {
        Write-Host "API shutdown failed, proceeding with process termination..." -ForegroundColor Yellow
    }
    
    # Find process by port 8001
    try {
        $netstatOutput = netstat -ano | Select-String ":8001.*LISTENING"
        if ($netstatOutput) {
            $pid = ($netstatOutput.ToString().Split() | Where-Object { $_ -match '^\d+$' })[-1]
            
            if ($pid) {
                Write-Host "Found model service process: PID $pid" -ForegroundColor Cyan
                
                # Get process details
                $process = Get-Process -Id $pid -ErrorAction SilentlyContinue
                if ($process) {
                    # Try graceful termination first
                    Write-Host "Attempting graceful termination..." -ForegroundColor Yellow
                    $process.CloseMainWindow()
                    Start-Sleep -Seconds 3
                    
                    # Check if process still exists
                    $stillRunning = Get-Process -Id $pid -ErrorAction SilentlyContinue
                    if ($stillRunning) {
                        Write-Host "Forcing process termination..." -ForegroundColor Red
                        Stop-Process -Id $pid -Force
                    }
                    
                    Write-Host "✅ Model service stopped successfully" -ForegroundColor Green
                    return $true
                }
            }
        }
        
        Write-Host "⚠️  No process found listening on port 8001" -ForegroundColor Yellow
        return $true
    } catch {
        Write-Host "❌ Error stopping model service: $_" -ForegroundColor Red
        return $false
    }
}

function Start-DevEnvironment {
    Write-Host "================================================" -ForegroundColor Cyan
    Write-Host "    Starting Life Strands System             " -ForegroundColor Cyan
    Write-Host "    Windows Native + Docker Services          " -ForegroundColor Cyan
    Write-Host "================================================" -ForegroundColor Cyan
    Write-Host ""
    
    # Check if virtual environment exists first
    if (-not (Test-Path "rocm_env\Scripts\Activate.ps1")) {
        Write-Host "⚠️  Virtual environment not found!" -ForegroundColor Yellow
        Write-Host ""
        $runSetup = Read-Host "Do you want to run the model service setup now? (y/N)"
        
        if ($runSetup -like "y*") {
            Write-Host ""
            Write-Host "Running model service setup first..." -ForegroundColor Cyan
            $setupSuccess = Setup-ModelService
            
            if (-not $setupSuccess) {
                Write-Host "❌ Setup failed. Cannot continue with dev-up." -ForegroundColor Red
                return
            }
            
            Write-Host ""
            Write-Host "Setup completed! Continuing with service startup..." -ForegroundColor Green
            Write-Host ""
        } else {
            Write-Host ""
            Write-Host "❌ Cannot start services without virtual environment." -ForegroundColor Red
            Write-Host "Please run: .\dev.ps1 setup-model" -ForegroundColor Yellow
            return
        }
    }
    
    Write-Host "Step 1: Starting native Windows model service..." -ForegroundColor Yellow
    $modelStarted = Start-ModelService
    
    Write-Host ""
    Write-Host "Step 2: Starting Docker services..." -ForegroundColor Yellow
    
    try {
        $result = docker-compose -f docker-compose.native-model.yml --profile dev-tools --profile frontend up -d
        if ($LASTEXITCODE -ne 0) {
            Write-Host "ERROR: Failed to start Docker services" -ForegroundColor Red
            Write-Host "Make sure Docker is running and try again" -ForegroundColor Yellow
            return
        }
    } catch {
        Write-Host "ERROR: Failed to start Docker services: $_" -ForegroundColor Red
        return
    }
    
    Write-Host ""
    Write-Host "Step 3: Waiting for services to be ready..." -ForegroundColor Yellow
    Start-Sleep -Seconds 5
    
    Write-Host ""
    Write-Host "================================================" -ForegroundColor Green
    Write-Host "    Life Strands System Started Successfully  " -ForegroundColor Green
    Write-Host "================================================" -ForegroundColor Green
    Write-Host ""
    Write-Host "Available services:" -ForegroundColor Yellow
    Write-Host "  Gateway API:       http://localhost:8000" -ForegroundColor Cyan
    Write-Host "  Model Service:     http://localhost:8001 (Native Vulkan)" -ForegroundColor Green
    Write-Host "  Chat Service:      http://localhost:8002" -ForegroundColor Cyan
    Write-Host "  NPC Service:       http://localhost:8003" -ForegroundColor Cyan
    Write-Host "  Summary Service:   http://localhost:8004" -ForegroundColor Cyan
    Write-Host "  Monitor Service:   http://localhost:8005" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "  Chat Interface:    http://localhost:3001" -ForegroundColor Magenta
    Write-Host "  Admin Dashboard:   http://localhost:3002" -ForegroundColor Magenta
    Write-Host ""
    Write-Host "Use '.\dev.ps1 logs' to monitor startup logs" -ForegroundColor Gray
    Write-Host "Use '.\dev.ps1 status' to check service health" -ForegroundColor Gray
}

function Stop-DevEnvironment {
    Write-Host "================================================" -ForegroundColor Red
    Write-Host "    Stopping Life Strands System             " -ForegroundColor Red
    Write-Host "================================================" -ForegroundColor Red
    Write-Host ""
    
    Write-Host "Step 1: Stopping native model service..." -ForegroundColor Yellow
    Stop-ModelService | Out-Null
    
    Write-Host ""
    Write-Host "Step 2: Stopping Docker services..." -ForegroundColor Yellow
    docker-compose -f docker-compose.native-model.yml down
    
    Write-Host ""
    Write-Host "✅ All services stopped successfully" -ForegroundColor Green
}

function Show-Logs {
    param([string]$ServiceName)
    
    Write-Host "================================================" -ForegroundColor Cyan
    if ($ServiceName) {
        Write-Host "    Life Strands Logs - $ServiceName" -ForegroundColor Cyan
    } else {
        Write-Host "    Life Strands Docker Service Logs         " -ForegroundColor Cyan
    }
    Write-Host "================================================" -ForegroundColor Cyan
    Write-Host ""
    
    if ($ServiceName) {
        docker-compose -f docker-compose.native-model.yml logs --tail=50 $ServiceName
    } else {
        docker-compose -f docker-compose.native-model.yml logs --tail=20
    }
}

function Show-Status {
    Write-Host "================================================" -ForegroundColor Cyan
    Write-Host "    Life Strands System Status                " -ForegroundColor Cyan
    Write-Host "================================================" -ForegroundColor Cyan
    Write-Host ""
    
    Write-Host "Docker Services:" -ForegroundColor Yellow
    docker-compose -f docker-compose.native-model.yml ps
    Write-Host ""
    
    Write-Host "Individual Service Status:" -ForegroundColor Yellow
    
    # Check each service individually
    $services = @(
        @{ Name = "Gateway"; Url = "http://localhost:8000/health" },
        @{ Name = "Model (Native)"; Url = "http://localhost:8001/health" },
        @{ Name = "Chat"; Url = "http://localhost:8002/health" },
        @{ Name = "NPC"; Url = "http://localhost:8003/health" },
        @{ Name = "Summary"; Url = "http://localhost:8004/health" },
        @{ Name = "Monitor"; Url = "http://localhost:8005/health" }
    )
    
    foreach ($service in $services) {
        try {
            $response = Invoke-WebRequest -Uri $service.Url -TimeoutSec 5 -ErrorAction SilentlyContinue
            if ($response.StatusCode -eq 200) {
                Write-Host "✅ $($service.Name): Running ($($service.Url))" -ForegroundColor Green
            } else {
                Write-Host "❌ $($service.Name): HTTP $($response.StatusCode)" -ForegroundColor Red
            }
        } catch {
            Write-Host "❌ $($service.Name): Not responding ($($_.Exception.Message))" -ForegroundColor Red
        }
    }
    
    Write-Host ""
    Write-Host "Quick Network Test:" -ForegroundColor Yellow
    
    # Test basic network connectivity
    $ports = @(8000, 8001, 8002, 8003, 8004, 8005)
    foreach ($port in $ports) {
        try {
            $tcpClient = New-Object System.Net.Sockets.TcpClient
            $tcpClient.ConnectAsync("localhost", $port).Wait(1000)
            if ($tcpClient.Connected) {
                Write-Host "✅ Port ${port}: Open" -ForegroundColor Green
                $tcpClient.Close()
            } else {
                Write-Host "❌ Port ${port}: Closed" -ForegroundColor Red
            }
        } catch {
            Write-Host "❌ Port ${port}: Closed" -ForegroundColor Red
        }
    }
}

function Test-ServiceHealth {
    Write-Host "================================================" -ForegroundColor Magenta
    Write-Host "    Life Strands Health Check                 " -ForegroundColor Magenta
    Write-Host "================================================" -ForegroundColor Magenta
    Write-Host ""
    
    $services = @(
        @{ Name = "Gateway Service"; Url = "http://localhost:8000/health" },
        @{ Name = "Model Service"; Url = "http://localhost:8001/health" },
        @{ Name = "Chat Service"; Url = "http://localhost:8002/health" },
        @{ Name = "NPC Service"; Url = "http://localhost:8003/health" },
        @{ Name = "Summary Service"; Url = "http://localhost:8004/health" },
        @{ Name = "Monitor Service"; Url = "http://localhost:8005/health" }
    )
    
    $healthy = 0
    $total = $services.Count
    
    Write-Host "Checking all services..." -ForegroundColor Cyan
    Write-Host ""
    
    foreach ($service in $services) {
        try {
            $response = Invoke-WebRequest -Uri $service.Url -TimeoutSec 2 -ErrorAction SilentlyContinue
            if ($response.StatusCode -eq 200) {
                Write-Host "✅ $($service.Name): Healthy" -ForegroundColor Green
                $healthy++
            } else {
                Write-Host "❌ $($service.Name): Unhealthy" -ForegroundColor Red
            }
        } catch {
            Write-Host "❌ $($service.Name): Unhealthy" -ForegroundColor Red
        }
    }
    
    Write-Host ""
    Write-Host "System Health: $healthy/$total services healthy" -ForegroundColor Cyan
    
    if ($healthy -eq $total) {
        Write-Host "✅ All services are running perfectly!" -ForegroundColor Green
    } else {
        Write-Host "⚠️  Some services need attention" -ForegroundColor Yellow
    }
}

# Main command dispatcher
switch ($Command) {
    "help" { Show-Help }
    "setup-model" { Setup-ModelService }
    "dev-up" { Start-DevEnvironment }
    "dev-down" { Stop-DevEnvironment }
    "restart" { 
        Write-Host "Restarting Life Strands System..." -ForegroundColor Yellow
        Stop-DevEnvironment
        Start-Sleep -Seconds 3
        Start-DevEnvironment
    }
    "docker-restart" {
        Write-Host "Restarting Docker services only (keeping model service)..." -ForegroundColor Yellow
        Write-Host "Stopping Docker services..." -ForegroundColor Cyan
        docker-compose -f docker-compose.native-model.yml down
        Write-Host "Starting Docker services..." -ForegroundColor Cyan
        docker-compose -f docker-compose.native-model.yml up -d
        Write-Host "✅ Docker services restarted" -ForegroundColor Green
    }
    "rebuild" {
        Write-Host "Rebuilding Docker services with latest code..." -ForegroundColor Yellow
        Write-Host "Stopping services..." -ForegroundColor Cyan
        docker-compose -f docker-compose.native-model.yml down
        Write-Host "Building fresh images..." -ForegroundColor Cyan
        docker-compose -f docker-compose.native-model.yml build --no-cache
        Write-Host "Starting services with new images..." -ForegroundColor Cyan
        docker-compose -f docker-compose.native-model.yml up -d
        Write-Host "✅ Services rebuilt and restarted" -ForegroundColor Green
    }
    "model-start" { Start-ModelService }
    "model-stop" { Stop-ModelService }
    "logs" { 
        if ($ServiceName) {
            Show-Logs -ServiceName $ServiceName
        } else {
            Show-Logs
        }
    }
    "status" { Show-Status }
    "health" { Test-ServiceHealth }
    default { Show-Help }
}