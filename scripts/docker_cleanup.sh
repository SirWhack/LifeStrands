#!/bin/bash
# Docker Cleanup Script
# Cleans up orphaned containers, networks, and unused resources

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo -e "${BLUE}Docker Cleanup for Life Strands${NC}"
echo "==============================="

# Stop all running Life Strands containers
echo -e "${BLUE}Stopping Life Strands containers...${NC}"
sudo docker ps --filter "name=lifestrands" --format "table {{.Names}}" | grep -v NAMES | xargs -r sudo docker stop || echo "No Life Strands containers running"

# Remove Life Strands containers
echo -e "${BLUE}Removing Life Strands containers...${NC}"
sudo docker ps -a --filter "name=lifestrands" --format "table {{.Names}}" | grep -v NAMES | xargs -r sudo docker rm || echo "No Life Strands containers to remove"

# Remove Life Strands networks
echo -e "${BLUE}Removing Life Strands networks...${NC}"
sudo docker network ls --filter "name=lifestrands" --format "table {{.Name}}" | grep -v NAME | xargs -r sudo docker network rm || echo "No Life Strands networks to remove"

# Clean up orphaned containers
echo -e "${BLUE}Removing orphaned containers...${NC}"
sudo docker container prune -f

# Clean up unused networks  
echo -e "${BLUE}Removing unused networks...${NC}"
sudo docker network prune -f

# Clean up unused volumes
echo -e "${BLUE}Removing unused volumes...${NC}"
sudo docker volume prune -f

# Clean up unused images
echo -e "${BLUE}Removing unused images...${NC}"
sudo docker image prune -f

# Show current Docker status
echo ""
echo -e "${GREEN}Cleanup completed!${NC}"
echo ""
echo -e "${BLUE}Current Docker status:${NC}"
echo "Containers:"
sudo docker ps -a --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"
echo ""
echo "Networks:"
sudo docker network ls --format "table {{.Name}}\t{{.Driver}}\t{{.Scope}}"
echo ""
echo "Volumes:"
sudo docker volume ls --format "table {{.Name}}\t{{.Driver}}"

echo ""
echo -e "${GREEN}✅ Docker cleanup completed successfully!${NC}"