# CLAUDE.md - Model Service

This file provides guidance to Claude Code when working with the Life Strands Model Service.

## Service Overview

The Model Service provides LLM inference for the Life Strands system. It can run in two modes:

1. **GPU Mode**: Real GPU-accelerated inference using native Windows with Vulkan acceleration
2. **Mock Mode**: Lightweight testing mode with canned responses (no GPU required)

**Port:** 8001  
**Purpose:** LLM Inference, Model Management, Testing Support  
**Dependencies:** 
- GPU Mode: Native Windows, Vulkan GPU Drivers, GGUF Models
- Mock Mode: Python runtime only
**Runtime:** Native Windows (GPU mode) or any platform (Mock mode)

## Architecture

### Core Components

**GPU Mode:**
- **ModelManager** (`src/model_manager.py`): Model lifecycle and GPU memory management
- **LlamaWrapper** (`src/llama_wrapper.py`): llama-cpp-python interface with Vulkan support
- **MemoryMonitor** (`src/memory_monitor.py`): GPU VRAM and system memory monitoring
- **StateMachine** (`src/state_machine.py`): Model state tracking and transitions

**Mock Mode:**
- **MockModelService** (`src/mock_model_service.py`): Lightweight service with canned responses
- **MockModelManager** (`src/mock_model_service.py`): Drop-in replacement for ModelManager

**Shared:**
- **Main Service** (`main.py`): FastAPI application with automatic mode detection

### GPU Acceleration

**Technology Stack:**
- **Vulkan**: Primary GPU acceleration (NOT ROCm)
- **llama-cpp-python**: Compiled with `CMAKE_ARGS="-DGGML_VULKAN=ON"`
- **AMD 7900 XTX**: Target GPU hardware
- **GGUF Models**: Quantized model format for efficient inference

**Model Storage:**
- All models in `/Models/` directory
- Chat Model: `Gryphe_Codex-24B-Small-3.2-Q6_K_L.gguf` (24B parameters)
- Summary Model: `dphn.Dolphin-Mistral-24B-Venice-Edition.Q6_K.gguf`
- Embedding Model: `all-MiniLM-L6-v2.F32.gguf`

## Model Management

### State Machine

```python
class ModelState(Enum):
    IDLE = "idle"           # No model loaded
    LOADING = "loading"     # Model being loaded
    LOADED = "loaded"       # Model ready for inference
    GENERATING = "generating"  # Currently processing request
    UNLOADING = "unloading"   # Model being unloaded
    ERROR = "error"         # Error state
```

### Memory Management

**VRAM Usage (24B Model):**
- Model weights: ~18GB
- KV cache: ~1.3GB  
- Compute buffers: ~0.6GB
- **Total GPU usage**: ~20GB

**Optimizations:**
- `use_mmap: False` - Prevents CPU RAM duplication
- All 41 layers offloaded to GPU
- Efficient memory mapping for large models
- Automatic garbage collection on model unload

### Hot-Swapping

```python
async def load_model(self, model_type: str) -> bool:
    """Hot-swap between chat and summary models"""
```

**Features:**
- Seamless switching between model types
- Memory pre-validation before loading
- Automatic unloading of previous model
- State preservation during switches

### Mock Mode Architecture

**Mock Service Features:**
- **Canned Responses**: Realistic pre-written responses for different model types
- **Contextual Selection**: Different response sets for chat, summary, and NPC interactions
- **Realistic Timing**: Simulates token streaming at configurable speeds
- **Memory Simulation**: Mock VRAM usage and model state tracking
- **Deterministic Embeddings**: Consistent vector embeddings based on text content

**Response Sets:**
- **Chat Responses**: General conversational replies
- **Summary Responses**: Analysis and summarization outputs
- **NPC Responses**: Fantasy/medieval character dialogue

**Mock Configuration:**
```python
# Available mock models
mock_models = {
    "chat": {"name": "Mock Chat Model", "vram": 18000},
    "summary": {"name": "Mock Summary Model", "vram": 8000}, 
    "embedding": {"name": "Mock Embedding Model", "vram": 500}
}
```

## Configuration

### Model Configurations

```python
# Windows Vulkan optimizations
self.model_configs = {
    "chat": {
        "path": "Models/Gryphe_Codex-24B-Small-3.2-Q6_K_L.gguf",
        "n_ctx": 8192,
        "n_batch": 1024,
        "n_gpu_layers": -1,  # All layers on GPU
        "use_mmap": False,   # Prevent RAM duplication
        "f16_kv": True,      # FP16 key-value cache
        "verbose": True
    }
}
```

### Environment Variables

- `MODELS_PATH`: Path to GGUF model files
- `CHAT_MODEL`: Chat model filename
- `SUMMARY_MODEL`: Summary model filename
- `EMBEDDING_MODEL`: Embedding model filename
- `CHAT_CONTEXT_SIZE`: Context window size (default: 8192)
- `VULKAN_SDK`: Vulkan SDK path (auto-detected)

