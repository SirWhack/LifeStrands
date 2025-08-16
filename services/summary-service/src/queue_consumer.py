import asyncio
import redis.asyncio as redis
import json
import logging
from typing import Dict, Any, Optional, List
from datetime import datetime
import traceback

logger = logging.getLogger(__name__)

class QueueConsumer:
    """Consume conversation summaries from Redis queue"""
    
    def __init__(self, redis_url: str = None):
        import os
        self.redis_url = redis_url or os.getenv("REDIS_URL", "redis://localhost:6379")
        self.redis_client: Optional[redis.Redis] = None
        self.is_running = False
        self.consumer_tasks = []
        self.processed_count = 0
        
        # Queue configurations
        self.queues = {
            "summary_queue": {
                "concurrency": 3,
                "retry_limit": 3,
                "timeout": 300  # 5 minutes
            }
        }
        
        # Service dependencies
        from .summary_generator import SummaryGenerator
        from .change_extractor import ChangeExtractor
        from .memory_updater import MemoryUpdater
        
        self.summary_generator = SummaryGenerator()
        self.change_extractor = ChangeExtractor()
        self.memory_updater = MemoryUpdater()
        
    async def initialize(self):
        """Initialize Redis connection and prepare consumer"""
        try:
            self.redis_client = redis.from_url(self.redis_url)
            await self.redis_client.ping()
            
            logger.info("QueueConsumer initialized successfully")
            
        except Exception as e:
            logger.error(f"Failed to initialize QueueConsumer: {e}")
            raise
            
    async def start_consumer(self):
        """Start listening to summary queue"""
        try:
            if self.is_running:
                logger.warning("Consumer is already running")
                return
                
            self.is_running = True
            
            # Start consumer tasks for each queue
            for queue_name, config in self.queues.items():
                concurrency = config["concurrency"]
                
                for i in range(concurrency):
                    task = asyncio.create_task(
                        self._consumer_worker(queue_name, f"worker-{i+1}", config)
                    )
                    self.consumer_tasks.append(task)
                    
            logger.info(f"Started {len(self.consumer_tasks)} consumer workers")
            
            # Wait for all workers to complete
            await asyncio.gather(*self.consumer_tasks)
            
        except Exception as e:
            logger.error(f"Error in consumer startup: {e}")
            self.is_running = False
            
    async def stop_consumer(self):
        """Stop all consumer workers"""
        try:
            self.is_running = False
            
            # Cancel all tasks
            for task in self.consumer_tasks:
                if not task.done():
                    task.cancel()
                    
            # Wait for tasks to complete/cancel
            if self.consumer_tasks:
                await asyncio.gather(*self.consumer_tasks, return_exceptions=True)
                
            self.consumer_tasks.clear()
            
            logger.info("All consumer workers stopped")
            
        except Exception as e:
            logger.error(f"Error stopping consumer: {e}")
            
    async def _consumer_worker(self, queue_name: str, worker_id: str, config: Dict[str, Any]):
        """Individual consumer worker"""
        logger.info(f"Starting consumer worker {worker_id} for queue {queue_name}")
        
        while self.is_running:
            try:
                # Block until message available or timeout
                result = await self.redis_client.brpop(queue_name, timeout=5)
                
                if not result:
                    continue  # Timeout, check if still running
                    
                queue, message_data = result
                
                try:
                    message = json.loads(message_data.decode('utf-8'))
                    logger.info(f"Worker {worker_id} processing message: {message.get('session_id', 'unknown')}")
                    
                    # Process the message
                    await self.process_summary_request(message)
                    
                    logger.debug(f"Worker {worker_id} completed processing message")
                    
                except json.JSONDecodeError as e:
                    logger.error(f"Worker {worker_id} failed to decode message: {e}")
                    await self._handle_poison_message(message_data, "Invalid JSON")
                    
                except Exception as e:
                    logger.error(f"Worker {worker_id} error processing message: {e}")
                    
                    try:
                        message = json.loads(message_data.decode('utf-8'))
                        await self.handle_processing_error(e, message)
                    except:
                        await self._handle_poison_message(message_data, str(e))
                        
            except asyncio.CancelledError:
                logger.info(f"Consumer worker {worker_id} cancelled")
                break
                
            except Exception as e:
                logger.error(f"Unexpected error in consumer worker {worker_id}: {e}")
                await asyncio.sleep(1)  # Brief pause before retrying
                
        logger.info(f"Consumer worker {worker_id} stopped")
        
    async def process_summary_request(self, message: Dict[str, Any]):
        """Process single summary request"""
        try:
            # Extract message data
            session_id = message.get("session_id")
            npc_id = message.get("npc_id")
            user_id = message.get("user_id")
            transcript = message.get("messages", [])
            
            if not all([session_id, npc_id, transcript]):
                raise ValueError("Missing required message fields")
                
            logger.info(f"Processing summary for session {session_id}, NPC {npc_id}")
            
            # Step 1: Generate conversation summary
            summary = await self.summary_generator.generate_summary(transcript)
            
            if not summary:
                logger.warning(f"No summary generated for session {session_id}")
                return
                
            # Step 2: Extract key points
            key_points = await self.summary_generator.extract_key_points(transcript)
            
            # Step 3: Analyze conversation for changes
            life_strand = await self._get_npc_data(npc_id)
            changes = await self.change_extractor.analyze_conversation(transcript, life_strand)
            
            # Step 4: Generate memory entry
            memory_entry = await self.summary_generator.generate_memory_entry(summary, npc_id)
            
            # Step 5: Calculate emotional impact
            emotional_impact = await self.change_extractor.calculate_emotional_impact(transcript)
            
            # Step 6: Apply auto-approved changes
            auto_approved_changes = self._filter_auto_approved_changes(changes)
            
            if auto_approved_changes:
                await self.memory_updater.apply_changes(npc_id, auto_approved_changes)
                
            # Step 7: Add conversation memory
            if memory_entry:
                await self.memory_updater.add_conversation_memory(npc_id, memory_entry)
                
            # Step 8: Store summary in database
            await self._store_conversation_summary(
                session_id, summary, key_points, emotional_impact, changes
            )
            
            # Step 9: Notify completion
            await self.notify_completion(session_id)
            
            # Increment processed counter
            self.processed_count += 1
            
            logger.info(f"Successfully processed summary for session {session_id}")
            
        except Exception as e:
            logger.error(f"Error processing summary request: {e}")
            logger.error(f"Traceback: {traceback.format_exc()}")
            raise
            
    async def handle_processing_error(self, error: Exception, message: Dict[str, Any]):
        """Handle failed summary generation"""
        try:
            session_id = message.get("session_id", "unknown")
            retry_count = message.get("retry_count", 0)
            max_retries = 3
            
            logger.error(f"Processing error for session {session_id}: {error}")
            
            if retry_count < max_retries:
                # Retry the message
                retry_message = message.copy()
                retry_message["retry_count"] = retry_count + 1
                retry_message["last_error"] = str(error)
                retry_message["retry_at"] = datetime.utcnow().isoformat()
                
                # Add back to queue with delay
                await asyncio.sleep(min(60 * (retry_count + 1), 300))  # Exponential backoff, max 5 min
                
                await self.redis_client.lpush(
                    "summary_queue",
                    json.dumps(retry_message, default=str)
                )
                
                logger.info(f"Queued retry #{retry_count + 1} for session {session_id}")
                
            else:
                # Max retries reached, store error
                await self._store_processing_error(session_id, error, message)
                logger.error(f"Max retries reached for session {session_id}, storing error")
                
        except Exception as e:
            logger.error(f"Error handling processing error: {e}")
            
    async def notify_completion(self, session_id: str):
        """Notify that summary is complete"""
        try:
            # Send completion notification via Redis pub/sub
            notification = {
                "type": "summary_completed",
                "session_id": session_id,
                "timestamp": datetime.utcnow().isoformat()
            }
            
            await self.redis_client.publish(
                "summary_notifications",
                json.dumps(notification, default=str)
            )
            
            # Also store completion flag
            await self.redis_client.set(
                f"summary_completed:{session_id}",
                "true",
                ex=86400  # 24 hour TTL
            )
            
            logger.debug(f"Sent completion notification for session {session_id}")
            
        except Exception as e:
            logger.error(f"Error sending completion notification: {e}")
            
    def _filter_auto_approved_changes(self, changes: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Filter changes that can be auto-approved"""
        try:
            auto_approved = []
            confidence_threshold = 0.8
            
            for change in changes:
                confidence = change.get("confidence_score", 0)
                change_type = change.get("change_type")
                
                # Auto-approve high confidence changes of certain types
                if confidence >= confidence_threshold:
                    if change_type in [
                        "memory_added", 
                        "knowledge_learned", 
                        "emotional_impact"
                    ]:
                        auto_approved.append(change)
                        
                    elif change_type == "status_updated":
                        # Auto-approve status changes for mood and activity
                        field = change.get("change_data", {}).get("field")
                        if field in ["mood", "activity"]:
                            auto_approved.append(change)
                            
            logger.debug(f"Auto-approved {len(auto_approved)} out of {len(changes)} changes")
            return auto_approved
            
        except Exception as e:
            logger.error(f"Error filtering auto-approved changes: {e}")
            return []
            
    async def _get_npc_data(self, npc_id: str) -> Dict[str, Any]:
        """Get NPC data for analysis"""
        try:
            import aiohttp
            
            async with aiohttp.ClientSession() as session:
                async with session.get(f"http://localhost:8003/npcs/{npc_id}") as response:
                    if response.status == 200:
                        return await response.json()
                    else:
                        logger.warning(f"Could not get NPC data: {response.status}")
                        return {}
                        
        except Exception as e:
            logger.error(f"Error getting NPC data: {e}")
            return {}
            
    async def _store_conversation_summary(
        self, 
        session_id: str, 
        summary: str, 
        key_points: List[str], 
        emotional_impact: Dict[str, Any], 
        changes: List[Dict[str, Any]]
    ):
        """Store summary in database"""
        try:
            # Store summary data in Redis for now
            # In production, this would go to PostgreSQL
            
            summary_data = {
                "session_id": session_id,
                "summary": summary,
                "key_points": key_points,
                "emotional_impact": emotional_impact,
                "changes": changes,
                "processed_at": datetime.utcnow().isoformat()
            }
            
            await self.redis_client.set(
                f"summary:{session_id}",
                json.dumps(summary_data, default=str),
                ex=86400 * 7  # 7 days TTL
            )
            
            logger.debug(f"Stored summary for session {session_id}")
            
        except Exception as e:
            logger.error(f"Error storing conversation summary: {e}")
            
    async def _store_processing_error(self, session_id: str, error: Exception, message: Dict[str, Any]):
        """Store processing error details"""
        try:
            error_data = {
                "session_id": session_id,
                "error_message": str(error),
                "error_type": type(error).__name__,
                "original_message": message,
                "failed_at": datetime.utcnow().isoformat()
            }
            
            await self.redis_client.set(
                f"summary_error:{session_id}",
                json.dumps(error_data, default=str),
                ex=86400 * 3  # 3 days TTL
            )
            
            logger.info(f"Stored processing error for session {session_id}")
            
        except Exception as e:
            logger.error(f"Error storing processing error: {e}")
            
    async def _handle_poison_message(self, message_data: bytes, error_reason: str):
        """Handle messages that can't be processed"""
        try:
            # Store poison message for investigation
            poison_data = {
                "message_data": message_data.decode('utf-8', errors='replace'),
                "error_reason": error_reason,
                "timestamp": datetime.utcnow().isoformat()
            }
            
            await self.redis_client.lpush(
                "poison_messages",
                json.dumps(poison_data, default=str)
            )
            
            logger.warning(f"Stored poison message: {error_reason}")
            
        except Exception as e:
            logger.error(f"Error handling poison message: {e}")
            
    async def get_queue_stats(self) -> Dict[str, Any]:
        """Get queue processing statistics"""
        try:
            stats = {}
            
            for queue_name in self.queues.keys():
                queue_length = await self.redis_client.llen(queue_name)
                stats[queue_name] = {
                    "length": queue_length,
                    "workers": self.queues[queue_name]["concurrency"]
                }
                
            # Additional stats
            poison_count = await self.redis_client.llen("poison_messages")
            
            stats["system"] = {
                "is_running": self.is_running,
                "active_workers": len([t for t in self.consumer_tasks if not t.done()]),
                "total_workers": len(self.consumer_tasks),
                "poison_messages": poison_count
            }
            
            return stats
            
        except Exception as e:
            logger.error(f"Error getting queue stats: {e}")
            return {}
            
    async def clear_queue(self, queue_name: str) -> int:
        """Clear all messages from queue"""
        try:
            if queue_name not in self.queues:
                raise ValueError(f"Unknown queue: {queue_name}")
                
            cleared_count = await self.redis_client.delete(queue_name)
            logger.info(f"Cleared {cleared_count} messages from queue {queue_name}")
            
            return cleared_count
            
        except Exception as e:
            logger.error(f"Error clearing queue {queue_name}: {e}")
            return 0
            
    async def requeue_failed_messages(self, max_age_hours: int = 24) -> int:
        """Requeue failed messages for retry"""
        try:
            # This would retrieve failed messages from database/storage
            # and requeue them for processing
            
            # For now, just a placeholder
            logger.info("Requeue failed messages not implemented yet")
            return 0
            
        except Exception as e:
            logger.error(f"Error requeuing failed messages: {e}")
            return 0
            
    async def start_processing(self):
        """Alias for start_consumer for compatibility"""
        return await self.start_consumer()
        
    async def stop_processing(self):
        """Alias for stop_consumer for compatibility"""
        return await self.stop_consumer()

    async def health_check(self) -> Dict[str, Any]:
        """Get health status of queue consumer"""
        try:
            health = {
                "status": "healthy" if self.is_running else "stopped",
                "workers_running": len([t for t in self.consumer_tasks if not t.done()]),
                "redis_connected": False
            }
            
            # Test Redis connection
            try:
                await self.redis_client.ping()
                health["redis_connected"] = True
            except:
                health["redis_connected"] = False
                health["status"] = "unhealthy"
                
            # Check worker health
            if self.is_running and health["workers_running"] == 0:
                health["status"] = "unhealthy"
                
            return health
            
        except Exception as e:
            logger.error(f"Error in health check: {e}")
            return {"status": "error", "error": str(e)}
            
    def is_processing(self) -> bool:
        """Check if queue processing is active"""
        return self.is_running
        
    def get_processed_count(self) -> int:
        """Get total number of processed items"""
        return self.processed_count
        
    async def get_queue_status(self) -> Dict[str, Any]:
        """Get current queue status"""
        try:
            if not self.redis_client:
                return {"length": 0, "failed": 0, "avg_time": 0}
                
            # Get queue length
            queue_length = await self.redis_client.llen("summary_queue")
            failed_count = await self.redis_client.llen("summary_queue:failed")
            
            return {
                "length": queue_length,
                "failed": failed_count,
                "avg_time": 0  # Would need to track processing times
            }
        except Exception as e:
            logger.error(f"Error getting queue status: {e}")
            return {"length": 0, "failed": 0, "avg_time": 0}
            
    async def retry_failed_jobs(self) -> int:
        """Retry failed jobs"""
        try:
            if not self.redis_client:
                return 0
                
            # Move failed jobs back to main queue
            failed_count = 0
            while True:
                item = await self.redis_client.rpop("summary_queue:failed")
                if not item:
                    break
                await self.redis_client.lpush("summary_queue", item)
                failed_count += 1
                
            logger.info(f"Retried {failed_count} failed jobs")
            return failed_count
            
        except Exception as e:
            logger.error(f"Error retrying failed jobs: {e}")
            return 0