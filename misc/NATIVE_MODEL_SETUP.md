# Life Strands - Native Windows Model Service Setup

This guide explains how to run the Life Strands system with the model service running natively on Windows for optimal GPU access, while keeping other services in Docker containers.

## 🎯 Why Native Model Service?

- **Direct GPU Access**: No Docker/WSL layer blocking GPU access
- **ROCm Optimization**: Full access to Windows ROCm drivers for AMD GPUs
- **Better Performance**: No virtualization overhead for GPU operations
- **Easier Debugging**: Direct access to GPU tools and monitoring

## 🏗️ Architecture

```
┌─────────────────────┐    ┌─────────────────────────────────┐
│   Docker Services   │    │      Windows Native             │
│  ┌─────────────────┐│    │  ┌─────────────────────────────┐│
│  │ Gateway Service ││◄──►│  │   Model Service (ROCm)     ││
│  │ Chat Service    ││    │  │   - LLM Inference          ││
│  │ NPC Service     ││    │  │   - Embeddings             ││
│  │ Summary Service ││    │  │   - GPU Memory Management  ││
│  │ Monitor Service ││    │  └─────────────────────────────┘│
│  │ Database        ││    │              │                  │
│  │ Redis           ││    │              ▼                  │
│  │ Monitoring      ││    │  ┌─────────────────────────────┐│
│  └─────────────────┘│    │  │   AMD 7900 XTX GPU         ││
└─────────────────────┘    │  │   (Direct ROCm Access)     ││
                           │  └─────────────────────────────┘│
                           └─────────────────────────────────┘
```

## 🚀 Quick Start

### 1. Set Up ROCm Environment (One-time setup)

```powershell
# Run the ROCm setup script
.\setup_windows_rocm.ps1

# Or manually create environment
python -m venv rocm_env
.\rocm_env\Scripts\Activate.ps1
pip install -r requirements.txt

# Install ROCm-enabled llama-cpp-python
pip uninstall llama-cpp-python -y
pip install llama-cpp-python --extra-index-url https://abetlen.github.io/llama-cpp-python/whl/rocm
```

### 2. Start the System

**Option A: Using Makefile (Recommended)**
```powershell
# Start all Docker services except model service
make native-up

# In a separate PowerShell terminal, start the native model service
.\start_native_model_service.ps1
```

**Option B: Manual Start**
```powershell
# Terminal 1: Start Docker services
docker-compose -f docker-compose.native-model.yml up -d

# Terminal 2: Start native model service
.\rocm_env\Scripts\Activate.ps1
python run_unified_model_service.py
```

### 3. Verify Everything is Running

```powershell
# Check service status
make health-check

# Or manually check endpoints
curl http://localhost:8001/status  # Native model service
curl http://localhost:8000/health  # Gateway service
curl http://localhost:8002/health  # Chat service
```

## 📊 Service Endpoints

### Native Model Service (Port 8001)
- `GET /status` - Service status with GPU detection
- `GET /health` - Health check
- `POST /load-model` - Load chat/summary models
- `POST /switch/{model_type}` - Switch between models
- `POST /generate` - Text generation
- `POST /embeddings` - Generate embeddings
- `GET /docs` - API documentation

### Other Services (Docker)
- **Gateway**: http://localhost:8000
- **Chat Interface**: http://localhost:3001 *(requires frontend)*
- **Admin Dashboard**: http://localhost:3002 *(requires frontend)*
- **Monitoring**: http://localhost:3000 (Grafana)
- **Database Admin**: http://localhost:8080 (pgAdmin)

## 🔧 Configuration

### Environment Variables for Native Model Service

The startup scripts automatically set these, but you can customize:

```powershell
# ROCm Configuration
$env:HIP_PLATFORM = "amd"
$env:HSA_OVERRIDE_GFX_VERSION = "11.0.0"  # For RX 7900 XTX
$env:HIP_VISIBLE_DEVICES = "0"

# Model Configuration  
$env:MODELS_PATH = "D:\AI\Life Strands v2\Models"
$env:CHAT_MODEL = "Gryphe_Codex-24B-Small-3.2-Q6_K_L.gguf"
$env:SUMMARY_MODEL = "dphn.Dolphin-Mistral-24B-Venice-Edition.Q6_K.gguf"
$env:EMBEDDING_MODEL = "all-MiniLM-L6-v2.F32.gguf"

# Service Configuration
$env:REDIS_URL = "redis://localhost:6379"
$env:DATABASE_URL = "postgresql://lifestrands_user:lifestrands_password@localhost:5432/lifestrands"
```

## 🐛 Troubleshooting

### GPU Not Detected
```powershell
# Check ROCm installation
& "C:\Program Files\AMD\ROCm\6.2\bin\hipInfo.exe"

# Check llama-cpp-python GPU support
python -c "from llama_cpp import llama_cpp; print('GPU offload:', llama_cpp.llama_supports_gpu_offload())"

# If False, reinstall with ROCm support
pip uninstall llama-cpp-python -y
$env:CMAKE_ARGS = "-DLLAMA_HIPBLAS=on -DHIP_PLATFORM=amd -DAMDGPU_TARGETS=gfx1100"
$env:FORCE_CMAKE = "1"
pip install llama-cpp-python --no-cache-dir --force-reinstall --no-binary=llama-cpp-python
```

### Service Connection Issues
```powershell
# Check if model service is running
curl http://localhost:8001/health

# Check Docker services can reach model service
curl http://host.docker.internal:8001/health

# Restart Docker networking if needed
docker network ls
docker network prune
```

### Model Loading Failures
```powershell
# Verify model files exist
ls Models\

# Check model service logs for detailed error info
# The service runs in console mode, so errors will be visible

# Test model loading manually
curl -X POST http://localhost:8001/load-model -H "Content-Type: application/json" -d '{"model_type": "chat"}'
```

## 📁 File Structure

```
Life Strands v2/
├── docker-compose.native-model.yml  # Docker config without model service
├── run_unified_model_service.py     # Unified model service (Windows/Linux)
├── start_native_model_service.ps1   # PowerShell startup script
├── start_native_model_service.bat   # Batch startup script
├── services/
│   └── model-service/               # Enhanced model service code
│       ├── main.py                  # FastAPI application
│       └── src/
│           └── model_manager.py     # Platform-aware model manager
└── Models/                          # Model files directory
    ├── Gryphe_Codex-24B-Small-3.2-Q6_K_L.gguf
    ├── dphn.Dolphin-Mistral-24B-Venice-Edition.Q6_K.gguf
    └── all-MiniLM-L6-v2.F32.gguf
```

## 🔄 Development Workflow

### Daily Development
```powershell
# Start the system
make native-up
.\start_native_model_service.ps1

# Develop and test...

# Stop the system
make native-down
# Ctrl+C in model service terminal
```

### Switching Between Modes
```powershell
# Traditional Docker mode (all services in containers)
make dev-down     # Stop native mode
make dev-up       # Start traditional mode

# Back to native model mode
make dev-down     # Stop traditional mode  
make native-up    # Start native mode
# Start model service manually
```

## 📈 Performance Benefits

With native model service you should see:
- **Faster model loading** (seconds vs minutes)
- **Better inference speed** (direct GPU access)
- **Lower memory overhead** (no Docker layer)
- **More reliable GPU detection** (direct ROCm access)
- **Better debugging** (direct access to GPU tools)

## 🔐 Security Notes

- Model service runs on localhost:8001 (not exposed externally)
- Docker services use internal networking with `host.docker.internal`
- No additional firewall configuration needed
- Same authentication/authorization as Docker mode