# Life Strands System

A sophisticated AI-driven conversation system that enables dynamic, persistent interactions with NPCs (Non-Player Characters) using Large Language Models. Each NPC has a comprehensive "Life Strand" - a rich data structure containing their personality, memories, relationships, and knowledge that evolves through conversations.

## 🌟 Features

### Core Capabilities
- **Dynamic NPC Personalities**: Rich Life Strand data structures containing background, personality traits, memories, relationships, and knowledge
- **Real-time Conversations**: WebSocket-based streaming conversations with instant token-by-token responses  
- **Hot-swappable Models**: Seamless switching between chat and summary models based on GPU memory availability
- **Persistent Memory**: Conversations automatically generate summaries and update NPC Life Strands
- **Vector Search**: Semantic similarity search for NPCs, memories, and knowledge using pgvector
- **Microservices Architecture**: Scalable, distributed system with independent services

### Advanced Features
- **Conversation Analysis**: AI-powered extraction of personality changes, relationship updates, and learned information
- **Memory Management**: Intelligent pruning and prioritization of NPC memories
- **Real-time Monitoring**: Comprehensive system health monitoring with alerts
- **Rate Limiting**: Protection against abuse with configurable rate limits
- **Authentication**: JWT-based authentication with role-based access control

## 🏗️ System Architecture

```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   Chat UI       │    │  Admin Panel    │    │   Monitoring    │
│  (Frontend)     │    │  (Frontend)     │    │  (Grafana)      │
└─────────┬───────┘    └─────────┬───────┘    └─────────┬───────┘
          │                      │                      │
          └──────────────────────┼──────────────────────┘
                                 │
                    ┌─────────────┴──────────────┐
                    │     Gateway Service        │
                    │  (API Gateway/Auth)        │
                    └─────────────┬──────────────┘
                                 │
        ┌────────────┬────────────┼────────────┬────────────┐
        │            │            │            │            │
┌───────▼──┐  ┌──────▼──┐  ┌──────▼──┐  ┌──────▼──┐  ┌──────▼──┐
│  Model   │  │  Chat   │  │   NPC   │  │Summary  │  │Monitor  │
│ Service  │  │Service  │  │Service  │  │Service  │  │Service  │
│(GPU/LLM) │  │(Convs)  │  │(NPCs)   │  │(Analysis│  │(Health) │
└───────┬──┘  └──────┬──┘  └──────┬──┘  └──────┬──┘  └──────┬──┘
        │            │            │            │            │
        └────────────┴────────────┼────────────┴────────────┘
                                 │
               ┌─────────────────┼─────────────────┐
               │                                  │
        ┌──────▼────┐                    ┌────────▼────┐
        │PostgreSQL │                    │    Redis    │
        │(+pgvector)│                    │(Queue/Cache)│
        └───────────┘                    └─────────────┘
```

### Services Overview

| Service | Port | Purpose |
|---------|------|---------|
| **Gateway** | 8000 | API gateway, authentication, routing |
| **Model Service** | 8001 | LLM management, GPU orchestration |
| **Chat Service** | 8002 | Conversation management, WebSocket handling |
| **NPC Service** | 8003 | Life Strand CRUD, vector search |
| **Summary Service** | 8004 | Post-conversation analysis and updates |
| **Monitor Service** | 8005 | System health monitoring and alerts |

## 🚀 Quick Start

### Prerequisites
- **Docker & Docker Compose** (recommended)
- **Python 3.9+** (for local development)
- **PostgreSQL 15+** with pgvector extension
- **Redis 7+**
- **8GB+ GPU VRAM** (for local LLM inference)
- **GGUF model files** (e.g., Llama 2, CodeLlama, Mistral)

### Option 1: Docker Compose (Recommended)

1. **Clone and setup:**
   ```bash
   git clone <repository-url>
   cd life-strands-v2
   cp .env.example .env
   # Edit .env with your configuration
   ```

2. **Download model files:**
   ```bash
   mkdir -p models
   # Download GGUF model files to the models/ directory
   # Example: llama-2-7b-chat.Q4_K_M.gguf
   ```

3. **Start the system:**
   ```bash
   make dev-up
   # Or: docker-compose --profile dev-tools --profile monitoring up -d
   ```

4. **Access the services:**
   - **API Gateway**: http://localhost:8000
   - **Chat Interface**: http://localhost:3001
   - **Admin Dashboard**: http://localhost:3002  
   - **Grafana Monitoring**: http://localhost:3000
   - **Database Admin**: http://localhost:8080

### Option 2: Local Development

1. **Setup Python environment:**
   ```bash
   python -m venv venv
   source venv/bin/activate  # or `venv\Scripts\activate` on Windows
   pip install -r requirements.txt
   ```

