# Life Strands - Windows Model Service Scripts

This directory contains scripts for managing the native Windows model service with Vulkan GPU acceleration.

## Scripts

### Start Model Service

**WSL/Linux:**
```bash
./start_model_service_wsl.sh
```

**PowerShell (Windows):**
```powershell
.\start_model_service_window.ps1
```

**Batch (Windows):**
```batch
start_model_service_window.bat
```

- Starts the model service in a new terminal window
- Configures Vulkan environment
- Provides colored output and error handling
- Monitors service startup and health
- WSL version automatically detects Windows environment

### Stop Model Service

**WSL/Linux:**
```bash
./stop_model_service_wsl.sh
```

**PowerShell (Windows):**
```powershell
.\stop_model_service.ps1
```

**Batch (Windows):**
```batch
stop_model_service.bat
```

- Gracefully shuts down the model service
- First attempts API shutdown
- Falls back to process termination if needed
- Cleans up any remaining Python processes
- WSL version uses Windows commands via cmd.exe

## Usage with Makefile

The scripts are integrated with the main Makefile:

```bash
# Start entire system (automated)
make dev-up

# Stop entire system (automated)
make dev-down

# Start only model service manually
make model-start-native

# Stop only model service manually
make model-stop-native
```

## Features

### Terminal Window Management
- New dedicated terminal for model service
- Colored output for better visibility
- Window title shows service name
- Stays open for manual control

### Health Monitoring
- Automatic service health checks
- Wait for GPU initialization
- Connection verification
- Clear status feedback

### Error Handling
- Graceful fallback strategies
- Process cleanup on failure
- Clear error messages
- Manual recovery instructions

### Cross-Platform Support
- **WSL/Linux**: Bash scripts that interoperate with Windows
- **PowerShell**: Native Windows scripts for modern environments
- **Batch**: Legacy Windows compatibility
- **Automatic Detection**: Makefile detects environment and uses appropriate script
- **Windows Integration**: WSL scripts use Windows Terminal and cmd.exe

## Manual Usage

### Direct Script Execution

From the root directory:
```bash
# PowerShell
powershell -ExecutionPolicy Bypass -File "scripts/start_model_service_window.ps1"

# Batch
scripts\start_model_service_window.bat
```

### Direct Model Service

From `services/model-service`:
```bash
python main.py
```

## Configuration

The scripts automatically configure:
- Working directory to model service folder
- Vulkan environment variables
- Python virtual environment (if needed)
- Service health monitoring
- Error logging and recovery

## Troubleshooting

### Script Won't Start
1. Check PowerShell execution policy
2. Verify Python installation
3. Ensure model service directory exists
4. Check file permissions

### Service Won't Connect
1. Check Windows firewall settings
2. Verify port 8001 is available
3. Check Vulkan driver installation
4. Monitor GPU memory usage

### Process Won't Stop
1. Close terminal window manually
2. Use Task Manager to end Python processes
3. Check for hanging GPU processes
4. Restart if necessary

## Development

### Adding Features
1. Modify the PowerShell script for main logic
2. Update the batch script for compatibility
3. Test both scripts independently
4. Update Makefile integration

### Debugging
- Scripts include verbose output
- Error messages show specific failures
- Process IDs are tracked
- Health checks provide diagnostics