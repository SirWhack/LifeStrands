import asyncio
import logging
import os
from contextlib import asynccontextmanager
from typing import AsyncGenerator

# Configure logging FIRST before importing any app modules
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import List

# Check for backend mode
MOCK_MODE = os.getenv("MOCK_MODE", "false").lower() == "true"
LM_STUDIO_MODE = os.getenv("LM_STUDIO_MODE", "false").lower() == "true"

if MOCK_MODE:
    logger.info("Mock mode enabled - using canned responses")
    try:
        from src.mock_model_service import MockModelManager
    except ImportError:
        from mock_model_service import MockModelManager
elif LM_STUDIO_MODE:
    logger.info("LM Studio mode enabled - using LM Studio backend")
    try:
        from src.lm_studio_backend import LMStudioBackend
    except ImportError:
        from lm_studio_backend import LMStudioBackend
else:
    logger.info("GPU mode enabled - using real model service")
    try:
        from src.model_manager import ModelManager
        from src.request_distributor import RequestDistributor, ServiceType
        from src.intelligent_queue_manager import IntelligentQueueManager
        from src.enhanced_model_pools import GenerationPool, EmbeddingPool
    except ImportError:
        # Fallback for when running directly from model-service directory
        from model_manager import ModelManager
        from request_distributor import RequestDistributor, ServiceType
        from intelligent_queue_manager import IntelligentQueueManager
        from enhanced_model_pools import GenerationPool, EmbeddingPool

# Global components
model_manager = None
request_distributor = None
queue_manager = None
generation_pool = None
embedding_pool = None
lm_studio_backend = None

class GenerateRequest(BaseModel):
    prompt: str
    model_type: str = "chat"
    service_type: str = "chat"  # New: for intelligent queuing
    max_tokens: int = 512
    temperature: float = 0.7
    top_p: float = 0.9
    stream: bool = True
    priority: int = None  # New: optional priority override
    timeout: float = 300.0  # New: request timeout

class LoadModelRequest(BaseModel):
    model_type: str

class EmbeddingsRequest(BaseModel):
    texts: List[str]
    priority: int = 3  # New: priority for embedding requests
    timeout: float = 60.0  # New: timeout for embedding requests

# OpenAI-compatible models
class ChatMessage(BaseModel):
    role: str
    content: str

class ChatCompletionRequest(BaseModel):
    model: str = None
    messages: List[ChatMessage]
    max_tokens: int = 512
    temperature: float = 0.7
    top_p: float = 0.9
    stream: bool = True

