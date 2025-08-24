# Life Strands System - Makefile
# Provides common development and deployment commands

.PHONY: help dev-up dev-down dev-hybrid test migrate seed logs monitor clean \
        prod-build prod-deploy backup restore \
        model-status model-reload model-switch model-start-native model-stop-native \
        health-check reset-queues reset-model install-deps \
        windows-setup windows-start windows-status native-up native-down

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
	@echo "  make setup-model          # Setup Windows model service (run first time)"
	@echo "  make dev-up               # Start all services (Docker + Native Vulkan Model)"
	@echo "  make dev-down             # Stop all services (Docker + Native Model)"
	@echo "  make model-start-native   # Start only the model service in new terminal"
	@echo "  make model-stop-native    # Stop only the model service"
	@echo "  make health-check         # Check all service health"
	@echo "  make test                 # Run the full test suite"
	@echo "  make logs s=chat-service  # Show logs for specific service"

info: ## Show system information and status
	@echo "Life Strands System Information:"
	@echo "================================"
	@echo "Docker Compose Status:"
	@docker-compose -f docker-compose.native-model.yml ps
	@echo ""
	@echo "Native Model Service Status:"
	@curl -s http://localhost:8001/health 2>/dev/null && echo "✅ Native model service running" || echo "❌ Native model service not running"
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

setup-model: ## Setup Windows model service environment with Vulkan llama-cpp-python
	@echo "Setting up Windows model service environment..."
	@if grep -qi microsoft /proc/version 2>/dev/null; then \
		echo "Detected WSL environment, running Windows PowerShell script..."; \
		powershell.exe -ExecutionPolicy Bypass -File "setup_model_service_windows.ps1"; \
	elif command -v powershell.exe >/dev/null 2>&1; then \
		powershell.exe -ExecutionPolicy Bypass -File "setup_model_service_windows.ps1"; \
	else \
		echo "❌ Windows PowerShell not found. Please run manually:"; \
		echo "   powershell.exe -ExecutionPolicy Bypass -File setup_model_service_windows.ps1"; \
	fi

dev-up: ## Start all services in development mode (Docker + native model + frontend)
	@echo "Starting Life Strands System in development mode..."
	@echo "Using native Windows model service for optimal GPU performance"
	@echo ""
	@echo "Step 1: Starting Docker services (excluding model service)..."
	@docker-compose -f docker-compose.native-model.yml --profile dev-tools --profile frontend up -d
	@echo ""
	@echo "Step 2: Starting native Windows model service in new terminal..."
	@if grep -qi microsoft /proc/version 2>/dev/null; then \
		echo "Detected WSL environment, using WSL-compatible script..."; \
		scripts/start_model_service_wsl.sh; \
	elif command -v powershell.exe >/dev/null 2>&1; then \
		powershell.exe -ExecutionPolicy Bypass -File "scripts/start_model_service_window.ps1"; \
	elif command -v cmd.exe >/dev/null 2>&1; then \
		echo "Using Windows batch script..."; \
		cmd.exe /c scripts\\start_model_service_window.bat; \
	else \
		echo "❌ Windows environment not detected. Please start model service manually:"; \
		echo "   cd services/model-service && python main.py"; \
	fi
	@echo ""
	@echo "Step 3: Waiting for all services to be ready..."
	@sleep 8
	@echo "All services starting... Use 'make logs' to monitor startup"
	@echo ""
	@echo "Available services:"
	@echo "  Gateway API:       http://localhost:8000"
	@echo "  Model Service:     http://localhost:8001 (Native Vulkan)"
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

native-up: ## Start services with native Windows model service
	@echo "Starting Life Strands System with native Windows model service..."
	@echo "Step 1: Starting Docker services (excluding model service)..."
	@docker-compose -f docker-compose.native-model.yml --profile dev-tools --profile monitoring up -d
	@echo "Step 2: Please start the native model service in a separate terminal:"
	@echo "  PowerShell: .\start_native_model_service.ps1"
	@echo "  Batch:      start_native_model_service.bat"
	@echo "  Manual:     python run_unified_model_service.py"
	@echo ""
	@echo "Available services:"
	@echo "  Gateway API:       http://localhost:8000"
	@echo "  Model Service:     http://localhost:8001 (NATIVE - Start manually)"
	@echo "  Chat Interface:    http://localhost:3001"
	@echo "  Admin Dashboard:   http://localhost:3002"
	@echo "  Monitoring:        http://localhost:3000 (Grafana)"
	@echo "  Database Admin:    http://localhost:8080 (pgAdmin)"
	@echo "  Redis Admin:       http://localhost:8081 (Redis Commander)"

