# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Life Strands is a sophisticated AI-driven conversation system that enables dynamic, persistent interactions with NPCs using Large Language Models. Each NPC has a comprehensive "Life Strand" - a rich data structure containing their personality, memories, relationships, and knowledge that evolves through conversations.

## Architecture

The system uses a microservices architecture with these core services:

- **Gateway Service** (port 8000): API gateway, authentication, routing
- **Model Service** (port 8001): LLM management, GPU orchestration, hot-swapping
- **Chat Service** (port 8002): Conversation management, WebSocket handling
- **NPC Service** (port 8003): Life Strand CRUD, vector search with pgvector
- **Summary Service** (port 8004): Post-conversation analysis and NPC updates
- **Monitor Service** (port 8005): System health monitoring and alerts

Supporting infrastructure:
- **PostgreSQL** with pgvector extension for semantic search
- **Redis** for queuing, caching, and real-time communication
- **React frontends**: Chat interface (port 3001) and admin dashboard (port 3002)

## Common Development Commands

### Starting the System

**From WSL/Linux:**
```bash
make dev-up              # Start all services (Docker + Native Windows Model in new terminal)
make dev-down            # Stop all services (Docker + Native Windows Model)
make dev-restart         # Restart all services
make model-start-native  # Start only the model service in new terminal
make model-stop-native   # Stop only the model service
```

**From Windows (PowerShell/Command Prompt):**
```powershell
.\dev.ps1 dev-up         # Start all services (recommended)
.\dev.ps1 dev-down       # Stop all services
.\dev.ps1 status         # Check service status
.\dev.ps1 health         # Health check all services

# OR using batch file:
dev.bat dev-up           # Start all services
dev.bat dev-down         # Stop all services
```

### Testing
```bash
make test                # Run full test suite (unit + integration + load)
make test-unit           # Run unit tests only
make test-integration    # Run integration tests only
make test-coverage       # Run tests with coverage report
```

### Database Operations
```bash
make migrate             # Run database migrations
make seed                # Seed database with test NPCs
make backup              # Backup database and Redis
make psql                # Connect to PostgreSQL
```

### Model Management
```bash
make model-status        # Check current model status and VRAM usage
make model-switch type=chat    # Switch to chat model
make model-switch type=summary # Switch to summary model
make model-reload        # Force model reload
make model-unload        # Unload current model to free VRAM
```

### Monitoring & Debugging
```bash
make health-check        # Check all service health
make logs                # View logs from all services
make logs s=model        # View logs from specific service
make monitor             # Open Grafana monitoring dashboard
make reset-queues        # Clear Redis queues
```

### Frontend Development
```bash
# Chat interface
cd frontends/chat-interface
npm run dev              # Start development server
npm run build            # Build for production
npm run lint             # Run ESLint
npm run type-check       # TypeScript type checking

# Admin dashboard
cd frontends/admin-dashboard
npm run dev              # Start development server
npm run build            # Build for production
npm run lint             # Run ESLint
npm run type-check       # TypeScript type checking
```

## Code Architecture

### Life Strand Data Structure
Central to the system is the Life Strand schema defined in `services/npc-service/src/life_strand_schema.py`. Life Strands contain:
- **Background**: Age, occupation, location, history, family, education
- **Personality**: Traits, motivations, fears, values, quirks
- **Current Status**: Mood, health, energy, current location, activity
- **Relationships**: Type, status, intensity, notes, history with other entities
- **Knowledge**: Topic-based information with confidence scores
- **Memories**: Conversation memories with importance and emotional impact

### Model Hot-Swapping
The Model Service implements sophisticated GPU memory management in `services/model-service/src/model_manager.py`. Key features:
- **State Machine**: Tracks model states (idle, loading, loaded, generating, unloading, error)
- **Memory Monitoring**: Predicts VRAM requirements before loading
- **Hot-Swapping**: Seamlessly switches between chat and summary models based on demand
- **GGUF Support**: Uses llama.cpp for efficient GGUF model inference

### Conversation Flow
1. **Chat Service** receives user message via WebSocket
2. **Context Builder** converts Life Strand to optimized LLM prompt
3. **Model Service** generates streaming response
4. **Stream Handler** forwards tokens to WebSocket in real-time
5. **Summary Service** processes completed conversations asynchronously
6. **Change Extractor** identifies potential Life Strand updates
7. **Memory Updater** applies approved changes to NPC data

### Vector Search
NPCs support semantic similarity search via pgvector:
- **Embedding Generation**: Life Strand content vectorized for search
- **Similarity Queries**: Find NPCs with similar personalities
- **Memory Search**: Semantic search within NPC memories and knowledge

## Key Implementation Details

### Native Windows Model Service
The Model Service runs **natively on Windows** (not in Docker) for optimal GPU performance:
- **Vulkan Acceleration**: Uses AMD 7900 XTX with Vulkan drivers (NOT ROCm)
- **Direct GPU Access**: Bypasses Docker overhead for maximum performance
- **Native Integration**: Docker services connect via `host.docker.internal:8001`
- **Memory Efficiency**: `use_mmap: False` prevents CPU RAM duplication
- **24B Model Support**: Handles large models like Gryphe_Codex-24B-Small-3.2-Q6_K_L.gguf

### WebSocket Management
Both chat and monitoring use WebSocket connections with auto-reconnect:
- **Chat WebSocket** (`frontends/chat-interface/src/hooks/useWebSocket.ts`): Real-time conversation
- **Monitor WebSocket** (`services/monitor-service/src/websocket_broadcaster.py`): System metrics broadcasting

