-- Life Strands System - Update Embedding Dimensions for Local Models
-- Migration 003: Update vector dimensions from 1536 (OpenAI) to 384 (all-MiniLM-L6-v2)

-- Drop existing indexes first (required for column type change)
DROP INDEX IF EXISTS idx_npc_embedding_cosine;
DROP INDEX IF EXISTS idx_conversation_embeddings_cosine;
DROP INDEX IF EXISTS idx_knowledge_embeddings_cosine;
DROP INDEX IF EXISTS idx_memory_embeddings_cosine;

-- Update NPCs table embedding column
ALTER TABLE npcs ALTER COLUMN embedding TYPE vector(384);

-- Update conversation embeddings table
ALTER TABLE conversation_embeddings ALTER COLUMN embedding TYPE vector(384);

-- Update knowledge embeddings table  
ALTER TABLE knowledge_embeddings ALTER COLUMN embedding TYPE vector(384);

-- Update memory embeddings table
ALTER TABLE memory_embeddings ALTER COLUMN embedding TYPE vector(384);

-- Recreate indexes with new dimensions
CREATE INDEX idx_npc_embedding_cosine ON npcs USING ivfflat (embedding vector_cosine_ops)
WITH (lists = 100);

CREATE INDEX idx_conversation_embeddings_cosine ON conversation_embeddings 
USING ivfflat (embedding vector_cosine_ops) WITH (lists = 50);

CREATE INDEX idx_knowledge_embeddings_cosine ON knowledge_embeddings 
USING ivfflat (embedding vector_cosine_ops) WITH (lists = 50);

CREATE INDEX idx_memory_embeddings_cosine ON memory_embeddings 
USING ivfflat (embedding vector_cosine_ops) WITH (lists = 50);

-- Update search functions to use new dimensions
DROP FUNCTION IF EXISTS search_npc_knowledge(UUID, vector(1536), FLOAT, INTEGER);
DROP FUNCTION IF EXISTS search_npc_memories(UUID, vector(1536), FLOAT, INTEGER, INTEGER);
DROP FUNCTION IF EXISTS search_conversation_messages(vector(1536), FLOAT, INTEGER, UUID);

-- Recreate functions with 384 dimensions
CREATE OR REPLACE FUNCTION search_npc_knowledge(
    target_npc_id UUID,
    query_embedding vector(384),
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

CREATE OR REPLACE FUNCTION search_npc_memories(
    target_npc_id UUID,
    query_embedding vector(384),
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

CREATE OR REPLACE FUNCTION search_conversation_messages(
    query_embedding vector(384),
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

-- Clear existing embeddings since they're no longer compatible
-- This will trigger regeneration with the new local embedding model
UPDATE npcs SET embedding = NULL, embedding_generated_at = NULL;
UPDATE conversation_embeddings SET embedding = NULL;
UPDATE knowledge_embeddings SET embedding = NULL;
UPDATE memory_embeddings SET embedding = NULL;

-- Update comments to reflect new model
COMMENT ON COLUMN npcs.embedding IS 'Vector embedding (384D) from sentence-transformers model for similarity search';
COMMENT ON TABLE conversation_embeddings IS 'Vector embeddings (384D) of conversation messages for semantic search';
COMMENT ON TABLE knowledge_embeddings IS 'Vector embeddings (384D) of NPC knowledge items for RAG functionality';
COMMENT ON TABLE memory_embeddings IS 'Vector embeddings (384D) of NPC memories for episodic recall';

-- Update migration tracking
INSERT INTO system_metrics (metric_type, metric_name, metric_value, service_name, instance_id) 
VALUES ('migration', 'schema_version', 3, 'database', 'local_embeddings_migration');

-- Log the migration
INSERT INTO system_metrics (metric_type, metric_name, metric_value, service_name, instance_id) 
VALUES ('migration', 'embedding_model_change', 384, 'database', 'changed_from_openai_to_local');