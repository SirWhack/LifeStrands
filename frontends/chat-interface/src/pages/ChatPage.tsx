import React, { useState, useEffect, useRef, useCallback, useMemo } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import {
  Container,
  Typography,
  Paper,
  Box,
  TextField,
  Button,
  List,
  ListItem,
  Avatar,
  Chip,
  CircularProgress,
  Alert,
  Select,
  MenuItem,
  FormControl,
  InputLabel,
  IconButton,
  Divider
} from '@mui/material';
import {
  Send as SendIcon,
  PersonAdd as PersonAddIcon,
  Refresh as RefreshIcon,
  Stop as StopIcon,
  VolumeUp as SpeakIcon
} from '@mui/icons-material';
import { useWebSocket } from '../hooks/useWebSocket';
import { useNPC } from '../hooks/useNPC';
import { useDemoAuth } from '../contexts/AuthContext'; // Use demo auth for development

interface Message {
  id: string;
  sender: 'user' | 'npc';
  content: string;
  timestamp: string;
  isStreaming?: boolean;
}

const ChatPage: React.FC = () => {
  const { npcId } = useParams<{ npcId: string }>();
  const navigate = useNavigate();
  
  // Authentication - using demo auth for development
  const { user, token, isAuthenticated } = useDemoAuth();
  
  // NPC Management - Connect via gateway service for CORS handling
  const { npcs, currentNPC, setCurrentNPC, fetchNPCs, fetchNPC, loading: npcLoading, error: npcError } = useNPC({
    apiBaseUrl: 'http://localhost:8000', // Connect via gateway service
    authToken: token || undefined
  });

  // Local state
  const [messages, setMessages] = useState<Message[]>([]);
  const [inputMessage, setInputMessage] = useState('');
  const [selectedNPCId, setSelectedNPCId] = useState<string>(npcId || '');
  const [streamingMessage, setStreamingMessage] = useState<string>('');
  const [isGenerating, setIsGenerating] = useState(false);
  const [speakingMessageId, setSpeakingMessageId] = useState<string | null>(null);

  const messagesEndRef = useRef<HTMLDivElement>(null);
  const streamingMessageRef = useRef<string>('');
  const streamingTimeoutRef = useRef<NodeJS.Timeout | null>(null);

  // --- Add refs for stable WebSocket handling as per code review ---
  const currentNPCIdRef = useRef<string | undefined>(undefined);
  useEffect(() => { 
    currentNPCIdRef.current = currentNPC?.id;
  }, [currentNPC?.id]);

  const onMessageRef = useRef<(m: any) => void>(() => {});

  // --- Make WebSocket message handler stable (no dependencies) ---
  useEffect(() => {
    onMessageRef.current = (message: any) => {
      if (!message) return;
      
      console.log('🔥 STABLE handleWebSocketMessage:', message.type, message);
      console.log('🔍 Handler instance ID:', Date.now()); // Debug handler recreation
      
      switch (message.type) {
        case 'connection_ready':
          console.log('✅ WebSocket connection ready');
          break;
          
        case 'response_complete': {
          console.log('🎯 Hit response_complete case!');
          const msgNpc = String(message.npc_id ?? '');
          const curNpc = String(currentNPCIdRef.current ?? '');
          console.log('🔍 NPC comparison - msgNpc:', msgNpc, 'curNpc:', curNpc);
          
          // Complete message received - use robust string comparison
          if (!msgNpc || !curNpc || msgNpc === curNpc) {
            console.log('✅ Passed NPC ID condition check');
            const finalContent = (streamingMessageRef.current || '').trim();
            
            console.log('🔍 Final content from REF:', streamingMessageRef.current?.length || 0);
            console.log('🔍 Final content preview:', finalContent.substring(0, 100) + '...');
            
            if (finalContent.length > 0) {
              console.log('✅ Converting streaming message to permanent:', finalContent.length, 'characters');
              
              const newMessage: Message = {
                id: Date.now().toString(),
                sender: 'npc' as const,
                content: finalContent,
                timestamp: new Date().toISOString()
              };
              
              setMessages(prev => {
                console.log('📋 Adding message to', prev.length, 'existing messages');
                return [...prev, newMessage];
              });
              console.log('📋 Added message with content length:', finalContent.length);
            } else {
              console.warn('⚠️ response_complete but no streaming content to commit - REF was empty!');
            }
            
            // Clear streaming state
            streamingMessageRef.current = '';
            setStreamingMessage('');
          }
          setIsGenerating(false);
          break;
        }
        
        case 'response_chunk': {
          console.log('🎯 Hit response_chunk case!');
          const msgNpc = String(message.npc_id ?? '');
          const curNpc = String(currentNPCIdRef.current ?? '');
          
          // Streaming token received - use robust string comparison
          if (!msgNpc || !curNpc || msgNpc === curNpc) {
            const chunk = message.chunk ?? '';
            const updated = (streamingMessageRef.current ?? '') + chunk;
            
            // Update both ref and state
            streamingMessageRef.current = updated;
            setStreamingMessage(updated);
            
            console.log('📝 Chunk:', JSON.stringify(chunk), 'Total in REF:', streamingMessageRef.current.length);
          }
          break;
        }
        
        case 'message_complete': {
          // Handle complete (non-streaming) messages
          console.log('🎯 Hit message_complete case (non-streaming)!');
          const msgNpc = String(message.npc_id ?? '');
          const curNpc = String(currentNPCIdRef.current ?? '');
          
          if (!msgNpc || !curNpc || msgNpc === curNpc) {
            const completeContent = message.content || '';
            console.log('📝 Complete message received:', completeContent.length, 'characters');
            
            if (completeContent.length > 0) {
              const newMessage: Message = {
                id: Date.now().toString(),
                sender: 'npc' as const,
                content: completeContent.trim(),
                timestamp: new Date().toISOString()
              };
              
              setMessages(prev => {
                console.log('📋 Adding complete message to', prev.length, 'existing messages');
                return [...prev, newMessage];
              });
            }
            
            // Clear any streaming state
            streamingMessageRef.current = '';
            setStreamingMessage('');
          }
          setIsGenerating(false);
          break;
        }
        
        case 'pong':
          // Keep alive response - no action needed
          break;
          
        case 'error':
          console.error('WebSocket error:', message.message);
          setIsGenerating(false);
          break;
          
        default:
          console.log('❓ Unknown message type:', message.type);
          break;
      }
    };
  }, []); // <-- No dependencies - stable handler

  // WebSocket for real-time chat - Connect via gateway service for CORS handling
  const webSocketOptions = useMemo(() => ({
    url: 'ws://localhost:8000/ws', // Primary: Via Gateway Service
    fallbackUrls: ['ws://localhost:8002/ws'], // Fallback: Direct to Chat Service
    enableFallback: true,
    shouldReconnect: true,
    token: token || undefined, // Pass authentication token
    heartbeatInterval: 60000, // 60 seconds
    maxMessageQueueSize: 50,
    onMessage: (message: any) => onMessageRef.current(message), // <-- stable wrapper
    onError: (error: any) => {
      console.error('WebSocket connection error:', error);
    },
    onOpen: () => {
      console.log('WebSocket connected successfully');
    },
    onClose: (event: any) => {
      console.log('WebSocket disconnected:', event.code, event.reason);
    }
  }), [token]); // <-- DOES NOT depend on streamingMessage or handler

  const {
    connectionState,
    sendMessage: sendWSMessage,
    lastMessage,
    connectionError,
    isTyping
  } = useWebSocket(webSocketOptions);

  // Auto-scroll to bottom
  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages, streamingMessage]);

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      if (streamingTimeoutRef.current) {
        clearTimeout(streamingTimeoutRef.current);
      }
    };
  }, []);

  // Handle NPC selection
  const handleNPCChange = useCallback(async (npcId: string) => {
    console.log('🔄 NPC Selection started:', npcId);
    if (!npcId) return;
    
    setSelectedNPCId(npcId);
    console.log('📡 Fetching NPC details...');
    const npc = await fetchNPC(npcId);
    if (npc) {
      console.log('✅ NPC fetched:', npc.name);
      setCurrentNPC(npc);
      navigate(`/chat/${npcId}`);
      
      // Clear messages for new NPC conversation and clean up streaming
      setMessages([]);
      setStreamingMessage('');
      streamingMessageRef.current = '';
      if (streamingTimeoutRef.current) {
        clearTimeout(streamingTimeoutRef.current);
        streamingTimeoutRef.current = null;
      }
      
      console.log('✅ NPC selection complete - WebSocket will handle conversation automatically');
    } else {
      console.error('❌ Failed to fetch NPC');
    }
  }, [fetchNPC, setCurrentNPC, navigate]);



  // Send message
  const handleSendMessage = useCallback(async () => {
    if (!inputMessage.trim() || !currentNPC) return;

    const userMessage: Message = {
      id: Date.now().toString(),
      sender: 'user',
      content: inputMessage.trim(),
      timestamp: new Date().toISOString()
    };

    setMessages(prev => [...prev, userMessage]);
    
    // Send via WebSocket with NPC ID for routing
    sendWSMessage({
      type: 'message',
      npc_id: currentNPC.id,
      content: inputMessage.trim()
    });

    setInputMessage('');
    setIsGenerating(true);
  }, [inputMessage, currentNPC, sendWSMessage]);

  // Handle speaking message
  const handleSpeak = useCallback(async (messageId: string, text: string) => {
    if (!currentNPC || speakingMessageId) return;
    
    try {
      setSpeakingMessageId(messageId);
      
      // Call audio service via gateway
      const response = await fetch('http://localhost:8000/api/audio/speak', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': token ? `Bearer ${token}` : ''
        },
        body: JSON.stringify({
          text: text,
          npc_id: currentNPC.id
        })
      });
      
      if (!response.ok) {
        throw new Error(`Audio generation failed: ${response.statusText}`);
      }
      
      // Get audio data as blob
      const audioBlob = await response.blob();
      
      // Create audio element and play
      const audioUrl = URL.createObjectURL(audioBlob);
      const audio = new Audio(audioUrl);
      
      audio.onended = () => {
        setSpeakingMessageId(null);
        URL.revokeObjectURL(audioUrl);
      };
      
      audio.onerror = () => {
        setSpeakingMessageId(null);
        URL.revokeObjectURL(audioUrl);
        console.error('Audio playback failed');
      };
      
      await audio.play();
      
    } catch (error) {
      console.error('Error generating speech:', error);
      setSpeakingMessageId(null);
    }
  }, [currentNPC, token, speakingMessageId]);

  // Handle Enter key
  const handleKeyPress = (event: React.KeyboardEvent) => {
    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault();
      handleSendMessage();
    }
  };

  // Initial setup
  useEffect(() => {
    if (npcId && npcs.length > 0 && !currentNPC) {
      handleNPCChange(npcId);
    }
  }, [npcId, npcs, currentNPC, handleNPCChange]);

  // Connection status indicator
  const getConnectionStatusColor = () => {
    switch (connectionState) {
      case 'connected': return 'success';
      case 'connecting': return 'warning';
      case 'disconnected': return 'error';
      case 'error': return 'error';
      default: return 'default';
    }
  };

  // Show authentication status for development
  if (!isAuthenticated) {
    return (
      <Container maxWidth="sm" sx={{ py: 4 }}>
        <Alert severity="error">
          Authentication required. Please ensure the authentication service is running.
        </Alert>
      </Container>
    );
  }

  return (
    <Container maxWidth="lg" sx={{ py: 2, height: '100%', display: 'flex', flexDirection: 'column' }}>
      {/* Header */}
      <Paper sx={{ p: 2, mb: 2 }}>
        <Box display="flex" alignItems="center" justifyContent="space-between">
          <Box>
            <Typography variant="h5">Life Strands Chat</Typography>
            <Typography variant="caption" color="text.secondary">
              Connected as: {user?.username} | Token: {token ? 'Valid' : 'Missing'}
            </Typography>
          </Box>
          
          <Box display="flex" alignItems="center" gap={2}>
            {/* Connection Status */}
            <Chip 
              label={connectionState} 
              color={getConnectionStatusColor() as any}
              size="small"
            />
            
            {/* NPC Selection */}
            <FormControl size="small" sx={{ minWidth: 200 }}>
              <InputLabel>Select NPC</InputLabel>
              <Select
                value={selectedNPCId}
                onChange={(e) => handleNPCChange(e.target.value)}
                label="Select NPC"
                disabled={npcLoading}
              >
                {npcs.map((npc) => (
                  <MenuItem key={npc.id} value={npc.id}>
                    {npc.name || 'Unnamed NPC'}
                  </MenuItem>
                ))}
              </Select>
            </FormControl>
            
            {/* Refresh NPCs */}
            <IconButton onClick={fetchNPCs} disabled={npcLoading}>
              <RefreshIcon />
            </IconButton>
          </Box>
        </Box>

        {/* Current NPC Info */}
        {currentNPC && (
          <Box mt={2} p={2} bgcolor="background.paper" borderRadius={1}>
            <Typography variant="h6">{currentNPC.name}</Typography>
            <Typography variant="body2" color="text.secondary">
              {currentNPC.background?.occupation} • {currentNPC.current_status?.mood}
            </Typography>
            <Box mt={1}>
              {currentNPC.personality?.traits?.slice(0, 5).map((trait, index) => (
                <Chip key={index} label={trait} size="small" sx={{ mr: 0.5, mb: 0.5 }} />
              ))}
            </Box>
          </Box>
        )}
      </Paper>

      {/* Chat Area */}
      <Paper sx={{ flexGrow: 1, display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
        {/* Messages */}
        <Box sx={{ flexGrow: 1, overflow: 'auto', p: 2 }}>
          {/* Error Messages */}
          {(npcError || connectionError) && (
            <Alert severity="error" sx={{ mb: 2 }}>
              {npcError || connectionError}
            </Alert>
          )}

          {/* Loading */}
          {npcLoading && (
            <Box display="flex" justifyContent="center" p={2}>
              <CircularProgress />
            </Box>
          )}

          {/* Welcome Message */}
          {messages.length === 0 && currentNPC && (
            <Alert severity="info" sx={{ mb: 2 }}>
              Start a conversation with {currentNPC.name}! They are currently {currentNPC.current_status?.mood} and in {currentNPC.current_status?.location}.
            </Alert>
          )}

          {/* Message List - Virtualized for performance with large conversations */}
          <List sx={{ py: 0 }}>
            {messages.slice(-50).map((message) => ( // Show only last 50 messages for performance
              <ListItem
                key={message.id}
                sx={{
                  display: 'flex',
                  justifyContent: message.sender === 'user' ? 'flex-end' : 'flex-start',
                  px: 0,
                  py: 1
                }}
              >
                <Box
                  sx={{
                    maxWidth: '70%',
                    display: 'flex',
                    flexDirection: message.sender === 'user' ? 'row-reverse' : 'row',
                    alignItems: 'flex-start',
                    gap: 1
                  }}
                >
                  <Avatar
                    sx={{
                      bgcolor: message.sender === 'user' ? 'primary.main' : 'secondary.main',
                      width: 32,
                      height: 32
                    }}
                  >
                    {message.sender === 'user' ? 'U' : currentNPC?.name?.charAt(0) || 'N'}
                  </Avatar>
                  
                  <Paper
                    sx={{
                      p: 2,
                      bgcolor: message.sender === 'user' ? 'primary.light' : 'background.default',
                      color: message.sender === 'user' ? 'primary.contrastText' : 'text.primary',
                      position: 'relative'
                    }}
                  >
                    <Typography variant="body1" sx={{ whiteSpace: 'pre-wrap' }}>
                      {message.content}
                    </Typography>
                    <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', mt: 0.5 }}>
                      <Typography variant="caption" sx={{ opacity: 0.7 }}>
                        {new Date(message.timestamp).toLocaleTimeString()}
                      </Typography>
                      {message.sender === 'npc' && (
                        <IconButton
                          size="small"
                          onClick={() => handleSpeak(message.id, message.content)}
                          disabled={speakingMessageId !== null}
                          sx={{ 
                            opacity: speakingMessageId === message.id ? 1 : 0.6,
                            '&:hover': { opacity: 1 }
                          }}
                        >
                          {speakingMessageId === message.id ? (
                            <CircularProgress size={16} />
                          ) : (
                            <SpeakIcon fontSize="small" />
                          )}
                        </IconButton>
                      )}
                    </Box>
                  </Paper>
                </Box>
              </ListItem>
            ))}

            {/* Streaming Message */}
            {streamingMessage && (
              <ListItem sx={{ display: 'flex', justifyContent: 'flex-start', px: 0, py: 1 }}>
                <Box sx={{ maxWidth: '70%', display: 'flex', alignItems: 'flex-start', gap: 1 }}>
                  <Avatar sx={{ bgcolor: 'secondary.main', width: 32, height: 32 }}>
                    {currentNPC?.name?.charAt(0) || 'N'}
                  </Avatar>
                  <Paper sx={{ p: 2, bgcolor: 'background.default', position: 'relative' }}>
                    <Typography variant="body1" sx={{ whiteSpace: 'pre-wrap' }}>
                      {streamingMessage}
                      <Box
                        component="span"
                        sx={{
                          display: 'inline-block',
                          width: '2px',
                          height: '1em',
                          bgcolor: 'text.primary',
                          ml: 0.5,
                          animation: 'blink 1s infinite'
                        }}
                      />
                    </Typography>
                    {/* Debug info - remove in production */}
                    <Typography variant="caption" sx={{ opacity: 0.5, fontSize: '10px', display: 'block', mt: 0.5 }}>
                      DEBUG: {streamingMessage.length} chars streaming
                    </Typography>
                  </Paper>
                </Box>
              </ListItem>
            )}

            {/* Typing Indicator */}
            {isTyping && !streamingMessage && (
              <ListItem sx={{ display: 'flex', justifyContent: 'flex-start', px: 0, py: 1 }}>
                <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                  <Avatar sx={{ bgcolor: 'secondary.main', width: 32, height: 32 }}>
                    {currentNPC?.name?.charAt(0) || 'N'}
                  </Avatar>
                  <Typography variant="body2" color="text.secondary">
                    {currentNPC?.name || 'NPC'} is typing...
                  </Typography>
                </Box>
              </ListItem>
            )}
          </List>

          <div ref={messagesEndRef} />
        </Box>

        <Divider />

        {/* Input Area */}
        <Box sx={{ p: 2 }}>
          <Box display="flex" gap={1} alignItems="flex-end">
            <TextField
              fullWidth
              multiline
              maxRows={4}
              variant="outlined"
              placeholder={currentNPC ? `Message ${currentNPC.name}...` : 'Select an NPC to start chatting'}
              value={inputMessage}
              onChange={(e) => setInputMessage(e.target.value)}
              onKeyPress={handleKeyPress}
              disabled={!currentNPC || connectionState !== 'connected' || isGenerating}
            />
            <Button
              variant="contained"
              endIcon={isGenerating ? <StopIcon /> : <SendIcon />}
              onClick={handleSendMessage}
              disabled={!inputMessage.trim() || !currentNPC || connectionState !== 'connected'}
              sx={{ minWidth: 100 }}
            >
              {isGenerating ? 'Stop' : 'Send'}
            </Button>
          </Box>

          {/* Status */}
          <Typography variant="caption" color="text.secondary" sx={{ mt: 1, display: 'block' }}>
            Connection: {connectionState} • Auth: {isAuthenticated ? 'Authenticated' : 'Not authenticated'}
            {currentNPC && ` • Chatting with ${currentNPC.name}`}
          </Typography>
        </Box>
      </Paper>

      {/* CSS for blinking cursor */}
      <style>{`
        @keyframes blink {
          0%, 50% { opacity: 1; }
          51%, 100% { opacity: 0; }
        }
      `}</style>
    </Container>
  );
};

export default ChatPage;