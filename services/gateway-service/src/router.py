import asyncio
import aiohttp
import json
import logging
from typing import Dict, Any, List, Optional
from datetime import datetime
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

class ServiceRoute:
    def __init__(self, pattern: str, service_url: str, methods: List[str] = None, auth_required: bool = True):
        self.pattern = pattern
        self.service_url = service_url
        self.methods = methods or ["GET", "POST", "PUT", "DELETE"]
        self.auth_required = auth_required
        self.health_check_url = f"{service_url}/health"
        self.is_healthy = True
        self.last_health_check = datetime.utcnow()

class APIRouter:
    """Route requests to appropriate microservices"""
    
    def __init__(self):
        self.routes: List[ServiceRoute] = []
        self.service_registry: Dict[str, str] = {}
        self.circuit_breakers: Dict[str, Dict[str, Any]] = {}
        self.request_timeout = 30
        self.retry_attempts = 2
        
        # Register default services
        self._register_default_services()
        
    def _register_default_services(self):
        """Register default service routes"""
        default_routes = [
            # Model Service routes
            ServiceRoute("/api/model/status", "http://localhost:8001", ["GET"], False),
            ServiceRoute("/api/model/switch/*", "http://localhost:8001", ["POST"]),
            ServiceRoute("/api/model/generate/*", "http://localhost:8001", ["POST"]),
            ServiceRoute("/api/model/*", "http://localhost:8001"),
            
            # Chat Service routes  
            ServiceRoute("/api/conversations/*", "http://localhost:8002"),
            ServiceRoute("/api/chat/*", "http://localhost:8002"),
            
            # NPC Service routes
            ServiceRoute("/api/npcs/*", "http://localhost:8003"),
            ServiceRoute("/api/search/*", "http://localhost:8003"),
            
            # Summary Service routes
            ServiceRoute("/api/summaries/*", "http://localhost:8004"),
            ServiceRoute("/api/analysis/*", "http://localhost:8004"),
            
            # Monitor Service routes
            ServiceRoute("/api/metrics/*", "http://localhost:8005"),
            ServiceRoute("/api/health/*", "http://localhost:8005", ["GET"], False),
            ServiceRoute("/api/alerts/*", "http://localhost:8005"),
        ]
        
        for route in default_routes:
            self.routes.append(route)
            
        # Register services in registry
        self.service_registry = {
            "model-service": "http://localhost:8001",
            "chat-service": "http://localhost:8002", 
            "npc-service": "http://localhost:8003",
            "summary-service": "http://localhost:8004",
            "monitor-service": "http://localhost:8005"
        }
        
    async def route_request(self, path: str, method: str, body: Dict[str, Any] = None, headers: Dict[str, str] = None) -> Dict[str, Any]:
        """Determine target service and forward request"""
        try:
            # Find matching route
            route = self._find_route(path, method)
            if not route:
                return {
                    "status": 404,
                    "error": "Route not found",
                    "path": path,
                    "method": method
                }
                
            # Check circuit breaker
            service_name = self._get_service_name_from_url(route.service_url)
            if self._is_circuit_open(service_name):
                return {
                    "status": 503,
                    "error": "Service temporarily unavailable",
                    "service": service_name
                }
                
            # Transform path for downstream service
            downstream_path = self._transform_path(path, route)
            
            # Forward request
            response = await self._forward_request(
                route.service_url,
                downstream_path,
                method,
                body,
                headers
            )
            
            # Update circuit breaker on success
            self._record_success(service_name)
            
            return response
            
        except Exception as e:
            logger.error(f"Error routing request {method} {path}: {e}")
            
            # Update circuit breaker on failure
            if 'service_name' in locals():
                self._record_failure(service_name)
                
            return {
                "status": 500,
                "error": "Internal gateway error",
                "message": str(e)
            }
            
    async def aggregate_responses(self, requests: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Combine responses from multiple services"""
        try:
            tasks = []
            
            for req in requests:
                task = self.route_request(
                    req.get("path", ""),
                    req.get("method", "GET"),
                    req.get("body"),
                    req.get("headers")
                )
                tasks.append(task)
                
            # Execute requests concurrently
            responses = await asyncio.gather(*tasks, return_exceptions=True)
            
            # Combine responses
            aggregated = {
                "timestamp": datetime.utcnow().isoformat(),
                "request_count": len(requests),
                "responses": []
            }
            
            for i, response in enumerate(responses):
                if isinstance(response, Exception):
                    aggregated["responses"].append({
                        "request_index": i,
                        "status": 500,
                        "error": str(response)
                    })
                else:
                    aggregated["responses"].append({
                        "request_index": i,
                        **response
                    })
                    
            return aggregated
            
        except Exception as e:
            logger.error(f"Error aggregating responses: {e}")
            return {
                "status": 500,
                "error": "Failed to aggregate responses",
                "message": str(e)
            }
            
    async def handle_service_unavailable(self, service: str) -> Dict[str, Any]:
        """Fallback behavior for failed services"""
        try:
            service_url = self.service_registry.get(service)
            if not service_url:
                return {
                    "status": 404,
                    "error": f"Unknown service: {service}"
                }
                
            # Check if service is in circuit breaker
            if self._is_circuit_open(service):
                return {
                    "status": 503,
                    "error": f"Service {service} is temporarily unavailable",
                    "retry_after": self._get_retry_after(service)
                }
                
            # Try to reach service health endpoint
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.get(
                        f"{service_url}/health",
                        timeout=aiohttp.ClientTimeout(total=5)
                    ) as response:
                        if response.status == 200:
                            # Service is actually healthy, reset circuit breaker
                            self._reset_circuit_breaker(service)
                            return {
                                "status": 200,
                                "message": f"Service {service} is available",
                                "health_check": "passed"
                            }
                        else:
                            return {
                                "status": 503,
                                "error": f"Service {service} health check failed",
                                "status_code": response.status
                            }
                            
            except Exception as e:
                self._record_failure(service)
                return {
                    "status": 503,
                    "error": f"Service {service} is unreachable",
                    "message": str(e)
                }
                
        except Exception as e:
            logger.error(f"Error handling service unavailable for {service}: {e}")
            return {
                "status": 500,
                "error": "Error checking service availability",
                "message": str(e)
            }
            
    def register_service(self, service_name: str, url: str, routes: List[Dict[str, Any]] = None):
        """Register microservice endpoints"""
        try:
            self.service_registry[service_name] = url
            
            # Add custom routes if provided
            if routes:
                for route_config in routes:
                    route = ServiceRoute(
                        pattern=route_config["pattern"],
                        service_url=url,
                        methods=route_config.get("methods", ["GET", "POST"]),
                        auth_required=route_config.get("auth_required", True)
                    )
                    self.routes.append(route)
                    
            logger.info(f"Registered service: {service_name} at {url}")
            
        except Exception as e:
            logger.error(f"Error registering service {service_name}: {e}")
            
    def _find_route(self, path: str, method: str) -> Optional[ServiceRoute]:
        """Find matching route for path and method"""
        for route in self.routes:
            if self._path_matches_pattern(path, route.pattern) and method in route.methods:
                return route
        return None
        
    def _path_matches_pattern(self, path: str, pattern: str) -> bool:
        """Check if path matches route pattern"""
        # Simple pattern matching with wildcard support
        if pattern.endswith("/*"):
            # Wildcard pattern
            prefix = pattern[:-2]
            return path.startswith(prefix)
        else:
            # Exact match
            return path == pattern
            
    def _transform_path(self, original_path: str, route: ServiceRoute) -> str:
        """Transform API gateway path to downstream service path"""
        try:
            # Remove /api prefix and service prefix if present
            path = original_path
            
            if path.startswith("/api/"):
                path = path[4:]  # Remove /api
                
            # Remove service-specific prefixes
            service_prefixes = {
                "model/": "/",
                "conversations/": "/conversations/",
                "chat/": "/", 
                "npcs/": "/npcs/",
                "search/": "/search/",
                "summaries/": "/summaries/",
                "analysis/": "/analysis/",
                "metrics/": "/metrics/",
                "health/": "/health/",
                "alerts/": "/alerts/"
            }
            
            for prefix, replacement in service_prefixes.items():
                if path.startswith(prefix):
                    path = replacement + path[len(prefix):]
                    break
                    
            return path
            
        except Exception as e:
            logger.error(f"Error transforming path {original_path}: {e}")
            return original_path
            
    async def _forward_request(
        self, 
        service_url: str, 
        path: str, 
        method: str, 
        body: Dict[str, Any] = None,
        headers: Dict[str, str] = None
    ) -> Dict[str, Any]:
        """Forward request to downstream service"""
        try:
            url = f"{service_url}{path}"
            request_headers = headers or {}
            
            # Add gateway headers
            request_headers.update({
                "X-Gateway-Request-ID": f"gw_{int(datetime.utcnow().timestamp())}",
                "X-Gateway-Timestamp": datetime.utcnow().isoformat(),
                "User-Agent": "Life-Strands-Gateway/1.0"
            })
            
            async with aiohttp.ClientSession() as session:
                async with session.request(
                    method=method,
                    url=url,
                    json=body if body else None,
                    headers=request_headers,
                    timeout=aiohttp.ClientTimeout(total=self.request_timeout)
                ) as response:
                    
                    # Read response
                    try:
                        if response.content_type == "application/json":
                            response_data = await response.json()
                        else:
                            response_data = await response.text()
                    except:
                        response_data = None
                        
                    return {
                        "status": response.status,
                        "data": response_data,
                        "headers": dict(response.headers),
                        "content_type": response.content_type
                    }
                    
        except asyncio.TimeoutError:
            logger.error(f"Request timeout for {method} {service_url}{path}")
            return {
                "status": 504,
                "error": "Gateway timeout",
                "message": f"Request to {service_url} timed out"
            }
            
        except Exception as e:
            logger.error(f"Error forwarding request to {service_url}{path}: {e}")
            return {
                "status": 502,
                "error": "Bad gateway",
                "message": str(e),
                "service_url": service_url
            }
            
    def _get_service_name_from_url(self, service_url: str) -> str:
        """Extract service name from URL"""
        for name, url in self.service_registry.items():
            if url == service_url:
                return name
        
        # Fallback: extract from URL
        parsed = urlparse(service_url)
        return f"{parsed.hostname}_{parsed.port}"
        
    def _is_circuit_open(self, service_name: str) -> bool:
        """Check if circuit breaker is open for service"""
        if service_name not in self.circuit_breakers:
            return False
            
        circuit = self.circuit_breakers[service_name]
        
        # Check if circuit should be reset
        if circuit["state"] == "open":
            if datetime.utcnow() - circuit["last_failure"] > circuit["reset_timeout"]:
                circuit["state"] = "half_open"
                circuit["failure_count"] = 0
                
        return circuit["state"] == "open"
        
    def _record_success(self, service_name: str):
        """Record successful request for circuit breaker"""
        if service_name in self.circuit_breakers:
            circuit = self.circuit_breakers[service_name]
            if circuit["state"] == "half_open":
                # Reset circuit breaker on successful half-open request
                circuit["state"] = "closed"
                circuit["failure_count"] = 0
                
    def _record_failure(self, service_name: str):
        """Record failed request for circuit breaker"""
        if service_name not in self.circuit_breakers:
            self.circuit_breakers[service_name] = {
                "state": "closed",
                "failure_count": 0,
                "failure_threshold": 5,
                "reset_timeout": timedelta(seconds=60),
                "last_failure": datetime.utcnow()
            }
            
        circuit = self.circuit_breakers[service_name]
        circuit["failure_count"] += 1
        circuit["last_failure"] = datetime.utcnow()
        
        # Open circuit if threshold exceeded
        if circuit["failure_count"] >= circuit["failure_threshold"]:
            circuit["state"] = "open"
            logger.warning(f"Circuit breaker opened for service: {service_name}")
            
    def _reset_circuit_breaker(self, service_name: str):
        """Reset circuit breaker for service"""
        if service_name in self.circuit_breakers:
            self.circuit_breakers[service_name].update({
                "state": "closed",
                "failure_count": 0
            })
            logger.info(f"Circuit breaker reset for service: {service_name}")
            
    def _get_retry_after(self, service_name: str) -> int:
        """Get retry-after time for circuit breaker"""
        if service_name not in self.circuit_breakers:
            return 60
            
        circuit = self.circuit_breakers[service_name]
        elapsed = datetime.utcnow() - circuit["last_failure"]
        remaining = circuit["reset_timeout"] - elapsed
        
        return max(0, int(remaining.total_seconds()))
        
    async def health_check_services(self) -> Dict[str, Any]:
        """Check health of all registered services"""
        try:
            health_results = {
                "timestamp": datetime.utcnow().isoformat(),
                "services": {},
                "summary": {
                    "total": len(self.service_registry),
                    "healthy": 0,
                    "unhealthy": 0
                }
            }
            
            tasks = []
            for service_name, service_url in self.service_registry.items():
                task = self._check_service_health(service_name, service_url)
                tasks.append(task)
                
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            for i, (service_name, _) in enumerate(self.service_registry.items()):
                result = results[i]
                
                if isinstance(result, Exception):
                    health_results["services"][service_name] = {
                        "status": "error",
                        "error": str(result)
                    }
                    health_results["summary"]["unhealthy"] += 1
                else:
                    health_results["services"][service_name] = result
                    if result["status"] == "healthy":
                        health_results["summary"]["healthy"] += 1
                    else:
                        health_results["summary"]["unhealthy"] += 1
                        
            return health_results
            
        except Exception as e:
            logger.error(f"Error checking service health: {e}")
            return {
                "timestamp": datetime.utcnow().isoformat(),
                "error": str(e)
            }
            
    async def _check_service_health(self, service_name: str, service_url: str) -> Dict[str, Any]:
        """Check health of single service"""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{service_url}/health",
                    timeout=aiohttp.ClientTimeout(total=10)
                ) as response:
                    
                    if response.status == 200:
                        try:
                            health_data = await response.json()
                            return {
                                "status": "healthy",
                                "response_time_ms": response.headers.get("X-Response-Time", "unknown"),
                                **health_data
                            }
                        except:
                            return {"status": "healthy"}
                    else:
                        return {
                            "status": "unhealthy",
                            "status_code": response.status
                        }
                        
        except Exception as e:
            return {
                "status": "error",
                "error": str(e)
            }
            
    def get_routing_stats(self) -> Dict[str, Any]:
        """Get routing and circuit breaker statistics"""
        try:
            return {
                "registered_services": len(self.service_registry),
                "registered_routes": len(self.routes),
                "circuit_breakers": {
                    name: {
                        "state": cb["state"],
                        "failure_count": cb["failure_count"],
                        "last_failure": cb["last_failure"].isoformat()
                    }
                    for name, cb in self.circuit_breakers.items()
                },
                "service_registry": self.service_registry
            }
            
        except Exception as e:
            logger.error(f"Error getting routing stats: {e}")
            return {"error": str(e)}
            
    def update_service_url(self, service_name: str, new_url: str):
        """Update service URL (for dynamic service discovery)"""
        try:
            if service_name in self.service_registry:
                old_url = self.service_registry[service_name]
                self.service_registry[service_name] = new_url
                
                # Update routes
                for route in self.routes:
                    if route.service_url == old_url:
                        route.service_url = new_url
                        
                logger.info(f"Updated service URL for {service_name}: {old_url} -> {new_url}")
                
        except Exception as e:
            logger.error(f"Error updating service URL for {service_name}: {e}")
            
    async def initialize(self):
        """Initialize the router"""
        try:
            logger.info("Initializing APIRouter...")
            # Router is already initialized in __init__
            logger.info("APIRouter initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize APIRouter: {e}")
            raise
            
    async def get_service_health(self) -> Dict[str, Any]:
        """Get health status of all services"""
        return await self.health_check_services()
        
    async def proxy_request(self, service_name: str, method: str, path: str, json: Dict[str, Any] = None, headers: Dict[str, str] = None) -> Dict[str, Any]:
        """Proxy request to specific service"""
        try:
            service_url = self.service_registry.get(service_name)
            if not service_url:
                return {
                    "status": 404,
                    "error": f"Service {service_name} not found"
                }
                
            return await self._forward_request(service_url, path, method, json, headers)
            
        except Exception as e:
            logger.error(f"Error proxying request to {service_name}: {e}")
            return {
                "status": 500,
                "error": "Proxy error",
                "message": str(e)
            }