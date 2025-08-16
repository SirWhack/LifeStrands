# CLAUDE.md - Monitor Service

This file provides guidance to Claude Code when working with the Life Strands Monitor Service.

## Service Overview

The Monitor Service provides comprehensive system monitoring, health checking, metrics collection, and alerting for the Life Strands ecosystem. It monitors all services including the native Windows model service and provides real-time system visibility.

**Port:** 8005  
**Purpose:** System Monitoring, Health Checks, Metrics Collection, Alerting  
**Dependencies:** All Services, Redis, PostgreSQL, WebSocket Broadcasting

## Architecture

### Core Components

- **HealthChecker** (`src/health_checker.py`): Service health monitoring and status tracking
- **MetricsCollector** (`src/metrics_collector.py`): Performance metrics gathering and aggregation
- **AlertManager** (`src/alert_manager.py`): Alert generation and notification system
- **WebSocketBroadcaster** (`src/websocket_broadcaster.py`): Real-time monitoring dashboard updates
- **Main Service** (`main.py`): FastAPI application with monitoring endpoints

### Monitoring Scope

**Services Monitored:**
- **Gateway Service** (port 8000): API gateway health and routing metrics
- **Model Service** (port 8001): Native Windows Vulkan service performance
- **Chat Service** (port 8002): Conversation and WebSocket metrics
- **NPC Service** (port 8003): Database and search performance
- **Summary Service** (port 8004): Queue processing and analysis metrics

**Infrastructure Monitored:**
- **PostgreSQL**: Database connectivity and performance
- **Redis**: Queue health and memory usage
- **System Resources**: CPU, memory, disk usage
- **Network**: Service connectivity and latencies

## Key Features

### 1. Health Monitoring

```python
class HealthChecker:
    async def check_all_services(self) -> Dict[str, Any]:
        """Comprehensive health check of all services"""
```

**Health Check Components:**
- **Service Availability**: HTTP endpoint accessibility
- **Response Times**: Latency measurement and tracking
- **Error Rates**: Failed request monitoring
- **Resource Usage**: CPU, memory, GPU metrics
- **Dependency Status**: Database and queue connectivity

### 2. Metrics Collection

```python
class MetricsCollector:
    async def collect_system_metrics(self) -> Dict[str, Any]:
        """Gather comprehensive system metrics"""
```

**Metric Categories:**
- **Performance Metrics**: Response times, throughput, latency
- **Resource Metrics**: CPU, memory, GPU utilization
- **Business Metrics**: Conversations, NPCs, summaries processed
- **Error Metrics**: Failure rates, timeout counts
- **Custom Metrics**: Service-specific measurements

### 3. Alert Management

```python
class AlertManager:
    def evaluate_alert_conditions(self, metrics: Dict) -> List[Alert]:
        """Evaluate metrics against alert thresholds"""
```

**Alert Types:**
- **Critical**: Service down, database unavailable
- **Warning**: High latency, resource usage spikes
- **Info**: Deployment events, configuration changes
- **Performance**: Degraded response times
- **Capacity**: Resource utilization thresholds

### 4. Real-time Broadcasting

```python
class WebSocketBroadcaster:
    async def broadcast_metrics(self, metrics: Dict[str, Any]):
        """Stream metrics to connected dashboards"""
```

**Broadcasting Features:**
- **Live Metrics**: Real-time performance data
- **Health Status**: Service status updates
- **Alert Notifications**: Immediate alert broadcasting
- **Dashboard Updates**: Dynamic visualization updates

## Model Service Integration

### Native Service Monitoring

