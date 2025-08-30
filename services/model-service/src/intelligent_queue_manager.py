import heapq
import asyncio
from dataclasses import dataclass, field
from typing import Dict, List, Any, Optional, AsyncGenerator
from enum import Enum
import time
import statistics
import logging

from .request_distributor import RequestContext, ServiceType

logger = logging.getLogger(__name__)

class RequestType(Enum):
    GENERATION = "generation"
    EMBEDDING = "embedding"
    MODEL_SWITCH = "model_switch"

@dataclass
class QueuedRequest:
    priority: int
    timestamp: float
    request_context: Optional[RequestContext]
    future: asyncio.Future
    request_type: RequestType = RequestType.GENERATION
    
    def __lt__(self, other):
        # Higher priority first (lower number = higher priority)
        if self.priority != other.priority:
            return self.priority < other.priority
        return self.timestamp < other.timestamp

class DemandPredictor:
    """Predicts future model demand based on usage patterns"""
    
    def __init__(self):
        self.request_history = []
        self.max_history = 1000
        
    def record_request(self, service_type: ServiceType, timestamp: float):
        """Record a request for demand prediction"""
        self.request_history.append((service_type, timestamp))
        if len(self.request_history) > self.max_history:
            self.request_history.pop(0)
    
    def predict_next_model_need(self) -> Optional[str]:
        """Predict which model will be needed next"""
        if len(self.request_history) < 10:
            return None
            
        # Analyze recent patterns
        recent_requests = self.request_history[-50:]
        current_time = time.time()
        
        # Count requests by service in last 5 minutes
        recent_counts = {}
        for service_type, timestamp in recent_requests:
            if current_time - timestamp <= 300:  # 5 minutes
                model_type = self._service_to_model(service_type)
                recent_counts[model_type] = recent_counts.get(model_type, 0) + 1
        
        if not recent_counts:
            return None
            
        # Return most frequently requested model
        return max(recent_counts.items(), key=lambda x: x[1])[0]
    
    def get_demand_pattern(self) -> Dict[str, Any]:
        """Get current demand pattern analysis"""
        if len(self.request_history) < 5:
            return {"insufficient_data": True}
        
        current_time = time.time()
        
        # Analyze last hour
        last_hour = [
            (service_type, timestamp) for service_type, timestamp in self.request_history
            if current_time - timestamp <= 3600
        ]
        
        service_counts = {}
        for service_type, _ in last_hour:
            service_counts[service_type.value] = service_counts.get(service_type.value, 0) + 1
        
        # Calculate request frequency (requests per minute)
        time_span = min(3600, current_time - self.request_history[0][1]) / 60  # minutes
        total_requests = len(last_hour)
        
        return {
            "requests_per_minute": total_requests / max(time_span, 1),
            "service_distribution": service_counts,
            "predicted_next_model": self.predict_next_model_need(),
            "analysis_period_minutes": time_span
        }
    
    def _service_to_model(self, service_type: ServiceType) -> str:
        """Map service type to model type"""
        mapping = {
            ServiceType.CHAT: "chat",
            ServiceType.SUMMARY: "summary",
            ServiceType.NPC: "embedding"
        }
        return mapping.get(service_type, "chat")

