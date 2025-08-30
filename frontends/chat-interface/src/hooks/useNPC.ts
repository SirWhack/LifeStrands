import { useState, useEffect, useCallback } from 'react';

// Life Strand schema matching our actual NPC service
export interface LifeStrand {
  id: string;
  schema_version: string;
  name: string;
  background: {
    age: number;
    occupation: string;
    location: string;
    history: string;
    family?: string[];
    education?: string;
  };
  personality: {
    traits: string[];
    motivations: string[];
    fears: string[];
    values: string[];
    quirks?: string[];
  };
  current_status: {
    mood: string;
    health: string;
    energy: string;
    location: string;
    activity: string;
  };
  relationships: {
    [key: string]: {
      type: string;
      status: string;
      intensity: number;
      notes: string;
    };
  };
  knowledge: Array<{
    topic: string;
    content: string;
    source: string;
    confidence: number;
  }>;
  memories: Array<{
    content: string;
    timestamp: string;
    importance: number;
    emotional_impact: string;
    people_involved: string[];
    tags: string[];
  }>;
  status: string;
  created_at: string;
  updated_at: string;
}

// NPC type that matches our API response (LifeStrand is the full NPC data)
export type NPC = LifeStrand;

interface UseNPCOptions {
  apiBaseUrl?: string;
  authToken?: string;
}

interface UseNPCReturn {
  npcs: NPC[];
  currentNPC: NPC | null;
  loading: boolean;
  error: string | null;
  fetchNPCs: () => Promise<void>;
  fetchNPC: (id: string) => Promise<NPC | null>;
  createNPC: (npcData: Partial<NPC>) => Promise<NPC | null>;
  updateNPC: (id: string, updates: Partial<NPC>) => Promise<NPC | null>;
  deleteNPC: (id: string) => Promise<boolean>;
  searchNPCs: (query: string, filters?: any) => Promise<NPC[]>;
  setCurrentNPC: (npc: NPC | null) => void;
}

export const useNPC = (options: UseNPCOptions = {}): UseNPCReturn => {
  const { apiBaseUrl = 'http://localhost:8000/api', authToken } = options;

  const [npcs, setNPCs] = useState<NPC[]>([]);
  const [currentNPC, setCurrentNPC] = useState<NPC | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const apiHeaders = {
    'Content-Type': 'application/json',
    ...(authToken && { 'Authorization': `Bearer ${authToken}` })
  };

  const handleApiError = (error: any): string => {
    if (error.response) {
      return error.response.data?.message || `API Error: ${error.response.status}`;
    }
    return error.message || 'An unexpected error occurred';
  };

  const fetchNPCs = useCallback(async () => {
    setLoading(true);
    setError(null);

    try {
      const response = await fetch(`${apiBaseUrl}/npcs`, {
        headers: apiHeaders
      });

      if (!response.ok) {
        throw new Error(`Failed to fetch NPCs: ${response.status}`);
      }

      const data = await response.json();
      setNPCs(data.npcs || []);
    } catch (err: any) {
      const errorMessage = handleApiError(err);
      setError(errorMessage);
      console.error('Error fetching NPCs:', err);
    } finally {
      setLoading(false);
    }
  }, [apiBaseUrl, authToken]);

  const fetchNPC = useCallback(async (id: string): Promise<NPC | null> => {
    setLoading(true);
    setError(null);

    try {
      const response = await fetch(`${apiBaseUrl}/npc/${id}`, {
        headers: apiHeaders
      });

      if (!response.ok) {
        throw new Error(`Failed to fetch NPC: ${response.status}`);
      }

      const npc = await response.json();
      return npc;
    } catch (err: any) {
      const errorMessage = handleApiError(err);
      setError(errorMessage);
      console.error(`Error fetching NPC ${id}:`, err);
      return null;
    } finally {
      setLoading(false);
    }
  }, [apiBaseUrl, authToken]);

  const createNPC = useCallback(async (npcData: Partial<NPC>): Promise<NPC | null> => {
    setLoading(true);
    setError(null);

    try {
      const response = await fetch(`${apiBaseUrl}/npcs`, {
        method: 'POST',
        headers: apiHeaders,
        body: JSON.stringify(npcData)
      });

      if (!response.ok) {
        throw new Error(`Failed to create NPC: ${response.status}`);
      }

      const newNPC = await response.json();
      setNPCs(prev => [...prev, newNPC]);
      return newNPC;
    } catch (err: any) {
      const errorMessage = handleApiError(err);
      setError(errorMessage);
      console.error('Error creating NPC:', err);
      return null;
    } finally {
      setLoading(false);
    }
  }, [apiBaseUrl, authToken]);

  const updateNPC = useCallback(async (id: string, updates: Partial<NPC>): Promise<NPC | null> => {
    setLoading(true);
    setError(null);

    try {
      const response = await fetch(`${apiBaseUrl}/npc/${id}`, {
        method: 'PUT',
        headers: apiHeaders,
        body: JSON.stringify(updates)
      });

      if (!response.ok) {
        throw new Error(`Failed to update NPC: ${response.status}`);
      }

      const updatedNPC = await response.json();
      
      setNPCs(prev => prev.map(npc => npc.id === id ? updatedNPC : npc));
      
      if (currentNPC?.id === id) {
        setCurrentNPC(updatedNPC);
      }

      return updatedNPC;
    } catch (err: any) {
      const errorMessage = handleApiError(err);
      setError(errorMessage);
      console.error(`Error updating NPC ${id}:`, err);
      return null;
    } finally {
      setLoading(false);
    }
  }, [apiBaseUrl, authToken, currentNPC]);

  const deleteNPC = useCallback(async (id: string): Promise<boolean> => {
    setLoading(true);
    setError(null);

    try {
      const response = await fetch(`${apiBaseUrl}/npc/${id}`, {
        method: 'DELETE',
        headers: apiHeaders
      });

      if (!response.ok) {
        throw new Error(`Failed to delete NPC: ${response.status}`);
      }

      setNPCs(prev => prev.filter(npc => npc.id !== id));
      
      if (currentNPC?.id === id) {
        setCurrentNPC(null);
      }

      return true;
    } catch (err: any) {
      const errorMessage = handleApiError(err);
      setError(errorMessage);
      console.error(`Error deleting NPC ${id}:`, err);
      return false;
    } finally {
      setLoading(false);
    }
  }, [apiBaseUrl, authToken, currentNPC]);

  const searchNPCs = useCallback(async (query: string, filters: any = {}): Promise<NPC[]> => {
    setLoading(true);
    setError(null);

    try {
      const params = new URLSearchParams({
        q: query,
        ...filters
      });

      const response = await fetch(`${apiBaseUrl}/search?${params}`, {
        headers: apiHeaders
      });

      if (!response.ok) {
        throw new Error(`Failed to search NPCs: ${response.status}`);
      }

      const data = await response.json();
      return data.results || [];
    } catch (err: any) {
      const errorMessage = handleApiError(err);
      setError(errorMessage);
      console.error('Error searching NPCs:', err);
      return [];
    } finally {
      setLoading(false);
    }
  }, [apiBaseUrl, authToken]);

  // Load NPCs on mount
  useEffect(() => {
    fetchNPCs();
  }, [fetchNPCs]);

  return {
    npcs,
    currentNPC,
    loading,
    error,
    fetchNPCs,
    fetchNPC,
    createNPC,
    updateNPC,
    deleteNPC,
    searchNPCs,
    setCurrentNPC
  };
};