native-down: ## Stop services using native model configuration
	@echo "Stopping Life Strands System (native model configuration)..."
	@docker-compose -f docker-compose.native-model.yml down
	@echo "Note: Stop the native model service manually (Ctrl+C in its terminal)"

model-start-native: ## Start native Windows model service in new terminal
	@echo "Starting native Windows model service in new terminal..."
	@if grep -qi microsoft /proc/version 2>/dev/null; then \
		echo "Detected WSL environment, using WSL-compatible script..."; \
		scripts/start_model_service_wsl.sh; \
	elif command -v powershell.exe >/dev/null 2>&1; then \
		powershell.exe -ExecutionPolicy Bypass -File "scripts/start_model_service_window.ps1"; \
	elif command -v cmd.exe >/dev/null 2>&1; then \
		echo "Using Windows batch script..."; \
		cmd.exe /c scripts\\start_model_service_window.bat; \
	else \
		echo "❌ Windows environment not detected. Please start model service manually:"; \
		echo "   cd services/model-service && python main.py"; \
	fi

model-stop-native: ## Stop native Windows model service
	@echo "Stopping native Windows model service..."
	@if grep -qi microsoft /proc/version 2>/dev/null; then \
		echo "Detected WSL environment, using WSL-compatible script..."; \
		scripts/stop_model_service_wsl.sh; \
	elif command -v powershell.exe >/dev/null 2>&1; then \
		powershell.exe -ExecutionPolicy Bypass -File "scripts/stop_model_service.ps1"; \
	elif command -v cmd.exe >/dev/null 2>&1; then \
		echo "Using Windows batch script..."; \
		cmd.exe /c scripts\\stop_model_service.bat; \
	else \
		echo "⚠️  Cannot stop model service automatically. Please stop manually."; \
	fi

frontend-up: ## Start frontend applications (requires main system to be running)
	@echo "Starting frontend applications..."
	@docker-compose --profile frontend up -d

dev-hybrid: ## Start hybrid mode (Docker services + Manual native model)
	@echo "Starting Life Strands System in hybrid mode..."
	@echo "This will start all Docker services EXCEPT the model service"
	@echo "You need to start the model service manually for GPU access"
	@echo ""
	@$(MAKE) native-up
	@echo "Frontend applications started:"
	@echo "  Chat Interface:    http://localhost:3001"
	@echo "  Admin Dashboard:   http://localhost:3002"

frontend-down: ## Stop frontend applications
	@echo "Stopping frontend applications..."
	@docker-compose --profile frontend down

dev-down: ## Stop all development services
	@echo "Stopping Life Strands System..."
	@echo "Step 1: Stopping native Windows model service..."
	@if grep -qi microsoft /proc/version 2>/dev/null; then \
		echo "Detected WSL environment, using WSL-compatible script..."; \
		scripts/stop_model_service_wsl.sh; \
	elif command -v powershell.exe >/dev/null 2>&1; then \
		powershell.exe -ExecutionPolicy Bypass -File "scripts/stop_model_service.ps1"; \
	elif command -v cmd.exe >/dev/null 2>&1; then \
		echo "Using Windows batch script..."; \
		cmd.exe /c scripts\\stop_model_service.bat; \
	else \
		echo "⚠️  Cannot stop model service automatically. Please stop manually."; \
	fi
	@echo ""
	@echo "Step 2: Stopping Docker services..."
	@docker-compose -f docker-compose.native-model.yml down
	@echo "All services stopped."

dev-restart: ## Restart all development services
	@echo "Restarting Life Strands System..."
	@make dev-down
	@make dev-up

dev-build: ## Build all development images
	@echo "Building development images (excluding model service)..."
	@docker-compose -f docker-compose.native-model.yml build --parallel
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
	@docker-compose -f docker-compose.native-model.yml exec postgres psql -U lifestrands_user -d lifestrands -f /docker-entrypoint-initdb.d/001_initial_schema.sql
	@docker-compose -f docker-compose.native-model.yml exec postgres psql -U lifestrands_user -d lifestrands -f /docker-entrypoint-initdb.d/002_add_embeddings.sql
	@echo "Migrations completed."

migrate-reset: ## Reset database and run all migrations
	@echo "Resetting database..."
	@docker-compose -f docker-compose.native-model.yml exec postgres psql -U lifestrands_user -d postgres -c "DROP DATABASE IF EXISTS lifestrands;"
	@docker-compose -f docker-compose.native-model.yml exec postgres psql -U lifestrands_user -d postgres -c "CREATE DATABASE lifestrands;"
	@make migrate
	@echo "Database reset and migrations completed."

seed: ## Seed database with test NPCs
	@echo "Seeding database with test data..."
	@python scripts/seed_database.py
	@echo "Database seeded successfully."

