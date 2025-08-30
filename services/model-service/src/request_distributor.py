from enum import Enum
from dataclasses import dataclass
from typing import Dict, Any, Optional, AsyncGenerator, List
import asyncio
import time
import uuid
from fastapi import HTTPException
import logging

logger = logging.getLogger(__name__)

class ServiceType(Enum):
    CHAT = "chat"
    SUMMARY = "summary" 
    NPC = "npc"

class CircuitBreakerState(Enum):
    CLOSED = "closed"      # Normal operation
    OPEN = "open"          # Failing fast
    HALF_OPEN = "half_open" # Testing recovery

@dataclass
class RequestContext:
    service_type: ServiceType
    request_id: str
    priority: int
    timeout: float
    prompt: str
    generation_params: Dict[str, Any]
    estimated_tokens: int

class CircuitBreaker:
    """Circuit breaker implementation for service reliability"""
    
    def __init__(self, service_name: str, failure_threshold: int = 5, 
                 recovery_timeout: int = 60, success_threshold: int = 3):
        self.service_name = service_name
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.success_threshold = success_threshold
        
        self.state = CircuitBreakerState.CLOSED
        self.failure_count = 0
        self.success_count = 0
        self.last_failure_time = 0
        
    def can_proceed(self) -> bool:
        """Check if requests can proceed through this circuit breaker"""
        current_time = time.time()
        
        if self.state == CircuitBreakerState.CLOSED:
            return True
        elif self.state == CircuitBreakerState.OPEN:
            if current_time - self.last_failure_time > self.recovery_timeout:
                self.state = CircuitBreakerState.HALF_OPEN
                self.success_count = 0
                logger.info(f"Circuit breaker for {self.service_name} transitioning to HALF_OPEN")
                return True
            return False
        elif self.state == CircuitBreakerState.HALF_OPEN:
            return True
        
        return False
    
    def record_success(self):
        """Record a successful operation"""
        if self.state == CircuitBreakerState.HALF_OPEN:
            self.success_count += 1
            if self.success_count >= self.success_threshold:
                self.state = CircuitBreakerState.CLOSED
                self.failure_count = 0
                logger.info(f"Circuit breaker for {self.service_name} transitioning to CLOSED")
        elif self.state == CircuitBreakerState.CLOSED:
            self.failure_count = 0  # Reset failure count on success
    
    def record_failure(self):
        """Record a failed operation"""
        self.failure_count += 1
        self.last_failure_time = time.time()
        
        if self.state == CircuitBreakerState.CLOSED and self.failure_count >= self.failure_threshold:
            self.state = CircuitBreakerState.OPEN
            logger.warning(f"Circuit breaker for {self.service_name} transitioning to OPEN")
        elif self.state == CircuitBreakerState.HALF_OPEN:
            self.state = CircuitBreakerState.OPEN
            logger.warning(f"Circuit breaker for {self.service_name} transitioning back to OPEN")

