#!/usr/bin/env python3

"""
Simple Chat Service for testing WebSocket connectivity
This is a minimal version to test the frontend WebSocket connection
"""

import json
import asyncio
import logging
from typing import Dict, Any
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Life Strands Chat Service - Simple")

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/health")
async def health():
    return {"status": "healthy", "service": "chat-service-simple"}

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    logger.info("WebSocket connection established")
    
    # Send connection ready message
    await websocket.send_text(json.dumps({
        "type": "connection_ready",
        "message": "WebSocket connected successfully"
    }))
    
    try:
        while True:
            # Receive message from client
            data = await websocket.receive_text()
            logger.info(f"Received: {data}")
            
            try:
                message_data = json.loads(data)
            except json.JSONDecodeError:
                await websocket.send_text(json.dumps({
                    "type": "error",
                    "message": "Invalid message format"
                }))
                continue
            
            if message_data.get("type") == "message":
                # Simulate chat response
                user_message = message_data.get("content", "")
                npc_id = message_data.get("npc_id", "test-npc")
                
                # Send streaming response
                response = f"Hello! You said: '{user_message}'. This is a test response from the simple chat service."
                
                # Simulate streaming by sending chunks
                words = response.split()
                for i, word in enumerate(words):
                    await websocket.send_text(json.dumps({
                        "type": "response_chunk",
                        "chunk": word + " ",
                        "npc_id": npc_id
                    }))
                    await asyncio.sleep(0.1)  # Small delay to simulate streaming
                
                # Send completion message
                await websocket.send_text(json.dumps({
                    "type": "response_complete",
                    "npc_id": npc_id
                }))
                
            elif message_data.get("type") == "ping":
                await websocket.send_text(json.dumps({
                    "type": "pong"
                }))
            
    except WebSocketDisconnect:
        logger.info("WebSocket disconnected")
    except Exception as e:
        logger.error(f"WebSocket error: {e}")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8002)