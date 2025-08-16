#!/bin/bash

# Life Strands - Stop Model Service from WSL
# This script stops the native Windows model service from within WSL

echo "================================================"
echo "    Stopping Life Strands Model Service       "
echo "================================================"
echo

# First try graceful shutdown via API
echo "Attempting graceful shutdown..."
if curl -s -X POST http://localhost:8001/shutdown >/dev/null 2>&1; then
    echo "✅ Model service shutdown successfully via API"
    sleep 2
    exit 0
fi

echo "API shutdown failed, proceeding with process termination..."
echo

# Find and kill process on port 8001 using Windows commands
echo "Finding model service process on port 8001..."

# Use Windows netstat via cmd.exe to find the process
if command -v cmd.exe >/dev/null 2>&1; then
    # Get the PID of the process using port 8001
    PID=$(cmd.exe /c "netstat -ano | findstr :8001" 2>/dev/null | grep "LISTENING" | awk '{print $5}' | head -1)
    
    if [ -n "$PID" ]; then
        echo "Found model service process: PID $PID"
        
        # Try graceful termination first
        echo "Attempting graceful termination..."
        cmd.exe /c "taskkill /PID $PID" >/dev/null 2>&1
        
        sleep 3
        
        # Check if still running, force kill if necessary
        if cmd.exe /c "tasklist /FI \"PID eq $PID\"" 2>/dev/null | grep -q "$PID"; then
            echo "Forcing process termination..."
            cmd.exe /c "taskkill /F /PID $PID" >/dev/null 2>&1
        fi
        
        echo "✅ Model service stopped successfully"
    else
        echo "⚠️  No process found listening on port 8001"
    fi
else
    echo "⚠️  Cannot access Windows commands from WSL"
    echo "Please stop the model service manually:"
    echo "1. Close the model service terminal window, or"
    echo "2. Press Ctrl+C in the model service window, or"
    echo "3. Use Windows Task Manager to end Python processes"
fi

echo
echo "Checking for any remaining model service processes..."

# Try to kill any remaining Python processes running model service
if command -v cmd.exe >/dev/null 2>&1; then
    # Find Python processes with model-service in command line
    cmd.exe /c "wmic process where \"name='python.exe' and commandline like '%model-service%main.py%'\" get processid /value" 2>/dev/null | grep "ProcessId=" | while read line; do
        if [[ $line =~ ProcessId=([0-9]+) ]]; then
            PID=${BASH_REMATCH[1]}
            if [ -n "$PID" ] && [ "$PID" != "0" ]; then
                echo "Found model service Python process: PID $PID"
                cmd.exe /c "taskkill /F /PID $PID" >/dev/null 2>&1
                if [ $? -eq 0 ]; then
                    echo "✅ Terminated Python process: PID $PID"
                else
                    echo "❌ Failed to terminate process: PID $PID"
                fi
            fi
        fi
    done
fi

echo
echo "Model service shutdown complete."
echo