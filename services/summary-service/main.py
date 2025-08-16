import asyncio
import logging
import os
from contextlib import asynccontextmanager
from typing import Dict, List, Any

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from src.queue_consumer import QueueConsumer
from src.summary_generator import SummaryGenerator
from src.change_extractor import ChangeExtractor
from src.memory_updater import MemoryUpdater

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Global components
model_service_url = os.getenv("MODEL_SERVICE_URL", "http://host.docker.internal:8001")
npc_service_url = os.getenv("NPC_SERVICE_URL", "http://npc-service:8003")

queue_consumer = QueueConsumer()
summary_generator = SummaryGenerator(model_service_url)
change_extractor = ChangeExtractor()
memory_updater = MemoryUpdater(npc_service_url)

class GenerateSummaryRequest(BaseModel):
    session_id: str
    npc_id: str
    user_id: str
    messages: List[Dict[str, Any]]

class ApplyUpdatesRequest(BaseModel):
    npc_id: str
    updates: Dict[str, Any]

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
        # Generate summary
        summary = await summary_generator.generate_conversation_summary(
            request.session_id,
            request.npc_id,
            request.user_id,
            request.messages
        )
        
        # Extract potential changes
        changes = await change_extractor.extract_changes(
            request.npc_id,
            request.messages,
            summary
        )
        
        logger.info(f"Generated summary for session {request.session_id}")
        
        return {
            "session_id": request.session_id,
            "summary": summary,
            "extracted_changes": changes,
            "auto_apply": await _should_auto_apply(changes)
        }
        
    except Exception as e:
        logger.error(f"Error generating summary for session {request.session_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/summary/apply-updates")
async def apply_npc_updates(request: ApplyUpdatesRequest):
    """Apply approved changes to NPC Life Strand"""
    try:
        success = await memory_updater.apply_updates(
            request.npc_id,
            request.updates
        )
        
        if success:
            logger.info(f"Applied updates to NPC {request.npc_id}")
            return {"message": "Updates applied successfully"}
        else:
            raise HTTPException(status_code=404, detail="NPC not found")
            
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

@app.get("/npc/{npc_id}/pending-updates")
async def get_pending_updates(npc_id: str):
    """Get pending Life Strand updates for review"""
    try:
        updates = await memory_updater.get_pending_updates(npc_id)
        return {"pending_updates": updates}
        
    except Exception as e:
        logger.error(f"Error getting pending updates for NPC {npc_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/npc/{npc_id}/approve-update/{update_id}")
async def approve_pending_update(npc_id: str, update_id: str):
    """Approve a pending Life Strand update"""
    try:
        success = await memory_updater.approve_update(npc_id, update_id)
        
        if success:
            return {"message": "Update approved and applied"}
        else:
            raise HTTPException(status_code=404, detail="Update not found")
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error approving update {update_id} for NPC {npc_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.delete("/npc/{npc_id}/reject-update/{update_id}")
async def reject_pending_update(npc_id: str, update_id: str):
    """Reject a pending Life Strand update"""
    try:
        success = await memory_updater.reject_update(npc_id, update_id)
        
        if success:
            return {"message": "Update rejected"}
        else:
            raise HTTPException(status_code=404, detail="Update not found")
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error rejecting update {update_id} for NPC {npc_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/stats")
async def get_service_stats():
    """Get service processing statistics"""
    try:
        stats = {
            "total_summaries_generated": summary_generator.get_total_summaries(),
            "total_updates_applied": memory_updater.get_total_updates(),
            "queue_status": await queue_consumer.get_queue_status(),
            "auto_approval_rate": await _get_auto_approval_rate()
        }
        
        return stats
        
    except Exception as e:
        logger.error(f"Error getting service stats: {e}")
        raise HTTPException(status_code=500, detail=str(e))

async def _should_auto_apply(changes: Dict[str, Any]) -> bool:
    """Determine if changes should be auto-applied based on confidence scores"""
    try:
        # Get auto-approval threshold from environment
        import os
        threshold = float(os.getenv("SUMMARY_AUTO_APPROVAL_THRESHOLD", "0.8"))
        
        # Check confidence scores for all changes
        for change in changes.get("memory_updates", []):
            if change.get("confidence", 0) < threshold:
                return False
                
        for change in changes.get("relationship_updates", []):
            if change.get("confidence", 0) < threshold:
                return False
                
        for change in changes.get("knowledge_updates", []):
            if change.get("confidence", 0) < threshold:
                return False
                
        return True
        
    except Exception as e:
        logger.error(f"Error determining auto-apply status: {e}")
        return False

async def _get_auto_approval_rate() -> float:
    """Calculate the auto-approval rate for recent updates"""
    try:
        return await memory_updater.get_auto_approval_rate()
    except Exception:
        return 0.0

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8004,
        reload=False,
        log_level="info"
    )