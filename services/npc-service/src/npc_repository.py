import asyncio
import asyncpg
import json
import logging
from typing import Dict, List, Any, Optional
from datetime import datetime
import uuid

logger = logging.getLogger(__name__)

class NPCRepository:
    """Database operations for Life Strand data"""
    
    def __init__(self, database_url: str = None):
        self.database_url = database_url or "postgresql://user:pass@localhost/lifestrands"
        self.pool: Optional[asyncpg.Pool] = None
        
    async def initialize(self):
        """Initialize database connection pool"""
        try:
            self.pool = await asyncpg.create_pool(
                self.database_url,
                min_size=5,
                max_size=20,
                command_timeout=60
            )
            
            # Test connection
            async with self.pool.acquire() as conn:
                await conn.fetchval("SELECT 1")
                
            logger.info("NPCRepository initialized with database connection")
            
        except Exception as e:
            logger.error(f"Failed to initialize NPCRepository: {e}")
            raise
            
    async def create_npc(self, life_strand: Dict[str, Any]) -> str:
        """Create new NPC with validation"""
        try:
            from .life_strand_schema import LifeStrandValidator
            validator = LifeStrandValidator()
            
            # Validate life strand data
            if not validator.validate_life_strand(life_strand):
                raise ValueError("Invalid life strand data")
                
            # Generate NPC ID
            npc_id = str(uuid.uuid4())
            life_strand["id"] = npc_id
            life_strand["created_at"] = datetime.utcnow().isoformat()
            life_strand["updated_at"] = datetime.utcnow().isoformat()
            
            # Extract queryable fields
            queryable_fields = validator.extract_queryable_fields(life_strand)
            
            async with self.pool.acquire() as conn:
                # Insert into NPCs table
                await conn.execute("""
                    INSERT INTO npcs (
                        id, name, location, faction, status, background_occupation,
                        background_age, personality_traits, life_strand_data, 
                        created_at, updated_at
                    ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)
                """, 
                    npc_id,
                    queryable_fields.get("name"),
                    queryable_fields.get("location"),
                    queryable_fields.get("faction"),
                    queryable_fields.get("status", "active"),
                    queryable_fields.get("background_occupation"),
                    queryable_fields.get("background_age"),
                    json.dumps(queryable_fields.get("personality_traits", [])),
                    json.dumps(life_strand),
                    datetime.utcnow(),
                    datetime.utcnow()
                )
                
            logger.info(f"Created NPC: {npc_id} ({queryable_fields.get('name', 'Unknown')})")
            return npc_id
            
        except Exception as e:
            logger.error(f"Error creating NPC: {e}")
            raise
            
    async def get_npc(self, npc_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve full Life Strand data"""
        try:
            async with self.pool.acquire() as conn:
                row = await conn.fetchrow(
                    "SELECT life_strand_data FROM npcs WHERE id = $1 AND status != 'archived'",
                    npc_id
                )
                
                if row:
                    return json.loads(row["life_strand_data"])
                    
            return None
            
        except Exception as e:
            logger.error(f"Error getting NPC {npc_id}: {e}")
            return None
            
    async def update_npc(self, npc_id: str, updates: Dict[str, Any]):
        """Apply changes to Life Strand"""
        try:
            from .life_strand_schema import LifeStrandValidator
            validator = LifeStrandValidator()
            
            # Get current life strand
            current_life_strand = await self.get_npc(npc_id)
            if not current_life_strand:
                raise ValueError(f"NPC {npc_id} not found")
                
            # Merge changes
            updated_life_strand = validator.merge_changes(current_life_strand, updates)
            updated_life_strand["updated_at"] = datetime.utcnow().isoformat()
            
            # Validate updated data
            if not validator.validate_life_strand(updated_life_strand):
                raise ValueError("Updated life strand data is invalid")
                
            # Extract queryable fields
            queryable_fields = validator.extract_queryable_fields(updated_life_strand)
            
            async with self.pool.acquire() as conn:
                await conn.execute("""
                    UPDATE npcs SET 
                        name = $2,
                        location = $3,
                        faction = $4,
                        status = $5,
                        background_occupation = $6,
                        background_age = $7,
                        personality_traits = $8,
                        life_strand_data = $9,
                        updated_at = $10
                    WHERE id = $1
                """,
                    npc_id,
                    queryable_fields.get("name"),
                    queryable_fields.get("location"),
                    queryable_fields.get("faction"),
                    queryable_fields.get("status", "active"),
                    queryable_fields.get("background_occupation"),
                    queryable_fields.get("background_age"),
                    json.dumps(queryable_fields.get("personality_traits", [])),
                    json.dumps(updated_life_strand),
                    datetime.utcnow()
                )
                
            logger.info(f"Updated NPC: {npc_id}")
            
        except Exception as e:
            logger.error(f"Error updating NPC {npc_id}: {e}")
            raise
            
    async def query_npcs(self, filters: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Query NPCs by location, faction, status, etc."""
        try:
            # Build query conditions
            conditions = ["status != 'archived'"]
            params = []
            param_count = 0
            
            if "location" in filters:
                param_count += 1
                conditions.append(f"location = ${param_count}")
                params.append(filters["location"])
                
            if "faction" in filters:
                param_count += 1
                conditions.append(f"faction = ${param_count}")
                params.append(filters["faction"])
                
            if "status" in filters:
                param_count += 1
                conditions.append(f"status = ${param_count}")
                params.append(filters["status"])
                
            if "name_search" in filters:
                param_count += 1
                conditions.append(f"name ILIKE ${param_count}")
                params.append(f"%{filters['name_search']}%")
                
            if "age_min" in filters:
                param_count += 1
                conditions.append(f"background_age >= ${param_count}")
                params.append(filters["age_min"])
                
            if "age_max" in filters:
                param_count += 1
                conditions.append(f"background_age <= ${param_count}")
                params.append(filters["age_max"])
                
            # Build final query
            query = f"""
                SELECT id, name, location, faction, status, background_occupation,
                       background_age, personality_traits, created_at, updated_at
                FROM npcs 
                WHERE {' AND '.join(conditions)}
                ORDER BY updated_at DESC
                LIMIT {filters.get('limit', 50)}
            """
            
            async with self.pool.acquire() as conn:
                rows = await conn.fetch(query, *params)
                
                results = []
                for row in rows:
                    result = dict(row)
                    # Parse JSON fields
                    if result["personality_traits"]:
                        result["personality_traits"] = json.loads(result["personality_traits"])
                    results.append(result)
                    
                return results
                
        except Exception as e:
            logger.error(f"Error querying NPCs with filters {filters}: {e}")
            return []
            
    async def get_npc_for_prompt(self, npc_id: str) -> Dict[str, Any]:
        """Get optimized subset for LLM prompt"""
        try:
            life_strand = await self.get_npc(npc_id)
            if not life_strand:
                return {}
                
            # Return only essential fields for prompts
            prompt_data = {
                "id": npc_id,
                "name": life_strand.get("name", "Unknown"),
                "background": {
                    "age": life_strand.get("background", {}).get("age"),
                    "occupation": life_strand.get("background", {}).get("occupation"),
                    "location": life_strand.get("background", {}).get("location"),
                    "history": life_strand.get("background", {}).get("history", "")[:500]  # Truncate
                },
                "personality": {
                    "traits": life_strand.get("personality", {}).get("traits", [])[:5],  # Top 5
                    "motivations": life_strand.get("personality", {}).get("motivations", [])[:3],
                    "fears": life_strand.get("personality", {}).get("fears", [])[:2]
                },
                "current_status": life_strand.get("current_status", {}),
                "relationships": life_strand.get("relationships", {}),
                "knowledge": life_strand.get("knowledge", [])[:10],  # Most recent/important
                "memories": life_strand.get("memories", [])[-5:]  # Recent memories
            }
            
            return prompt_data
            
        except Exception as e:
            logger.error(f"Error getting NPC for prompt {npc_id}: {e}")
            return {}
            
    async def archive_npc(self, npc_id: str):
        """Soft delete / archive NPC"""
        try:
            async with self.pool.acquire() as conn:
                result = await conn.execute(
                    "UPDATE npcs SET status = 'archived', updated_at = $2 WHERE id = $1",
                    npc_id, datetime.utcnow()
                )
                
                if result == "UPDATE 0":
                    raise ValueError(f"NPC {npc_id} not found")
                    
            logger.info(f"Archived NPC: {npc_id}")
            
        except Exception as e:
            logger.error(f"Error archiving NPC {npc_id}: {e}")
            raise
            
    async def restore_npc(self, npc_id: str):
        """Restore archived NPC"""
        try:
            async with self.pool.acquire() as conn:
                result = await conn.execute(
                    "UPDATE npcs SET status = 'active', updated_at = $2 WHERE id = $1 AND status = 'archived'",
                    npc_id, datetime.utcnow()
                )
                
                if result == "UPDATE 0":
                    raise ValueError(f"Archived NPC {npc_id} not found")
                    
            logger.info(f"Restored NPC: {npc_id}")
            
        except Exception as e:
            logger.error(f"Error restoring NPC {npc_id}: {e}")
            raise
            
    async def get_npc_summary(self, npc_id: str) -> Dict[str, Any]:
        """Get basic NPC information"""
        try:
            async with self.pool.acquire() as conn:
                row = await conn.fetchrow("""
                    SELECT id, name, location, faction, status, background_occupation,
                           background_age, created_at, updated_at
                    FROM npcs WHERE id = $1
                """, npc_id)
                
                if row:
                    return dict(row)
                    
            return {}
            
        except Exception as e:
            logger.error(f"Error getting NPC summary {npc_id}: {e}")
            return {}
            
    async def search_npcs_by_trait(self, trait: str, limit: int = 10) -> List[Dict[str, Any]]:
        """Search NPCs by personality trait"""
        try:
            async with self.pool.acquire() as conn:
                rows = await conn.fetch("""
                    SELECT id, name, location, faction, personality_traits
                    FROM npcs 
                    WHERE status != 'archived' 
                    AND personality_traits::text ILIKE $1
                    ORDER BY updated_at DESC
                    LIMIT $2
                """, f"%{trait}%", limit)
                
                results = []
                for row in rows:
                    result = dict(row)
                    result["personality_traits"] = json.loads(result["personality_traits"]) if result["personality_traits"] else []
                    results.append(result)
                    
                return results
                
        except Exception as e:
            logger.error(f"Error searching NPCs by trait '{trait}': {e}")
            return []
            
    async def get_npcs_by_location(self, location: str, limit: int = 20) -> List[Dict[str, Any]]:
        """Get all NPCs in a specific location"""
        try:
            return await self.query_npcs({"location": location, "limit": limit})
        except Exception as e:
            logger.error(f"Error getting NPCs by location '{location}': {e}")
            return []
            
    async def get_npcs_by_faction(self, faction: str, limit: int = 20) -> List[Dict[str, Any]]:
        """Get all NPCs in a specific faction"""
        try:
            return await self.query_npcs({"faction": faction, "limit": limit})
        except Exception as e:
            logger.error(f"Error getting NPCs by faction '{faction}': {e}")
            return []
            
    async def get_repository_stats(self) -> Dict[str, Any]:
        """Get repository statistics"""
        try:
            async with self.pool.acquire() as conn:
                # Total counts
                total_npcs = await conn.fetchval("SELECT COUNT(*) FROM npcs WHERE status != 'archived'")
                archived_npcs = await conn.fetchval("SELECT COUNT(*) FROM npcs WHERE status = 'archived'")
                
                # By location
                location_stats = await conn.fetch("""
                    SELECT location, COUNT(*) as count 
                    FROM npcs 
                    WHERE status != 'archived' AND location IS NOT NULL 
                    GROUP BY location 
                    ORDER BY count DESC
                """)
                
                # By faction
                faction_stats = await conn.fetch("""
                    SELECT faction, COUNT(*) as count 
                    FROM npcs 
                    WHERE status != 'archived' AND faction IS NOT NULL 
                    GROUP BY faction 
                    ORDER BY count DESC
                """)
                
                return {
                    "total_active_npcs": total_npcs,
                    "archived_npcs": archived_npcs,
                    "locations": [dict(row) for row in location_stats],
                    "factions": [dict(row) for row in faction_stats]
                }
                
        except Exception as e:
            logger.error(f"Error getting repository stats: {e}")
            return {}
            
    async def cleanup_old_data(self, days_old: int = 365):
        """Cleanup very old archived NPCs"""
        try:
            cutoff_date = datetime.utcnow().replace(day=datetime.utcnow().day - days_old)
            
            async with self.pool.acquire() as conn:
                result = await conn.execute("""
                    DELETE FROM npcs 
                    WHERE status = 'archived' 
                    AND updated_at < $1
                """, cutoff_date)
                
                deleted_count = int(result.split()[-1])
                logger.info(f"Cleaned up {deleted_count} old archived NPCs")
                return deleted_count
                
        except Exception as e:
            logger.error(f"Error cleaning up old data: {e}")
            return 0
            
    async def close(self):
        """Close database connection pool"""
        try:
            if self.pool:
                await self.pool.close()
                logger.info("NPCRepository database connections closed")
        except Exception as e:
            logger.error(f"Error closing database connections: {e}")