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
        # Default to Windows host IP for WSL; override with LM_STUDIO_BASE_URL/MODEL_SERVICE_URL
        self.lm_studio_url = (
            os.getenv("LM_STUDIO_BASE_URL")
            or os.getenv("MODEL_SERVICE_URL")
            or "http://10.4.20.10:1234/v1"
        )
        # Pin localhost defaults for native/dev runs; docker-compose overrides via env
        self.npc_service_url = os.getenv("NPC_SERVICE_URL", "http://localhost:8003")
        # Optional explicit model override (e.g., gryphe_codex-24b-small-3.2@q5_k_l)
        self.chat_model_id = os.getenv("CHAT_MODEL_ID") or os.getenv("MODEL_ID")
        self._cleanup_task: Optional[asyncio.Task] = None

    async def initialize(self):
        """Initialize Redis connection and start cleanup task"""
        try:
            import os
            # Ensure the same Redis is used across services in local/dev
            redis_url = os.getenv("REDIS_URL", "redis://localhost:6379")
            self.redis_client = redis.from_url(redis_url)
            await self.redis_client.ping()
            
            # Start periodic cleanup task
            self._cleanup_task = asyncio.create_task(self._periodic_cleanup())
            
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
            try:
                from .context_builder import ContextBuilder  # package context
            except Exception:
                from context_builder import ContextBuilder   # module context
            context_builder = ContextBuilder()
            
            # Get NPC data
            npc_data = await self._get_npc_data(session.npc_id)
            
            # Build ChatML format messages
            system_prompt = context_builder.build_system_prompt(npc_data)
            
            # Create ChatML message structure
            messages = [
                {"role": "system", "content": system_prompt}
            ]
            
            # Add conversation history in ChatML format
            for msg in session.messages[-10:]:  # Last 10 messages to stay within context
                role = "assistant" if msg["role"] == "assistant" else "user"
                messages.append({"role": role, "content": msg["content"]})
            
            # Get complete response from model service (non-streaming for now)
            complete_response = await self._get_complete_response_from_model_chatml(messages, session_id)
            
            # Send complete response
            yield complete_response
            
            # Store complete response
            session.add_message("assistant", complete_response)
            
            # Update session in Redis
            await self._store_session(session)
            
            logger.debug(f"Processed message for session {session_id}")
            
        except Exception as e:
            logger.error(f"Error processing message for session {session_id}: {e}")
            raise

    async def stream_message(self, session_id: str, message: str) -> AsyncGenerator[str, None]:
        """Process user message and stream response chunks as they arrive."""
        try:
            session = await self._get_session(session_id)
            if not session or not session.is_active:
                raise ValueError(f"Invalid or inactive session: {session_id}")

            # Add user message to session
            session.add_message("user", message)

            # Build context for LLM
            try:
                from .context_builder import ContextBuilder
            except Exception:
                from context_builder import ContextBuilder
            context_builder = ContextBuilder()

            # Get NPC data and system prompt
            npc_data = await self._get_npc_data(session.npc_id)
            system_prompt = context_builder.build_system_prompt(npc_data)

            # Assemble ChatML messages including recent history (which includes the just-added user message)
            messages = [{"role": "system", "content": system_prompt}]
            for msg in session.messages[-10:]:
                role = "assistant" if msg["role"] == "assistant" else "user"
                messages.append({"role": role, "content": msg["content"]})

            # Stream from model service
            collected: list[str] = []
            async for chunk in self._stream_from_model_chatml(messages, session_id):
                if chunk:
                    collected.append(chunk)
                    yield chunk

            # On completion, persist assistant message
            complete = "".join(collected).strip()
            if complete:
                session.add_message("assistant", complete)
                await self._store_session(session)

        except Exception as e:
            logger.error(f"Error streaming message for session {session_id}: {e}")
            # Propagate so caller can surface error
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
            timeout = aiohttp.ClientTimeout(total=15, connect=5, sock_read=10)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(f"{self.npc_service_url}/npc/{npc_id}") as response:
                    return response.status == 200
        except Exception as e:
            logger.error(f"Error validating NPC {npc_id}: {e}")
            return False
            
    async def _get_npc_data(self, npc_id: str) -> dict:
        """Get NPC data for context building"""
        try:
            import aiohttp
            timeout = aiohttp.ClientTimeout(total=15, connect=5, sock_read=10)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(f"{self.npc_service_url}/npc/{npc_id}/prompt") as response:
                    if response.status == 200:
                        return await response.json()
                    else:
                        logger.error(f"Failed to get NPC data: {response.status}")
                        return {}
        except Exception as e:
            logger.error(f"Error getting NPC data for {npc_id}: {e}")
            return {}
            
    async def _stream_from_model_chatml(self, messages: List[Dict], session_id: str) -> AsyncGenerator[str, None]:
        """Stream response from LM Studio using OpenAI-compatible API."""
        import aiohttp
        timeout = aiohttp.ClientTimeout(total=300, connect=10, sock_read=300)
        
        logger.info(f"Using currently loaded model in LM Studio for session {session_id}")
        
        # OpenAI-compatible payload
        payload = {
            "messages": messages,  # Proper ChatML message structure
            "max_tokens": 150,  # Shorter responses
            "temperature": 0.7,
            "top_p": 0.9,
            "stream": True,
            "stop": ["\n\nUser:", "User:", "\n\n###", "###"]  # Stop sequences
        }
        # If an explicit model is configured, include it
        if self.chat_model_id:
            payload["model"] = self.chat_model_id
        
        logger.info(f"Streaming from LM Studio for session {session_id}")
        
        try:
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(f"{self.lm_studio_url}/chat/completions", json=payload) as resp:
                    resp.raise_for_status()
                    
                    chunk_count = 0
                    token_count = 0
                    max_tokens = 150  # Hard limit
                    had_content = False
                    buffered: list[str] = []
                    
                    async for line in resp.content:
                        if not line:
                            continue
                            
                        line_str = line.decode(errors="ignore").strip()
                        
                        # Skip empty lines and non-data lines
                        if not line_str or not line_str.startswith("data: "):
                            continue
                            
                        # Extract JSON data
                        data_str = line_str[6:]  # Remove "data: " prefix
                        
                        # Handle [DONE] marker
                        if data_str.strip() == "[DONE]":
                            logger.info(f"LM Studio streaming complete for session {session_id} ({chunk_count} chunks)")
                            break
                            
                        try:
                            data = json.loads(data_str)
                            
                            # Extract content from OpenAI format
                            choices = data.get("choices", [])
                            if choices:
                                choice = choices[0]
                                delta = choice.get("delta", {})
                                content = delta.get("content", "")
                                
                                # Check if generation is complete
                                if choice.get("finish_reason") in ["stop", "length"]:
                                    logger.info(f"LM Studio generation finished: {choice.get('finish_reason')} for session {session_id}")
                                    break
                                    
                                if content:
                                    chunk_count += 1
                                    token_count += len(content.split())  # Rough token count
                                    had_content = True
                                    buffered.append(content)
                                    
                                    # Hard stop at token limit
                                    if token_count >= max_tokens:
                                        logger.info(f"Reached token limit ({max_tokens}) for session {session_id}")
                                        yield content
                                        break
                                        
                                    yield content
                                    
                        except json.JSONDecodeError:
                            continue
                            
                    logger.info(f"Streaming generator exhausted for session {session_id} ({chunk_count} total chunks)")

                    # Fallback: if no content streamed, try a non-streaming completion once
                    if not had_content:
                        try:
                            logger.info(f"No streamed content for session {session_id}; fetching complete response")
                            full = await self._get_complete_response_from_model_chatml(messages, session_id)
                            if full:
                                yield full
                        except Exception as fe:
                            logger.error(f"Fallback complete response failed: {fe}")
                            
        except Exception as e:
            logger.error(f"Error streaming from LM Studio: {e}")
            raise
    
    async def _get_complete_response_from_model_chatml(self, messages: List[Dict], session_id: str) -> str:
        """Get complete response from LM Studio using OpenAI-compatible API."""
        import aiohttp
        timeout = aiohttp.ClientTimeout(total=300, connect=10, sock_read=300)
        
        logger.info(f"Getting complete response from LM Studio for session {session_id}")
        
        # OpenAI-compatible payload (non-streaming)
        payload = {
            "messages": messages,  # Proper ChatML message structure
            "max_tokens": 150,  # Shorter responses
            "temperature": 0.7,
            "top_p": 0.9,
            "stream": False,  # No streaming
            "stop": ["\n\nUser:", "User:", "\n\n###", "###"]  # Stop sequences
        }
        if self.chat_model_id:
            payload["model"] = self.chat_model_id
        
        try:
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(f"{self.lm_studio_url}/chat/completions", json=payload) as resp:
                    resp.raise_for_status()
                    
                    response_data = await resp.json()
                    
                    # Extract content from OpenAI format
                    choices = response_data.get("choices", [])
                    if choices:
                        choice = choices[0]
                        message = choice.get("message", {})
                        content = message.get("content", "")
                        
                        logger.info(f"LM Studio complete response for session {session_id}: {len(content)} characters")
                        return content.strip()
                    
                    logger.warning(f"No choices in LM Studio response for session {session_id}")
                    return ""
                            
        except Exception as e:
            logger.error(f"Error getting complete response from LM Studio: {e}")
            return f"Sorry, I encountered an error: {str(e)}"
            
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

    async def shutdown(self):
        """Gracefully stop background tasks and close resources."""
        try:
            if self._cleanup_task:
                self._cleanup_task.cancel()
                try:
                    await self._cleanup_task
                except asyncio.CancelledError:
                    pass
            # No explicit Redis close needed for redis.asyncio client
            logger.info("ConversationManager shutdown complete")
        except Exception as e:
            logger.debug(f"ConversationManager shutdown error: {e}")
