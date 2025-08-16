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

try:
    from src.model_manager import ModelManager
except ImportError:
    # Fallback for when running directly from model-service directory
    from model_manager import ModelManager

# Global model manager instance
model_manager = None

class GenerateRequest(BaseModel):
    prompt: str
    model_type: str = "chat"
    max_tokens: int = 512
    temperature: float = 0.7
    top_p: float = 0.9
    stream: bool = True

class LoadModelRequest(BaseModel):
    model_type: str

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown events"""
    global model_manager
    logger.info("=== STARTING MODEL SERVICE ===")
    try:
        logger.info("Creating ModelManager instance...")
        model_manager = ModelManager()
        logger.info("ModelManager created, calling initialize()...")
        await model_manager.initialize()
        logger.info("ModelManager initialized successfully!")
        logger.info("=== MODEL SERVICE READY ===")
        yield
    except Exception as e:
        logger.error(f"Failed to initialize model service: {e}")
        logger.error("Full traceback:", exc_info=True)
        # Don't raise - let service start in degraded mode
        if not model_manager:
            logger.warning("Creating fallback ModelManager...")
            model_manager = ModelManager()  # Create a basic instance
        yield
    finally:
        logger.info("=== SHUTTING DOWN MODEL SERVICE ===")
        if model_manager:
            await model_manager.emergency_shutdown()
        logger.info("Model service shut down")

import platform
is_windows = platform.system() == "Windows"

app = FastAPI(
    title=f"Life Strands Model Service - {'Windows ROCm' if is_windows else 'Docker'}",
    description="Unified GPU model management and text generation service with full layer offloading",
    version="2.0.0",
    lifespan=lifespan
)

@app.get("/ping")
async def ping():
    """Simple ping endpoint"""
    print("=== PING CALLED ===")
    logger.info("Ping endpoint called")
    return {"message": "pong", "service": "model-service"}

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    print("=== HEALTH CHECK CALLED ===")  # Direct print to console
    logger.info("Health check endpoint called")  # Changed to INFO level
    if not model_manager:
        logger.warning("Health check: ModelManager not initialized")
        return {"status": "degraded", "error": "ModelManager not initialized"}
    try:
        logger.debug("Getting model status...")
        status = await model_manager.get_model_status()
        logger.debug(f"Model status retrieved: {status}")
        return {"status": "healthy", "model_status": status}
    except Exception as e:
        logger.error(f"Health check error: {e}", exc_info=True)
        return {"status": "error", "error": str(e)}

@app.post("/generate")
async def generate_text(request: GenerateRequest):
    """Generate text with streaming or completion mode"""
    try:
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
            async def generate_stream():
                async for token in model_manager.generate_stream(request.prompt, params):
                    yield f"data: {token}\n\n"
                yield "data: [DONE]\n\n"
            
            return StreamingResponse(
                generate_stream(), 
                media_type="text/event-stream"
            )
        else:
            result = await model_manager.generate_completion(request.prompt, params)
            return {"text": result}
            
    except Exception as e:
        logger.error(f"Generation error: {e}")
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
    try:
        await model_manager.unload_current_model()
        return {"message": "Model unloaded successfully"}
    except Exception as e:
        logger.error(f"Model unloading error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/status")
async def get_status():
    """Get detailed model and GPU status"""
    return await model_manager.get_model_status()

@app.post("/switch/{model_type}")
async def switch_model(model_type: str):
    """Windows-compatible model switching endpoint"""
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
    return await model_manager.monitor_vram()

@app.post("/emergency-shutdown")
async def emergency_shutdown():
    """Emergency model cleanup"""
    try:
        await model_manager.emergency_shutdown()
        return {"message": "Emergency shutdown completed"}
    except Exception as e:
        logger.error(f"Emergency shutdown error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/metrics")
async def get_metrics():
    """Get service metrics for monitoring"""
    from datetime import datetime
    try:
        status = await model_manager.get_model_status()
        return {
            "service": "model-service",
            "timestamp": datetime.utcnow().isoformat(),
            "status": status,
            "uptime": "healthy" if model_manager else "unhealthy"
        }
    except Exception as e:
        return {
            "service": "model-service",
            "timestamp": datetime.utcnow().isoformat(),
            "status": "error",
            "error": str(e)
        }

@app.post("/embeddings")
async def generate_embeddings(request: dict):
    """Generate embeddings for texts"""
    try:
        texts = request.get("texts", [])
        if not texts:
            raise HTTPException(status_code=400, detail="No texts provided")
            
        embeddings = await model_manager.generate_embeddings(texts)
        return {
            "embeddings": embeddings,
            "model": "all-MiniLM-L6-v2",
            "count": len(embeddings)
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
        
        # Unload current model to free VRAM
        await model_manager.unload_current_model()
        logger.info("Model unloaded successfully")
        
        # Clean up resources
        await model_manager.emergency_shutdown()
        logger.info("Resources cleaned up")
        
        # Schedule service shutdown
        def shutdown_server():
            os.kill(os.getpid(), signal.SIGTERM)
        
        # Delay shutdown to allow response to be sent
        asyncio.get_event_loop().call_later(1.0, shutdown_server)
        
        return {"message": "Shutdown initiated successfully"}
        
    except Exception as e:
        logger.error(f"Error during graceful shutdown: {e}")
        return {"message": f"Shutdown error: {str(e)}", "status": "partial"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8001,
        reload=False,
        log_level="info"
    )