#!/bin/bash
# Start Life Strands Services Natively in WSL2
# Usage: ./scripts/start_native_services.sh [service_name]
# If no service specified, starts all services

set -e

# Configuration
VENV_PATH="$(pwd)/venv"
ENV_FILE="$(pwd)/.env.native"
LOG_DIR="$(pwd)/logs"
PID_DIR="$(pwd)/pids"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m' 
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Ensure directories exist
mkdir -p "$LOG_DIR" "$PID_DIR"

# Check if virtual environment exists
if [ ! -d "$VENV_PATH" ]; then
    echo -e "${RED}Virtual environment not found. Run: ./scripts/setup_native_env.sh${NC}"
    exit 1
fi

# Activate virtual environment
source "$VENV_PATH/bin/activate"

# Load environment variables
if [ -f "$ENV_FILE" ]; then
    set -a
    source "$ENV_FILE" 
    set +a
    echo -e "${GREEN}Loaded environment from $ENV_FILE${NC}"
else
    echo -e "${YELLOW}Warning: $ENV_FILE not found, using defaults${NC}"
fi

# Service definitions
declare -A SERVICES=(
    ["gateway"]="services/gateway-service/main.py:8000"
    ["chat"]="services/chat-service/main.py:8002"
    ["npc"]="services/npc-service/main.py:8003"
    ["summary"]="services/summary-service/main.py:8004"
    ["monitor"]="services/monitor-service/main.py:8005"
)

# Function to start a single service
start_service() {
    local service_name=$1
    local service_info=${SERVICES[$service_name]}
    
    if [ -z "$service_info" ]; then
        echo -e "${RED}Unknown service: $service_name${NC}"
        return 1
    fi
    
    local service_path=$(echo "$service_info" | cut -d: -f1)
    local service_port=$(echo "$service_info" | cut -d: -f2)
    local pid_file="$PID_DIR/${service_name}.pid"
    local log_file="$LOG_DIR/${service_name}.log"
    
    # Check if service is already running
    if [ -f "$pid_file" ] && kill -0 $(cat "$pid_file") 2>/dev/null; then
        echo -e "${YELLOW}Service $service_name is already running (PID: $(cat $pid_file))${NC}"
        return 0
    fi
    
    # Check if required file exists
    if [ ! -f "$service_path" ]; then
        echo -e "${RED}Service file not found: $service_path${NC}"
        return 1
    fi
    
    echo -e "${BLUE}Starting $service_name service on port $service_port...${NC}"
    
    # Start service with uvicorn
    cd "$(dirname "$service_path")"
    uvicorn main:app \
        --host 0.0.0.0 \
        --port "$service_port" \
        --reload \
        > "$log_file" 2>&1 &
    
    local service_pid=$!
    echo $service_pid > "$pid_file"
    
    # Return to original directory
    cd - > /dev/null
    
    # Wait a moment and check if service started successfully
    sleep 2
    if kill -0 $service_pid 2>/dev/null; then
        echo -e "${GREEN}✅ Service $service_name started successfully (PID: $service_pid)${NC}"
        echo -e "   📋 Logs: $log_file"
        echo -e "   🌐 URL: http://localhost:$service_port"
    else
        echo -e "${RED}❌ Failed to start service $service_name${NC}"
        echo -e "   📋 Check logs: $log_file"
        rm -f "$pid_file"
        return 1
    fi
}

# Function to stop a service
stop_service() {
    local service_name=$1
    local pid_file="$PID_DIR/${service_name}.pid"
    
    if [ ! -f "$pid_file" ]; then
        echo -e "${YELLOW}Service $service_name is not running${NC}"
        return 0
    fi
    
    local service_pid=$(cat "$pid_file")
    if kill -0 $service_pid 2>/dev/null; then
        echo -e "${BLUE}Stopping $service_name service (PID: $service_pid)...${NC}"
        kill $service_pid
        rm -f "$pid_file"
        echo -e "${GREEN}✅ Service $service_name stopped${NC}"
    else
        echo -e "${YELLOW}Service $service_name was not running (stale PID file)${NC}"
        rm -f "$pid_file"
    fi
}

# Function to check service status
check_service_status() {
    local service_name=$1
    local service_info=${SERVICES[$service_name]}
    local service_port=$(echo "$service_info" | cut -d: -f2)
    local pid_file="$PID_DIR/${service_name}.pid"
    
    if [ -f "$pid_file" ] && kill -0 $(cat "$pid_file") 2>/dev/null; then
        local pid=$(cat "$pid_file")
        echo -e "${GREEN}✅ $service_name: Running (PID: $pid, Port: $service_port)${NC}"
        
        # Check if port is actually listening
        if curl -s http://localhost:$service_port/health > /dev/null 2>&1; then
            echo -e "   🌐 Health check: OK"
        else
            echo -e "   ⚠️  Health check: Failed (service may be starting)"
        fi
    else
        echo -e "${RED}❌ $service_name: Not running${NC}"
        [ -f "$pid_file" ] && rm -f "$pid_file"
    fi
}

# Function to show all service status
show_status() {
    echo -e "${BLUE}Life Strands Native Services Status:${NC}"
    echo "======================================"
    for service in "${!SERVICES[@]}"; do
        check_service_status "$service"
    done
}

# Function to stop all services
stop_all() {
    echo -e "${BLUE}Stopping all native services...${NC}"
    for service in "${!SERVICES[@]}"; do
        stop_service "$service"
    done
}

# Main script logic
case "${1:-start}" in
    "start")
        if [ -n "$2" ]; then
            start_service "$2"
        else
            echo -e "${BLUE}Starting all Life Strands native services...${NC}"
            # Start services in dependency order
            for service in gateway chat npc summary monitor; do
                start_service "$service"
                sleep 1  # Small delay between service starts
            done
            echo ""
            echo -e "${GREEN}🚀 All services started!${NC}"
            show_status
        fi
        ;;
    "stop")
        if [ -n "$2" ]; then
            stop_service "$2"
        else
            stop_all
        fi
        ;;
    "restart")
        if [ -n "$2" ]; then
            stop_service "$2"
            sleep 2
            start_service "$2"
        else
            stop_all
            sleep 2
            echo -e "${BLUE}Restarting all services...${NC}"
            for service in gateway chat npc summary monitor; do
                start_service "$service"
                sleep 1
            done
        fi
        ;;
    "status")
        show_status
        ;;
    "logs")
        if [ -n "$2" ]; then
            local log_file="$LOG_DIR/$2.log"
            if [ -f "$log_file" ]; then
                tail -f "$log_file"
            else
                echo -e "${RED}Log file not found: $log_file${NC}"
            fi
        else
            echo -e "${BLUE}Available log files:${NC}"
            ls -la "$LOG_DIR"/*.log 2>/dev/null || echo "No log files found"
        fi
        ;;
    *)
        echo "Usage: $0 [start|stop|restart|status|logs] [service_name]"
        echo ""
        echo "Available services: ${!SERVICES[*]}"
        echo ""
        echo "Examples:"
        echo "  $0 start           # Start all services"
        echo "  $0 start chat      # Start chat service only"
        echo "  $0 stop            # Stop all services"
        echo "  $0 status          # Show service status"
        echo "  $0 logs chat       # Show chat service logs"
        echo "  $0 restart         # Restart all services"
        exit 1
        ;;
esac