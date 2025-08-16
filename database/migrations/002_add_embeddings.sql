-- Life Strands System - Add Vector Embeddings
-- Migration 002: Add pgvector extension and embedding support

-- Enable vector extension
CREATE EXTENSION IF NOT EXISTS vector;

-- Add embedding column to NPCs table for semantic search
ALTER TABLE npcs ADD COLUMN embedding vector(1536);

-- Add embedding timestamp to track when embeddings were last generated
ALTER TABLE npcs ADD COLUMN embedding_generated_at TIMESTAMP WITH TIME ZONE;

-- Create index for vector similarity search
-- Using ivfflat index with cosine distance for good performance
CREATE INDEX idx_npc_embedding_cosine ON npcs USING ivfflat (embedding vector_cosine_ops)
WITH (lists = 100);

-- Alternative index for L2 distance if needed
-- CREATE INDEX idx_npc_embedding_l2 ON npcs USING ivfflat (embedding vector_l2_ops)
-- WITH (lists = 100);

-- Create table for conversation embeddings (for semantic search within conversations)
CREATE TABLE conversation_embeddings (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    conversation_id UUID NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    message_index INTEGER NOT NULL,
    role VARCHAR(20) NOT NULL CHECK (role IN ('user', 'assistant')),
    content TEXT NOT NULL,
    embedding vector(1536),
    
    -- Timestamps
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    
    -- Ensure uniqueness per conversation message
    UNIQUE(conversation_id, message_index)
);

-- Index for conversation embeddings
CREATE INDEX idx_conversation_embeddings_cosine ON conversation_embeddings 
USING ivfflat (embedding vector_cosine_ops) WITH (lists = 50);

-- Index for conversation lookups
CREATE INDEX idx_conversation_embeddings_conversation_id ON conversation_embeddings(conversation_id);
CREATE INDEX idx_conversation_embeddings_role ON conversation_embeddings(role);

-- Create table for knowledge base embeddings (for RAG functionality)
CREATE TABLE knowledge_embeddings (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    npc_id UUID NOT NULL REFERENCES npcs(id) ON DELETE CASCADE,
    knowledge_index INTEGER NOT NULL,
    topic VARCHAR(200) NOT NULL,
    content TEXT NOT NULL,
    embedding vector(1536),
    
    -- Knowledge metadata
    source VARCHAR(100),
    confidence INTEGER CHECK (confidence >= 1 AND confidence <= 10),
    last_accessed TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    
    -- Timestamps
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    
    -- Ensure uniqueness per NPC knowledge item
    UNIQUE(npc_id, knowledge_index)
);

-- Indexes for knowledge embeddings
CREATE INDEX idx_knowledge_embeddings_cosine ON knowledge_embeddings 
USING ivfflat (embedding vector_cosine_ops) WITH (lists = 50);

CREATE INDEX idx_knowledge_embeddings_npc_id ON knowledge_embeddings(npc_id);
CREATE INDEX idx_knowledge_embeddings_topic ON knowledge_embeddings(topic);
CREATE INDEX idx_knowledge_embeddings_last_accessed ON knowledge_embeddings(last_accessed);

-- Create table for memory embeddings (for episodic memory search)
CREATE TABLE memory_embeddings (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    npc_id UUID NOT NULL REFERENCES npcs(id) ON DELETE CASCADE,
    memory_index INTEGER NOT NULL,
    content TEXT NOT NULL,
    embedding vector(1536),
    
    -- Memory metadata
    importance INTEGER CHECK (importance >= 1 AND importance <= 10),
    emotional_impact VARCHAR(20) CHECK (emotional_impact IN ('positive', 'negative', 'neutral')),
    people_involved JSONB DEFAULT '[]'::jsonb,
    tags JSONB DEFAULT '[]'::jsonb,
    memory_timestamp TIMESTAMP WITH TIME ZONE,
    
    -- Timestamps
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    
    -- Ensure uniqueness per NPC memory
    UNIQUE(npc_id, memory_index)
);

-- Indexes for memory embeddings
CREATE INDEX idx_memory_embeddings_cosine ON memory_embeddings 
USING ivfflat (embedding vector_cosine_ops) WITH (lists = 50);

CREATE INDEX idx_memory_embeddings_npc_id ON memory_embeddings(npc_id);
CREATE INDEX idx_memory_embeddings_importance ON memory_embeddings(importance);
CREATE INDEX idx_memory_embeddings_emotional_impact ON memory_embeddings(emotional_impact);
CREATE INDEX idx_memory_embeddings_timestamp ON memory_embeddings(memory_timestamp);
CREATE INDEX idx_memory_embeddings_people_gin ON memory_embeddings USING GIN (people_involved);
CREATE INDEX idx_memory_embeddings_tags_gin ON memory_embeddings USING GIN (tags);

