import asyncio
import logging
import os
from contextlib import asynccontextmanager
from typing import Dict, List, Any, Optional

from fastapi import FastAPI, HTTPException, Query, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from src.npc_repository import NPCRepository
from src.life_strand_schema import LifeStrand, NPCUpdate
from src.embedding_manager import embedding_manager

# Graceful imports for optional monitoring components
try:
    from src.health_checker import HealthChecker
    health_checker = HealthChecker()
except ImportError:
    # Dev fallback
    class HealthChecker:
        async def initialize(self): pass
        async def start_monitoring(self): pass
        async def stop_monitoring(self): pass
        def is_monitoring(self): return False
        async def get_system_health(self): return {}
        async def get_service_status(self): return {}
        async def get_service_health(self, name): return {}
        async def restart_service(self, name): return False
        def get_uptime(self): return 0
        async def get_monitored_services(self): return []
    health_checker = HealthChecker()

try:
    from src.metrics_collector import MetricsCollector
    metrics_collector = MetricsCollector()
except ImportError:
    class MetricsCollector:
        async def initialize(self): pass
        async def start_collection(self): pass
        async def stop_collection(self): pass
        def get_metrics(self): return {}
    metrics_collector = MetricsCollector()

try:
    from src.alert_manager import AlertManager
    alert_manager = AlertManager()
except ImportError:
    class AlertManager:
        async def initialize(self): pass
        async def start_monitoring(self): pass
        async def stop_monitoring(self): pass
        async def send_alert(self, alert): pass
    alert_manager = AlertManager()

try:
    from src.websocket_broadcaster import WebSocketBroadcaster
    websocket_broadcaster = WebSocketBroadcaster()
except ImportError:
    import uuid
    class WebSocketBroadcaster:
        def __init__(self):
            self.connections = {}
        async def initialize(self): pass
        async def start_broadcasting(self): pass
        async def stop_broadcasting(self): pass
        def add_connection(self, websocket): 
            client_id = str(uuid.uuid4())
            self.connections[client_id] = websocket
            return client_id
        def remove_connection(self, client_id):
            self.connections.pop(client_id, None)
        async def broadcast(self, message): pass
    websocket_broadcaster = WebSocketBroadcaster()

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Global components
database_url = os.getenv("DATABASE_URL", "postgresql://lifestrands_user:lifestrands_password@postgres:5432/lifestrands")
npc_repository = NPCRepository(database_url)

class CreateNPCRequest(BaseModel):
    life_strand: LifeStrand

class SearchNPCsRequest(BaseModel):
    query: str
    limit: int = 10

