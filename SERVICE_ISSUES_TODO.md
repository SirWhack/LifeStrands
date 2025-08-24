# Life Strands System - Service Issues & TODO

**Date:** 2025-08-23  
**Context:** System partially running, Model Service being refactored

## Current System Status

### ✅ Working Services
- **PostgreSQL** (port 5432) - Database healthy, accepting connections
- **Redis** (port 6379) - Cache/queue service healthy  
- **Gateway Service** (port 8000) - API gateway running, but can't reach other services via localhost
- **Chat Service** (port 8002) - Healthy, 0 active sessions, ready for connections
- **NPC Service** (port 8003) - Healthy, 2 NPCs loaded, embeddings disabled
- **Monitor Service** (port 8005) - Healthy, metrics collecting, alerts active
- **Grafana** (port 3000) - Monitoring dashboard running
- **Prometheus** (port 9090) - Metrics collection running  
- **Jaeger** (port 16686) - Distributed tracing running

### ❌ Failing Services
1. **Summary Service** (port 8004) - **PRIORITY ISSUE**
   - Status: Restarting continuously (exit code 3)
   - Problem: Tries to connect to Model Service at startup in `summary_generator.py:53`
   - Error: `Cannot connect to host host.docker.internal:8001`
   - Impact: Post-conversation analysis and NPC memory updates not working

2. **Model Service** (port 8001) - **INTENTIONALLY DISABLED**
   - Status: Not running (commented out in Makefile)
   - Reason: Being refactored by user
   - Impact: No LLM generation capability

3. **Nginx** (port 80/443) - **LOW PRIORITY**  
   - Status: Restarting continuously
   - Problem: Looking for `lifestrands-chat-interface:3000` upstream
   - Root Cause: Frontend containers not running
   - Impact: No web interface routing

4. **pgAdmin** (port 8080) - **LOW PRIORITY**
   - Status: Restarting 
   - Problem: Connection issues with PostgreSQL
   - Likely: Timing issue, may resolve automatically

## TODO Items

### 🔥 High Priority

#### 1. Fix Summary Service Startup Dependency
**Problem:** Summary Service crashes on startup because it requires Model Service health check

**Solutions:**
- **Option A:** Modify `services/summary-service/src/summary_generator.py` to make Model Service connection optional at startup
- **Option B:** Add retry logic with exponential backoff for Model Service connection
- **Option C:** Temporarily disable Summary Service until Model Service is refactored

**Files to check:**
- `services/summary-service/src/summary_generator.py:53` (initialization code)
- `services/summary-service/main.py:43` (startup lifecycle)

#### 2. Test Core Conversation Flow
**Goal:** Verify Gateway → Chat → NPC chain works without Model Service

**Steps:**
1. Test WebSocket connection to Chat Service
2. Verify NPC data retrieval from NPC Service  
3. Confirm conversation session management
4. Document what works vs what needs Model Service

### 🔧 Medium Priority

#### 3. Fix pgAdmin Connection
**Steps:**
1. Check pgAdmin container logs
2. Verify PostgreSQL connection settings in docker-compose
3. Check if it's just a startup timing issue

#### 4. Document Service Architecture
**Create comprehensive service map:**
- Which services depend on which
- What works without Model Service
- Network connectivity between containers
- Port mapping and internal vs external access

### 🔨 Low Priority  

#### 5. Fix Nginx Configuration
**Problem:** Frontend containers not running
- Check if frontend containers are defined in docker-compose
- Verify nginx.conf configuration
- Consider if frontend is needed for current testing

#### 6. Clean Up Docker Environment
- Remove orphaned containers (lifestrands-model-service)
- Clean up unused images and volumes
- Optimize startup order with proper depends_on

## Network Architecture Notes

**Internal Docker Network:** `172.20.0.0/16`
- PostgreSQL: `172.20.0.10:5432`
- Redis: `172.20.0.11:6379` 
- Chat Service: `172.20.0.30:8002`
- NPC Service: `172.20.0.40:8003`
- Summary Service: `172.20.0.50:8004`
- Monitor Service: `172.20.0.60:8005`
- Gateway: `172.20.0.200:8000`

**External Access:**
- Model Service: `host.docker.internal:8001` (Windows native)
- All services expose ports to localhost for external access

## Key Commands for Future Reference

```bash
# Start all services (Model Service disabled)
make dev-up

# Check service status
make health-check  
docker-compose -f docker-compose.native-model.yml ps

# View specific service logs
make logs s=summary-service
make logs s=chat-service

# Connect to database
make psql

# Connect to Redis
make redis-cli

# Restart single service
docker-compose -f docker-compose.native-model.yml restart summary-service
```

## Service Dependencies

```
Gateway Service
├── Depends on: PostgreSQL, Redis
├── Connects to: Chat, NPC, Summary, Monitor Services
└── Status: Working but can't reach other services via localhost health checks

Chat Service  
├── Depends on: PostgreSQL, Redis
├── Connects to: NPC Service, Model Service (for generation)
└── Status: Working, ready for WebSocket connections

NPC Service
├── Depends on: PostgreSQL, Redis  
├── Connects to: Model Service (for embeddings)
└── Status: Working, 2 NPCs loaded, embeddings disabled

Summary Service
├── Depends on: PostgreSQL, Redis
├── Connects to: NPC Service, Model Service (REQUIRED at startup)
└── Status: FAILING - cannot start without Model Service

Monitor Service
├── Depends on: Redis
├── Connects to: All services for health monitoring
└── Status: Working, collecting metrics
```

## Next Steps When Model Service is Ready

1. **Test Summary Service**: Once Model Service is running, Summary Service should start properly
2. **Enable Embeddings**: NPC Service can generate embeddings for semantic search  
3. **Test Full Conversation Flow**: Gateway → Chat → Model → Summary → NPC updates
4. **Performance Testing**: Load test with multiple concurrent conversations

## Notes for Future Self

- **Model Service refactor in progress** - don't try to fix it, user is handling it
- **Core conversation system is functional** - just can't generate responses yet
- **Database and caching layers are solid** - no issues with persistence
- **Monitoring stack is complete** - use Grafana to track system health
- **Focus on making services Model Service optional** - better resilience during development