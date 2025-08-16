# CLAUDE.md - Gateway Service

This file provides guidance to Claude Code when working with the Life Strands Gateway Service.

## Service Overview

The Gateway Service is the API gateway and entry point for the Life Strands system. It provides unified routing, authentication, rate limiting, and circuit breaker patterns for all microservices.

**Port:** 8000  
**Purpose:** API Gateway, Authentication, Request Routing, Rate Limiting  
**Dependencies:** All other services (routes requests to them)

## Architecture

### Core Components

- **APIRouter** (`src/router.py`): Main routing engine with service discovery
- **Authentication** (`src/auth.py`): JWT-based authentication and authorization  
- **Rate Limiter** (`src/rate_limiter.py`): Request rate limiting and abuse prevention
- **Main Service** (`main.py`): FastAPI application with middleware setup

### Service Registry

The gateway maintains a registry of all backend services:

```python
self.service_registry = {
    "model-service": "http://host.docker.internal:8001",  # Native Windows service
    "chat-service": "http://localhost:8002", 
    "npc-service": "http://localhost:8003",
    "summary-service": "http://localhost:8004",
    "monitor-service": "http://localhost:8005"
}
```

**Note:** The model service URL points to `host.docker.internal:8001` to connect to the native Windows model service from Docker containers.

### Route Patterns

API routes are mapped using patterns:

- `/api/model/*` → Model Service (native Vulkan service)
- `/api/conversations/*` → Chat Service  
- `/api/chat/*` → Chat Service
- `/api/npcs/*` → NPC Service
- `/api/search/*` → NPC Service
- `/api/summaries/*` → Summary Service
- `/api/analysis/*` → Summary Service
- `/api/metrics/*` → Monitor Service
- `/api/health/*` → Monitor Service
- `/api/alerts/*` → Monitor Service

### Circuit Breaker Pattern

The gateway implements circuit breaker patterns to handle service failures:

- **Closed**: Normal operation, requests forwarded
- **Open**: Service failed, requests rejected immediately
- **Half-Open**: Testing if service recovered

Configuration:
- Failure threshold: 5 consecutive failures
- Reset timeout: 60 seconds
- Automatic recovery testing

## Key Features

### 1. Request Routing

```python
async def route_request(self, path: str, method: str, body: Dict[str, Any] = None, headers: Dict[str, str] = None)
```

- Matches incoming requests to service routes
- Transforms API paths to downstream service paths
- Forwards requests with gateway headers
- Handles timeouts and retries

### 2. Path Transformation

Gateway transforms external API paths to internal service paths:

```python
# External: /api/model/status 
# Internal: /status (to model service)

# External: /api/npcs/123
# Internal: /npcs/123 (to npc service)
```

### 3. Health Checking

```python
async def health_check_services(self) -> Dict[str, Any]
```

- Periodic health checks of all registered services
- Circuit breaker state management
- Service availability reporting

### 4. Request Aggregation

```python
async def aggregate_responses(self, requests: List[Dict[str, Any]]) -> Dict[str, Any]
```

- Combines responses from multiple services
- Concurrent request execution
- Error handling and partial failure support

## Authentication & Authorization

### JWT Token Validation

- Bearer token authentication
- Configurable token expiration
- Role-based access control support
- Protected and public endpoints

### Rate Limiting

- Per-IP rate limiting
- Configurable requests per minute
- Sliding window implementation
- Automatic ban and recovery

## Error Handling

### Standard Error Responses

```json
{
  "status": 500,
  "error": "Error type",
  "message": "Detailed error message",
  "service": "affected-service-name"
}
```

### Common Status Codes

- **200**: Success
- **404**: Route not found
- **429**: Rate limit exceeded
- **502**: Bad gateway (service error)
- **503**: Service unavailable (circuit breaker open)
- **504**: Gateway timeout

## Configuration

### Environment Variables

- `MODEL_SERVICE_URL`: URL of native model service
- `CHAT_SERVICE_URL`: URL of chat service
- `NPC_SERVICE_URL`: URL of NPC service  
- `SUMMARY_SERVICE_URL`: URL of summary service
- `MONITOR_SERVICE_URL`: URL of monitor service
- `JWT_SECRET`: Secret key for JWT validation
- `CORS_ORIGINS`: Allowed CORS origins
- `RATE_LIMIT_REQUESTS_PER_MINUTE`: Rate limiting threshold

### Service Discovery

Services can be dynamically registered:

```python
router.register_service("new-service", "http://localhost:8006", routes=[
    {"pattern": "/api/new/*", "methods": ["GET", "POST"]}
])
```

## Common Operations

### Adding New Routes

1. Define route pattern in `_register_default_services()`
2. Add service to registry
3. Configure authentication requirements
4. Test path transformation

### Monitoring Service Health

```python
# Check all services
health_status = await router.health_check_services()

# Check specific service  
service_health = await router.handle_service_unavailable("model-service")
```

### Circuit Breaker Management

```python
# Check circuit state
is_open = router._is_circuit_open("service-name")

# Reset circuit breaker
router._reset_circuit_breaker("service-name")
```

## Development Guidelines

### Adding New Microservices

1. Add service URL to environment variables
2. Register service in `_register_default_services()`
3. Define route patterns with proper wildcards
4. Test authentication and authorization
5. Verify circuit breaker behavior

### Request/Response Middleware

The gateway automatically adds:
- Request ID headers
- Timestamp headers
- User-Agent identification
- CORS headers
- Rate limiting headers

### Error Recovery

- Implement graceful degradation for service failures
- Use circuit breakers to prevent cascade failures
- Log all routing decisions for debugging
- Monitor gateway performance metrics

## Testing

### Health Check Endpoints

- `GET /health` - Gateway health
- `GET /api/health/services` - All service health status
- `GET /api/health/{service-name}` - Specific service health

### Routing Test

```bash
# Test model service routing
curl http://localhost:8000/api/model/status

# Test chat service routing  
curl http://localhost:8000/api/conversations

# Test NPC service routing
curl http://localhost:8000/api/npcs
```

## Integration Notes

### With Native Model Service

The gateway is configured to route model requests to the native Windows Vulkan service:

- Uses `host.docker.internal:8001` for Docker-to-Windows communication
- Preserves all model service endpoints and functionality
- Handles model service-specific error patterns

### With Frontend Applications

- Serves as single entry point for React frontends
- Handles CORS for development and production
- Provides WebSocket upgrading for real-time features
- Manages authentication tokens for frontend sessions

## Troubleshooting

### Common Issues

1. **Service Unavailable (503)**
   - Check if target service is running
   - Verify circuit breaker state
   - Check service URLs in configuration

2. **Route Not Found (404)**
   - Verify route pattern matches request path
   - Check method allowed for route
   - Ensure service is registered

3. **Gateway Timeout (504)**
   - Increase request timeout configuration
   - Check service response times
   - Monitor service health endpoints

4. **Authentication Errors (401)**
   - Verify JWT secret configuration
   - Check token expiration
   - Validate token format and signature

### Debugging

- Enable debug logging for detailed request tracing
- Monitor circuit breaker states
- Check service registry consistency
- Verify path transformation logic