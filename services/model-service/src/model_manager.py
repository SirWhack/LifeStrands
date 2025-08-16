import asyncio
import psutil
from typing import AsyncGenerator, Optional, Dict, Any
from enum import Enum
import logging
from contextlib import asynccontextmanager
import gc
import json

logger = logging.getLogger(__name__)

# Optional imports with fallbacks
try:
    import redis.asyncio as redis
    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False
    logger.warning("redis.asyncio not available - continuing without Redis support")
    redis = None

try:
    import GPUtil
    GPUTIL_AVAILABLE = True
except ImportError:
    GPUTIL_AVAILABLE = False
    logger.warning("GPUtil not available - continuing without GPU monitoring")
    GPUtil = None

class ModelState(Enum):
    IDLE = "idle"
    LOADING = "loading"
    LOADED = "loaded"
    GENERATING = "generating"
    UNLOADING = "unloading"
    ERROR = "error"

class ModelManager:
    """Manages GPU model loading, unloading, and hot-swapping"""
    
    def __init__(self):
        self.redis_client: Optional[Any] = None
        self.loaded_models: Dict[str, Any] = {}  # Store multiple loaded models
        self.current_chat_model = None
        self.current_summary_model = None
        self.current_embedding_model = None
        self.current_model = None
        self.current_wrapper = None
        self.current_model_type = None
        self.state: ModelState = ModelState.IDLE
        
        # Platform detection
        import platform
        self.is_windows = platform.system() == "Windows"
        
        # Get model configurations from environment variables
        import os
        from pathlib import Path
        
        # Auto-detect models path based on platform
        if self.is_windows:
            # Windows native mode - look for Models directory relative to project root
            models_path = os.getenv("MODELS_PATH", str(Path(__file__).parent.parent.parent.parent / "Models"))
        else:
            # Docker/Linux mode - use container path
            models_path = os.getenv("MODELS_PATH", "/models")
            
        chat_model = os.getenv("CHAT_MODEL", "Gryphe_Codex-24B-Small-3.2-Q6_K_L.gguf")
        summary_model = os.getenv("SUMMARY_MODEL", "dphn.Dolphin-Mistral-24B-Venice-Edition.Q6_K.gguf")
        embedding_model = os.getenv("EMBEDDING_MODEL", "all-MiniLM-L6-v2.F32.gguf")
        
        self.models_path = Path(models_path)
        logger.info(f"Platform: {'Windows' if self.is_windows else 'Linux/Docker'}")
        logger.info(f"Models path: {self.models_path}")
        
        # Model configurations with Windows-optimized settings
        if self.is_windows:
            # Windows ROCm optimizations
            self.model_configs = {
                "chat": {
                    "path": str(self.models_path / chat_model),
                    "type": "chat",
                    "n_ctx": int(os.getenv("CHAT_CONTEXT_SIZE", "8192")),
                    "n_gpu_layers": -1,
                    "n_batch": 1024,
                    "use_mmap": False,
                    "use_mlock": False,
                    "f16_kv": True,
                    "verbose": True
                },
                "summary": {
                    "path": str(self.models_path / summary_model),
                    "type": "chat",
                    "n_ctx": int(os.getenv("SUMMARY_CONTEXT_SIZE", "4096")),
                    "n_gpu_layers": -1,
                    "n_batch": 512,
                    "use_mmap": True,
                    "use_mlock": False,
                    "f16_kv": True,
                    "verbose": True
                },
                "embedding": {
                    "path": str(self.models_path / embedding_model),
                    "type": "embedding",
                    "n_ctx": 512,
                    "n_gpu_layers": -1,
                    "embedding": True,
                    "verbose": False
                }
            }
        else:
            # Docker/Linux configurations
            self.model_configs = {
                "chat": {
                    "path": f"{models_path}/{chat_model}",
                    "type": "chat",
                    "n_ctx": int(os.getenv("CHAT_CONTEXT_SIZE", "8192")),
                    "n_gpu_layers": -1
                },
                "summary": {
                    "path": f"{models_path}/{summary_model}", 
                    "type": "chat",
                    "n_ctx": int(os.getenv("SUMMARY_CONTEXT_SIZE", "4096")),
                    "n_gpu_layers": -1
                },
                "embedding": {
                    "path": f"{models_path}/{embedding_model}",
                    "type": "embedding",
                    "n_ctx": 512,
                    "n_gpu_layers": -1,
                    "embedding": True
                }
            }
        
    async def initialize(self):
        """Initialize Redis connection, check GPU availability"""
        try:
            import os
            
            # Redis connection (optional for Windows native mode)
            if REDIS_AVAILABLE:
                redis_url = os.getenv("REDIS_URL", "redis://localhost:6379")
                try:
                    self.redis_client = redis.from_url(redis_url)
                    await self.redis_client.ping()
                    logger.info("Redis connection established")
                except Exception as e:
                    if self.is_windows:
                        logger.warning(f"Redis not available (Windows native mode): {e}")
                        self.redis_client = None
                    else:
                        raise  # Redis required in Docker mode
            else:
                logger.warning("Redis not available - continuing without Redis support")
                self.redis_client = None
            
            # Platform-specific GPU detection
            if self.is_windows:
                await self._check_windows_gpu()
            else:
                await self._check_linux_gpu()
            
            await self._update_status()
            logger.info("ModelManager initialized successfully")
            
        except Exception as e:
            logger.error(f"Failed to initialize ModelManager: {e}")
            self.state = ModelState.ERROR
            raise
            
    async def load_model(self, model_type: str) -> bool:
        """Hot-swap to specified model (chat/summary)"""
        try:
            if model_type not in self.model_configs:
                raise ValueError(f"Unknown model type: {model_type}")
                
            # If already loaded with same type, return
            if self.current_model_type == model_type and self.state == ModelState.LOADED:
                logger.info(f"Model {model_type} already loaded")
                return True
                
            # Unload current model if different type
            if self.current_model and self.current_model_type != model_type:
                await self.unload_current_model()
                
            self.state = ModelState.LOADING
            await self._update_status()
            
            config = self.model_configs[model_type]
            
            # Check memory requirements
            try:
                from .memory_monitor import MemoryMonitor
            except ImportError:
                from memory_monitor import MemoryMonitor
            monitor = MemoryMonitor()
            if not await monitor.can_load_model(model_type):
                logger.error(f"Insufficient memory for {model_type} model")
                self.state = ModelState.ERROR
                return False
                
            # Load model using llama wrapper
            try:
                from .llama_wrapper import LlamaWrapper
            except ImportError:
                from llama_wrapper import LlamaWrapper
            self.current_wrapper = LlamaWrapper()
            self.current_model = self.current_wrapper.load_model(config["path"], config)
            self.current_model_type = model_type
            self.state = ModelState.LOADED
            
            await self._update_status()
            logger.info(f"Successfully loaded {model_type} model")
            return True
            
        except Exception as e:
            logger.error(f"Failed to load {model_type} model: {e}")
            self.state = ModelState.ERROR
            await self._update_status()
            return False
            
    async def unload_current_model(self):
        """Free VRAM and cleanup current model"""
        try:
            if not self.current_model:
                return
                
            self.state = ModelState.UNLOADING
            await self._update_status()
            
            # Cleanup model and wrapper
            if self.current_wrapper:
                self.current_wrapper.unload()
                self.current_wrapper = None
            self.current_model = None
            self.current_model_type = None
            
            # Force garbage collection
            gc.collect()
            # PyTorch CUDA cache clearing not needed for GGUF models
                
            self.state = ModelState.IDLE
            await self._update_status()
            logger.info("Model unloaded successfully")
            
        except Exception as e:
            logger.error(f"Error unloading model: {e}")
            self.state = ModelState.ERROR
            
    async def generate_stream(self, prompt: str, params: dict) -> AsyncGenerator[str, None]:
        """Stream tokens from current model"""
        if not self.current_model or self.state != ModelState.LOADED:
            raise RuntimeError("No model loaded")
            
        try:
            self.state = ModelState.GENERATING
            await self._update_status()
            
            async for token in self.current_wrapper.generate_tokens(prompt, **params):
                yield token
                
        finally:
            self.state = ModelState.LOADED
            await self._update_status()
            
    async def generate_completion(self, prompt: str, params: dict) -> str:
        """Generate complete response (for summaries)"""
        if not self.current_model or self.state != ModelState.LOADED:
            raise RuntimeError("No model loaded")
            
        try:
            self.state = ModelState.GENERATING
            await self._update_status()
            
            tokens = []
            async for token in self.current_wrapper.generate_tokens(prompt, **params):
                tokens.append(token)
                
            return "".join(tokens)
            
        finally:
            self.state = ModelState.LOADED
            await self._update_status()
            
    async def get_model_status(self) -> dict:
        """Return current model state, type, and memory usage"""
        try:
            base_status = {
                "state": self.state.value,
                "current_model_type": self.current_model_type,
                "current_model": self.current_model is not None,
                "platform": "windows-rocm" if self.is_windows else "linux-docker",
                "models_path": str(self.models_path),
                "available_models": list(self.model_configs.keys()),
                "timestamp": asyncio.get_event_loop().time()
            }
            
            # Add GPU info
            base_status["gpu_info"] = self.get_gpu_info()
            
            # Add memory stats if monitor is available
            try:
                try:
                    from .memory_monitor import MemoryMonitor
                except ImportError:
                    from memory_monitor import MemoryMonitor
                monitor = MemoryMonitor()
                gpu_stats = await monitor.get_gpu_stats()
                base_status["gpu_stats"] = gpu_stats
            except Exception as e:
                logger.debug(f"Memory monitor not available: {e}")
                base_status["gpu_stats"] = {"available": False, "reason": str(e)}
            
            return base_status
        except Exception as e:
            logger.error(f"Error getting status: {e}")
            return {
                "state": self.state.value,
                "current_model_type": self.current_model_type,
                "platform": "windows-rocm" if self.is_windows else "linux-docker",
                "error": str(e)
            }
            
    async def emergency_shutdown(self):
        """Force unload model and cleanup resources"""
        try:
            logger.warning("Emergency shutdown initiated")
            
            if self.current_wrapper:
                self.current_wrapper.unload()
                self.current_wrapper = None
            self.current_model = None
            self.current_model_type = None
                
            gc.collect()
            # PyTorch CUDA operations not needed for GGUF models
                
            self.state = ModelState.IDLE
            await self._update_status()
            logger.info("Emergency shutdown completed")
            
        except Exception as e:
            logger.error(f"Error during emergency shutdown: {e}")
            self.state = ModelState.ERROR
            
    async def _check_windows_gpu(self):
        """Windows-specific GPU detection with ROCm support"""
        try:
            # Check for AMD ROCm GPU - try multiple HIP SDK versions
            import subprocess
            hip_versions = ["6.4", "6.3", "6.2", "6.1", "6.0", "5.7"]
            rocm_found = False
            
            for version in hip_versions:
                hipinfo_path = rf"C:\Program Files\AMD\ROCm\{version}\bin\hipInfo.exe"
                try:
                    result = subprocess.run([hipinfo_path], 
                                          capture_output=True, text=True, timeout=10)
                    if result.returncode == 0:
                        rocm_found = True
                        gpu_output = result.stdout
                        if any(gpu_name in gpu_output for gpu_name in ["7900", "RX 7", "RDNA3"]):
                            logger.info(f"✅ AMD RDNA3 GPU detected with ROCm {version}")
                            logger.info("🔥 All model layers will be offloaded to GPU")
                        else:
                            logger.info(f"✅ AMD GPU detected with ROCm {version}")
                        break
                except FileNotFoundError:
                    continue
                except Exception as e:
                    logger.debug(f"ROCm {version} check failed: {e}")
                    continue
            
            if not rocm_found:
                # Fallback: check if HIP is in PATH
                try:
                    result = subprocess.run(["hipInfo"], 
                                          capture_output=True, text=True, timeout=10)
                    if result.returncode == 0:
                        logger.info("✅ AMD GPU detected with ROCm (via PATH)")
                        rocm_found = True
                except:
                    pass
                    
            if not rocm_found:
                logger.warning("ROCm not found - will use CPU-only inference")
                
        except Exception as e:
            logger.warning(f"GPU detection error: {e}")
            
        # Fallback to GPUtil for additional info
        if GPUTIL_AVAILABLE:
            try:
                gpus = GPUtil.getGPUs()
                if gpus:
                    for i, gpu in enumerate(gpus):
                        logger.info(f"GPU {i}: {gpu.name}, Memory: {gpu.memoryTotal}MB")
                else:
                    logger.warning("No GPUs detected via GPUtil")
            except Exception as e:
                logger.warning(f"GPUtil detection failed: {e}")
        else:
            logger.warning("GPUtil not available - skipping GPU detection")
            
    async def _check_linux_gpu(self):
        """Linux/Docker GPU detection"""
        if GPUTIL_AVAILABLE:
            try:
                gpus = GPUtil.getGPUs()
                if not gpus:
                    logger.warning("No GPUs detected")
                else:
                    logger.info(f"Found {len(gpus)} GPU(s)")
                    for i, gpu in enumerate(gpus):
                        logger.info(f"GPU {i}: {gpu.name}, Memory: {gpu.memoryTotal}MB")
            except Exception as e:
                logger.warning(f"GPU detection failed: {e}")
        else:
            logger.warning("GPUtil not available - skipping GPU detection")
            
    def get_gpu_info(self) -> dict:
        """Get GPU information for status endpoint"""
        if self.is_windows:
            return self._get_windows_gpu_info()
        else:
            return self._get_linux_gpu_info()
            
    def _get_windows_gpu_info(self) -> dict:
        """Windows-specific GPU info with ROCm detection"""
        try:
            import subprocess
            hip_versions = ["6.4", "6.3", "6.2", "6.1", "6.0", "5.7"]
            
            for version in hip_versions:
                hipinfo_path = rf"C:\Program Files\AMD\ROCm\{version}\bin\hipInfo.exe"
                try:
                    result = subprocess.run([hipinfo_path], 
                                          capture_output=True, text=True, timeout=10)
                    if result.returncode == 0:
                        gpu_output = result.stdout
                        if any(gpu_name in gpu_output for gpu_name in ["7900", "RX 7", "RDNA3"]):
                            return {
                                "platform": "windows-rocm",
                                "rocm_available": True,
                                "rocm_version": version,
                                "gpu_detected": "AMD RDNA3 GPU",
                                "output": gpu_output[:300],
                                "gpu_offload": "All layers (-1)"
                            }
                        else:
                            return {
                                "platform": "windows-rocm",
                                "rocm_available": True,
                                "rocm_version": version,
                                "gpu_detected": "AMD GPU found",
                                "output": gpu_output[:300],
                                "gpu_offload": "All layers (-1)"
                            }
                except FileNotFoundError:
                    continue
                except Exception:
                    continue
            
            # Check PATH fallback
            try:
                result = subprocess.run(["hipInfo"], 
                                      capture_output=True, text=True, timeout=10)
                if result.returncode == 0:
                    return {
                        "platform": "windows-rocm",
                        "rocm_available": True,
                        "rocm_version": "PATH",
                        "gpu_detected": "AMD GPU found (via PATH)",
                        "output": result.stdout[:300],
                        "gpu_offload": "All layers (-1)"
                    }
            except:
                pass
                
            return {
                "platform": "windows",
                "rocm_available": False,
                "reason": "ROCm not found in standard paths"
            }
        except Exception as e:
            return {
                "platform": "windows",
                "rocm_available": False,
                "reason": str(e)
            }
            
    def _get_linux_gpu_info(self) -> dict:
        """Linux/Docker GPU info"""
        if GPUTIL_AVAILABLE:
            try:
                gpus = GPUtil.getGPUs()
                if gpus:
                    return {
                        "platform": "linux-docker",
                        "gpu_count": len(gpus),
                        "gpus": [{"name": gpu.name, "memory": f"{gpu.memoryTotal}MB"} for gpu in gpus]
                    }
                else:
                    return {"platform": "linux-docker", "gpu_count": 0, "gpus": []}
            except Exception as e:
                return {"platform": "linux-docker", "error": str(e)}
        else:
            return {"platform": "linux-docker", "error": "GPUtil not available"}
            
    async def monitor_vram(self) -> dict:
        """Real-time VRAM monitoring"""
        try:
            try:
                from .memory_monitor import MemoryMonitor
            except ImportError:
                from memory_monitor import MemoryMonitor
            monitor = MemoryMonitor()
            return await monitor.get_gpu_stats()
        except Exception as e:
            logger.error(f"Error monitoring VRAM: {e}")
            return {"error": str(e)}
            
    async def _update_status(self):
        """Update status in Redis (if available)"""
        if self.redis_client:
            try:
                status = await self.get_model_status()
                await self.redis_client.set(
                    "model_service:status", 
                    json.dumps(status),
                    ex=60
                )
            except Exception as e:
                logger.error(f"Failed to update status in Redis: {e}")
        # In Windows native mode without Redis, just log the status
        elif self.is_windows:
            status = await self.get_model_status()
            logger.debug(f"Status update (no Redis): {status['state']}")
                
    async def load_embedding_model(self) -> bool:
        """Load the embedding model"""
        try:
            if "embedding" in self.loaded_models:
                logger.info("Embedding model already loaded")
                return True
                
            config = self.model_configs["embedding"]
            logger.info(f"Loading embedding model from {config['path']}")
            
            from llama_cpp import Llama
            
            # Load model with embedding=True
            model = Llama(
                model_path=config["path"],
                embedding=True,
                n_ctx=config["n_ctx"],
                n_gpu_layers=config["n_gpu_layers"],
                verbose=False
            )
            
            self.loaded_models["embedding"] = model
            self.current_embedding_model = model
            logger.info("Embedding model loaded successfully")
            return True
            
        except Exception as e:
            logger.error(f"Failed to load embedding model: {e}")
            return False
            
    async def generate_embeddings(self, texts: list[str]) -> list[list[float]]:
        """Generate embeddings for a list of texts"""
        try:
            if not self.current_embedding_model:
                if not await self.load_embedding_model():
                    raise Exception("Failed to load embedding model")
                    
            embeddings = []
            for text in texts:
                # Create embeddings using llama.cpp
                embedding = self.current_embedding_model.create_embedding(text)
                embeddings.append(embedding["data"][0]["embedding"])
                
            logger.info(f"Generated embeddings for {len(texts)} texts")
            return embeddings
            
        except Exception as e:
            logger.error(f"Error generating embeddings: {e}")
            raise
            
    async def get_model_for_task(self, task_type: str) -> Any:
        """Get or load model for specific task"""
        try:
            if task_type == "embedding":
                if not self.current_embedding_model:
                    await self.load_embedding_model()
                return self.current_embedding_model
            elif task_type in ["chat", "summary"]:
                # For now, use the same chat model for both
                # Later you can implement separate models
                if not self.current_chat_model:
                    # Load chat model if needed
                    pass
                return self.current_chat_model
            else:
                raise ValueError(f"Unknown task type: {task_type}")
                
        except Exception as e:
            logger.error(f"Error getting model for task {task_type}: {e}")
            raise