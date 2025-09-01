# Life Strands Hybrid Deployment Guide

This guide explains the hybrid deployment architecture where infrastructure services run in Docker containers while application services run natively in WSL2.

## Why Hybrid Deployment?

**Benefits:**
- **Better Performance**: Native services have direct access to system resources
- **Faster Development**: No container rebuild cycles, instant code changes
- **Easier Debugging**: Direct access to service processes and logs
- **GPU Optimization**: Model service runs natively for optimal GPU performance
- **Simplified Networking**: Services communicate via localhost
- **Resource Efficiency**: Reduced Docker overhead

**Trade-offs:**
- **More Setup**: Requires native Python environment setup
- **Platform Dependency**: Optimized for WSL2/Linux environments
- **Mixed Management**: Services managed through different systems

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│                    Life Strands Hybrid                     │
├─────────────────────┬───────────────────────────────────────┤
│   Docker Services   │         Native Services              │
│    (Infrastructure) │        (Applications)                │
├─────────────────────┼───────────────────────────────────────┤
│ ► PostgreSQL:5432   │ ► Gateway Service:8000               │
│ ► Redis:6379        │ ► Chat Service:8002                  │
│ ► pgAdmin:8080      │ ► NPC Service:8003                   │
│ ► Redis Cmd:8081    │ ► Summary Service:8004               │
│                     │ ► Monitor Service:8005               │
│                     │ ► Model Service:8001 (Windows)       │
└─────────────────────┴───────────────────────────────────────┘
```

## Quick Start

**Complete Setup (First Time):**
```bash
make quick-start
```
This runs the entire setup sequence automatically.

**Manual Setup:**
```bash
# 1. Install dependencies
./scripts/install_native_deps.sh

# 2. Setup environment  
make native-setup

# 3. Start hybrid deployment
make hybrid-up

# 4. Test deployment
make test-deployment

# 5. Check health
make health-check
```

## Daily Development Commands

```bash
# Start development session
make start              # Alias for hybrid-up

# Check status
make status             # Show all service status

# View service logs
make native-logs s=chat # View chat service logs

# Restart specific service
./scripts/start_native_services.sh restart chat

# Stop development session
make stop               # Alias for hybrid-down
```

## Service Management

### Native Services

All application services run natively using the startup script:

```bash
# Start all services
./scripts/start_native_services.sh start

# Start specific service
./scripts/start_native_services.sh start chat

# Stop all services
./scripts/start_native_services.sh stop

# Check status
./scripts/start_native_services.sh status

# View logs
./scripts/start_native_services.sh logs chat

# Restart service
./scripts/start_native_services.sh restart summary
```

**Available Services:**
- `gateway` - API Gateway (port 8000)
- `chat` - Chat Service (port 8002)
- `npc` - NPC Service (port 8003)
- `summary` - Summary Service (port 8004)
- `monitor` - Monitor Service (port 8005)

### Infrastructure Services

Infrastructure runs in Docker using the infrastructure-only compose file:

```bash
# Start infrastructure
docker-compose -f docker-compose.infrastructure.yml up -d

# With dev tools (pgAdmin, Redis Commander)
docker-compose -f docker-compose.infrastructure.yml --profile dev-tools up -d

# Stop infrastructure
docker-compose -f docker-compose.infrastructure.yml down

# Check status
docker-compose -f docker-compose.infrastructure.yml ps
```

## Configuration

### Environment Variables

Native services use `.env.native` for configuration:

```bash
# Database & Redis (Docker containers)
DATABASE_URL=postgresql://lifestrands_user:lifestrands_password@localhost:5432/lifestrands
REDIS_URL=redis://:redis_password@localhost:6379

# Service URLs (native services)
MODEL_SERVICE_URL=http://localhost:8001
CHAT_SERVICE_URL=http://localhost:8002
NPC_SERVICE_URL=http://localhost:8003
SUMMARY_SERVICE_URL=http://localhost:8004
MONITOR_SERVICE_URL=http://localhost:8005

# Application settings
MAX_CONCURRENT_CONVERSATIONS=50
ENABLE_EMBEDDINGS=false
LOG_LEVEL=INFO
```

### Service Discovery

Services connect to each other via localhost URLs:
- Docker infrastructure: `localhost:5432` (postgres), `localhost:6379` (redis)
- Native services: `localhost:800X` ports
- Model service: `localhost:8001` (runs natively on Windows)

## File Structure

```
LifeStrands/
├── docker-compose.yml                 # Full Docker deployment
├── docker-compose.infrastructure.yml  # Infrastructure-only (hybrid)
├── .env.native                        # Native service configuration
├── scripts/
│   ├── install_native_deps.sh         # Dependency installer
│   ├── setup_native_env.sh            # Environment setup
│   ├── start_native_services.sh       # Service management
│   ├── native_config.py               # Configuration loader
│   └── test_hybrid_deployment.sh      # Deployment tester
├── logs/                              # Native service logs
├── pids/                              # Native service PIDs
└── venv/                              # Python virtual environment
```

## Development Workflow

### Starting Development
```bash
# Start everything
make hybrid-up