2. **Setup databases:**
   ```bash
   # Start PostgreSQL and Redis
   docker run -d --name postgres -p 5432:5432 -e POSTGRES_PASSWORD=password pgvector/pgvector:pg15
   docker run -d --name redis -p 6379:6379 redis:7-alpine
   
   # Run migrations
   make migrate
   ```

3. **Start services manually:**
   ```bash
   # Terminal 1 - Model Service
   cd services/model-service
   python -m uvicorn src.main:app --host 0.0.0.0 --port 8001
   
   # Terminal 2 - Chat Service  
   cd services/chat-service
   python -m uvicorn src.main:app --host 0.0.0.0 --port 8002
   
   # ... (repeat for other services)
   ```

## 📖 Usage Guide

### Creating an NPC

```python
life_strand = {
    "name": "Elena Rodriguez",
    "background": {
        "age": 32,
        "occupation": "Marine Biologist",
        "location": "Coastal Research Station",
        "history": "Grew up by the ocean, fascinated by marine life..."
    },
    "personality": {
        "traits": ["curious", "methodical", "passionate", "introverted"],
        "motivations": ["ocean conservation", "scientific discovery"],
        "fears": ["climate change impact", "funding cuts"]
    },
    "current_status": {
        "mood": "focused",
        "health": "good", 
        "energy": "high"
    },
    "relationships": {},
    "knowledge": [],
    "memories": []
}

# Create NPC via API
response = requests.post("http://localhost:8000/api/npcs", json=life_strand)
npc_id = response.json()["npc_id"]
```

### Starting a Conversation

```python
# Start conversation
response = requests.post("http://localhost:8000/api/conversations/start", json={
    "npc_id": npc_id,
    "user_id": "user123"
})
session_id = response.json()["session_id"]

# Send message with streaming response
response = requests.post(f"http://localhost:8000/api/conversations/{session_id}/message", 
                        json={"content": "Tell me about your research"}, 
                        stream=True)

for chunk in response.iter_lines():
    if chunk:
        data = json.loads(chunk)
        if "token" in data:
            print(data["token"], end="")
```

### WebSocket Connection

```javascript
const ws = new WebSocket('ws://localhost:8000/ws');

// Subscribe to NPC updates
ws.send(JSON.stringify({
    type: 'subscribe_npc',
    npc_id: 'your-npc-id'
}));

// Listen for real-time updates
ws.onmessage = (event) => {
    const data = JSON.parse(event.data);
    
    if (data.type === 'token') {
        displayToken(data.content);
    } else if (data.type === 'npc_status_update') {
        updateNPCStatus(data.status);
    }
};
```

## 🛠️ Development Commands

The system includes a comprehensive Makefile with common development commands:

```bash
# Development
make dev-up          # Start development environment
make dev-down        # Stop all services
make logs            # View logs from all services
make logs s=model    # View logs from specific service

# Testing
make test            # Run full test suite
make test-unit       # Run unit tests only
make test-integration # Run integration tests

# Database
make migrate         # Run database migrations
make seed            # Seed with test data
make backup          # Create backup
make restore file=backup.sql  # Restore from backup

# Model Management
make model-status    # Check current model status
make model-switch type=chat   # Switch to chat model
make model-reload    # Reload current model

# Health & Monitoring
make health-check    # Check all service health
make monitor         # Open monitoring dashboard

# Maintenance
make clean          # Clean Docker resources
make reset-queues   # Clear Redis queues
```

## ⚙️ Configuration

### Environment Variables

Key configuration options in `.env`:

```bash
# Models
CHAT_MODEL=llama-2-7b-chat.Q4_K_M.gguf
SUMMARY_MODEL=llama-2-7b-instruct.Q4_K_M.gguf
MIN_VRAM_MB=8000

# Database
DATABASE_URL=postgresql://user:pass@localhost/lifestrands
REDIS_URL=redis://localhost:6379

# Features
ENABLE_EMBEDDINGS=true
ENABLE_AUTO_SUMMARIES=true
SUMMARY_AUTO_APPROVAL_THRESHOLD=0.8

# Performance
MAX_CONCURRENT_CONVERSATIONS=50
CONVERSATION_TIMEOUT_MINUTES=30
MEMORY_MAX_PER_NPC=50
```

### Model Requirements

Recommended GGUF models:
- **Chat Models**: Llama 2 7B/13B, CodeLlama, Mistral 7B
- **Summary Models**: Llama 2 7B Instruct, Mistral 7B Instruct
- **Quantization**: Q4_K_M for good balance of quality/speed
- **VRAM**: 8GB minimum, 16GB+ recommended

## 🧪 Testing

### Running Tests

```bash
# All tests
make test

# Specific test categories
make test-unit           # Unit tests
make test-integration    # Integration tests  
make test-load          # Load/stress tests

# With coverage
make test-coverage
```

