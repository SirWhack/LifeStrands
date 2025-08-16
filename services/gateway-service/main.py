import asyncio
import logging
import time
from contextlib import asynccontextmanager
from typing import Dict, List, Any

from fastapi import FastAPI, Request, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel

from src.auth import AuthManager
from src.router import APIRouter as ServiceRouter

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Global components
auth_manager = AuthManager()
service_router = ServiceRouter()
start_time = time.time()  # Track service startup time
security = HTTPBearer()

class LoginRequest(BaseModel):
    username: str
    password: str

class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown events"""
    try:
        await auth_manager.initialize()
        await service_router.initialize()
        
        logger.info("Gateway service started successfully")
        yield
    except Exception as e:
        logger.error(f"Failed to initialize gateway service: {e}")
        raise
    finally:
        logger.info("Gateway service shut down")

app = FastAPI(
    title="Life Strands API Gateway",
    description="Main API gateway for the Life Strands system",
    version="1.0.0",
    lifespan=lifespan
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:3001", "http://localhost:3002"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Add rate limiting middleware
from src.rate_limiter import rate_limit_middleware
app.middleware("http")(rate_limit_middleware)

async def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)):
    """Verify JWT token and get current user"""
    try:
        payload = await auth_manager.authenticate_request(credentials.credentials)
        if not payload:
            raise HTTPException(
                status_code=401,
                detail="Invalid authentication credentials",
                headers={"WWW-Authenticate": "Bearer"},
            )
        return payload
    except Exception as e:
        raise HTTPException(
            status_code=401,
            detail="Invalid authentication credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "services": await service_router.get_service_health()
    }

@app.post("/auth/login", response_model=TokenResponse)
async def login(request: LoginRequest):
    """Authenticate user and return JWT token"""
    try:
        access_token = await auth_manager.create_session(request.username, request.password)
        if not access_token:
            raise HTTPException(
                status_code=401,
                detail="Incorrect username or password"
            )
        
        return TokenResponse(access_token=access_token)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Login error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")

@app.post("/auth/register")
async def register(request: LoginRequest):
    """Register new user account"""
    try:
        from src.auth import UserRole
        user_id = await auth_manager.create_user(
            request.username, 
            f"{request.username}@lifestrands.local", 
            request.password, 
            UserRole.USER
        )
        if user_id:
            return {"message": "User registered successfully", "user_id": user_id}
        else:
            raise HTTPException(
                status_code=400,
                detail="Username already exists"
            )
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Registration error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")

@app.get("/auth/me")
async def get_current_user_info(current_user: dict = Depends(get_current_user)):
    """Get current user information"""
    return {
        "username": current_user.get("username"),
        "user_id": current_user.get("user_id"),
        "role": current_user.get("role")
    }

# Model Service Routes
@app.post("/model/generate")
async def model_generate(
    request: Dict[str, Any],
    current_user: dict = Depends(get_current_user)
):
    """Proxy to model service for text generation"""
    return await service_router.proxy_request(
        "model-service",
        "POST",
        "/generate",
        json=request,
        headers={"user-id": current_user.get("user_id")}
    )

@app.post("/model/load-model")
async def model_load(
    request: Dict[str, Any],
    current_user: dict = Depends(get_current_user)
):
    """Proxy to model service for model loading"""
    return await service_router.proxy_request(
        "model-service",
        "POST", 
        "/load-model",
        json=request
    )

@app.get("/model/status")
async def model_status():
    """Proxy to model service for status"""
    return await service_router.proxy_request(
        "model-service",
        "GET",
        "/status"
    )

# Chat Service Routes
@app.post("/chat/conversation/start")
async def chat_start_conversation(
    request: Dict[str, Any],
    current_user: dict = Depends(get_current_user)
):
    """Proxy to chat service to start conversation"""
    # Add user_id to request
    request["user_id"] = current_user.get("user_id")
    
    return await service_router.proxy_request(
        "chat-service",
        "POST",
        "/conversation/start",
        json=request
    )

@app.post("/chat/conversation/send")
async def chat_send_message(
    request: Dict[str, Any],
    current_user: dict = Depends(get_current_user)
):
    """Proxy to chat service to send message"""
    return await service_router.proxy_request(
        "chat-service",
        "POST",
        "/conversation/send",
        json=request,
        headers={"user-id": current_user.get("user_id")}
    )

@app.post("/chat/conversation/{session_id}/end")
async def chat_end_conversation(
    session_id: str,
    current_user: dict = Depends(get_current_user)
):
    """Proxy to chat service to end conversation"""
    return await service_router.proxy_request(
        "chat-service",
        "POST",
        f"/conversation/{session_id}/end"
    )

@app.get("/chat/conversation/{session_id}/history")
async def chat_get_history(
    session_id: str,
    current_user: dict = Depends(get_current_user)
):
    """Proxy to chat service to get conversation history"""
    return await service_router.proxy_request(
        "chat-service",
        "GET",
        f"/conversation/{session_id}/history"
    )

# NPC Service Routes
@app.post("/npc")
async def npc_create(
    request: Dict[str, Any],
    current_user: dict = Depends(get_current_user)
):
    """Proxy to NPC service to create NPC"""
    return await service_router.proxy_request(
        "npc-service",
        "POST",
        "/npc",
        json=request
    )

@app.get("/npc/{npc_id}")
async def npc_get(npc_id: str):
    """Proxy to NPC service to get NPC"""
    return await service_router.proxy_request(
        "npc-service",
        "GET",
        f"/npc/{npc_id}"
    )

@app.put("/npc/{npc_id}")
async def npc_update(
    npc_id: str,
    request: Dict[str, Any],
    current_user: dict = Depends(get_current_user)
):
    """Proxy to NPC service to update NPC"""
    return await service_router.proxy_request(
        "npc-service",
        "PUT",
        f"/npc/{npc_id}",
        json=request
    )

@app.get("/npcs")
async def npc_list(
    limit: int = 50,
    offset: int = 0
):
    """Proxy to NPC service to list NPCs"""
    return await service_router.proxy_request(
        "npc-service",
        "GET",
        f"/npcs?limit={limit}&offset={offset}"
    )

@app.post("/npcs/search")
async def npc_search(request: Dict[str, Any]):
    """Proxy to NPC service for semantic search"""
    return await service_router.proxy_request(
        "npc-service",
        "POST",
        "/npcs/search",
        json=request
    )

# Summary Service Routes
@app.post("/summary/generate")
async def summary_generate(
    request: Dict[str, Any],
    current_user: dict = Depends(get_current_user)
):
    """Proxy to summary service for conversation summary"""
    return await service_router.proxy_request(
        "summary-service",
        "POST",
        "/summary/generate",
        json=request
    )

@app.get("/summary/queue/status")
async def summary_queue_status():
    """Proxy to summary service for queue status"""
    return await service_router.proxy_request(
        "summary-service",
        "GET",
        "/queue/status"
    )

# Monitor Service Routes
@app.get("/monitor/system/health")
async def monitor_system_health():
    """Proxy to monitor service for system health"""
    return await service_router.proxy_request(
        "monitor-service",
        "GET",
        "/system/health"
    )

@app.get("/monitor/metrics")
async def monitor_metrics():
    """Proxy to monitor service for current metrics"""
    return await service_router.proxy_request(
        "monitor-service",
        "GET",
        "/metrics"
    )

@app.get("/monitor/alerts")
async def monitor_alerts():
    """Proxy to monitor service for active alerts"""
    return await service_router.proxy_request(
        "monitor-service",
        "GET",
        "/alerts"
    )

@app.get("/services/status")
async def get_all_service_status():
    """Get status of all backend services"""
    return await service_router.get_service_health()

@app.get("/metrics")
async def get_metrics():
    """Prometheus-style metrics endpoint for monitoring"""
    try:
        import psutil
        import time
        
        # Basic system metrics
        cpu_usage = psutil.cpu_percent()
        memory = psutil.virtual_memory()
        disk = psutil.disk_usage('/')
        
        # Gateway-specific metrics
        uptime = time.time() - start_time
        
        metrics = []
        metrics.append(f"# HELP gateway_cpu_usage_percent CPU usage percentage")
        metrics.append(f"# TYPE gateway_cpu_usage_percent gauge")
        metrics.append(f"gateway_cpu_usage_percent {cpu_usage}")
        
        metrics.append(f"# HELP gateway_memory_usage_percent Memory usage percentage")
        metrics.append(f"# TYPE gateway_memory_usage_percent gauge") 
        metrics.append(f"gateway_memory_usage_percent {memory.percent}")
        
        metrics.append(f"# HELP gateway_disk_usage_percent Disk usage percentage")
        metrics.append(f"# TYPE gateway_disk_usage_percent gauge")
        metrics.append(f"gateway_disk_usage_percent {disk.percent}")
        
        metrics.append(f"# HELP gateway_uptime_seconds Service uptime in seconds")
        metrics.append(f"# TYPE gateway_uptime_seconds counter")
        metrics.append(f"gateway_uptime_seconds {uptime}")
        
        return "\n".join(metrics)
        
    except Exception as e:
        logger.error(f"Error generating metrics: {e}")
        return "# Error generating metrics"

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=False,
        log_level="info"
    )