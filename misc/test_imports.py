import sys
sys.path.append('services/model-service/src')

print('Testing imports...')
try:
    from llama_wrapper import LlamaWrapper
    print('[OK] LlamaWrapper imported')
except Exception as e:
    print(f'[ERROR] LlamaWrapper import failed: {e}')

try:
    from model_manager import ModelManager
    print('[OK] ModelManager imported')
except Exception as e:
    print(f'[ERROR] ModelManager import failed: {e}')

try:
    from memory_monitor import MemoryMonitor
    print('[OK] MemoryMonitor imported')
except Exception as e:
    print(f'[ERROR] MemoryMonitor import failed: {e}')

print('Testing basic functionality...')
try:
    import asyncio
    async def test():
        manager = ModelManager()
        print('[OK] ModelManager created')

        # Test GPU detection specifically
        print('Testing GPU detection...')
        await manager._check_windows_gpu()
        print('[OK] GPU check completed')

        print('Testing memory monitor...')
        monitor = MemoryMonitor()
        gpu_stats = await monitor.get_gpu_stats()
        print(f'GPU stats: {gpu_stats}')

    asyncio.run(test())
except Exception as e:
    print(f'[ERROR] Functionality test failed: {e}')
    import traceback
    traceback.print_exc()