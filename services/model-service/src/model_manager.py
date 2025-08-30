import asyncio
import os
import psutil
from typing import AsyncGenerator, Optional, Dict, Any, List
from enum import Enum
import logging
from contextlib import asynccontextmanager
import gc
import json

logger = logging.getLogger(__name__)

# Import state machine
try:
    from .state_machine import ModelStateMachine, ModelState
except ImportError:
    from state_machine import ModelStateMachine, ModelState

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

# ModelState is now imported from state_machine

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
        
        # Initialize state machine
        self.state_machine = ModelStateMachine()
        
        # Concurrency control
        self._gen_lock = asyncio.Lock()
        self._load_lock = asyncio.Lock()
        
        # Platform detection and backend configuration
        import platform
        self.is_windows = platform.system() == "Windows"
        self.backend = os.getenv("BACKEND", "vulkan" if self.is_windows else "cuda").lower()
        
        logger.info(f"Platform: {'Windows' if self.is_windows else 'Linux/Docker'}, Backend: {self.backend}")
        
        # Get model configurations from environment variables
        from pathlib import Path
        
        # Auto-detect models path based on platform
        if self.is_windows:
            # Windows native mode - look for Models directory relative to project root
            # __file__ = /path/to/Life Strands v2/services/model-service/src/model_manager.py
            # We need to go up 3 levels: src -> model-service -> services -> Life Strands v2
            project_root = Path(__file__).parent.parent.parent.parent.resolve()
            models_path_env = os.getenv("MODELS_PATH")
            logger.info(f"Environment MODELS_PATH: {models_path_env}")
            models_path = os.getenv("MODELS_PATH", str(project_root / "Models"))
        else:
            # Docker/Linux mode - use container path
            models_path = os.getenv("MODELS_PATH", "/models")
            
        chat_model = os.getenv("CHAT_MODEL", "Gryphe_Codex-24B-Small-3.2-Q6_K_L.gguf")
        summary_model = os.getenv("SUMMARY_MODEL", "dphn.Dolphin-Mistral-24B-Venice-Edition.Q6_K.gguf")
        embedding_model = os.getenv("EMBEDDING_MODEL", "all-MiniLM-L6-v2.F32.gguf")
        
        self.models_path = Path(models_path).resolve()
        logger.info(f"Platform: {'Windows' if self.is_windows else 'Linux/Docker'}")
        logger.info(f"Models path: {self.models_path}")
        logger.info(f"Current working directory: {os.getcwd()}")
        logger.info(f"Resolved models path: {self.models_path.absolute()}")
        logger.info(f"__file__ location: {__file__}")
        logger.info(f"Calculated project_root: {Path(__file__).parent.parent.parent.parent.resolve()}")
        
        # Validate models directory exists
        if not self.models_path.exists():
            logger.error(f"Models directory does not exist: {self.models_path}")
            logger.error(f"Please ensure the Models directory exists at the correct path")
        elif not self.models_path.is_dir():
            logger.error(f"Models path is not a directory: {self.models_path}")
        else:
            # List available model files
            model_files = [f.name for f in self.models_path.iterdir() if f.is_file() and f.suffix == '.gguf']
            logger.info(f"Found {len(model_files)} GGUF model files: {model_files[:5]}{'...' if len(model_files) > 5 else ''}")
        
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
                        if self.redis_client:
                            try:
                                await self.redis_client.aclose()
                            except Exception:
                                pass
                        self.redis_client = None
                    else:
                        if self.redis_client:
                            try:
                                await self.redis_client.aclose()
                            except Exception:
                                pass
                        raise  # Redis required in Docker mode
            else:
                logger.warning("Redis not available - continuing without Redis support")
                self.redis_client = None
            
            # Backend-specific GPU detection
            if self.backend == "vulkan":
                await self._check_vulkan_gpu()
            elif self.backend == "rocm":
                await self._check_rocm_gpu()
            elif self.backend == "cuda":
                await self._check_cuda_gpu()
            else:
                logger.warning(f"Unknown backend '{self.backend}', skipping GPU detection")
            
            await self._update_status()
            logger.info("ModelManager initialized successfully")
            
        except Exception as e:
            logger.error(f"Failed to initialize ModelManager: {e}")
            await self.state_machine.handle_error(e)
            raise
            
    async def load_model(self, model_type: str) -> bool:
        """Hot-swap to specified model (chat/summary)"""
        async with self._load_lock:
            try:
                if model_type not in self.model_configs:
                    raise ValueError(f"Unknown model type: {model_type}")
                    
                # If already loaded with same type, return
                if self.current_model_type == model_type and self.state_machine.get_current_state() == ModelState.LOADED:
                    logger.info(f"Model {model_type} already loaded")
                    return True
                    
                # Unload current model if different type
                if self.current_model and self.current_model_type != model_type:
                    await self.unload_current_model()
                    
                await self.state_machine.transition(ModelState.LOADING)
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
                    await self.state_machine.handle_error(Exception(f"Insufficient memory for {model_type} model"))
                    return False
                    
                # Load model using llama wrapper
                try:
                    from .llama_wrapper import LlamaWrapper
                except ImportError:
                    from llama_wrapper import LlamaWrapper
                self.current_wrapper = LlamaWrapper()
                self.current_model = self.current_wrapper.load_model(config["path"], config)
                self.current_model_type = model_type
                await self.state_machine.transition(ModelState.LOADED)
                
                await self._update_status()
                logger.info(f"Successfully loaded {model_type} model")
                return True
                
            except Exception as e:
                logger.error(f"Failed to load {model_type} model: {e}")
                await self.state_machine.handle_error(e)
                await self._update_status()
                return False
            
    async def unload_current_model(self):
        """Free VRAM and cleanup current model"""
        try:
            if not self.current_model:
                return
                
            await self.state_machine.transition(ModelState.UNLOADING)
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
                
            await self.state_machine.transition(ModelState.IDLE)
            await self._update_status()
            logger.info("Model unloaded successfully")
            
        except Exception as e:
            logger.error(f"Error unloading model: {e}")
            await self.state_machine.handle_error(e)
            
    async def generate_stream(self, prompt: str, params: dict) -> AsyncGenerator[str, None]:
        """Stream tokens from current model"""
        async with self._gen_lock:
            if not self.current_model or self.state_machine.get_current_state() != ModelState.LOADED:
                raise RuntimeError("No model loaded")
                
            try:
                await self.state_machine.transition(ModelState.GENERATING)
                await self._update_status()
                
                async for token in self.current_wrapper.generate_tokens(prompt, **params):
                    yield token
                    
            finally:
                await self.state_machine.transition(ModelState.LOADED)
                await self._update_status()
            
    async def generate_completion(self, prompt: str, params: dict) -> str:
        """Generate complete response (for summaries)"""
        async with self._gen_lock:
            if not self.current_model or self.state_machine.get_current_state() != ModelState.LOADED:
                raise RuntimeError("No model loaded")
                
            try:
                await self.state_machine.transition(ModelState.GENERATING)
                await self._update_status()
                
                tokens = []
                async for token in self.current_wrapper.generate_tokens(prompt, **params):
                    tokens.append(token)
                    
                return "".join(tokens)
                
            finally:
                await self.state_machine.transition(ModelState.LOADED)
                await self._update_status()
            
    async def get_model_status(self) -> dict:
        """Return current model state, type, and memory usage"""
        try:
            base_status = {
                "state": self.state_machine.get_current_state().value,
                "current_model_type": self.current_model_type,
                "current_model": self.current_model is not None,
                "platform": "windows" if self.is_windows else "linux",
                "backend": self.backend,
                "models_path": str(self.models_path),
                "available_models": list(self.model_configs.keys()),
                "timestamp": asyncio.get_event_loop().time(),
                "state_machine_stats": self.state_machine.get_stats()
            }
            
            # Add GPU info
            base_status["gpu_info"] = self.get_gpu_info()
            
            # Add model metadata if available
            if self.current_wrapper:
                try:
                    base_status["model_info"] = self.current_wrapper.get_model_info()
                except Exception:
                    pass
            
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
                "state": self.state_machine.get_current_state().value,
                "current_model_type": self.current_model_type,
                "platform": "windows" if self.is_windows else "linux",
                "backend": self.backend,
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
            
            # Clean up Redis connection
            if self.redis_client:
                try:
                    await self.redis_client.aclose()
                    logger.debug("Redis connection closed")
                except Exception as redis_error:
                    logger.debug(f"Error closing Redis connection: {redis_error}")
                finally:
                    self.redis_client = None
                
            gc.collect()
            # PyTorch CUDA operations not needed for GGUF models
                
            await self.state_machine.transition(ModelState.IDLE)
            await self._update_status()
            logger.info("Emergency shutdown completed")
            
        except Exception as e:
            logger.error(f"Error during emergency shutdown: {e}")
            await self.state_machine.handle_error(e)
            
    async def _check_vulkan_gpu(self):
        """Vulkan backend GPU detection"""
        try:
            logger.info("Checking Vulkan GPU availability...")
            
            # Check if Vulkan SDK is available
            import subprocess
            try:
                # Safe subprocess call with timeout and error handling
                result = subprocess.run(["vulkaninfo", "--summary"], 
                                      capture_output=True, text=True, timeout=15,
                                      creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, 'CREATE_NO_WINDOW') else 0)
                if result.returncode == 0:
                    vulkan_output = result.stdout
                    # Look for device info in vulkaninfo output
                    lines = vulkan_output.split('\n')
                    device_count = 0
                    for line in lines:
                        if "deviceName" in line:
                            device_count += 1
                            device_name = line.split('=')[-1].strip()
                            logger.info(f"✅ Vulkan Device: {device_name}")
                    
                    if device_count > 0:
                        logger.info(f"✅ Vulkan backend ready with {device_count} device(s)")
                        logger.info("🔥 All model layers will be offloaded to GPU via Vulkan")
                    else:
                        logger.warning("Vulkan runtime available but no devices found")
                else:
                    logger.warning("vulkaninfo failed - Vulkan may not be properly installed")
                    
            except FileNotFoundError:
                logger.warning("vulkaninfo not found - install Vulkan SDK for verification")
            except Exception as e:
                logger.warning(f"Vulkan check failed: {e}")
                
        except Exception as e:
            logger.warning(f"Vulkan GPU detection error: {e}")
            
    async def _check_rocm_gpu(self):
        """ROCm backend GPU detection"""
        try:
            logger.info("Checking ROCm GPU availability...")
            
            import subprocess
            hip_versions = ["6.4", "6.3", "6.2", "6.1", "6.0", "5.7"]
            rocm_found = False
            
            for version in hip_versions:
                hipinfo_path = rf"C:\Program Files\AMD\ROCm\{version}\bin\hipInfo.exe" if self.is_windows else "hipInfo"
                try:
                    # Validate path exists before running
                    if self.is_windows and not os.path.exists(hipinfo_path):
                        continue
                    result = subprocess.run([hipinfo_path], 
                                          capture_output=True, text=True, timeout=10,
                                          creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, 'CREATE_NO_WINDOW') else 0)
                    if result.returncode == 0:
                        rocm_found = True
                        gpu_output = result.stdout
                        if any(gpu_name in gpu_output for gpu_name in ["7900", "RX 7", "RDNA3"]):
                            logger.info(f"✅ AMD RDNA3 GPU detected with ROCm {version}")
                        else:
                            logger.info(f"✅ AMD GPU detected with ROCm {version}")
                        break
                except FileNotFoundError:
                    continue
                except Exception as e:
                    logger.debug(f"ROCm {version} check failed: {e}")
                    continue
            
            if not rocm_found:
                logger.warning("ROCm not found - install ROCm for AMD GPU acceleration")
                
        except Exception as e:
            logger.warning(f"ROCm GPU detection error: {e}")
            
    async def _check_cuda_gpu(self):
        """CUDA backend GPU detection"""
        try:
            logger.info("Checking CUDA GPU availability...")
            
            if GPUTIL_AVAILABLE:
                try:
                    gpus = GPUtil.getGPUs()
                    if not gpus:
                        logger.warning("No CUDA GPUs detected")
                    else:
                        logger.info(f"✅ Found {len(gpus)} CUDA GPU(s)")
                        for i, gpu in enumerate(gpus):
                            logger.info(f"GPU {i}: {gpu.name}, Memory: {gpu.memoryTotal}MB")
                except Exception as e:
                    logger.warning(f"CUDA GPU detection failed: {e}")
            else:
                logger.warning("GPUtil not available - install GPUtil for CUDA detection")
                
        except Exception as e:
            logger.warning(f"CUDA GPU detection error: {e}")
            
    def get_gpu_info(self) -> dict:
        """Get GPU information for status endpoint"""
        return {
            "platform": "windows" if self.is_windows else "linux",
            "backend": self.backend,
            "backend_available": self._check_backend_available(),
            "timestamp": asyncio.get_event_loop().time()
        }
        
    def _check_backend_available(self) -> bool:
        """Quick check if the configured backend is available"""
        try:
            if self.backend == "vulkan":
                import subprocess
                result = subprocess.run(["vulkaninfo", "--summary"], 
                                      capture_output=True, timeout=5,
                                      creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, 'CREATE_NO_WINDOW') else 0)
                return result.returncode == 0
            elif self.backend == "rocm":
                import subprocess
                result = subprocess.run(["hipInfo"], 
                                      capture_output=True, timeout=5,
                                      creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, 'CREATE_NO_WINDOW') else 0)
                return result.returncode == 0
            elif self.backend == "cuda":
                return GPUTIL_AVAILABLE
            else:
                return False
        except:
            return False
            
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
            
    async def generate_embeddings(self, texts: List[str]) -> List[List[float]]:
        """Generate embeddings for a list of texts"""
        try:
            if not self.current_embedding_model:
                if not await self.load_embedding_model():
                    raise Exception("Failed to load embedding model")
                    
            embeddings = []
            for text in texts:
                # Create embeddings using llama.cpp
                embedding = self.current_embedding_model.create_embedding(input=text)
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