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
  Stop as StopIcon
} from '@mui/icons-material';
import { useWebSocket } from '../hooks/useWebSocket';
import { useNPC } from '../hooks/useNPC';

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
  
  // NPC Management
  const { npcs, currentNPC, setCurrentNPC, fetchNPCs, fetchNPC, loading: npcLoading, error: npcError } = useNPC({
    apiBaseUrl: 'http://localhost:8003'
  });

  // WebSocket for real-time chat - single persistent connection
  const webSocketOptions = useMemo(() => ({
    url: 'ws://localhost:8002/ws',
    shouldReconnect: true,
    onMessage: (message) => {
      console.log('Received WebSocket message:', message);
    },
    onError: (error) => {
      console.error('WebSocket connection error:', error);
    },
    onOpen: () => {
      console.log('WebSocket connected successfully');
    },
    onClose: (event) => {
      console.log('WebSocket disconnected:', event.code, event.reason);
    }
  }), []);

  const {
    connectionState,
    sendMessage: sendWSMessage,
    lastMessage,
    connectionError,
    isTyping
  } = useWebSocket(webSocketOptions);

  // Local state
  const [messages, setMessages] = useState<Message[]>([]);
  const [inputMessage, setInputMessage] = useState('');
  const [selectedNPCId, setSelectedNPCId] = useState<string>(npcId || '');
  const [streamingMessage, setStreamingMessage] = useState<string>('');
  const [isGenerating, setIsGenerating] = useState(false);

  const messagesEndRef = useRef<HTMLDivElement>(null);
  const streamingMessageRef = useRef<string>('');

  // Auto-scroll to bottom
  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages, streamingMessage]);

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
      
      // Clear messages for new NPC conversation
      setMessages([]);
      setStreamingMessage('');
      
      console.log('✅ NPC selection complete - WebSocket will handle conversation automatically');
    } else {
      console.error('❌ Failed to fetch NPC');
    }
  }, [fetchNPC, setCurrentNPC, navigate]);

  // Handle WebSocket messages
  const handleWebSocketMessage = useCallback((message: any) => {
    if (!message) return;

    console.log('Received WebSocket message:', message);

    switch (message.type) {
      case 'connection_ready':
        console.log('✅ WebSocket connection ready');
        break;
        
      case 'response_complete':
        // Complete message received for current NPC
        if (streamingMessageRef.current && (!message.npc_id || message.npc_id === currentNPC?.id)) {
          setMessages(prev => [...prev, {
            id: Date.now().toString(),
            sender: 'npc',
            content: streamingMessageRef.current,
            timestamp: new Date().toISOString()
          }]);
          setStreamingMessage('');
          streamingMessageRef.current = '';
        }
        setIsGenerating(false);
        break;
        
      case 'response_chunk':
        // Streaming token received for current NPC
        if (!message.npc_id || message.npc_id === currentNPC?.id) {
          const chunk = message.chunk || '';
          streamingMessageRef.current += chunk;
          setStreamingMessage(streamingMessageRef.current);
        }
        break;
        
      case 'pong':
        // Keep alive response - no action needed
        break;
        
      case 'error':
        console.error('WebSocket error:', message.message);
        setIsGenerating(false);
        break;
    }
  }, [currentNPC?.id]);

  useEffect(() => {
    handleWebSocketMessage(lastMessage);
  }, [lastMessage, handleWebSocketMessage]);

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

  return (
    <Container maxWidth="lg" sx={{ py: 2, height: '100%', display: 'flex', flexDirection: 'column' }}>
      {/* Header */}
      <Paper sx={{ p: 2, mb: 2 }}>
        <Box display="flex" alignItems="center" justifyContent="space-between">
          <Typography variant="h5">Life Strands Chat</Typography>
          
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

          {/* Message List */}
          <List sx={{ py: 0 }}>
            {messages.map((message) => (
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
                      color: message.sender === 'user' ? 'primary.contrastText' : 'text.primary'
                    }}
                  >
                    <Typography variant="body1" sx={{ whiteSpace: 'pre-wrap' }}>
                      {message.content}
                    </Typography>
                    <Typography variant="caption" sx={{ opacity: 0.7, mt: 0.5, display: 'block' }}>
                      {new Date(message.timestamp).toLocaleTimeString()}
                    </Typography>
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
            Connection: {connectionState}
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