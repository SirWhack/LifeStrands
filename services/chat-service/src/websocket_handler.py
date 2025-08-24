import asyncio
import json
import logging
import time
from typing import Dict, Any, Set, Optional
import websockets
from websockets.exceptions import ConnectionClosed, WebSocketException
import jwt
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

class ConnectionManager:
    """Manage active WebSocket connections"""
    
    def __init__(self):
        self.connections: Dict[str, Dict[str, Any]] = {}
        self.user_connections: Dict[str, Set[str]] = {}  # user_id -> connection_ids
        self.npc_subscribers: Dict[str, Set[str]] = {}   # npc_id -> connection_ids
        
    def add_connection(self, connection_id: str, websocket, user_id: str = None):
        """Add a new connection"""
        self.connections[connection_id] = {
            "websocket": websocket,
            "user_id": user_id,
            "connected_at": datetime.utcnow(),
            "last_heartbeat": datetime.utcnow(),
            "subscriptions": set()
        }
        
        if user_id:
            if user_id not in self.user_connections:
                self.user_connections[user_id] = set()
            self.user_connections[user_id].add(connection_id)
            
    def remove_connection(self, connection_id: str):
        """Remove a connection and cleanup subscriptions"""
        if connection_id in self.connections:
            conn_info = self.connections[connection_id]
            user_id = conn_info["user_id"]
            subscriptions = conn_info["subscriptions"]
            
            # Remove from user connections
            if user_id and user_id in self.user_connections:
                self.user_connections[user_id].discard(connection_id)
                if not self.user_connections[user_id]:
                    del self.user_connections[user_id]
                    
            # Remove from NPC subscriptions
            for npc_id in subscriptions:
                if npc_id in self.npc_subscribers:
                    self.npc_subscribers[npc_id].discard(connection_id)
                    if not self.npc_subscribers[npc_id]:
                        del self.npc_subscribers[npc_id]
                        
            del self.connections[connection_id]
            
    def subscribe_to_npc(self, connection_id: str, npc_id: str):
        """Subscribe connection to NPC status updates"""
        if connection_id in self.connections:
            self.connections[connection_id]["subscriptions"].add(npc_id)
            
            if npc_id not in self.npc_subscribers:
                self.npc_subscribers[npc_id] = set()
            self.npc_subscribers[npc_id].add(connection_id)
            
    def get_npc_subscribers(self, npc_id: str) -> Set[str]:
        """Get all connections subscribed to an NPC"""
        return self.npc_subscribers.get(npc_id, set()).copy()
        
    def update_heartbeat(self, connection_id: str):
        """Update last heartbeat time for connection"""
        if connection_id in self.connections:
            self.connections[connection_id]["last_heartbeat"] = datetime.utcnow()
            
    def get_connection_info(self, connection_id: str) -> Optional[Dict[str, Any]]:
        """Get connection information"""
        return self.connections.get(connection_id)
        
    def get_stats(self) -> Dict[str, Any]:
        """Get connection statistics"""
        return {
            "total_connections": len(self.connections),
            "unique_users": len(self.user_connections),
            "npc_subscriptions": len(self.npc_subscribers),
            "connections_per_user": {
                user_id: len(conn_ids) 
                for user_id, conn_ids in self.user_connections.items()
            }
        }

