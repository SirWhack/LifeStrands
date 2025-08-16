# Life Strands - Windows Development Guide

For Windows users who want to run the Life Strands system natively without WSL complexity.

## Quick Start

### Option 1: PowerShell (Recommended)
```powershell
# Start everything
.\dev.ps1 dev-up

# Stop everything
.\dev.ps1 dev-down

# Check status
.\dev.ps1 status
```

### Option 2: Command Prompt
```batch
# Start everything
dev.bat dev-up

# Stop everything
dev.bat dev-down

# Check status
dev.bat status
```

## Available Commands

### System Management
- `dev-up` - Start all services (Docker + Native Vulkan Model)
- `dev-down` - Stop all services
- `status` - Show what's currently running
- `health` - Check all service health
- `logs` - View Docker service logs

### Model Service Only
- `model-start` - Start just the model service in new window
- `model-stop` - Stop just the model service

## Prerequisites

1. **Docker Desktop** - Running and accessible
2. **Python** - Available in PATH 
3. **Vulkan Drivers** - For AMD 7900 XTX GPU acceleration
4. **PowerShell** or **Command Prompt** - For running commands
5. **Python Virtual Environment** - rocm_env with dependencies

## First-Time Setup

### Quick Setup (Recommended)
```powershell
# Install all dependencies automatically
.\install_deps.ps1

# Verify everything is working
.\verify_env.ps1
```

### Manual Setup
```powershell
# Create virtual environment
python -m venv rocm_env

# Activate environment
.\rocm_env\Scripts\Activate.ps1

# Install dependencies
pip install -r services\model-service\requirements.txt

# Install llama-cpp-python with Vulkan support
$env:CMAKE_ARGS = "-DGGML_VULKAN=ON"
pip install llama-cpp-python --force-reinstall --no-cache-dir
```

## What Happens When You Run dev-up

1. **Native Model Service** starts in a new terminal window with:
   - AMD 7900 XTX Vulkan GPU acceleration
   - Direct Windows performance (no Docker overhead)
   - Real-time GPU monitoring and control

2. **Docker Services** start automatically:
   - Gateway, Chat, NPC, Summary, Monitor services
   - PostgreSQL database with pgvector
   - Redis for queuing and caching

3. **Health Checks** verify all services are responding

4. **Service URLs** are displayed for easy access

## Service Access

Once started, you can access:

- **Gateway API**: http://localhost:8000
- **Model Service**: http://localhost:8001 (Native Vulkan)
- **Chat Service**: http://localhost:8002
- **NPC Service**: http://localhost:8003
- **Summary Service**: http://localhost:8004
- **Monitor Service**: http://localhost:8005

Frontend applications:
- **Chat Interface**: http://localhost:3001
- **Admin Dashboard**: http://localhost:3002

## Model Service Control

The native model service runs in its own terminal window where you can:
- See real-time GPU usage and performance
- Monitor model loading and switching
- View conversation processing logs
- Manually restart if needed (Ctrl+C, then restart)

## Troubleshooting

### Docker Issues
```powershell
# Check Docker is running
docker --version

# Check Docker services
.\dev.ps1 status
```

### Model Service Issues
```powershell
# Check if Python is accessible
python --version

# Check if model service directory exists
dir services\model-service\main.py

# Start model service manually
cd services\model-service
python main.py
```

### Port Conflicts
If you get port conflicts, check what's using the ports:
```powershell
netstat -ano | findstr :8001
```

### GPU Issues
Verify Vulkan is working:
```powershell
vulkaninfo --summary
```

## Development Workflow

### Typical Development Session
```powershell
# Start everything
.\dev.ps1 dev-up

# Develop and test...

# Check logs if needed
.\dev.ps1 logs

# Check service health
.\dev.ps1 health

# Stop when done
.\dev.ps1 dev-down
```

### Model Service Only
If you only need to work on the model service:
```powershell
# Start just the model service
.\dev.ps1 model-start

# Work on model service...

# Stop model service
.\dev.ps1 model-stop
```

## Advantages of Native Windows Development

✅ **Better GPU Performance** - Direct Vulkan access without Docker overhead  
✅ **Easier Development** - Native Windows tools and debugging  
✅ **Real-time Control** - Direct access to model service terminal  
✅ **Simplified Setup** - No WSL or Linux virtualization needed  
✅ **Windows Integration** - Native PowerShell and Command Prompt support

## File Structure

```
Life Strands v2/
├── dev.ps1              # PowerShell development commands
├── dev.bat              # Batch development commands  
├── WINDOWS_DEV.md       # This guide
├── services/            # Microservices
│   └── model-service/   # Native Windows Vulkan service
├── scripts/             # Additional utility scripts
└── docker-compose.native-model.yml  # Docker config excluding model service
```

## Support

If you encounter issues:
1. Check this guide first
2. Verify prerequisites are installed
3. Try the troubleshooting steps
4. Check the main project documentation
5. Use `.\dev.ps1 health` to diagnose service issues

The Windows development environment is designed to be simple, fast, and reliable for optimal Life Strands development experience!