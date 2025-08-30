from typing import Dict, Any, Optional, AsyncGenerator, List
import asyncio
from dataclasses import dataclass
from enum import Enum
import time
import logging
import gc

logger = logging.getLogger(__name__)

class PoolState(Enum):
    INITIALIZING = "initializing"
    READY = "ready"
    SCALING = "scaling"
    DEGRADED = "degraded"
    ERROR = "error"

@dataclass
class ModelInstance:
    instance_id: str
    model_type: str
    wrapper: Any
    state: str
    last_used: float
    requests_processed: int = 0
    avg_processing_time: float = 0.0
    vram_usage_gb: float = 0.0

class GenerationPool:
    """Manages chat and summary model instances with hot-swapping capabilities"""
    
    def __init__(self, config: Dict[str, Any], memory_monitor, model_manager=None):
        self.config = config
        self.memory_monitor = memory_monitor
        self.model_manager = model_manager  # Use provided model_manager instance
        self.state = PoolState.INITIALIZING
        
        # Model management
        self.current_instance: Optional[ModelInstance] = None
        self.current_model_type: Optional[str] = None
        self.preloading_model: Optional[str] = None
        self.preloaded_instance: Optional[ModelInstance] = None
        
        # Concurrency control
        self.generation_lock = asyncio.Lock()
        self.swap_lock = asyncio.Lock()
        
        # Performance tracking
        self.metrics = {
            "total_requests": 0,
            "model_swaps": 0,
            "avg_response_time": 0.0,
            "current_vram_usage": 0.0,
            "overlap_swaps": 0,
            "sequential_swaps": 0
        }
        
        # Configuration
        self.safety_margin_gb = config.get("safety_margin_gb", 1.0)

    async def initialize(self, default_model: str = "chat") -> bool:
        """Initialize pool with default model"""
        try:
            self.state = PoolState.INITIALIZING
            logger.info(f"Initializing GenerationPool with default model: {default_model}")
            
            instance = await self._create_model_instance(default_model)
            if instance:
                self.current_instance = instance
                self.current_model_type = default_model
                self.state = PoolState.READY
                logger.info(f"GenerationPool initialized successfully")
                return True
            else:
                self.state = PoolState.ERROR
                logger.error(f"Failed to initialize GenerationPool")
                return False
                
        except Exception as e:
            self.state = PoolState.ERROR
            logger.error(f"Error initializing GenerationPool: {e}")
            raise e

    async def generate_response(
        self,
        model_type: str,
        prompt: str,
        params: Dict[str, Any] = None
    ) -> AsyncGenerator[str, None]:
        """Generate response, switching models if needed"""
        
        # Ensure correct model is loaded
        if model_type != self.current_model_type:
            await self._ensure_model_loaded(model_type)
        
        # Acquire generation lock
        async with self.generation_lock:
            if not self.current_instance:
                raise Exception("No model instance available")
            
            start_time = time.time()
            self.metrics["total_requests"] += 1
            
            try:
                # Generate response using current instance
                async for token in self.current_instance.wrapper.generate_tokens(prompt, **(params or {})):
                    yield token
                
                # Update metrics
                processing_time = time.time() - start_time
                self._update_instance_metrics(self.current_instance, processing_time)
                self._update_avg_response_time(processing_time)
                
            except Exception as e:
                logger.error(f"Generation error: {e}")
                raise e

    async def _ensure_model_loaded(self, model_type: str):
        """Ensure the specified model is loaded"""
        async with self.swap_lock:
            if self.current_model_type == model_type:
                return  # Already loaded
            
            logger.info(f"Model swap required: {self.current_model_type} -> {model_type}")
            
            # Check if we have this model preloaded
            if (self.preloaded_instance and 
                self.preloaded_instance.model_type == model_type):
                await self._use_preloaded_model()
                return
            
            # Check if we can fit both models temporarily for smooth swap
            can_overlap = await self._can_overlap_models(model_type)
            
            if can_overlap:
                await self._overlapped_model_swap(model_type)
                self.metrics["overlap_swaps"] += 1
            else:
                await self._sequential_model_swap(model_type)
                self.metrics["sequential_swaps"] += 1

    async def _use_preloaded_model(self):
        """Switch to preloaded model instantly"""
        logger.info(f"Using preloaded model: {self.preloaded_instance.model_type}")
        
        # Cleanup old instance
        old_instance = self.current_instance
        
        # Atomic swap
        self.current_instance = self.preloaded_instance
        self.current_model_type = self.preloaded_instance.model_type
        self.preloaded_instance = None
        self.preloading_model = None
        
        # Cleanup old instance in background
        if old_instance:
            asyncio.create_task(self._cleanup_instance(old_instance))
        
        self.metrics["model_swaps"] += 1

    async def _overlapped_model_swap(self, target_model: str):
        """Load new model while keeping current one running"""
        logger.info(f"Starting overlapped model swap to: {target_model}")
        
        # Start loading new model in background
        new_instance_task = asyncio.create_task(
            self._create_model_instance(target_model)
        )
        
        # Continue serving requests with current model while new model loads
        new_instance = await new_instance_task
        
        if new_instance:
            # Atomic swap
            old_instance = self.current_instance
            self.current_instance = new_instance
            self.current_model_type = target_model
            
            # Cleanup old instance in background
            if old_instance:
                asyncio.create_task(self._cleanup_instance(old_instance))
            
            self.metrics["model_swaps"] += 1
            logger.info(f"Overlapped model swap completed: {target_model}")
        else:
            raise Exception(f"Failed to load model: {target_model}")

    async def _sequential_model_swap(self, target_model: str):
        """Traditional unload-then-load swap"""
        logger.info(f"Starting sequential model swap to: {target_model}")
        
        # Unload current model
        if self.current_instance:
            await self._cleanup_instance(self.current_instance)
            self.current_instance = None
            self.current_model_type = None
        
        # Load new model
        new_instance = await self._create_model_instance(target_model)
        if new_instance:
            self.current_instance = new_instance
            self.current_model_type = target_model
            self.metrics["model_swaps"] += 1
            logger.info(f"Sequential model swap completed: {target_model}")
        else:
            raise Exception(f"Failed to load model: {target_model}")

    async def _can_overlap_models(self, target_model: str) -> bool:
        """Check if we have enough VRAM to temporarily run both models"""
        try:
            current_usage = await self.memory_monitor.get_current_vram_usage()
            target_model_size = await self.memory_monitor.predict_model_size(target_model)
            total_vram = await self.memory_monitor.get_total_vram()
            
            # Calculate if we can fit both models plus safety margin
            required_vram = current_usage + target_model_size + self.safety_margin_gb
            can_overlap = required_vram <= total_vram
            
            logger.info(f"VRAM overlap check: current={current_usage:.1f}GB, "
                       f"target={target_model_size:.1f}GB, "
                       f"total={total_vram:.1f}GB, "
                       f"required={required_vram:.1f}GB, "
                       f"can_overlap={can_overlap}")
            
            return can_overlap
            
        except Exception as e:
            logger.warning(f"Error checking VRAM overlap capability: {e}")
            return False  # Default to safe sequential swap

    async def _create_model_instance(self, model_type: str) -> Optional[ModelInstance]:
        """Create a new model instance"""
        try:
            logger.info(f"Creating model instance: {model_type}")
            
            # Import here to avoid circular dependencies
            from .llama_wrapper import LlamaWrapper
            
            # Create a dedicated wrapper for this instance
            wrapper = LlamaWrapper()
            
            # Get model configuration from provided ModelManager instance
            if self.model_manager and hasattr(self.model_manager, 'model_configs'):
                logger.info(f"Using provided ModelManager for {model_type} config")
                model_config = self.model_manager.model_configs.get(model_type)
                if model_config:
                    logger.info(f"Found config for {model_type}: {model_config.get('path', 'NO_PATH')}")
            else:
                # Fallback: create new ModelManager instance
                logger.warning(f"Falling back to new ModelManager instance for {model_type}")
                logger.warning(f"model_manager exists: {self.model_manager is not None}")
                logger.warning(f"has model_configs: {hasattr(self.model_manager, 'model_configs') if self.model_manager else False}")
                try:
                    from .model_manager import ModelManager
                    temp_manager = ModelManager()
                    model_config = temp_manager.model_configs.get(model_type)
                    if model_config:
                        logger.warning(f"Fallback config for {model_type}: {model_config.get('path', 'NO_PATH')}")
                except Exception as e:
                    logger.error(f"Could not access ModelManager: {e}")
                    model_config = None
            
            if not model_config:
                raise Exception(f"No configuration for model: {model_type}")
            
            # Load model directly using wrapper
            model = wrapper.load_model(model_config["path"], model_config)
            
            if not model:
                raise Exception(f"Failed to load model: {model_type}")
            
            # Create instance wrapper
            instance = ModelInstance(
                instance_id=f"{model_type}_{int(time.time())}",
                model_type=model_type,
                wrapper=wrapper,
                state="ready",
                last_used=time.time(),
                vram_usage_gb=await self._get_model_vram_usage()
            )
            
            logger.info(f"Model instance created successfully: {model_type}")
            return instance
            
        except Exception as e:
            logger.error(f"Failed to create model instance {model_type}: {e}")
            return None

    async def _cleanup_instance(self, instance: ModelInstance):
        """Cleanup model instance and free VRAM"""
        try:
            logger.info(f"Cleaning up model instance: {instance.model_type}")
            
            if hasattr(instance.wrapper, 'unload'):
                instance.wrapper.unload()
            
            # Force garbage collection
            gc.collect()
            
            logger.info(f"Model instance cleaned up: {instance.model_type}")
            
        except Exception as e:
            logger.error(f"Error cleaning up instance {instance.instance_id}: {e}")

    async def preload_model(self, model_type: str):
        """Preload model if resources allow"""
        try:
            if model_type == self.current_model_type:
                return  # Already loaded
            
            if self.preloading_model == model_type:
                return  # Already preloading
            
            if await self._can_overlap_models(model_type):
                logger.info(f"Starting background preload: {model_type}")
                self.preloading_model = model_type
                # Start preloading in background
                asyncio.create_task(self._background_preload(model_type))
            else:
                logger.info(f"Cannot preload {model_type}: insufficient VRAM")
                
        except Exception as e:
            logger.error(f"Error preloading model {model_type}: {e}")

    async def _background_preload(self, model_type: str):
        """Background task to preload model"""
        try:
            logger.info(f"Background preloading: {model_type}")
            preloaded_instance = await self._create_model_instance(model_type)
            
            if preloaded_instance:
                # Store preloaded instance for quick swap
                self.preloaded_instance = preloaded_instance
                logger.info(f"Model preloaded successfully: {model_type}")
            else:
                logger.warning(f"Failed to preload model: {model_type}")
                
        except Exception as e:
            logger.error(f"Error in background preload of {model_type}: {e}")
        finally:
            self.preloading_model = None

    def get_current_model_type(self) -> Optional[str]:
        """Get currently loaded model type"""
        return self.current_model_type

    async def _get_model_vram_usage(self) -> float:
        """Get current model's VRAM usage"""
        try:
            stats = await self.memory_monitor.get_gpu_stats()
            return stats.get("gpu_memory_used_gb", 0.0)
        except Exception as e:
            logger.warning(f"Error getting VRAM usage: {e}")
            return 0.0

    def _update_instance_metrics(self, instance: ModelInstance, processing_time: float):
        """Update performance metrics for instance"""
        instance.requests_processed += 1
        instance.last_used = time.time()
        
        # Update rolling average
        if instance.avg_processing_time == 0:
            instance.avg_processing_time = processing_time
        else:
            instance.avg_processing_time = (
                instance.avg_processing_time * 0.9 + processing_time * 0.1
            )
    
    def _update_avg_response_time(self, processing_time: float):
        """Update overall average response time"""
        if self.metrics["avg_response_time"] == 0:
            self.metrics["avg_response_time"] = processing_time
        else:
            self.metrics["avg_response_time"] = (
                self.metrics["avg_response_time"] * 0.95 + processing_time * 0.05
            )

    async def get_pool_status(self) -> Dict[str, Any]:
        """Get detailed pool status"""
        current_vram = await self._get_model_vram_usage()
        
        return {
            "state": self.state.value,
            "current_model": self.current_model_type,
            "preloading_model": self.preloading_model,
            "preloaded_available": self.preloaded_instance is not None,
            "metrics": {
                **self.metrics,
                "current_vram_usage": current_vram
            },
            "current_instance": {
                "id": self.current_instance.instance_id if self.current_instance else None,
                "requests_processed": self.current_instance.requests_processed if self.current_instance else 0,
                "avg_processing_time": self.current_instance.avg_processing_time if self.current_instance else 0,
                "last_used": self.current_instance.last_used if self.current_instance else 0
            }
        }

