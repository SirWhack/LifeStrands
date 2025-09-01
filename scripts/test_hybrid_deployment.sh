#!/bin/bash
# Test Hybrid Deployment
# Validates that infrastructure and native services are working correctly

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m' 
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo -e "${BLUE}Testing Life Strands Hybrid Deployment${NC}"
echo "========================================"

# Test infrastructure services (Docker)
echo -e "${BLUE}Testing Docker Infrastructure Services...${NC}"

# Test PostgreSQL
echo -n "PostgreSQL: "
if pg_isready -h localhost -p 5432 -U lifestrands_user > /dev/null 2>&1; then
    echo -e "${GREEN}✅ Connected${NC}"
else
    echo -e "${RED}❌ Not accessible${NC}"
fi

# Test Redis
echo -n "Redis: "
if redis-cli -h localhost -p 6379 -a redis_password ping > /dev/null 2>&1; then
    echo -e "${GREEN}✅ Connected${NC}"
else
    echo -e "${RED}❌ Not accessible${NC}"
fi

# Test pgAdmin (if running)
echo -n "pgAdmin: "
if curl -s http://localhost:8080 > /dev/null 2>&1; then
    echo -e "${GREEN}✅ Accessible${NC}"
else
    echo -e "${YELLOW}⚠️  Not running${NC}"
fi

# Test Redis Commander (if running)
echo -n "Redis Commander: "
if curl -s http://localhost:8081 > /dev/null 2>&1; then
    echo -e "${GREEN}✅ Accessible${NC}"
else
    echo -e "${YELLOW}⚠️  Not running${NC}"
fi

echo ""
echo -e "${BLUE}Testing Native Services...${NC}"

# Test native services
services=("gateway:8000" "chat:8002" "npc:8003" "summary:8004" "monitor:8005")

for service_info in "${services[@]}"; do
    service_name=$(echo "$service_info" | cut -d: -f1)
    service_port=$(echo "$service_info" | cut -d: -f2)
    
    echo -n "${service_name} Service: "
    
    # Check if service responds
    if curl -s http://localhost:$service_port/health > /dev/null 2>&1; then
        echo -e "${GREEN}✅ Healthy${NC}"
    elif curl -s http://localhost:$service_port > /dev/null 2>&1; then
        echo -e "${YELLOW}⚠️  Responding but no health endpoint${NC}"
    else
        echo -e "${RED}❌ Not responding${NC}"
    fi
done

echo ""
echo -e "${BLUE}Testing Service Communication...${NC}"

# Test model service communication (if available)
echo -n "Model Service Integration: "
if curl -s http://localhost:8001/health > /dev/null 2>&1; then
    echo -e "${GREEN}✅ Model service accessible${NC}"
else
    echo -e "${YELLOW}⚠️  Model service not running (expected if not started)${NC}"
fi

# Test database connectivity from native services
echo -n "Database Integration: "
if curl -s http://localhost:8003/health 2>/dev/null | grep -q "healthy\|ok"; then
    echo -e "${GREEN}✅ NPC service can access database${NC}"
else
    echo -e "${YELLOW}⚠️  Cannot verify database integration${NC}"
fi

# Test Redis connectivity from native services  
echo -n "Redis Integration: "
if curl -s http://localhost:8002/health 2>/dev/null | grep -q "healthy\|ok"; then
    echo -e "${GREEN}✅ Chat service can access Redis${NC}"
else
    echo -e "${YELLOW}⚠️  Cannot verify Redis integration${NC}"
fi

echo ""
echo -e "${BLUE}Testing API Gateway Routing...${NC}"

# Test gateway routing to native services
echo -n "Gateway → Chat Service: "
if curl -s http://localhost:8000/chat/health > /dev/null 2>&1; then
    echo -e "${GREEN}✅ Routing works${NC}"
else
    echo -e "${YELLOW}⚠️  Cannot verify routing${NC}"
fi

echo -n "Gateway → NPC Service: "
if curl -s http://localhost:8000/npcs/health > /dev/null 2>&1; then
    echo -e "${GREEN}✅ Routing works${NC}"
else
    echo -e "${YELLOW}⚠️  Cannot verify routing${NC}"
fi

echo ""
echo -e "${BLUE}Performance Test (if services are running)...${NC}"

# Simple performance test
if curl -s http://localhost:8000/health > /dev/null 2>&1; then
    echo -n "Gateway Response Time: "
    response_time=$(curl -o /dev/null -s -w "%{time_total}" http://localhost:8000/health)
    if (( $(echo "$response_time < 1.0" | bc -l) )); then
        echo -e "${GREEN}✅ ${response_time}s${NC}"
    else
        echo -e "${YELLOW}⚠️  ${response_time}s (slow)${NC}"
    fi
fi

echo ""
echo -e "${BLUE}Testing Frontend Connectivity (if running)...${NC}"

# Test frontend applications
echo -n "Chat Interface: "
if curl -s http://localhost:3000 > /dev/null 2>&1; then
    echo -e "${GREEN}✅ Accessible${NC}"
else
    echo -e "${YELLOW}⚠️  Not running${NC}"
fi

echo -n "Admin Dashboard: "
if curl -s http://localhost:3002 > /dev/null 2>&1; then
    echo -e "${GREEN}✅ Accessible${NC}"
else
    echo -e "${YELLOW}⚠️  Not running${NC}"
fi

echo ""
echo -e "${BLUE}Resource Usage Check...${NC}"

# Check system resources
echo -n "System Memory: "
mem_usage=$(free | grep Mem | awk '{printf "%.1f%%", $3/$2 * 100.0}')
echo -e "${GREEN}${mem_usage} used${NC}"

echo -n "Disk Space: "
disk_usage=$(df / | tail -1 | awk '{print $5}')
echo -e "${GREEN}${disk_usage} used${NC}"

# Count running processes
echo -n "Docker Containers: "
container_count=$(docker ps --format "table {{.Names}}" | grep lifestrands | wc -l)
echo -e "${GREEN}${container_count} running${NC}"

echo -n "Native Service Processes: "
native_count=$(pgrep -f "uvicorn main:app" | wc -l)
echo -e "${GREEN}${native_count} running${NC}"

echo ""
echo -e "${BLUE}Summary${NC}"
echo "========"

if pg_isready -h localhost -p 5432 > /dev/null 2>&1 && redis-cli ping > /dev/null 2>&1; then
    echo -e "${GREEN}✅ Infrastructure services are running${NC}"
else
    echo -e "${RED}❌ Infrastructure services need attention${NC}"
fi

if curl -s http://localhost:8000/health > /dev/null 2>&1; then
    echo -e "${GREEN}✅ Core native services are responding${NC}"
else
    echo -e "${YELLOW}⚠️  Some native services may not be running${NC}"
fi

echo ""
echo -e "${BLUE}Next steps:${NC}"
echo "• Check any failed services with: ./scripts/start_native_services.sh status"
echo "• View service logs with: make native-logs s=service_name"
echo "• Monitor system with: make hybrid-status"
echo "• Access database admin at: http://localhost:8080"
echo "• Access Redis admin at: http://localhost:8081"

echo ""
echo -e "${GREEN}Hybrid deployment test completed!${NC}"