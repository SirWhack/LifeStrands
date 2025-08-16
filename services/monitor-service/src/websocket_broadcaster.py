import asyncio
import json
import logging
import websockets
from typing import Dict, Any, Set, List, Optional
from datetime import datetime, timedelta
import uuid
from websockets.exceptions import ConnectionClosed, WebSocketException

logger = logging.getLogger(__name__)

class DashboardConnection:
    def __init__(self, websocket, connection_id: str, client_info: Dict[str, Any] = None):
        self.websocket = websocket
        self.connection_id = connection_id
        self.client_info = client_info or {}
        self.connected_at = datetime.utcnow()
        self.last_ping = datetime.utcnow()
        self.subscriptions: Set[str] = set()
        self.is_active = True
        
    def to_dict(self) -> Dict[str, Any]:
        return {
            "connection_id": self.connection_id,
            "client_info": self.client_info,
            "connected_at": self.connected_at.isoformat(),
            "last_ping": self.last_ping.isoformat(),
            "subscriptions": list(self.subscriptions),
            "is_active": self.is_active,
            "duration_seconds": (datetime.utcnow() - self.connected_at).total_seconds()
        }

class WebSocketBroadcaster:
    """Broadcast real-time metrics to admin dashboard"""
    
    def __init__(self, host: str = "0.0.0.0", port: int = 8006):
        self.host = host
        self.port = port
        self.connections: Dict[str, DashboardConnection] = {}
        self.server: Optional[websockets.WebSocketServer] = None
        self.is_running = False
        
        # Message queues for different data types
        self.metrics_queue: asyncio.Queue = asyncio.Queue(maxsize=100)
        self.alert_queue: asyncio.Queue = asyncio.Queue(maxsize=50)
        
        # Broadcast intervals
        self.broadcast_intervals = {
            "metrics": 5,      # Broadcast metrics every 5 seconds
            "alerts": 1,       # Broadcast alerts immediately
            "heartbeat": 30    # Heartbeat every 30 seconds
        }
        
        # Historical data cache
        self.metrics_cache: List[Dict[str, Any]] = []
        self.max_cache_size = 1000
        self.cache_retention_hours = 24
        
        # Subscription types
        self.subscription_types = {
            "system_metrics", "service_health", "alerts", "model_status", 
            "database_metrics", "gpu_metrics", "conversation_stats"
        }
        
    async def initialize(self):
        """Initialize the WebSocket broadcaster (alias for start_server)"""
        await self.start_server()
    
    async def start_broadcasting(self):
        """Start broadcasting (alias for start_server)"""
        await self.start_server()
    
    async def stop_broadcasting(self):
        """Stop broadcasting (alias for stop_server)"""
        await self.stop_server()
    
    async def start_server(self):
        """Start WebSocket server"""
        try:
            if self.is_running:
                logger.warning("WebSocket server is already running")
                return
                
            self.server = await websockets.serve(
                self.handle_dashboard_connection,
                self.host,
                self.port
            )
            
            self.is_running = True
            
            # Start background tasks
            asyncio.create_task(self._metrics_broadcaster())
            asyncio.create_task(self._alert_broadcaster()) 
            asyncio.create_task(self._heartbeat_broadcaster())
            asyncio.create_task(self._cleanup_task())
            
            logger.info(f"WebSocket server started on {self.host}:{self.port}")
            
        except Exception as e:
            logger.error(f"Failed to start WebSocket server: {e}")
            raise
            
    async def stop_server(self):
        """Stop WebSocket server"""
        try:
            self.is_running = False
            
            # Close all connections
            for connection in self.connections.values():
                try:
                    await connection.websocket.close()
                except:
                    pass
                    
            self.connections.clear()
            
            # Stop server
            if self.server:
                self.server.close()
                await self.server.wait_closed()
                
            logger.info("WebSocket server stopped")
            
        except Exception as e:
            logger.error(f"Error stopping WebSocket server: {e}")
            
    async def handle_dashboard_connection(self, websocket, path):
        """Manage dashboard WebSocket connections"""
        connection_id = str(uuid.uuid4())
        connection = None
        
        try:
            # Create connection
            client_info = {
                "remote_address": websocket.remote_address,
                "path": path,
                "user_agent": websocket.request_headers.get("User-Agent", "Unknown")
            }
            
            connection = DashboardConnection(websocket, connection_id, client_info)
            self.connections[connection_id] = connection
            
            logger.info(f"Dashboard connected: {connection_id} from {websocket.remote_address}")
            
            # Send connection confirmation
            await self._send_to_connection(connection, {
                "type": "connection_established",
                "connection_id": connection_id,
                "server_time": datetime.utcnow().isoformat(),
                "available_subscriptions": list(self.subscription_types)
            })
            
            # Handle incoming messages
            async for message in websocket:
                await self._handle_client_message(connection, message)
                
        except ConnectionClosed:
            logger.info(f"Dashboard disconnected: {connection_id}")
            
        except Exception as e:
            logger.error(f"Error handling dashboard connection {connection_id}: {e}")
            
        finally:
            # Cleanup
            if connection_id in self.connections:
                del self.connections[connection_id]
                
    async def broadcast_metrics(self, metrics: Dict[str, Any]):
        """Send metrics to all connected dashboards"""
        try:
            # Add to cache
            self._add_to_metrics_cache(metrics)
            
            # Queue for broadcast
            try:
                self.metrics_queue.put_nowait({
                    "type": "metrics_update",
                    "data": metrics,
                    "timestamp": datetime.utcnow().isoformat()
                })
            except asyncio.QueueFull:
                # Remove oldest item and add new one
                try:
                    self.metrics_queue.get_nowait()
                    self.metrics_queue.put_nowait({
                        "type": "metrics_update", 
                        "data": metrics,
                        "timestamp": datetime.utcnow().isoformat()
                    })
                except asyncio.QueueEmpty:
                    pass
                    
        except Exception as e:
            logger.error(f"Error broadcasting metrics: {e}")
            
    async def broadcast_alert(self, alert: Dict[str, Any]):
        """Send urgent alerts to dashboards"""
        try:
            alert_message = {
                "type": "alert",
                "data": alert,
                "timestamp": datetime.utcnow().isoformat(),
                "priority": "urgent" if alert.get("severity") in ["high", "critical"] else "normal"
            }
            
            # Queue for immediate broadcast
            try:
                self.alert_queue.put_nowait(alert_message)
            except asyncio.QueueFull:
                # For alerts, we prioritize new ones
                try:
                    self.alert_queue.get_nowait()
                    self.alert_queue.put_nowait(alert_message)
                except asyncio.QueueEmpty:
                    pass
                    
        except Exception as e:
            logger.error(f"Error broadcasting alert: {e}")
            
    async def send_historical_data(self, websocket, timeframe: str):
        """Send historical metrics on request"""
        try:
            # Parse timeframe
            hours = self._parse_timeframe(timeframe)
            cutoff_time = datetime.utcnow() - timedelta(hours=hours)
            
            # Filter cached metrics
            historical_data = [
                metric for metric in self.metrics_cache
                if datetime.fromisoformat(metric.get("timestamp", "")) > cutoff_time
            ]
            
            # Send historical data
            await websocket.send(json.dumps({
                "type": "historical_data",
                "timeframe": timeframe,
                "data_points": len(historical_data),
                "data": historical_data,
                "timestamp": datetime.utcnow().isoformat()
            }))
            
            logger.debug(f"Sent {len(historical_data)} historical data points for timeframe {timeframe}")
            
        except Exception as e:
            logger.error(f"Error sending historical data: {e}")
            
    async def _handle_client_message(self, connection: DashboardConnection, message: str):
        """Handle incoming message from dashboard client"""
        try:
            data = json.loads(message)
            message_type = data.get("type")
            
            # Update ping time
            connection.last_ping = datetime.utcnow()
            
            if message_type == "subscribe":
                subscription = data.get("subscription")
                if subscription in self.subscription_types:
                    connection.subscriptions.add(subscription)
                    
                    await self._send_to_connection(connection, {
                        "type": "subscription_confirmed",
                        "subscription": subscription,
                        "active_subscriptions": list(connection.subscriptions)
                    })
                    
                    logger.debug(f"Connection {connection.connection_id} subscribed to {subscription}")
                    
            elif message_type == "unsubscribe":
                subscription = data.get("subscription")
                connection.subscriptions.discard(subscription)
                
                await self._send_to_connection(connection, {
                    "type": "unsubscription_confirmed",
                    "subscription": subscription,
                    "active_subscriptions": list(connection.subscriptions)
                })
                
            elif message_type == "get_historical":
                timeframe = data.get("timeframe", "1h")
                await self.send_historical_data(connection.websocket, timeframe)
                
            elif message_type == "ping":
                await self._send_to_connection(connection, {
                    "type": "pong",
                    "timestamp": datetime.utcnow().isoformat()
                })
                
            elif message_type == "get_connection_info":
                await self._send_to_connection(connection, {
                    "type": "connection_info",
                    "connection": connection.to_dict()
                })
                
            else:
                logger.warning(f"Unknown message type from {connection.connection_id}: {message_type}")
                
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON from {connection.connection_id}: {e}")
            
        except Exception as e:
            logger.error(f"Error handling client message from {connection.connection_id}: {e}")
            
    async def _send_to_connection(self, connection: DashboardConnection, message: Dict[str, Any]):
        """Send message to specific connection"""
        try:
            if not connection.is_active:
                return
                
            await connection.websocket.send(json.dumps(message))
            
        except ConnectionClosed:
            connection.is_active = False
            logger.debug(f"Connection {connection.connection_id} closed")
            
        except Exception as e:
            logger.error(f"Error sending to connection {connection.connection_id}: {e}")
            connection.is_active = False
            
    async def _broadcast_to_subscribers(self, message: Dict[str, Any], subscription_type: str = None):
        """Broadcast message to all subscribers"""
        try:
            tasks = []
            
            for connection in self.connections.values():
                if not connection.is_active:
                    continue
                    
                # Check subscription filter
                if subscription_type and subscription_type not in connection.subscriptions:
                    continue
                    
                task = self._send_to_connection(connection, message)
                tasks.append(task)
                
            if tasks:
                await asyncio.gather(*tasks, return_exceptions=True)
                
        except Exception as e:
            logger.error(f"Error broadcasting to subscribers: {e}")
            
    async def _metrics_broadcaster(self):
        """Background task to broadcast metrics"""
        while self.is_running:
            try:
                # Get metrics from queue
                try:
                    metrics_message = await asyncio.wait_for(
                        self.metrics_queue.get(),
                        timeout=self.broadcast_intervals["metrics"]
                    )
                    
                    # Broadcast to subscribers
                    await self._broadcast_to_subscribers(metrics_message, "system_metrics")
                    
                except asyncio.TimeoutError:
                    continue
                    
            except Exception as e:
                logger.error(f"Error in metrics broadcaster: {e}")
                await asyncio.sleep(1)
                
    async def _alert_broadcaster(self):
        """Background task to broadcast alerts"""
        while self.is_running:
            try:
                # Get alert from queue (blocking)
                alert_message = await self.alert_queue.get()
                
                # Broadcast immediately to all alert subscribers
                await self._broadcast_to_subscribers(alert_message, "alerts")
                
            except Exception as e:
                logger.error(f"Error in alert broadcaster: {e}")
                await asyncio.sleep(1)
                
    async def _heartbeat_broadcaster(self):
        """Background task to send heartbeat"""
        while self.is_running:
            try:
                await asyncio.sleep(self.broadcast_intervals["heartbeat"])
                
                heartbeat_message = {
                    "type": "heartbeat",
                    "timestamp": datetime.utcnow().isoformat(),
                    "server_status": "running",
                    "connected_clients": len([c for c in self.connections.values() if c.is_active])
                }
                
                await self._broadcast_to_subscribers(heartbeat_message)
                
            except Exception as e:
                logger.error(f"Error in heartbeat broadcaster: {e}")
                await asyncio.sleep(5)
                
    async def _cleanup_task(self):
        """Background task to cleanup inactive connections and old data"""
        while self.is_running:
            try:
                await asyncio.sleep(60)  # Run every minute
                
                # Remove inactive connections
                inactive_connections = [
                    conn_id for conn_id, conn in self.connections.items()
                    if not conn.is_active or self._is_connection_stale(conn)
                ]
                
                for conn_id in inactive_connections:
                    del self.connections[conn_id]
                    
                if inactive_connections:
                    logger.info(f"Cleaned up {len(inactive_connections)} inactive connections")
                    
                # Clean old cache data
                self._cleanup_metrics_cache()
                
            except Exception as e:
                logger.error(f"Error in cleanup task: {e}")
                await asyncio.sleep(30)
                
    def _is_connection_stale(self, connection: DashboardConnection) -> bool:
        """Check if connection is stale (no ping in 5 minutes)"""
        return datetime.utcnow() - connection.last_ping > timedelta(minutes=5)
        
    def _add_to_metrics_cache(self, metrics: Dict[str, Any]):
        """Add metrics to historical cache"""
        try:
            cache_entry = {
                "timestamp": datetime.utcnow().isoformat(),
                "data": metrics
            }
            
            self.metrics_cache.append(cache_entry)
            
            # Limit cache size
            if len(self.metrics_cache) > self.max_cache_size:
                self.metrics_cache = self.metrics_cache[-self.max_cache_size:]
                
        except Exception as e:
            logger.error(f"Error adding to metrics cache: {e}")
            
    def _cleanup_metrics_cache(self):
        """Remove old entries from metrics cache"""
        try:
            cutoff_time = datetime.utcnow() - timedelta(hours=self.cache_retention_hours)
            
            self.metrics_cache = [
                entry for entry in self.metrics_cache
                if datetime.fromisoformat(entry["timestamp"]) > cutoff_time
            ]
            
        except Exception as e:
            logger.error(f"Error cleaning up metrics cache: {e}")
            
    def _parse_timeframe(self, timeframe: str) -> int:
        """Parse timeframe string to hours"""
        try:
            timeframe = timeframe.lower()
            
            if timeframe.endswith('h'):
                return int(timeframe[:-1])
            elif timeframe.endswith('d'):
                return int(timeframe[:-1]) * 24
            elif timeframe.endswith('m'):
                return max(1, int(timeframe[:-1]) // 60)  # Minutes to hours, minimum 1
            else:
                # Default to 1 hour
                return 1
                
        except Exception:
            return 1  # Default fallback
            
    def get_connection_stats(self) -> Dict[str, Any]:
        """Get statistics about WebSocket connections"""
        try:
            active_connections = [conn for conn in self.connections.values() if conn.is_active]
            
            subscription_stats = {}
            for conn in active_connections:
                for sub in conn.subscriptions:
                    subscription_stats[sub] = subscription_stats.get(sub, 0) + 1
                    
            return {
                "total_connections": len(self.connections),
                "active_connections": len(active_connections),
                "server_running": self.is_running,
                "metrics_queue_size": self.metrics_queue.qsize(),
                "alert_queue_size": self.alert_queue.qsize(),
                "cache_size": len(self.metrics_cache),
                "subscription_counts": subscription_stats,
                "uptime_seconds": (datetime.utcnow() - datetime.utcnow()).total_seconds() if active_connections else 0
            }
            
        except Exception as e:
            logger.error(f"Error getting connection stats: {e}")
            return {"error": str(e)}
            
    async def send_custom_message(self, message: Dict[str, Any], subscription_filter: str = None):
        """Send custom message to dashboards"""
        try:
            await self._broadcast_to_subscribers(message, subscription_filter)
            
        except Exception as e:
            logger.error(f"Error sending custom message: {e}")
            
    def get_active_connections(self) -> List[Dict[str, Any]]:
        """Get list of active connections"""
        try:
            return [
                conn.to_dict() for conn in self.connections.values()
                if conn.is_active
            ]
        except Exception as e:
            logger.error(f"Error getting active connections: {e}")
            return []
            
    async def force_disconnect(self, connection_id: str) -> bool:
        """Force disconnect a specific connection"""
        try:
            if connection_id in self.connections:
                connection = self.connections[connection_id]
                await connection.websocket.close()
                connection.is_active = False
                del self.connections[connection_id]
                
                logger.info(f"Force disconnected: {connection_id}")
                return True
                
            return False
            
        except Exception as e:
            logger.error(f"Error force disconnecting {connection_id}: {e}")
            return False