backup: ## Backup database and Redis data
	@echo "Creating backup..."
	@mkdir -p backups
	@docker-compose -f docker-compose.native-model.yml exec postgres pg_dump -U lifestrands_user lifestrands > backups/lifestrands_$(shell date +%Y%m%d_%H%M%S).sql
	@docker-compose -f docker-compose.native-model.yml exec redis redis-cli --rdb backups/redis_$(shell date +%Y%m%d_%H%M%S).rdb
	@echo "Backup completed in backups/"

restore: ## Restore from backup (usage: make restore file=backup.sql)
ifndef file
	@echo "Usage: make restore file=backup_file.sql"
	@echo "Available backups:"
	@ls -la backups/
else
	@echo "Restoring from $(file)..."
	@docker-compose -f docker-compose.native-model.yml exec -T postgres psql -U lifestrands_user lifestrands < backups/$(file)
	@echo "Restore completed."
endif

# ================================
# Monitoring and Logging
# ================================

logs: ## Tail logs from all services or specific service (usage: make logs s=service_name)
ifdef s
	@echo "Showing logs for $(s) service..."
	@docker-compose -f docker-compose.native-model.yml logs -f $(s)
else
	@echo "Showing logs for all services..."
	@docker-compose -f docker-compose.native-model.yml logs -f --tail=100
endif

logs-errors: ## Show only error logs from all services
	@echo "Showing error logs..."
	@docker-compose -f docker-compose.native-model.yml logs --tail=1000 | grep -i error

monitor: ## Open monitoring dashboard in browser
	@echo "Opening monitoring dashboard..."
	@open http://localhost:3000 || xdg-open http://localhost:3000 || echo "Please open http://localhost:3000 manually"

health-check: ## Check the health of all services
	@echo "Checking service health..."
	@echo "================================"
	@echo "Gateway (API):"
	@curl -s http://localhost:8000/health || echo "❌ Gateway not responding"
	@echo ""
	@echo "Model Service:"
	@curl -s http://localhost:8001/health || echo "❌ Model Service not responding"
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
	@docker-compose -f docker-compose.native-model.yml exec postgres pg_isready -U lifestrands_user -d lifestrands && echo "✅ Database healthy" || echo "❌ Database not healthy"
	@echo "Redis:"
	@docker-compose -f docker-compose.native-model.yml exec redis redis-cli ping && echo "✅ Redis healthy" || echo "❌ Redis not healthy"

# ================================
# Model Management Commands
# ================================

model-status: ## Check model service status and current loaded model
	@echo "Model Service Status:"
	@curl -s http://localhost:8001/status | python -m json.tool || echo "Model service not responding"

model-reload: ## Force model reload
	@echo "Reloading model..."
	@curl -X POST http://localhost:8001/reload || echo "Failed to reload model"

model-switch: ## Switch between chat and summary models (usage: make model-switch type=chat|summary)
ifndef type
	@echo "Usage: make model-switch type=chat|summary"
else
	@echo "Switching to $(type) model..."
	@curl -X POST http://localhost:8001/switch/$(type) || echo "Failed to switch model"
endif

model-unload: ## Unload current model to free VRAM
	@echo "Unloading current model..."
	@curl -X POST http://localhost:8001/unload || echo "Failed to unload model"

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
	@docker-compose -f docker-compose.native-model.yml exec redis redis-cli FLUSHDB
	@echo "Redis queues cleared."

reset-model: ## Reset model to idle state
	@echo "Resetting model state..."
	@curl -X POST http://localhost:8001/reset || echo "Failed to reset model"
	@echo "Model state reset."

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
	@docker-compose -f docker-compose.native-model.yml exec $(s) /bin/bash
endif

psql: ## Connect to PostgreSQL database
	@echo "Connecting to database..."
	@docker-compose -f docker-compose.native-model.yml exec postgres psql -U lifestrands_user -d lifestrands

redis-cli: ## Connect to Redis CLI
	@echo "Connecting to Redis..."
	@docker-compose -f docker-compose.native-model.yml exec redis redis-cli

inspect: ## Show detailed container information (usage: make inspect s=service_name)
ifndef s
	@echo "Usage: make inspect s=service_name"
else
	@docker-compose -f docker-compose.native-model.yml exec $(s) ps aux
	@docker-compose -f docker-compose.native-model.yml exec $(s) df -h
	@docker-compose -f docker-compose.native-model.yml exec $(s) free -h
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
# Windows ROCm Commands
# ================================

