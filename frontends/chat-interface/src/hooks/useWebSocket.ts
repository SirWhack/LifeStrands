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
    reconnectInterval = 5000,
    maxReconnectAttempts = 20
  } = options;

  const [socket, setSocket] = useState<WebSocket | null>(null);
  const [connectionState, setConnectionState] = useState<'connecting' | 'connected' | 'disconnected' | 'error'>('disconnected');
  const [lastMessage, setLastMessage] = useState<WebSocketMessage | null>(null);
  const [connectionError, setConnectionError] = useState<string | null>(null);
  const [isTyping, setIsTyping] = useState(false);

  const reconnectAttempts = useRef(0);
  const reconnectTimeoutId = useRef<NodeJS.Timeout>();
  const shouldConnect = useRef(true);
  const totalReconnectAttempts = useRef(0);  // Track all reconnection attempts across cycles
  const maxTotalReconnectAttempts = 5;  // HARD STOP after 5 total reconnection attempts
  const messageQueue = useRef<WebSocketMessage[]>([]);  // Queue for offline messages

  const connect = useCallback(() => {
    if (!url || socket?.readyState === WebSocket.OPEN) {
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
        // Reset total attempts on successful connection
        totalReconnectAttempts.current = 0;
        
        // Process any queued messages
        if (messageQueue.current.length > 0) {
          console.log(`Processing ${messageQueue.current.length} queued messages`);
          messageQueue.current.forEach(message => {
            ws.send(JSON.stringify({
              ...message,
              timestamp: new Date().toISOString()
            }));
          });
          messageQueue.current = [];
        }
        
        // Send initial ping to keep connection alive
        ws.send(JSON.stringify({
          type: 'ping',
          timestamp: new Date().toISOString()
        }));
        
        onOpen?.(event);
      };

      ws.onclose = (event) => {
        console.log('WebSocket disconnected:', event.code, event.reason);
        setSocket(null);
        setConnectionState('disconnected');
        onClose?.(event);

        // Auto-reconnect if enabled and connection was not closed intentionally
        if (shouldReconnect && shouldConnect.current && event.code !== 1000 && event.code !== 1001) {
          // HARD STOP: Check total reconnection attempts across all cycles
          if (totalReconnectAttempts.current >= maxTotalReconnectAttempts) {
            console.error(`HARD STOP: Maximum total reconnection attempts reached (${totalReconnectAttempts.current}/${maxTotalReconnectAttempts}). Stopping all reconnection attempts.`);
            setConnectionError(`Connection failed after ${maxTotalReconnectAttempts} attempts. Please refresh the page to retry.`);
            setConnectionState('error');
            shouldConnect.current = false;
            return;
          }

          if (reconnectAttempts.current < maxReconnectAttempts) {
            reconnectAttempts.current++;
            totalReconnectAttempts.current++;
            
            // Exponential backoff: increase delay with each attempt
            const backoffDelay = Math.min(reconnectInterval * Math.pow(1.5, reconnectAttempts.current - 1), 30000);
            console.log(`Attempting reconnect ${reconnectAttempts.current}/${maxReconnectAttempts} (total: ${totalReconnectAttempts.current}/${maxTotalReconnectAttempts}) in ${backoffDelay}ms`);
            
            reconnectTimeoutId.current = setTimeout(() => {
              if (shouldConnect.current) {
                connect();
              }
            }, backoffDelay);
          } else {
            console.error('Max reconnection attempts reached for this cycle');
            setConnectionError('Connection lost. Waiting before retry...');
            setConnectionState('disconnected');
            // Reset cycle attempts but keep total count
            setTimeout(() => {
              reconnectAttempts.current = 0;
              if (shouldConnect.current && totalReconnectAttempts.current < maxTotalReconnectAttempts) {
                console.log('Resetting cycle reconnection attempts and trying again...');
                connect();
              }
            }, 30000); // 30 second delay before reset
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
  }, [url, protocols, shouldReconnect, reconnectInterval, maxReconnectAttempts]);

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
      // Queue message for when connection is restored (except pings)
      if (message.type !== 'ping') {
        console.log('WebSocket not connected, queuing message:', message.type);
        messageQueue.current.push(message);
        setConnectionError('Message queued - reconnecting...');
      } else {
        console.warn('Cannot send ping: WebSocket is not connected');
      }
    }
  }, [socket]);

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
    ? `ws://localhost:8002/ws${token ? `?token=${token}` : ''}`
    : '';

  console.log('useConversationWebSocket - conversationId:', conversationId, 'wsUrl:', wsUrl);

  const webSocketOptions = conversationId ? {
    url: wsUrl,
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