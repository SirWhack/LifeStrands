import asyncio
import logging
from contextlib import asynccontextmanager
from typing import Dict, List, Any

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from pydantic import BaseModel

from src.health_checker import HealthChecker
from src.metrics_collector import MetricsCollector
from src.alert_manager import AlertManager
from src.websocket_broadcaster import WebSocketBroadcaster

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Global components
health_checker = HealthChecker()
metrics_collector = MetricsCollector()
alert_manager = AlertManager()
websocket_broadcaster = WebSocketBroadcaster()

class AlertRule(BaseModel):
    name: str
    metric: str
    threshold: float
    operator: str  # "gt", "lt", "eq"
    severity: str  # "low", "medium", "high", "critical"

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown events"""
    try:
        await health_checker.initialize()
        await metrics_collector.initialize()
        await alert_manager.initialize()
        await websocket_broadcaster.initialize()
        
        # Start background monitoring tasks
        asyncio.create_task(health_checker.start_monitoring())
        asyncio.create_task(metrics_collector.start_collection())
        asyncio.create_task(alert_manager.start_monitoring())
        asyncio.create_task(websocket_broadcaster.start_broadcasting())
        
        logger.info("Monitor service started successfully")
        yield
    except Exception as e:
        logger.error(f"Failed to initialize monitor service: {e}")
        raise
    finally:
        await health_checker.stop_monitoring()
        await metrics_collector.stop_collection()
        await alert_manager.stop_monitoring()
        await websocket_broadcaster.stop_broadcasting()
        logger.info("Monitor service shut down")

app = FastAPI(
    title="Life Strands Monitor Service",
    description="System health monitoring and alerting service",
    version="1.0.0",
    lifespan=lifespan
)

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "monitoring_active": health_checker.is_monitoring(),
        "metrics_collecting": metrics_collector.is_collecting,
        "alerts_active": alert_manager.is_monitoring,
        "websocket_connections": len(getattr(websocket_broadcaster, 'active_connections', []))
    }

@app.get("/system/health")
async def get_system_health():
    """Get comprehensive system health status"""
    try:
        health_status = await health_checker.get_system_health()
        return health_status
        
    except Exception as e:
        logger.error(f"Error getting system health: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/metrics")
async def get_current_metrics():
    """Get current system metrics"""
    try:
        metrics = await metrics_collector.get_current_metrics()
        return {
            "timestamp": metrics.get("timestamp"),
            "system_metrics": metrics.get("system", {}),
            "service_metrics": metrics.get("services", {}),
            "database_metrics": metrics.get("database", {}),
            "model_metrics": metrics.get("model", {})
        }
        
    except Exception as e:
        logger.error(f"Error getting current metrics: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/metrics/history")
async def get_metrics_history(
    hours: int = 24,
    service: str = None
):
    """Get historical metrics data"""
    try:
        history = await metrics_collector.get_metrics_history(
            hours=hours,
            service_filter=service
        )
        return {"history": history}
        
    except Exception as e:
        logger.error(f"Error getting metrics history: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/alerts")
async def get_active_alerts():
    """Get currently active alerts"""
    try:
        alerts = await alert_manager.get_active_alerts()
        return {"alerts": alerts}
        
    except Exception as e:
        logger.error(f"Error getting active alerts: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/alerts/history")
async def get_alert_history(hours: int = 168):  # 7 days default
    """Get alert history"""
    try:
        history = await alert_manager.get_alert_history(hours=hours)
        return {"history": history}
        
    except Exception as e:
        logger.error(f"Error getting alert history: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/alerts/rules")
async def create_alert_rule(rule: AlertRule):
    """Create a new alert rule"""
    try:
        rule_id = await alert_manager.create_rule(
            name=rule.name,
            metric=rule.metric,
            threshold=rule.threshold,
            operator=rule.operator,
            severity=rule.severity
        )
        
        return {"rule_id": rule_id, "message": "Alert rule created successfully"}
        
    except Exception as e:
        logger.error(f"Error creating alert rule: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.delete("/alerts/rules/{rule_id}")
async def delete_alert_rule(rule_id: str):
    """Delete an alert rule"""
    try:
        success = await alert_manager.delete_rule(rule_id)
        
        if success:
            return {"message": "Alert rule deleted successfully"}
        else:
            raise HTTPException(status_code=404, detail="Alert rule not found")
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting alert rule {rule_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/alerts/{alert_id}/acknowledge")
async def acknowledge_alert(alert_id: str):
    """Acknowledge an active alert"""
    try:
        success = await alert_manager.acknowledge_alert(alert_id)
        
        if success:
            return {"message": "Alert acknowledged"}
        else:
            raise HTTPException(status_code=404, detail="Alert not found")
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error acknowledging alert {alert_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/services")
async def get_service_status():
    """Get status of all monitored services"""
    try:
        services = await health_checker.get_service_status()
        return {"services": services}
        
    except Exception as e:
        logger.error(f"Error getting service status: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/services/{service_name}/health")
async def get_service_health(service_name: str):
    """Get detailed health information for a specific service"""
    try:
        health = await health_checker.get_service_health(service_name)
        
        if health:
            return health
        else:
            raise HTTPException(status_code=404, detail="Service not found")
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting health for service {service_name}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/services/{service_name}/restart")
async def restart_service(service_name: str):
    """Restart a specific service (if Docker integration is enabled)"""
    try:
        success = await health_checker.restart_service(service_name)
        
        if success:
            return {"message": f"Service {service_name} restarted successfully"}
        else:
            raise HTTPException(
                status_code=400, 
                detail="Service restart not available or failed"
            )
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error restarting service {service_name}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.websocket("/ws/monitor")
async def monitor_websocket(websocket: WebSocket):
    """WebSocket endpoint for real-time monitoring updates"""
    await websocket.accept()
    
    try:
        client_id = websocket_broadcaster.add_connection(websocket)
        logger.info(f"Monitor WebSocket connected: {client_id}")
        
        # Send initial data
        initial_data = {
            "type": "initial_data",
            "system_health": await health_checker.get_system_health(),
            "current_metrics": await metrics_collector.get_current_metrics(),
            "active_alerts": await alert_manager.get_active_alerts()
        }
        
        await websocket.send_json(initial_data)
        
        # Keep connection alive and handle client messages
        while True:
            try:
                message = await websocket.receive_json()
                
                if message.get("type") == "ping":
                    await websocket.send_json({"type": "pong"})
                    
            except Exception as e:
                logger.debug(f"WebSocket message error: {e}")
                break
                
    except WebSocketDisconnect:
        logger.info(f"Monitor WebSocket disconnected: {client_id}")
    except Exception as e:
        logger.error(f"Monitor WebSocket error: {e}")
    finally:
        websocket_broadcaster.remove_connection(client_id)

@app.get("/stats")
async def get_monitoring_stats():
    """Get monitoring service statistics"""
    try:
        stats = {
            "monitoring_uptime": health_checker.get_uptime(),
            "total_metrics_collected": metrics_collector.get_total_metrics(),
            "total_alerts_generated": alert_manager.get_total_alerts(),
            "websocket_connections": len(websocket_broadcaster.active_connections),
            "services_monitored": len(await health_checker.get_monitored_services())
        }
        
        return stats
        
    except Exception as e:
        logger.error(f"Error getting monitoring stats: {e}")
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8005,
        reload=False,
        log_level="info"
    )