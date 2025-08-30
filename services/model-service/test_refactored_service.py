#!/usr/bin/env python3
"""
Test script for the refactored Model Service architecture.
This script validates the new components and their integration.
"""

import asyncio
import logging
import sys
import time
from typing import Dict, Any

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

async def test_request_distributor():
    """Test the RequestDistributor with circuit breakers"""
    logger.info("=== Testing RequestDistributor ===")
    
    try:
        from src.request_distributor import RequestDistributor, ServiceType, CircuitBreaker
        
        # Test circuit breaker
        cb = CircuitBreaker("test", failure_threshold=2, recovery_timeout=1, success_threshold=1)
        
        # Test normal operation
        assert cb.can_proceed() == True, "Circuit breaker should allow requests initially"
        cb.record_success()
        assert cb.can_proceed() == True, "Circuit breaker should stay closed after success"
        
        # Test failure handling
        cb.record_failure()
        assert cb.can_proceed() == True, "Circuit breaker should stay closed after single failure"
        cb.record_failure()
        assert cb.can_proceed() == False, "Circuit breaker should open after threshold failures"
        
        logger.info("✅ RequestDistributor tests passed")
        return True
        
    except Exception as e:
        logger.error(f"❌ RequestDistributor test failed: {e}")
        return False

async def test_intelligent_queue_manager():
    """Test the IntelligentQueueManager components"""
    logger.info("=== Testing IntelligentQueueManager ===")
    
    try:
        from src.intelligent_queue_manager import IntelligentQueueManager, DemandPredictor
        from src.request_distributor import ServiceType
        
        # Test demand predictor
        predictor = DemandPredictor()
        
        # Record some requests
        current_time = time.time()
        predictor.record_request(ServiceType.CHAT, current_time - 10)
        predictor.record_request(ServiceType.CHAT, current_time - 5)
        predictor.record_request(ServiceType.SUMMARY, current_time - 3)
        
        # Test prediction
        pattern = predictor.get_demand_pattern()
        assert isinstance(pattern, dict), "Demand pattern should be a dictionary"
        
        prediction = predictor.predict_next_model_need()
        # Should predict chat model as it's most frequent
        assert prediction == "chat", f"Expected 'chat', got '{prediction}'"
        
        logger.info("✅ IntelligentQueueManager tests passed")
        return True
        
    except Exception as e:
        logger.error(f"❌ IntelligentQueueManager test failed: {e}")
        return False

async def test_enhanced_model_pools():
    """Test the enhanced model pools"""
    logger.info("=== Testing EnhancedModelPools ===")
    
    try:
        from src.enhanced_model_pools import GenerationPool, EmbeddingPool, PoolState
        
        # Mock memory monitor
        class MockMemoryMonitor:
            def __init__(self):
                self.model_configs = {
                    "chat": {
                        "path": "dummy_path.gguf",
                        "n_ctx": 8192,
                        "n_gpu_layers": -1
                    }
                }
            
            async def get_current_vram_usage(self):
                return 5.0  # GB
            
            async def predict_model_size(self, model_type):
                return 15.0  # GB
            
            async def get_total_vram(self):
                return 24.0  # GB
            
            async def get_gpu_stats(self):
                return {"gpu_memory_used_gb": 5.0}
        
        # Test pool initialization
        config = {"safety_margin_gb": 1.0}
        memory_monitor = MockMemoryMonitor()
        
        generation_pool = GenerationPool(config, memory_monitor)
        assert generation_pool.state == PoolState.INITIALIZING
        
        embedding_pool = EmbeddingPool(config, memory_monitor)
        assert embedding_pool.state == PoolState.INITIALIZING
        
        logger.info("✅ EnhancedModelPools tests passed")
        return True
        
    except Exception as e:
        logger.error(f"❌ EnhancedModelPools test failed: {e}")
        return False

