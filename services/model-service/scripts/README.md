# Model Service Scripts

This directory contains scripts for running and testing the Life Strands Model Service with Vulkan GPU acceleration.

## 🎯 Unified Workflow

The Life Strands system now uses a **unified development workflow**:

1. **Start the native model service** (for optimal Vulkan GPU performance)
2. **Run `make dev-up`** to start all other services in Docker

## Scripts

### 🚀 Startup Scripts

**For Windows PowerShell:**
```powershell
.\start_vulkan_model_service.ps1
```

**For Windows Command Prompt:**
```cmd
start_vulkan_model_service.bat
```

These scripts will:
- Navigate to project root
- Activate the `rocm_env` virtual environment
- Set up Vulkan environment variables
- Configure model paths and service settings
- Start the model service with GPU acceleration on port 8001

### 🧪 Testing Scripts

**Test Vulkan Setup:**
```bash
python test_vulkan_setup.py
```

This script verifies:
- llama-cpp-python installation
- Vulkan runtime availability
- GPU detection
- Backend compilation (checks for Vulkan support)

## 🚀 Complete System Startup

**Step 1: Start the native model service**
```cmd
cd services\model-service\scripts
.\start_vulkan_model_service.bat
```

**Step 2: Start all other services (from project root)**
```bash
make dev-up
```

This will start:
- PostgreSQL with pgvector (port 5432)
- Redis (port 6379)
- Gateway Service (port 8000)
- Chat Service (port 8002)
- NPC Service (port 8003)
- Summary Service (port 8004)
- Monitor Service (port 8005)
- Admin tools (pgAdmin, Redis Commander, Grafana, Prometheus)

**Step 3: Check everything is running**
```bash
make health-check
```

## 🛠️ Development Commands

- `make dev-up` - Start all Docker services (model service must be started separately)
- `make dev-down` - Stop all Docker services
- `make logs` - View logs from all services
- `make logs s=chat-service` - View logs from specific service
- `make health-check` - Check all service health
- `make model-status` - Check native model service status

## Requirements

1. **Virtual Environment**: Must have `rocm_env` directory with llama-cpp-python compiled with Vulkan support
2. **Vulkan Runtime**: Vulkan drivers and runtime installed
3. **Models**: GGUF model files in the `Models/` directory

## Service Endpoints

Once running, the services will be available at:

- **Model Service**: `http://localhost:8001` (Native Vulkan)
- **Gateway API**: `http://localhost:8000` 
- **Chat Service**: `http://localhost:8002`
- **NPC Service**: `http://localhost:8003`
- **Summary Service**: `http://localhost:8004`
- **Monitor Service**: `http://localhost:8005`
- **Database Admin**: `http://localhost:8080` (pgAdmin)
- **Redis Admin**: `http://localhost:8081` (Redis Commander)
- **Monitoring**: `http://localhost:3000` (Grafana)

## Troubleshooting

1. **Import Errors**: Run `test_vulkan_setup.py` to verify setup
2. **No GPU Acceleration**: Check that llama-cpp-python was compiled with `CMAKE_ARGS="-DGGML_VULKAN=ON"`
3. **Vulkan Errors**: Verify Vulkan drivers are installed and `vulkaninfo` works
4. **Missing Models**: Ensure GGUF files are in the `Models/` directory
5. **Port Conflicts**: Make sure no other services are using ports 8001-8005