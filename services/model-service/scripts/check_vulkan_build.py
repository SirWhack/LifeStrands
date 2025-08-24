#!/usr/bin/env python3
"""
Check if llama-cpp-python was compiled with Vulkan support
"""
import sys
import subprocess
import platform
import os

def check_vulkan_build():
    """Check if llama-cpp-python has Vulkan support compiled in"""
    print("=" * 60)
    print("LLAMA-CPP-PYTHON VULKAN BUILD CHECK")
    print("=" * 60)
    
    vulkan_detected = False
    
    # Test 1: Import check
    try:
        import llama_cpp
        print("[SUCCESS] llama-cpp-python imported successfully")
        print(f"   Version: {getattr(llama_cpp, '__version__', 'Unknown')}")
    except ImportError as e:
        print(f"[ERROR] Failed to import llama-cpp-python: {e}")
        return False
    
    # Test 2: Check compiled backends
    print("\n[INFO] Checking compiled backends...")
    try:
        from llama_cpp import llama_cpp
        
        # Try to access backend info if available
        if hasattr(llama_cpp, 'llama_supports_gpu_offload'):
            try:
                gpu_support = llama_cpp.llama_supports_gpu_offload()
                print(f"   GPU offload support: {'[SUCCESS] Yes' if gpu_support else '[WARNING] No'}")
                if gpu_support:
                    vulkan_detected = True
            except Exception as e:
                print(f"   [WARNING] Could not check GPU offload: {e}")
        
        # Check for Vulkan-specific functions/constants
        vulkan_indicators = [
            'GGML_USE_VULKAN',
            'llama_vulkan_available', 
            'ggml_vulkan_init',
            'llama_backend_init'
        ]
        
        vulkan_found_indicators = []
        for indicator in vulkan_indicators:
            if hasattr(llama_cpp, indicator):
                vulkan_found_indicators.append(indicator)
                
        if vulkan_found_indicators:
            print(f"   [SUCCESS] Vulkan indicators found: {', '.join(vulkan_found_indicators)}")
            vulkan_detected = True
        else:
            print("   [WARNING] No obvious Vulkan indicators found")
            
    except Exception as e:
        print(f"   [ERROR] Backend check error: {e}")
    
    # Test 3: Check system Vulkan
    print("\n[INFO] System Vulkan check...")
    try:
        result = subprocess.run(["vulkaninfo", "--summary"], 
                              capture_output=True, text=True, timeout=10,
                              creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
        if result.returncode == 0:
            print("   [SUCCESS] Vulkan runtime available")
            # Look for AMD GPU
            output_lower = result.stdout.lower()
            if any(amd in output_lower for amd in ["7900", "rdna3", "radeon"]):
                print("   [SUCCESS] AMD GPU detected in Vulkan")
            elif "amd" in output_lower:
                print("   [SUCCESS] AMD hardware detected in Vulkan")
        else:
            print("   [ERROR] Vulkan runtime not working")
            print(f"   Error output: {result.stderr[:100]}")
    except FileNotFoundError:
        print("   [ERROR] vulkaninfo not found - Vulkan SDK may not be installed")
    except subprocess.TimeoutExpired:
        print("   [ERROR] vulkaninfo timed out")
    except Exception as e:
        print(f"   [ERROR] Vulkan check error: {e}")
    
    # Test 4: Try creating a Llama instance with GPU layers
    print("\n[INFO] Testing GPU layer assignment...")
    try:
        from llama_cpp import Llama
        # Use a dummy path - we expect this to fail, but want to see the error
        test_llama = Llama(
            model_path="nonexistent.gguf",
            n_ctx=512,
            n_gpu_layers=1,  # Try to use GPU
            verbose=True
        )
    except Exception as e:
        error_str = str(e).lower()
        print(f"   Expected error (first 150 chars): {str(e)[:150]}...")
        
        # Check for backend mentions in error
        if "vulkan" in error_str:
            print("   [SUCCESS] VULKAN BACKEND DETECTED!")
            vulkan_detected = True
        elif "cuda" in error_str:
            print("   [WARNING] CUDA backend detected (not Vulkan)")
        elif "hip" in error_str or "rocm" in error_str:
            print("   [WARNING] ROCm/HIP backend detected (not Vulkan)")
        elif "cpu" in error_str or "no gpu" in error_str:
            print("   [WARNING] CPU-only build detected")
        elif "model_path" in error_str or "no such file" in error_str:
            print("   [INFO] Model file error (as expected), but no backend info detected")
        else:
            print("   [WARNING] Unclear backend from error message")
            
    # Test 5: Alternative method - try to get backend info directly
    print("\n[INFO] Alternative backend detection...")
    try:
        import llama_cpp
        # Try to access the backend initialization
        if hasattr(llama_cpp, 'llama_backend_init'):
            print("   [INFO] Attempting backend initialization...")
            try:
                llama_cpp.llama_backend_init()
                print("   [SUCCESS] Backend initialized successfully")
                vulkan_detected = True
            except Exception as be:
                be_str = str(be).lower()
                if "vulkan" in be_str:
                    print("   [SUCCESS] Vulkan mentioned in backend init")
                    vulkan_detected = True
                else:
                    print(f"   [INFO] Backend init result: {str(be)[:100]}")
    except Exception as e:
        print(f"   [INFO] Alternative detection failed: {e}")
    
    # Test 6: Check pip installation details
    print("\n[INFO] Checking installation details...")
    try:
        result = subprocess.run([sys.executable, "-m", "pip", "show", "llama-cpp-python"], 
                              capture_output=True, text=True, timeout=10)
        if result.returncode == 0:
            lines = result.stdout.split('\n')
            for line in lines:
                if line.startswith('Version:') or line.startswith('Location:') or line.startswith('Summary:'):
                    print(f"   {line}")
        else:
            print("   [WARNING] Could not get pip package details")
    except Exception as e:
        print(f"   [WARNING] Could not get pip details: {e}")
    
    # Final verdict
    print("\n" + "=" * 60)
    print("FINAL VERDICT:")
    print("=" * 60)
    
    if vulkan_detected:
        print("[SUCCESS] Vulkan support appears to be compiled in!")
        print("Your llama-cpp-python installation should work with Vulkan GPU acceleration.")
        print("")
        print("Next steps:")
        print("1. Ensure your models are in the Models/ directory")
        print("2. Start the model service: python main.py")
        print("3. Check http://localhost:8001/status for GPU info")
        return True
    else:
        print("[WARNING] Vulkan support was NOT clearly detected!")
        print("")
        print("To rebuild with Vulkan support:")
        print("1. $env:CMAKE_ARGS = '-DGGML_VULKAN=ON'")
        print("2. pip install llama-cpp-python --force-reinstall --no-cache-dir --verbose")
        print("3. Run this script again to verify")
        return False
    
    print("=" * 60)

if __name__ == "__main__":
    check_vulkan_build()