windows-setup: ## Setup Windows ROCm environment and dependencies
	@echo "Setting up Windows ROCm environment..."
	@echo "Please run this in Windows Command Prompt or PowerShell:"
	@echo ""
	@echo "1. Create virtual environment:"
	@echo "   python -m venv rocm_env"
	@echo "   rocm_env\\Scripts\\activate.bat"
	@echo ""
	@echo "2. Install dependencies:"
	@echo "   pip install --upgrade pip"
	@echo "   pip install --extra-index-url https://abetlen.github.io/llama-cpp-python/whl/rocm llama-cpp-python"
	@echo "   pip install fastapi uvicorn redis psutil pydantic python-multipart aiofiles"
	@echo ""
	@echo "3. Start Windows model service:"
	@echo "   python run_model_service_windows.py"

windows-start: ## Start Windows ROCm model service (run in Windows)
	@echo "Starting Windows ROCm model service..."
	@echo "Please run this command in Windows (not WSL):"
	@echo "  python run_model_service_windows.py"
	@echo ""
	@echo "The service will be available at:"
	@echo "  http://localhost:8001 (Windows host)"

windows-test: ## Test Windows ROCm setup
	@echo "Testing Windows ROCm setup..."
	@echo "Please run these commands in Windows Command Prompt:"
	@echo ""
	@echo "1. Test ROCm installation:"
	@echo "   \"C:\\Program Files\\AMD\\ROCm\\6.2\\bin\\hipInfo.exe\""
	@echo ""
	@echo "2. Test Python dependencies:"
	@echo "   python test_install.py"
	@echo ""
	@echo "3. Test model service (if running):"
	@echo "   curl http://localhost:8001/health"
	@echo "   curl http://localhost:8001/status"

windows-status: ## Check Windows ROCm model service status (from WSL)
	@echo "Checking Windows ROCm model service status..."
	@curl -s http://172.31.64.1:8001/health && echo "✅ Windows service healthy" || echo "❌ Windows service not responding"
	@echo ""
	@echo "Detailed status:"
	@curl -s http://172.31.64.1:8001/status | python3 -m json.tool || echo "❌ Failed to get status"

windows-switch-chat: ## Switch to chat model on Windows service
	@echo "Switching to chat model on Windows service..."
	@curl -s -X POST http://172.31.64.1:8001/switch/chat | python3 -m json.tool || echo "❌ Failed to switch model"

windows-switch-summary: ## Switch to summary model on Windows service
	@echo "Switching to summary model on Windows service..."
	@curl -s -X POST http://172.31.64.1:8001/switch/summary | python3 -m json.tool || echo "❌ Failed to switch model"

windows-generate-test: ## Test text generation on Windows service
	@echo "Testing text generation on Windows ROCm service..."
	@echo '{"prompt": "Test GPU acceleration with ROCm", "max_tokens": 50}' | curl -s -X POST http://172.31.64.1:8001/generate -H "Content-Type: application/json" -d @- | python3 -m json.tool || echo "❌ Generation test failed"

windows-hybrid: ## Start hybrid mode (Docker services + Windows model service)
	@echo "Starting hybrid mode: Docker services + Windows ROCm model service"
	@echo "Step 1: Stopping Docker model service..."
	@docker stop lifestrands-model-service 2>/dev/null || echo "Model service already stopped"
	@echo "Step 2: Starting other Docker services..."
	@docker-compose --profile dev-tools --profile monitoring up -d postgres redis gateway-service chat-service npc-service summary-service monitor-service grafana prometheus pgadmin redis-commander
	@echo ""
	@echo "Step 3: Start Windows model service manually:"
	@echo "  In Windows: python run_model_service_windows.py"
	@echo ""
	@echo "Available services:"
	@echo "  Gateway API:       http://localhost:8000"
	@echo "  Model Service:     http://localhost:8001 (Windows ROCm)"
	@echo "  Other services:    Docker containers"

windows-info: ## Show Windows ROCm system information
	@echo "Windows ROCm System Information:"
	@echo "================================"
	@echo "Model Service Status:"
	@curl -s http://172.31.64.1:8001/status | python3 -m json.tool 2>/dev/null || echo "❌ Windows service not running"
	@echo ""
	@echo "Docker Services Status:"
	@docker-compose ps | grep -v "model-service" || echo "No Docker services running"
	@echo ""
	@echo "Expected Model Files:"
	@echo "  Chat Model:    Models/Gryphe_Codex-24B-Small-3.2-Q6_K_L.gguf"
	@echo "  Summary Model: Models/dphn.Dolphin-Mistral-24B-Venice-Edition.Q6_K.gguf"

# ================================
# Quick Start Shortcuts
# ================================

start: dev-up ## Alias for dev-up
stop: dev-down ## Alias for dev-down
restart: dev-restart ## Alias for dev-restart
status: health-check ## Alias for health-check
log: logs ## Alias for logs