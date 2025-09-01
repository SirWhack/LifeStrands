# Life Strands System - Makefile
# Provides common development and deployment commands

.PHONY: help dev-up dev-down dev-hybrid test migrate seed logs monitor clean \
        prod-build prod-deploy backup restore \
        health-check reset-queues install-deps

# Default target
.DEFAULT_GOAL := help

# ================================
# Help and Information
# ================================

help: ## Show available commands with descriptions
	@echo "Life Strands System - Available Commands:"
	@echo ""
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-20s\033[0m %s\n", $$1, $$2}'
	@echo ""
	@echo "Examples:"
	@echo "  make dev-up               # Start all services (requires LM Studio running)"
	@echo "  make dev-down             # Stop all services"
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
	@pip install -r requirements.txt
	@echo "Installing Node.js dependencies..."
	@cd frontends/chat-interface && npm install
	@cd frontends/admin-dashboard && npm install
	@echo "Dependencies installed successfully!"


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
# Testing Commands
# ================================

test: ## Run the full test suite
	@echo "Running Life Strands test suite..."
	@python -m pytest tests/ -v --tb=short
	@echo "Running integration tests..."
	@python -m pytest tests/integration/ -v
	@echo "Running load tests..."
	@python -m pytest tests/load/ -v -m "not slow"
	@echo "All tests completed."

test-unit: ## Run unit tests only
	@echo "Running unit tests..."
	@python -m pytest tests/unit/ -v

test-integration: ## Run integration tests only
	@echo "Running integration tests..."
	@python -m pytest tests/integration/ -v

test-load: ## Run load tests
	@echo "Running load tests..."
	@python -m pytest tests/load/ -v

test-coverage: ## Run tests with coverage report
	@echo "Running tests with coverage..."
	@python -m pytest tests/ --cov=services --cov-report=html --cov-report=term
	@echo "Coverage report generated in htmlcov/"

# ================================
# Database Commands
# ================================

migrate: ## Run database migrations
	@echo "Running database migrations..."
	@docker-compose exec postgres psql -U lifestrands_user -d lifestrands -f /docker-entrypoint-initdb.d/001_initial_schema.sql
	@docker-compose exec postgres psql -U lifestrands_user -d lifestrands -f /docker-entrypoint-initdb.d/002_add_embeddings.sql
	@echo "Migrations completed."

migrate-reset: ## Reset database and run all migrations
	@echo "Resetting database..."
	@docker-compose exec postgres psql -U lifestrands_user -d postgres -c "DROP DATABASE IF EXISTS lifestrands;"
	@docker-compose exec postgres psql -U lifestrands_user -d postgres -c "CREATE DATABASE lifestrands;"
	@make migrate
	@echo "Database reset and migrations completed."

seed: ## Seed database with test NPCs
	@echo "Seeding database with test data..."
	@python scripts/seed_database.py
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

health-check: ## Check the health of all services
	@echo "Checking service health..."
	@echo "================================"
	@echo "Gateway (API):"
	@curl -s http://localhost:8000/health || echo "❌ Gateway not responding"
	@echo ""
	@echo "LM Studio:"
	@curl -s http://localhost:1234/v1/models || echo "❌ LM Studio not responding"
	@echo ""
	@echo "Chat Service:"
	@curl -s http://localhost:8002/health || echo "❌ Chat Service not responding"
	@echo ""
	@echo "NPC Service:"
	@curl -s http://localhost:8003/health || echo "❌ NPC Service not responding"
	@echo ""
	@echo "Summary Service:"
	@curl -s http://localhost:8004/health || echo "❌ Summary Service not responding"
	@echo ""
	@echo "Monitor Service:"
	@curl -s http://localhost:8005/health || echo "❌ Monitor Service not responding"
	@echo ""
	@echo "Database:"
	@docker-compose exec postgres pg_isready -U lifestrands_user -d lifestrands && echo "✅ Database healthy" || echo "❌ Database not healthy"
	@echo "Redis:"
	@docker-compose exec redis redis-cli ping && echo "✅ Redis healthy" || echo "❌ Redis not healthy"

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

start: dev-up ## Alias for dev-up
stop: dev-down ## Alias for dev-down
restart: dev-restart ## Alias for dev-restart
status: health-check ## Alias for health-check
log: logs ## Alias for logs