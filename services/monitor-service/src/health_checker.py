import asyncio
import aiohttp
import asyncpg
import redis.asyncio as redis
import logging
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta
import json

logger = logging.getLogger(__name__)

class HealthChecker:
    """Monitor service health and dependencies"""
    
    def __init__(
        self,
        database_url: str = None,
        redis_url: str = None
    ):
        import os
        self.database_url = database_url or os.getenv("DATABASE_URL", "postgresql://user:pass@localhost/lifestrands")
        self.redis_url = redis_url or os.getenv("REDIS_URL", "redis://localhost:6379")
        
        # Service configurations
        self.services = {
            "model-service": {
                "url": "http://host.docker.internal:8001",
                "health_endpoint": "/health",
                "timeout": 10,
                "critical": True
            },
            "chat-service": {
                "url": "http://localhost:8002", 
                "health_endpoint": "/health",
                "timeout": 5,
                "critical": True
            },
            "npc-service": {
                "url": "http://localhost:8003",
                "health_endpoint": "/health",
                "timeout": 5,
                "critical": True
            },
            "summary-service": {
                "url": "http://localhost:8004",
                "health_endpoint": "/health",
                "timeout": 5,
                "critical": False
            },
            "gateway": {
                "url": "http://localhost:8000",
                "health_endpoint": "/health",
                "timeout": 5,
                "critical": True
            }
        }
        
        # Health check intervals
        self.check_intervals = {
            "services": 30,      # Service health every 30s
            "database": 60,      # Database health every minute
            "redis": 60,         # Redis health every minute
            "deep_check": 300    # Deep health check every 5 minutes
        }
        
        # Health history for trend analysis
        self.health_history = {}
        self.max_history = 100
        
    async def check_all_services(self) -> Dict[str, Any]:
        """Check health of all microservices"""
        try:
            health_results = {
                "timestamp": datetime.utcnow().isoformat(),
                "overall_status": "healthy",
                "services": {},
                "dependencies": {},
                "summary": {
                    "total_services": len(self.services),
                    "healthy_services": 0,
                    "unhealthy_services": 0,
                    "critical_failures": 0
                }
            }
            
            # Check all services concurrently
            service_tasks = [
                self._check_service_health(name, config)
                for name, config in self.services.items()
            ]
            
            service_results = await asyncio.gather(*service_tasks, return_exceptions=True)
            
            # Process results
            for i, result in enumerate(service_results):
                service_name = list(self.services.keys())[i]
                service_config = self.services[service_name]
                
                if isinstance(result, Exception):
                    service_health = {
                        "status": "error",
                        "error": str(result),
                        "critical": service_config["critical"]
                    }
                else:
                    service_health = result
                    
                health_results["services"][service_name] = service_health
                
                # Update summary
                if service_health["status"] == "healthy":
                    health_results["summary"]["healthy_services"] += 1
                else:
                    health_results["summary"]["unhealthy_services"] += 1
                    if service_config["critical"]:
                        health_results["summary"]["critical_failures"] += 1
                        
            # Check dependencies
            dependency_tasks = [
                self.check_database_health(),
                self.check_redis_health()
            ]
            
            db_health, redis_health = await asyncio.gather(*dependency_tasks, return_exceptions=True)
            
            health_results["dependencies"]["database"] = (
                db_health if not isinstance(db_health, Exception) 
                else {"status": "error", "error": str(db_health)}
            )
            
            health_results["dependencies"]["redis"] = (
                redis_health if not isinstance(redis_health, Exception)
                else {"status": "error", "error": str(redis_health)}
            )
            
            # Determine overall status
            if health_results["summary"]["critical_failures"] > 0:
                health_results["overall_status"] = "critical"
            elif health_results["summary"]["unhealthy_services"] > 0:
                health_results["overall_status"] = "degraded"
            elif (health_results["dependencies"]["database"]["status"] != "healthy" or 
                  health_results["dependencies"]["redis"]["status"] != "healthy"):
                health_results["overall_status"] = "degraded"
                
            # Store in history
            self._update_health_history("overall", health_results)
            
            return health_results
            
        except Exception as e:
            logger.error(f"Error checking all services: {e}")
            return {
                "timestamp": datetime.utcnow().isoformat(),
                "overall_status": "error",
                "error": str(e)
            }
            
    async def check_database_health(self) -> Dict[str, Any]:
        """Verify database connectivity and performance"""
        start_time = datetime.utcnow()
        
        try:
            # Test connection
            conn = await asyncpg.connect(self.database_url)
            
            try:
                # Basic connectivity test
                await conn.fetchval("SELECT 1")
                
                # Check if main tables exist
                tables_exist = await conn.fetchval("""
                    SELECT COUNT(*) FROM information_schema.tables 
                    WHERE table_name IN ('npcs', 'conversations', 'conversation_changes', 'system_metrics')
                """)
                
                # Test query performance
                query_start = datetime.utcnow()
                await conn.fetchval("SELECT COUNT(*) FROM npcs")
                query_time = (datetime.utcnow() - query_start).total_seconds() * 1000
                
                # Check connection pool if available
                pool_info = None
                try:
                    pool_stats = await conn.fetchrow("""
                        SELECT 
                            numbackends as active_connections,
                            datname as database_name
                        FROM pg_stat_database 
                        WHERE datname = current_database()
                    """)
                    pool_info = dict(pool_stats) if pool_stats else None
                except:
                    pass
                    
                response_time = (datetime.utcnow() - start_time).total_seconds() * 1000
                
                health_data = {
                    "status": "healthy",
                    "response_time_ms": response_time,
                    "query_time_ms": query_time,
                    "tables_found": int(tables_exist),
                    "expected_tables": 4,
                    "connection_info": pool_info
                }
                
                # Add warnings for slow queries
                if query_time > 1000:  # 1 second
                    health_data["warning"] = "Slow database queries detected"
                    
                return health_data
                
            finally:
                await conn.close()
                
        except asyncpg.ConnectionDoesNotExistError:
            return {
                "status": "error",
                "error": "Database does not exist",
                "response_time_ms": (datetime.utcnow() - start_time).total_seconds() * 1000
            }
        except asyncpg.InvalidPasswordError:
            return {
                "status": "error", 
                "error": "Invalid database credentials",
                "response_time_ms": (datetime.utcnow() - start_time).total_seconds() * 1000
            }
        except Exception as e:
            return {
                "status": "error",
                "error": str(e),
                "response_time_ms": (datetime.utcnow() - start_time).total_seconds() * 1000
            }
            
    async def check_redis_health(self) -> Dict[str, Any]:
        """Verify Redis connectivity and memory"""
        start_time = datetime.utcnow()
        
        try:
            # Connect to Redis
            redis_client = redis.from_url(self.redis_url)
            
            try:
                # Test connectivity
                await redis_client.ping()
                
                # Get Redis info
                info = await redis_client.info()
                
                # Test read/write operations
                test_key = "health_check_test"
                test_value = f"test_{int(datetime.utcnow().timestamp())}"
                
                await redis_client.set(test_key, test_value, ex=10)
                retrieved_value = await redis_client.get(test_key)
                
                if retrieved_value.decode() != test_value:
                    raise Exception("Redis read/write test failed")
                    
                await redis_client.delete(test_key)
                
                response_time = (datetime.utcnow() - start_time).total_seconds() * 1000
                
                # Check memory usage
                used_memory = info.get("used_memory", 0)
                max_memory = info.get("maxmemory", 0)
                memory_usage_percent = (used_memory / max_memory * 100) if max_memory > 0 else 0
                
                health_data = {
                    "status": "healthy",
                    "response_time_ms": response_time,
                    "redis_version": info.get("redis_version"),
                    "uptime_seconds": info.get("uptime_in_seconds"),
                    "connected_clients": info.get("connected_clients"),
                    "used_memory_mb": used_memory // 1024 // 1024,
                    "max_memory_mb": max_memory // 1024 // 1024,
                    "memory_usage_percent": memory_usage_percent,
                    "total_commands_processed": info.get("total_commands_processed"),
                    "keyspace_hits": info.get("keyspace_hits"),
                    "keyspace_misses": info.get("keyspace_misses")
                }
                
                # Add warnings
                if memory_usage_percent > 90:
                    health_data["warning"] = "High memory usage"
                elif memory_usage_percent > 80:
                    health_data["warning"] = "Elevated memory usage"
                    
                return health_data
                
            finally:
                await redis_client.close()
                
        except redis.ConnectionError:
            return {
                "status": "error",
                "error": "Cannot connect to Redis",
                "response_time_ms": (datetime.utcnow() - start_time).total_seconds() * 1000
            }
        except Exception as e:
            return {
                "status": "error",
                "error": str(e),
                "response_time_ms": (datetime.utcnow() - start_time).total_seconds() * 1000
            }
            
    async def check_model_service_health(self) -> Dict[str, Any]:
        """Verify model service responsiveness"""
        try:
            service_health = await self._check_service_health("model-service", self.services["model-service"])
            
            if service_health["status"] == "healthy":
                # Additional model-specific checks
                async with aiohttp.ClientSession() as session:
                    try:
                        # Check model status
                        async with session.get(
                            f"{self.services['model-service']['url']}/status",
                            timeout=aiohttp.ClientTimeout(total=10)
                        ) as response:
                            if response.status == 200:
                                status_data = await response.json()
                                service_health.update({
                                    "model_loaded": status_data.get("state") == "loaded",
                                    "current_model_type": status_data.get("current_model_type"),
                                    "gpu_available": status_data.get("gpu_stats", {}).get("available", False)
                                })
                            else:
                                service_health["warning"] = f"Status endpoint returned {response.status}"
                                
                    except Exception as e:
                        service_health["warning"] = f"Could not get detailed status: {str(e)}"
                        
            return service_health
            
        except Exception as e:
            logger.error(f"Error checking model service health: {e}")
            return {"status": "error", "error": str(e)}
            
    async def trigger_recovery(self, service: str):
        """Attempt to recover failed service"""
        try:
            logger.info(f"Attempting recovery for service: {service}")
            
            if service not in self.services:
                raise ValueError(f"Unknown service: {service}")
                
            # Service-specific recovery strategies
            if service == "model-service":
                await self._recover_model_service()
            elif service == "chat-service":
                await self._recover_chat_service()
            elif service in ["npc-service", "summary-service", "gateway"]:
                await self._recover_generic_service(service)
            else:
                logger.warning(f"No recovery strategy for service: {service}")
                
        except Exception as e:
            logger.error(f"Error triggering recovery for {service}: {e}")
            
    async def _check_service_health(self, service_name: str, config: Dict[str, Any]) -> Dict[str, Any]:
        """Check health of a single service"""
        start_time = datetime.utcnow()
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{config['url']}{config['health_endpoint']}",
                    timeout=aiohttp.ClientTimeout(total=config['timeout'])
                ) as response:
                    
                    response_time = (datetime.utcnow() - start_time).total_seconds() * 1000
                    
                    health_data = {
                        "status": "healthy" if response.status == 200 else "unhealthy",
                        "response_time_ms": response_time,
                        "status_code": response.status,
                        "critical": config["critical"]
                    }
                    
                    # Try to get detailed health info
                    if response.status == 200:
                        try:
                            content_type = response.headers.get('content-type', '')
                            if 'application/json' in content_type:
                                health_details = await response.json()
                                health_data.update(health_details)
                        except:
                            pass  # Health endpoint might not return JSON
                            
                    # Update service history
                    self._update_health_history(service_name, health_data)
                    
                    return health_data
                    
        except asyncio.TimeoutError:
            response_time = (datetime.utcnow() - start_time).total_seconds() * 1000
            health_data = {
                "status": "timeout",
                "response_time_ms": response_time,
                "error": f"Request timeout after {config['timeout']}s",
                "critical": config["critical"]
            }
            self._update_health_history(service_name, health_data)
            return health_data
            
        except Exception as e:
            response_time = (datetime.utcnow() - start_time).total_seconds() * 1000
            health_data = {
                "status": "error",
                "response_time_ms": response_time,
                "error": str(e),
                "critical": config["critical"]
            }
            self._update_health_history(service_name, health_data)
            return health_data
            
    def _update_health_history(self, service_name: str, health_data: Dict[str, Any]):
        """Update health history for trend analysis"""
        if service_name not in self.health_history:
            self.health_history[service_name] = []
            
        history_entry = {
            "timestamp": datetime.utcnow().isoformat(),
            "status": health_data["status"],
            "response_time_ms": health_data.get("response_time_ms", 0)
        }
        
        self.health_history[service_name].append(history_entry)
        
        # Keep only recent history
        if len(self.health_history[service_name]) > self.max_history:
            self.health_history[service_name] = self.health_history[service_name][-self.max_history:]
            
    async def _recover_model_service(self):
        """Attempt to recover model service"""
        try:
            # Try to reset model state
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self.services['model-service']['url']}/reset",
                    timeout=aiohttp.ClientTimeout(total=30)
                ) as response:
                    if response.status == 200:
                        logger.info("Model service reset successful")
                        return
                        
            logger.warning("Model service reset failed")
            
        except Exception as e:
            logger.error(f"Error recovering model service: {e}")
            
    async def _recover_chat_service(self):
        """Attempt to recover chat service"""
        try:
            # Clear any stuck conversations
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self.services['chat-service']['url']}/admin/clear-stuck-sessions",
                    timeout=aiohttp.ClientTimeout(total=10)
                ) as response:
                    if response.status == 200:
                        logger.info("Chat service recovery successful")
                        return
                        
            logger.warning("Chat service recovery failed")
            
        except Exception as e:
            logger.error(f"Error recovering chat service: {e}")
            
    async def _recover_generic_service(self, service_name: str):
        """Generic service recovery"""
        try:
            # Just log the attempt - in production this might trigger container restart
            logger.info(f"Generic recovery triggered for {service_name}")
            
            # Could implement:
            # - Container restart via Docker API
            # - Service restart via systemd
            # - Load balancer health check reset
            # - Cache clearing
            
        except Exception as e:
            logger.error(f"Error in generic recovery for {service_name}: {e}")
            
    def get_health_trends(self, service_name: str, minutes: int = 60) -> Dict[str, Any]:
        """Get health trends for a service"""
        try:
            if service_name not in self.health_history:
                return {"error": f"No health history for {service_name}"}
                
            cutoff_time = datetime.utcnow() - timedelta(minutes=minutes)
            
            recent_entries = [
                entry for entry in self.health_history[service_name]
                if datetime.fromisoformat(entry["timestamp"]) > cutoff_time
            ]
            
            if not recent_entries:
                return {"error": "No recent health data"}
                
            # Calculate trends
            status_counts = {}
            response_times = []
            
            for entry in recent_entries:
                status = entry["status"]
                status_counts[status] = status_counts.get(status, 0) + 1
                
                if entry["response_time_ms"] > 0:
                    response_times.append(entry["response_time_ms"])
                    
            return {
                "service_name": service_name,
                "time_range_minutes": minutes,
                "total_checks": len(recent_entries),
                "status_distribution": status_counts,
                "uptime_percentage": (status_counts.get("healthy", 0) / len(recent_entries)) * 100,
                "avg_response_time_ms": sum(response_times) / len(response_times) if response_times else 0,
                "max_response_time_ms": max(response_times) if response_times else 0,
                "min_response_time_ms": min(response_times) if response_times else 0
            }
            
        except Exception as e:
            logger.error(f"Error getting health trends for {service_name}: {e}")
            return {"error": str(e)}
            
    def get_overall_health_summary(self) -> Dict[str, Any]:
        """Get overall system health summary"""
        try:
            summary = {
                "timestamp": datetime.utcnow().isoformat(),
                "services": {},
                "overall_uptime": 0,
                "critical_services_up": 0,
                "total_critical_services": 0
            }
            
            total_uptime = 0
            service_count = 0
            
            for service_name, config in self.services.items():
                trends = self.get_health_trends(service_name, 60)  # Last hour
                
                if "error" not in trends:
                    uptime = trends["uptime_percentage"]
                    summary["services"][service_name] = {
                        "uptime_percentage": uptime,
                        "critical": config["critical"],
                        "avg_response_time": trends["avg_response_time_ms"]
                    }
                    
                    total_uptime += uptime
                    service_count += 1
                    
                    if config["critical"]:
                        summary["total_critical_services"] += 1
                        if uptime > 95:  # Consider 95%+ as "up"
                            summary["critical_services_up"] += 1
                            
            if service_count > 0:
                summary["overall_uptime"] = total_uptime / service_count
                
            return summary
            
        except Exception as e:
            logger.error(f"Error getting overall health summary: {e}")
            return {"error": str(e)}
            
    async def run_deep_health_check(self) -> Dict[str, Any]:
        """Run comprehensive health check"""
        try:
            deep_check = {
                "timestamp": datetime.utcnow().isoformat(),
                "type": "deep_health_check",
                "results": {}
            }
            
            # Check all services with extended timeouts
            for service_name in self.services:
                self.services[service_name]["timeout"] = 30  # Extended timeout
                
            # Run standard health check
            basic_health = await self.check_all_services()
            deep_check["results"]["basic_health"] = basic_health
            
            # Additional deep checks
            deep_check["results"]["model_service_details"] = await self.check_model_service_health()
            
            # Check database performance
            deep_check["results"]["database_performance"] = await self._check_database_performance()
            
            # Check Redis performance  
            deep_check["results"]["redis_performance"] = await self._check_redis_performance()
            
            # Reset timeouts
            for service_name, config in self.services.items():
                if service_name == "model-service":
                    config["timeout"] = 10
                else:
                    config["timeout"] = 5
                    
            return deep_check
            
        except Exception as e:
            logger.error(f"Error in deep health check: {e}")
            return {"timestamp": datetime.utcnow().isoformat(), "error": str(e)}
            
    async def _check_database_performance(self) -> Dict[str, Any]:
        """Check database performance metrics"""
        try:
            conn = await asyncpg.connect(self.database_url)
            
            try:
                # Test query performance on main tables
                perf_results = {}
                
                tables = ["npcs", "conversations", "conversation_changes"]
                for table in tables:
                    start_time = datetime.utcnow()
                    count = await conn.fetchval(f"SELECT COUNT(*) FROM {table}")
                    query_time = (datetime.utcnow() - start_time).total_seconds() * 1000
                    
                    perf_results[table] = {
                        "row_count": count,
                        "query_time_ms": query_time
                    }
                    
                return {
                    "status": "healthy",
                    "table_performance": perf_results
                }
                
            finally:
                await conn.close()
                
        except Exception as e:
            return {"status": "error", "error": str(e)}
            
    async def _check_redis_performance(self) -> Dict[str, Any]:
        """Check Redis performance metrics"""
        try:
            redis_client = redis.from_url(self.redis_url)
            
            try:
                # Test Redis performance
                start_time = datetime.utcnow()
                
                # Test SET operation
                await redis_client.set("perf_test", "test_value")
                set_time = (datetime.utcnow() - start_time).total_seconds() * 1000
                
                # Test GET operation
                start_time = datetime.utcnow()
                await redis_client.get("perf_test")
                get_time = (datetime.utcnow() - start_time).total_seconds() * 1000
                
                # Cleanup
                await redis_client.delete("perf_test")
                
                return {
                    "status": "healthy",
                    "set_operation_ms": set_time,
                    "get_operation_ms": get_time
                }
                
            finally:
                await redis_client.close()
                
        except Exception as e:
            return {"status": "error", "error": str(e)}
            
    async def initialize(self):
        """Initialize the health checker"""
        try:
            logger.info("Initializing HealthChecker...")
            # Test database connection
            conn = await asyncpg.connect(self.database_url)
            await conn.close()
            
            # Test Redis connection
            redis_client = redis.from_url(self.redis_url)
            await redis_client.ping()
            await redis_client.close()
            
            logger.info("HealthChecker initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize HealthChecker: {e}")
            raise
            
    async def start_monitoring(self):
        """Start the monitoring loop"""
        logger.info("Starting health monitoring...")
        while True:
            try:
                health_results = await self.check_all_services()
                # Store results for metrics collection
                self.last_health_check = health_results
                await asyncio.sleep(self.check_intervals["services"])
            except Exception as e:
                logger.error(f"Error in monitoring loop: {e}")
                await asyncio.sleep(self.check_intervals["services"])
                
    async def stop_monitoring(self):
        """Stop the monitoring"""
        logger.info("Stopping health monitoring...")
        # Could cancel any running tasks here if needed