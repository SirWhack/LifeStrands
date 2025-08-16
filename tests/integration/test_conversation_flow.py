import asyncio
import pytest
import json
import uuid
from datetime import datetime, timedelta
import websockets
from unittest.mock import AsyncMock, MagicMock
import aiohttp

# Test configuration
TEST_CONFIG = {
    "model_service_url": "http://localhost:8001",
    "chat_service_url": "http://localhost:8002",
    "npc_service_url": "http://localhost:8003",
    "summary_service_url": "http://localhost:8004",
    "gateway_url": "http://localhost:8000",
    "websocket_url": "ws://localhost:8000/ws",
    "test_timeout": 30
}

@pytest.fixture
async def test_npc():
    """Create a test NPC for conversation testing"""
    test_life_strand = {
        "name": "Test Character",
        "background": {
            "age": 25,
            "occupation": "Researcher",
            "location": "City Center"
        },
        "personality": {
            "traits": ["curious", "analytical", "friendly"],
            "motivations": ["seeking knowledge", "helping others"],
            "fears": ["failure", "isolation"]
        },
        "current_status": {
            "mood": "neutral",
            "health": "good",
            "energy": "high"
        },
        "relationships": {},
        "knowledge": [],
        "memories": []
    }
    
    async with aiohttp.ClientSession() as session:
        async with session.post(
            f"{TEST_CONFIG['npc_service_url']}/npcs",
            json=test_life_strand
        ) as response:
            if response.status == 201:
                data = await response.json()
                return data["npc_id"]
            else:
                pytest.fail(f"Failed to create test NPC: {response.status}")

@pytest.fixture
async def websocket_connection():
    """Create WebSocket connection for testing"""
    uri = f"{TEST_CONFIG['websocket_url']}?token=test_token"
    try:
        websocket = await websockets.connect(uri)
        yield websocket
    finally:
        await websocket.close()