## API Endpoints

### Core Generation

```python
POST /generate
{
    "prompt": "Your prompt here",
    "model_type": "chat",
    "max_tokens": 512,
    "temperature": 0.7,
    "stream": true
}
```

**Response:** Server-Sent Events stream or complete JSON response

### Model Management

```python
# Load specific model
POST /load-model
{"model_type": "chat"}

# Switch model
POST /switch/{model_type}

# Unload current model
POST /unload-model

# Emergency cleanup
POST /emergency-shutdown
```

### Status and Monitoring

```python
# Detailed status
GET /status

# Health check
GET /health

# VRAM monitoring
GET /vram

# Service metrics
GET /metrics
```

### Embeddings

```python
POST /embeddings
{
    "texts": ["Text to embed", "Another text"]
}
```

### Mock Mode Endpoints

**Additional endpoints available in mock mode:**

```python
# Get mock service information
GET /mock-info

# Configure mock behavior
POST /mock-config
{
    "generation_speed": 35,    # tokens per second
    "mock_vram_usage": 15000   # MB
}

# Get mock statistics
GET /mock-stats
```

**Mock Response Format:**
All responses include `"mock_mode": true` to identify test mode.

## Streaming Implementation

### Thread Pool Architecture

```python
async def generate_tokens(self, prompt: str, **kwargs) -> AsyncGenerator[str, None]:
    """Generate tokens without blocking event loop"""
```

**Implementation:**
- Worker thread handles llama.cpp generation
- AsyncIO queue for thread-safe token passing
- Non-blocking event loop operation
- Proper error propagation from worker thread

### Server-Sent Events

```python
# Correct SSE format
Content-Type: text/event-stream

data: token_content

data: [DONE]

```

## Performance Optimization

### GPU Utilization

```
Model Performance (24B Q6_K):
- Generation Speed: 38+ tokens/second
- Prompt Processing: 18+ tokens/second
- VRAM Usage: ~20GB total
- All layers on Vulkan GPU
```

### Memory Efficiency

- **No CPU RAM duplication**: Fixed memory mapping issue
- **Optimized batching**: 1024 batch size for throughput
- **Efficient KV cache**: FP16 precision for memory savings
- **Dynamic unloading**: Free VRAM when switching models

### Context Management

- **Window Sliding**: Automatic context truncation
- **Token Counting**: Accurate token limit enforcement
- **Relevance Filtering**: Keep most important context
- **Batch Processing**: Efficient prompt evaluation

## Error Handling

### Import Safety

```python
# Optional dependencies with fallbacks
try:
    import redis.asyncio as redis
    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False
    logger.warning("Redis not available - continuing without Redis support")
```

### Model Loading Errors

- **File not found**: Verify model path and filename
- **Insufficient VRAM**: Check available GPU memory
- **Vulkan errors**: Verify driver installation
- **Quantization issues**: Ensure GGUF format compatibility

### Generation Errors

- **Context overflow**: Automatic truncation and retry
- **GPU OOM**: Model unloading and reload
- **Vulkan failures**: Fallback error handling
- **Timeout handling**: Request abortion and cleanup

## Development Guidelines

### Building llama-cpp-python

```bash
# Vulkan compilation
set CMAKE_ARGS=-DGGML_VULKAN=ON
pip install llama-cpp-python --force-reinstall --no-cache-dir --verbose
```

### Testing Setup

```python
# Test Vulkan functionality
python services/model-service/scripts/test_vulkan_setup.py

# Test model loading
curl -X POST http://localhost:8001/load-model \
  -H "Content-Type: application/json" \
  -d '{"model_type":"chat"}'
```

### Performance Monitoring

```python
# Monitor VRAM usage
GET /vram

# Model state tracking
GET /status

# Generation metrics
llama_perf_context_print output
```

## Integration Points

### With Chat Service

```python
# Streaming generation request
POST /generate
{
    "prompt": "Built context from chat service",
    "stream": true,
    "model_type": "chat"
}
```

### With Summary Service

```python
# Summary generation
POST /generate
{
    "prompt": "Conversation analysis prompt",
    "stream": false,
    "model_type": "summary",
    "max_tokens": 1024
}
```

### With NPC Service

```python
# Embedding generation
POST /embeddings
{
    "texts": ["Life Strand content for similarity search"]
}
```

## Startup Process

### GPU Mode (Native Windows Execution)

```bash
# 1. Navigate to scripts directory
cd services\model-service\scripts

# 2. Start with Vulkan optimization
.\start_vulkan_model_service.bat
```

