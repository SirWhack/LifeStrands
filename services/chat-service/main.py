import asyncio
import logging
import json
from contextlib import asynccontextmanager
from typing import Dict, Any

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
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
        logger.info("Chat service shut down")

app = FastAPI(
    title="Life Strands Chat Service", 
    description="Real-time conversation management service",
    version="1.0.0",
    lifespan=lifespan
)

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    active_sessions = await conversation_manager.get_active_sessions()
    return {
        "status": "healthy",
        "active_sessions": len(active_sessions),
        "connected_websockets": len(websocket_handler.active_connections)
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

@app.get("/conversation/{session_id}/history")
async def get_conversation_history(session_id: str):
    """Get conversation message history"""
    try:
        history = await conversation_manager.get_conversation_history(session_id)
        return {"messages": history}
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

@app.websocket("/ws/{session_id}")
async def websocket_endpoint(websocket: WebSocket, session_id: str):
    """WebSocket endpoint for real-time chat"""
    await websocket.accept()
    
    try:
        # Register connection
        websocket_handler.add_connection(session_id, websocket)
        logger.info(f"WebSocket connected for session {session_id}")
        
        while True:
            # Receive message from client
            data = await websocket.receive_text()
            message_data = json.loads(data)
            
            if message_data.get("type") == "message":
                user_message = message_data.get("message", "")
                
                # Stream response back to client
                async for chunk in conversation_manager.process_message(
                    session_id, 
                    user_message
                ):
                    await websocket.send_text(json.dumps({
                        "type": "response_chunk",
                        "chunk": chunk
                    }))
                
                # Send end-of-response marker
                await websocket.send_text(json.dumps({
                    "type": "response_complete"
                }))
                
            elif message_data.get("type") == "ping":
                await websocket.send_text(json.dumps({
                    "type": "pong"
                }))
                
    except WebSocketDisconnect:
        logger.info(f"WebSocket disconnected for session {session_id}")
    except Exception as e:
        logger.error(f"WebSocket error for session {session_id}: {e}")
        await websocket.send_text(json.dumps({
            "type": "error",
            "message": str(e)
        }))
    finally:
        websocket_handler.remove_connection(session_id)

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