// Utility hook for managing NPC conversations
export const useNPCConversation = (npcId: string | null) => {
  const [conversationHistory, setConversationHistory] = useState<any[]>([]);
  const [currentConversationId, setCurrentConversationId] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const startConversation = useCallback(async (userId: string, authToken?: string) => {
    console.log('🚀 startConversation called with npcId:', npcId, 'userId:', userId);
    if (!npcId) {
      console.error('❌ No npcId provided to startConversation');
      return null;
    }

    setLoading(true);
    setError(null);

    try {
      console.log('📡 Sending conversation start request...');
      const response = await fetch('http://localhost:8002/conversation/start', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...(authToken && { 'Authorization': `Bearer ${authToken}` })
        },
        body: JSON.stringify({
          npc_id: npcId,
          user_id: userId
        })
      });

      console.log('📥 Conversation start response status:', response.status);

      if (!response.ok) {
        throw new Error(`Failed to start conversation: ${response.status}`);
      }

      const conversation = await response.json();
      console.log('✅ Conversation response:', conversation);
      setCurrentConversationId(conversation.session_id);
      console.log('🆔 Set conversation ID:', conversation.session_id);
      return conversation;
    } catch (err: any) {
      setError(err.message);
      console.error('Error starting conversation:', err);
      return null;
    } finally {
      setLoading(false);
    }
  }, [npcId]);

  const endConversation = useCallback(async (authToken?: string) => {
    if (!currentConversationId) return;

    try {
      await fetch(`http://localhost:8002/conversation/${currentConversationId}/end`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...(authToken && { 'Authorization': `Bearer ${authToken}` })
        }
      });

      setCurrentConversationId(null);
      setConversationHistory([]);
    } catch (err) {
      console.error('Error ending conversation:', err);
    }
  }, [currentConversationId]);

  const sendMessage = useCallback(async (message: string, authToken?: string) => {
    if (!currentConversationId) return null;

    try {
      const response = await fetch(`http://localhost:8002/conversation/send`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...(authToken && { 'Authorization': `Bearer ${authToken}` })
        },
        body: JSON.stringify({
          session_id: currentConversationId,
          message
        })
      });

      if (!response.ok) {
        throw new Error(`Failed to send message: ${response.status}`);
      }

      const result = await response.json();
      return result;
    } catch (err) {
      console.error('Error sending message:', err);
      return null;
    }
  }, [currentConversationId]);

  return {
    conversationHistory,
    currentConversationId,
    loading,
    error,
    startConversation,
    endConversation,
    sendMessage,
    setConversationHistory
  };
};