**GPU Startup Sequence:**
1. Activate `rocm_env` virtual environment
2. Set Vulkan environment variables
3. Configure model paths and settings
4. Initialize ModelManager
5. Check GPU availability
6. Start FastAPI server on port 8001

### Mock Mode (Any Platform)

```bash
# Option 1: Use dedicated mock scripts
cd services\model-service\scripts
.\start_mock_model_service.bat        # Windows batch
.\start_mock_model_service.ps1        # PowerShell

# Option 2: Use environment variable
set MOCK_MODE=true
python main.py

# Option 3: Run mock service directly
python main_mock.py
```

**Mock Startup Sequence:**
1. Set `MOCK_MODE=true` environment variable
2. Initialize MockModelManager
3. Load default mock chat model
4. Start FastAPI server on port 8001

### Mode Selection

The service automatically detects mode based on the `MOCK_MODE` environment variable:

```bash
# GPU Mode (default)
MOCK_MODE=false  # or unset
python main.py

# Mock Mode
MOCK_MODE=true
python main.py
```

### Docker Integration

**GPU Mode:** Model service runs NATIVELY on Windows, not in Docker:
- Docker services connect via `host.docker.internal:8001`
- Optimal GPU performance with native Vulkan drivers
- Direct access to Windows Vulkan runtime
- No Docker GPU passthrough complexity

**Mock Mode:** Can run anywhere:
- Lightweight Python service
- No GPU dependencies
- Cross-platform compatible
- Perfect for development and testing

## Troubleshooting

### Common Issues

**GPU Mode Issues:**

1. **Import Errors on Startup**
   - Check virtual environment activation
   - Verify llama-cpp-python installation
   - Ensure Vulkan compilation flags

2. **No GPU Acceleration**
   - Verify Vulkan drivers installed
   - Check `vulkaninfo` command works
   - Confirm llama-cpp-python Vulkan build

3. **Memory Issues**
   - Monitor VRAM usage with `/vram` endpoint
   - Check `use_mmap: False` setting
   - Verify model file sizes

4. **Performance Problems**
   - Check GPU temperature and throttling
   - Monitor batch size configuration
   - Verify all layers on GPU

**Mock Mode Issues:**

1. **Mock Service Not Starting**
   - Verify `MOCK_MODE=true` environment variable
   - Check Python dependencies (FastAPI, Pydantic)
   - Ensure `src/mock_model_service.py` exists

2. **Unrealistic Response Times**
   - Adjust generation speed via `/mock-config` endpoint
   - Check network latency between services
   - Verify streaming implementation

3. **Inconsistent Embeddings**
   - Embeddings are deterministic based on text hash
   - Same text will always produce same embedding
   - Different text lengths produce different vectors

4. **Other Services Not Recognizing Mock Mode**
   - Verify all endpoints return `"mock_mode": true`
   - Check service connectivity via health endpoints
   - Confirm other services handle mock responses properly

### Debug Commands

**GPU Mode:**
```bash
# Check Vulkan setup
vulkaninfo --summary

# Test GPU detection
python test_vulkan_setup.py

# Monitor VRAM
curl http://localhost:8001/vram

# Check model status
curl http://localhost:8001/status
```

**Mock Mode:**
```bash
# Check mock service info
curl http://localhost:8001/mock-info

# Test mock generation
curl -X POST http://localhost:8001/generate \
  -H "Content-Type: application/json" \
  -d '{"prompt":"Hello","stream":false,"model_type":"chat"}'

# Monitor mock stats
curl http://localhost:8001/mock-stats

# Configure mock behavior
curl -X POST http://localhost:8001/mock-config \
  -H "Content-Type: application/json" \
  -d '{"generation_speed":50}'
```

**Both Modes:**
```bash
# Health check (includes mock_mode flag)
curl http://localhost:8001/health

# Service metrics
curl http://localhost:8001/metrics
```

### Log Analysis

```
# Successful GPU loading
load_tensors: layer 0 assigned to device Vulkan0
...
load_tensors: offloaded 41/41 layers to GPU

# Performance metrics
llama_perf_context_print: eval time = 38.34 tokens per second
```

## Security Considerations

- **Local-only access**: Service binds to localhost for security
- **No model file exposure**: Models stored locally, not served
- **Input validation**: Prompt sanitization and length limits
- **Resource limits**: VRAM and generation time constraints
- **Error message filtering**: No internal path exposure

## Future Enhancements

### Planned Features

- **Model caching**: Keep multiple models in VRAM
- **Dynamic batching**: Multiple concurrent requests
- **LoRA adapter support**: Fine-tuned model variants
- **Quantization options**: Runtime precision adjustment

### Optimization Areas

- **Memory pooling**: Reduce allocation overhead
- **Pipeline parallelism**: Overlap computation stages
- **Context compression**: Smarter context management
- **Cache optimization**: Faster model switching