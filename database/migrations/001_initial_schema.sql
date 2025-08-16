-- Life Strands System - Initial Database Schema
-- Migration 001: Core tables for NPC management

-- Enable UUID extension
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Core NPC table with queryable fields and JSONB storage
CREATE TABLE npcs (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name VARCHAR(100) NOT NULL,
    location VARCHAR(100),
    faction VARCHAR(100),
    status VARCHAR(20) NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'inactive', 'archived')),
    
    -- Background information for quick queries
    background_occupation VARCHAR(100),
    background_age INTEGER CHECK (background_age >= 0 AND background_age <= 300),
    
    -- Personality traits stored as JSONB array for search
    personality_traits JSONB DEFAULT '[]'::jsonb,
    
    -- Full Life Strand data stored as JSONB
    life_strand_data JSONB NOT NULL,
    
    -- Timestamps
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);

-- Conversations table for tracking chat sessions
CREATE TABLE conversations (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    npc_id UUID NOT NULL REFERENCES npcs(id) ON DELETE CASCADE,
    user_id VARCHAR(100) NOT NULL,
    session_id VARCHAR(100) UNIQUE NOT NULL,
    
    -- Conversation metadata
    started_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    ended_at TIMESTAMP WITH TIME ZONE,
    is_active BOOLEAN NOT NULL DEFAULT true,
    
    -- Message count and duration for analytics
    message_count INTEGER NOT NULL DEFAULT 0,
    duration_seconds INTEGER,
    
    -- Full conversation transcript
    transcript JSONB NOT NULL DEFAULT '[]'::jsonb,
    
    -- Summary and analysis results
    summary TEXT,
    key_points JSONB DEFAULT '[]'::jsonb,
    emotional_impact JSONB DEFAULT '{}'::jsonb,
    
    -- Timestamps
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);

-- Conversation changes table for tracking Life Strand updates
CREATE TABLE conversation_changes (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    conversation_id UUID NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    npc_id UUID NOT NULL REFERENCES npcs(id) ON DELETE CASCADE,
    
    -- Change metadata
    change_type VARCHAR(50) NOT NULL CHECK (change_type IN (
        'memory_added', 'relationship_updated', 'personality_changed', 
        'knowledge_learned', 'status_updated', 'other'
    )),
    
    -- Auto-approval status
    status VARCHAR(20) NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'approved', 'rejected', 'applied')),
    confidence_score DECIMAL(3,2) CHECK (confidence_score >= 0.0 AND confidence_score <= 1.0),
    
    -- Change details
    change_summary TEXT NOT NULL,
    change_data JSONB NOT NULL,
    
    -- Processing timestamps
    generated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    reviewed_at TIMESTAMP WITH TIME ZONE,
    applied_at TIMESTAMP WITH TIME ZONE,
    
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);

-- System metrics table for monitoring
CREATE TABLE system_metrics (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    metric_type VARCHAR(50) NOT NULL,
    metric_name VARCHAR(100) NOT NULL,
    metric_value DECIMAL(10,4) NOT NULL,
    metric_unit VARCHAR(20),
    
    -- Additional metadata
    service_name VARCHAR(50) NOT NULL,
    instance_id VARCHAR(100),
    tags JSONB DEFAULT '{}'::jsonb,
    
    -- Timestamp
    recorded_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    
    -- Composite index will be created below
    UNIQUE(service_name, metric_name, instance_id, recorded_at)
);

-- Create indexes for performance

-- NPC table indexes
CREATE INDEX idx_npc_name ON npcs(name);
CREATE INDEX idx_npc_location ON npcs(location);
CREATE INDEX idx_npc_faction ON npcs(faction);
CREATE INDEX idx_npc_status ON npcs(status);
CREATE INDEX idx_npc_background_age ON npcs(background_age);
CREATE INDEX idx_npc_background_occupation ON npcs(background_occupation);
CREATE INDEX idx_npc_created_at ON npcs(created_at);
CREATE INDEX idx_npc_updated_at ON npcs(updated_at);

-- JSONB indexes for Life Strand data
CREATE INDEX idx_npc_personality_traits_gin ON npcs USING GIN (personality_traits);
CREATE INDEX idx_npc_life_strand_gin ON npcs USING GIN (life_strand_data);