class TestConversationFlow:
    """Test full conversation lifecycle"""
    
    @pytest.mark.asyncio
    async def test_full_conversation_cycle(self, test_npc):
        """Test conversation from start to summary application"""
        
        user_id = f"test_user_{uuid.uuid4()}"
        session_id = None
        
        try:
            # Step 1: Start conversation
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{TEST_CONFIG['chat_service_url']}/conversations/start",
                    json={
                        "npc_id": test_npc,
                        "user_id": user_id
                    }
                ) as response:
                    assert response.status == 201
                    data = await response.json()
                    session_id = data["session_id"]
                    assert session_id is not None
            
            # Step 2: Send messages and verify responses
            test_messages = [
                "Hello, how are you today?",
                "What do you do for work?",
                "That sounds interesting! Tell me more about your research.",
                "What motivates you in your work?",
                "Thank you for the conversation. Goodbye!"
            ]
            
            for message in test_messages:
                async with aiohttp.ClientSession() as session:
                    async with session.post(
                        f"{TEST_CONFIG['chat_service_url']}/conversations/{session_id}/message",
                        json={"content": message}
                    ) as response:
                        assert response.status == 200
                        
                        # Verify streaming response
                        response_chunks = []
                        async for chunk in response.content:
                            if chunk:
                                try:
                                    chunk_data = json.loads(chunk.decode())
                                    if "token" in chunk_data:
                                        response_chunks.append(chunk_data["token"])
                                except json.JSONDecodeError:
                                    continue
                        
                        # Verify we got a meaningful response
                        full_response = "".join(response_chunks)
                        assert len(full_response) > 10, "Response too short"
                        
                        # Add delay to simulate real conversation
                        await asyncio.sleep(0.5)
            
            # Step 3: End conversation
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{TEST_CONFIG['chat_service_url']}/conversations/{session_id}/end"
                ) as response:
                    assert response.status == 200
            
            # Step 4: Wait for summary generation
            await asyncio.sleep(5)  # Give time for summary processing
            
            # Step 5: Verify conversation was recorded
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{TEST_CONFIG['chat_service_url']}/conversations/{session_id}/history"
                ) as response:
                    assert response.status == 200
                    history = await response.json()
                    
                    # Verify message count (user + assistant messages)
                    assert len(history) >= len(test_messages) * 2  # Each exchange = 2 messages
                    
                    # Verify message structure
                    for msg in history:
                        assert "role" in msg
                        assert "content" in msg
                        assert "timestamp" in msg
                        assert msg["role"] in ["user", "assistant"]
            
            # Step 6: Check for summary generation
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{TEST_CONFIG['summary_service_url']}/conversations/{session_id}/summary"
                ) as response:
                    if response.status == 200:
                        summary_data = await response.json()
                        assert "summary" in summary_data
                        assert "key_points" in summary_data
                        assert len(summary_data["summary"]) > 0
            
            # Step 7: Verify NPC was updated with conversation memory
            await asyncio.sleep(3)  # Give time for NPC updates
            
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{TEST_CONFIG['npc_service_url']}/npcs/{test_npc}"
                ) as response:
                    assert response.status == 200
                    npc_data = await response.json()
                    
                    # Check if memories were added
                    memories = npc_data.get("memories", [])
                    assert len(memories) > 0, "No memories were added to NPC"
                    
                    # Verify memory structure
                    latest_memory = memories[-1]
                    assert "content" in latest_memory
                    assert "timestamp" in latest_memory
                    
        except Exception as e:
            pytest.fail(f"Full conversation cycle test failed: {str(e)}")
        
        finally:
            # Cleanup: End session if still active
            if session_id:
                try:
                    async with aiohttp.ClientSession() as session:
                        await session.post(
                            f"{TEST_CONFIG['chat_service_url']}/conversations/{session_id}/end"
                        )
                except:
                    pass  # Ignore cleanup errors
    
    @pytest.mark.asyncio
    async def test_model_switching(self):
        """Test hot-swap between chat and summary models"""
        
        try:
            # Step 1: Check initial model status
            async with aiohttp.ClientSession() as session:
                async with session.get(f"{TEST_CONFIG['model_service_url']}/status") as response:
                    assert response.status == 200
                    initial_status = await response.json()
                    initial_model = initial_status.get("current_model_type")
            
            # Step 2: Switch to chat model
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{TEST_CONFIG['model_service_url']}/switch/chat"
                ) as response:
                    assert response.status == 200
            
            # Wait for model switch
            await asyncio.sleep(10)
            
            # Step 3: Verify chat model is loaded
            async with aiohttp.ClientSession() as session:
                async with session.get(f"{TEST_CONFIG['model_service_url']}/status") as response:
                    assert response.status == 200
                    status = await response.json()
                    assert status["current_model_type"] == "chat"
                    assert status["state"] == "loaded"
            
            # Step 4: Test chat generation
            test_prompt = "Hello, how are you?"
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{TEST_CONFIG['model_service_url']}/generate/stream",
                    json={"prompt": test_prompt, "max_tokens": 50}
                ) as response:
                    assert response.status == 200
                    
                    # Verify streaming works
                    tokens_received = 0
                    async for chunk in response.content:
                        if chunk:
                            try:
                                data = json.loads(chunk.decode())
                                if "token" in data:
                                    tokens_received += 1
                            except json.JSONDecodeError:
                                continue
                    
                    assert tokens_received > 0, "No tokens received from chat model"
            
            # Step 5: Switch to summary model
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{TEST_CONFIG['model_service_url']}/switch/summary"
                ) as response:
                    assert response.status == 200
            
            # Wait for model switch
            await asyncio.sleep(10)
            
            # Step 6: Verify summary model is loaded
            async with aiohttp.ClientSession() as session:
                async with session.get(f"{TEST_CONFIG['model_service_url']}/status") as response:
                    assert response.status == 200
                    status = await response.json()
                    assert status["current_model_type"] == "summary"
                    assert status["state"] == "loaded"
            
            # Step 7: Test summary generation
            summary_prompt = "Summarize this conversation: User said hello, AI responded with greeting and asked how they could help."
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{TEST_CONFIG['model_service_url']}/generate/completion",
                    json={"prompt": summary_prompt, "max_tokens": 100}
                ) as response:
                    assert response.status == 200
                    data = await response.json()
                    assert "content" in data
                    assert len(data["content"]) > 10, "Summary too short"
            
        except Exception as e:
            pytest.fail(f"Model switching test failed: {str(e)}")
    
    @pytest.mark.asyncio
    async def test_concurrent_requests(self, test_npc):
        """Test queue handling with multiple concurrent requests"""
        
        user_count = 5
        messages_per_user = 3
        session_ids = []
        
        try:
            # Step 1: Start multiple conversations concurrently
            start_tasks = []
            for i in range(user_count):
                user_id = f"concurrent_user_{i}_{uuid.uuid4()}"
                task = self._start_conversation(test_npc, user_id)
                start_tasks.append(task)
            
            session_ids = await asyncio.gather(*start_tasks)
            assert len(session_ids) == user_count
            assert all(sid is not None for sid in session_ids)
            
            # Step 2: Send messages concurrently from all sessions
            message_tasks = []
            for i, session_id in enumerate(session_ids):
                for j in range(messages_per_user):
                    message = f"Hello from user {i}, message {j+1}"
                    task = self._send_message(session_id, message)
                    message_tasks.append(task)
            
            # Wait for all messages to complete
            results = await asyncio.gather(*message_tasks, return_exceptions=True)
            
            # Verify most messages succeeded (some might timeout under load)
            successful_responses = [r for r in results if not isinstance(r, Exception)]
            success_rate = len(successful_responses) / len(results)
            
            assert success_rate >= 0.8, f"Success rate too low: {success_rate:.2%}"
            
            # Step 3: End all conversations
            end_tasks = [
                self._end_conversation(session_id) 
                for session_id in session_ids
            ]
            
            await asyncio.gather(*end_tasks, return_exceptions=True)
            
            # Step 4: Verify system stability
            async with aiohttp.ClientSession() as session:
                async with session.get(f"{TEST_CONFIG['model_service_url']}/status") as response:
                    assert response.status == 200
                    status = await response.json()
                    assert status["state"] in ["loaded", "idle"]
            
        except Exception as e:
            pytest.fail(f"Concurrent requests test failed: {str(e)}")
        
        finally:
            # Cleanup: End any remaining sessions
            cleanup_tasks = [
                self._end_conversation(session_id) 
                for session_id in session_ids if session_id
            ]
            if cleanup_tasks:
                await asyncio.gather(*cleanup_tasks, return_exceptions=True)
    
    @pytest.mark.asyncio
    async def test_websocket_streaming(self, websocket_connection, test_npc):
        """Test WebSocket streaming functionality"""
        
        try:
            # Step 1: Subscribe to NPC updates
            subscribe_msg = {
                "type": "subscribe_npc",
                "npc_id": test_npc
            }
            await websocket_connection.send(json.dumps(subscribe_msg))
            
            # Wait for subscription confirmation
            response = await websocket_connection.recv()
            response_data = json.loads(response)
            assert response_data["type"] == "subscription_confirmed"
            
            # Step 2: Start conversation via REST API
            user_id = f"ws_test_user_{uuid.uuid4()}"
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{TEST_CONFIG['chat_service_url']}/conversations/start",
                    json={"npc_id": test_npc, "user_id": user_id}
                ) as response:
                    assert response.status == 201
                    data = await response.json()
                    session_id = data["session_id"]
            
            # Step 3: Send message and monitor WebSocket for updates
            message_task = asyncio.create_task(
                self._send_message(session_id, "Hello, can you hear me?")
            )
            
            # Monitor WebSocket for real-time updates
            websocket_messages = []
            timeout_time = datetime.now() + timedelta(seconds=10)
            
            while datetime.now() < timeout_time:
                try:
                    response = await asyncio.wait_for(
                        websocket_connection.recv(), 
                        timeout=1.0
                    )
                    message_data = json.loads(response)
                    websocket_messages.append(message_data)
                    
                    # Look for stream tokens or status updates
                    if message_data.get("type") in ["token", "stream_complete"]:
                        break
                        
                except asyncio.TimeoutError:
                    continue
            
            # Wait for message task to complete
            await message_task
            
            # Verify we received WebSocket updates
            assert len(websocket_messages) > 0, "No WebSocket messages received"
            
            # Check for expected message types
            message_types = [msg.get("type") for msg in websocket_messages]
            assert any(msg_type in ["token", "npc_status_update", "stream_complete"] 
                      for msg_type in message_types), "No relevant WebSocket updates received"
            
            # Step 4: End conversation
            async with aiohttp.ClientSession() as session:
                await session.post(
                    f"{TEST_CONFIG['chat_service_url']}/conversations/{session_id}/end"
                )
            
        except Exception as e:
            pytest.fail(f"WebSocket streaming test failed: {str(e)}")
    
    # Helper methods
    
    async def _start_conversation(self, npc_id: str, user_id: str) -> str:
        """Helper to start a conversation"""
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{TEST_CONFIG['chat_service_url']}/conversations/start",
                json={"npc_id": npc_id, "user_id": user_id}
            ) as response:
                if response.status == 201:
                    data = await response.json()
                    return data["session_id"]
                else:
                    raise Exception(f"Failed to start conversation: {response.status}")
    
    async def _send_message(self, session_id: str, content: str) -> bool:
        """Helper to send a message"""
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{TEST_CONFIG['chat_service_url']}/conversations/{session_id}/message",
                json={"content": content}
            ) as response:
                if response.status == 200:
                    # Consume the streaming response
                    async for chunk in response.content:
                        pass  # Just consume, don't process
                    return True
                else:
                    raise Exception(f"Failed to send message: {response.status}")
    
    async def _end_conversation(self, session_id: str) -> bool:
        """Helper to end a conversation"""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{TEST_CONFIG['chat_service_url']}/conversations/{session_id}/end"
                ) as response:
                    return response.status == 200
        except:
            return False  # Ignore errors during cleanup

# Test configuration and fixtures for pytest

@pytest.fixture(scope="session")
def event_loop():
    """Create an instance of the default event loop for the test session."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()

@pytest.mark.asyncio
async def test_system_health_check():
    """Basic system health check before running integration tests"""
    
    services = [
        ("Model Service", f"{TEST_CONFIG['model_service_url']}/health"),
        ("Chat Service", f"{TEST_CONFIG['chat_service_url']}/health"),
        ("NPC Service", f"{TEST_CONFIG['npc_service_url']}/health"),
        ("Summary Service", f"{TEST_CONFIG['summary_service_url']}/health"),
        ("Gateway", f"{TEST_CONFIG['gateway_url']}/health")
    ]
    
    async with aiohttp.ClientSession() as session:
        for service_name, url in services:
            try:
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=5)) as response:
                    assert response.status == 200, f"{service_name} health check failed"
            except Exception as e:
                pytest.skip(f"{service_name} not available: {str(e)}")