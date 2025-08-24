#!/bin/bash

# Life Strands - Start Model Service from WSL
# This script starts the native Windows model service from within WSL

set -e

echo "================================================"
echo "    Life Strands - Starting Model Service     "
echo "    Native Windows Vulkan GPU Acceleration    "
echo "================================================"
echo

# Get the root directory (parent of scripts folder)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(dirname "$SCRIPT_DIR")"
SERVICE_DIR="$ROOT_DIR/services/model-service"

echo "Root Directory: $ROOT_DIR"
echo "Service Directory: $SERVICE_DIR"
echo

# Check if service directory exists
if [ ! -d "$SERVICE_DIR" ]; then
    echo "ERROR: Model service directory not found: $SERVICE_DIR"
    echo "Please ensure you're running this from the correct location."
    exit 1
fi

echo "Starting model service in new Windows terminal..."

# Convert WSL path to Windows path
WIN_SERVICE_PATH=$(wslpath -w "$SERVICE_DIR" 2>/dev/null)
if [ $? -ne 0 ] || [ -z "$WIN_SERVICE_PATH" ]; then
    echo "Warning: wslpath failed, using manual conversion..."
    # Manual conversion for /mnt/d/ paths
    WIN_SERVICE_PATH=$(echo "$SERVICE_DIR" | sed 's|/mnt/\([a-z]\)/|\U\1:/|')
fi
echo "Windows Service Path: $WIN_SERVICE_PATH"

# Try different methods to start the service
start_service() {
    # Get the root directory Windows path
    ROOT_WIN_PATH=$(echo "$ROOT_DIR" | sed 's|/mnt/\([a-z]\)/|\U\1:/|')
    SCRIPT_WIN_PATH="$ROOT_WIN_PATH\\services\\model-service\\scripts\\start_vulkan_model_service.ps1"
    
    # Method 1: Try Windows Terminal with PowerShell (best option)
    if command -v wt.exe >/dev/null 2>&1; then
        echo "Using Windows Terminal with PowerShell..."
        wt.exe new-tab --title "LifeStrandsModel" --startingDirectory "$ROOT_WIN_PATH" powershell.exe -ExecutionPolicy Bypass -File "$SCRIPT_WIN_PATH"
        return $?
    fi
    
    # Method 2: PowerShell direct approach
    if command -v powershell.exe >/dev/null 2>&1; then
        echo "Using PowerShell..."
        powershell.exe -Command "Start-Process powershell -ArgumentList '-ExecutionPolicy', 'Bypass', '-File', '$SCRIPT_WIN_PATH' -WorkingDirectory '$ROOT_WIN_PATH' -WindowStyle Normal"
        return $?
    fi
    
    # Method 3: Command Prompt fallback
    if command -v cmd.exe >/dev/null 2>&1; then
        echo "Using Command Prompt..."
        cmd.exe /c start "LifeStrandsModel" powershell.exe -ExecutionPolicy Bypass -File "$SCRIPT_WIN_PATH"
        return $?
    fi
    
    return 1
}

# Attempt to start the service
if start_service; then
    echo "✅ Model service terminal launched successfully!"
    echo
    echo "Waiting for service to initialize..."
    sleep 3
    
    # Check if the service is responding
    echo "Checking service health..."
    
    max_wait=30
    wait_time=0
    service_ready=false
    
    while [ $wait_time -lt $max_wait ] && [ "$service_ready" = "false" ]; do
        if curl -s http://localhost:8001/health >/dev/null 2>&1; then
            service_ready=true
            echo "✅ Model service is ready and responding!"
            break
        fi
        
        echo -n "."
        sleep 2
        wait_time=$((wait_time + 2))
    done
    
    if [ "$service_ready" = "false" ]; then
        echo
        echo "⚠️  Service may still be starting. Check the model service window for details."
    fi
    
    echo
    echo "Model service window is running. You can control it from there."
    echo
    
else
    echo "❌ Failed to start model service terminal automatically"
    echo
    ROOT_WIN_PATH=$(echo "$ROOT_DIR" | sed 's|/mnt/\([a-z]\)/|\U\1:/|')
    echo "Manual startup options:"
    echo "1. First, set up the environment (if not done already):"
    echo "   Open PowerShell in: $ROOT_WIN_PATH"
    echo "   Run: .\\setup_model_service_windows.ps1"
    echo
    echo "2. Then start the service:"
    echo "   Run: .\\services\\model-service\\scripts\\start_vulkan_model_service.ps1"
    echo
    echo "Or from WSL, try manually:"
    echo "   cd \"$ROOT_DIR\" && powershell.exe ./setup_model_service_windows.ps1"
    echo "   cd \"$ROOT_DIR\" && powershell.exe ./services/model-service/scripts/start_vulkan_model_service.ps1"
    exit 1
fi