import asyncio
import uuid
import json
import logging
import os
from typing import AsyncGenerator, Dict, Any, Optional, List
from datetime import datetime, timedelta
import redis.asyncio as redis

logger = logging.getLogger(__name__)

class ConversationSession:
    def __init__(self, session_id: str, npc_id: str, user_id: str):
        self.session_id = session_id
        self.npc_id = npc_id
        self.user_id = user_id
        self.created_at = datetime.utcnow()
        self.last_activity = datetime.utcnow()
        self.messages: List[Dict[str, Any]] = []
        self.is_active = True
        self.timeout_seconds = 1800  # 30 minutes default

    def add_message(self, role: str, content: str, metadata: Optional[Dict] = None):
        message = {
            "role": role,
            "content": content,
            "timestamp": datetime.utcnow().isoformat(),
            "metadata": metadata or {}
        }
        self.messages.append(message)
        self.last_activity = datetime.utcnow()

    def is_expired(self) -> bool:
        return datetime.utcnow() - self.last_activity > timedelta(seconds=self.timeout_seconds)

    def to_dict(self) -> dict:
        return {
            "session_id": self.session_id,
            "npc_id": self.npc_id,
            "user_id": self.user_id,
            "created_at": self.created_at.isoformat(),
            "last_activity": self.last_activity.isoformat(),
            "messages": self.messages,
            "is_active": self.is_active
        }

