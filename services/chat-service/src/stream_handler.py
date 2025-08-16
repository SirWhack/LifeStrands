import asyncio
import json
import logging
import time
from typing import AsyncGenerator, Optional, Dict, Any
import websockets
from websockets.exceptions import ConnectionClosed, WebSocketException

logger = logging.getLogger(__name__)

class TokenBuffer:
    """Buffer for handling partial tokens and smooth display"""
    
    def __init__(self, buffer_size: int = 3):
        self.buffer = []
        self.buffer_size = buffer_size
        self.word_boundary_chars = {' ', '\n', '\t', '.', ',', '!', '?', ';', ':'}
        
    def add_token(self, token: str) -> Optional[str]:
        """Add token to buffer and return complete words when ready"""
        self.buffer.append(token)
        
        # Check if we have a word boundary or buffer is full
        current_text = ''.join(self.buffer)
        
        if (len(self.buffer) >= self.buffer_size or 
            any(char in current_text for char in self.word_boundary_chars)):
            result = current_text
            self.buffer.clear()
            return result
            
        return None
        
    def flush(self) -> str:
        """Flush any remaining tokens in buffer"""
        if self.buffer:
            result = ''.join(self.buffer)
            self.buffer.clear()
            return result
        return ""

class StreamMetrics:
    """Track streaming performance metrics"""
    
    def __init__(self):
        self.start_time: Optional[float] = None
        self.first_token_time: Optional[float] = None
        self.token_count = 0
        self.total_chars = 0
        self.last_token_time: Optional[float] = None
        
    def start(self):
        """Start timing"""
        self.start_time = time.time()
        self.token_count = 0
        self.total_chars = 0
        self.first_token_time = None
        self.last_token_time = None
        
    def add_token(self, token: str):
        """Record a new token"""
        current_time = time.time()
        
        if self.first_token_time is None:
            self.first_token_time = current_time
            
        self.token_count += 1
        self.total_chars += len(token)
        self.last_token_time = current_time
        
    def get_stats(self) -> Dict[str, Any]:
        """Get current streaming statistics"""
        if not self.start_time:
            return {}
            
        current_time = time.time()
        total_time = current_time - self.start_time
        
        stats = {
            "total_time_seconds": total_time,
            "token_count": self.token_count,
            "total_characters": self.total_chars,
            "tokens_per_second": 0,
            "characters_per_second": 0,
            "time_to_first_token": None
        }
        
        if self.token_count > 0 and total_time > 0:
            stats["tokens_per_second"] = self.token_count / total_time
            stats["characters_per_second"] = self.total_chars / total_time
            
        if self.first_token_time and self.start_time:
            stats["time_to_first_token"] = self.first_token_time - self.start_time
            
        return stats

