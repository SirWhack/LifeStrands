# Life Strands System - Makefile
# Provides common development and deployment commands

.PHONY: help dev-up dev-down dev-hybrid test migrate seed logs monitor clean \
        prod-build prod-deploy backup restore \
        health-check reset-queues install-deps \
        native-setup native-up native-down native-restart native-status native-logs \
        hybrid-up hybrid-down hybrid-restart hybrid-status

# Default target
.DEFAULT_GOAL := help

# Prefer project venv if present, otherwise system python3, then python
ifneq (,$(wildcard ./venv/bin/python))
  PYTHON := ./venv/bin/python
else
  PYTHON ?= $(shell command -v python3 2>/dev/null)
  ifeq ($(PYTHON),)
    PYTHON := $(shell command -v python 2>/dev/null)
  endif
endif

# ================================
# Help and Information
# ================================

help: ## Show available commands with descriptions
	@echo "Life Strands System - Available Commands:"
	@echo ""
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-20s\033[0m %s\n", $$1, $$2}'
	@echo ""
	@echo "Examples:"
	@echo "  make hybrid-up            # Start hybrid deployment (recommended)"
	@echo "  make dev-up               # Start all services in Docker"
	@echo "  make native-up            # Start services natively in WSL2"
	@echo "  make health-check         # Check all service health"
	@echo "  make test                 # Run the full test suite"
	@echo "  make logs s=chat-service  # Show logs for specific service"

info: ## Show system information and status
	@echo "Life Strands System Information:"
	@echo "================================"
	@echo "Docker Compose Status:"
	@docker-compose ps
	@echo ""
	@echo "LM Studio Status:"
	@curl -s http://localhost:1234/v1/models 2>/dev/null && echo "✅ LM Studio running" || echo "❌ LM Studio not running"
	@echo ""
	@echo "Docker Images:"
	@docker images | grep lifestrands
	@echo ""
	@echo "Network Status:"
	@docker network ls | grep lifestrands
	@echo ""
	@echo "Volume Status:"
	@docker volume ls | grep lifestrands

# ================================
# Development Commands
# ================================

install-deps: ## Install development dependencies
		@echo "Installing Python dependencies..."
		@pip install -r requirements.txt || true
		@echo "Installing Node.js dependencies..."
		@cd frontends/chat-interface && npm install
		@cd frontends/admin-dashboard && npm install
		@echo "Dependencies installed successfully!"

setup-tests: ## Install test dependencies into venv (pytest, etc.)
		@echo "Installing test dependencies into venv..."
		@if [ ! -x ./venv/bin/pip ]; then \
		  echo "Creating venv..."; \
		  python3 -m venv venv; \
		fi
		@./venv/bin/pip install -r requirements-dev.txt
		@echo "Test dependencies installed."


dev-up: ## Start all services in development mode (requires LM Studio running)
	@echo "Starting Life Strands System in development mode..."
	@echo "Make sure LM Studio is running on http://localhost:1234"
	@echo ""
	@echo "Starting Docker services..."
	@docker-compose --profile dev-tools --profile frontend up -d
	@echo ""
	@echo "Waiting for all services to be ready..."
	@sleep 8
	@echo "All services starting... Use 'make logs' to monitor startup"
	@echo ""
	@echo "Available services:"
	@echo "  Gateway API:       http://localhost:8000"
	@echo "  LM Studio:         http://localhost:1234 (External)"
	@echo "  Chat Service:      http://localhost:8002"
	@echo "  NPC Service:       http://localhost:8003"
	@echo "  Summary Service:   http://localhost:8004"
	@echo "  Monitor Service:   http://localhost:8005"
	@echo "  Chat Interface:    http://localhost:3001"
	@echo "  Admin Dashboard:   http://localhost:3002"
	@echo "  Database Admin:    http://localhost:8080 (pgAdmin)"
	@echo "  Redis Admin:       http://localhost:8081 (Redis Commander)"
	@echo "  Monitoring:        http://localhost:9090 (Prometheus)"
	@echo "  Dashboards:        http://localhost:3000 (Grafana)"





frontend-up: ## Start frontend applications (requires main system to be running)
	@echo "Starting frontend applications..."
	@docker-compose --profile frontend up -d


frontend-down: ## Stop frontend applications
	@echo "Stopping frontend applications..."
	@docker-compose --profile frontend down

dev-down: ## Stop all development services
	@echo "Stopping Life Strands System..."
	@echo "Stopping Docker services..."
	@docker-compose down
	@echo "All services stopped."
	@echo "Note: LM Studio will continue running (stop manually if needed)"

dev-restart: ## Restart all development services
	@echo "Restarting Life Strands System..."
	@make dev-down
	@make dev-up

dev-build: ## Build all development images
	@echo "Building development images..."
	@docker-compose build --parallel
	@echo "Build completed."

# ================================
# Native WSL2 Deployment Commands
# ================================

native-setup: ## Setup native WSL2 environment and dependencies
	@echo "Setting up native WSL2 environment..."
	@chmod +x scripts/setup_native_env.sh scripts/start_native_services.sh
	@./scripts/setup_native_env.sh
	@echo "Native environment setup completed!"

native-setup-minimal: ## Minimal setup for Python 3.12 compatibility issues
	@echo "Setting up minimal native environment (Python 3.12 compatible)..."
	@chmod +x scripts/install_minimal_deps.sh scripts/start_native_services.sh
	@./scripts/install_minimal_deps.sh
	@echo "Minimal native environment setup completed!"

native-up: ## Start all services natively in WSL2
	@echo "Starting Life Strands services natively in WSL2..."
	@./scripts/start_native_services.sh start
	@echo ""
	@echo "Native services started! Available endpoints:"
	@echo "  Gateway API:       http://localhost:8000"
	@echo "  Chat Service:      http://localhost:8002" 
	@echo "  NPC Service:       http://localhost:8003"
	@echo "  Summary Service:   http://localhost:8004"
	@echo "  Monitor Service:   http://localhost:8005"

native-down: ## Stop all native services
	@echo "Stopping native services..."
	@./scripts/start_native_services.sh stop
	@echo "Native services stopped."

native-restart: ## Restart all native services  
	@echo "Restarting native services..."
	@./scripts/start_native_services.sh restart
	@echo "Native services restarted."

native-status: ## Show status of native services
	@./scripts/start_native_services.sh status

native-logs: ## Show logs for native services (usage: make native-logs s=service)
ifdef s
	@./scripts/start_native_services.sh logs $(s)
else
	@echo "Usage: make native-logs s=service_name"
	@echo "Available services: gateway, chat, npc, summary, monitor"
endif

# ================================
# Hybrid Deployment Commands (Recommended)
# ================================

hybrid-up: ## Start hybrid deployment (infrastructure in Docker, services native)
	@echo "Starting Life Strands in hybrid mode..."
	@echo "🐳 Starting infrastructure services in Docker..."
	@docker-compose -f docker-compose.infrastructure.yml --profile dev-tools up -d postgres redis pgadmin redis-commander
	@echo "⏳ Waiting for infrastructure to be ready..."
	@sleep 8
	@echo "🚀 Starting application services natively..."
	@./scripts/start_native_services.sh start
	@echo ""
	@echo "🎉 Hybrid deployment completed!"
	@echo ""
	@echo "Available services:"
	@echo "  Gateway API:       http://localhost:8000 (Native)"
	@echo "  Chat Service:      http://localhost:8002 (Native + WebSocket)"
	@echo "  NPC Service:       http://localhost:8003 (Native)"
	@echo "  Summary Service:   http://localhost:8004 (Native - optional)"
	@echo "  Monitor Service:   http://localhost:8005 (Native - optional)"
	@echo "  Database:          localhost:5432 (Docker)"
	@echo "  Redis:             localhost:6379 (Docker)"
	@echo "  Database Admin:    http://localhost:8080 (Docker)"
	@echo "  Redis Admin:       http://localhost:8081 (Docker)"
	@echo ""
	@echo "💡 LM Studio Integration:"
	@echo "  Ensure LM Studio is running with a model loaded"
	@echo "  Chat service will connect to LM Studio automatically"
	@echo "  WebSocket chat available at ws://localhost:8002/ws"

hybrid-down: ## Stop hybrid deployment
	@echo "Stopping hybrid deployment..."
	@echo "🛑 Stopping native services..."
	@./scripts/start_native_services.sh stop
	@echo "🐳 Stopping Docker infrastructure..."
	@docker-compose -f docker-compose.infrastructure.yml down
	@echo "Hybrid deployment stopped."

hybrid-restart: ## Restart hybrid deployment
	@echo "Restarting hybrid deployment..."
	@make hybrid-down
	@make hybrid-up

hybrid-status: ## Show status of hybrid deployment
	@echo "Hybrid Deployment Status:"
	@echo "========================="
	@echo ""
	@echo "📊 Native Services:"
	@./scripts/start_native_services.sh status
	@echo ""
	@echo "🐳 Docker Infrastructure:"
	@docker-compose -f docker-compose.infrastructure.yml ps postgres redis pgadmin redis-commander
	@echo ""
	@echo "🤖 LM Studio Status:"
	@curl -s http://localhost:1234/v1/models --connect-timeout 3 > /dev/null && echo "  ✅ LM Studio accessible at localhost:1234" || echo "  ❌ LM Studio not accessible (start LM Studio with a model)"

test-chat: ## Test chat functionality end-to-end
	@echo "Testing Life Strands Chat System..."
	@echo "==================================="
	@echo "🔍 Testing service connectivity:"
	@curl -s http://localhost:8002/health && echo "  ✅ Chat Service healthy" || echo "  ❌ Chat Service not responding"
	@curl -s http://localhost:8003/health && echo "  ✅ NPC Service healthy" || echo "  ❌ NPC Service not responding"  
	@curl -s http://localhost:1234/v1/models --connect-timeout 3 > /dev/null && echo "  ✅ LM Studio connected" || echo "  ❌ LM Studio not accessible"
	@echo ""
	@echo "💬 Chat endpoints:"
	@echo "  REST API: http://localhost:8002/conversation/start"
	@echo "  WebSocket: ws://localhost:8002/ws" 
	@echo "  Frontend: http://localhost:3000 (if started)"
	@echo ""
	@echo "📋 To test chat:"
	@echo "  1. Ensure LM Studio is running with a model loaded"
	@echo "  2. Open the chat frontend or use WebSocket directly"
	@echo "  3. Chat will automatically create NPCs as needed"

start-chat-frontend: ## Start the chat frontend in Docker
	@echo "Starting chat frontend..."
	@docker-compose -f docker-compose.infrastructure.yml --profile frontend up -d chat-interface
	@echo "Chat frontend starting at http://localhost:3000"

# ================================
# Testing Commands
# ================================

test: ## Run the full test suite
		@echo "Running Life Strands test suite..."
		@$(PYTHON) -m pytest tests/ -v --tb=short
		@echo "Running integration tests..."
		@$(PYTHON) -m pytest tests/integration/ -v
		@echo "Running load tests..."
		@$(PYTHON) -m pytest tests/load/ -v -m "not slow"
		@echo "All tests completed."

test-unit: ## Run unit tests only
		@echo "Running unit tests..."
		@$(PYTHON) -m pytest tests/unit/ -v

test-integration: ## Run integration tests only
		@echo "Running integration tests..."
		@$(PYTHON) -m pytest tests/integration/ -v

test-load: ## Run load tests
		@echo "Running load tests..."
		@$(PYTHON) -m pytest tests/load/ -v

test-coverage: ## Run tests with coverage report
		@echo "Running tests with coverage..."
		@$(PYTHON) -m pytest tests/ --cov=services --cov-report=html --cov-report=term
		@echo "Coverage report generated in htmlcov/"

# ================================
# Database Commands
# ================================

migrate: ## Run database migrations
	@echo "Running database migrations..."
	@docker-compose exec postgres psql -U lifestrands_user -d lifestrands -f /docker-entrypoint-initdb.d/001_initial_schema.sql
	@docker-compose exec postgres psql -U lifestrands_user -d lifestrands -f /docker-entrypoint-initdb.d/002_add_embeddings.sql
	@docker-compose exec postgres psql -U lifestrands_user -d lifestrands -f /docker-entrypoint-initdb.d/003_update_embedding_dimensions.sql || true
	@echo "Migrations completed."

migrate-reset: ## Reset database and run all migrations
	@echo "Resetting database..."
	@docker-compose exec postgres psql -U lifestrands_user -d postgres -c "DROP DATABASE IF EXISTS lifestrands;"
	@docker-compose exec postgres psql -U lifestrands_user -d postgres -c "CREATE DATABASE lifestrands;"
	@make migrate
	@echo "Database reset and migrations completed."

seed: ## Seed database with test NPCs
	@echo "Seeding database with test NPCs..."
	@docker-compose exec -T postgres psql -U lifestrands_user -d lifestrands -f /docker-entrypoint-initdb.d/seed_npcs.sql
	@echo "Database seeded successfully."

backup: ## Backup database and Redis data
	@echo "Creating backup..."
	@mkdir -p backups
	@docker-compose exec postgres pg_dump -U lifestrands_user lifestrands > backups/lifestrands_$(shell date +%Y%m%d_%H%M%S).sql
	@docker-compose exec redis redis-cli --rdb backups/redis_$(shell date +%Y%m%d_%H%M%S).rdb
	@echo "Backup completed in backups/"

restore: ## Restore from backup (usage: make restore file=backup.sql)
ifndef file
	@echo "Usage: make restore file=backup_file.sql"
	@echo "Available backups:"
	@ls -la backups/
else
	@echo "Restoring from $(file)..."
	@docker-compose exec -T postgres psql -U lifestrands_user lifestrands < backups/$(file)
	@echo "Restore completed."
endif

# ================================
# Monitoring and Logging
# ================================

logs: ## Tail logs from all services or specific service (usage: make logs s=service_name)
ifdef s
	@echo "Showing logs for $(s) service..."
	@docker-compose logs -f $(s)
else
	@echo "Showing logs for all services..."
	@docker-compose logs -f --tail=100
endif

logs-errors: ## Show only error logs from all services
	@echo "Showing error logs..."
	@docker-compose logs --tail=1000 | grep -i error

monitor: ## Open monitoring dashboard in browser
	@echo "Opening monitoring dashboard..."
	@open http://localhost:3000 || xdg-open http://localhost:3000 || echo "Please open http://localhost:3000 manually"

health-check: ## Check the health of all services (works with any deployment mode)
	@echo "Checking service health..."
	@echo "================================"
	@echo "Gateway (API):"
	@curl -s http://localhost:8000/health && echo "✅ Gateway healthy" || echo "❌ Gateway not responding"
	@echo ""
	@echo "Model Service:"
	@curl -s http://localhost:8001/health && echo "✅ Model Service healthy" || echo "❌ Model Service not responding" 
	@echo ""
	@echo "Chat Service:"
	@curl -s http://localhost:8002/health && echo "✅ Chat Service healthy" || echo "❌ Chat Service not responding"
	@echo ""
	@echo "NPC Service:"
	@curl -s http://localhost:8003/health && echo "✅ NPC Service healthy" || echo "❌ NPC Service not responding"
	@echo ""
	@echo "Summary Service:"
	@curl -s http://localhost:8004/health && echo "✅ Summary Service healthy" || echo "❌ Summary Service not responding"
	@echo ""
	@echo "Monitor Service:"
	@curl -s http://localhost:8005/health && echo "✅ Monitor Service healthy" || echo "❌ Monitor Service not responding"
	@echo ""
	@echo "Database:"
	@pg_isready -h localhost -p 5432 -U lifestrands_user && echo "✅ Database healthy" || echo "❌ Database not healthy"
	@echo "Redis:"
	@redis-cli -h localhost -p 6379 ping && echo "✅ Redis healthy" || echo "❌ Redis not healthy"

# ================================
# LM Studio Integration
# ================================

lm-studio-status: ## Check LM Studio status and loaded model
	@echo "LM Studio Status:"
	@curl -s http://localhost:1234/v1/models | python -m json.tool || echo "LM Studio not responding"

lm-studio-test: ## Test LM Studio connectivity
	@echo "Testing LM Studio connectivity..."
	@curl -s -X POST http://localhost:1234/v1/chat/completions \
		-H "Content-Type: application/json" \
		-d '{"messages":[{"role":"user","content":"Hello"}],"max_tokens":5}' \
		| python -m json.tool || echo "LM Studio test failed"

# ================================
# Production Commands
# ================================

prod-build: ## Build production containers
	@echo "Building production images..."
	@docker-compose -f docker-compose.yml -f docker-compose.prod.yml build --parallel
	@echo "Production build completed."

prod-deploy: ## Deploy to production (requires proper setup)
	@echo "Deploying to production..."
	@docker-compose -f docker-compose.yml -f docker-compose.prod.yml up -d
	@echo "Production deployment completed."

prod-stop: ## Stop production services
	@echo "Stopping production services..."
	@docker-compose -f docker-compose.yml -f docker-compose.prod.yml down
	@echo "Production services stopped."

# ================================
# Cleanup and Maintenance
# ================================

clean: ## Clean up unused Docker resources
	@echo "Cleaning up Docker resources..."
	@docker system prune -f
	@docker volume prune -f
	@echo "Cleanup completed."

docker-cleanup: ## Comprehensive Docker cleanup (removes Life Strands containers/networks)
	@echo "Running comprehensive Docker cleanup..."
	@chmod +x scripts/docker_cleanup.sh
	@./scripts/docker_cleanup.sh

clean-all: ## Remove all containers, images, and volumes (DESTRUCTIVE)
	@echo "⚠️  WARNING: This will remove all containers, images, and volumes!"
	@echo "Press Ctrl+C to cancel, or Enter to continue..."
	@read
	@docker-compose down -v --remove-orphans
	@docker system prune -a -f --volumes
	@echo "Complete cleanup finished."

reset-queues: ## Clear Redis queues and caches
	@echo "Clearing Redis queues..."
	@docker-compose exec redis redis-cli FLUSHDB
	@echo "Redis queues cleared."


prune-logs: ## Prune old log files
	@echo "Pruning old logs..."
	@docker-compose exec gateway find /app/logs -name "*.log" -mtime +7 -delete
	@docker-compose exec model-service find /app/logs -name "*.log" -mtime +7 -delete
	@echo "Old logs pruned."

# ================================
# Development Utilities
# ================================

shell: ## Open shell in specific service container (usage: make shell s=service_name)
ifndef s
	@echo "Usage: make shell s=service_name"
	@echo "Available services: gateway-service, chat-service, npc-service, summary-service, monitor-service"
else
	@echo "Opening shell in $(s)..."
	@docker-compose exec $(s) /bin/bash
endif

psql: ## Connect to PostgreSQL database
	@echo "Connecting to database..."
	@docker-compose exec postgres psql -U lifestrands_user -d lifestrands

redis-cli: ## Connect to Redis CLI
	@echo "Connecting to Redis..."
	@docker-compose exec redis redis-cli

inspect: ## Show detailed container information (usage: make inspect s=service_name)
ifndef s
	@echo "Usage: make inspect s=service_name"
else
	@docker-compose exec $(s) ps aux
	@docker-compose exec $(s) df -h
	@docker-compose exec $(s) free -h
endif

# ================================
# Performance and Benchmarking
# ================================

benchmark: ## Run performance benchmarks
	@echo "Running performance benchmarks..."
	@python scripts/benchmark.py
	@echo "Benchmarks completed."

stress-test: ## Run stress tests against the system
	@echo "Running stress tests..."
	@python scripts/stress_test.py
	@echo "Stress tests completed."

# ================================
# Security and Maintenance
# ================================

security-scan: ## Run security scans on containers
	@echo "Running security scans..."
	@docker scan lifestrands-gateway:latest || echo "Docker scan not available"
	@echo "Security scan completed."

update-deps: ## Update all dependencies
	@echo "Updating dependencies..."
	@pip-review --auto
	@cd frontends/chat-interface && npm update
	@cd frontends/admin-dashboard && npm update
	@echo "Dependencies updated."

# ================================
# Documentation
# ================================

docs: ## Generate API documentation
	@echo "Generating API documentation..."
	@python scripts/generate_docs.py
	@echo "Documentation generated in docs/"


# ================================
# Quick Start Shortcuts
# ================================

start: hybrid-up ## Alias for hybrid-up (recommended)
stop: hybrid-down ## Alias for hybrid-down
restart: hybrid-restart ## Alias for hybrid-restart
status: hybrid-status ## Alias for hybrid-status
log: logs ## Alias for logs

setup: native-setup ## Alias for native-setup
test-deployment: ## Test hybrid deployment
	@./scripts/test_hybrid_deployment.sh

quick-start: ## Complete quick start sequence
	@echo "🚀 Life Strands Quick Start"
	@echo "=========================="
	@echo "This will set up and start Life Strands in hybrid mode..."
	@echo ""
	@echo "Step 1: Installing dependencies..."
	@./scripts/install_native_deps.sh
	@echo ""
	@echo "Step 2: Setting up native environment..."
	@make native-setup
	@echo ""
	@echo "Step 3: Starting hybrid deployment..." 
	@make hybrid-up
	@echo ""
	@echo "Step 4: Testing deployment..."
	@./scripts/test_hybrid_deployment.sh
	@echo ""
	@echo "🎉 Quick start completed!"
	@echo ""
	@echo "Next steps:"
	@echo "• Access services at http://localhost:8000"
	@echo "• Check status with: make status"
	@echo "• View logs with: make native-logs s=service_name" 
	@echo "• Stop with: make stop"
