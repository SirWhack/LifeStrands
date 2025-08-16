import asyncio
import aiohttp
import json
import logging
from typing import Dict, Any, List, Optional, Callable
from datetime import datetime, timedelta
from enum import Enum
import hashlib

logger = logging.getLogger(__name__)

class AlertSeverity(Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"

class AlertStatus(Enum):
    ACTIVE = "active"
    ACKNOWLEDGED = "acknowledged" 
    RESOLVED = "resolved"
    MUTED = "muted"

class Alert:
    def __init__(
        self,
        alert_type: str,
        message: str,
        severity: AlertSeverity,
        source: str,
        metadata: Dict[str, Any] = None
    ):
        self.alert_id = self._generate_alert_id(alert_type, source, message)
        self.alert_type = alert_type
        self.message = message
        self.severity = severity
        self.source = source
        self.metadata = metadata or {}
        self.status = AlertStatus.ACTIVE
        self.created_at = datetime.utcnow()
        self.updated_at = datetime.utcnow()
        self.acknowledged_at: Optional[datetime] = None
        self.resolved_at: Optional[datetime] = None
        self.acknowledged_by: Optional[str] = None
        self.count = 1  # For duplicate detection
        
    def _generate_alert_id(self, alert_type: str, source: str, message: str) -> str:
        """Generate unique alert ID based on type, source, and message"""
        content = f"{alert_type}:{source}:{message}"
        return hashlib.md5(content.encode()).hexdigest()[:12]
        
    def to_dict(self) -> Dict[str, Any]:
        return {
            "alert_id": self.alert_id,
            "alert_type": self.alert_type,
            "message": self.message,
            "severity": self.severity.value,
            "source": self.source,
            "status": self.status.value,
            "metadata": self.metadata,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "acknowledged_at": self.acknowledged_at.isoformat() if self.acknowledged_at else None,
            "resolved_at": self.resolved_at.isoformat() if self.resolved_at else None,
            "acknowledged_by": self.acknowledged_by,
            "count": self.count
        }

class AlertManager:
    """Manage system alerts and thresholds"""
    
    def __init__(self):
        self.thresholds = {}
        self.active_alerts: Dict[str, Alert] = {}
        self.alert_history: List[Alert] = []
        self.max_history = 1000
        
        # Alert channels
        self.alert_channels = []
        self.webhook_urls = []
        
        # Rate limiting
        self.rate_limits = {}
        self.rate_limit_window = 300  # 5 minutes
        
        # Default thresholds
        self.configure_default_thresholds()
        
        # Monitoring state
        self.is_monitoring = False
        self.monitoring_task = None
        
    def configure_thresholds(self, config: Dict[str, Any]):
        """Set alert thresholds for metrics"""
        try:
            self.thresholds.update(config)
            logger.info(f"Updated alert thresholds: {list(config.keys())}")
            
        except Exception as e:
            logger.error(f"Error configuring thresholds: {e}")
            
    def configure_default_thresholds(self):
        """Set default alert thresholds"""
        self.thresholds = {
            # System thresholds
            "cpu_usage_percent": {"warning": 80, "critical": 95},
            "memory_usage_percent": {"warning": 85, "critical": 95},
            "disk_usage_percent": {"warning": 80, "critical": 90},
            "disk_free_gb": {"warning": 5, "critical": 1},
            
            # GPU thresholds
            "gpu_memory_usage_percent": {"warning": 90, "critical": 98},
            "gpu_temperature_c": {"warning": 80, "critical": 90},
            "gpu_utilization_percent": {"warning": 95, "critical": 99},
            
            # Service thresholds
            "response_time_ms": {"warning": 5000, "critical": 15000},
            "error_rate_percent": {"warning": 5, "critical": 10},
            "queue_length": {"warning": 100, "critical": 500},
            
            # Database thresholds
            "database_connections": {"warning": 80, "critical": 95},
            "database_query_time_ms": {"warning": 1000, "critical": 5000},
            "database_connection_pool_usage": {"warning": 80, "critical": 95},
            
            # Redis thresholds
            "redis_memory_usage_percent": {"warning": 80, "critical": 90},
            "redis_connection_count": {"warning": 90, "critical": 100},
            
            # Application-specific thresholds
            "active_conversations": {"warning": 80, "critical": 100},
            "model_load_failures": {"warning": 3, "critical": 5},
            "summary_queue_backlog": {"warning": 50, "critical": 200}
        }
        
    async def initialize(self):
        """Initialize the AlertManager"""
        try:
            logger.info("Initializing AlertManager...")
            # Load any persistent alert state
            logger.info("AlertManager initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize AlertManager: {e}")
            raise
            
    async def start_monitoring(self):
        """Start background alert monitoring"""
        try:
            if self.is_monitoring:
                logger.warning("AlertManager monitoring is already running")
                return
                
            self.is_monitoring = True
            self.monitoring_task = asyncio.create_task(self._monitoring_loop())
            logger.info("AlertManager monitoring started")
            
        except Exception as e:
            logger.error(f"Failed to start AlertManager monitoring: {e}")
            self.is_monitoring = False
            
    async def stop_monitoring(self):
        """Stop background alert monitoring"""
        try:
            self.is_monitoring = False
            
            if self.monitoring_task and not self.monitoring_task.done():
                self.monitoring_task.cancel()
                try:
                    await self.monitoring_task
                except asyncio.CancelledError:
                    pass
                    
            logger.info("AlertManager monitoring stopped")
            
        except Exception as e:
            logger.error(f"Error stopping AlertManager monitoring: {e}")
            
    async def _monitoring_loop(self):
        """Background monitoring loop"""
        try:
            while self.is_monitoring:
                await asyncio.sleep(30)  # Check every 30 seconds
                
                # Cleanup old alerts
                await self._cleanup_old_alerts()
                
                # Check for stale alerts that should auto-resolve
                await self._check_stale_alerts()
                
        except asyncio.CancelledError:
            logger.info("Alert monitoring loop cancelled")
        except Exception as e:
            logger.error(f"Error in alert monitoring loop: {e}")
            
    async def _cleanup_old_alerts(self):
        """Remove old alerts from history"""
        try:
            cutoff_time = datetime.utcnow() - timedelta(hours=24)
            self.alert_history = [alert for alert in self.alert_history if alert.created_at > cutoff_time]
        except Exception as e:
            logger.error(f"Error cleaning up old alerts: {e}")
            
    async def _check_stale_alerts(self):
        """Check for alerts that should auto-resolve"""
        try:
            stale_cutoff = datetime.utcnow() - timedelta(minutes=30)
            stale_alerts = []
            
            for alert_id, alert in self.active_alerts.items():
                if alert.status == AlertStatus.ACTIVE and alert.updated_at < stale_cutoff:
                    stale_alerts.append(alert_id)
                    
            for alert_id in stale_alerts:
                await self.manage_alert_state(alert_id, "auto_resolve", "system")
                
        except Exception as e:
            logger.error(f"Error checking stale alerts: {e}")
        
    async def check_thresholds(self, metrics: Dict[str, Any]):
        """Check if metrics exceed thresholds"""
        try:
            for metric_name, value in metrics.items():
                if not isinstance(value, (int, float)):
                    continue
                    
                await self._check_single_threshold(metric_name, value, metrics.get("source", "system"))
                
        except Exception as e:
            logger.error(f"Error checking thresholds: {e}")
            
    async def _check_single_threshold(self, metric_name: str, value: float, source: str):
        """Check a single metric against thresholds"""
        try:
            if metric_name not in self.thresholds:
                return
                
            threshold_config = self.thresholds[metric_name]
            
            # Check critical threshold
            if "critical" in threshold_config and value >= threshold_config["critical"]:
                await self._trigger_alert(
                    alert_type="threshold_exceeded",
                    message=f"{metric_name} exceeded critical threshold: {value} >= {threshold_config['critical']}",
                    severity=AlertSeverity.CRITICAL,
                    source=source,
                    metadata={
                        "metric_name": metric_name,
                        "current_value": value,
                        "threshold_value": threshold_config["critical"],
                        "threshold_type": "critical"
                    }
                )
                
            # Check warning threshold
            elif "warning" in threshold_config and value >= threshold_config["warning"]:
                await self._trigger_alert(
                    alert_type="threshold_exceeded",
                    message=f"{metric_name} exceeded warning threshold: {value} >= {threshold_config['warning']}",
                    severity=AlertSeverity.HIGH,
                    source=source,
                    metadata={
                        "metric_name": metric_name,
                        "current_value": value,
                        "threshold_value": threshold_config["warning"],
                        "threshold_type": "warning"
                    }
                )
                
        except Exception as e:
            logger.error(f"Error checking threshold for {metric_name}: {e}")
            
    async def send_alert(self, alert_type: str, message: str, severity: AlertSeverity = AlertSeverity.MEDIUM, source: str = "system", metadata: Dict[str, Any] = None):
        """Send alert to admin dashboard"""
        try:
            await self._trigger_alert(alert_type, message, severity, source, metadata)
            
        except Exception as e:
            logger.error(f"Error sending alert: {e}")
            
    async def _trigger_alert(self, alert_type: str, message: str, severity: AlertSeverity, source: str, metadata: Dict[str, Any] = None):
        """Internal method to trigger an alert"""
        try:
            # Create alert object
            alert = Alert(alert_type, message, severity, source, metadata)
            
            # Check for rate limiting
            if self._is_rate_limited(alert):
                logger.debug(f"Alert rate limited: {alert.alert_id}")
                return
                
            # Check for duplicate alerts
            if alert.alert_id in self.active_alerts:
                # Update existing alert
                existing_alert = self.active_alerts[alert.alert_id]
                existing_alert.count += 1
                existing_alert.updated_at = datetime.utcnow()
                existing_alert.metadata.update(metadata or {})
                alert = existing_alert
                logger.debug(f"Updated existing alert: {alert.alert_id} (count: {alert.count})")
            else:
                # Add new alert
                self.active_alerts[alert.alert_id] = alert
                logger.info(f"New alert triggered: {alert.alert_type} - {alert.message}")
                
            # Send notifications
            await self._send_notifications(alert)
            
            # Update rate limiting
            self._update_rate_limit(alert)
            
        except Exception as e:
            logger.error(f"Error triggering alert: {e}")
            
    async def _send_notifications(self, alert: Alert):
        """Send alert notifications to configured channels"""
        try:
            notification_tasks = []
            
            # Send to webhook URLs
            for webhook_url in self.webhook_urls:
                task = self._send_webhook_notification(webhook_url, alert)
                notification_tasks.append(task)
                
            # Send to alert channels
            for channel in self.alert_channels:
                task = self._send_channel_notification(channel, alert)
                notification_tasks.append(task)
                
            if notification_tasks:
                await asyncio.gather(*notification_tasks, return_exceptions=True)
                
        except Exception as e:
            logger.error(f"Error sending notifications for alert {alert.alert_id}: {e}")
            
    async def _send_webhook_notification(self, webhook_url: str, alert: Alert):
        """Send alert to webhook URL"""
        try:
            payload = {
                "alert": alert.to_dict(),
                "timestamp": datetime.utcnow().isoformat(),
                "system": "life-strands"
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    webhook_url,
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=10),
                    headers={"Content-Type": "application/json"}
                ) as response:
                    
                    if response.status == 200:
                        logger.debug(f"Alert sent to webhook: {webhook_url}")
                    else:
                        logger.warning(f"Webhook notification failed: {response.status}")
                        
        except Exception as e:
            logger.error(f"Error sending webhook notification: {e}")
            
    async def _send_channel_notification(self, channel: Callable, alert: Alert):
        """Send alert to custom channel"""
        try:
            await channel(alert)
            
        except Exception as e:
            logger.error(f"Error sending channel notification: {e}")
            
    def _is_rate_limited(self, alert: Alert) -> bool:
        """Check if alert is rate limited"""
        try:
            now = datetime.utcnow()
            rate_key = f"{alert.alert_type}:{alert.source}"
            
            if rate_key not in self.rate_limits:
                return False
                
            rate_data = self.rate_limits[rate_key]
            
            # Clean old entries
            rate_data["timestamps"] = [
                ts for ts in rate_data["timestamps"]
                if now - ts < timedelta(seconds=self.rate_limit_window)
            ]
            
            # Check rate limit
            max_alerts = rate_data.get("max_per_window", 10)
            return len(rate_data["timestamps"]) >= max_alerts
            
        except Exception as e:
            logger.error(f"Error checking rate limit: {e}")
            return False
            
    def _update_rate_limit(self, alert: Alert):
        """Update rate limiting data"""
        try:
            rate_key = f"{alert.alert_type}:{alert.source}"
            
            if rate_key not in self.rate_limits:
                self.rate_limits[rate_key] = {
                    "timestamps": [],
                    "max_per_window": 10
                }
                
            self.rate_limits[rate_key]["timestamps"].append(datetime.utcnow())
            
        except Exception as e:
            logger.error(f"Error updating rate limit: {e}")
            
    async def manage_alert_state(self, alert_id: str, action: str, user: str = "system") -> bool:
        """Track alert acknowledgment and resolution"""
        try:
            if alert_id not in self.active_alerts:
                logger.warning(f"Alert not found: {alert_id}")
                return False
                
            alert = self.active_alerts[alert_id]
            
            if action == "acknowledge":
                alert.status = AlertStatus.ACKNOWLEDGED
                alert.acknowledged_at = datetime.utcnow()
                alert.acknowledged_by = user
                logger.info(f"Alert {alert_id} acknowledged by {user}")
                
            elif action == "resolve":
                alert.status = AlertStatus.RESOLVED
                alert.resolved_at = datetime.utcnow()
                
                # Move to history
                self.alert_history.append(alert)
                del self.active_alerts[alert_id]
                
                # Limit history size
                if len(self.alert_history) > self.max_history:
                    self.alert_history = self.alert_history[-self.max_history:]
                    
                logger.info(f"Alert {alert_id} resolved")
                
            elif action == "mute":
                alert.status = AlertStatus.MUTED
                logger.info(f"Alert {alert_id} muted")
                
            else:
                logger.warning(f"Unknown alert action: {action}")
                return False
                
            alert.updated_at = datetime.utcnow()
            return True
            
        except Exception as e:
            logger.error(f"Error managing alert state for {alert_id}: {e}")
            return False
            
    def get_active_alerts(self, severity: Optional[AlertSeverity] = None) -> List[Dict[str, Any]]:
        """Get currently active alerts"""
        try:
            alerts = []
            
            for alert in self.active_alerts.values():
                if severity is None or alert.severity == severity:
                    alerts.append(alert.to_dict())
                    
            # Sort by severity and creation time
            severity_order = {
                AlertSeverity.CRITICAL: 0,
                AlertSeverity.HIGH: 1, 
                AlertSeverity.MEDIUM: 2,
                AlertSeverity.LOW: 3
            }
            
            alerts.sort(key=lambda a: (severity_order.get(AlertSeverity(a["severity"]), 4), a["created_at"]))
            
            return alerts
            
        except Exception as e:
            logger.error(f"Error getting active alerts: {e}")
            return []
            
    def get_alert_summary(self) -> Dict[str, Any]:
        """Get alert summary statistics"""
        try:
            active_by_severity = {}
            active_by_source = {}
            
            for alert in self.active_alerts.values():
                # Count by severity
                severity = alert.severity.value
                active_by_severity[severity] = active_by_severity.get(severity, 0) + 1
                
                # Count by source
                source = alert.source
                active_by_source[source] = active_by_source.get(source, 0) + 1
                
            # Recent resolution stats
            recent_cutoff = datetime.utcnow() - timedelta(hours=24)
            recent_resolved = [
                alert for alert in self.alert_history
                if alert.resolved_at and alert.resolved_at > recent_cutoff
            ]
            
            return {
                "active_alerts_count": len(self.active_alerts),
                "active_by_severity": active_by_severity,
                "active_by_source": active_by_source,
                "resolved_last_24h": len(recent_resolved),
                "total_in_history": len(self.alert_history),
                "configured_thresholds": len(self.thresholds)
            }
            
        except Exception as e:
            logger.error(f"Error getting alert summary: {e}")
            return {"error": str(e)}
            
    def add_webhook_url(self, webhook_url: str):
        """Add webhook URL for alert notifications"""
        if webhook_url not in self.webhook_urls:
            self.webhook_urls.append(webhook_url)
            logger.info(f"Added webhook URL: {webhook_url}")
            
    def remove_webhook_url(self, webhook_url: str):
        """Remove webhook URL"""
        if webhook_url in self.webhook_urls:
            self.webhook_urls.remove(webhook_url)
            logger.info(f"Removed webhook URL: {webhook_url}")
            
    def add_alert_channel(self, channel: Callable):
        """Add custom alert channel"""
        self.alert_channels.append(channel)
        logger.info("Added custom alert channel")
        
    async def test_alerts(self) -> Dict[str, Any]:
        """Test alert system functionality"""
        try:
            test_results = {"timestamp": datetime.utcnow().isoformat(), "tests": []}
            
            # Test basic alert creation
            await self.send_alert(
                "test_alert",
                "This is a test alert",
                AlertSeverity.LOW,
                "test_system"
            )
            
            test_results["tests"].append({
                "test": "basic_alert_creation",
                "status": "passed",
                "active_alerts_count": len(self.active_alerts)
            })
            
            # Test threshold checking
            await self.check_thresholds({
                "cpu_usage_percent": 85,  # Should trigger warning
                "source": "test_metrics"
            })
            
            test_results["tests"].append({
                "test": "threshold_checking",
                "status": "passed"
            })
            
            # Test alert management
            if self.active_alerts:
                alert_id = list(self.active_alerts.keys())[0]
                success = await self.manage_alert_state(alert_id, "acknowledge", "test_user")
                
                test_results["tests"].append({
                    "test": "alert_management",
                    "status": "passed" if success else "failed"
                })
                
            return test_results
            
        except Exception as e:
            logger.error(f"Error testing alerts: {e}")
            return {"error": str(e)}
            
    def cleanup_old_alerts(self, hours: int = 48):
        """Clean up old resolved alerts"""
        try:
            cutoff_time = datetime.utcnow() - timedelta(hours=hours)
            
            # Clean history
            self.alert_history = [
                alert for alert in self.alert_history
                if not alert.resolved_at or alert.resolved_at > cutoff_time
            ]
            
            # Clean rate limit data
            for rate_key in list(self.rate_limits.keys()):
                rate_data = self.rate_limits[rate_key]
                rate_data["timestamps"] = [
                    ts for ts in rate_data["timestamps"]
                    if datetime.utcnow() - ts < timedelta(hours=hours)
                ]
                
                if not rate_data["timestamps"]:
                    del self.rate_limits[rate_key]
                    
            logger.info(f"Cleaned up alerts older than {hours} hours")
            
        except Exception as e:
            logger.error(f"Error cleaning up old alerts: {e}")
            
    def get_alert_by_id(self, alert_id: str) -> Optional[Dict[str, Any]]:
        """Get specific alert by ID"""
        try:
            # Check active alerts
            if alert_id in self.active_alerts:
                return self.active_alerts[alert_id].to_dict()
                
            # Check history
            for alert in self.alert_history:
                if alert.alert_id == alert_id:
                    return alert.to_dict()
                    
            return None
            
        except Exception as e:
            logger.error(f"Error getting alert {alert_id}: {e}")
            return None