# Or step by step:
docker-compose -f docker-compose.infrastructure.yml --profile dev-tools up -d
./scripts/start_native_services.sh start
```

### Making Changes
1. Edit service code directly
2. Service auto-reloads with `--reload` flag
3. Check logs: `make native-logs s=service_name`
4. Test changes: `curl http://localhost:800X/health`

### Debugging Issues
```bash
# Check service status
make hybrid-status

# View service logs
make native-logs s=chat

# Test connectivity
make health-check

# Run deployment test
./scripts/test_hybrid_deployment.sh

# Debug specific service
./scripts/start_native_services.sh stop chat
cd services/chat-service && python main.py  # Debug directly
```

### Stopping Development
```bash
make hybrid-down
```

## Troubleshooting

### Common Issues

**Services Not Starting:**
```bash
# Check virtual environment
source venv/bin/activate
python --version

# Check dependencies
pip list | grep fastapi

# Check logs
make native-logs s=gateway
```

**Database Connection Issues:**
```bash
# Check PostgreSQL
pg_isready -h localhost -p 5432 -U lifestrands_user

# Check Redis
redis-cli -h localhost -p 6379 ping

# Restart infrastructure
docker-compose -f docker-compose.infrastructure.yml restart postgres redis
```

**Service Communication Issues:**
```bash
# Test service endpoints
curl http://localhost:8000/health  # Gateway
curl http://localhost:8002/health  # Chat
curl http://localhost:8003/health  # NPC

# Check port conflicts
netstat -tulpn | grep :800
```

### Performance Issues

**High Memory Usage:**
```bash
# Check service memory usage
ps aux | grep "uvicorn main:app"

# Monitor Docker containers
docker stats

# Check system resources
htop
```

**Slow Response Times:**
```bash
# Profile service performance
curl -w "@curl-format.txt" http://localhost:8000/health

# Check database performance
# Connect to pgAdmin at http://localhost:8080

# Monitor service logs
tail -f logs/gateway.log
```

## Advanced Configuration

### Custom Service Ports
Edit `.env.native` and update port mappings:
```bash
GATEWAY_URL=http://localhost:8000
CHAT_SERVICE_URL=http://localhost:8002
# ... etc
```

### Production Deployment
For production, consider:
1. Use systemd services for auto-restart
2. Configure proper logging rotation
3. Set up monitoring and alerting  
4. Use nginx reverse proxy
5. Configure SSL/TLS certificates

### Performance Tuning
```bash
# Increase worker processes
export UVICORN_WORKERS=4

# Adjust memory limits
export MAX_MEMORY_MB=4096

# Configure database connection pooling
export DB_POOL_SIZE=20
```

## Monitoring and Observability

### Service Health
```bash
# Check all services
make health-check

# Individual service health
curl http://localhost:8000/health
curl http://localhost:8002/health
curl http://localhost:8003/health
```

### Logs and Metrics
```bash
# View service logs
make native-logs s=service_name

# Monitor system metrics
curl http://localhost:8005/metrics

# Database admin
open http://localhost:8080

# Redis admin  
open http://localhost:8081
```

### Performance Monitoring
```bash
# Service response times
curl -w "%{time_total}" http://localhost:8000/health

# System resource usage
htop

# Database performance
# Use pgAdmin query analyzer

# GPU monitoring (for model service)
nvidia-smi  # or AMD equivalent
```

## Migration from Full Docker

To migrate from full Docker deployment:

1. **Backup existing data:**
   ```bash
   make backup
   ```

2. **Stop Docker services:**
   ```bash
   make dev-down
   ```

3. **Setup hybrid deployment:**
   ```bash
   ./scripts/install_native_deps.sh
   make native-setup
   ```

4. **Start hybrid deployment:**
   ```bash
   make hybrid-up
   ```

5. **Restore data if needed:**
   ```bash
   make restore file=backup_file.sql
   ```

## Conclusion

The hybrid deployment provides the best balance of performance, development experience, and resource efficiency. It keeps complex infrastructure containerized while allowing application services to run natively for optimal performance and debugging experience.

For any issues or questions, refer to the main `CLAUDE.md` documentation or the troubleshooting section above.