class ConversationManager:
    """Orchestrates conversations between users and NPCs"""
    
    def __init__(self):
        self.redis_client: Optional[redis.Redis] = None
        self.active_sessions: Dict[str, ConversationSession] = {}
        self.cleanup_interval = 300  # 5 minutes
        self.model_service_url = os.getenv("MODEL_SERVICE_URL", "http://host.docker.internal:8001")
        self.npc_service_url = "http://localhost:8003"
        
    async def initialize(self):
        """Initialize Redis connection and start cleanup task"""
        try:
            import os
            redis_url = os.getenv("REDIS_URL", "redis://localhost:6379")
            self.redis_client = redis.from_url(redis_url)
            await self.redis_client.ping()
            
            # Start periodic cleanup task
            asyncio.create_task(self._periodic_cleanup())
            
            logger.info("ConversationManager initialized successfully")
            
        except Exception as e:
            logger.error(f"Failed to initialize ConversationManager: {e}")
            raise
            
    async def start_conversation(self, npc_id: str, user_id: str) -> str:
        """Initialize new conversation session"""
        try:
            session_id = str(uuid.uuid4())
            
            # Validate NPC exists
            if not await self._validate_npc(npc_id):
                raise ValueError(f"NPC {npc_id} not found")
                
            # Create session
            session = ConversationSession(session_id, npc_id, user_id)
            self.active_sessions[session_id] = session
            
            # Store in Redis for persistence
            await self._store_session(session)
            
            # Log conversation start
            logger.info(f"Started conversation {session_id} between user {user_id} and NPC {npc_id}")
            
            # Notify model service about new session
            await self._notify_model_service("session_started", {
                "session_id": session_id,
                "npc_id": npc_id,
                "user_id": user_id
            })
            
            return session_id
            
        except Exception as e:
            logger.error(f"Error starting conversation: {e}")
            raise
            
    async def process_message(self, session_id: str, message: str) -> AsyncGenerator[str, None]:
        """Process user message and stream response"""
        try:
            session = await self._get_session(session_id)
            if not session or not session.is_active:
                raise ValueError(f"Invalid or inactive session: {session_id}")
                
            # Add user message to session
            session.add_message("user", message)
            
            # Build context for LLM
            from .context_builder import ContextBuilder
            context_builder = ContextBuilder()
            
            # Get NPC data
            npc_data = await self._get_npc_data(session.npc_id)
            
            # Build conversation context
            system_prompt = context_builder.build_system_prompt(npc_data)
            conversation_context = context_builder.build_conversation_context(
                npc_data, session.messages
            )
            
            # Combine prompts
            full_prompt = f"{system_prompt}\n\n{conversation_context}\n\nUser: {message}\nAssistant:"
            
            # Stream response from model service
            response_chunks = []
            async for chunk in self._stream_from_model(full_prompt, session_id):
                response_chunks.append(chunk)
                yield chunk
                
            # Store complete response
            complete_response = "".join(response_chunks)
            session.add_message("assistant", complete_response)
            
            # Update session in Redis
            await self._store_session(session)
            
            logger.debug(f"Processed message for session {session_id}")
            
        except Exception as e:
            logger.error(f"Error processing message for session {session_id}: {e}")
            raise
            
    async def end_conversation(self, session_id: str):
        """Finalize conversation and trigger summary"""
        try:
            session = await self._get_session(session_id)
            if not session:
                logger.warning(f"Session {session_id} not found")
                return
                
            # Mark session as inactive
            session.is_active = False
            await self._store_session(session)
            
            # Trigger summary generation
            await self._queue_for_summary(session)
            
            # Remove from active sessions
            if session_id in self.active_sessions:
                del self.active_sessions[session_id]
                
            logger.info(f"Ended conversation {session_id}")
            
        except Exception as e:
            logger.error(f"Error ending conversation {session_id}: {e}")
            raise
            
    async def get_conversation_history(self, session_id: str) -> List[Dict[str, Any]]:
        """Retrieve full conversation transcript"""
        try:
            session = await self._get_session(session_id)
            if not session:
                raise ValueError(f"Session {session_id} not found")
                
            return session.messages
            
        except Exception as e:
            logger.error(f"Error getting conversation history for {session_id}: {e}")
            raise
            
    async def handle_timeout(self, session_id: str):
        """Handle idle conversation timeout"""
        try:
            session = await self._get_session(session_id)
            if not session:
                return
                
            if session.is_expired():
                logger.info(f"Session {session_id} timed out")
                await self.end_conversation(session_id)
                
        except Exception as e:
            logger.error(f"Error handling timeout for session {session_id}: {e}")
            
    async def get_active_sessions(self) -> Dict[str, Dict[str, Any]]:
        """Get all active conversation sessions"""
        try:
            return {
                session_id: session.to_dict() 
                for session_id, session in self.active_sessions.items()
                if session.is_active
            }
        except Exception as e:
            logger.error(f"Error getting active sessions: {e}")
            return {}
            
    async def _get_session(self, session_id: str) -> Optional[ConversationSession]:
        """Get session from memory or Redis"""
        try:
            # Check memory first
            if session_id in self.active_sessions:
                return self.active_sessions[session_id]
                
            # Try Redis
            if self.redis_client:
                session_data = await self.redis_client.get(f"conversation:{session_id}")
                if session_data:
                    data = json.loads(session_data)
                    session = self._session_from_dict(data)
                    self.active_sessions[session_id] = session
                    return session
                    
            return None
            
        except Exception as e:
            logger.error(f"Error getting session {session_id}: {e}")
            return None
            
    async def _store_session(self, session: ConversationSession):
        """Store session in Redis"""
        try:
            if self.redis_client:
                session_data = json.dumps(session.to_dict(), default=str)
                await self.redis_client.set(
                    f"conversation:{session.session_id}",
                    session_data,
                    ex=86400  # 24 hours TTL
                )
        except Exception as e:
            logger.error(f"Error storing session {session.session_id}: {e}")
            
    def _session_from_dict(self, data: dict) -> ConversationSession:
        """Create session object from dictionary"""
        session = ConversationSession(
            data["session_id"],
            data["npc_id"],
            data["user_id"]
        )
        session.created_at = datetime.fromisoformat(data["created_at"])
        session.last_activity = datetime.fromisoformat(data["last_activity"])
        session.messages = data["messages"]
        session.is_active = data["is_active"]
        return session
        
    async def _validate_npc(self, npc_id: str) -> bool:
        """Validate NPC exists"""
        try:
            import aiohttp
            async with aiohttp.ClientSession() as session:
                async with session.get(f"{self.npc_service_url}/npc/{npc_id}") as response:
                    return response.status == 200
        except Exception as e:
            logger.error(f"Error validating NPC {npc_id}: {e}")
            return False
            
    async def _get_npc_data(self, npc_id: str) -> dict:
        """Get NPC data for context building"""
        try:
            import aiohttp
            async with aiohttp.ClientSession() as session:
                async with session.get(f"{self.npc_service_url}/npc/{npc_id}/prompt") as response:
                    if response.status == 200:
                        return await response.json()
                    else:
                        logger.error(f"Failed to get NPC data: {response.status}")
                        return {}
        except Exception as e:
            logger.error(f"Error getting NPC data for {npc_id}: {e}")
            return {}
            
    async def _stream_from_model(self, prompt: str, session_id: str) -> AsyncGenerator[str, None]:
        """Stream response from model service"""
        try:
            import aiohttp
            async with aiohttp.ClientSession() as session:
                payload = {
                    "prompt": prompt,
                    "session_id": session_id,
                    "stream": True
                }
                
                async with session.post(
                    f"{self.model_service_url}/generate/stream",
                    json=payload
                ) as response:
                    if response.status == 200:
                        async for line in response.content:
                            if line:
                                try:
                                    data = json.loads(line.decode().strip())
                                    if "token" in data:
                                        yield data["token"]
                                except json.JSONDecodeError:
                                    continue
                    else:
                        raise Exception(f"Model service error: {response.status}")
                        
        except Exception as e:
            logger.error(f"Error streaming from model service: {e}")
            raise
            
    async def _queue_for_summary(self, session: ConversationSession):
        """Queue conversation for summary generation"""
        try:
            if self.redis_client:
                summary_request = {
                    "session_id": session.session_id,
                    "npc_id": session.npc_id,
                    "user_id": session.user_id,
                    "messages": session.messages,
                    "created_at": session.created_at.isoformat(),
                    "ended_at": datetime.utcnow().isoformat()
                }
                
                await self.redis_client.lpush(
                    "summary_queue",
                    json.dumps(summary_request, default=str)
                )
                
                logger.info(f"Queued session {session.session_id} for summary")
                
        except Exception as e:
            logger.error(f"Error queuing session for summary: {e}")
            
    async def _notify_model_service(self, event: str, data: dict):
        """Send notifications to model service"""
        try:
            if self.redis_client:
                notification = {
                    "event": event,
                    "timestamp": datetime.utcnow().isoformat(),
                    "data": data
                }
                await self.redis_client.publish(
                    "model_service_notifications",
                    json.dumps(notification, default=str)
                )
        except Exception as e:
            logger.debug(f"Error notifying model service: {e}")
            
    async def _periodic_cleanup(self):
        """Periodically cleanup expired sessions"""
        while True:
            try:
                await asyncio.sleep(self.cleanup_interval)
                
                expired_sessions = [
                    session_id for session_id, session in self.active_sessions.items()
                    if session.is_expired()
                ]
                
                for session_id in expired_sessions:
                    await self.handle_timeout(session_id)
                    
                if expired_sessions:
                    logger.info(f"Cleaned up {len(expired_sessions)} expired sessions")
                    
            except Exception as e:
                logger.error(f"Error in periodic cleanup: {e}")
                await asyncio.sleep(60)  # Wait before retrying