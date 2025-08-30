"""
Mock Model Service Main Application

A lightweight version of the model service that uses canned responses
for testing other services without requiring GPU resources or model files.
"""

import asyncio
import logging
import os
from contextlib import asynccontextmanager

# Configure logging FIRST
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import List
from datetime import datetime

# Import mock implementation
from src.mock_model_service import MockModelManager, mock_model_service

# Global mock manager
mock_manager = None

class GenerateRequest(BaseModel):
    prompt: str
    model_type: str = "chat"
    service_type: str = "chat"
    max_tokens: int = 512
    temperature: float = 0.7
    top_p: float = 0.9
    stream: bool = True
    priority: int = None
    timeout: float = 300.0

class LoadModelRequest(BaseModel):
    model_type: str

class EmbeddingsRequest(BaseModel):
    texts: List[str]
    priority: int = 3
    timeout: float = 60.0

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown for mock service"""
    global mock_manager
    logger.info("=== STARTING MOCK MODEL SERVICE ===")
    
    try:
        # Initialize mock manager
        mock_manager = MockModelManager()
        await mock_manager.initialize()
        
        # Load default chat model
        await mock_manager.load_model("chat")
        
        logger.info("=== MOCK MODEL SERVICE READY ===")
        yield
        
    except Exception as e:
        logger.error(f"Failed to initialize mock service: {e}")
        raise
    finally:
        logger.info("=== SHUTTING DOWN MOCK MODEL SERVICE ===")
        
        if mock_manager:
            await mock_manager.emergency_shutdown()
            
        logger.info("Mock model service shut down")

app = FastAPI(
    title="Life Strands Mock Model Service",
    description="Mock GPU model service for testing with canned responses",
    version="1.0.0-mock",
    lifespan=lifespan
)

@app.get("/ping")
async def ping():
    """Simple ping endpoint"""
    logger.info("Ping endpoint called")
    return {"message": "pong", "service": "mock-model-service"}

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    logger.info("Health check endpoint called")
    
    if not mock_manager:
        return {"status": "degraded", "error": "MockManager not initialized"}
        
    try:
        status = await mock_manager.get_model_status()
        return {"status": "healthy", "model_status": status, "mock_mode": True}
    except Exception as e:
        logger.error(f"Health check error: {e}")
        return {"status": "error", "error": str(e), "mock_mode": True}

@app.post("/generate")
async def generate_text(request: GenerateRequest):
    """Generate text with mock responses"""
    if not mock_manager:
        raise HTTPException(status_code=503, detail="MockManager not ready")
    
    try:
        logger.info(f"Mock generation request: {request.model_type}, stream: {request.stream}")
        
        # Load model if needed
        if mock_manager.current_model_type != request.model_type:
            success = await mock_manager.load_model(request.model_type)
            if not success:
                raise HTTPException(
                    status_code=500, 
                    detail=f"Failed to load mock {request.model_type} model"
                )
        
        params = {
            "max_tokens": request.max_tokens,
            "temperature": request.temperature,
            "top_p": request.top_p
        }
        
        if request.stream:
            import json
            
            async def generate_stream():
                try:
                    async for token in mock_manager.generate_stream(request.prompt, params):
                        token_data = json.dumps({"token": token})
                        yield f"data: {token_data}\n\n"
                    
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
            result = await mock_manager.generate_completion(request.prompt, params)
            return {"text": result}
            
    except Exception as e:
        logger.error(f"Mock generation error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/load-model")
async def load_model(request: LoadModelRequest):
    """Load mock model"""
    logger.info(f"Mock load model request: {request.model_type}")
    
    if not mock_manager:
        raise HTTPException(status_code=500, detail="MockManager not initialized")
        
    try:
        success = await mock_manager.load_model(request.model_type)
        if success:
            return {"message": f"Successfully loaded mock {request.model_type} model"}
        else:
            raise HTTPException(
                status_code=500,
                detail=f"Failed to load mock {request.model_type} model"
            )
    except Exception as e:
        logger.error(f"Mock model loading error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/unload-model")
async def unload_model():
    """Unload current mock model"""
    if not mock_manager:
        raise HTTPException(status_code=503, detail="MockManager not ready")
        
    try:
        await mock_manager.unload_current_model()
        return {"message": "Mock model unloaded successfully"}
    except Exception as e:
        logger.error(f"Mock model unloading error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/status")
async def get_status():
    """Get detailed mock model status"""
    if not mock_manager:
        raise HTTPException(status_code=503, detail="MockManager not ready")
        
    status = await mock_manager.get_model_status()
    
    # Add mock state history
    status["state_history"] = await mock_manager.state_machine.get_state_history()
    
    return status

@app.post("/switch/{model_type}")
async def switch_model(model_type: str):
    """Switch mock model"""
    if not mock_manager:
        raise HTTPException(status_code=503, detail="MockManager not ready")
        
    try:
        if model_type not in mock_manager.model_configs:
            raise HTTPException(404, f"Mock model type '{model_type}' not found")
        
        success = await mock_manager.load_model(model_type)
        if success:
            config = mock_manager.model_configs[model_type]
            return {
                "status": "success",
                "model_type": model_type,
                "model_name": config["name"],
                "model_size": config["size"],
                "context_size": config["context_size"],
                "mock_mode": True
            }
        else:
            raise HTTPException(500, f"Failed to load mock {model_type} model")
    except Exception as e:
        logger.error(f"Mock model switching error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/vram")
async def get_vram_usage():
    """Get mock VRAM usage"""
    if not mock_manager:
        raise HTTPException(status_code=503, detail="MockManager not ready")
        
    return await mock_manager.monitor_vram()

@app.post("/emergency-shutdown")
async def emergency_shutdown():
    """Emergency mock service cleanup"""
    if not mock_manager:
        raise HTTPException(status_code=503, detail="MockManager not ready")
        
    try:
        await mock_manager.emergency_shutdown()
        return {"message": "Mock emergency shutdown completed"}
    except Exception as e:
        logger.error(f"Mock emergency shutdown error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/metrics")
async def get_metrics():
    """Get mock service metrics"""
    try:
        metrics = {
            "service": "mock-model-service",
            "timestamp": datetime.utcnow().isoformat(),
            "mock_mode": True,
            "uptime": "healthy" if mock_manager else "unhealthy"
        }
        
        if mock_manager:
            status = await mock_manager.get_model_status()
            metrics["model_status"] = status
            metrics["request_stats"] = mock_model_service.get_request_stats()
        
        return metrics
        
    except Exception as e:
        return {
            "service": "mock-model-service", 
            "timestamp": datetime.utcnow().isoformat(),
            "status": "error",
            "error": str(e),
            "mock_mode": True
        }

@app.post("/embeddings")
async def generate_embeddings(request: EmbeddingsRequest):
    """Generate mock embeddings"""
    if not mock_manager:
        raise HTTPException(status_code=503, detail="MockManager not ready")
        
    try:
        texts = request.texts
        if not texts:
            raise HTTPException(status_code=400, detail="No texts provided")
        
        logger.info(f"Mock embedding request for {len(texts)} texts")
        embeddings = await mock_manager.generate_embeddings(texts)
            
        return {
            "embeddings": embeddings,
            "model": "mock-embedding-model",
            "count": len(embeddings),
            "batch_size": len(texts),
            "mock_mode": True
        }
    except Exception as e:
        logger.error(f"Error generating mock embeddings: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# Mock-specific endpoints

@app.get("/mock-info")
async def get_mock_info():
    """Get information about mock service capabilities"""
    return {
        "service": "mock-model-service",
        "description": "Mock implementation for testing without GPU resources",
        "features": [
            "Streaming text generation",
            "Model hot-swapping simulation", 
            "Embedding generation",
            "VRAM monitoring simulation",
            "Realistic response timing",
            "Contextual canned responses"
        ],
        "available_models": list(mock_model_service.model_configs.keys()) if mock_manager else [],
        "response_sets": {
            "chat": len(mock_model_service.chat_responses),
            "summary": len(mock_model_service.summary_responses), 
            "npc": len(mock_model_service.npc_responses)
        },
        "mock_mode": True
    }

@app.post("/mock-config")
async def update_mock_config(config: dict):
    """Update mock service configuration"""
    if not mock_manager:
        raise HTTPException(status_code=503, detail="MockManager not ready")
        
    try:
        # Update generation speed
        if "generation_speed" in config:
            mock_model_service.generation_speed = max(1, min(100, config["generation_speed"]))
            
        # Update VRAM usage simulation
        if "mock_vram_usage" in config:
            mock_model_service.mock_vram_usage = max(0, min(24000, config["mock_vram_usage"]))
            
        return {
            "message": "Mock configuration updated",
            "current_config": {
                "generation_speed": mock_model_service.generation_speed,
                "mock_vram_usage": mock_model_service.mock_vram_usage,
                "current_model": mock_model_service.current_model_type
            }
        }
    except Exception as e:
        logger.error(f"Error updating mock config: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/mock-stats")
async def get_mock_stats():
    """Get detailed mock service statistics"""
    if not mock_manager:
        raise HTTPException(status_code=503, detail="MockManager not ready")
        
    return mock_model_service.get_request_stats()

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main_mock:app",
        host="0.0.0.0", 
        port=8001,
        reload=False,
        log_level="info"
    )