class OpenAIEmbeddingsRequest(BaseModel):
    model: str = None
    input: List[str]

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown events with mock, LM Studio, or real architecture"""
    global model_manager, request_distributor, queue_manager, generation_pool, embedding_pool, lm_studio_backend
    
    if MOCK_MODE:
        logger.info("=== STARTING MOCK MODEL SERVICE ===")
        try:
            # Initialize mock manager
            model_manager = MockModelManager()
            await model_manager.initialize()
            
            # Load default chat model
            await model_manager.load_model("chat")
            
            logger.info("=== MOCK MODEL SERVICE READY ===")
            yield
        except Exception as e:
            logger.error(f"Failed to initialize mock service: {e}")
            raise
        finally:
            logger.info("=== SHUTTING DOWN MOCK MODEL SERVICE ===")
            if model_manager:
                await model_manager.emergency_shutdown()
            logger.info("Mock model service shut down")
    elif LM_STUDIO_MODE:
        logger.info("=== STARTING LM STUDIO MODEL SERVICE ===")
        try:
            # Initialize LM Studio backend
            lm_studio_backend = LMStudioBackend()
            success = await lm_studio_backend.initialize()
            
            if not success:
                raise Exception("Failed to connect to LM Studio")
            
            logger.info("=== LM STUDIO MODEL SERVICE READY ===")
            yield
        except Exception as e:
            logger.error(f"Failed to initialize LM Studio service: {e}")
            raise
        finally:
            logger.info("=== SHUTTING DOWN LM STUDIO MODEL SERVICE ===")
            if lm_studio_backend:
                await lm_studio_backend.cleanup()
            logger.info("LM Studio model service shut down")
    else:
        logger.info("=== STARTING ENHANCED MODEL SERVICE ===")
        try:
            # Initialize legacy model manager for compatibility
            logger.info("Creating ModelManager instance...")
            model_manager = ModelManager()
            logger.info("ModelManager created, calling initialize()...")
            await model_manager.initialize()
            logger.info("ModelManager initialized successfully!")
            
            # Initialize new architecture components
            logger.info("Initializing new architecture components...")
            
            # Configuration for new components
            config = {
                "max_queue_size": 100,
                "batch_timeout": 0.2,
                "max_batch_size": 10,
                "safety_margin_gb": 1.0
            }
            
            # Create memory monitor for enhanced pools
            try:
                from src.memory_monitor import MemoryMonitor
            except ImportError:
                from memory_monitor import MemoryMonitor
            
            memory_monitor = MemoryMonitor()
            
            # Store reference in model_manager for compatibility
            model_manager.memory_monitor = memory_monitor
            model_manager.model_configs = model_manager.model_configs  # Ensure configs are accessible
            
            # Initialize model pools with the initialized model_manager
            generation_pool = GenerationPool(config, memory_monitor, model_manager)
            embedding_pool = EmbeddingPool(config, memory_monitor, model_manager)
            
            # Initialize pools
            await generation_pool.initialize("chat")  # Start with chat model
            await embedding_pool.initialize()
            
            model_pools = {
                "generation": generation_pool,
                "embedding": embedding_pool
            }
            
            # Initialize queue manager
            queue_manager = IntelligentQueueManager(model_pools, config)
            await queue_manager.start()
            
            # Initialize request distributor
            circuit_breaker_config = {
                "failure_threshold": 5,
                "recovery_timeout": 60,
                "success_threshold": 3
            }
            request_distributor = RequestDistributor(queue_manager, circuit_breaker_config)
            
            logger.info("=== ENHANCED MODEL SERVICE READY ===")
            yield
        except Exception as e:
            logger.error(f"Failed to initialize enhanced model service: {e}")
            logger.error("Full traceback:", exc_info=True)
            # Don't raise - let service start in degraded mode
            if not model_manager:
                logger.warning("Creating fallback ModelManager...")
                model_manager = ModelManager()  # Create a basic instance
            yield
        finally:
            logger.info("=== SHUTTING DOWN ENHANCED MODEL SERVICE ===")
            
            # Shutdown new components
            if queue_manager:
                await queue_manager.shutdown()
            
            if model_manager:
                await model_manager.emergency_shutdown()
            
            logger.info("Enhanced model service shut down")

import platform
is_windows = platform.system() == "Windows"

if MOCK_MODE:
    service_title = "Life Strands Model Service - Mock Mode"
    service_description = "Mock model service with canned responses"
    service_version = "2.0.0-mock"
elif LM_STUDIO_MODE:
    service_title = "Life Strands Model Service - LM Studio Backend"
    service_description = "OpenAI-compatible API using LM Studio backend"
    service_version = "2.0.0-lmstudio"
else:
    service_title = f"Life Strands Model Service - {'Windows Vulkan' if is_windows else 'Docker'}"
    service_description = "Unified GPU model management and text generation service with full layer offloading"
    service_version = "2.0.0"

app = FastAPI(
    title=service_title,
    description=service_description,
    version=service_version,
    lifespan=lifespan
)

@app.get("/ping")
async def ping():
    """Simple ping endpoint"""
    logger.info("Ping endpoint called")
    return {"message": "pong", "service": "model-service"}

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    logger.info("Health check endpoint called")
    
    if LM_STUDIO_MODE:
        if not lm_studio_backend:
            return {"status": "degraded", "error": "LM Studio backend not initialized", "lm_studio_mode": True}
        try:
            health_info = await lm_studio_backend.health_check()
            return {"status": "healthy", "backend_info": health_info, "lm_studio_mode": True}
        except Exception as e:
            logger.error(f"LM Studio health check error: {e}")
            return {"status": "error", "error": str(e), "lm_studio_mode": True}
    elif not model_manager:
        logger.warning("Health check: ModelManager not initialized")
        return {"status": "degraded", "error": "ModelManager not initialized", "mock_mode": MOCK_MODE}
    try:
        logger.debug("Getting model status...")
        status = await model_manager.get_model_status()
        logger.debug(f"Model status retrieved: {status}")
        return {"status": "healthy", "model_status": status, "mock_mode": MOCK_MODE}
    except Exception as e:
        logger.error(f"Health check error: {e}", exc_info=True)
        return {"status": "error", "error": str(e), "mock_mode": MOCK_MODE}

@app.post("/generate")
async def generate_text(request: GenerateRequest):
    """Generate text with enhanced queuing and streaming"""
    try:
        if LM_STUDIO_MODE:
            # Use LM Studio backend
            return await _lm_studio_generate(request)
        elif not request_distributor:
            # Fallback to legacy mode
            logger.warning("Using legacy generation mode")
            return await _legacy_generate(request)
        
        # Map service type
        service_type_map = {
            "chat": ServiceType.CHAT,
            "summary": ServiceType.SUMMARY,
            "npc": ServiceType.NPC
        }
        service_type = service_type_map.get(request.service_type, ServiceType.CHAT)
        
        params = {
            "max_tokens": request.max_tokens,
            "temperature": request.temperature,
            "top_p": request.top_p
        }
        
        if request.stream:
            import json
            
            async def generate_stream():
                try:
                    async for token in request_distributor.handle_generation_request(
                        service_type=service_type,
                        prompt=request.prompt,
                        generation_params=params,
                        priority=request.priority,
                        timeout=request.timeout
                    ):
                        # Encode token in JSON to handle special characters safely
                        token_data = json.dumps({"token": token})
                        yield f"data: {token_data}\n\n"
                    
                    # Send completion signal
                    completion_data = json.dumps({"done": True})
                    yield f"data: {completion_data}\n\n"
                except Exception as e:
                    error_data = json.dumps({"error": str(e)})
                    yield f"data: {error_data}\n\n"
            
            return StreamingResponse(
                generate_stream(), 
                media_type="text/event-stream",
                headers={
                    "Cache-Control": "no-cache",
                    "Connection": "keep-alive",
                    "X-Accel-Buffering": "no"
                }
            )
        else:
            # Non-streaming mode - collect all tokens
            result_text = ""
            async for token in request_distributor.handle_generation_request(
                service_type=service_type,
                prompt=request.prompt,
                generation_params=params,
                priority=request.priority,
                timeout=request.timeout
            ):
                result_text += token
            
            return {"text": result_text}
            
    except Exception as e:
        logger.error(f"Generation error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

async def _legacy_generate(request: GenerateRequest):
    """Fallback to legacy generation for compatibility"""
    if not model_manager:
        raise HTTPException(status_code=503, detail="ModelManager not ready")
    
    # Load model if needed
    if model_manager.current_model_type != request.model_type:
        success = await model_manager.load_model(request.model_type)
        if not success:
            raise HTTPException(
                status_code=500, 
                detail=f"Failed to load {request.model_type} model"
            )
    
    params = {
        "max_tokens": request.max_tokens,
        "temperature": request.temperature,
        "top_p": request.top_p
    }
    
    if request.stream:
        import json
        
        async def generate_stream():
            async for token in model_manager.generate_stream(request.prompt, params):
                token_data = json.dumps({"token": token})
                yield f"data: {token_data}\n\n"
            
            completion_data = json.dumps({"done": True})
            yield f"data: {completion_data}\n\n"
        
        return StreamingResponse(
            generate_stream(), 
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no"
            }
        )
    else:
        result = await model_manager.generate_completion(request.prompt, params)
        return {"text": result}

async def _lm_studio_generate(request: GenerateRequest):
    """Generate text using LM Studio backend"""
    if not lm_studio_backend:
        raise HTTPException(status_code=503, detail="LM Studio backend not ready")
    
    try:
        # Convert prompt to chat format
        messages = [{"role": "user", "content": request.prompt}]
        
        if request.stream:
            import json
            
            async def generate_stream():
                try:
                    async for token in lm_studio_backend.generate_chat_completion(
                        messages=messages,
                        model=None,  # Let LM Studio auto-select
                        max_tokens=request.max_tokens,
                        temperature=request.temperature,
                        top_p=request.top_p,
                        stream=True
                    ):
                        # Use legacy format for backward compatibility
                        token_data = json.dumps({"token": token})
                        yield f"data: {token_data}\n\n"
                    
                    # Send completion signal
                    completion_data = json.dumps({"done": True})
                    yield f"data: {completion_data}\n\n"
                except Exception as e:
                    error_data = json.dumps({"error": str(e)})
                    yield f"data: {error_data}\n\n"
            
            return StreamingResponse(
                generate_stream(), 
                media_type="text/event-stream",
                headers={
                    "Cache-Control": "no-cache",
                    "Connection": "keep-alive",
                    "X-Accel-Buffering": "no"
                }
            )
        else:
            # Non-streaming mode
            result_text = ""
            async for token in lm_studio_backend.generate_chat_completion(
                messages=messages,
                model=None,
                max_tokens=request.max_tokens,
                temperature=request.temperature,
                top_p=request.top_p,
                stream=True
            ):
                result_text += token
            
            return {"text": result_text}
            
    except Exception as e:
        logger.error(f"LM Studio generation error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/load-model")
async def load_model(request: LoadModelRequest):
    """Hot-swap model"""
    logger.info(f"Load model request: {request.model_type}")
    if not model_manager:
        logger.error("Load model: ModelManager not initialized")
        raise HTTPException(status_code=500, detail="ModelManager not initialized")
    try:
        logger.info(f"Calling model_manager.load_model({request.model_type})...")
        success = await model_manager.load_model(request.model_type)
        logger.info(f"Load model result: {success}")
        if success:
            return {"message": f"Successfully loaded {request.model_type} model"}
        else:
            raise HTTPException(
                status_code=500,
                detail=f"Failed to load {request.model_type} model"
            )
    except Exception as e:
        logger.error(f"Model loading error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/unload-model")
async def unload_model():
    """Unload current model to free VRAM"""
    if not model_manager:
        raise HTTPException(status_code=503, detail="ModelManager not ready")
    try:
        await model_manager.unload_current_model()
        return {"message": "Model unloaded successfully"}
    except Exception as e:
        logger.error(f"Model unloading error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/status")
async def get_status():
    """Get detailed model and GPU status"""
    if not model_manager:
        raise HTTPException(status_code=503, detail="ModelManager not ready")
    status = await model_manager.get_model_status()
    # Add state machine history for debugging
    status["state_history"] = await model_manager.state_machine.get_state_history()
    return status

@app.post("/switch/{model_type}")
async def switch_model(model_type: str):
    """Windows-compatible model switching endpoint"""
    if not model_manager:
        raise HTTPException(status_code=503, detail="ModelManager not ready")
    try:
        if model_type not in model_manager.model_configs:
            raise HTTPException(404, f"Model type '{model_type}' not found")
        
        success = await model_manager.load_model(model_type)
        if success:
            config = model_manager.model_configs[model_type]
            return {
                "status": "success",
                "model_type": model_type,
                "gpu_layers": config.get("n_gpu_layers", -1),
                "context_size": config.get("n_ctx", 4096)
            }
        else:
            raise HTTPException(500, f"Failed to load {model_type} model")
    except Exception as e:
        logger.error(f"Model switching error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/vram")
async def get_vram_usage():
    """Real-time VRAM monitoring"""
    if not model_manager:
        raise HTTPException(status_code=503, detail="ModelManager not ready")
    return await model_manager.monitor_vram()

@app.post("/emergency-shutdown")
async def emergency_shutdown():
    """Emergency model cleanup"""
    if not model_manager:
        raise HTTPException(status_code=503, detail="ModelManager not ready")
    try:
        await model_manager.emergency_shutdown()
        return {"message": "Emergency shutdown completed"}
    except Exception as e:
        logger.error(f"Emergency shutdown error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/metrics")
async def get_metrics():
    """Get comprehensive service metrics"""
    from datetime import datetime
    try:
        metrics = {
            "service": "enhanced-model-service",
            "timestamp": datetime.utcnow().isoformat(),
            "uptime": "healthy" if model_manager else "unhealthy"
        }
        
        # Legacy metrics
        if model_manager:
            metrics["legacy_status"] = await model_manager.get_model_status()
        
        # Enhanced architecture metrics
        if request_distributor:
            metrics["request_distributor"] = request_distributor.get_request_stats()
        
        if queue_manager:
            metrics["queue_status"] = await queue_manager.get_queue_status()
        
        if generation_pool:
            metrics["generation_pool"] = await generation_pool.get_pool_status()
        
        if embedding_pool:
            metrics["embedding_pool"] = await embedding_pool.get_pool_status()
        
        return metrics
        
    except Exception as e:
        return {
            "service": "enhanced-model-service",
            "timestamp": datetime.utcnow().isoformat(),
            "status": "error",
            "error": str(e)
        }

@app.get("/queue-status")
async def get_queue_status():
    """Get detailed queue status"""
    if not queue_manager:
        raise HTTPException(status_code=503, detail="Queue manager not available")
    
    try:
        return await queue_manager.get_queue_status()
    except Exception as e:
        logger.error(f"Error getting queue status: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/circuit-breakers")
async def get_circuit_breaker_status():
    """Get circuit breaker status"""
    if not request_distributor:
        raise HTTPException(status_code=503, detail="Request distributor not available")
    
    try:
        return request_distributor.get_circuit_breaker_status()
    except Exception as e:
        logger.error(f"Error getting circuit breaker status: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/pool-status")
async def get_pool_status():
    """Get model pool status"""
    try:
        status = {}
        
        if generation_pool:
            status["generation_pool"] = await generation_pool.get_pool_status()
        
        if embedding_pool:
            status["embedding_pool"] = await embedding_pool.get_pool_status()
        
        if not status:
            raise HTTPException(status_code=503, detail="Model pools not available")
        
        return status
    except Exception as e:
        logger.error(f"Error getting pool status: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/embeddings")
async def generate_embeddings(request: EmbeddingsRequest):
    """Generate embeddings with enhanced batching"""
    try:
        texts = request.texts
        if not texts:
            raise HTTPException(status_code=400, detail="No texts provided")
        
        if LM_STUDIO_MODE:
            # Use LM Studio backend
            embeddings = await lm_studio_backend.generate_embeddings(texts)
            return {
                "embeddings": embeddings,
                "model": "text-embedding-nomic-embed-text-v1.5",
                "count": len(embeddings),
                "batch_size": len(texts)
            }
        elif request_distributor:
            # Use new architecture with batching
            embeddings = await request_distributor.handle_embedding_request(
                texts=texts,
                priority=request.priority,
                timeout=request.timeout
            )
        else:
            # Fallback to legacy mode
            logger.warning("Using legacy embedding mode")
            embeddings = await model_manager.generate_embeddings(texts)
            
        return {
            "embeddings": embeddings,
            "model": "all-MiniLM-L6-v2",
            "count": len(embeddings),
            "batch_size": len(texts)
        }
    except Exception as e:
        logger.error(f"Error generating embeddings: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/shutdown")
async def graceful_shutdown():
    """Gracefully shutdown the model service"""
    import asyncio
    import os
    import signal
    
    try:
        logger.info("Graceful shutdown requested")
        
        if model_manager:
            # Unload current model to free VRAM
            await model_manager.unload_current_model()
            logger.info("Model unloaded successfully")
            
            # Clean up resources
            await model_manager.emergency_shutdown()
            logger.info("Resources cleaned up")
        else:
            logger.warning("ModelManager not available during shutdown")
        
        # Schedule service shutdown
        def shutdown_server():
            try:
                if os.name == "nt":
                    # Try CTRL_BREAK_EVENT first, fallback to SIGTERM
                    try:
                        os.kill(os.getpid(), signal.CTRL_BREAK_EVENT)
                    except (AttributeError, OSError):
                        # Fallback for Windows systems without CTRL_BREAK_EVENT
                        os.kill(os.getpid(), signal.SIGTERM)
                else:
                    os.kill(os.getpid(), signal.SIGTERM)
            except Exception as sig_error:
                logger.error(f"Error sending shutdown signal: {sig_error}")
                # Force exit as last resort
                os._exit(0)
        
        # Delay shutdown to allow response to be sent
        asyncio.get_running_loop().call_later(1.0, shutdown_server)
        
        return {"message": "Shutdown initiated successfully"}
        
    except Exception as e:
        logger.error(f"Error during graceful shutdown: {e}")
        return {"message": f"Shutdown error: {str(e)}", "status": "partial"}

# OpenAI-compatible endpoints
@app.get("/v1/models")
async def list_models():
    """OpenAI-compatible models endpoint"""
    if LM_STUDIO_MODE:
        if not lm_studio_backend:
            raise HTTPException(status_code=503, detail="LM Studio backend not ready")
        try:
            return await lm_studio_backend.get_models()
        except Exception as e:
            logger.error(f"Error fetching models from LM Studio: {e}")
            raise HTTPException(status_code=500, detail=str(e))
    else:
        # Fallback for other modes
        if not model_manager:
            raise HTTPException(status_code=503, detail="ModelManager not ready")
        
        # Convert internal model configs to OpenAI format
        models = []
        for model_type, config in getattr(model_manager, 'model_configs', {}).items():
            models.append({
                "id": model_type,
                "object": "model",
                "owned_by": "life-strands"
            })
        
        return {"data": models, "object": "list"}

@app.post("/v1/chat/completions")
async def chat_completions(request: ChatCompletionRequest):
    """OpenAI-compatible chat completions endpoint"""
    if LM_STUDIO_MODE:
        if not lm_studio_backend:
            raise HTTPException(status_code=503, detail="LM Studio backend not ready")
        
        try:
            messages = [{"role": msg.role, "content": msg.content} for msg in request.messages]
            
            if request.stream:
                import json
                
                async def generate_stream():
                    try:
                        async for token in lm_studio_backend.generate_chat_completion(
                            messages=messages,
                            model=request.model,
                            max_tokens=request.max_tokens,
                            temperature=request.temperature,
                            top_p=request.top_p,
                            stream=True
                        ):
                            # OpenAI SSE format
                            chunk = {
                                "id": "chatcmpl-123",
                                "object": "chat.completion.chunk",
                                "created": 1677652288,
                                "model": request.model or "default",
                                "choices": [{
                                    "index": 0,
                                    "delta": {"content": token},
                                    "finish_reason": None
                                }]
                            }
                            yield f"data: {json.dumps(chunk)}\n\n"
                        
                        # Send completion
                        final_chunk = {
                            "id": "chatcmpl-123",
                            "object": "chat.completion.chunk",
                            "created": 1677652288,
                            "model": request.model or "default",
                            "choices": [{
                                "index": 0,
                                "delta": {},
                                "finish_reason": "stop"
                            }]
                        }
                        yield f"data: {json.dumps(final_chunk)}\n\n"
                        yield "data: [DONE]\n\n"
                        
                    except Exception as e:
                        error_chunk = {
                            "error": {
                                "message": str(e),
                                "type": "internal_server_error"
                            }
                        }
                        yield f"data: {json.dumps(error_chunk)}\n\n"
                
                return StreamingResponse(
                    generate_stream(),
                    media_type="text/event-stream",
                    headers={
                        "Cache-Control": "no-cache",
                        "Connection": "keep-alive"
                    }
                )
            else:
                # Non-streaming
                result_text = ""
                async for token in lm_studio_backend.generate_chat_completion(
                    messages=messages,
                    model=request.model,
                    max_tokens=request.max_tokens,
                    temperature=request.temperature,
                    top_p=request.top_p,
                    stream=True
                ):
                    result_text += token
                
                return {
                    "id": "chatcmpl-123",
                    "object": "chat.completion",
                    "created": 1677652288,
                    "model": request.model or "default",
                    "choices": [{
                        "index": 0,
                        "message": {
                            "role": "assistant",
                            "content": result_text
                        },
                        "finish_reason": "stop"
                    }],
                    "usage": {
                        "prompt_tokens": 0,
                        "completion_tokens": 0,
                        "total_tokens": 0
                    }
                }
        except Exception as e:
            logger.error(f"Chat completion error: {e}")
            raise HTTPException(status_code=500, detail=str(e))
    else:
        raise HTTPException(status_code=501, detail="OpenAI API only available in LM Studio mode")

@app.post("/v1/embeddings")
async def openai_embeddings(request: OpenAIEmbeddingsRequest):
    """OpenAI-compatible embeddings endpoint"""
    if LM_STUDIO_MODE:
        if not lm_studio_backend:
            raise HTTPException(status_code=503, detail="LM Studio backend not ready")
        
        try:
            embeddings = await lm_studio_backend.generate_embeddings(
                texts=request.input,
                model=request.model
            )
            
            # Convert to OpenAI format
            data = []
            for i, embedding in enumerate(embeddings):
                data.append({
                    "object": "embedding",
                    "embedding": embedding,
                    "index": i
                })
            
            return {
                "object": "list",
                "data": data,
                "model": request.model or "default",
                "usage": {
                    "prompt_tokens": sum(len(text.split()) for text in request.input),
                    "total_tokens": sum(len(text.split()) for text in request.input)
                }
            }
        except Exception as e:
            logger.error(f"Embeddings error: {e}")
            raise HTTPException(status_code=500, detail=str(e))
    else:
        raise HTTPException(status_code=501, detail="OpenAI API only available in LM Studio mode")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8001,
        reload=False,
        log_level="info"
    )