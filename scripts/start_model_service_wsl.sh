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
WIN_SERVICE_PATH=$(wslpath -w "$SERVICE_DIR")
echo "Windows Service Path: $WIN_SERVICE_PATH"

# Try different methods to start the service
start_service() {
    # Method 1: Simple approach - start python directly in new window
    if command -v cmd.exe >/dev/null 2>&1; then
        echo "Using Command Prompt..."
        # Use a simpler approach - just start python in the service directory
        cd "$SERVICE_DIR"
        cmd.exe /c "start \"Life Strands Model Service\" cmd.exe /k python main.py"
        return $?
    fi
    
    # Method 2: Try Windows Terminal if available
    if command -v wt.exe >/dev/null 2>&1; then
        echo "Using Windows Terminal..."
        cd "$SERVICE_DIR"
        wt.exe new-tab --title "Life Strands Model Service" cmd.exe /k python main.py
        return $?
    fi
    
    # Method 3: PowerShell fallback
    if command -v powershell.exe >/dev/null 2>&1; then
        echo "Using PowerShell..."
        cd "$SERVICE_DIR"
        powershell.exe -Command "Start-Process python -ArgumentList 'main.py' -WorkingDirectory '$WIN_SERVICE_PATH' -WindowStyle Normal"
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
    echo "Manual startup options:"
    echo "1. Open Windows Terminal or Command Prompt"
    echo "2. Navigate to: $WIN_SERVICE_PATH"
    echo "3. Run: python main.py"
    echo
    echo "Or from WSL, try:"
    echo "cd \"$SERVICE_DIR\" && python main.py"
    exit 1
fi