```python
async def check_model_service_health(self) -> Dict[str, Any]:
    """Monitor native Windows Vulkan model service"""
    
    try:
        # Check basic health
        async with aiohttp.ClientSession() as session:
            async with session.get(
                "http://host.docker.internal:8001/health",
                timeout=aiohttp.ClientTimeout(total=10)
            ) as response:
                health_data = await response.json()
                
        # Get detailed status
        async with session.get(
            "http://host.docker.internal:8001/status"
        ) as response:
            status_data = await response.json()
            
        # Get VRAM usage
        async with session.get(
            "http://host.docker.internal:8001/vram"
        ) as response:
            vram_data = await response.json()
            
        return {
            "status": "healthy",
            "model_type": status_data.get("current_model_type"),
            "gpu_usage": vram_data,
            "platform": "windows-vulkan",
            "performance": self.calculate_model_performance(status_data)
        }
        
    except Exception as e:
        return {
            "status": "error",
            "error": str(e),
            "platform": "windows-vulkan"
        }
```

**Model Service Metrics:**
- **GPU Utilization**: VRAM usage and availability
- **Model Status**: Currently loaded model type
- **Generation Performance**: Tokens per second, latency
- **Queue Status**: Pending requests and processing time
- **Vulkan Health**: GPU driver and runtime status

### Performance Tracking

```python
def calculate_model_performance(self, status_data: Dict) -> Dict:
    """Calculate model service performance metrics"""
    
    return {
        "tokens_per_second": self.extract_tps_from_logs(),
        "average_latency": self.calculate_average_latency(),
        "gpu_memory_usage": status_data.get("gpu_stats", {}).get("used_memory"),
        "model_load_time": status_data.get("last_load_time"),
        "active_requests": status_data.get("active_generation_count", 0)
    }
```

## Metrics and Analytics

### System Metrics

```python
{
    "timestamp": "2024-01-01T12:00:00Z",
    "services": {
        "gateway": {
            "status": "healthy",
            "response_time_ms": 45,
            "requests_per_minute": 120,
            "error_rate": 0.02
        },
        "model_service": {
            "status": "healthy", 
            "platform": "windows-vulkan",
            "gpu_memory_used": "18.5GB",
            "tokens_per_second": 38.4,
            "model_type": "chat"
        },
        "chat_service": {
            "status": "healthy",
            "active_sessions": 15,
            "messages_per_minute": 85,
            "websocket_connections": 23
        }
    },
    "infrastructure": {
        "database": {
            "status": "healthy",
            "connections": 12,
            "query_time_avg": 25
        },
        "redis": {
            "status": "healthy",
            "memory_usage": "256MB",
            "queue_sizes": {
                "summary_queue": 8
            }
        }
    }
}
```

### Business Metrics

```python
{
    "conversations": {
        "active_count": 15,
        "total_today": 127,
        "average_duration": "18 minutes"
    },
    "npcs": {
        "total_count": 245,
        "active_count": 189,
        "updated_today": 34
    },
    "summaries": {
        "processed_today": 89,
        "pending_count": 8,
        "average_processing_time": "45 seconds"
    }
}
```

### Performance Analytics

```python
{
    "response_times": {
        "gateway": {"p50": 45, "p95": 120, "p99": 250},
        "chat_service": {"p50": 32, "p95": 95, "p99": 180},
        "model_service": {"p50": 1200, "p95": 2500, "p99": 4000}
    },
    "throughput": {
        "requests_per_second": 8.5,
        "conversations_per_hour": 42,
        "tokens_generated_per_minute": 2340
    },
    "resource_utilization": {
        "cpu_usage": 45,
        "memory_usage": 68,
        "gpu_memory_usage": 85
    }
}
```

## Alert System

### Alert Configuration

```python
ALERT_THRESHOLDS = {
    "critical": {
        "service_down": {"threshold": 0, "duration": "30s"},
        "database_unreachable": {"threshold": 0, "duration": "10s"},
        "gpu_memory_full": {"threshold": 95, "duration": "60s"}
    },
    "warning": {
        "high_latency": {"threshold": 2000, "duration": "300s"},
        "error_rate": {"threshold": 5, "duration": "120s"},
        "queue_backlog": {"threshold": 50, "duration": "600s"}
    },
    "info": {
        "model_switch": {"threshold": 0, "duration": "0s"},
        "service_restart": {"threshold": 0, "duration": "0s"}
    }
}
```

### Alert Generation