class WebSocketHandler:
    """WebSocket connection management for real-time chat"""
    
    def __init__(self):
        self.connection_manager = ConnectionManager()
        self.heartbeat_interval = 30
        self.connection_timeout = 300  # 5 minutes
        import os
        self.jwt_secret = os.getenv("WS_JWT_SECRET", "dev-only-secret")
        self.cleanup_task = None
    
    @property
    def active_connections(self):
        """Get list of active connection IDs for compatibility"""
        return list(self.connection_manager.connections.keys())
        
    async def initialize(self):
        """Initialize the WebSocket handler"""
        # Start periodic cleanup task
        self.cleanup_task = asyncio.create_task(self._periodic_cleanup())
        logger.info("WebSocketHandler initialized")
        
    async def handle_connection(self, websocket, path: str):
        """Accept and authenticate WebSocket connection"""
        connection_id = None
        try:
            # Generate unique connection ID
            connection_id = f"conn_{int(time.time() * 1000)}_{id(websocket)}"
            
            # Authenticate connection
            user_id = await self._authenticate_connection(websocket, path)
            
            # Add to connection manager
            self.connection_manager.add_connection(connection_id, websocket, user_id)
            
            logger.info(f"WebSocket connection established: {connection_id} (user: {user_id})")
            
            # Send connection confirmation
            await self._send_message(websocket, {
                "type": "connection_established",
                "connection_id": connection_id,
                "user_id": user_id,
                "timestamp": time.time()
            })
            
            # Start heartbeat task
            heartbeat_task = asyncio.create_task(
                self.maintain_heartbeat(websocket, connection_id)
            )
            
            try:
                # Handle messages from client
                async for message in websocket:
                    await self._handle_client_message(websocket, message, connection_id)
                    
            except ConnectionClosed:
                logger.info(f"WebSocket connection closed: {connection_id}")
            except Exception as e:
                logger.error(f"Error handling WebSocket connection {connection_id}: {e}")
                
        except Exception as e:
            logger.error(f"Error in WebSocket connection handler: {e}")
            
        finally:
            # Cleanup
            if connection_id:
                await self.handle_disconnect(connection_id)
            if 'heartbeat_task' in locals():
                heartbeat_task.cancel()
                
    async def broadcast_npc_status(self, npc_id: str, status: Dict[str, Any]):
        """Send NPC status updates to connected clients"""
        try:
            subscribers = self.connection_manager.get_npc_subscribers(npc_id)
            
            if not subscribers:
                return
                
            message = {
                "type": "npc_status_update",
                "npc_id": npc_id,
                "status": status,
                "timestamp": time.time()
            }
            
            # Send to all subscribers
            tasks = []
            for connection_id in subscribers:
                conn_info = self.connection_manager.get_connection_info(connection_id)
                if conn_info:
                    websocket = conn_info["websocket"]
                    tasks.append(self._send_message(websocket, message))
                    
            if tasks:
                await asyncio.gather(*tasks, return_exceptions=True)
                logger.debug(f"Broadcasted NPC status update for {npc_id} to {len(tasks)} clients")
                
        except Exception as e:
            logger.error(f"Error broadcasting NPC status for {npc_id}: {e}")
            
    async def handle_disconnect(self, connection_id: str):
        """Cleanup on client disconnection"""
        try:
            conn_info = self.connection_manager.get_connection_info(connection_id)
            if conn_info:
                user_id = conn_info["user_id"]
                connected_duration = datetime.utcnow() - conn_info["connected_at"]
                
                logger.info(
                    f"WebSocket disconnected: {connection_id} "
                    f"(user: {user_id}, duration: {connected_duration})"
                )
                
            self.connection_manager.remove_connection(connection_id)
            
        except Exception as e:
            logger.error(f"Error handling disconnect for {connection_id}: {e}")
            
    async def maintain_heartbeat(self, websocket, connection_id: str):
        """Keep connection alive with heartbeat"""
        try:
            while True:
                try:
                    # Send ping
                    await websocket.ping()
                    
                    # Update heartbeat time
                    self.connection_manager.update_heartbeat(connection_id)
                    
                    await asyncio.sleep(self.heartbeat_interval)
                    
                except ConnectionClosed:
                    logger.debug(f"Connection closed during heartbeat: {connection_id}")
                    break
                except Exception as e:
                    logger.error(f"Heartbeat error for {connection_id}: {e}")
                    break
                    
        except Exception as e:
            logger.error(f"Error in heartbeat maintenance for {connection_id}: {e}")
            
    async def broadcast_to_all(self, message: Dict[str, Any], exclude_user: str = None):
        """Broadcast message to all connected clients"""
        try:
            tasks = []
            for connection_id, conn_info in self.connection_manager.connections.items():
                if exclude_user and conn_info["user_id"] == exclude_user:
                    continue
                    
                websocket = conn_info["websocket"]
                tasks.append(self._send_message(websocket, message))
                
            if tasks:
                await asyncio.gather(*tasks, return_exceptions=True)
                logger.debug(f"Broadcasted message to {len(tasks)} clients")
                
        except Exception as e:
            logger.error(f"Error broadcasting to all clients: {e}")
            
    async def send_to_user(self, user_id: str, message: Dict[str, Any]):
        """Send message to all connections of a specific user"""
        try:
            if user_id not in self.connection_manager.user_connections:
                logger.debug(f"No connections found for user {user_id}")
                return
                
            connection_ids = self.connection_manager.user_connections[user_id]
            tasks = []
            
            for connection_id in connection_ids:
                conn_info = self.connection_manager.get_connection_info(connection_id)
                if conn_info:
                    websocket = conn_info["websocket"]
                    tasks.append(self._send_message(websocket, message))
                    
            if tasks:
                await asyncio.gather(*tasks, return_exceptions=True)
                logger.debug(f"Sent message to user {user_id} ({len(tasks)} connections)")
                
        except Exception as e:
            logger.error(f"Error sending message to user {user_id}: {e}")
            
    async def _authenticate_connection(self, websocket, path: str) -> Optional[str]:
        """Authenticate WebSocket connection"""
        try:
            # For demo purposes, we'll accept connections without authentication
            # In production, this should validate JWT tokens or session cookies
            
            # Extract token from path or headers
            # Example: /ws?token=jwt_token_here
            if "token=" in path:
                token = path.split("token=")[1].split("&")[0]
                try:
                    # Decode JWT (in production, use proper validation)
                    payload = jwt.decode(token, self.jwt_secret, algorithms=["HS256"])
                    return payload.get("user_id")
                except jwt.InvalidTokenError:
                    logger.warning("Invalid JWT token in WebSocket connection")
                    
            # No/invalid token -> anonymous user for demo
            return f"anonymous-{int(time.time())}"
            
        except Exception as e:
            logger.error(f"Error authenticating WebSocket connection: {e}")
            return None
            
    async def _handle_client_message(self, websocket, message: str, connection_id: str):
        """Handle incoming message from client"""
        try:
            data = json.loads(message)
            message_type = data.get("type")
            
            if message_type == "subscribe_npc":
                npc_id = data.get("npc_id")
                if npc_id:
                    self.connection_manager.subscribe_to_npc(connection_id, npc_id)
                    await self._send_message(websocket, {
                        "type": "subscription_confirmed",
                        "npc_id": npc_id,
                        "connection_id": connection_id
                    })
                    
            elif message_type == "heartbeat":
                self.connection_manager.update_heartbeat(connection_id)
                await self._send_message(websocket, {
                    "type": "heartbeat_ack",
                    "timestamp": time.time()
                })
                
            elif message_type == "get_connection_info":
                conn_info = self.connection_manager.get_connection_info(connection_id)
                if conn_info:
                    await self._send_message(websocket, {
                        "type": "connection_info",
                        "connection_id": connection_id,
                        "user_id": conn_info["user_id"],
                        "connected_at": conn_info["connected_at"].isoformat(),
                        "subscriptions": list(conn_info["subscriptions"])
                    })
                    
            else:
                logger.debug(f"Unknown message type from {connection_id}: {message_type}")
                
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON from {connection_id}: {e}")
        except Exception as e:
            logger.error(f"Error handling client message from {connection_id}: {e}")
            
    async def _send_message(self, websocket, message: Dict[str, Any]):
        """Send message to WebSocket client"""
        try:
            await websocket.send(json.dumps(message, default=str))
        except ConnectionClosed:
            # Connection already closed, ignore
            pass
        except Exception as e:
            logger.error(f"Error sending message to WebSocket: {e}")
            raise
            
    async def _periodic_cleanup(self):
        """Periodically cleanup stale connections"""
        while True:
            try:
                await asyncio.sleep(60)  # Run every minute
                
                current_time = datetime.utcnow()
                stale_connections = []
                
                for connection_id, conn_info in self.connection_manager.connections.items():
                    last_heartbeat = conn_info["last_heartbeat"]
                    if current_time - last_heartbeat > timedelta(seconds=self.connection_timeout):
                        stale_connections.append(connection_id)
                        
                # Remove stale connections
                for connection_id in stale_connections:
                    await self.handle_disconnect(connection_id)
                    
                if stale_connections:
                    logger.info(f"Cleaned up {len(stale_connections)} stale connections")
                    
            except Exception as e:
                logger.error(f"Error in periodic cleanup: {e}")
                await asyncio.sleep(30)  # Wait before retrying
                
    def get_stats(self) -> Dict[str, Any]:
        """Get WebSocket handler statistics"""
        try:
            base_stats = self.connection_manager.get_stats()
            
            # Add handler-specific stats
            base_stats.update({
                "heartbeat_interval": self.heartbeat_interval,
                "connection_timeout": self.connection_timeout,
                "cleanup_task_running": self.cleanup_task and not self.cleanup_task.done()
            })
            
            return base_stats
            
        except Exception as e:
            logger.error(f"Error getting WebSocket stats: {e}")
            return {}
            
    async def shutdown(self):
        """Graceful shutdown of WebSocket handler"""
        try:
            logger.info("Shutting down WebSocket handler")
            
            # Cancel cleanup task
            if self.cleanup_task:
                self.cleanup_task.cancel()
                
            # Close all connections
            close_tasks = []
            for connection_id, conn_info in self.connection_manager.connections.items():
                websocket = conn_info["websocket"]
                close_tasks.append(websocket.close())
                
            if close_tasks:
                await asyncio.gather(*close_tasks, return_exceptions=True)
                
            logger.info("WebSocket handler shutdown complete")
            
        except Exception as e:
            logger.error(f"Error during WebSocket handler shutdown: {e}")