-- Specific JSONB path indexes for common queries
CREATE INDEX idx_npc_current_mood ON npcs USING GIN ((life_strand_data->'current_status'->>'mood'));
CREATE INDEX idx_npc_relationships ON npcs USING GIN ((life_strand_data->'relationships'));

-- Conversation table indexes
CREATE INDEX idx_conversation_npc_id ON conversations(npc_id);
CREATE INDEX idx_conversation_user_id ON conversations(user_id);
CREATE INDEX idx_conversation_session_id ON conversations(session_id);
CREATE INDEX idx_conversation_is_active ON conversations(is_active);
CREATE INDEX idx_conversation_started_at ON conversations(started_at);
CREATE INDEX idx_conversation_ended_at ON conversations(ended_at);

-- JSONB indexes for conversation data
CREATE INDEX idx_conversation_transcript_gin ON conversations USING GIN (transcript);
CREATE INDEX idx_conversation_key_points_gin ON conversations USING GIN (key_points);

-- Conversation changes table indexes
CREATE INDEX idx_changes_conversation_id ON conversation_changes(conversation_id);
CREATE INDEX idx_changes_npc_id ON conversation_changes(npc_id);
CREATE INDEX idx_changes_type ON conversation_changes(change_type);
CREATE INDEX idx_changes_status ON conversation_changes(status);
CREATE INDEX idx_changes_confidence ON conversation_changes(confidence_score);
CREATE INDEX idx_changes_generated_at ON conversation_changes(generated_at);
CREATE INDEX idx_changes_data_gin ON conversation_changes USING GIN (change_data);

-- System metrics indexes
CREATE INDEX idx_metrics_type ON system_metrics(metric_type);
CREATE INDEX idx_metrics_service ON system_metrics(service_name);
CREATE INDEX idx_metrics_recorded_at ON system_metrics(recorded_at);
CREATE INDEX idx_metrics_composite ON system_metrics(service_name, metric_name, recorded_at);

-- Create composite indexes for common query patterns
CREATE INDEX idx_npc_location_faction ON npcs(location, faction) WHERE status = 'active';
CREATE INDEX idx_npc_faction_status ON npcs(faction, status);
CREATE INDEX idx_active_conversations ON conversations(npc_id, is_active, started_at);
CREATE INDEX idx_pending_changes ON conversation_changes(npc_id, status, generated_at) WHERE status = 'pending';

-- Create partial indexes for better performance
CREATE INDEX idx_active_npcs ON npcs(updated_at) WHERE status = 'active';
CREATE INDEX idx_recent_conversations ON conversations(started_at) WHERE started_at > NOW() - INTERVAL '7 days';
CREATE INDEX idx_recent_changes ON conversation_changes(generated_at) WHERE generated_at > NOW() - INTERVAL '24 hours';

-- Full-text search indexes
CREATE INDEX idx_npc_name_fulltext ON npcs USING gin(to_tsvector('english', name));
CREATE INDEX idx_npc_occupation_fulltext ON npcs USING gin(to_tsvector('english', background_occupation));

-- Add constraints and triggers

-- Update timestamp trigger function
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Apply update timestamp triggers
CREATE TRIGGER update_npcs_updated_at 
    BEFORE UPDATE ON npcs 
    FOR EACH ROW 
    EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_conversations_updated_at 
    BEFORE UPDATE ON conversations 
    FOR EACH ROW 
    EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_conversation_changes_updated_at 
    BEFORE UPDATE ON conversation_changes 
    FOR EACH ROW 
    EXECUTE FUNCTION update_updated_at_column();