class RequestDistributor:
    """Routes and validates requests with circuit breaker protection"""
    
    def __init__(self, queue_manager, circuit_breaker_config: Dict[str, Any] = None):
        self.queue_manager = queue_manager
        
        # Default circuit breaker configuration
        cb_config = circuit_breaker_config or {
            "failure_threshold": 5,
            "recovery_timeout": 60,
            "success_threshold": 3
        }
        
        self.circuit_breakers = {
            ServiceType.CHAT: CircuitBreaker("chat", **cb_config),
            ServiceType.SUMMARY: CircuitBreaker("summary", **cb_config),
            ServiceType.NPC: CircuitBreaker("npc", **cb_config)
        }
        
        # Request tracking
        self.active_requests = {}
        self.request_stats = {
            "total_requests": 0,
            "failed_requests": 0,
            "circuit_breaker_trips": 0
        }
        
    async def handle_generation_request(
        self, 
        service_type: ServiceType,
        prompt: str,
        generation_params: Dict[str, Any] = None,
        priority: int = None,
        timeout: float = 300.0
    ) -> AsyncGenerator[str, None]:
        """Route generation request through circuit breaker to queue"""
        
        circuit_breaker = self.circuit_breakers[service_type]
        
        if not circuit_breaker.can_proceed():
            self.request_stats["circuit_breaker_trips"] += 1
            raise HTTPException(
                status_code=503, 
                detail=f"Service temporarily unavailable: {service_type.value}"
            )
        
        # Set service-specific defaults
        if priority is None:
            priority = self._get_default_priority(service_type)
        
        request_context = RequestContext(
            service_type=service_type,
            request_id=self._generate_request_id(),
            priority=priority,
            timeout=timeout,
            prompt=prompt,
            generation_params=generation_params or {},
            estimated_tokens=len(prompt) // 4  # Rough estimate
        )
        
        self.request_stats["total_requests"] += 1
        self.active_requests[request_context.request_id] = request_context
        
        try:
            async for token in self.queue_manager.process_generation_request(request_context):
                yield token
                
            circuit_breaker.record_success()
            
        except Exception as e:
            circuit_breaker.record_failure()
            self.request_stats["failed_requests"] += 1
            logger.error(f"Request {request_context.request_id} failed: {e}")
            raise
        finally:
            self.active_requests.pop(request_context.request_id, None)
    
    async def handle_embedding_request(
        self,
        texts: List[str],
        priority: int = 3,
        timeout: float = 60.0
    ) -> List[List[float]]:
        """Handle embedding requests with batching"""
        
        circuit_breaker = self.circuit_breakers[ServiceType.NPC]
        
        if not circuit_breaker.can_proceed():
            self.request_stats["circuit_breaker_trips"] += 1
            raise HTTPException(
                status_code=503,
                detail="Embedding service temporarily unavailable"
            )
            
        request_id = self._generate_request_id()
        self.request_stats["total_requests"] += 1
            
        try:
            result = await self.queue_manager.process_embedding_request(
                texts=texts,
                priority=priority,
                timeout=timeout,
                request_id=request_id
            )
            
            circuit_breaker.record_success()
            return result
            
        except Exception as e:
            circuit_breaker.record_failure()
            self.request_stats["failed_requests"] += 1
            logger.error(f"Embedding request {request_id} failed: {e}")
            raise
    
    def _get_default_priority(self, service_type: ServiceType) -> int:
        """Get default priority based on service type"""
        priorities = {
            ServiceType.CHAT: 1,      # Highest priority (real-time)
            ServiceType.NPC: 3,       # Medium priority (embeddings)
            ServiceType.SUMMARY: 5,   # Lower priority (batch processing)
        }
        return priorities[service_type]
    
    def _generate_request_id(self) -> str:
        """Generate unique request ID"""
        return str(uuid.uuid4())
    
    def get_circuit_breaker_status(self) -> Dict[str, Any]:
        """Get status of all circuit breakers"""
        status = {}
        for service_type, cb in self.circuit_breakers.items():
            status[service_type.value] = {
                "state": cb.state.value,
                "failure_count": cb.failure_count,
                "success_count": cb.success_count,
                "last_failure_time": cb.last_failure_time
            }
        return status
    
    def get_request_stats(self) -> Dict[str, Any]:
        """Get request processing statistics"""
        return {
            **self.request_stats,
            "active_requests": len(self.active_requests),
            "circuit_breaker_status": self.get_circuit_breaker_status()
        }
    
    async def health_check(self) -> Dict[str, Any]:
        """Comprehensive health check"""
        circuit_breaker_health = {}
        overall_healthy = True
        
        for service_type, cb in self.circuit_breakers.items():
            service_healthy = cb.state != CircuitBreakerState.OPEN
            circuit_breaker_health[service_type.value] = {
                "healthy": service_healthy,
                "state": cb.state.value
            }
            if not service_healthy:
                overall_healthy = False
        
        queue_health = await self.queue_manager.health_check() if hasattr(self.queue_manager, 'health_check') else {"healthy": True}
        
        return {
            "healthy": overall_healthy and queue_health.get("healthy", True),
            "circuit_breakers": circuit_breaker_health,
            "queue_manager": queue_health,
            "request_stats": self.get_request_stats()
        }