-- Create functions for similarity search

-- Function to find similar NPCs based on personality/background
CREATE OR REPLACE FUNCTION find_similar_npcs(
    target_npc_id UUID,
    similarity_threshold FLOAT DEFAULT 0.7,
    max_results INTEGER DEFAULT 10
)
RETURNS TABLE (
    id UUID,
    name VARCHAR,
    similarity FLOAT,
    location VARCHAR,
    faction VARCHAR
) AS $$
BEGIN
    RETURN QUERY
    SELECT 
        n.id,
        n.name,
        1 - (target.embedding <=> n.embedding) as similarity,
        n.location,
        n.faction
    FROM npcs n
    CROSS JOIN (SELECT embedding FROM npcs WHERE npcs.id = target_npc_id) as target
    WHERE n.id != target_npc_id 
        AND n.status = 'active'
        AND n.embedding IS NOT NULL
        AND target.embedding IS NOT NULL
        AND 1 - (target.embedding <=> n.embedding) >= similarity_threshold
    ORDER BY target.embedding <=> n.embedding
    LIMIT max_results;
END;
$$ LANGUAGE plpgsql;

-- Function for semantic search within NPC knowledge
CREATE OR REPLACE FUNCTION search_npc_knowledge(
    target_npc_id UUID,
    query_embedding vector(1536),
    similarity_threshold FLOAT DEFAULT 0.6,
    max_results INTEGER DEFAULT 5
)
RETURNS TABLE (
    id UUID,
    topic VARCHAR,
    content TEXT,
    similarity FLOAT,
    confidence INTEGER
) AS $$
BEGIN
    RETURN QUERY
    SELECT 
        ke.id,
        ke.topic,
        ke.content,
        1 - (query_embedding <=> ke.embedding) as similarity,
        ke.confidence
    FROM knowledge_embeddings ke
    WHERE ke.npc_id = target_npc_id
        AND ke.embedding IS NOT NULL
        AND 1 - (query_embedding <=> ke.embedding) >= similarity_threshold
    ORDER BY query_embedding <=> ke.embedding
    LIMIT max_results;
END;
$$ LANGUAGE plpgsql;

-- Function for semantic search within NPC memories
CREATE OR REPLACE FUNCTION search_npc_memories(
    target_npc_id UUID,
    query_embedding vector(1536),
    similarity_threshold FLOAT DEFAULT 0.6,
    max_results INTEGER DEFAULT 5,
    min_importance INTEGER DEFAULT 1
)
RETURNS TABLE (
    id UUID,
    content TEXT,
    similarity FLOAT,
    importance INTEGER,
    emotional_impact VARCHAR,
    memory_timestamp TIMESTAMP WITH TIME ZONE
) AS $$
BEGIN
    RETURN QUERY
    SELECT 
        me.id,
        me.content,
        1 - (query_embedding <=> me.embedding) as similarity,
        me.importance,
        me.emotional_impact,
        me.memory_timestamp
    FROM memory_embeddings me
    WHERE me.npc_id = target_npc_id
        AND me.embedding IS NOT NULL
        AND me.importance >= min_importance
        AND 1 - (query_embedding <=> me.embedding) >= similarity_threshold
    ORDER BY query_embedding <=> me.embedding
    LIMIT max_results;
END;
$$ LANGUAGE plpgsql;

-- Function to search conversations semantically
CREATE OR REPLACE FUNCTION search_conversation_messages(
    query_embedding vector(1536),
    similarity_threshold FLOAT DEFAULT 0.7,
    max_results INTEGER DEFAULT 20,
    target_npc_id UUID DEFAULT NULL
)
RETURNS TABLE (
    conversation_id UUID,
    npc_id UUID,
    npc_name VARCHAR,
    message_index INTEGER,
    role VARCHAR,
    content TEXT,
    similarity FLOAT
) AS $$
BEGIN
    RETURN QUERY
    SELECT 
        ce.conversation_id,
        c.npc_id,
        n.name as npc_name,
        ce.message_index,
        ce.role,
        ce.content,
        1 - (query_embedding <=> ce.embedding) as similarity
    FROM conversation_embeddings ce
    JOIN conversations c ON ce.conversation_id = c.id
    JOIN npcs n ON c.npc_id = n.id
    WHERE ce.embedding IS NOT NULL
        AND 1 - (query_embedding <=> ce.embedding) >= similarity_threshold
        AND (target_npc_id IS NULL OR c.npc_id = target_npc_id)
    ORDER BY query_embedding <=> ce.embedding
    LIMIT max_results;