-- Validation functions
CREATE OR REPLACE FUNCTION validate_life_strand_data()
RETURNS TRIGGER AS $$
BEGIN
    -- Ensure required fields exist in JSONB
    IF NOT (NEW.life_strand_data ? 'name') THEN
        RAISE EXCEPTION 'Life strand data must contain name field';
    END IF;
    
    IF NOT (NEW.life_strand_data ? 'personality') THEN
        RAISE EXCEPTION 'Life strand data must contain personality field';
    END IF;
    
    IF NOT (NEW.life_strand_data ? 'background') THEN
        RAISE EXCEPTION 'Life strand data must contain background field';
    END IF;
    
    -- Sync name field
    NEW.name = NEW.life_strand_data->>'name';
    
    -- Sync location from current_status or background
    IF NEW.life_strand_data->'current_status' ? 'location' THEN
        NEW.location = NEW.life_strand_data->'current_status'->>'location';
    ELSIF NEW.life_strand_data->'background' ? 'location' THEN
        NEW.location = NEW.life_strand_data->'background'->>'location';
    END IF;
    
    -- Sync other fields
    IF NEW.life_strand_data->'background' ? 'occupation' THEN
        NEW.background_occupation = NEW.life_strand_data->'background'->>'occupation';
    END IF;
    
    IF NEW.life_strand_data->'background' ? 'age' THEN
        NEW.background_age = (NEW.life_strand_data->'background'->>'age')::integer;
    END IF;
    
    IF NEW.life_strand_data->'personality' ? 'traits' THEN
        NEW.personality_traits = NEW.life_strand_data->'personality'->'traits';
    END IF;
    
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Apply validation trigger
CREATE TRIGGER validate_npc_life_strand 
    BEFORE INSERT OR UPDATE ON npcs 
    FOR EACH ROW 
    EXECUTE FUNCTION validate_life_strand_data();

-- Create views for common queries

-- Active NPCs summary view
CREATE VIEW active_npcs_summary AS
SELECT 
    id,
    name,
    location,
    faction,
    background_occupation,
    background_age,
    personality_traits,
    created_at,
    updated_at
FROM npcs 
WHERE status = 'active'
ORDER BY updated_at DESC;

-- Recent conversations view
CREATE VIEW recent_conversations AS
SELECT 
    c.id,
    c.session_id,
    c.npc_id,
    n.name as npc_name,
    c.user_id,
    c.started_at,
    c.ended_at,
    c.is_active,
    c.message_count,
    c.summary
FROM conversations c
JOIN npcs n ON c.npc_id = n.id
WHERE c.started_at > NOW() - INTERVAL '7 days'
ORDER BY c.started_at DESC;

-- Pending changes view
CREATE VIEW pending_conversation_changes AS
SELECT 
    cc.id,
    cc.conversation_id,
    cc.npc_id,
    n.name as npc_name,
    cc.change_type,
    cc.change_summary,
    cc.confidence_score,
    cc.generated_at
FROM conversation_changes cc
JOIN npcs n ON cc.npc_id = n.id
WHERE cc.status = 'pending'
ORDER BY cc.confidence_score DESC, cc.generated_at ASC;

-- System health view
CREATE VIEW system_health AS
SELECT 
    service_name,
    COUNT(*) as metric_count,
    MAX(recorded_at) as last_recorded,
    AVG(CASE WHEN metric_name = 'response_time_ms' THEN metric_value END) as avg_response_time,
    MAX(CASE WHEN metric_name = 'memory_usage_mb' THEN metric_value END) as max_memory_usage
FROM system_metrics 
WHERE recorded_at > NOW() - INTERVAL '1 hour'
GROUP BY service_name
ORDER BY service_name;

-- Add helpful comments
COMMENT ON TABLE npcs IS 'Core NPC table storing Life Strand data with queryable fields';
COMMENT ON TABLE conversations IS 'Chat sessions between users and NPCs with full transcripts';
COMMENT ON TABLE conversation_changes IS 'Proposed changes to Life Strands extracted from conversations';
COMMENT ON TABLE system_metrics IS 'System performance and health metrics';

COMMENT ON COLUMN npcs.life_strand_data IS 'Full Life Strand data stored as JSONB';
COMMENT ON COLUMN npcs.personality_traits IS 'Extracted personality traits for quick search';
COMMENT ON COLUMN conversations.transcript IS 'Complete conversation messages as JSONB array';
COMMENT ON COLUMN conversation_changes.change_data IS 'Detailed change information as JSONB';
COMMENT ON COLUMN conversation_changes.confidence_score IS 'AI confidence in the proposed change (0.0-1.0)';

-- Migration completion
INSERT INTO system_metrics (metric_type, metric_name, metric_value, service_name, instance_id) 
VALUES ('migration', 'schema_version', 1, 'database', 'initial_migration');