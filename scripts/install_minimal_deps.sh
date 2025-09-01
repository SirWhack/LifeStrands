#!/bin/bash
# Minimal Dependencies Installation (Python 3.12 Compatible)
# This script installs only essential dependencies to get started

set -e

# Colors for output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

echo -e "${BLUE}Installing minimal Life Strands dependencies for Python 3.12...${NC}"

# Update system packages
echo -e "${BLUE}Updating system packages...${NC}"
sudo apt update

# Install only essential system dependencies
echo -e "${BLUE}Installing essential system dependencies...${NC}"
sudo apt install -y \
    python3 \
    python3-pip \
    python3-venv \
    python3-dev \
    build-essential \
    libpq-dev \
    postgresql-client \
    redis-tools \
    curl \
    git

# Remove existing virtual environment
if [ -d "venv" ]; then
    echo -e "${YELLOW}Removing existing virtual environment...${NC}"
    rm -rf venv
fi

# Create fresh virtual environment
echo -e "${BLUE}Creating fresh Python virtual environment...${NC}"
python3 -m venv venv --without-pip

# Activate virtual environment
source venv/bin/activate

# Install pip manually to avoid setuptools issues
echo -e "${BLUE}Installing pip manually...${NC}"
curl https://bootstrap.pypa.io/get-pip.py -o get-pip.py
python get-pip.py
rm get-pip.py

# Install compatible setuptools and wheel
echo -e "${BLUE}Installing compatible build tools...${NC}"
python -m pip install "setuptools==68.2.2" "wheel==0.41.2"

# Install only essential packages first
echo -e "${BLUE}Installing essential Python packages...${NC}"
python -m pip install --only-binary=all \
    fastapi==0.104.1 \
    uvicorn==0.24.0 \
    pydantic==2.5.0 \
    python-dotenv==1.0.0

# Install database packages (avoid psycopg2 compilation issues)
echo -e "${BLUE}Installing database packages...${NC}"
python -m pip install --only-binary=all \
    asyncpg==0.29.0

# Try psycopg2-binary with fallback
echo -e "${BLUE}Installing PostgreSQL adapter...${NC}"
if ! python -m pip install --only-binary=all psycopg2-binary==2.9.7; then
    echo -e "${YELLOW}psycopg2-binary failed, skipping (asyncpg will work instead)${NC}"
fi

# Install Redis client
echo -e "${BLUE}Installing Redis client...${NC}"
python -m pip install --only-binary=all redis==5.0.1

# Install web dependencies
echo -e "${BLUE}Installing web dependencies...${NC}"
python -m pip install --only-binary=all \
    aiohttp==3.9.0 \
    httpx==0.25.2 \
    websockets==12.0

# Install auth dependencies  
echo -e "${BLUE}Installing auth dependencies...${NC}"
python -m pip install --only-binary=all \
    PyJWT==2.8.0 \
    bcrypt==4.0.1 \
    passlib==1.7.4

# Create minimal configuration
if [ ! -f ".env.minimal" ]; then
    echo -e "${BLUE}Creating minimal configuration...${NC}"
    cat > .env.minimal << 'EOF'
# Minimal Life Strands Configuration
DATABASE_URL=postgresql://lifestrands_user:lifestrands_password@localhost:5432/lifestrands
REDIS_URL=redis://:redis_password@localhost:6379
MODEL_SERVICE_URL=http://localhost:8001
LOG_LEVEL=INFO
MAX_CONCURRENT_CONVERSATIONS=10
ENABLE_EMBEDDINGS=false
EOF
fi

# Create directories
mkdir -p logs pids

echo ""
echo -e "${GREEN}✅ Minimal dependencies installed successfully!${NC}"
echo ""
echo -e "${BLUE}Next steps:${NC}"
echo "1. Start infrastructure: docker-compose -f docker-compose.infrastructure.yml up -d postgres redis"
echo "2. Activate environment: source venv/bin/activate"  
echo "3. Test a service: cd services/gateway-service && python main.py"
echo ""
echo -e "${YELLOW}Note: This is a minimal installation. Some features may not work.${NC}"
echo -e "${YELLOW}If you need full functionality, try the Docker deployment instead.${NC}"