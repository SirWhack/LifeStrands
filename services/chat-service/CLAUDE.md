# CLAUDE.md - Chat Service

This file provides guidance to Claude Code when working with the Life Strands Chat Service.

## Service Overview

The Chat Service manages real-time conversations between users and NPCs. It orchestrates the conversation flow, builds context for the model service, handles WebSocket connections, and manages conversation sessions.

**Port:** 8002  
**Purpose:** Conversation Management, WebSocket Handling, Context Building  
**Dependencies:** Model Service, NPC Service, Summary Service, Redis

## Architecture

### Core Components

- **ConversationManager** (`src/conversation_manager.py`): Main conversation orchestration
- **ContextBuilder** (`src/context_builder.py`): Builds optimized prompts for LLM
- **StreamHandler** (`src/stream_handler.py`): Manages real-time response streaming  
- **WebSocketHandler** (`src/websocket_handler.py`): WebSocket connection management
- **Main Service** (`main.py`): FastAPI application with WebSocket endpoints

### Conversation Flow

1. **Session Creation**: User initiates conversation with NPC
2. **Context Building**: Life Strand data converted to LLM prompt
3. **Message Processing**: User message added to conversation history
4. **Model Interaction**: Streaming request sent to model service
5. **Response Streaming**: Tokens streamed back to client via WebSocket
6. **Session Management**: Conversation stored and managed in Redis
7. **Summary Queuing**: Completed conversations queued for analysis

## Key Features

### 1. Conversation Sessions

```python
class ConversationSession:
    def __init__(self, session_id: str, npc_id: str, user_id: str):
        self.session_id = session_id
        self.npc_id = npc_id
        self.user_id = user_id
        self.messages: List[Dict[str, Any]] = []
        self.timeout_seconds = 1800  # 30 minutes
```

**Session Management:**
- Unique session IDs for each conversation
- Automatic timeout handling (30-minute default)
- Persistent storage in Redis with 24-hour TTL
- Active session tracking in memory

### 2. Context Building

The ContextBuilder transforms Life Strand data into optimized LLM prompts:

```python
def build_system_prompt(self, npc_data: dict) -> str:
    """Build system prompt from Life Strand data"""
```

**Context Components:**
- **System Prompt**: NPC personality, background, current status
- **Relationship Context**: Existing relationships with user
- **Knowledge Context**: Relevant knowledge and memories
- **Conversation History**: Recent message history
- **Current Situation**: Current mood, location, activity

### 3. Real-time Streaming

```python
async def process_message(self, session_id: str, message: str) -> AsyncGenerator[str, None]:
    """Process user message and stream response"""
```

**Streaming Process:**
- Builds complete context for model service
- Sends streaming request to native model service
- Forwards tokens to WebSocket client in real-time
- Stores complete response in conversation history

### 4. WebSocket Management

- Persistent WebSocket connections for real-time chat
- Connection state tracking and recovery
- Message queuing for offline users
- Automatic reconnection handling

## Context Building Strategy

### System Prompt Structure

```
You are [NPC Name], a [age]-year-old [occupation] living in [location].

PERSONALITY:
- Traits: [personality traits]
- Motivations: [core motivations]
- Current mood: [current emotional state]

BACKGROUND:
[condensed background information]

RELATIONSHIPS:
[relevant relationship information]

CURRENT SITUATION:
[current status, location, activity]

Please respond as this character would, maintaining consistency with their personality and background.
```

### Context Optimization

- **Token Limits**: Respects model context window limits
- **Relevance Filtering**: Only includes relevant memories and knowledge
- **Dynamic Truncation**: Removes oldest messages when context is full
- **Relationship Prioritization**: Emphasizes relationships with current user

## Session Management

### Session Lifecycle

1. **Creation**: `start_conversation(npc_id, user_id)`
2. **Active Phase**: Message exchange and streaming
3. **Timeout Handling**: Automatic cleanup after inactivity
4. **Termination**: `end_conversation(session_id)`
5. **Summary Queuing**: Conversation sent for post-processing

### Redis Integration

```python
# Session storage
await self.redis_client.set(
    f"conversation:{session_id}",
    session_data,
    ex=86400  # 24 hours TTL
)

# Summary queue
await self.redis_client.lpush(
    "summary_queue",
    json.dumps(summary_request)
)
```

### Cleanup and Optimization

- **Periodic Cleanup**: Removes expired sessions every 5 minutes
- **Memory Management**: Active sessions stored in memory for performance
- **Redis Fallback**: Sessions loaded from Redis if not in memory
- **Automatic Timeout**: Sessions expire after 30 minutes of inactivity

## Error Handling

### Common Error Scenarios

1. **Invalid Session**: Session not found or expired
2. **NPC Not Found**: Target NPC doesn't exist
3. **Model Service Unavailable**: Native model service offline
4. **WebSocket Disconnection**: Client connection lost
5. **Context Too Large**: Conversation history exceeds token limits

### Error Recovery