class StreamHandler:
    """Manages token streaming and WebSocket communication"""
    
    def __init__(self):
        self.active_streams: Dict[str, Dict[str, Any]] = {}
        self.buffer_size = 3
        self.heartbeat_interval = 30
        
    async def stream_tokens_to_client(self, generator: AsyncGenerator[str, None], websocket, session_id: str = None):
        """Stream tokens as they generate to WebSocket"""
        try:
            if not session_id:
                session_id = f"stream_{int(time.time())}"
                
            # Initialize stream state
            stream_state = {
                "websocket": websocket,
                "buffer": TokenBuffer(self.buffer_size),
                "metrics": StreamMetrics(),
                "is_active": True,
                "interrupted": False
            }
            
            self.active_streams[session_id] = stream_state
            stream_state["metrics"].start()
            
            logger.info(f"Started streaming to client for session {session_id}")
            
            # Send stream start event
            await self._send_stream_event(websocket, "stream_start", {
                "session_id": session_id,
                "timestamp": time.time()
            })
            
            try:
                async for token in generator:
                    if stream_state["interrupted"]:
                        logger.info(f"Stream {session_id} was interrupted")
                        break
                        
                    # Add token to metrics
                    stream_state["metrics"].add_token(token)
                    
                    # Buffer token for smooth display
                    buffered_text = stream_state["buffer"].add_token(token)
                    
                    if buffered_text:
                        # Send buffered text to client
                        await self._send_token(websocket, buffered_text, session_id)
                        
                # Flush any remaining tokens
                remaining = stream_state["buffer"].flush()
                if remaining:
                    await self._send_token(websocket, remaining, session_id)
                    
                # Send stream complete event
                final_stats = stream_state["metrics"].get_stats()
                await self._send_stream_event(websocket, "stream_complete", {
                    "session_id": session_id,
                    "stats": final_stats,
                    "timestamp": time.time()
                })
                
                logger.info(f"Completed streaming for session {session_id}: {final_stats}")
                
            except ConnectionClosed:
                logger.info(f"Client disconnected during stream {session_id}")
            except WebSocketException as e:
                logger.error(f"WebSocket error during stream {session_id}: {e}")
            except Exception as e:
                logger.error(f"Error during streaming {session_id}: {e}")
                await self._send_stream_event(websocket, "stream_error", {
                    "session_id": session_id,
                    "error": str(e),
                    "timestamp": time.time()
                })
                
        except Exception as e:
            logger.error(f"Critical error in stream_tokens_to_client: {e}")
            
        finally:
            # Cleanup
            if session_id in self.active_streams:
                self.active_streams[session_id]["is_active"] = False
                del self.active_streams[session_id]
                
    async def buffer_partial_tokens(self, token: str, buffer: TokenBuffer) -> Optional[str]:
        """Handle partial word tokens for smooth display"""
        try:
            return buffer.add_token(token)
        except Exception as e:
            logger.error(f"Error buffering token: {e}")
            return token  # Fallback to immediate display
            
    async def handle_stream_interruption(self, session_id: str):
        """Graceful handling of interrupted streams"""
        try:
            if session_id in self.active_streams:
                stream_state = self.active_streams[session_id]
                stream_state["interrupted"] = True
                
                # Send interruption notification
                if stream_state["websocket"]:
                    await self._send_stream_event(
                        stream_state["websocket"],
                        "stream_interrupted",
                        {
                            "session_id": session_id,
                            "timestamp": time.time()
                        }
                    )
                    
                logger.info(f"Stream {session_id} marked for interruption")
                
        except Exception as e:
            logger.error(f"Error handling stream interruption for {session_id}: {e}")
            
    async def calculate_tokens_per_second(self, session_id: str) -> float:
        """Real-time token generation speed"""
        try:
            if session_id in self.active_streams:
                metrics = self.active_streams[session_id]["metrics"]
                stats = metrics.get_stats()
                return stats.get("tokens_per_second", 0.0)
            return 0.0
        except Exception as e:
            logger.error(f"Error calculating tokens per second for {session_id}: {e}")
            return 0.0
            
    async def get_stream_stats(self, session_id: str) -> Dict[str, Any]:
        """Get real-time statistics for a stream"""
        try:
            if session_id in self.active_streams:
                stream_state = self.active_streams[session_id]
                stats = stream_state["metrics"].get_stats()
                stats.update({
                    "is_active": stream_state["is_active"],
                    "interrupted": stream_state["interrupted"]
                })
                return stats
            return {}
        except Exception as e:
            logger.error(f"Error getting stream stats for {session_id}: {e}")
            return {}
            
    async def get_active_streams(self) -> Dict[str, Dict[str, Any]]:
        """Get information about all active streams"""
        try:
            active_info = {}
            for session_id, stream_state in self.active_streams.items():
                if stream_state["is_active"]:
                    active_info[session_id] = {
                        "stats": stream_state["metrics"].get_stats(),
                        "interrupted": stream_state["interrupted"]
                    }
            return active_info
        except Exception as e:
            logger.error(f"Error getting active streams: {e}")
            return {}
            
    async def _send_token(self, websocket, token: str, session_id: str):
        """Send a token to the WebSocket client"""
        try:
            message = {
                "type": "token",
                "session_id": session_id,
                "content": token,
                "timestamp": time.time()
            }
            
            await websocket.send(json.dumps(message))
            
        except ConnectionClosed:
            logger.debug(f"Connection closed while sending token for {session_id}")
            raise
        except Exception as e:
            logger.error(f"Error sending token for {session_id}: {e}")
            raise
            
    async def _send_stream_event(self, websocket, event_type: str, data: Dict[str, Any]):
        """Send stream event to WebSocket client"""
        try:
            message = {
                "type": event_type,
                **data
            }
            
            await websocket.send(json.dumps(message))
            
        except ConnectionClosed:
            logger.debug(f"Connection closed while sending {event_type} event")
        except Exception as e:
            logger.error(f"Error sending {event_type} event: {e}")
            
    def cleanup_inactive_streams(self):
        """Remove inactive streams from memory"""
        try:
            inactive_sessions = [
                session_id for session_id, stream_state in self.active_streams.items()
                if not stream_state["is_active"]
            ]
            
            for session_id in inactive_sessions:
                del self.active_streams[session_id]
                
            if inactive_sessions:
                logger.debug(f"Cleaned up {len(inactive_sessions)} inactive streams")
                
        except Exception as e:
            logger.error(f"Error cleaning up inactive streams: {e}")
            
    async def start_heartbeat(self, websocket, session_id: str):
        """Start heartbeat to keep connection alive"""
        try:
            while session_id in self.active_streams and self.active_streams[session_id]["is_active"]:
                try:
                    await self._send_stream_event(websocket, "heartbeat", {
                        "session_id": session_id,
                        "timestamp": time.time()
                    })
                    await asyncio.sleep(self.heartbeat_interval)
                except ConnectionClosed:
                    break
                except Exception as e:
                    logger.error(f"Heartbeat error for {session_id}: {e}")
                    break
                    
        except Exception as e:
            logger.error(f"Error in heartbeat for {session_id}: {e}")
            
    def get_global_stats(self) -> Dict[str, Any]:
        """Get global streaming statistics"""
        try:
            active_count = len(self.active_streams)
            total_tokens = sum(
                stream_state["metrics"].token_count 
                for stream_state in self.active_streams.values()
            )
            
            avg_tokens_per_second = 0
            if active_count > 0:
                total_tps = sum(
                    stream_state["metrics"].get_stats().get("tokens_per_second", 0)
                    for stream_state in self.active_streams.values()
                )
                avg_tokens_per_second = total_tps / active_count
                
            return {
                "active_streams": active_count,
                "total_tokens_generated": total_tokens,
                "average_tokens_per_second": avg_tokens_per_second,
                "buffer_size": self.buffer_size,
                "heartbeat_interval": self.heartbeat_interval
            }
            
        except Exception as e:
            logger.error(f"Error getting global stats: {e}")
            return {}