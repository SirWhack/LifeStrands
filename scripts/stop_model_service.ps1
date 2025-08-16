#!/usr/bin/env powershell

<#
.SYNOPSIS
    Stop the Life Strands Model Service
.DESCRIPTION
    This script gracefully stops the native Windows model service and closes its terminal window.
.NOTES
    Finds and terminates the model service process running on port 8001.
#>

Write-Host "=================================================" -ForegroundColor Red
Write-Host "    Stopping Life Strands Model Service        " -ForegroundColor Red
Write-Host "=================================================" -ForegroundColor Red
Write-Host ""

try {
    # First, try to gracefully shutdown via API
    Write-Host "Attempting graceful shutdown..." -ForegroundColor Yellow
    try {
        $response = Invoke-WebRequest -Uri "http://localhost:8001/shutdown" -Method POST -TimeoutSec 5 -ErrorAction SilentlyContinue
        if ($response.StatusCode -eq 200) {
            Write-Host "✅ Model service shutdown successfully via API" -ForegroundColor Green
            Start-Sleep -Seconds 2
            exit 0
        }
    } catch {
        Write-Host "API shutdown failed, proceeding with process termination..." -ForegroundColor Yellow
    }

    # Find process by port 8001
    Write-Host "Finding model service process on port 8001..." -ForegroundColor Cyan
    
    $netstatOutput = netstat -ano | Select-String ":8001.*LISTENING"
    if ($netstatOutput) {
        $pid = ($netstatOutput.ToString().Split() | Where-Object { $_ -match '^\d+$' })[-1]
        
        if ($pid) {
            Write-Host "Found model service process: PID $pid" -ForegroundColor Cyan
            
            # Get process details
            $process = Get-Process -Id $pid -ErrorAction SilentlyContinue
            if ($process) {
                Write-Host "Process: $($process.ProcessName) (PID: $($process.Id))" -ForegroundColor Yellow
                
                # Try graceful termination first
                Write-Host "Attempting graceful termination..." -ForegroundColor Yellow
                $process.CloseMainWindow()
                
                # Wait a few seconds for graceful shutdown
                Start-Sleep -Seconds 3
                
                # Check if process still exists
                $stillRunning = Get-Process -Id $pid -ErrorAction SilentlyContinue
                if ($stillRunning) {
                    Write-Host "Forcing process termination..." -ForegroundColor Red
                    Stop-Process -Id $pid -Force
                }
                
                Write-Host "✅ Model service stopped successfully" -ForegroundColor Green
            } else {
                Write-Host "⚠️  Process not found or already stopped" -ForegroundColor Yellow
            }
        } else {
            Write-Host "⚠️  Could not determine process ID" -ForegroundColor Yellow
        }
    } else {
        Write-Host "⚠️  No process found listening on port 8001" -ForegroundColor Yellow
    }

    # Also look for Python processes running main.py in model-service directory
    Write-Host ""
    Write-Host "Checking for any remaining model service processes..." -ForegroundColor Cyan
    
    $pythonProcesses = Get-WmiObject Win32_Process | Where-Object { 
        $_.Name -eq "python.exe" -and 
        $_.CommandLine -like "*model-service*main.py*" 
    }
    
    foreach ($proc in $pythonProcesses) {
        Write-Host "Found model service Python process: PID $($proc.ProcessId)" -ForegroundColor Yellow
        try {
            Stop-Process -Id $proc.ProcessId -Force
            Write-Host "✅ Terminated Python process: PID $($proc.ProcessId)" -ForegroundColor Green
        } catch {
            Write-Host "❌ Failed to terminate process: PID $($proc.ProcessId)" -ForegroundColor Red
        }
    }

    Write-Host ""
    Write-Host "Model service shutdown complete." -ForegroundColor Green
    
} catch {
    Write-Host "❌ Error stopping model service: $_" -ForegroundColor Red
    Write-Host ""
    Write-Host "Manual cleanup:" -ForegroundColor Yellow
    Write-Host "1. Close the model service terminal window" -ForegroundColor Cyan
    Write-Host "2. Or use Task Manager to end Python processes" -ForegroundColor Cyan
    exit 1
}