### Test Structure

```
tests/
├── integration/
│   ├── test_conversation_flow.py  # Full conversation lifecycle
│   ├── test_model_switching.py    # Model hot-swapping
│   └── test_websocket_streaming.py
├── unit/
│   ├── test_context_builder.py    # Prompt building logic
│   ├── test_life_strand_schema.py # Data validation  
│   └── test_memory_monitor.py     # Resource monitoring
└── load/
    ├── test_concurrent_conversations.py
    └── test_system_load.py
```

## 📊 Monitoring & Observability

### Built-in Monitoring

- **Health Endpoints**: All services expose `/health` endpoints
- **Metrics Collection**: Prometheus-compatible metrics 
- **Real-time Dashboards**: Pre-configured Grafana dashboards
- **Distributed Tracing**: OpenTelemetry integration (optional)
- **Log Aggregation**: Structured JSON logging

### Key Metrics

- **Model Service**: GPU utilization, VRAM usage, token generation speed
- **Chat Service**: Active conversations, response times, WebSocket connections
- **Database**: Query performance, connection pool status, vector search latency
- **System**: CPU/memory usage, disk space, network I/O

### Alerts

Configurable alerts for:
- High GPU temperature/memory usage
- Failed model switches
- Database connection issues
- Conversation timeouts
- Queue backlogs

## 🔧 Troubleshooting

### Common Issues

**Model fails to load:**
```bash
# Check GPU availability and VRAM
make model-status

# Check model file exists and permissions
ls -la models/

# View detailed logs
make logs s=model
```

**Conversations not responding:**
```bash
# Check service health
make health-check

# Verify model is loaded
curl http://localhost:8001/status

# Check Redis connectivity
make redis-cli
```

**Database connection issues:**
```bash
# Check PostgreSQL status
make psql

# Run migrations
make migrate

# Check connection pool
curl http://localhost:8003/health
```

**High memory usage:**
```bash
# Monitor system resources
make monitor

# Clear model cache
make model-reload

# Restart services
make dev-restart
```

## 🚀 Production Deployment

### Production Checklist

- [ ] Set strong JWT secret and database passwords
- [ ] Configure SSL/TLS certificates
- [ ] Set up backup automation
- [ ] Configure external monitoring/alerting
- [ ] Review rate limiting settings
- [ ] Set up log rotation
- [ ] Configure firewall rules
- [ ] Set resource limits

### Docker Production

```bash
# Build production images
make prod-build

# Deploy with production config
make prod-deploy

# Monitor production health
make health-check
```

### Scaling Considerations

- **Horizontal Scaling**: Most services can run multiple instances behind load balancer
- **Database**: Consider read replicas for heavy read workloads
- **Model Service**: Typically single instance due to GPU constraints
- **Redis**: Use Redis Cluster for high availability
- **Storage**: Ensure adequate disk space for logs and database

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch: `git checkout -b feature/amazing-feature`
3. Make your changes and add tests
4. Run the test suite: `make test`
5. Commit your changes: `git commit -m 'Add amazing feature'`
6. Push to the branch: `git push origin feature/amazing-feature`  
7. Open a Pull Request

### Development Guidelines

- Follow PEP 8 style guide
- Write comprehensive tests
- Update documentation for new features
- Use conventional commit messages
- Ensure all CI checks pass

## 📋 Roadmap

### Upcoming Features

- **Multimodal Support**: Image and voice input for conversations
- **Advanced Emotions**: More sophisticated emotional modeling
- **Group Conversations**: Multi-NPC conversations
- **World Simulation**: Environmental effects on NPC behavior
- **Plugin System**: Custom conversation behaviors
- **Mobile Apps**: iOS/Android native applications
- **Voice Integration**: Text-to-speech and speech-to-text

### Performance Improvements

- **Model Quantization**: INT8/INT4 quantization for better performance  
- **Caching Layer**: Intelligent response caching
- **Database Optimization**: Query optimization and indexing
- **Edge Deployment**: Support for edge computing scenarios

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 🙏 Acknowledgments

- **Llama.cpp**: Efficient LLM inference engine
- **pgvector**: PostgreSQL vector similarity search
- **FastAPI**: Modern, fast web framework for Python
- **Docker**: Containerization platform
- **The open-source AI community**: For making this possible

## 📞 Support

- **Issues**: [GitHub Issues](https://github.com/your-org/life-strands/issues)
- **Discussions**: [GitHub Discussions](https://github.com/your-org/life-strands/discussions)
- **Documentation**: [Full Documentation](https://docs.life-strands.ai)
- **Discord**: [Community Discord](https://discord.gg/life-strands)

---

**Life Strands System** - Bringing AI characters to life through persistent, meaningful conversations. 🌟