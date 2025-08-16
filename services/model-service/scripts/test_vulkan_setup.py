#!/usr/bin/env python3
"""
Test script to verify Vulkan GPU acceleration setup for llama-cpp-python
"""
import sys
import os

def test_vulkan_setup():
    """Test Vulkan-based llama-cpp-python setup"""
    print("=" * 60)
    print("VULKAN GPU ACCELERATION TEST")
    print("=" * 60)
    
    # Test llama-cpp-python import
    try:
        from llama_cpp import Llama
        print("✅ llama-cpp-python imported successfully")
    except ImportError as e:
        print(f"❌ Failed to import llama-cpp-python: {e}")
        return False
    
    # Test platform detection
    import platform
    print(f"📊 Platform: {platform.system()} {platform.machine()}")
    
    # Test Vulkan runtime
    print("\n🔍 Checking Vulkan runtime...")
    import subprocess
    try:
        result = subprocess.run(["vulkaninfo", "--summary"], 
                              capture_output=True, text=True, timeout=10)
        if result.returncode == 0:
            print("✅ Vulkan runtime detected")
            # Look for GPU info in output
            if "7900" in result.stdout or "RDNA3" in result.stdout:
                print("🔥 AMD 7900 XTX detected!")
            elif "GPU" in result.stdout:
                print("🎮 GPU detected via Vulkan")
        else:
            print("⚠️  Vulkan runtime check failed")
    except FileNotFoundError:
        print("⚠️  vulkaninfo not found in PATH")
    except Exception as e:
        print(f"⚠️  Vulkan check error: {e}")
    
    # Test model loading with verbose output to check for Vulkan backend
    print("\n🧪 Testing model loading (will fail - checking for Vulkan backend)...")
    try:
        # This will fail since we don't provide a real model path
        # But the verbose output should mention Vulkan if compiled correctly
        test_llama = Llama(
            model_path="dummy_path", 
            n_ctx=512, 
            n_gpu_layers=-1,  # Try to use GPU
            verbose=True
        )
    except Exception as e:
        error_msg = str(e).lower()
        print(f"📝 Model loading error (expected): {str(e)[:100]}...")
        
        # Check for Vulkan mentions in error
        if "vulkan" in error_msg:
            print("✅ Vulkan backend detected in llama-cpp-python!")
        elif any(backend in error_msg for backend in ["cuda", "hip", "rocm"]):
            print("⚠️  Other GPU backend detected, but not Vulkan")
        else:
            print("❌ No GPU backend detected - may be CPU-only build")
    
    # Test environment variables
    print("\n🌍 Environment variables:")
    vulkan_vars = ["VULKAN_SDK", "VK_ICD_FILENAMES"]
    for var in vulkan_vars:
        value = os.getenv(var, "Not set")
        print(f"   {var}: {value}")
    
    # Quick GPU detection via GPUtil if available
    print("\n🎮 GPU Detection:")
    try:
        import GPUtil
        gpus = GPUtil.getGPUs()
        if gpus:
            for i, gpu in enumerate(gpus):
                print(f"   GPU {i}: {gpu.name} ({gpu.memoryTotal}MB)")
        else:
            print("   No GPUs detected via GPUtil")
    except ImportError:
        print("   GPUtil not available")
    except Exception as e:
        print(f"   GPUtil error: {e}")
    
    print("\n" + "=" * 60)
    print("TEST SUMMARY:")
    print("✅ = Good    ⚠️  = Warning    ❌ = Error")
    print("\nIf you see 'Vulkan backend detected', your setup is correct!")
    print("If not, rebuild with: CMAKE_ARGS='-DGGML_VULKAN=ON' pip install llama-cpp-python --force-reinstall --no-cache-dir")
    print("=" * 60)
    
    return True

if __name__ == "__main__":
    test_vulkan_setup()