import asyncio
import aiohttp
import json
import logging
import os
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

class MemoryUpdater:
    """Apply approved changes to NPC Life Strands"""
    
    def __init__(self, npc_service_url: str = None):
        self.npc_service_url = npc_service_url or os.getenv("NPC_SERVICE_URL", "http://npc-service:8003")
        self.max_memories_per_npc = 50
        self.memory_importance_threshold = 3
        self._total_updates_applied = 0
    
    async def initialize(self):
        """Initialize the MemoryUpdater"""
        try:
            logger.info("Initializing MemoryUpdater...")
            # Test connection to NPC service
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{self.npc_service_url}/health",
                    timeout=aiohttp.ClientTimeout(total=5)
                ) as response:
                    if response.status != 200:
                        logger.warning(f"NPC service health check failed: {response.status}")
            logger.info("MemoryUpdater initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize MemoryUpdater: {e}")
            raise
        
    async def apply_changes(self, npc_id: str, changes: List[Dict[str, Any]]):
        """Apply auto-approved changes to Life Strand"""
        try:
            if not changes:
                logger.debug(f"No changes to apply for NPC {npc_id}")
                return
                
            # Get current NPC data
            current_life_strand = await self._get_npc_data(npc_id)
            if not current_life_strand:
                logger.error(f"Could not retrieve NPC data for {npc_id}")
                return
                
            # Process each change
            updated_life_strand = current_life_strand.copy()
            
            for change in changes:
                try:
                    change_type = change.get("change_type")
                    change_data = change.get("change_data", {})
                    
                    if change_type == "memory_added":
                        await self._apply_memory_addition(updated_life_strand, change_data)
                    elif change_type == "relationship_updated":
                        await self._apply_relationship_update(updated_life_strand, change_data)
                    elif change_type == "personality_changed":
                        await self._apply_personality_change(updated_life_strand, change_data)
                    elif change_type == "knowledge_learned":
                        await self._apply_knowledge_update(updated_life_strand, change_data)
                    elif change_type == "status_updated":
                        await self._apply_status_update(updated_life_strand, change_data)
                    else:
                        logger.warning(f"Unknown change type: {change_type}")
                        
                except Exception as e:
                    logger.error(f"Error applying change {change_type}: {e}")
                    continue
                    
            # Update NPC with all changes
            await self._update_npc(npc_id, updated_life_strand)
            self._total_updates_applied += len(changes)
            logger.info(f"Applied {len(changes)} changes to NPC {npc_id}")
            
        except Exception as e:
            logger.error(f"Error applying changes to NPC {npc_id}: {e}")
            
    async def add_conversation_memory(self, npc_id: str, memory: Dict[str, Any]):
        """Add conversation to NPC's memory"""
        try:
            if not memory or not memory.get("content"):
                logger.warning("Empty memory provided")
                return
                
            # Get current NPC data
            current_life_strand = await self._get_npc_data(npc_id)
            if not current_life_strand:
                logger.error(f"Could not retrieve NPC data for {npc_id}")
                return
                
            # Add memory
            memories = current_life_strand.get("memories", [])
            
            # Ensure memory has required fields
            memory_entry = {
                "content": memory["content"],
                "timestamp": memory.get("timestamp", datetime.utcnow().isoformat()),
                "importance": memory.get("importance", 5),
                "emotional_impact": memory.get("emotional_impact", "neutral"),
                "people_involved": memory.get("people_involved", ["user"]),
                "tags": memory.get("tags", [])
            }
            
            # Add to memories list
            memories.append(memory_entry)
            
            # Sort by timestamp and limit size
            memories = sorted(memories, key=lambda m: m.get("timestamp", ""), reverse=True)
            if len(memories) > self.max_memories_per_npc:
                memories = await self._prioritize_memories(memories, self.max_memories_per_npc)
                
            # Update NPC
            updated_life_strand = current_life_strand.copy()
            updated_life_strand["memories"] = memories
            
            await self._update_npc(npc_id, updated_life_strand)
            
            logger.info(f"Added conversation memory to NPC {npc_id}")
            
        except Exception as e:
            logger.error(f"Error adding conversation memory to NPC {npc_id}: {e}")
            
    async def update_relationships(self, npc_id: str, relationship_changes: List[Dict[str, Any]]):
        """Update relationship statuses and intensities"""
        try:
            if not relationship_changes:
                return
                
            # Get current NPC data
            current_life_strand = await self._get_npc_data(npc_id)
            if not current_life_strand:
                logger.error(f"Could not retrieve NPC data for {npc_id}")
                return
                
            relationships = current_life_strand.get("relationships", {})
            
            for change in relationship_changes:
                try:
                    person = change.get("person")
                    if not person:
                        continue
                        
                    relationship_type = change.get("type", "acquaintance")
                    status = change.get("status", "neutral")
                    intensity = min(10, max(1, int(change.get("intensity", 5))))
                    notes = change.get("notes", "")
                    
                    # Update or create relationship
                    if person in relationships:
                        # Update existing relationship
                        existing = relationships[person]
                        existing.update({
                            "type": relationship_type,
                            "status": status,
                            "intensity": intensity
                        })
                        
                        # Add to history if notes provided
                        if notes:
                            history = existing.get("history", [])
                            history.append({
                                "date": datetime.utcnow().isoformat(),
                                "change": notes
                            })
                            existing["history"] = history[-10:]  # Keep last 10 entries
                            
                    else:
                        # Create new relationship
                        relationships[person] = {
                            "type": relationship_type,
                            "status": status,
                            "intensity": intensity,
                            "notes": notes,
                            "history": [{
                                "date": datetime.utcnow().isoformat(),
                                "change": "Relationship established"
                            }] if notes else []
                        }
                        
                except Exception as e:
                    logger.error(f"Error updating relationship with {change.get('person', 'unknown')}: {e}")
                    continue
                    
            # Update NPC
            updated_life_strand = current_life_strand.copy()
            updated_life_strand["relationships"] = relationships
            
            await self._update_npc(npc_id, updated_life_strand)
            
            logger.info(f"Updated {len(relationship_changes)} relationships for NPC {npc_id}")
            
        except Exception as e:
            logger.error(f"Error updating relationships for NPC {npc_id}: {e}")
            
    async def prune_old_memories(self, npc_id: str):
        """Remove or compress old memories"""
        try:
            # Get current NPC data
            current_life_strand = await self._get_npc_data(npc_id)
            if not current_life_strand:
                return
                
            memories = current_life_strand.get("memories", [])
            
            if len(memories) <= self.max_memories_per_npc:
                logger.debug(f"NPC {npc_id} memory count within limits")
                return
                
            # Prioritize memories
            prioritized_memories = await self._prioritize_memories(memories, self.max_memories_per_npc)
            
            # Update NPC
            updated_life_strand = current_life_strand.copy()
            updated_life_strand["memories"] = prioritized_memories
            
            await self._update_npc(npc_id, updated_life_strand)
            
            removed_count = len(memories) - len(prioritized_memories)
            logger.info(f"Pruned {removed_count} old memories from NPC {npc_id}")
            
        except Exception as e:
            logger.error(f"Error pruning memories for NPC {npc_id}: {e}")
            
    async def _apply_memory_addition(self, life_strand: Dict[str, Any], change_data: Dict[str, Any]):
        """Apply memory addition change"""
        memories = life_strand.get("memories", [])
        
        memory_entry = {
            "content": change_data.get("content", ""),
            "timestamp": change_data.get("timestamp", datetime.utcnow().isoformat()),
            "importance": change_data.get("importance", 5),
            "emotional_impact": change_data.get("emotional_impact", "neutral"),
            "people_involved": change_data.get("people_involved", []),
            "tags": change_data.get("tags", [])
        }
        
        memories.append(memory_entry)
        life_strand["memories"] = memories
        
    async def _apply_relationship_update(self, life_strand: Dict[str, Any], change_data: Dict[str, Any]):
        """Apply relationship update change"""
        relationships = life_strand.get("relationships", {})
        person = change_data.get("person")
        
        if not person:
            return
            
        relationship_data = {
            "type": change_data.get("type", "acquaintance"),
            "status": change_data.get("status", "neutral"),
            "intensity": min(10, max(1, int(change_data.get("intensity", 5)))),
            "notes": change_data.get("notes", "")
        }
        
        if person in relationships:
            relationships[person].update(relationship_data)
        else:
            relationships[person] = relationship_data
            
        life_strand["relationships"] = relationships
        
    async def _apply_personality_change(self, life_strand: Dict[str, Any], change_data: Dict[str, Any]):
        """Apply personality change"""
        personality = life_strand.get("personality", {})
        change_type = change_data.get("change_type")
        item = change_data.get("item")
        
        if not item:
            return
            
        if change_type == "trait_added":
            traits = personality.get("traits", [])
            if item not in traits:
                traits.append(item)
                personality["traits"] = traits[:10]  # Limit to 10 traits
                
        elif change_type == "motivation_added":
            motivations = personality.get("motivations", [])
            if item not in motivations:
                motivations.append(item)
                personality["motivations"] = motivations[:5]  # Limit to 5 motivations
                
        elif change_type == "fear_added":
            fears = personality.get("fears", [])
            if item not in fears:
                fears.append(item)
                personality["fears"] = fears[:5]  # Limit to 5 fears
                
        life_strand["personality"] = personality
        
    async def _apply_knowledge_update(self, life_strand: Dict[str, Any], change_data: Dict[str, Any]):
        """Apply knowledge update change"""
        knowledge = life_strand.get("knowledge", [])
        
        new_knowledge = {
            "topic": change_data.get("topic", ""),
            "content": change_data.get("content", ""),
            "source": change_data.get("source", "conversation"),
            "confidence": min(10, max(1, int(change_data.get("confidence", 5)))),
            "acquired_date": change_data.get("acquired_date", datetime.utcnow().isoformat())
        }
        
        # Check if topic already exists
        topic = new_knowledge["topic"]
        existing_index = -1
        for i, existing_knowledge in enumerate(knowledge):
            if existing_knowledge.get("topic", "").lower() == topic.lower():
                existing_index = i
                break
                
        if existing_index >= 0:
            # Update existing knowledge
            knowledge[existing_index].update(new_knowledge)
        else:
            # Add new knowledge
            knowledge.append(new_knowledge)
            
        # Limit knowledge items
        life_strand["knowledge"] = knowledge[:100]  # Limit to 100 knowledge items
        
    async def _apply_status_update(self, life_strand: Dict[str, Any], change_data: Dict[str, Any]):
        """Apply status update change"""
        current_status = life_strand.get("current_status", {})
        field = change_data.get("field")
        new_value = change_data.get("new_value")
        
        if field and new_value:
            current_status[field] = new_value
            
        life_strand["current_status"] = current_status
        
    async def _prioritize_memories(self, memories: List[Dict[str, Any]], limit: int) -> List[Dict[str, Any]]:
        """Prioritize memories based on importance and recency"""
        try:
            def memory_score(memory):
                importance = memory.get("importance", 5)
                
                # Recency boost
                try:
                    timestamp = datetime.fromisoformat(memory.get("timestamp", ""))
                    days_old = (datetime.utcnow() - timestamp).days
                    recency_boost = max(0, 2 - (days_old / 15))  # Boost for last 30 days
                except:
                    recency_boost = 0
                    
                # Emotional impact boost
                emotional_impact = memory.get("emotional_impact", "neutral")
                emotion_boost = 1 if emotional_impact in ["positive", "negative"] else 0
                
                return importance + recency_boost + emotion_boost
                
            # Sort by score
            scored_memories = sorted(memories, key=memory_score, reverse=True)
            
            # Take top memories, but ensure we keep at least some recent ones
            recent_memories = [m for m in memories if self._is_recent_memory(m)]
            important_memories = scored_memories[:limit]
            
            # Combine recent and important, removing duplicates
            final_memories = []
            seen_contents = set()
            
            # Add recent memories first
            for memory in recent_memories[:limit//4]:  # Up to 25% recent
                content = memory.get("content", "")
                if content not in seen_contents:
                    final_memories.append(memory)
                    seen_contents.add(content)
                    
            # Add important memories
            for memory in important_memories:
                if len(final_memories) >= limit:
                    break
                content = memory.get("content", "")
                if content not in seen_contents:
                    final_memories.append(memory)
                    seen_contents.add(content)
                    
            return final_memories
            
        except Exception as e:
            logger.error(f"Error prioritizing memories: {e}")
            return memories[:limit]  # Fallback to simple truncation
            
    def _is_recent_memory(self, memory: Dict[str, Any]) -> bool:
        """Check if memory is from the last 7 days"""
        try:
            timestamp = datetime.fromisoformat(memory.get("timestamp", ""))
            return datetime.utcnow() - timestamp < timedelta(days=7)
        except:
            return False
            
    async def _get_npc_data(self, npc_id: str) -> Optional[Dict[str, Any]]:
        """Get NPC data from NPC service"""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(f"{self.npc_service_url}/npc/{npc_id}") as response:
                    if response.status == 200:
                        return await response.json()
                    else:
                        logger.error(f"Failed to get NPC data: {response.status}")
                        return None
                        
        except Exception as e:
            logger.error(f"Error getting NPC data for {npc_id}: {e}")
            return None
            
    async def _update_npc(self, npc_id: str, life_strand: Dict[str, Any]):
        """Update NPC data via NPC service"""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.put(
                    f"{self.npc_service_url}/npc/{npc_id}",
                    json=life_strand
                ) as response:
                    if response.status not in [200, 204]:
                        logger.error(f"Failed to update NPC: {response.status}")
                        
        except Exception as e:
            logger.error(f"Error updating NPC {npc_id}: {e}")
            
    async def get_memory_stats(self, npc_id: str) -> Dict[str, Any]:
        """Get memory statistics for NPC"""
        try:
            life_strand = await self._get_npc_data(npc_id)
            if not life_strand:
                return {}
                
            memories = life_strand.get("memories", [])
            
            if not memories:
                return {"total_memories": 0}
                
            # Calculate statistics
            importance_scores = [m.get("importance", 5) for m in memories]
            emotional_impacts = [m.get("emotional_impact", "neutral") for m in memories]
            
            stats = {
                "total_memories": len(memories),
                "average_importance": sum(importance_scores) / len(importance_scores),
                "max_importance": max(importance_scores),
                "min_importance": min(importance_scores),
                "emotional_distribution": {
                    "positive": emotional_impacts.count("positive"),
                    "negative": emotional_impacts.count("negative"),
                    "neutral": emotional_impacts.count("neutral")
                },
                "recent_memories": len([m for m in memories if self._is_recent_memory(m)]),
                "oldest_memory": min(m.get("timestamp", "") for m in memories) if memories else None,
                "newest_memory": max(m.get("timestamp", "") for m in memories) if memories else None
            }
            
            return stats
            
        except Exception as e:
            logger.error(f"Error getting memory stats for NPC {npc_id}: {e}")
            return {}
            
    async def cleanup_memories_batch(self, npc_ids: List[str]):
        """Clean up memories for multiple NPCs"""
        try:
            cleanup_tasks = [self.prune_old_memories(npc_id) for npc_id in npc_ids]
            await asyncio.gather(*cleanup_tasks, return_exceptions=True)
            
            logger.info(f"Completed memory cleanup for {len(npc_ids)} NPCs")
            
        except Exception as e:
            logger.error(f"Error in batch memory cleanup: {e}")
            
    def validate_change_data(self, change: Dict[str, Any]) -> bool:
        """Validate change data structure"""
        try:
            required_fields = ["change_type", "change_summary", "change_data"]
            
            for field in required_fields:
                if field not in change:
                    logger.warning(f"Missing required field: {field}")
                    return False
                    
            change_type = change["change_type"]
            change_data = change["change_data"]
            
            # Validate based on change type
            if change_type == "memory_added":
                return "content" in change_data
            elif change_type == "relationship_updated":
                return "person" in change_data
            elif change_type == "personality_changed":
                return "change_type" in change_data and "item" in change_data
            elif change_type == "knowledge_learned":
                return "topic" in change_data and "content" in change_data
            elif change_type == "status_updated":
                return "field" in change_data and "new_value" in change_data
                
            return True
            
        except Exception as e:
            logger.error(f"Error validating change data: {e}")
            return False
            
    def get_total_updates(self) -> int:
        return self._total_updates_applied