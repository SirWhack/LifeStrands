import { useState, useEffect, useRef, useCallback } from 'react';

export interface WebSocketMessage {
  type: string;
  data?: any;
  error?: string;
  timestamp?: string;
  conversation_id?: string;
  npc_id?: string;
  content?: string;
  chunk?: string;
  message?: string;
  subscription?: string;
  sequence?: number;
  token?: string;
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
  fallbackUrls?: string[];
  token?: string;
  enableFallback?: boolean;
  heartbeatInterval?: number;
  maxMessageQueueSize?: number;
}

export const useWebSocket = (options: UseWebSocketOptions = {}): WebSocketHookReturn => {
  const {
    url = 'ws://localhost:8000/ws', // Use Gateway port as primary
    protocols,
    onOpen,
    onClose,
    onMessage,
    onError,
    shouldReconnect = true,
    reconnectInterval = 5000,
    maxReconnectAttempts = 20,
    fallbackUrls = ['ws://localhost:8002/ws'], // Chat service as fallback
    token,
    enableFallback = true,
    heartbeatInterval = 60000, // 60 seconds
    maxMessageQueueSize = 100
  } = options;

  const [socket, setSocket] = useState<WebSocket | null>(null);
  const [connectionState, setConnectionState] = useState<'connecting' | 'connected' | 'disconnected' | 'error'>('disconnected');
  const [lastMessage, setLastMessage] = useState<WebSocketMessage | null>(null);
  const [connectionError, setConnectionError] = useState<string | null>(null);
  const [isTyping, setIsTyping] = useState(false);

  const reconnectAttempts = useRef(0);
  const reconnectTimeoutId = useRef<NodeJS.Timeout>();
  const shouldConnect = useRef(true);
  const currentUrlIndex = useRef(0);
  const messageQueue = useRef<WebSocketMessage[]>([]);  // Queue for offline messages
  const heartbeatTimeoutId = useRef<NodeJS.Timeout>();
  const sequenceNumber = useRef(0);
  const connectionStartTime = useRef<number>(Date.now());

  const connect = useCallback(() => {
    const currentUrl = getCurrentUrl();
    if (!currentUrl || socket?.readyState === WebSocket.OPEN) {
      return;
    }

    setConnectionState('connecting');
    setConnectionError(null);
    connectionStartTime.current = Date.now();

    try {
      const wsUrl = token ? `${currentUrl}?token=${encodeURIComponent(token)}` : currentUrl;
      const ws = new WebSocket(wsUrl, protocols);

      ws.onopen = (event) => {
        console.log('WebSocket connected');
        setSocket(ws);
        setConnectionState('connected');
        reconnectAttempts.current = 0;
        // Reset connection attempts and URL index on successful connection
        currentUrlIndex.current = 0;
        
        // Process any queued messages (limit to prevent overwhelming)
        if (messageQueue.current.length > 0) {
          console.log(`Processing ${Math.min(messageQueue.current.length, maxMessageQueueSize)} queued messages`);
          const messagesToProcess = messageQueue.current.splice(0, maxMessageQueueSize);
          messagesToProcess.forEach(message => {
            ws.send(JSON.stringify({
              ...message,
              timestamp: new Date().toISOString(),
              sequence: ++sequenceNumber.current
            }));
          });
        }
        
        // Send initial ping to keep connection alive
        ws.send(JSON.stringify({
          type: 'ping',
          timestamp: new Date().toISOString()
        }));

        // Start heartbeat with configurable interval
        const startHeartbeat = () => {
          heartbeatTimeoutId.current = setInterval(() => {
            if (ws.readyState === WebSocket.OPEN) {
              ws.send(JSON.stringify({
                type: 'ping',
                timestamp: new Date().toISOString(),
                sequence: ++sequenceNumber.current
              }));
            }
          }, heartbeatInterval);
        };
        startHeartbeat();
        
        onOpen?.(event);
      };

      ws.onclose = (event) => {
        console.log('WebSocket disconnected:', event.code, event.reason);
        setSocket(null);
        setConnectionState('disconnected');
        
        // Clean up heartbeat interval
        if (heartbeatTimeoutId.current) {
          clearInterval(heartbeatTimeoutId.current);
        }
        
        onClose?.(event);

        // Auto-reconnect with fallback strategy
        if (shouldReconnect && shouldConnect.current && event.code !== 1000 && event.code !== 1001) {
          handleReconnection();
        }
      };

      ws.onerror = (event) => {
        console.error('WebSocket error:', event);
        const errorMessage = getContextualErrorMessage(event);
        setConnectionError(errorMessage);
        setConnectionState('error');
        onError?.(event);
        
        // Try fallback URL on error if available
        if (enableFallback && hasNextUrl()) {
          console.log('Trying fallback URL due to connection error');
          tryNextUrl();
        }
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
      setConnectionError(`Failed to create WebSocket connection: ${error instanceof Error ? error.message : 'Unknown error'}`);
      setConnectionState('error');
      
      // Try fallback URL on connection creation error
      if (enableFallback && hasNextUrl()) {
        console.log('Trying fallback URL due to connection creation error');
        tryNextUrl();
      }
    }
  }, [url, protocols, shouldReconnect, reconnectInterval, maxReconnectAttempts, fallbackUrls, token, enableFallback, heartbeatInterval, maxMessageQueueSize]);

  const disconnect = useCallback(() => {
    shouldConnect.current = false;
    
    // Clear all timeouts
    if (reconnectTimeoutId.current) {
      clearTimeout(reconnectTimeoutId.current);
    }
    if (heartbeatTimeoutId.current) {
      clearInterval(heartbeatTimeoutId.current);
    }

    if (socket) {
      socket.close(1000, 'Client disconnect');
    }
  }, [socket]);

  const sendMessage = useCallback((message: WebSocketMessage) => {
    if (socket?.readyState === WebSocket.OPEN) {
      const messageWithMetadata = {
        ...message,
        timestamp: new Date().toISOString(),
        sequence: ++sequenceNumber.current
      };
      
      try {
        socket.send(JSON.stringify(messageWithMetadata));
      } catch (error) {
        console.error('Error sending message:', error);
        // Queue message on send error
        if (message.type !== 'ping' && messageQueue.current.length < maxMessageQueueSize) {
          messageQueue.current.push(message);
          setConnectionError('Message queued due to send error');
        }
      }
    } else {
      // Queue message for when connection is restored (except pings)
      if (message.type !== 'ping' && messageQueue.current.length < maxMessageQueueSize) {
        console.log('WebSocket not connected, queuing message:', message.type);
        messageQueue.current.push(message);
        setConnectionError('Message queued - reconnecting...');
      } else if (messageQueue.current.length >= maxMessageQueueSize) {
        console.warn('Message queue full, dropping message:', message.type);
      } else {
        console.warn('Cannot send ping: WebSocket is not connected');
      }
    }
  }, [socket, maxMessageQueueSize]);

  // Stable connect function
  const connectStable = useCallback(() => {
    if (url) {
      shouldConnect.current = true;
      connect();
    }
  }, [url, connect]);

  // Auto-connect on mount and when URL changes
  useEffect(() => {
    if (url) {
      connectStable();
    } else {
      shouldConnect.current = false;
    }

    return () => {
      shouldConnect.current = false;
      if (reconnectTimeoutId.current) {
        clearTimeout(reconnectTimeoutId.current);
      }
    };
  }, [url, connectStable]);

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      if (reconnectTimeoutId.current) {
        clearTimeout(reconnectTimeoutId.current);
      }
      if (heartbeatTimeoutId.current) {
        clearInterval(heartbeatTimeoutId.current);
      }
    };
  }, []);

  // Helper functions
  const getCurrentUrl = useCallback(() => {
    const urls = [url, ...fallbackUrls];
    return urls[currentUrlIndex.current] || url;
  }, [url, fallbackUrls]);

  const hasNextUrl = useCallback(() => {
    const urls = [url, ...fallbackUrls];
    return currentUrlIndex.current < urls.length - 1;
  }, [url, fallbackUrls]);

  const tryNextUrl = useCallback(() => {
    if (hasNextUrl()) {
      currentUrlIndex.current++;
      console.log(`Trying fallback URL: ${getCurrentUrl()}`);
      reconnectAttempts.current = 0; // Reset attempts for new URL
      connect();
    }
  }, [hasNextUrl, getCurrentUrl, connect]);

  const handleReconnection = useCallback(() => {
    if (reconnectAttempts.current < maxReconnectAttempts) {
      reconnectAttempts.current++;
      
      // Exponential backoff: increase delay with each attempt
      const backoffDelay = Math.min(reconnectInterval * Math.pow(1.5, reconnectAttempts.current - 1), 30000);
      console.log(`Attempting reconnect ${reconnectAttempts.current}/${maxReconnectAttempts} to ${getCurrentUrl()} in ${backoffDelay}ms`);
      
      reconnectTimeoutId.current = setTimeout(() => {
        if (shouldConnect.current) {
          connect();
        }
      }, backoffDelay);
    } else if (enableFallback && hasNextUrl()) {
      console.log('Max reconnection attempts reached, trying fallback URL');
      tryNextUrl();
    } else {
      // Implement graceful degradation instead of hard stop
      console.log('All connection options exhausted. Entering graceful degradation mode.');
      setConnectionError('Connection lost. Click reconnect to retry or refresh the page.');
      setConnectionState('error');
      
      // Allow manual reconnection after a cooldown period
      setTimeout(() => {
        if (shouldConnect.current) {
          console.log('Cooldown period ended. Allowing reconnection attempts.');
          reconnectAttempts.current = 0;
          currentUrlIndex.current = 0; // Reset to primary URL
        }
      }, 60000); // 60 second cooldown
    }
  }, [reconnectAttempts.current, maxReconnectAttempts, reconnectInterval, enableFallback, hasNextUrl, tryNextUrl, getCurrentUrl, connect]);

  const getContextualErrorMessage = useCallback((event: Event) => {
    const connectionDuration = Date.now() - connectionStartTime.current;
    
    if (connectionDuration < 5000) {
      return 'Connection failed immediately. Check if the service is running.';
    } else if (connectionDuration < 30000) {
      return 'Connection lost unexpectedly. Attempting to reconnect...';
    } else {
      return 'Long-running connection lost. This may be due to network issues.';
    }
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
    ? `ws://localhost:8000/ws${token ? `?token=${token}` : ''}` // Use Gateway
    : '';

  console.log('useConversationWebSocket - conversationId:', conversationId, 'wsUrl:', wsUrl);

  const webSocketOptions = conversationId ? {
    url: wsUrl,
    fallbackUrls: ['ws://localhost:8002/ws'], // Chat service fallback
    token,
    enableFallback: true,
    shouldReconnect: true,
    onMessage: (message) => {
      console.log('Conversation message:', message);
    },
    onError: (error) => {
      console.error('Conversation WebSocket error:', error);
    }
  } : {
    url: '',
    shouldReconnect: false
  };

  return useWebSocket(webSocketOptions);
};

// Hook for monitoring WebSocket
export const useMonitoringWebSocket = (subscriptions: string[] = []) => {
  const wsUrl = 'ws://localhost:8000/monitor/ws'; // Route through Gateway

  const webSocket = useWebSocket({
    url: wsUrl,
    fallbackUrls: ['ws://localhost:8005/ws'], // Monitor service fallback
    enableFallback: true,
    heartbeatInterval: 30000, // More frequent for monitoring
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