class UpdateNPCRequest(BaseModel):
    updates: NPCUpdate

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown events"""
    tasks: List[asyncio.Task] = []
    try:
        await npc_repository.initialize()
        await embedding_manager.initialize()
        await health_checker.initialize()
        await metrics_collector.initialize()
        await alert_manager.initialize()
        await websocket_broadcaster.initialize()

        tasks.append(asyncio.create_task(health_checker.start_monitoring()))
        tasks.append(asyncio.create_task(metrics_collector.start_collection()))
        tasks.append(asyncio.create_task(alert_manager.start_monitoring()))
        tasks.append(asyncio.create_task(websocket_broadcaster.start_broadcasting()))
        
        logger.info("NPC service started successfully")
        yield
    except Exception as e:
        logger.error(f"Failed to initialize NPC service: {e}")
        raise
    finally:
        await health_checker.stop_monitoring()
        await metrics_collector.stop_collection()
        await alert_manager.stop_monitoring()
        await websocket_broadcaster.stop_broadcasting()
        
        for t in tasks:
            if not t.done():
                t.cancel()
                try:
                    await t
                except asyncio.CancelledError:
                    pass
        
        await npc_repository.close()
        logger.info("NPC service shut down")

app = FastAPI(
    title="Life Strands NPC Service",
    description="NPC Life Strand management with vector search",
    version="1.0.0",
    lifespan=lifespan
)

# Add CORS middleware for frontend access
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",  # React frontend
        "http://localhost:3001",  # Alternative frontend port
        "http://localhost:3002",  # Admin dashboard
        "http://127.0.0.1:3000",
        "http://127.0.0.1:3001",
        "http://127.0.0.1:3002"
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    npc_count = await npc_repository.get_npc_count()
    return {
        "status": "healthy",
        "total_npcs": npc_count,
        "embeddings_enabled": embedding_manager.is_enabled(),
        "health_monitoring": health_checker.is_monitoring(),
        "database": "connected" if npc_repository.pool else "disconnected"
    }

@app.post("/npc", response_model=Dict[str, str])
async def create_npc(request: CreateNPCRequest):
    """Create a new NPC with Life Strand data"""
    try:
        # Convert Pydantic model to dict for repository
        ls_dict = request.life_strand.model_dump(exclude_none=True)
        npc_id = await npc_repository.create_npc(ls_dict)
        
        # Generate and persist embedding if enabled
        if embedding_manager.is_enabled():
            vec = await embedding_manager.generate_npc_embedding(ls_dict)
            await npc_repository.upsert_embedding(npc_id, vec)
            
        logger.info(f"Created NPC {npc_id}")
        return {"npc_id": npc_id}
        
    except Exception as e:
        logger.error(f"Error creating NPC: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/npc/{npc_id}", response_model=LifeStrand)
async def get_npc(npc_id: str):
    """Get NPC Life Strand by ID"""
    try:
        life_strand = await npc_repository.get_npc(npc_id)
        if not life_strand:
            raise HTTPException(status_code=404, detail="NPC not found")
        return life_strand
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting NPC {npc_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/npc/{npc_id}/prompt")
async def get_npc_for_prompt(npc_id: str):
    """Get NPC data optimized for LLM context"""
    try:
        life_strand = await npc_repository.get_npc(npc_id)
        if not life_strand:
            raise HTTPException(status_code=404, detail="NPC not found")
            
        # Convert to prompt-optimized format with safe dict access
        bg = life_strand.get("background", {}) or {}
        personality = life_strand.get("personality", {}) or {}
        current = life_strand.get("current_status", {}) or {}
        relationships = life_strand.get("relationships", {}) or {}
        memories = life_strand.get("memories", []) or []
        knowledge = life_strand.get("knowledge", []) or []
        
        prompt_data = {
            "name": life_strand.get("name"),
            "age": bg.get("age"),
            "occupation": bg.get("occupation"),
            "location": current.get("location", bg.get("location")),
            "personality_traits": personality.get("traits", [])[:10],
            "current_mood": current.get("mood"),
            "current_activity": current.get("current_activity") or current.get("activity"),
            "recent_memories": memories[-10:],
            "key_relationships": [
                {"person": k, **(v or {})}
                for k, v in relationships.items()
                if (v or {}).get("intensity", 0) >= 7
            ][:5],
            "knowledge_areas": [k.get("topic") for k in knowledge if isinstance(k, dict) and k.get("topic")][:10]
        }
        
        return prompt_data
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting NPC prompt data for {npc_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.put("/npc/{npc_id}")
async def update_npc(npc_id: str, request: UpdateNPCRequest):
    """Update NPC Life Strand with new information"""
    try:
        # Convert Pydantic model to dict for repository
        updates = request.updates.model_dump(exclude_none=True)
        success = await npc_repository.update_npc(npc_id, updates)
        if not success:
            raise HTTPException(status_code=404, detail="NPC not found")
            
        # Update embeddings if enabled
        if embedding_manager.is_enabled():
            updated_life_strand = await npc_repository.get_npc(npc_id)
            vec = await embedding_manager.generate_npc_embedding(updated_life_strand)
            await npc_repository.upsert_embedding(npc_id, vec)
            
        return {"message": "NPC updated successfully"}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating NPC {npc_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.delete("/npc/{npc_id}")
async def delete_npc(npc_id: str):
    """Delete an NPC"""
    try:
        success = await npc_repository.archive_npc(npc_id)
        if not success:
            raise HTTPException(status_code=404, detail="NPC not found")
            
        # Clear embedding if enabled
        if embedding_manager.is_enabled():
            await npc_repository.clear_embedding(npc_id)
            
        return {"message": "NPC deleted successfully"}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting NPC {npc_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/npcs")
async def list_npcs(
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0)
):
    """List all NPCs with pagination"""
    try:
        npcs = await npc_repository.list_npcs(limit=limit, offset=offset)
        total = await npc_repository.get_npc_count()
        
        return {
            "npcs": npcs,
            "total": total,
            "limit": limit,
            "offset": offset
        }
        
    except Exception as e:
        logger.error(f"Error listing NPCs: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/npcs/search")
async def search_npcs(request: SearchNPCsRequest):
    """Semantic search for NPCs using embeddings"""
    try:
        if not embedding_manager.is_enabled():
            raise HTTPException(
                status_code=400, 
                detail="Vector search not enabled"
            )
            
        # Generate query embedding and search
        query_vec = await embedding_manager.generate_embedding(request.query.strip())
        results = await npc_repository.search_by_embedding(query_vec, limit=request.limit)
        
        return {"results": results}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error searching NPCs: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/npc/{npc_id}/memories")
async def get_npc_memories(npc_id: str):
    """Get NPC conversation memories"""
    try:
        life_strand = await npc_repository.get_npc(npc_id)
        if not life_strand:
            raise HTTPException(status_code=404, detail="NPC not found")
            
        return {"memories": life_strand.get("memories", [])}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting memories for NPC {npc_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/npc/{npc_id}/memory")
async def add_npc_memory(npc_id: str, memory: Dict[str, Any]):
    """Add a new memory to an NPC"""
    try:
        success = await npc_repository.add_memory(npc_id, memory)
        if not success:
            raise HTTPException(status_code=404, detail="NPC not found")
            
        return {"message": "Memory added successfully"}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error adding memory to NPC {npc_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/npc/{npc_id}/relationships")
async def get_npc_relationships(npc_id: str):
    """Get NPC relationships"""
    try:
        life_strand = await npc_repository.get_npc(npc_id)
        if not life_strand:
            raise HTTPException(status_code=404, detail="NPC not found")
            
        return {"relationships": life_strand.get("relationships", {})}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting relationships for NPC {npc_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/stats")
async def get_service_stats():
    """Get service statistics"""
    try:
        stats = await npc_repository.get_stats()
        return {
            "npc_count": stats["npc_count"],
            "total_memories": stats["total_memories"],
            "avg_relationships_per_npc": stats["avg_relationships"],
            "embeddings_enabled": embedding_manager.is_enabled()
        }
        
    except Exception as e:
        logger.error(f"Error getting service stats: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/metrics")
async def get_metrics():
    """Get Prometheus metrics for monitoring"""
    try:
        stats = await npc_repository.get_stats()
        return {
            "npc_service_npc_count": stats["npc_count"],
            "npc_service_total_memories": stats["total_memories"],
            "npc_service_avg_relationships_per_npc": stats["avg_relationships"],
            "npc_service_embeddings_enabled": 1 if embedding_manager.is_enabled() else 0,
            "npc_service_status": 1
        }
        
    except Exception as e:
        logger.error(f"Error getting metrics: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.websocket("/ws/monitor")
async def monitor_websocket(websocket: WebSocket):
    """WebSocket endpoint for real-time monitoring updates"""
    await websocket.accept()
    client_id = None
    try:
        client_id = websocket_broadcaster.add_connection(websocket)
        logger.info(f"Monitor WebSocket connected: {client_id}")
        
        while True:
            # Send periodic updates or wait for messages
            await websocket.receive_text()  # Keep connection alive
            
    except WebSocketDisconnect:
        logger.info(f"Monitor WebSocket disconnected: {client_id}")
    except Exception as e:
        logger.error(f"Monitor WebSocket error: {e}")
    finally:
        if client_id is not None:
            websocket_broadcaster.remove_connection(client_id)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8003,
        reload=False,
        log_level="info"
    )