import asyncio
import logging
from typing import AsyncGenerator, Dict, Any, Optional
import os
from contextlib import asynccontextmanager
import concurrent.futures

logger = logging.getLogger(__name__)

try:
    from llama_cpp import Llama
    LLAMA_CPP_AVAILABLE = True
except ImportError:
    LLAMA_CPP_AVAILABLE = False
    logger.warning("llama-cpp-python not available. Install with: pip install llama-cpp-python")

class LlamaWrapper:
    """Wrapper around llama.cpp with parameter management"""
    
    def __init__(self):
        self.model: Optional[Llama] = None
        self.model_path: Optional[str] = None
        self.config: Dict[str, Any] = {}
        
        # Safe parameter allowlists for llama-cpp-python
        self.supported_model_params = {
            "model_path", "n_ctx", "n_batch", "n_gpu_layers", "n_threads",
            "use_mmap", "use_mlock", "seed", "verbose", "logits_all", 
            "vocab_only", "embedding"
        }
        
        self.supported_generation_params = {
            "max_tokens", "temperature", "top_p", "top_k", "repeat_penalty",
            "stop", "stream", "echo", "suffix", "logprobs", "tfs_z", 
            "typical_p", "mirostat_mode", "mirostat_tau", "mirostat_eta"
        }
        
        self.default_params = {
            "max_tokens": 512,
            "temperature": 0.8,
            "top_p": 0.95,
            "top_k": 40,
            "repeat_penalty": 1.1,
            "stop": ["</s>", "\n\n"],
            "stream": True
        }
        
    def load_model(self, model_path: str, config: dict):
        """Load GGUF model with specified configuration"""
        try:
            if not LLAMA_CPP_AVAILABLE:
                raise RuntimeError("llama-cpp-python not available")
                
            if not os.path.exists(model_path):
                raise FileNotFoundError(f"Model file not found: {model_path}")
                
            logger.info(f"Loading model from {model_path}")
            
            # Build model parameters safely
            model_params = {"model_path": model_path}
            
            # Add only supported parameters from config
            for param in self.supported_model_params:
                if param in config and config[param] is not None:
                    model_params[param] = config[param]
            
            # Set safe defaults for missing critical parameters
            model_params.setdefault("n_ctx", 4096)
            model_params.setdefault("n_batch", 512)
            model_params.setdefault("n_gpu_layers", -1)
            model_params.setdefault("verbose", False)
            model_params.setdefault("use_mmap", True)
            model_params.setdefault("use_mlock", False)
            model_params.setdefault("seed", -1)
            
            logger.info(f"Filtered model params: {list(model_params.keys())}")
            
            self.model = Llama(**model_params)
            self.model_path = model_path
            self.config = config
            
            logger.info(f"Model loaded successfully: {model_path}")
            logger.info(f"Context size: {self.model.n_ctx()}")
            logger.info(f"Vocab size: {self.model.n_vocab()}")
            
            return self.model
            
        except Exception as e:
            logger.error(f"Failed to load model {model_path}: {e}")
            self.model = None
            self.model_path = None
            self.config = {}
            raise
            
    async def generate_tokens(self, prompt: str, **kwargs) -> AsyncGenerator[str, None]:
        """Generate tokens with fine-grained parameter control"""
        if not self.model:
            raise RuntimeError("No model loaded")
            
        try:
            # Merge and filter parameters safely
            merged_params = {**self.default_params, **kwargs}
            params = {k: v for k, v in merged_params.items() 
                     if k in self.supported_generation_params}
            
            # Ensure streaming is enabled
            params["stream"] = True
            
            logger.debug(f"Filtered generation params: {list(params.keys())}")
            
            # Use a bounded queue to pass tokens from worker thread to async generator
            token_queue = asyncio.Queue(maxsize=256)
            loop = asyncio.get_running_loop()
            stop_event = asyncio.Event()
            
            def _generate_worker():
                """Worker function that runs in thread pool"""
                try:
                    response_stream = self.model(prompt, **params)
                    for chunk in response_stream:
                        if stop_event.is_set():
                            break
                        if "choices" in chunk and len(chunk["choices"]) > 0:
                            choice = chunk["choices"][0]
                            if "text" in choice:
                                token = choice["text"]
                                if token:
                                    # Use thread-safe method to put token in queue
                                    asyncio.run_coroutine_threadsafe(
                                        token_queue.put(token), loop
                                    )
                    # Signal completion
                    asyncio.run_coroutine_threadsafe(
                        token_queue.put(None), loop
                    )
                except Exception as e:
                    logger.error(f"Error during generation: {e}")
                    # Signal error
                    asyncio.run_coroutine_threadsafe(
                        token_queue.put(e), loop
                    )
                    
            # Start generation in a thread pool executor
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
                future = executor.submit(_generate_worker)
            
                # Yield tokens from queue
                try:
                    while True:
                        item = await token_queue.get()
                        if item is None:
                            # Completion signal
                            break
                        elif isinstance(item, Exception):
                            # Error signal
                            stop_event.set()
                            raise item
                        else:
                            # Token
                            yield item
                            # Small delay to prevent overwhelming the consumer
                            await asyncio.sleep(0.001)
                finally:
                    # Ensure worker is stopped and completed
                    stop_event.set()
                    try:
                        # Wait for the worker thread to complete with timeout
                        await asyncio.wait_for(
                            asyncio.wrap_future(future), 
                            timeout=5.0
                        )
                    except asyncio.TimeoutError:
                        logger.warning("Worker thread did not complete within timeout")
                    except Exception as e:
                        logger.debug(f"Worker completion error: {e}")
                            
        except Exception as e:
            logger.error(f"Error generating tokens: {e}")
            raise
            
    def adjust_parameters(self, params: dict):
        """Dynamically adjust generation parameters"""
        try:
            # Filter to only supported parameters
            filtered_params = {k: v for k, v in params.items() 
                             if k in self.supported_generation_params}
            
            if filtered_params:
                self.default_params.update(filtered_params)
                logger.info(f"Updated generation parameters: {filtered_params}")
            else:
                logger.warning("No valid parameters provided for adjustment")
                
        except Exception as e:
            logger.error(f"Error adjusting parameters: {e}")
            
    def get_model_info(self) -> dict:
        """Return model metadata and capabilities"""
        try:
            if not self.model:
                return {"status": "no_model_loaded"}
                
            info = {
                "status": "loaded",
                "model_path": self.model_path,
                "context_size": self.model.n_ctx(),
                "vocab_size": self.model.n_vocab(),
                "embedding_size": self.model.n_embd() if hasattr(self.model, 'n_embd') else None,
                "config": self.config,
                "default_params": self.default_params
            }
            
            # Try to get model metadata
            try:
                metadata = self.model.metadata if hasattr(self.model, 'metadata') else {}
                info["metadata"] = metadata
            except Exception as e:
                logger.debug(f"Could not retrieve model metadata: {e}")
                
            return info
            
        except Exception as e:
            logger.error(f"Error getting model info: {e}")
            return {"status": "error", "error": str(e)}
            
    def tokenize(self, text: str) -> list:
        """Tokenize text using the model's tokenizer"""
        try:
            if not self.model:
                raise RuntimeError("No model loaded")
                
            tokens = self.model.tokenize(text.encode("utf-8"))
            return tokens
            
        except Exception as e:
            logger.error(f"Error tokenizing text: {e}")
            raise
            
    def detokenize(self, tokens: list) -> str:
        """Convert tokens back to text"""
        try:
            if not self.model:
                raise RuntimeError("No model loaded")
                
            text = self.model.detokenize(tokens).decode("utf-8", errors="ignore")
            return text
            
        except Exception as e:
            logger.error(f"Error detokenizing: {e}")
            raise
            
    def count_tokens(self, text: str) -> int:
        """Count tokens in text"""
        try:
            tokens = self.tokenize(text)
            return len(tokens)
        except Exception as e:
            logger.error(f"Error counting tokens: {e}")
            return -1
            
    def truncate_to_token_limit(self, text: str, max_tokens: int) -> str:
        """Truncate text to fit within token limit"""
        try:
            tokens = self.tokenize(text)
            if len(tokens) <= max_tokens:
                return text
                
            truncated_tokens = tokens[:max_tokens]
            return self.detokenize(truncated_tokens)
            
        except Exception as e:
            logger.error(f"Error truncating text: {e}")
            return text
            
    def unload(self):
        """Unload the model to free memory"""
        try:
            if self.model:
                del self.model
                self.model = None
                self.model_path = None
                self.config = {}
                
                # Force garbage collection to free memory
                import gc
                gc.collect()
                
                logger.info("Model unloaded successfully")
                
        except Exception as e:
            logger.error(f"Error unloading model: {e}")
            
    def is_loaded(self) -> bool:
        """Check if model is loaded"""
        return self.model is not None
        
    @asynccontextmanager
    async def generation_context(self, **params):
        """Context manager for generation with cleanup"""
        old_params = self.default_params.copy()
        try:
            if params:
                self.adjust_parameters(params)
            yield self
        finally:
            self.default_params = old_params