class IntelligentQueueManager:
    """Manages request queues with intelligent prioritization and demand prediction"""
    
    def __init__(self, model_pools: Dict[str, Any], config: Dict[str, Any]):
        self.model_pools = model_pools
        self.config = config
        
        # Queue management
        self._generation_queue: List[QueuedRequest] = []
        self._embedding_queue: List[QueuedRequest] = []
        self._queue_lock = asyncio.Lock()
        
        # Demand prediction
        self.demand_predictor = DemandPredictor()
        
        # Statistics
        self.stats = {
            "requests_processed": 0,
            "avg_wait_time": 0.0,
            "current_queue_size": 0,
            "model_utilization": {},
            "processing_errors": 0
        }
        
        # Configuration
        self.max_queue_size = config.get("max_queue_size", 100)
        self.batch_timeout = config.get("batch_timeout", 0.2)  # 200ms
        self.max_batch_size = config.get("max_batch_size", 10)
        
        # Start background processors
        self._processor_tasks = []
        self._shutdown_event = asyncio.Event()
        
    async def start(self):
        """Start background processing tasks"""
        self._processor_tasks = [
            asyncio.create_task(self._generation_processor()),
            asyncio.create_task(self._embedding_processor()),
            asyncio.create_task(self._predictive_model_manager()),
            asyncio.create_task(self._stats_updater())
        ]
        logger.info("IntelligentQueueManager started")
    
    async def shutdown(self):
        """Shutdown background tasks gracefully"""
        self._shutdown_event.set()
        
        # Cancel all tasks
        for task in self._processor_tasks:
            task.cancel()
        
        # Wait for tasks to complete
        await asyncio.gather(*self._processor_tasks, return_exceptions=True)
        
        logger.info("IntelligentQueueManager shut down")
    
    async def process_generation_request(self, request_context: RequestContext) -> AsyncGenerator[str, None]:
        """Queue generation request and return async generator for streaming"""
        
        # Check queue capacity
        async with self._queue_lock:
            if len(self._generation_queue) >= self.max_queue_size:
                raise Exception("Queue at capacity, try again later")
        
        # Record for demand prediction
        self.demand_predictor.record_request(request_context.service_type, time.time())
        
        # Create future for result
        result_future = asyncio.Future()
        
        # Create queued request
        queued_request = QueuedRequest(
            priority=request_context.priority,
            timestamp=time.time(),
            request_context=request_context,
            future=result_future,
            request_type=RequestType.GENERATION
        )
        
        # Add to appropriate queue
        async with self._queue_lock:
            heapq.heappush(self._generation_queue, queued_request)
            self.stats["current_queue_size"] = len(self._generation_queue)
        
        # Wait for and stream results
        try:
            result_generator = await result_future
            async for token in result_generator:
                yield token
        except Exception as e:
            logger.error(f"Generation request failed: {e}")
            raise
        finally:
            self.stats["requests_processed"] += 1

    async def process_embedding_request(
        self,
        texts: List[str],
        priority: int = 3,
        timeout: float = 60.0,
        request_id: str = None
    ) -> List[List[float]]:
        """Process embedding request with intelligent batching"""
        
        result_future = asyncio.Future()
        
        request_data = {
            "texts": texts,
            "priority": priority,
            "timeout": timeout,
            "timestamp": time.time(),
            "request_id": request_id
        }
        
        queued_request = QueuedRequest(
            priority=priority,
            timestamp=time.time(),
            request_context=None,  # Special handling for embeddings
            future=result_future,
            request_type=RequestType.EMBEDDING
        )
        
        # Store request data in the queued request for processor to access
        queued_request.embedding_data = request_data
        
        async with self._queue_lock:
            heapq.heappush(self._embedding_queue, queued_request)
        
        return await result_future

    async def _generation_processor(self):
        """Background processor for generation requests"""
        while not self._shutdown_event.is_set():
            try:
                request = None
                async with self._queue_lock:
                    if self._generation_queue:
                        request = heapq.heappop(self._generation_queue)
                        self.stats["current_queue_size"] = len(self._generation_queue)
                
                if request:
                    # Check if request has timed out
                    if time.time() - request.timestamp > request.request_context.timeout:
                        request.future.set_exception(
                            asyncio.TimeoutError("Request timed out in queue")
                        )
                        continue
                    
                    # Determine required model type
                    model_type = self._determine_model_type(request.request_context)
                    
                    # Get or load appropriate model
                    model_pool = self.model_pools["generation"]
                    
                    try:
                        # Process the generation request - don't await the async generator
                        result_generator = model_pool.generate_response(
                            model_type=model_type,
                            prompt=request.request_context.prompt,
                            params=request.request_context.generation_params
                        )
                        
                        request.future.set_result(result_generator)
                        
                        # Update utilization stats
                        self._update_model_utilization(model_type)
                        
                    except Exception as e:
                        self.stats["processing_errors"] += 1
                        request.future.set_exception(e)
                        logger.error(f"Generation processing error: {e}")
                
                else:
                    # No requests available, wait briefly
                    await asyncio.sleep(0.1)
                    
            except Exception as e:
                logger.error(f"Error in generation processor: {e}")
                await asyncio.sleep(1)

    async def _embedding_processor(self):
        """Background processor for embedding requests with intelligent batching"""
        batch_buffer = []
        last_batch_time = time.time()
        
        while not self._shutdown_event.is_set():
            try:
                # Collect requests for batching
                while (len(batch_buffer) < self.max_batch_size and 
                       time.time() - last_batch_time < self.batch_timeout):
                    
                    async with self._queue_lock:
                        if self._embedding_queue:
                            request = heapq.heappop(self._embedding_queue)
                            batch_buffer.append(request)
                        else:
                            await asyncio.sleep(0.05)
                            break  # Exit inner loop if no requests
                
                if batch_buffer:
                    await self._process_embedding_batch(batch_buffer)
                    batch_buffer.clear()
                    last_batch_time = time.time()
                else:
                    await asyncio.sleep(0.1)
                    
            except Exception as e:
                logger.error(f"Error in embedding processor: {e}")
                # Set error for any requests in current batch
                for request in batch_buffer:
                    if not request.future.done():
                        request.future.set_exception(e)
                batch_buffer.clear()
                await asyncio.sleep(1)

    async def _process_embedding_batch(self, requests: List[QueuedRequest]):
        """Process a batch of embedding requests efficiently"""
        try:
            # Combine all texts from batch
            all_texts = []
            request_mappings = []
            
            for request in requests:
                embedding_data = request.embedding_data
                start_idx = len(all_texts)
                texts = embedding_data["texts"]
                all_texts.extend(texts)
                request_mappings.append((request, start_idx, len(texts)))
            
            # Generate embeddings for entire batch
            embedding_pool = self.model_pools["embedding"]
            all_embeddings = await embedding_pool.generate_embeddings(all_texts)
            
            # Distribute results back to individual requests
            for request, start_idx, text_count in request_mappings:
                request_embeddings = all_embeddings[start_idx:start_idx + text_count]
                if not request.future.done():
                    request.future.set_result(request_embeddings)
                
        except Exception as e:
            logger.error(f"Embedding batch processing error: {e}")
            # Set error for all requests in batch
            for request, _, _ in request_mappings:
                if not request.future.done():
                    request.future.set_exception(e)

    async def _predictive_model_manager(self):
        """Proactively manage models based on predicted demand"""
        while not self._shutdown_event.is_set():
            try:
                # Run prediction every 30 seconds
                await asyncio.sleep(30)
                
                predicted_model = self.demand_predictor.predict_next_model_need()
                if predicted_model and predicted_model != "embedding":  # Don't preload embedding models
                    generation_pool = self.model_pools["generation"]
                    current_model = generation_pool.get_current_model_type()
                    
                    if predicted_model != current_model:
                        # Check if we can preload without disrupting current operations
                        queue_size = len(self._generation_queue)
                        if queue_size < 3:  # Low load, safe to preload
                            logger.info(f"Preloading predicted model: {predicted_model}")
                            await generation_pool.preload_model(predicted_model)
                            
            except Exception as e:
                logger.error(f"Error in predictive model manager: {e}")

    async def _stats_updater(self):
        """Update performance statistics"""
        while not self._shutdown_event.is_set():
            try:
                await asyncio.sleep(10)  # Update every 10 seconds
                
                # Update queue sizes
                async with self._queue_lock:
                    gen_queue_size = len(self._generation_queue)
                    emb_queue_size = len(self._embedding_queue)
                
                self.stats.update({
                    "generation_queue_size": gen_queue_size,
                    "embedding_queue_size": emb_queue_size,
                    "total_queue_size": gen_queue_size + emb_queue_size
                })
                
            except Exception as e:
                logger.error(f"Error in stats updater: {e}")

    def _determine_model_type(self, request_context: RequestContext) -> str:
        """Determine which model type to use based on request"""
        service_to_model = {
            ServiceType.CHAT: "chat",
            ServiceType.SUMMARY: "summary"
        }
        return service_to_model.get(request_context.service_type, "chat")
    
    def _update_model_utilization(self, model_type: str):
        """Update model utilization statistics"""
        current_time = time.time()
        if model_type not in self.stats["model_utilization"]:
            self.stats["model_utilization"][model_type] = {
                "requests": 0,
                "last_used": current_time
            }
        
        self.stats["model_utilization"][model_type]["requests"] += 1
        self.stats["model_utilization"][model_type]["last_used"] = current_time

    async def get_queue_status(self) -> Dict[str, Any]:
        """Get current queue status and performance metrics"""
        async with self._queue_lock:
            generation_queue_size = len(self._generation_queue)
            embedding_queue_size = len(self._embedding_queue)
        
        demand_pattern = self.demand_predictor.get_demand_pattern()
        
        return {
            "generation_queue_size": generation_queue_size,
            "embedding_queue_size": embedding_queue_size,
            "total_requests_processed": self.stats["requests_processed"],
            "processing_errors": self.stats["processing_errors"],
            "model_utilization": self.stats["model_utilization"],
            "demand_pattern": demand_pattern,
            "queue_capacity": {
                "max_size": self.max_queue_size,
                "current_usage": (generation_queue_size + embedding_queue_size) / self.max_queue_size
            }
        }
    
    async def health_check(self) -> Dict[str, Any]:
        """Health check for queue manager"""
        async with self._queue_lock:
            total_queue_size = len(self._generation_queue) + len(self._embedding_queue)
        
        # Check if queues are overwhelmed
        queue_health = total_queue_size < (self.max_queue_size * 0.8)  # 80% threshold
        
        # Check if processors are running
        processors_healthy = all(not task.done() for task in self._processor_tasks)
        
        return {
            "healthy": queue_health and processors_healthy,
            "queue_size": total_queue_size,
            "queue_capacity": self.max_queue_size,
            "processors_running": len([t for t in self._processor_tasks if not t.done()])
        }