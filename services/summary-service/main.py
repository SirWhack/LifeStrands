import asyncio
import logging
import os
from contextlib import asynccontextmanager
from typing import Dict, List, Any
from datetime import datetime

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from src.queue_consumer import QueueConsumer
from src.summary_generator import SummaryGenerator
from src.change_extractor import ChangeExtractor
from src.memory_updater import MemoryUpdater
import aiohttp

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Global components
model_service_url = os.getenv("LM_STUDIO_BASE_URL", os.getenv("MODEL_SERVICE_URL", "http://10.4.20.10:1234/v1"))
# Pin localhost for native/dev; docker-compose sets NPC_SERVICE_URL to internal DNS
npc_service_url = os.getenv("NPC_SERVICE_URL", "http://localhost:8003")

queue_consumer = QueueConsumer()
summary_generator = SummaryGenerator(model_service_url)
change_extractor = ChangeExtractor(model_service_url)
memory_updater = MemoryUpdater(npc_service_url)

class GenerateSummaryRequest(BaseModel):
    session_id: str
    npc_id: str
    user_id: str
    messages: List[Dict[str, Any]]

class ApplyUpdatesRequest(BaseModel):
    npc_id: str
    changes: List[Dict[str, Any]]

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown events"""
    try:
        await queue_consumer.initialize()
        await summary_generator.initialize()
        await change_extractor.initialize()
        await memory_updater.initialize()
        
        # Start background queue processing
        asyncio.create_task(queue_consumer.start_processing())
        
        logger.info("Summary service started successfully")
        yield
    except Exception as e:
        logger.error(f"Failed to initialize summary service: {e}")
        raise
    finally:
        await queue_consumer.stop_processing()
        logger.info("Summary service shut down")

app = FastAPI(
    title="Life Strands Summary Service",
    description="Post-conversation analysis and NPC Life Strand updates",
    version="1.0.0",
    lifespan=lifespan
)

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    queue_status = await queue_consumer.get_queue_status()
    return {
        "status": "healthy",
        "queue_length": queue_status.get("length", 0),
        "processing_active": queue_consumer.is_processing(),
        "total_processed": queue_consumer.get_processed_count()
    }

@app.post("/summary/generate")
async def generate_summary(request: GenerateSummaryRequest):
    """Generate conversation summary and extract Life Strand changes"""
    try:
        # Generate a concise summary from the messages
        summary = await summary_generator.generate_summary(request.messages)

        # Fetch NPC Life Strand context and extract changes
        life_strand = await _fetch_life_strand(request.npc_id)
        changes = await change_extractor.analyze_conversation(request.messages, life_strand)
        
        logger.info(f"Generated summary for session {request.session_id}")
        
        return {
            "session_id": request.session_id,
            "summary": summary,
            "extracted_changes": changes,
            "auto_apply": _should_auto_apply_list(changes)
        }
        
    except Exception as e:
        logger.error(f"Error generating summary for session {request.session_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/summary/apply-updates")
async def apply_npc_updates(request: ApplyUpdatesRequest):
    """Apply approved changes to NPC Life Strand"""
    try:
        await memory_updater.apply_changes(request.npc_id, request.changes)
        logger.info(f"Applied updates to NPC {request.npc_id}")
        return {"message": "Updates applied successfully"}
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error applying updates to NPC {request.npc_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/queue/status")
async def get_queue_status():
    """Get current queue processing status"""
    try:
        status = await queue_consumer.get_queue_status()
        return {
            "queue_length": status.get("length", 0),
            "processing_active": queue_consumer.is_processing(),
            "total_processed": queue_consumer.get_processed_count(),
            "failed_jobs": status.get("failed", 0),
            "average_processing_time": status.get("avg_time", 0)
        }
        
    except Exception as e:
        logger.error(f"Error getting queue status: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/queue/retry-failed")
async def retry_failed_jobs():
    """Retry failed summary generation jobs"""
    try:
        retried_count = await queue_consumer.retry_failed_jobs()
        return {"message": f"Retried {retried_count} failed jobs"}
        
    except Exception as e:
        logger.error(f"Error retrying failed jobs: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# NOTE: pending-updates/approve/reject endpoints were removed because
# they are not implemented in MemoryUpdater. Re-add them when ready.

@app.get("/stats")
async def get_service_stats():
    """Get service processing statistics"""
    try:
        stats = {
            "total_summaries_generated": summary_generator.get_total_summaries(),
            "total_updates_applied": memory_updater.get_total_updates(),
            "queue_status": await queue_consumer.get_queue_status()
        }
        
        return stats
        
    except Exception as e:
        logger.error(f"Error getting service stats: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/metrics")
async def get_metrics():
    """Get Prometheus metrics for monitoring"""
    try:
        queue_status = await queue_consumer.get_queue_status()
        return {
            "summary_service_queue_length": queue_status.get("length", 0),
            "summary_service_total_processed": queue_consumer.get_processed_count(),
            "summary_service_processing_active": 1 if queue_consumer.is_processing() else 0,
            "summary_service_status": 1
        }
        
    except Exception as e:
        logger.error(f"Error getting metrics: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/logs/npc-changes/{session_id}")
async def get_npc_change_log(session_id: str):
    """Get detailed NPC change log for a specific session"""
    try:
        import redis.asyncio as redis
        import os
        
        redis_url = os.getenv("REDIS_URL", "redis://localhost:6379")
        redis_client = redis.from_url(redis_url)
        
        log_data = await redis_client.get(f"npc_change_log:{session_id}")
        
        if not log_data:
            raise HTTPException(status_code=404, detail=f"No change log found for session {session_id}")
            
        return {
            "session_id": session_id,
            "log": log_data.decode('utf-8'),
            "retrieved_at": datetime.utcnow().isoformat()
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving NPC change log: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/logs/recent-changes")
async def get_recent_npc_changes(limit: int = 10):
    """Get recent NPC change logs"""
    try:
        import redis.asyncio as redis
        import os
        
        redis_url = os.getenv("REDIS_URL", "redis://localhost:6379")
        redis_client = redis.from_url(redis_url)
        
        # Get all change log keys
        keys = await redis_client.keys("npc_change_log:*")
        
        if not keys:
            return {"recent_changes": [], "total": 0}
            
        # Sort by key (session_id) and take most recent
        keys.sort(reverse=True)
        recent_keys = keys[:limit]
        
        logs = []
        for key in recent_keys:
            log_data = await redis_client.get(key)
            if log_data:
                session_id = key.decode('utf-8').replace('npc_change_log:', '')
                logs.append({
                    "session_id": session_id,
                    "log": log_data.decode('utf-8')
                })
        
        return {
            "recent_changes": logs,
            "total": len(keys),
            "showing": len(logs)
        }
        
    except Exception as e:
        logger.error(f"Error retrieving recent NPC changes: {e}")
        raise HTTPException(status_code=500, detail=str(e))

def _should_auto_apply_list(changes: List[Dict[str, Any]]) -> bool:
    """Auto-apply changes above confidence threshold - permissive for fictional NPCs."""
    try:
        threshold = float(os.getenv("SUMMARY_AUTO_APPROVAL_THRESHOLD", "0.6"))  # Lowered default
        if not changes:
            return False
        # Auto-apply if ANY changes meet threshold (more permissive)
        for change in changes:
            if float(change.get("confidence_score", 0.0)) >= threshold:
                return True
        return False
    except Exception as e:
        logger.error(f"Error determining auto-apply status: {e}")
        return False

async def _fetch_life_strand(npc_id: str) -> Dict[str, Any]:
    """Fetch NPC Life Strand from the NPC service for change extraction."""
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(f"{npc_service_url}/npc/{npc_id}", timeout=aiohttp.ClientTimeout(total=10)) as resp:
                if resp.status == 200:
                    return await resp.json()
                logger.warning(f"NPC service returned {resp.status} for npc_id={npc_id}")
                return {}
    except Exception as e:
        logger.error(f"Error fetching life strand for NPC {npc_id}: {e}")
        return {}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8004,
        reload=False,
        log_level="info"
    )
