import { useState, useEffect, useRef, useCallback } from 'react';

export interface WebSocketMessage {
  type: string;
  data?: any;
  error?: string;
  timestamp?: string;
  conversation_id?: string;
}

export interface WebSocketHookReturn {
  socket: WebSocket | null;
  connectionState: 'connecting' | 'connected' | 'disconnected' | 'error';
  sendMessage: (message: WebSocketMessage) => void;
  lastMessage: WebSocketMessage | null;
  connectionError: string | null;
  isTyping: boolean;
  connect: () => void;
  disconnect: () => void;
}

interface UseWebSocketOptions {
  url?: string;
  protocols?: string | string[];
  onOpen?: (event: Event) => void;
  onClose?: (event: CloseEvent) => void;
  onMessage?: (message: WebSocketMessage) => void;
  onError?: (error: Event) => void;
  shouldReconnect?: boolean;
  reconnectInterval?: number;
  maxReconnectAttempts?: number;
}

export const useWebSocket = (options: UseWebSocketOptions = {}): WebSocketHookReturn => {
  const {
    url = 'ws://localhost:8002/ws',
    protocols,
    onOpen,
    onClose,
    onMessage,
    onError,
    shouldReconnect = true,
    reconnectInterval = 3000,
    maxReconnectAttempts = 5
  } = options;

  const [socket, setSocket] = useState<WebSocket | null>(null);
  const [connectionState, setConnectionState] = useState<'connecting' | 'connected' | 'disconnected' | 'error'>('disconnected');
  const [lastMessage, setLastMessage] = useState<WebSocketMessage | null>(null);
  const [connectionError, setConnectionError] = useState<string | null>(null);
  const [isTyping, setIsTyping] = useState(false);

  const reconnectAttempts = useRef(0);
  const reconnectTimeoutId = useRef<NodeJS.Timeout>();
  const shouldConnect = useRef(true);

  const connect = useCallback(() => {
    if (socket?.readyState === WebSocket.OPEN) {
      return;
    }

    setConnectionState('connecting');
    setConnectionError(null);

    try {
      const ws = new WebSocket(url, protocols);

      ws.onopen = (event) => {
        console.log('WebSocket connected');
        setSocket(ws);
        setConnectionState('connected');
        reconnectAttempts.current = 0;
        onOpen?.(event);
      };

      ws.onclose = (event) => {
        console.log('WebSocket disconnected:', event.code, event.reason);
        setSocket(null);
        setConnectionState('disconnected');
        onClose?.(event);

        // Auto-reconnect if enabled and connection was not closed intentionally
        if (shouldReconnect && shouldConnect.current && event.code !== 1000) {
          if (reconnectAttempts.current < maxReconnectAttempts) {
            reconnectAttempts.current++;
            console.log(`Attempting reconnect ${reconnectAttempts.current}/${maxReconnectAttempts}`);
            
            reconnectTimeoutId.current = setTimeout(() => {
              connect();
            }, reconnectInterval);
          } else {
            console.error('Max reconnection attempts reached');
            setConnectionError('Connection lost. Max reconnection attempts reached.');
            setConnectionState('error');
          }
        }
      };

      ws.onerror = (event) => {
        console.error('WebSocket error:', event);
        setConnectionError('WebSocket connection error');
        setConnectionState('error');
        onError?.(event);
      };

      ws.onmessage = (event) => {
        try {
          const message: WebSocketMessage = JSON.parse(event.data);
          setLastMessage(message);

          // Handle typing indicators
          if (message.type === 'typing_start') {
            setIsTyping(true);
          } else if (message.type === 'typing_stop' || message.type === 'message') {
            setIsTyping(false);
          }

          onMessage?.(message);
        } catch (error) {
          console.error('Error parsing WebSocket message:', error);
        }
      };

      setSocket(ws);
    } catch (error) {
      console.error('Error creating WebSocket connection:', error);
      setConnectionError('Failed to create WebSocket connection');
      setConnectionState('error');
    }
  }, [url, protocols, onOpen, onClose, onMessage, onError, shouldReconnect, reconnectInterval, maxReconnectAttempts]);

  const disconnect = useCallback(() => {
    shouldConnect.current = false;
    
    if (reconnectTimeoutId.current) {
      clearTimeout(reconnectTimeoutId.current);
    }

    if (socket) {
      socket.close(1000, 'Client disconnect');
    }
  }, [socket]);

  const sendMessage = useCallback((message: WebSocketMessage) => {
    if (socket?.readyState === WebSocket.OPEN) {
      socket.send(JSON.stringify({
        ...message,
        timestamp: new Date().toISOString()
      }));
    } else {
      console.warn('Cannot send message: WebSocket is not connected');
      setConnectionError('Cannot send message: Not connected');
    }
  }, [socket]);

  // Auto-connect on mount
  useEffect(() => {
    shouldConnect.current = true;
    connect();

    return () => {
      shouldConnect.current = false;
      if (reconnectTimeoutId.current) {
        clearTimeout(reconnectTimeoutId.current);
      }
      if (socket) {
        socket.close(1000, 'Component unmount');
      }
    };
  }, []);

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      if (reconnectTimeoutId.current) {
        clearTimeout(reconnectTimeoutId.current);
      }
    };
  }, []);

  return {
    socket,
    connectionState,
    sendMessage,
    lastMessage,
    connectionError,
    isTyping,
    connect,
    disconnect
  };
};

// Utility hook for conversation-specific WebSocket
export const useConversationWebSocket = (conversationId: string | null, token?: string) => {
  const wsUrl = conversationId 
    ? `ws://localhost:8002/ws/conversations/${conversationId}${token ? `?token=${token}` : ''}`
    : 'ws://localhost:8002/ws';

  return useWebSocket({
    url: wsUrl,
    shouldReconnect: !!conversationId,
    onMessage: (message) => {
      console.log('Conversation message:', message);
    },
    onError: (error) => {
      console.error('Conversation WebSocket error:', error);
    }
  });
};

// Hook for monitoring WebSocket
export const useMonitoringWebSocket = (subscriptions: string[] = []) => {
  const wsUrl = 'ws://localhost:8006/ws';

  const webSocket = useWebSocket({
    url: wsUrl,
    onOpen: () => {
      console.log('Monitoring WebSocket connected');
    }
  });

  // Subscribe to monitoring channels
  useEffect(() => {
    if (webSocket.connectionState === 'connected' && subscriptions.length > 0) {
      subscriptions.forEach(subscription => {
        webSocket.sendMessage({
          type: 'subscribe',
          subscription
        });
      });
    }
  }, [webSocket.connectionState, subscriptions]);

  return webSocket;
};