```python
try:
    async for chunk in self._stream_from_model(full_prompt, session_id):
        yield chunk
except Exception as e:
    logger.error(f"Error streaming from model service: {e}")
    yield f"Error: {str(e)}"
```

## Configuration

### Environment Variables

- `MODEL_SERVICE_URL`: URL of native Vulkan model service
- `NPC_SERVICE_URL`: URL of NPC service for Life Strand data
- `REDIS_URL`: Redis connection string
- `MAX_CONCURRENT_CONVERSATIONS`: Concurrent session limit
- `CONVERSATION_TIMEOUT_MINUTES`: Session timeout duration

### Service Dependencies

```python
self.model_service_url = "http://host.docker.internal:8001"  # Native service
self.npc_service_url = "http://localhost:8003"
```

## WebSocket API

### Connection Endpoints

- `ws://localhost:8002/ws/{session_id}` - Main conversation WebSocket
- `ws://localhost:8002/ws/monitor/{user_id}` - User activity monitoring

### Message Format

**Client to Server:**
```json
{
  "type": "message",
  "content": "User message text",
  "metadata": {
    "timestamp": "2024-01-01T12:00:00Z"
  }
}
```

**Server to Client:**
```json
{
  "type": "token",
  "content": "Response token",
  "session_id": "session-uuid"
}
```

### WebSocket Events

- `connection_established`: WebSocket connected
- `session_started`: New conversation session created
- `message_received`: User message received
- `response_streaming`: Model response streaming
- `response_complete`: Complete response received
- `session_ended`: Conversation terminated
- `error`: Error occurred

## Integration Points

### With Model Service

```python
async def _stream_from_model(self, prompt: str, session_id: str):
    """Stream response from native Vulkan model service"""
    payload = {
        "prompt": prompt,
        "session_id": session_id,
        "stream": True,
        "model_type": "chat"
    }
```

**Model Service Integration:**
- Direct communication with native Windows model service
- Streaming response handling
- Model switching support (chat/summary)
- Error propagation and recovery

### With NPC Service

```python
async def _get_npc_data(self, npc_id: str) -> dict:
    """Get Life Strand data for context building"""
```

**NPC Service Integration:**
- Fetches complete Life Strand data
- Validates NPC existence
- Handles NPC updates during conversation
- Retrieves relationship information

### With Summary Service

```python
async def _queue_for_summary(self, session: ConversationSession):
    """Queue completed conversation for analysis"""
```

**Summary Integration:**
- Queues conversations for post-processing
- Provides conversation metadata
- Triggers Life Strand updates
- Handles summary feedback

## Development Guidelines

### Adding New Features

1. **Message Types**: Extend WebSocket message handling
2. **Context Components**: Add new context building elements
3. **Session Metadata**: Extend session tracking
4. **Integration Points**: Add new service dependencies

### Performance Optimization

- **Connection Pooling**: Reuse HTTP connections to services
- **Context Caching**: Cache frequently used NPC data
- **Session Pooling**: Optimize session creation/destruction
- **Memory Management**: Monitor active session memory usage

### Testing

```python
# Unit tests
pytest tests/unit/test_conversation_manager.py

# Integration tests
pytest tests/integration/test_chat_flow.py

# WebSocket tests
pytest tests/integration/test_websocket_handler.py
```

## Common Operations

### Starting a Conversation

```python
session_id = await conversation_manager.start_conversation(
    npc_id="npc-123",
    user_id="user-456"
)
```

### Processing Messages

```python
async for token in conversation_manager.process_message(
    session_id, "Hello, how are you?"
):
    await websocket.send_text(token)
```

### Managing Sessions

```python
# Get active sessions
active = await conversation_manager.get_active_sessions()

# Handle timeout
await conversation_manager.handle_timeout(session_id)

# End conversation
await conversation_manager.end_conversation(session_id)
```

## Monitoring and Debugging

### Key Metrics

- Active conversation count
- Average session duration
- Message processing latency
- WebSocket connection stability
- Model service response times

### Logging

- Session lifecycle events
- Context building decisions
- Model service interactions
- WebSocket connection events
- Error conditions and recovery

### Health Checks

- Service dependency availability
- Redis connection health
- Active session count
- WebSocket connection count
- Memory usage monitoring

## Troubleshooting

### Common Issues

1. **WebSocket Disconnections**
   - Check client connection stability
   - Monitor server resource usage
   - Verify proxy/load balancer configuration

2. **Context Building Errors**
   - Validate NPC data completeness
   - Check token limit calculations
   - Verify Life Strand data format

3. **Model Service Timeouts**
   - Check native model service health
   - Monitor GPU memory usage
   - Verify network connectivity

4. **Session Management Issues**
   - Check Redis connectivity
   - Monitor session cleanup timing
   - Verify session data serialization

### Debug Commands

```bash
# Check service health
curl http://localhost:8002/health

# Monitor active sessions
curl http://localhost:8002/sessions/active

# Check Redis connection
curl http://localhost:8002/debug/redis

# WebSocket connection test
wscat -c ws://localhost:8002/ws/test-session
```