END;
$$ LANGUAGE plpgsql;

-- Create trigger to update embedding timestamp
CREATE OR REPLACE FUNCTION update_embedding_timestamp()
RETURNS TRIGGER AS $$
BEGIN
    IF NEW.embedding IS DISTINCT FROM OLD.embedding THEN
        NEW.embedding_generated_at = NOW();
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER update_npc_embedding_timestamp
    BEFORE UPDATE ON npcs
    FOR EACH ROW
    EXECUTE FUNCTION update_embedding_timestamp();

-- Apply update timestamp triggers to new tables
CREATE TRIGGER update_conversation_embeddings_updated_at 
    BEFORE UPDATE ON conversation_embeddings 
    FOR EACH ROW 
    EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_knowledge_embeddings_updated_at 
    BEFORE UPDATE ON knowledge_embeddings 
    FOR EACH ROW 
    EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_memory_embeddings_updated_at 
    BEFORE UPDATE ON memory_embeddings 
    FOR EACH ROW 
    EXECUTE FUNCTION update_updated_at_column();

-- Create views for embedding management

-- NPCs needing embedding generation
CREATE VIEW npcs_needing_embeddings AS
SELECT 
    id,
    name,
    location,
    faction,
    updated_at,
    embedding_generated_at,
    CASE 
        WHEN embedding IS NULL THEN 'missing'
        WHEN embedding_generated_at IS NULL THEN 'missing'
        WHEN updated_at > embedding_generated_at THEN 'outdated'
        ELSE 'current'
    END as embedding_status
FROM npcs 
WHERE status = 'active'
    AND (embedding IS NULL 
         OR embedding_generated_at IS NULL 
         OR updated_at > embedding_generated_at)
ORDER BY updated_at DESC;

-- Embedding statistics view
CREATE VIEW embedding_stats AS
SELECT 
    'npcs' as table_name,
    COUNT(*) as total_rows,
    COUNT(embedding) as with_embeddings,
    COUNT(*) - COUNT(embedding) as missing_embeddings,
    ROUND(COUNT(embedding)::numeric / COUNT(*) * 100, 2) as completion_percentage
FROM npcs WHERE status = 'active'
UNION ALL
SELECT 
    'conversation_embeddings' as table_name,
    COUNT(*) as total_rows,
    COUNT(embedding) as with_embeddings,
    COUNT(*) - COUNT(embedding) as missing_embeddings,
    ROUND(COUNT(embedding)::numeric / COUNT(*) * 100, 2) as completion_percentage
FROM conversation_embeddings
UNION ALL
SELECT 
    'knowledge_embeddings' as table_name,
    COUNT(*) as total_rows,
    COUNT(embedding) as with_embeddings,
    COUNT(*) - COUNT(embedding) as missing_embeddings,
    ROUND(COUNT(embedding)::numeric / COUNT(*) * 100, 2) as completion_percentage
FROM knowledge_embeddings
UNION ALL
SELECT 
    'memory_embeddings' as table_name,
    COUNT(*) as total_rows,
    COUNT(embedding) as with_embeddings,
    COUNT(*) - COUNT(embedding) as missing_embeddings,
    ROUND(COUNT(embedding)::numeric / COUNT(*) * 100, 2) as completion_percentage
FROM memory_embeddings;

-- Add helpful comments
COMMENT ON COLUMN npcs.embedding IS 'Vector embedding of NPC personality and background for similarity search';
COMMENT ON COLUMN npcs.embedding_generated_at IS 'Timestamp when embedding was last generated';
COMMENT ON TABLE conversation_embeddings IS 'Vector embeddings of conversation messages for semantic search';
COMMENT ON TABLE knowledge_embeddings IS 'Vector embeddings of NPC knowledge items for RAG functionality';
COMMENT ON TABLE memory_embeddings IS 'Vector embeddings of NPC memories for episodic recall';

COMMENT ON FUNCTION find_similar_npcs IS 'Find NPCs with similar personalities/backgrounds';
COMMENT ON FUNCTION search_npc_knowledge IS 'Search NPC knowledge base semantically';
COMMENT ON FUNCTION search_npc_memories IS 'Search NPC memories semantically';
COMMENT ON FUNCTION search_conversation_messages IS 'Search conversation messages semantically';

-- Update migration tracking
INSERT INTO system_metrics (metric_type, metric_name, metric_value, service_name, instance_id) 
VALUES ('migration', 'schema_version', 2, 'database', 'embeddings_migration');