```python
class AlertManager:
    def evaluate_model_service_alerts(self, metrics: Dict) -> List[Alert]:
        """Evaluate model service specific alerts"""
        
        alerts = []
        
        # GPU memory usage
        gpu_usage = metrics.get("gpu_memory_usage", 0)
        if gpu_usage > 95:
            alerts.append(Alert(
                level="critical",
                message=f"GPU memory usage critical: {gpu_usage}%",
                service="model-service",
                metric="gpu_memory_usage"
            ))
            
        # Generation performance
        tps = metrics.get("tokens_per_second", 0)
        if tps < 10:  # Performance degradation
            alerts.append(Alert(
                level="warning", 
                message=f"Model performance degraded: {tps} tokens/second",
                service="model-service",
                metric="generation_performance"
            ))
            
        return alerts
```

### Notification Channels

```python
class NotificationManager:
    async def send_alert(self, alert: Alert):
        """Send alert through configured channels"""
        
        # WebSocket broadcast for dashboards
        await self.websocket_broadcaster.broadcast_alert(alert)
        
        # Email for critical alerts
        if alert.level == "critical":
            await self.send_email_alert(alert)
            
        # Slack integration
        if self.slack_webhook:
            await self.send_slack_alert(alert)
            
        # Log alert
        logger.warning(f"ALERT [{alert.level}]: {alert.message}")
```

## API Endpoints

### Health and Status

```python
# Overall system health
GET /health

# Detailed service status
GET /health/services

# Specific service health
GET /health/{service_name}

# Historical health data
GET /health/history?hours=24
```

### Metrics and Analytics

```python
# Current metrics
GET /metrics

# Historical metrics
GET /metrics/history?start=2024-01-01&end=2024-01-02

# Service-specific metrics
GET /metrics/{service_name}

# Performance analytics
GET /analytics/performance

# Business metrics
GET /analytics/business
```

### Alert Management

```python
# Active alerts
GET /alerts

# Alert history
GET /alerts/history

# Acknowledge alert
POST /alerts/{alert_id}/acknowledge

# Alert configuration
GET /alerts/config
PUT /alerts/config
```

### Real-time Monitoring

```python
# WebSocket endpoint for real-time updates
ws://localhost:8005/ws/monitor

# System dashboard data
GET /dashboard/data

# Service topology
GET /topology
```

## WebSocket Integration

### Real-time Dashboard

```python
class MonitoringWebSocket:
    async def handle_connection(self, websocket: WebSocket):
        """Handle dashboard WebSocket connections"""
        
        await websocket.accept()
        
        # Send initial state
        await self.send_initial_metrics(websocket)
        
        # Start periodic updates
        while True:
            try:
                # Collect current metrics
                metrics = await self.metrics_collector.collect_all()
                
                # Send to dashboard
                await websocket.send_json({
                    "type": "metrics_update",
                    "data": metrics,
                    "timestamp": datetime.utcnow().isoformat()
                })
                
                await asyncio.sleep(5)  # Update every 5 seconds
                
            except WebSocketDisconnect:
                break
```

### Message Types

```python
# Metrics update
{
    "type": "metrics_update",
    "data": {comprehensive_metrics},
    "timestamp": "2024-01-01T12:00:00Z"
}

# Alert notification
{
    "type": "alert",
    "alert": {
        "level": "warning",
        "message": "High latency detected",
        "service": "chat-service"
    }
}

# Service status change
{
    "type": "status_change",
    "service": "model-service",
    "old_status": "generating",
    "new_status": "loaded"
}
```

## Configuration

### Environment Variables

- `REDIS_URL`: Redis connection for metrics storage
- `DATABASE_URL`: PostgreSQL connection for historical data
- `ALERT_EMAIL`: Email address for critical alerts
- `SLACK_WEBHOOK`: Slack webhook for notifications
- `METRICS_RETENTION_DAYS`: How long to keep metrics (30)
- `MONITORING_INTERVAL`: Metrics collection frequency (30s)

### Service URLs

