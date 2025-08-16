import asyncio
import logging
import os
from contextlib import asynccontextmanager
from typing import Dict, List, Any, Optional

from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel

from src.npc_repository import NPCRepository
from src.life_strand_schema import LifeStrand, NPCUpdate
from src.embedding_manager import embedding_manager

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
    try:
        await npc_repository.initialize()
        await embedding_manager.initialize()
        logger.info("NPC service started successfully")
        yield
    except Exception as e:
        logger.error(f"Failed to initialize NPC service: {e}")
        raise
    finally:
        await npc_repository.close()
        logger.info("NPC service shut down")

app = FastAPI(
    title="Life Strands NPC Service",
    description="NPC Life Strand management with vector search",
    version="1.0.0",
    lifespan=lifespan
)

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    npc_count = await npc_repository.get_npc_count()
    return {
        "status": "healthy",
        "total_npcs": npc_count,
        "embeddings_enabled": embedding_manager.is_enabled()
    }

@app.post("/npc", response_model=Dict[str, str])
async def create_npc(request: CreateNPCRequest):
    """Create a new NPC with Life Strand data"""
    try:
        npc_id = await npc_repository.create_npc(request.life_strand)
        
        # Generate embeddings if enabled
        if embedding_manager.is_enabled():
            await embedding_manager.generate_npc_embeddings(npc_id, request.life_strand)
            
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
            
        # Convert to prompt-optimized format
        prompt_data = {
            "name": life_strand.background.name,
            "age": life_strand.background.age,
            "occupation": life_strand.background.occupation,
            "location": life_strand.background.location,
            "personality_traits": life_strand.personality.traits,
            "current_mood": life_strand.current_status.mood,
            "current_activity": life_strand.current_status.current_activity,
            "recent_memories": life_strand.memories[-10:] if life_strand.memories else [],
            "key_relationships": [
                rel for rel in life_strand.relationships 
                if rel.intensity > 0.7
            ][:5],
            "knowledge_areas": list(life_strand.knowledge.keys())[:10]
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
        success = await npc_repository.update_npc(npc_id, request.updates)
        if not success:
            raise HTTPException(status_code=404, detail="NPC not found")
            
        # Update embeddings if enabled
        if embedding_manager.is_enabled():
            updated_life_strand = await npc_repository.get_npc(npc_id)
            await embedding_manager.update_npc_embeddings(npc_id, updated_life_strand)
            
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
        success = await npc_repository.delete_npc(npc_id)
        if not success:
            raise HTTPException(status_code=404, detail="NPC not found")
            
        # Remove embeddings if enabled
        if embedding_manager.is_enabled():
            await embedding_manager.remove_npc_embeddings(npc_id)
            
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
            
        results = await embedding_manager.search_npcs(
            request.query, 
            limit=request.limit
        )
        
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
            
        return {"memories": life_strand.memories}
        
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
            
        return {"relationships": life_strand.relationships}
        
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

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8003,
        reload=False,
        log_level="info"
    )