#!/bin/bash
# Setup Native Environment for Life Strands Services
# This script prepares the WSL2 environment for running services natively

set -e

echo "Setting up Life Strands native environment..."

# Create virtual environment if it doesn't exist
if [ ! -d "venv" ]; then
    echo "Creating Python virtual environment..."
    python3 -m venv venv
fi

# Activate virtual environment
source venv/bin/activate

# Upgrade pip
pip install --upgrade pip

# Install common dependencies
echo "Installing common Python dependencies..."
pip install \
    fastapi \
    uvicorn \
    pydantic \
    asyncio \
    aiohttp \
    redis \
    psycopg2-binary \
    sqlalchemy \
    websockets \
    python-multipart \
    python-dotenv \
    bcrypt \
    PyJWT \
    prometheus_client \
    structlog

# Install service-specific dependencies
echo "Installing service-specific dependencies..."
for service in gateway-service chat-service npc-service summary-service monitor-service; do
    if [ -f "services/$service/requirements.txt" ]; then
        echo "Installing dependencies for $service..."
        pip install -r "services/$service/requirements.txt"
    fi
done

# Create logs directory
mkdir -p logs

# Create environment file if it doesn't exist
if [ ! -f ".env.native" ]; then
    echo "Creating native environment configuration..."
    cat > .env.native << EOF
# Native WSL2 Environment Configuration
DATABASE_URL=postgresql://lifestrands_user:lifestrands_password@localhost:5432/lifestrands
REDIS_URL=redis://:redis_password@localhost:6379
MODEL_SERVICE_URL=http://localhost:8001

# Service URLs (localhost for native services)
GATEWAY_URL=http://localhost:8000
CHAT_SERVICE_URL=http://localhost:8002  
NPC_SERVICE_URL=http://localhost:8003
SUMMARY_SERVICE_URL=http://localhost:8004
MONITOR_SERVICE_URL=http://localhost:8005

# Authentication
JWT_SECRET=your-jwt-secret-here
CORS_ORIGINS=http://localhost:3000,http://localhost:3001,http://localhost:3002

# Service Configuration
MAX_CONCURRENT_CONVERSATIONS=50
CONVERSATION_TIMEOUT_MINUTES=30
RATE_LIMIT_REQUESTS_PER_MINUTE=100

# Model Configuration  
ENABLE_EMBEDDINGS=false
SUMMARY_AUTO_APPROVAL_THRESHOLD=0.8

# Logging
LOG_LEVEL=INFO
EOF
    echo "Created .env.native - please review and customize as needed"
fi

echo "Native environment setup completed!"
echo "Virtual environment: $(pwd)/venv"
echo "Environment file: $(pwd)/.env.native"
echo ""
echo "To activate: source venv/bin/activate"