```python
SERVICE_URLS = {
    "gateway": "http://localhost:8000",
    "model_service": "http://host.docker.internal:8001",  # Native service
    "chat_service": "http://localhost:8002",
    "npc_service": "http://localhost:8003", 
    "summary_service": "http://localhost:8004"
}
```

## Performance Optimization

### Metrics Aggregation

```python
class MetricsAggregator:
    def aggregate_time_series(self, metrics: List[Dict], interval: str) -> List[Dict]:
        """Aggregate metrics over time intervals"""
        
        # Group by time buckets
        buckets = self.create_time_buckets(metrics, interval)
        
        # Calculate aggregates
        aggregated = []
        for bucket in buckets:
            aggregated.append({
                "timestamp": bucket["start_time"],
                "avg_response_time": statistics.mean(bucket["response_times"]),
                "total_requests": sum(bucket["request_counts"]),
                "error_rate": statistics.mean(bucket["error_rates"])
            })
            
        return aggregated
```

### Caching Strategy

- **Recent Metrics**: Cache last 5 minutes in memory
- **Historical Data**: Store in Redis with TTL
- **Dashboard State**: Cache dashboard data for quick loading
- **Alert State**: Cache active alerts for fast lookup

### Sampling and Filtering

- **High-frequency metrics**: Sample every 5 seconds
- **Low-frequency metrics**: Sample every 30 seconds
- **Historical storage**: Aggregate to 5-minute intervals
- **Retention**: Keep detailed data for 7 days, aggregated for 30 days

## Error Handling and Recovery

### Service Monitoring Failures

```python
async def handle_monitoring_failure(self, service_name: str, error: Exception):
    """Handle failures in service monitoring"""
    
    # Log the error
    logger.error(f"Failed to monitor {service_name}: {error}")
    
    # Update service status
    await self.update_service_status(service_name, "monitoring_failed")
    
    # Generate alert
    alert = Alert(
        level="warning",
        message=f"Monitoring failed for {service_name}: {str(error)}",
        service=service_name
    )
    await self.alert_manager.send_alert(alert)
    
    # Schedule retry
    await asyncio.sleep(30)
    await self.retry_service_monitoring(service_name)
```

### Data Quality

- **Metric validation**: Ensure reasonable values
- **Outlier detection**: Identify and flag anomalies
- **Missing data handling**: Interpolate or mark as unavailable
- **Data consistency**: Cross-validate between sources

## Debugging and Troubleshooting

### Debug Endpoints

```python
# Monitoring system health
GET /debug/monitor-health

# Metrics collection status
GET /debug/collection-status

# WebSocket connections
GET /debug/websocket-stats

# Alert evaluation
GET /debug/alert-evaluation
```

### Common Issues

1. **Model Service Connection Issues**
   - Check Windows firewall settings
   - Verify `host.docker.internal` resolution
   - Test direct HTTP connectivity

2. **High Memory Usage**
   - Monitor metrics retention settings
   - Check for memory leaks in collectors
   - Verify garbage collection frequency

3. **WebSocket Disconnections**
   - Check client connection stability
   - Monitor server resource usage
   - Verify proxy configurations

4. **Alert Flooding**
   - Review alert thresholds
   - Implement alert dampening
   - Check for cascading failures

### Performance Monitoring

```python
# Monitor service performance
GET /debug/performance-stats

# Resource usage tracking
GET /debug/resource-usage

# Collection timing analysis
GET /debug/timing-analysis
```

## Integration Testing

### Health Check Validation

```python
# Test all service health checks
GET /debug/test-health-checks

# Simulate service failures
POST /debug/simulate-failure
{
    "service": "model-service",
    "failure_type": "timeout"
}
```

### Metrics Collection Testing

```python
# Test metrics collection
POST /debug/test-metrics-collection

# Validate metric calculations
POST /debug/validate-metrics
```

### Alert System Testing

```python
# Test alert generation
POST /debug/test-alerts
{
    "trigger_type": "high_latency",
    "service": "chat-service"
}

# Test notification delivery
POST /debug/test-notifications
```