### Queue-Based Processing
Redis queues handle asynchronous operations:
- **Summary Queue**: Post-conversation analysis
- **Memory Update Queue**: Life Strand modifications
- **Alert Queue**: System monitoring alerts

### Authentication & Authorization
JWT-based auth with role-based access control in `services/gateway-service/src/auth.py`.

### Rate Limiting
Configurable rate limiting in `services/gateway-service/src/rate_limiter.py` for API protection.

### Data Validation and Schema Management
The Life Strand schema uses comprehensive validation in `services/npc-service/src/life_strand_schema.py`:
- **JSON Schema Validation**: Enforces data structure and types
- **Custom Business Rules**: Age consistency, relationship intensity ranges
- **Data Sanitization**: Truncates long fields, limits array sizes
- **Schema Migration**: Version-aware data migration support
- **Intelligent Merging**: Handles conversation updates without data loss

### Context Building Strategy
The Chat Service uses `services/chat-service/src/context_builder.py` to convert Life Strands into optimized prompts:
- **Token Management**: Respects context window limits (8192 tokens default)
- **Relevance Filtering**: Prioritizes recent memories and relationships
- **Dynamic Truncation**: Removes oldest context when limits are reached
- **Personality Emphasis**: Highlights core traits and motivations

## Testing Strategy

- **Unit Tests**: Focus on individual components like context building and Life Strand validation
- **Integration Tests**: Full conversation flows including model switching
- **Load Tests**: Concurrent conversations and memory stability during hot-swapping

Test files located in `tests/` with subdirectories for `unit/`, `integration/`, and `load/` testing.

### Running Specific Tests
```bash
# Run specific test file
pytest tests/unit/test_context_builder.py -v

# Run tests with specific markers
pytest tests/integration/ -v -m "not slow"

# Run with coverage for specific service
pytest tests/unit/test_life_strand_schema.py --cov=services/npc-service
```

## Development Environment

### Docker Compose Profiles
The system uses multiple Docker Compose profiles for different scenarios:
- **Default**: Core services (gateway, chat, npc, summary, monitor)
- **dev-tools**: Adds pgAdmin and Redis Commander for development
- **monitoring**: Adds Grafana, Prometheus, and Jaeger
- **frontend**: React applications for chat interface and admin dashboard

### Environment Configuration
Key environment variables (configured via `.env`):
- `CHAT_MODEL`: Filename of chat model (e.g., Gryphe_Codex-24B-Small-3.2-Q6_K_L.gguf)
- `SUMMARY_MODEL`: Filename of summary model
- `EMBEDDING_MODEL`: Filename of embedding model
- `ENABLE_EMBEDDINGS`: Enable/disable embedding generation for search
- `MIN_VRAM_MB`: Minimum VRAM required for model loading

### Model Files Organization
Models are stored in the `Models/` directory:
- **Chat Models**: Large context models for conversations (24B parameters recommended)
- **Summary Models**: Efficient models for conversation analysis
- **Embedding Models**: Small models for vector generation (384-dimension)

## Service-Specific Details

### Model Service (`services/model-service/`)
- **State Machine**: `src/state_machine.py` tracks model loading states
- **Memory Monitor**: `src/memory_monitor.py` prevents VRAM exhaustion
- **Llama Wrapper**: `src/llama_wrapper.py` interfaces with llama.cpp
- **Threading**: Uses thread pools for non-blocking token generation

### NPC Service (`services/npc-service/`)
- **Life Strand Schema**: `src/life_strand_schema.py` defines data structure
- **Repository Pattern**: `src/npc_repository.py` handles database operations
- **Embedding Manager**: `src/embedding_manager.py` manages vector search
- **pgvector Integration**: Uses PostgreSQL extension for similarity search

### Chat Service (`services/chat-service/`)
- **Session Management**: 30-minute timeout, Redis persistence
- **Context Building**: Optimizes prompts for token efficiency
- **Streaming**: Real-time token forwarding via WebSocket
- **Conversation History**: Automatic truncation and relevance filtering

### Summary Service (`services/summary-service/`)
- **Queue Consumer**: Processes conversations asynchronously
- **Change Extraction**: Identifies personality/relationship updates
- **Memory Updates**: Applies changes to Life Strand data
- **Auto-Approval**: Configurable confidence threshold for automatic updates

## Development Notes

- All services use FastAPI with async/await patterns
- Frontend built with React 18 + TypeScript + Vite + Material-UI
- Database migrations in `database/migrations/`
- Docker Compose with development, monitoring, and frontend profiles
- Structured logging with JSON format for production
- GPU memory monitoring prevents VRAM exhaustion during model operations

### Code Style and Patterns
- **Async/Await**: All I/O operations use async patterns
- **Dependency Injection**: Services configured via environment variables
- **Error Handling**: Graceful degradation with fallback strategies
- **Logging**: Structured JSON logging with contextual information
- **Type Hints**: Python services use comprehensive type annotations

### Performance Considerations
- **Connection Pooling**: Database and Redis connections are pooled
- **Batch Processing**: Embedding generation and database operations are batched
- **Caching**: Frequent NPC data cached in Redis with TTL
- **Memory Management**: Model service automatically manages GPU memory
- **Context Optimization**: Chat service optimizes prompt size for model efficiency