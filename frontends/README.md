# Life Strands Frontend Components

This directory contains the React-based frontend components for the Life Strands system.

## Components

### Chat Interface (`chat-interface/`)
- **Port**: 3000
- **Description**: User-facing chat interface for interacting with NPCs
- **Key Features**:
  - Real-time WebSocket chat with NPCs
  - NPC library and selection
  - Conversation history
  - Responsive Material-UI design

### Admin Dashboard (`admin-dashboard/`)
- **Port**: 3001
- **Description**: Administrative dashboard for system monitoring
- **Key Features**:
  - Real-time system metrics visualization
  - Alert management
  - Service health monitoring
  - Performance analytics

## Development Setup

### Prerequisites
- Node.js 16+ 
- npm or yarn

### Installation

```bash
# Install chat interface dependencies
cd chat-interface
npm install

# Install admin dashboard dependencies  
cd ../admin-dashboard
npm install
```

### Running in Development Mode

```bash
# Start chat interface (http://localhost:3000)
cd chat-interface
npm run dev

# Start admin dashboard (http://localhost:3001)
cd admin-dashboard
npm run dev
```

### Building for Production

```bash
# Build chat interface
cd chat-interface
npm run build

# Build admin dashboard
cd admin-dashboard
npm run build
```

## Architecture

### Chat Interface
- **Framework**: React 18 + TypeScript
- **Build Tool**: Vite
- **UI Library**: Material-UI v5
- **State Management**: Zustand + React Query
- **WebSocket**: Native WebSocket with custom hooks

### Admin Dashboard
- **Framework**: React 18 + TypeScript
- **Build Tool**: Vite
- **UI Library**: Material-UI v5 + MUI X Charts
- **Charting**: Recharts
- **State Management**: Zustand + React Query
- **Real-time Updates**: WebSocket + Server-Sent Events

## Key Hooks

### useWebSocket
Manages WebSocket connections with auto-reconnect:
```typescript
const { socket, connectionState, sendMessage } = useWebSocket({
  url: 'ws://localhost:8002/ws',
  shouldReconnect: true
});
```

### useNPC
Handles NPC data operations:
```typescript
const { npcs, fetchNPC, createNPC, updateNPC } = useNPC();
```

### useMonitoring
Manages system monitoring data:
```typescript
const { metrics, alerts, healthStatus } = useMonitoring({
  enableRealTime: true
});
```

## API Integration

Both frontends integrate with the Life Strands backend services:

- **Gateway**: http://localhost:8000/api
- **Chat WebSocket**: ws://localhost:8002/ws
- **Monitoring WebSocket**: ws://localhost:8006/ws

## Security

- JWT token authentication
- API key support for service communication
- CORS configuration for development
- CSP headers in production builds

## Deployment

### Docker Support
Both frontends include Dockerfile configurations for containerized deployment.

### Environment Variables
- `VITE_API_BASE_URL`: Backend API URL
- `VITE_WS_URL`: WebSocket server URL
- `VITE_MONITORING_WS_URL`: Monitoring WebSocket URL

## Contributing

1. Follow TypeScript strict mode
2. Use Material-UI components consistently
3. Implement proper error boundaries
4. Add loading states for async operations
5. Write unit tests for custom hooks
6. Follow React best practices

## Testing

```bash
# Run type checking
npm run type-check

# Run linting
npm run lint

# Future: Unit tests
npm test
```