async def test_llama_wrapper_embeddings():
    """Test the new embedding functionality in LlamaWrapper"""
    logger.info("=== Testing LlamaWrapper Embeddings ===")
    
    try:
        from src.llama_wrapper import LlamaWrapper
        
        wrapper = LlamaWrapper()
        
        # Test embedding generation with no model loaded (should use fallback)
        texts = ["Hello world", "Test text", "Another example"]
        embeddings = await wrapper.generate_embeddings(texts)
        
        assert isinstance(embeddings, list), "Embeddings should be a list"
        assert len(embeddings) == len(texts), "Should have one embedding per text"
        assert all(isinstance(emb, list) for emb in embeddings), "Each embedding should be a list"
        assert all(len(emb) == 384 for emb in embeddings), "Fallback embeddings should be 384-dimensional"
        
        logger.info("✅ LlamaWrapper embeddings test passed")
        return True
        
    except Exception as e:
        logger.error(f"❌ LlamaWrapper embeddings test failed: {e}")
        return False

async def test_integration():
    """Test integration between components"""
    logger.info("=== Testing Component Integration ===")
    
    try:
        # Mock model pools
        class MockGenerationPool:
            def __init__(self):
                self.current_model_type = "chat"
            
            def get_current_model_type(self):
                return self.current_model_type
            
            async def generate_response(self, model_type, prompt, params):
                # Mock async generator
                for token in ["Hello", " ", "world", "!"]:
                    yield token
            
            async def preload_model(self, model_type):
                pass
            
            async def health_check(self):
                return {"healthy": True}
        
        class MockEmbeddingPool:
            async def generate_embeddings(self, texts):
                return [[0.0] * 384 for _ in texts]
            
            async def health_check(self):
                return {"healthy": True}
        
        model_pools = {
            "generation": MockGenerationPool(),
            "embedding": MockEmbeddingPool()
        }
        
        # Test queue manager with model pools
        from src.intelligent_queue_manager import IntelligentQueueManager
        
        config = {"max_queue_size": 10, "batch_timeout": 0.1, "max_batch_size": 5}
        queue_manager = IntelligentQueueManager(model_pools, config)
        
        # Test basic functionality without starting background tasks
        status = await queue_manager.get_queue_status()
        assert isinstance(status, dict), "Queue status should be a dictionary"
        
        logger.info("✅ Component integration tests passed")
        return True
        
    except Exception as e:
        logger.error(f"❌ Component integration test failed: {e}")
        return False

async def run_all_tests():
    """Run all tests and report results"""
    logger.info("🚀 Starting Model Service Refactor Tests")
    
    tests = [
        ("RequestDistributor", test_request_distributor),
        ("IntelligentQueueManager", test_intelligent_queue_manager),
        ("EnhancedModelPools", test_enhanced_model_pools),
        ("LlamaWrapper Embeddings", test_llama_wrapper_embeddings),
        ("Component Integration", test_integration)
    ]
    
    results = {}
    
    for test_name, test_func in tests:
        logger.info(f"\n--- Running {test_name} tests ---")
        try:
            result = await test_func()
            results[test_name] = result
        except Exception as e:
            logger.error(f"❌ {test_name} test failed with exception: {e}")
            results[test_name] = False
    
    # Report summary
    logger.info("\n" + "="*50)
    logger.info("📊 TEST RESULTS SUMMARY")
    logger.info("="*50)
    
    passed = 0
    total = len(tests)
    
    for test_name, result in results.items():
        status = "✅ PASSED" if result else "❌ FAILED"
        logger.info(f"{test_name:25} | {status}")
        if result:
            passed += 1
    
    logger.info("="*50)
    logger.info(f"Total: {passed}/{total} tests passed")
    
    if passed == total:
        logger.info("🎉 All tests passed! Refactor is ready for deployment.")
        return True
    else:
        logger.warning(f"⚠️  {total - passed} tests failed. Review issues before deployment.")
        return False

if __name__ == "__main__":
    # Run tests
    success = asyncio.run(run_all_tests())
    sys.exit(0 if success else 1)