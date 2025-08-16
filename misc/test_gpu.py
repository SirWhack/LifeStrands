#!/usr/bin/env python3
"""
Test script to verify GPU acceleration for AMD 7900 XTX
"""
import sys
import os
sys.path.append('rocm_env/Scripts')

try:
    from llama_cpp import Llama
    print("[OK] llama-cpp-python imported successfully")
    
    # Test basic functionality
    print(f"[INFO] llama-cpp-python version: {Llama.__version__ if hasattr(Llama, '__version__') else 'unknown'}")
    
    # Check if we can create a Llama instance (without loading a model)
    try:
        # This will fail since we don't have a model, but it tells us about backends
        test_llama = Llama(model_path="dummy", n_ctx=512, verbose=True)
    except Exception as e:
        print(f"[INFO] Expected model loading error: {str(e)[:100]}...")
        
        # Check if the error mentions GPU backends
        error_msg = str(e).lower()
        if any(backend in error_msg for backend in ["vulkan", "cuda", "hip", "rocm"]):
            print("[GOOD] GPU backend mentioned in error - good sign!")
        else:
            print("[WARN] No GPU backend mentioned in error")
    
    # Test platform detection
    import platform
    print(f"[INFO] Platform: {platform.system()} {platform.machine()}")
    
    # Test ROCm detection
    import subprocess
    hip_versions = ["6.4", "6.3", "6.2", "6.1", "6.0"]
    rocm_found = False
    
    for version in hip_versions:
        hipinfo_path = rf"C:\Program Files\AMD\ROCm\{version}\bin\hipInfo.exe"
        try:
            result = subprocess.run([hipinfo_path], capture_output=True, text=True, timeout=10)
            if result.returncode == 0:
                print(f"[OK] ROCm {version} detected")
                print(f"[INFO] GPU info: {result.stdout[:200]}...")
                rocm_found = True
                break
        except FileNotFoundError:
            continue
        except Exception as e:
            print(f"[ERROR] ROCm {version} check failed: {e}")
    
    if not rocm_found:
        print("[ERROR] No ROCm installation detected")
        
    # Test GPU detection via GPUtil
    try:
        import GPUtil
        gpus = GPUtil.getGPUs()
        if gpus:
            for gpu in gpus:
                print(f"[GPU] GPU found: {gpu.name} ({gpu.memoryTotal}MB)")
        else:
            print("[ERROR] No GPUs detected via GPUtil")
    except Exception as e:
        print(f"[ERROR] GPUtil error: {e}")
        
except ImportError as e:
    print(f"[ERROR] Failed to import llama-cpp-python: {e}")
except Exception as e:
    print(f"[ERROR] Unexpected error: {e}")

print("\n" + "="*50)
print("Test completed. If you see ROCm detected but no GPU backend")
print("mentioned in llama-cpp-python, you need to rebuild with:")
print("CMAKE_ARGS='-DGGML_VULKAN=ON' pip install llama-cpp-python --force-reinstall --no-cache-dir")