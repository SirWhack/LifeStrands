import asyncio
import logging
import json
from contextlib import asynccontextmanager
from typing import Dict, Any

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from src.conversation_manager import ConversationManager
from src.websocket_handler import WebSocketHandler

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Global managers
conversation_manager = ConversationManager()
websocket_handler = WebSocketHandler()

class StartConversationRequest(BaseModel):
    npc_id: str
    user_id: str

class SendMessageRequest(BaseModel):
    session_id: str
    message: str

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown events"""
    try:
        await conversation_manager.initialize()
        await websocket_handler.initialize()
        logger.info("Chat service started successfully")
        yield
    except Exception as e:
        logger.error(f"Failed to initialize chat service: {e}")
        raise
    finally:
        try:
            await websocket_handler.shutdown()
        except Exception as e:
            logger.debug(f"WebSocket handler shutdown error: {e}")
        try:
            # Graceful shutdown for conversation manager (cleanup tasks)
            if hasattr(conversation_manager, "shutdown"):
                await conversation_manager.shutdown()
        except Exception as e:
            logger.debug(f"Conversation manager shutdown error: {e}")
        logger.info("Chat service shut down")

app = FastAPI(
    title="Life Strands Chat Service", 
    description="Real-time conversation management service",
    version="1.0.0",
    lifespan=lifespan
)

# Add CORS middleware for frontend access
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",  # React frontend
        "http://localhost:3001",  # Alternative frontend port
        "http://localhost:3002",  # Admin dashboard
        "http://127.0.0.1:3000",
        "http://127.0.0.1:3001",
        "http://127.0.0.1:3002"
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    active_sessions = await conversation_manager.get_active_sessions()
    return {
        "status": "healthy",
        "active_sessions": len(active_sessions),
        "connected_websockets": len(websocket_handler.connection_manager.connections)
    }

@app.post("/conversation/start")
async def start_conversation(request: StartConversationRequest):
    """Start a new conversation session"""
    try:
        session_id = await conversation_manager.start_conversation(
            request.npc_id, 
            request.user_id
        )
        return {"session_id": session_id}
    except Exception as e:
        logger.error(f"Error starting conversation: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# Compatibility route expected by integration tests
@app.post("/conversations/start", status_code=201)
async def start_conversation_v2(request: StartConversationRequest):
    return await start_conversation(request)

@app.post("/conversation/send")
async def send_message(request: SendMessageRequest):
    """Send message in conversation (non-streaming)"""
    try:
        response_chunks = []
        async for chunk in conversation_manager.process_message(
            request.session_id,
            request.message
        ):
            response_chunks.append(chunk)
            
        return {"response": "".join(response_chunks)}
        
    except Exception as e:
        logger.error(f"Error sending message: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/conversation/{session_id}/end")
async def end_conversation(session_id: str):
    """End a conversation session"""
    try:
        await conversation_manager.end_conversation(session_id)
        return {"message": "Conversation ended successfully"}
    except Exception as e:
        logger.error(f"Error ending conversation: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# Compatibility route
@app.post("/conversations/{session_id}/end")
async def end_conversation_v2(session_id: str):
    return await end_conversation(session_id)

@app.get("/conversation/{session_id}/history")
async def get_conversation_history(session_id: str):
    """Get conversation message history"""
    try:
        history = await conversation_manager.get_conversation_history(session_id)
        return {"messages": history}
    except Exception as e:
        logger.error(f"Error getting conversation history: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# Compatibility route returning a raw list as expected by tests
@app.get("/conversations/{session_id}/history")
async def get_conversation_history_v2(session_id: str):
    try:
        history = await conversation_manager.get_conversation_history(session_id)
        return history
    except Exception as e:
        logger.error(f"Error getting conversation history: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/conversations/active")
async def get_active_conversations():
    """Get all active conversation sessions"""
    try:
        sessions = await conversation_manager.get_active_sessions()
        return {"active_sessions": sessions}
    except Exception as e:
        logger.error(f"Error getting active conversations: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/metrics")
async def get_metrics():
    """Get service metrics for monitoring"""
    from datetime import datetime
    try:
        active_sessions = await conversation_manager.get_active_sessions()
        return {
            "service": "chat-service",
            "timestamp": datetime.utcnow().isoformat(),
            "active_conversations": len(active_sessions),
            "status": "healthy"
        }
    except Exception as e:
        return {
            "service": "chat-service",
            "timestamp": datetime.utcnow().isoformat(),
            "status": "error",
            "error": str(e)
        }

# Streaming message endpoint (JSON lines per chunk) for test compatibility
from fastapi import Request
from fastapi.responses import StreamingResponse

@app.post("/conversations/{session_id}/message")
async def send_message_streaming(session_id: str, request: Request):
    try:
        body = await request.json()
        content = body.get("content", "")

        async def token_stream():
            try:
                async for chunk in conversation_manager.stream_message(session_id, content):
                    if chunk:
                        yield f"{json.dumps({'token': chunk})}\n"
            except Exception as e:
                # Emit an error frame then end stream
                yield f"{json.dumps({'error': str(e)})}\n"

        return StreamingResponse(token_stream(), media_type="application/json")
    except Exception as e:
        logger.error(f"Error in streaming endpoint: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# LM Studio connectivity check (debug)
@app.get("/lmstudio/status")
async def lmstudio_status():
    import aiohttp
    url = conversation_manager.lm_studio_url.rstrip("/") + "/models"
    try:
        timeout = aiohttp.ClientTimeout(total=10, connect=3, sock_read=7)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(url) as resp:
                text = await resp.text()
                return {"url": url, "status": resp.status, "body": text[:1000]}
    except Exception as e:
        logger.error(f"LM Studio status check failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket endpoint for real-time chat - user-based connection"""
    await websocket.accept()
    
    # Generate unique connection ID for this user session
    import time
    user_id = "default-user"  # For now, use default user
    connection_id = f"user_{user_id}_{int(time.time() * 1000)}"
    
    try:
        # Register connection
        websocket_handler.connection_manager.add_connection(connection_id, websocket, user_id)
        logger.info(f"WebSocket connected for user {user_id} (connection: {connection_id})")
        
        # Send connection ready message
        await websocket.send_text(json.dumps({
            "type": "connection_ready",
            "user_id": user_id,
            "connection_id": connection_id
        }))
        
        # Store user's active conversations
        user_conversations = {}  # npc_id -> session_id
        
        while True:
            try:
                # Receive message from client using FastAPI's receive_text
                data = await websocket.receive_text()
                
                if not data:
                    continue
                    
                try:
                    message_data = json.loads(data)
                except json.JSONDecodeError:
                    logger.error(f"Invalid JSON received: {data}")
                    await websocket.send_text(json.dumps({
                        "type": "error",
                        "message": "Invalid message format"
                    }))
                    continue
                
                if message_data.get("type") == "message":
                    npc_id = message_data.get("npc_id")
                    user_message = message_data.get("content", "")
                    
                    logger.info(f"Processing message for NPC {npc_id}: {user_message[:50]}...")
                    
                    if not npc_id:
                        await websocket.send_text(json.dumps({
                            "type": "error",
                            "message": "npc_id required for messages"
                        }))
                        continue
                    
                    # Get or create conversation for this user+NPC pair
                    if npc_id not in user_conversations:
                        session_id = await conversation_manager.start_conversation(npc_id, user_id)
                        user_conversations[npc_id] = session_id
                        logger.info(f"Created conversation {session_id} for user {user_id} + NPC {npc_id}")
                    else:
                        session_id = user_conversations[npc_id]
                    
                    # Stream response chunks over WebSocket
                    try:
                        logger.info(f"Streaming response for session {session_id}")
                        any_chunk = False
                        async for chunk in conversation_manager.stream_message(
                            session_id,
                            user_message
                        ):
                            if websocket.client_state.value == 1 and chunk:
                                any_chunk = True
                                await websocket.send_text(json.dumps({
                                    "type": "response_chunk",
                                    "npc_id": npc_id,
                                    "chunk": chunk
                                }))

                        # If no chunks were produced, try to send a complete message body
                        if not any_chunk and websocket.client_state.value == 1:
                            logger.info(f"No chunks produced; sending complete message for {session_id}")
                            complete_response = await conversation_manager._get_complete_response_from_model_chatml(
                                messages=[{"role": "user", "content": user_message}],
                                session_id=session_id
                            )
                            await websocket.send_text(json.dumps({
                                "type": "message_complete",
                                "content": complete_response,
                                "npc_id": npc_id
                            }))
                        elif websocket.client_state.value == 1:
                            # Send stream completion signal
                            await websocket.send_text(json.dumps({
                                "type": "response_complete",
                                "npc_id": npc_id
                            }))
                        else:
                            logger.warning(f"WebSocket disconnected, cannot send complete message for NPC {npc_id}")
                    except Exception as stream_error:
                        logger.error(f"Error streaming response: {stream_error}")
                        if websocket.client_state.value == 1:
                            await websocket.send_text(json.dumps({
                                "type": "error",
                                "message": f"Error generating response: {str(stream_error)}",
                                "npc_id": npc_id
                            }))
                    
                elif message_data.get("type") == "ping":
                    if websocket.client_state.value == 1:  # CONNECTED
                        await websocket.send_text(json.dumps({
                            "type": "pong"
                        }))
                        
            except WebSocketDisconnect:
                logger.info(f"WebSocket disconnected normally for connection {connection_id}")
                break
            except Exception as e:
                logger.error(f"Error in message loop for connection {connection_id}: {e}")
                # Only try to send error if connection is still open
                if websocket.client_state.value == 1:  # CONNECTED
                    try:
                        await websocket.send_text(json.dumps({
                            "type": "error",
                            "message": str(e)
                        }))
                    except Exception as send_error:
                        logger.debug(f"Could not send error to closed connection {connection_id}: {send_error}")
                break
                
    except WebSocketDisconnect:
        logger.info(f"WebSocket disconnected for user {user_id} (connection: {connection_id})")
    except Exception as e:
        logger.error(f"WebSocket error for connection {connection_id}: {e}")
    finally:
        # Clean up conversations for this connection
        if user_conversations:
            logger.info(f"Cleaning up {len(user_conversations)} conversations for connection {connection_id}")
            for npc_id, session_id in user_conversations.items():
                try:
                    await conversation_manager.end_conversation(session_id)
                except Exception as cleanup_error:
                    logger.debug(f"Error cleaning up session {session_id}: {cleanup_error}")
        
        # Remove connection from manager
        try:
            websocket_handler.connection_manager.remove_connection(connection_id)
        except Exception as remove_error:
            logger.debug(f"Error removing connection {connection_id}: {remove_error}")

@app.websocket("/ws/monitor")
async def monitor_websocket(websocket: WebSocket):
    """WebSocket for monitoring active conversations"""
    await websocket.accept()
    
    try:
        logger.info("Monitor WebSocket connected")
        
        while True:
            # Send periodic updates
            await asyncio.sleep(5)
            
            active_sessions = await conversation_manager.get_active_sessions()
            
            await websocket.send_text(json.dumps({
                "type": "session_update",
                "active_sessions": len(active_sessions),
                "sessions": list(active_sessions.keys())
            }))
            
    except WebSocketDisconnect:
        logger.info("Monitor WebSocket disconnected")
    except Exception as e:
        logger.error(f"Monitor WebSocket error: {e}")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8002,
        reload=False,
        log_level="info"
    )
