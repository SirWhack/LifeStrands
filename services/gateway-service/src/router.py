import asyncio
import aiohttp
import json
import logging
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta
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
        self._session: Optional[aiohttp.ClientSession] = None
        # Register default services
        self._register_default_services()

    def _register_default_services(self):
        """Register default service routes"""
        default_routes = [
            # Model Service routes (native Windows service)
            ServiceRoute("/api/model/status", "http://host.docker.internal:8001", ["GET"], False),
            ServiceRoute("/api/model/switch/*", "http://host.docker.internal:8001", ["POST"]),
            ServiceRoute("/api/model/generate/*", "http://host.docker.internal:8001", ["POST"]),
            ServiceRoute("/api/model/*", "http://host.docker.internal:8001"),
            # Chat Service routes (Docker services)
            ServiceRoute("/api/conversations/*", "http://chat-service:8002"),
            ServiceRoute("/api/chat/*", "http://chat-service:8002"),
            # NPC Service routes
            ServiceRoute("/api/npcs/*", "http://npc-service:8003"),
            ServiceRoute("/api/search/*", "http://npc-service:8003"),
            # Summary Service routes
            ServiceRoute("/api/summaries/*", "http://summary-service:8004"),
            ServiceRoute("/api/analysis/*", "http://summary-service:8004"),
            # Monitor Service routes
            ServiceRoute("/api/metrics/*", "http://monitor-service:8005"),
            ServiceRoute("/api/health/*", "http://monitor-service:8005", ["GET"], False),
            ServiceRoute("/api/alerts/*", "http://monitor-service:8005"),
        ]
        for route in default_routes:
            self.routes.append(route)

        # Register services in registry
        self.service_registry = {
            "model-service": "http://host.docker.internal:8001",
            "chat-service": "http://chat-service:8002",
            "npc-service": "http://npc-service:8003",
            "summary-service": "http://summary-service:8004",
            "monitor-service": "http://monitor-service:8005",
        }

    async def route_request(
        self,
        path: str,
        method: str,
        body: Dict[str, Any] = None,
        headers: Dict[str, str] = None,
        user: Dict[str, Any] = None,
    ) -> Dict[str, Any]:
        """Determine target service and forward request"""
        try:
            # Find matching route
            route = self._find_route(path, method)
            if not route:
                return {"status": 404, "error": "Route not found", "path": path, "method": method}

            # Enforce auth if required
            if route.auth_required:
                authz = headers.get("Authorization") if headers else None
                api_key = headers.get("X-API-Key") if headers else None
                if not (user or authz or api_key):
                    return {"status": 401, "error": "Authentication required"}

            # Transform path for downstream service
            downstream_path = self._transform_path(path, route)

            # Check circuit breaker
            service_name = self._get_service_name_from_url(route.service_url)
            if self._is_circuit_open(service_name):
                return {"status": 503, "error": "Service temporarily unavailable", "service": service_name}

            # Forward request
            response = await self._forward_request(
                route.service_url,
                downstream_path,
                method,
                body,
                headers,
            )

            # Update circuit breaker on success-ish status
            if 200 <= response.get("status", 500) < 500:
                self._record_success(service_name)
            else:
                self._record_failure(service_name)

            return response
        except Exception as e:
            logger.error(f"Error routing request {method} {path}: {e}")
            if "service_name" in locals():
                self._record_failure(service_name)
            return {"status": 500, "error": "Internal gateway error", "message": str(e)}

    async def aggregate_responses(self, requests: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Combine responses from multiple services"""
        try:
            tasks = []
            for req in requests:
                task = self.route_request(
                    req.get("path", ""),
                    req.get("method", "GET"),
                    req.get("body"),
                    req.get("headers"),
                )
                tasks.append(task)

            responses = await asyncio.gather(*tasks, return_exceptions=True)

            aggregated = {"timestamp": datetime.utcnow().isoformat(), "request_count": len(requests), "responses": []}
            for i, response in enumerate(responses):
                if isinstance(response, Exception):
                    aggregated["responses"].append({"request_index": i, "status": 500, "error": str(response)})
                else:
                    aggregated["responses"].append({"request_index": i, **response})
            return aggregated
        except Exception as e:
            logger.error(f"Error aggregating responses: {e}")
            return {"status": 500, "error": "Failed to aggregate responses", "message": str(e)}

    def register_service(self, service_name: str, url: str, routes: List[Dict[str, Any]] = None):
        """Register microservice endpoints"""
        try:
            self.service_registry[service_name] = url
            if routes:
                for route_config in routes:
                    route = ServiceRoute(
                        pattern=route_config["pattern"],
                        service_url=url,
                        methods=route_config.get("methods", ["GET", "POST"]),
                        auth_required=route_config.get("auth_required", True),
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
        if pattern.endswith("/*"):
            prefix = pattern[:-2]
            return path.startswith(prefix)
        return path == pattern

    def _transform_path(self, original_path: str, route: ServiceRoute) -> str:
        """Transform API gateway path to downstream service path"""
        try:
            path = original_path
            if path.startswith("/api/"):
                path = path[4:]  # Remove /api

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
                "alerts/": "/alerts/",
            }
            for prefix, replacement in service_prefixes.items():
                if path.startswith(prefix):
                    path = replacement + path[len(prefix) :]
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
        headers: Dict[str, str] = None,
    ) -> Dict[str, Any]:
        """Forward request to downstream service"""
        try:
            url = f"{service_url}{path}"
            request_headers = headers or {}
            request_headers.update(
                {
                    "X-Gateway-Request-ID": f"gw_{int(datetime.utcnow().timestamp())}",
                    "X-Gateway-Timestamp": datetime.utcnow().isoformat(),
                    "User-Agent": "Life-Strands-Gateway/1.0",
                }
            )

            session = self._session or aiohttp.ClientSession()

            attempt = 0
            last_exc: Optional[BaseException] = None
            while attempt <= self.retry_attempts:
                try:
                    async with session.request(
                        method=method,
                        url=url,
                        json=body if body else None,
                        headers=request_headers,
                    ) as response:
                        try:
                            if response.content_type == "application/json":
                                response_data = await response.json()
                            else:
                                response_data = await response.text()
                        except Exception:
                            response_data = None
                        return {
                            "status": response.status,
                            "data": response_data,
                            "headers": dict(response.headers),
                            "content_type": response.content_type,
                        }
                except (asyncio.TimeoutError, aiohttp.ClientError) as e:
                    last_exc = e
                except Exception as e:
                    last_exc = e
                    break

                # Retry idempotent methods only
                if method.upper() not in {"GET", "HEAD", "OPTIONS"}:
                    break
                await asyncio.sleep(0.25 * (2 ** attempt))
                attempt += 1

            logger.error(f"Request to {service_url}{path} failed after retries: {last_exc}")
            if isinstance(last_exc, asyncio.TimeoutError):
                return {"status": 504, "error": "Gateway timeout", "message": f"Request to {service_url} timed out"}
            return {"status": 502, "error": "Bad gateway", "message": str(last_exc), "service_url": service_url}
        except Exception as e:
            logger.error(f"Error forwarding request to {service_url}{path}: {e}")
            return {"status": 502, "error": "Bad gateway", "message": str(e), "service_url": service_url}

    def _get_service_name_from_url(self, service_url: str) -> str:
        """Extract service name from URL"""
        for name, url in self.service_registry.items():
            if url == service_url:
                return name
        parsed = urlparse(service_url)
        return f"{parsed.hostname}_{parsed.port}"

    def _is_circuit_open(self, service_name: str) -> bool:
        """Check if circuit breaker is open for service"""
        if service_name not in self.circuit_breakers:
            return False
        circuit = self.circuit_breakers[service_name]
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
                "last_failure": datetime.utcnow(),
            }
        circuit = self.circuit_breakers[service_name]
        circuit["failure_count"] += 1
        circuit["last_failure"] = datetime.utcnow()
        if circuit["failure_count"] >= circuit["failure_threshold"]:
            circuit["state"] = "open"
            logger.warning(f"Circuit breaker opened for service: {service_name}")

    def _reset_circuit_breaker(self, service_name: str):
        """Reset circuit breaker for service"""
        if service_name in self.circuit_breakers:
            self.circuit_breakers[service_name].update({"state": "closed", "failure_count": 0})
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
                "summary": {"total": len(self.service_registry), "healthy": 0, "unhealthy": 0},
            }
            tasks = []
            for service_name, service_url in self.service_registry.items():
                task = self._check_service_health(service_name, service_url)
                tasks.append(task)
            results = await asyncio.gather(*tasks, return_exceptions=True)
            for i, (service_name, _) in enumerate(self.service_registry.items()):
                result = results[i]
                if isinstance(result, Exception):
                    health_results["services"][service_name] = {"status": "error", "error": str(result)}
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
            return {"timestamp": datetime.utcnow().isoformat(), "error": str(e)}

    async def _check_service_health(self, service_name: str, service_url: str) -> Dict[str, Any]:
        """Check health of single service"""
        try:
            session = self._session or aiohttp.ClientSession()
            async with session.get(f"{service_url}/health") as response:
                if response.status == 200:
                    try:
                        health_data = await response.json()
                        return {
                            "status": "healthy",
                            "response_time_ms": response.headers.get("X-Response-Time", "unknown"),
                            **health_data,
                        }
                    except Exception:
                        return {"status": "healthy"}
                else:
                    return {"status": "unhealthy", "status_code": response.status}
        except Exception as e:
            return {"status": "error", "error": str(e)}

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
                        "last_failure": cb["last_failure"].isoformat(),
                    }
                    for name, cb in self.circuit_breakers.items()
                },
                "service_registry": self.service_registry,
            }
        except Exception as e:
            logger.error(f"Error getting routing stats: {e}")
            return {"error": str(e)}

    async def initialize(self):
        """Initialize the router"""
        try:
            logger.info("Initializing APIRouter...")
            if self._session is None:
                timeout = aiohttp.ClientTimeout(total=self.request_timeout)
                self._session = aiohttp.ClientSession(timeout=timeout)
            logger.info("APIRouter initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize APIRouter: {e}")
            raise

    async def aclose(self):
        if self._session and not self._session.closed:
            await self._session.close()
