import asyncio
import psutil
import json
import logging
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta
import aiohttp
import asyncpg
import redis.asyncio as redis

try:
    import GPUtil
    GPU_UTIL_AVAILABLE = True
except ImportError:
    GPU_UTIL_AVAILABLE = False

try:
    import nvidia_ml_py3 as nvml
    nvml.nvmlInit()
    NVML_AVAILABLE = True
except ImportError:
    NVML_AVAILABLE = False

logger = logging.getLogger(__name__)

class MetricsCollector:
    """Collect system and application metrics"""
    
    def __init__(
        self,
        database_url: str = None,
        redis_url: str = None
    ):
        import os
        self.database_url = database_url or os.getenv("DATABASE_URL", "postgresql://user:pass@localhost/lifestrands")
        self.redis_url = redis_url or os.getenv("REDIS_URL", "redis://localhost:6379")
        self.db_pool: Optional[asyncpg.Pool] = None
        self.redis_client: Optional[redis.Redis] = None
        
        # Service endpoints
        self.services = {
            "model-service": "http://host.docker.internal:8001",
            "chat-service": "http://localhost:8002", 
            "npc-service": "http://localhost:8003",
            "summary-service": "http://localhost:8004",
            "gateway": "http://localhost:8000"
        }
        
        # Collection intervals (seconds)
        self.collection_intervals = {
            "system": 30,      # System metrics every 30s
            "services": 60,    # Service metrics every minute
            "gpu": 30,         # GPU metrics every 30s
            "database": 120    # Database metrics every 2 minutes
        }
        
        # Collection state
        self.is_collecting = False
        self.collection_tasks = []
        
    async def initialize(self):
        """Initialize database and Redis connections"""
        try:
            # Initialize database connection pool
            self.db_pool = await asyncpg.create_pool(
                self.database_url,
                min_size=2,
                max_size=10
            )
            
            # Initialize Redis connection
            self.redis_client = redis.from_url(self.redis_url)
            await self.redis_client.ping()
            
            logger.info("MetricsCollector initialized successfully")
            
        except Exception as e:
            logger.error(f"Failed to initialize MetricsCollector: {e}")
            raise
            
    async def collect_gpu_metrics(self) -> Dict[str, Any]:
        """GPU usage, temperature, memory"""
        try:
            gpu_metrics = {
                "timestamp": datetime.utcnow().isoformat(),
                "available": False,
                "devices": []
            }
            
            # Try NVML first (more detailed info)
            if NVML_AVAILABLE:
                try:
                    device_count = nvml.nvmlDeviceGetCount()
                    gpu_metrics["available"] = device_count > 0
                    
                    for i in range(device_count):
                        handle = nvml.nvmlDeviceGetHandleByIndex(i)
                        name = nvml.nvmlDeviceGetName(handle).decode('utf-8')
                        
                        # Memory info
                        mem_info = nvml.nvmlDeviceGetMemoryInfo(handle)
                        memory_total = mem_info.total // 1024 // 1024
                        memory_used = mem_info.used // 1024 // 1024
                        memory_free = mem_info.free // 1024 // 1024
                        
                        # Temperature
                        try:
                            temp = nvml.nvmlDeviceGetTemperature(handle, nvml.NVML_TEMPERATURE_GPU)
                        except:
                            temp = None
                            
                        # Utilization
                        try:
                            util = nvml.nvmlDeviceGetUtilizationRates(handle)
                            gpu_util = util.gpu
                            mem_util = util.memory
                        except:
                            gpu_util = None
                            mem_util = None
                            
                        device_metrics = {
                            "device_id": i,
                            "name": name,
                            "memory_total_mb": memory_total,
                            "memory_used_mb": memory_used,
                            "memory_free_mb": memory_free,
                            "memory_utilization_percent": (memory_used / memory_total * 100) if memory_total > 0 else 0,
                            "temperature_c": temp,
                            "gpu_utilization_percent": gpu_util,
                            "memory_bandwidth_utilization_percent": mem_util
                        }
                        
                        gpu_metrics["devices"].append(device_metrics)
                        
                except Exception as e:
                    logger.debug(f"NVML error: {e}")
                    
            # Fallback to GPUtil
            elif GPU_UTIL_AVAILABLE:
                try:
                    gpus = GPUtil.getGPUs()
                    gpu_metrics["available"] = len(gpus) > 0
                    
                    for i, gpu in enumerate(gpus):
                        device_metrics = {
                            "device_id": i,
                            "name": gpu.name,
                            "memory_total_mb": gpu.memoryTotal,
                            "memory_used_mb": gpu.memoryUsed,
                            "memory_free_mb": gpu.memoryFree,
                            "memory_utilization_percent": gpu.memoryUtil * 100,
                            "temperature_c": gpu.temperature,
                            "gpu_utilization_percent": gpu.load * 100
                        }
                        
                        gpu_metrics["devices"].append(device_metrics)
                        
                except Exception as e:
                    logger.debug(f"GPUtil error: {e}")
                    
            return gpu_metrics
            
        except Exception as e:
            logger.error(f"Error collecting GPU metrics: {e}")
            return {"timestamp": datetime.utcnow().isoformat(), "available": False, "error": str(e)}
            
    async def collect_cpu_metrics(self) -> Dict[str, Any]:
        """CPU usage, load average"""
        try:
            # CPU usage
            cpu_percent = psutil.cpu_percent(interval=1)
            cpu_count = psutil.cpu_count()
            cpu_freq = psutil.cpu_freq()
            
            # Load average (Unix systems)
            try:
                load_avg = psutil.getloadavg()
            except AttributeError:
                load_avg = None
                
            # Per-core CPU usage
            per_cpu = psutil.cpu_percent(percpu=True)
            
            return {
                "timestamp": datetime.utcnow().isoformat(),
                "cpu_percent": cpu_percent,
                "cpu_count": cpu_count,
                "frequency_mhz": cpu_freq.current if cpu_freq else None,
                "load_average": list(load_avg) if load_avg else None,
                "per_cpu_percent": per_cpu
            }
            
        except Exception as e:
            logger.error(f"Error collecting CPU metrics: {e}")
            return {"timestamp": datetime.utcnow().isoformat(), "error": str(e)}
            
    async def collect_memory_metrics(self) -> Dict[str, Any]:
        """System memory usage"""
        try:
            # Virtual memory
            memory = psutil.virtual_memory()
            
            # Swap memory
            swap = psutil.swap_memory()
            
            return {
                "timestamp": datetime.utcnow().isoformat(),
                "virtual_memory": {
                    "total_mb": memory.total // 1024 // 1024,
                    "available_mb": memory.available // 1024 // 1024,
                    "used_mb": memory.used // 1024 // 1024,
                    "percent": memory.percent,
                    "free_mb": memory.free // 1024 // 1024,
                    "buffers_mb": getattr(memory, 'buffers', 0) // 1024 // 1024,
                    "cached_mb": getattr(memory, 'cached', 0) // 1024 // 1024
                },
                "swap_memory": {
                    "total_mb": swap.total // 1024 // 1024,
                    "used_mb": swap.used // 1024 // 1024,
                    "free_mb": swap.free // 1024 // 1024,
                    "percent": swap.percent
                }
            }
            
        except Exception as e:
            logger.error(f"Error collecting memory metrics: {e}")
            return {"timestamp": datetime.utcnow().isoformat(), "error": str(e)}
            
    async def collect_disk_metrics(self) -> Dict[str, Any]:
        """Disk usage and I/O metrics"""
        try:
            # Disk usage for all mounted filesystems
            disk_usage = []
            for partition in psutil.disk_partitions():
                try:
                    usage = psutil.disk_usage(partition.mountpoint)
                    disk_usage.append({
                        "device": partition.device,
                        "mountpoint": partition.mountpoint,
                        "fstype": partition.fstype,
                        "total_gb": usage.total // 1024 // 1024 // 1024,
                        "used_gb": usage.used // 1024 // 1024 // 1024,
                        "free_gb": usage.free // 1024 // 1024 // 1024,
                        "percent": (usage.used / usage.total * 100) if usage.total > 0 else 0
                    })
                except PermissionError:
                    continue
                    
            # Disk I/O
            disk_io = psutil.disk_io_counters()
            
            return {
                "timestamp": datetime.utcnow().isoformat(),
                "disk_usage": disk_usage,
                "disk_io": {
                    "read_count": disk_io.read_count,
                    "write_count": disk_io.write_count,
                    "read_bytes": disk_io.read_bytes,
                    "write_bytes": disk_io.write_bytes,
                    "read_time": disk_io.read_time,
                    "write_time": disk_io.write_time
                } if disk_io else None
            }
            
        except Exception as e:
            logger.error(f"Error collecting disk metrics: {e}")
            return {"timestamp": datetime.utcnow().isoformat(), "error": str(e)}
            
    async def collect_network_metrics(self) -> Dict[str, Any]:
        """Network I/O metrics"""
        try:
            # Network I/O
            net_io = psutil.net_io_counters()
            
            # Per-interface statistics
            per_interface = {}
            for interface, stats in psutil.net_io_counters(pernic=True).items():
                per_interface[interface] = {
                    "bytes_sent": stats.bytes_sent,
                    "bytes_recv": stats.bytes_recv,
                    "packets_sent": stats.packets_sent,
                    "packets_recv": stats.packets_recv,
                    "errin": stats.errin,
                    "errout": stats.errout,
                    "dropin": stats.dropin,
                    "dropout": stats.dropout
                }
                
            return {
                "timestamp": datetime.utcnow().isoformat(),
                "total": {
                    "bytes_sent": net_io.bytes_sent,
                    "bytes_recv": net_io.bytes_recv,
                    "packets_sent": net_io.packets_sent,
                    "packets_recv": net_io.packets_recv,
                    "errin": net_io.errin,
                    "errout": net_io.errout,
                    "dropin": net_io.dropin,
                    "dropout": net_io.dropout
                },
                "per_interface": per_interface
            }
            
        except Exception as e:
            logger.error(f"Error collecting network metrics: {e}")
            return {"timestamp": datetime.utcnow().isoformat(), "error": str(e)}
            
    async def collect_service_metrics(self) -> Dict[str, Any]:
        """Response times, queue depths, active sessions"""
        try:
            service_metrics = {
                "timestamp": datetime.utcnow().isoformat(),
                "services": {}
            }
            
            # Collect metrics from each service
            for service_name, base_url in self.services.items():
                try:
                    service_data = await self._collect_single_service_metrics(service_name, base_url)
                    service_metrics["services"][service_name] = service_data
                except Exception as e:
                    logger.warning(f"Failed to collect metrics from {service_name}: {e}")
                    service_metrics["services"][service_name] = {
                        "status": "error",
                        "error": str(e)
                    }
                    
            return service_metrics
            
        except Exception as e:
            logger.error(f"Error collecting service metrics: {e}")
            return {"timestamp": datetime.utcnow().isoformat(), "error": str(e)}
            
    async def collect_model_metrics(self) -> Dict[str, Any]:
        """Token speed, model state, queue length"""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{self.services['model-service']}/status",
                    timeout=aiohttp.ClientTimeout(total=10)
                ) as response:
                    
                    if response.status == 200:
                        status_data = await response.json()
                        
                        return {
                            "timestamp": datetime.utcnow().isoformat(),
                            "model_state": status_data.get("state"),
                            "current_model_type": status_data.get("current_model_type"),
                            "gpu_stats": status_data.get("gpu_stats", {}),
                            "memory_usage": status_data.get("gpu_stats", {}).get("memory_used_mb", 0),
                            "temperature": status_data.get("gpu_stats", {}).get("temperature_c", 0),
                            "status": "healthy"
                        }
                    else:
                        return {
                            "timestamp": datetime.utcnow().isoformat(),
                            "status": "error",
                            "error": f"HTTP {response.status}"
                        }
                        
        except Exception as e:
            logger.error(f"Error collecting model metrics: {e}")
            return {
                "timestamp": datetime.utcnow().isoformat(),
                "status": "error",
                "error": str(e)
            }
            
    async def collect_database_metrics(self) -> Dict[str, Any]:
        """Database performance and connection metrics"""
        try:
            if not self.db_pool:
                return {"timestamp": datetime.utcnow().isoformat(), "error": "Database not connected"}
                
            async with self.db_pool.acquire() as conn:
                # Connection pool stats
                pool_stats = {
                    "size": self.db_pool.get_size(),
                    "min_size": self.db_pool.get_min_size(),
                    "max_size": self.db_pool.get_max_size(),
                    "idle_connections": self.db_pool.get_idle_size()
                }
                
                # Database stats
                db_stats = await conn.fetchrow("""
                    SELECT 
                        numbackends as active_connections,
                        xact_commit as transactions_committed,
                        xact_rollback as transactions_rolled_back,
                        blks_read as blocks_read,
                        blks_hit as blocks_hit,
                        tup_returned as tuples_returned,
                        tup_fetched as tuples_fetched,
                        tup_inserted as tuples_inserted,
                        tup_updated as tuples_updated,
                        tup_deleted as tuples_deleted
                    FROM pg_stat_database 
                    WHERE datname = current_database()
                """)
                
                # Table stats for main tables
                table_stats = await conn.fetch("""
                    SELECT 
                        schemaname,
                        tablename,
                        n_tup_ins as inserts,
                        n_tup_upd as updates,
                        n_tup_del as deletes,
                        n_live_tup as live_tuples,
                        n_dead_tup as dead_tuples,
                        last_vacuum,
                        last_autovacuum,
                        last_analyze,
                        last_autoanalyze
                    FROM pg_stat_user_tables
                    WHERE tablename IN ('npcs', 'conversations', 'conversation_changes')
                """)
                
                # Index usage stats
                index_stats = await conn.fetch("""
                    SELECT 
                        schemaname,
                        tablename,
                        indexname,
                        idx_tup_read,
                        idx_tup_fetch
                    FROM pg_stat_user_indexes
                    WHERE tablename IN ('npcs', 'conversations', 'conversation_changes')
                """)
                
                return {
                    "timestamp": datetime.utcnow().isoformat(),
                    "pool_stats": dict(pool_stats),
                    "database_stats": dict(db_stats) if db_stats else {},
                    "table_stats": [dict(row) for row in table_stats],
                    "index_stats": [dict(row) for row in index_stats],
                    "status": "healthy"
                }
                
        except Exception as e:
            logger.error(f"Error collecting database metrics: {e}")
            return {
                "timestamp": datetime.utcnow().isoformat(),
                "status": "error",
                "error": str(e)
            }
            
    async def collect_redis_metrics(self) -> Dict[str, Any]:
        """Redis performance and usage metrics"""
        try:
            if not self.redis_client:
                return {"timestamp": datetime.utcnow().isoformat(), "error": "Redis not connected"}
                
            # Get Redis info
            info = await self.redis_client.info()
            
            # Get queue lengths
            queue_lengths = {}
            queue_names = ["summary_queue", "poison_messages"]
            
            for queue_name in queue_names:
                try:
                    length = await self.redis_client.llen(queue_name)
                    queue_lengths[queue_name] = length
                except:
                    queue_lengths[queue_name] = 0
                    
            # Get key count by pattern
            key_counts = {}
            patterns = ["conversation:*", "summary:*", "model_service:*"]
            
            for pattern in patterns:
                try:
                    keys = await self.redis_client.keys(pattern)
                    key_counts[pattern] = len(keys)
                except:
                    key_counts[pattern] = 0
                    
            return {
                "timestamp": datetime.utcnow().isoformat(),
                "server_info": {
                    "redis_version": info.get("redis_version"),
                    "uptime_in_seconds": info.get("uptime_in_seconds"),
                    "connected_clients": info.get("connected_clients"),
                    "used_memory": info.get("used_memory"),
                    "used_memory_human": info.get("used_memory_human"),
                    "maxmemory": info.get("maxmemory"),
                    "maxmemory_human": info.get("maxmemory_human")
                },
                "stats": {
                    "total_connections_received": info.get("total_connections_received"),
                    "total_commands_processed": info.get("total_commands_processed"),
                    "keyspace_hits": info.get("keyspace_hits"),
                    "keyspace_misses": info.get("keyspace_misses"),
                    "expired_keys": info.get("expired_keys"),
                    "evicted_keys": info.get("evicted_keys")
                },
                "queue_lengths": queue_lengths,
                "key_counts": key_counts,
                "status": "healthy"
            }
            
        except Exception as e:
            logger.error(f"Error collecting Redis metrics: {e}")
            return {
                "timestamp": datetime.utcnow().isoformat(),
                "status": "error", 
                "error": str(e)
            }
            
    async def aggregate_metrics(self, window: int) -> Dict[str, Any]:
        """Aggregate metrics over time window"""
        try:
            end_time = datetime.utcnow()
            start_time = end_time - timedelta(seconds=window)
            
            if not self.db_pool:
                return {"error": "Database not connected"}
                
            async with self.db_pool.acquire() as conn:
                # Get metrics within time window
                metrics = await conn.fetch("""
                    SELECT 
                        metric_type,
                        metric_name,
                        service_name,
                        AVG(metric_value) as avg_value,
                        MIN(metric_value) as min_value,
                        MAX(metric_value) as max_value,
                        COUNT(*) as sample_count
                    FROM system_metrics 
                    WHERE recorded_at BETWEEN $1 AND $2
                    GROUP BY metric_type, metric_name, service_name
                    ORDER BY metric_type, service_name, metric_name
                """, start_time, end_time)
                
                aggregated = {
                    "time_window_seconds": window,
                    "start_time": start_time.isoformat(),
                    "end_time": end_time.isoformat(),
                    "metrics": {}
                }
                
                for row in metrics:
                    metric_type = row["metric_type"]
                    service_name = row["service_name"]
                    
                    if metric_type not in aggregated["metrics"]:
                        aggregated["metrics"][metric_type] = {}
                        
                    if service_name not in aggregated["metrics"][metric_type]:
                        aggregated["metrics"][metric_type][service_name] = {}
                        
                    aggregated["metrics"][metric_type][service_name][row["metric_name"]] = {
                        "avg": float(row["avg_value"]),
                        "min": float(row["min_value"]),
                        "max": float(row["max_value"]),
                        "samples": row["sample_count"]
                    }
                    
                return aggregated
                
        except Exception as e:
            logger.error(f"Error aggregating metrics: {e}")
            return {"error": str(e)}
            
    async def _collect_single_service_metrics(self, service_name: str, base_url: str) -> Dict[str, Any]:
        """Collect metrics from a single service"""
        start_time = datetime.utcnow()
        
        try:
            async with aiohttp.ClientSession() as session:
                # Health check
                async with session.get(
                    f"{base_url}/health",
                    timeout=aiohttp.ClientTimeout(total=10)
                ) as response:
                    
                    response_time = (datetime.utcnow() - start_time).total_seconds() * 1000
                    
                    service_data = {
                        "status": "healthy" if response.status == 200 else "unhealthy",
                        "response_time_ms": response_time,
                        "status_code": response.status
                    }
                    
                    if response.status == 200:
                        try:
                            health_data = await response.json()
                            service_data.update(health_data)
                        except:
                            pass  # Health endpoint might not return JSON
                            
                    return service_data
                    
        except asyncio.TimeoutError:
            return {
                "status": "timeout",
                "response_time_ms": 10000,
                "error": "Request timeout"
            }
        except Exception as e:
            return {
                "status": "error",
                "error": str(e),
                "response_time_ms": (datetime.utcnow() - start_time).total_seconds() * 1000
            }
            
    async def store_metrics(self, metrics: Dict[str, Any], metric_type: str, service_name: str):
        """Store metrics in database"""
        try:
            if not self.db_pool:
                return
                
            async with self.db_pool.acquire() as conn:
                timestamp = datetime.utcnow()
                
                # Insert metrics
                for key, value in metrics.items():
                    if key in ["timestamp", "error", "status"]:
                        continue
                        
                    if isinstance(value, (int, float)):
                        await conn.execute("""
                            INSERT INTO system_metrics 
                            (metric_type, metric_name, metric_value, service_name, recorded_at)
                            VALUES ($1, $2, $3, $4, $5)
                        """, metric_type, key, float(value), service_name, timestamp)
                        
        except Exception as e:
            logger.error(f"Error storing metrics: {e}")
            
    async def get_recent_metrics(self, minutes: int = 10) -> Dict[str, Any]:
        """Get recent metrics for dashboard"""
        try:
            if not self.db_pool:
                return {"error": "Database not connected"}
                
            cutoff_time = datetime.utcnow() - timedelta(minutes=minutes)
            
            async with self.db_pool.acquire() as conn:
                metrics = await conn.fetch("""
                    SELECT 
                        metric_type,
                        metric_name,
                        service_name,
                        metric_value,
                        recorded_at
                    FROM system_metrics 
                    WHERE recorded_at > $1
                    ORDER BY recorded_at DESC
                    LIMIT 1000
                """, cutoff_time)
                
                return {
                    "time_range_minutes": minutes,
                    "metric_count": len(metrics),
                    "metrics": [dict(row) for row in metrics]
                }
                
        except Exception as e:
            logger.error(f"Error getting recent metrics: {e}")
            return {"error": str(e)}
            
    async def cleanup_old_metrics(self, days: int = 30):
        """Clean up old metric data"""
        try:
            if not self.db_pool:
                return 0
                
            cutoff_time = datetime.utcnow() - timedelta(days=days)
            
            async with self.db_pool.acquire() as conn:
                result = await conn.execute("""
                    DELETE FROM system_metrics 
                    WHERE recorded_at < $1
                """, cutoff_time)
                
                deleted_count = int(result.split()[-1])
                logger.info(f"Cleaned up {deleted_count} old metrics (older than {days} days)")
                
                return deleted_count
                
        except Exception as e:
            logger.error(f"Error cleaning up old metrics: {e}")
            return 0
            
    async def start_collection(self):
        """Start background metrics collection"""
        try:
            if self.is_collecting:
                logger.warning("Metrics collection is already running")
                return
                
            self.is_collecting = True
            
            # Start collection tasks for different metrics
            for metric_type, interval in self.collection_intervals.items():
                task = asyncio.create_task(
                    self._collection_loop(metric_type, interval)
                )
                self.collection_tasks.append(task)
                
            logger.info(f"Started {len(self.collection_tasks)} metrics collection tasks")
            
        except Exception as e:
            logger.error(f"Failed to start metrics collection: {e}")
            self.is_collecting = False
            
    async def stop_collection(self):
        """Stop background metrics collection"""
        try:
            self.is_collecting = False
            
            # Cancel all collection tasks
            for task in self.collection_tasks:
                if not task.done():
                    task.cancel()
                    
            # Wait for tasks to complete/cancel
            if self.collection_tasks:
                await asyncio.gather(*self.collection_tasks, return_exceptions=True)
                
            self.collection_tasks.clear()
            logger.info("Metrics collection stopped")
            
        except Exception as e:
            logger.error(f"Error stopping metrics collection: {e}")
            
    async def _collection_loop(self, metric_type: str, interval: int):
        """Background collection loop for specific metric type"""
        try:
            while self.is_collecting:
                try:
                    if metric_type == "system":
                        metrics = await self.collect_system_metrics()
                        await self.store_metrics("system", metrics)
                    elif metric_type == "services":
                        for service_name, url in self.services.items():
                            metrics = await self.collect_service_metrics(service_name, url)
                            await self.store_metrics(f"service_{service_name}", metrics)
                    elif metric_type == "gpu":
                        metrics = await self.collect_gpu_metrics()
                        await self.store_metrics("gpu", metrics)
                    elif metric_type == "database":
                        metrics = await self.collect_database_metrics()
                        await self.store_metrics("database", metrics)
                        
                except Exception as e:
                    logger.error(f"Error collecting {metric_type} metrics: {e}")
                    
                await asyncio.sleep(interval)
                
        except asyncio.CancelledError:
            logger.info(f"{metric_type} metrics collection loop cancelled")
        except Exception as e:
            logger.error(f"Error in {metric_type} collection loop: {e}")