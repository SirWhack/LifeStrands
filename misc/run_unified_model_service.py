#!/usr/bin/env python3
"""
Unified Life Strands Model Service - Works on both Windows and Linux/Docker
Automatically detects platform and optimizes for Windows ROCm or Linux GPU
"""

import os
import sys
import platform
from pathlib import Path

# Set ROCm environment variables for Windows before importing anything else
if platform.system() == "Windows":
    os.environ["HIP_PLATFORM"] = "amd"
    os.environ["HSA_OVERRIDE_GFX_VERSION"] = "11.0.0"  # For RX 7900 XTX
    os.environ["HIP_VISIBLE_DEVICES"] = "0"
    print("🔥 Windows ROCm environment configured for AMD 7900 XTX")

# Add the services directory to Python path
services_dir = Path(__file__).parent / "services" / "model-service"
if services_dir.exists():
    sys.path.insert(0, str(services_dir))
    print(f"📁 Added services path: {services_dir}")
else:
    # Fallback for when running from services/model-service directory
    sys.path.insert(0, str(Path(__file__).parent))

# Check dependencies
try:
    import uvicorn
    import fastapi
    from llama_cpp import Llama, llama_cpp
    print("✅ All dependencies available")
    try:
        import llama_cpp
        print(f"🔧 llama-cpp-python version: {llama_cpp.__version__}")
    except AttributeError:
        print("🔧 llama-cpp-python version: unknown")
    
    # Test GPU offload capability
    print(f"🚀 GPU offload support: {llama_cpp.llama_supports_gpu_offload()}")
    
    if not llama_cpp.llama_supports_gpu_offload():
        print("⚠️  WARNING: GPU offload not supported - models will run on CPU")
        print("   Install ROCm version: pip install llama-cpp-python --extra-index-url https://abetlen.github.io/llama-cpp-python/whl/rocm")
    
except ImportError as e:
    print(f"❌ Missing dependency: {e}")
    print("Install required packages:")
    print("  pip install fastapi uvicorn")
    print("  pip install llama-cpp-python --extra-index-url https://abetlen.github.io/llama-cpp-python/whl/rocm")
    sys.exit(1)

def main():
    is_windows = platform.system() == "Windows"
    
    print("🚀 Starting Unified Life Strands Model Service")
    print(f"🖥️  Platform: {platform.system()}")
    print(f"🔥 GPU Acceleration: {'ROCm (AMD)' if is_windows else 'CUDA/ROCm'}")
    
    if is_windows:
        # Windows native mode
        models_path = Path(__file__).parent / "Models"
        print(f"📁 Models directory: {models_path}")
        
        # Set environment variables for Windows
        os.environ["MODELS_PATH"] = str(models_path)
        os.environ["REDIS_URL"] = "redis://localhost:6379"  # Optional
        
        print("\n🌐 Service endpoints:")
        print("  http://localhost:8001/status - Service status with GPU info")
        print("  http://localhost:8001/health - Health check")
        print("  http://localhost:8001/docs - API documentation")
        print("  http://localhost:8001/load-model - Load chat/summary model")
        print("  http://localhost:8001/generate - Text generation")
        print("  http://localhost:8001/embeddings - Generate embeddings")
        print("  http://localhost:8001/vram - VRAM monitoring")
        
    else:
        # Docker/Linux mode
        print("🐳 Running in Docker/Linux mode")
        print("📁 Models directory: /models")
    
    print("\n" + "="*60)
    print("🔥 ALL MODEL LAYERS WILL BE OFFLOADED TO GPU (-1)")
    print("⚡ Maximum GPU acceleration enabled")
    print("="*60 + "\n")
    
    # Import and run the main FastAPI app
    try:
        # Try importing from the services directory first
        if services_dir.exists():
            import sys
            sys.path.insert(0, str(services_dir))
            import main
            app = main.app
        else:
            # Fallback import
            from services.model_service.main import app
            
        uvicorn.run(
            app,
            host="0.0.0.0",
            port=8001,
            log_level="info",
            reload=False  # Disable reload for production stability
        )
    except ImportError as e:
        print(f"❌ Failed to import model service: {e}")
        print("Make sure you're running from the project root directory")
        sys.exit(1)

if __name__ == "__main__":
    main()