class EmbeddingPool:
    """Manages embedding model instances - always available"""
    
    def __init__(self, config: Dict[str, Any], memory_monitor, model_manager=None):
        self.config = config
        self.memory_monitor = memory_monitor
        self.model_manager = model_manager  # Use provided model_manager instance
        self.instance: Optional[ModelInstance] = None
        self.state = PoolState.INITIALIZING
        
        # Performance tracking
        self.metrics = {
            "total_requests": 0,
            "total_texts_processed": 0,
            "avg_batch_size": 0.0,
            "avg_processing_time": 0.0
        }

    async def initialize(self) -> bool:
        """Initialize embedding pool"""
        try:
            self.state = PoolState.INITIALIZING
            logger.info("Initializing EmbeddingPool")
            
            instance = await self._create_embedding_instance()
            if instance:
                self.instance = instance
                self.state = PoolState.READY
                logger.info("EmbeddingPool initialized successfully")
                return True
            else:
                self.state = PoolState.ERROR
                logger.error("Failed to initialize EmbeddingPool")
                return False
                
        except Exception as e:
            self.state = PoolState.ERROR
            logger.error(f"Error initializing EmbeddingPool: {e}")
            raise e

    async def generate_embeddings(self, texts: List[str]) -> List[List[float]]:
        """Generate embeddings for list of texts"""
        
        if not self.instance:
            raise Exception("Embedding model not initialized")
        
        try:
            start_time = time.time()
            
            self.metrics["total_requests"] += 1
            self.metrics["total_texts_processed"] += len(texts)
            
            # Generate embeddings using the model
            embeddings = await self.instance.wrapper.generate_embeddings(texts)
            
            processing_time = time.time() - start_time
            
            # Update average batch size
            if self.metrics["total_requests"] == 1:
                self.metrics["avg_batch_size"] = len(texts)
                self.metrics["avg_processing_time"] = processing_time
            else:
                self.metrics["avg_batch_size"] = (
                    self.metrics["avg_batch_size"] * 0.9 + len(texts) * 0.1
                )
                self.metrics["avg_processing_time"] = (
                    self.metrics["avg_processing_time"] * 0.9 + processing_time * 0.1
                )
            
            return embeddings
            
        except Exception as e:
            logger.error(f"Embedding generation error: {e}")
            raise e

    async def _create_embedding_instance(self) -> Optional[ModelInstance]:
        """Create embedding model instance"""
        try:
            logger.info("Creating embedding model instance")
            
            # Try to get existing embedding manager from provided ModelManager
            if self.model_manager and hasattr(self.model_manager, 'embedding_manager') and self.model_manager.embedding_manager:
                embedding_manager = self.model_manager.embedding_manager
                
                instance = ModelInstance(
                    instance_id=f"embedding_{int(time.time())}",
                    model_type="embedding",
                    wrapper=embedding_manager,
                    state="ready",
                    last_used=time.time(),
                    vram_usage_gb=1.0  # Embedding models are typically small
                )
                
                logger.info("Embedding model instance created using existing manager")
                return instance
            
            # Fallback: try to create new ModelManager instance
            try:
                from .model_manager import ModelManager
                temp_manager = ModelManager()
                
                # Check if ModelManager has an embedding manager
                if hasattr(temp_manager, 'embedding_manager') and temp_manager.embedding_manager:
                    embedding_manager = temp_manager.embedding_manager
                    
                    instance = ModelInstance(
                        instance_id=f"embedding_{int(time.time())}",
                        model_type="embedding",
                        wrapper=embedding_manager,
                        state="ready",
                        last_used=time.time(),
                        vram_usage_gb=1.0  # Embedding models are typically small
                    )
                    
                    logger.info("Embedding model instance created using existing manager")
                    return instance
            except Exception as e:
                logger.debug(f"Could not access ModelManager embedding manager: {e}")
            
            # Fallback: try to create a new wrapper for embeddings
            try:
                from .llama_wrapper import LlamaWrapper
                
                wrapper = LlamaWrapper()
                
                # Create a dummy instance that can handle embedding requests
                # This will use the fallback embedding generation in LlamaWrapper
                instance = ModelInstance(
                    instance_id=f"embedding_{int(time.time())}",
                    model_type="embedding",
                    wrapper=wrapper,
                    state="ready",
                    last_used=time.time(),
                    vram_usage_gb=0.5  # Minimal VRAM for fallback
                )
                
                logger.info("Embedding model instance created with fallback wrapper")
                return instance
                
            except Exception as e:
                logger.warning(f"Could not create embedding wrapper: {e}")
                return None
            
        except Exception as e:
            logger.error(f"Failed to create embedding instance: {e}")
            return None

    async def get_pool_status(self) -> Dict[str, Any]:
        """Get embedding pool status"""
        return {
            "state": self.state.value,
            "metrics": self.metrics,
            "instance_available": self.instance is not None,
            "instance_info": {
                "id": self.instance.instance_id if self.instance else None,
                "last_used": self.instance.last_used if self.instance else 0
            }
        }