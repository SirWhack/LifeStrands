#!/bin/bash
# Fix WSL Docker Issues
# Handles Docker daemon issues in WSL environment

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo -e "${BLUE}Fixing WSL Docker Issues${NC}"
echo "======================="

echo -e "${BLUE}1. Checking WSL distributions...${NC}"
powershell.exe -c "wsl -l -v" || echo "Cannot access WSL from Linux side"

echo -e "${BLUE}2. Stopping Docker service...${NC}"
sudo service docker stop || echo "Docker service not running"

echo -e "${BLUE}3. Cleaning Docker daemon state...${NC}"
sudo rm -rf /var/lib/docker/network/files/local-kv.db || echo "No local-kv.db to remove"

echo -e "${BLUE}4. Starting Docker service...${NC}"
sudo service docker start

echo -e "${BLUE}5. Waiting for Docker to be ready...${NC}"
sleep 5

echo -e "${BLUE}6. Testing Docker daemon...${NC}"
if sudo docker info > /dev/null 2>&1; then
    echo -e "${GREEN}✅ Docker daemon is working${NC}"
else
    echo -e "${RED}❌ Docker daemon still has issues${NC}"
    echo -e "${YELLOW}Try restarting WSL or Docker Desktop${NC}"
fi

echo -e "${BLUE}7. Attempting manual cleanup...${NC}"

# Try to remove any stuck containers manually
echo "Removing containers..."
sudo docker ps -aq | xargs -r sudo docker rm -f || echo "No containers to remove"

# Try to remove networks manually
echo "Removing networks..."
sudo docker network ls --format "{{.Name}}" | grep -v "bridge\|host\|none" | xargs -r sudo docker network rm || echo "No custom networks to remove"

# Try to remove volumes
echo "Removing volumes..."
sudo docker volume ls -q | xargs -r sudo docker volume rm || echo "No volumes to remove"

echo ""
echo -e "${GREEN}Cleanup completed!${NC}"
echo ""
echo -e "${BLUE}Current Docker status:${NC}"
sudo docker ps -a || echo "Cannot list containers"
sudo docker network ls || echo "Cannot list networks"

echo ""
echo -e "${YELLOW}If issues persist, try:${NC}"
echo "1. Restart Docker Desktop (if using Docker Desktop)"
echo "2. Restart WSL: wsl --shutdown (from Windows)"
echo "3. Restart your WSL distribution"