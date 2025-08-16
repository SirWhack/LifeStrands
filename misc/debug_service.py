import sys
import os
sys.path.append('services/model-service/src')

import asyncio
import logging

# Set up detailed logging
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

async def test_model_manager():
    print("=== Testing ModelManager Initialization ===")
    
    try:
        from model_manager import ModelManager
        print("[OK] ModelManager imported")
        
        manager = ModelManager()
        print("[OK] ModelManager created")
        print(f"Platform detected: {'Windows' if manager.is_windows else 'Linux'}")
        print(f"Models path: {manager.models_path}")
        
        # Test each initialization step
        print("\n=== Testing GPU Detection ===")
        if manager.is_windows:
            await manager._check_windows_gpu()
            print("[OK] Windows GPU check completed")
        else:
            await manager._check_linux_gpu()
            print("[OK] Linux GPU check completed")
            
        print("\n=== Testing Memory Monitor ===")
        try:
            from memory_monitor import MemoryMonitor
            monitor = MemoryMonitor()
            gpu_stats = await monitor.get_gpu_stats()
            print(f"GPU stats: {gpu_stats}")
        except Exception as e:
            print(f"[ERROR] Memory monitor failed: {e}")
        
        print("\n=== Testing Full Initialization ===")
        await manager.initialize()
        print("[SUCCESS] ModelManager initialized successfully!")
        
        status = await manager.get_model_status()
        print(f"Final status: {status}")
        
    except Exception as e:
        print(f"[ERROR] Test failed: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test_model_manager())