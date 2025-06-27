-- FeedMe v2.0 Phase 1: Database Unification Migration
-- This migration ensures FeedMe tables exist in Supabase and adds v2.0 enhancements

-- Enable required extensions
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- 1. Create FeedMe conversations table with v2.0 enhancements
CREATE TABLE IF NOT EXISTS feedme_conversations (
    id                  BIGSERIAL PRIMARY KEY,
    uuid                UUID DEFAULT uuid_generate_v4() UNIQUE,  -- V2.0: UUID for external references
    title               TEXT NOT NULL,
    original_filename   TEXT,
    raw_transcript      TEXT NOT NULL,
    parsed_content      TEXT,
    metadata            JSONB DEFAULT '{}',
    uploaded_by         TEXT,
    uploaded_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    processed_at        TIMESTAMPTZ,
    processing_status   TEXT DEFAULT 'pending' CHECK (processing_status IN ('pending', 'processing', 'completed', 'failed')),
    error_message       TEXT,
    total_examples      INTEGER DEFAULT 0,
    
    -- V2.0 Phase 1: Versioning support
    version             INTEGER DEFAULT 1 NOT NULL,
    is_active           BOOLEAN DEFAULT true,
    updated_by          TEXT,
    
    -- V2.0 Phase 1: Enhanced metadata
    source_type         TEXT DEFAULT 'manual' CHECK (source_type IN ('manual', 'api', 'bulk_import')),
    file_size_bytes     BIGINT,
    processing_time_ms  INTEGER,
    quality_score       FLOAT DEFAULT 0.0 CHECK (quality_score >= 0.0 AND quality_score <= 1.0),
    
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- 2. Create FeedMe examples table with v2.0 enhancements
CREATE TABLE IF NOT EXISTS feedme_examples (
    id                  BIGSERIAL PRIMARY KEY,
    uuid                UUID DEFAULT uuid_generate_v4() UNIQUE,  -- V2.0: UUID for external references
    conversation_id     BIGINT NOT NULL REFERENCES feedme_conversations(id) ON DELETE CASCADE,
    
    question_text       TEXT NOT NULL,
    answer_text         TEXT NOT NULL,
    context_before      TEXT,
    context_after       TEXT,
    
    -- Embeddings for similarity search
    question_embedding  VECTOR(768),
    answer_embedding    VECTOR(768),
    combined_embedding  VECTOR(768),
    
    -- Categorization and metadata
    tags                TEXT[],
    issue_type          TEXT,
    resolution_type     TEXT,
    confidence_score    FLOAT DEFAULT 0.0 CHECK (confidence_score >= 0.0 AND confidence_score <= 1.0),
    usefulness_score    FLOAT DEFAULT 0.0 CHECK (usefulness_score >= 0.0 AND usefulness_score <= 1.0),
    is_active           BOOLEAN DEFAULT true,
    
    -- V2.0 Phase 1: Versioning support
    version             INTEGER DEFAULT 1 NOT NULL,
    updated_by          TEXT,
    
    -- V2.0 Phase 5: Adaptive retrieval weights
    retrieval_weight    FLOAT DEFAULT 1.0 CHECK (retrieval_weight >= 0.0 AND retrieval_weight <= 2.0),
    usage_count         INTEGER DEFAULT 0,
    positive_feedback   INTEGER DEFAULT 0,
    negative_feedback   INTEGER DEFAULT 0,
    last_used_at        TIMESTAMPTZ,
    
    -- V2.0 Phase 6: Enhanced analytics
    source_position     INTEGER,  -- Position in original conversation
    extraction_method   TEXT DEFAULT 'ai' CHECK (extraction_method IN ('ai', 'manual', 'semi_auto')),
    extraction_confidence FLOAT DEFAULT 0.0 CHECK (extraction_confidence >= 0.0 AND extraction_confidence <= 1.0),
    
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- 3. Enhanced indexes for v2.0 performance
-- Conversation indexes
CREATE INDEX IF NOT EXISTS idx_feedme_conversations_uuid ON feedme_conversations (uuid);
CREATE INDEX IF NOT EXISTS idx_feedme_conversations_status ON feedme_conversations (processing_status);
CREATE INDEX IF NOT EXISTS idx_feedme_conversations_uploaded_at ON feedme_conversations (uploaded_at DESC);
CREATE INDEX IF NOT EXISTS idx_feedme_conversations_uploaded_by ON feedme_conversations (uploaded_by);
CREATE INDEX IF NOT EXISTS idx_feedme_conversations_active ON feedme_conversations (is_active) WHERE is_active = true;
CREATE INDEX IF NOT EXISTS idx_feedme_conversations_version ON feedme_conversations (version DESC);
CREATE INDEX IF NOT EXISTS idx_feedme_conversations_source_type ON feedme_conversations (source_type);
CREATE INDEX IF NOT EXISTS idx_feedme_conversations_quality ON feedme_conversations (quality_score DESC);

-- Example indexes for similarity search and filtering
CREATE INDEX IF NOT EXISTS idx_feedme_examples_uuid ON feedme_examples (uuid);
CREATE INDEX IF NOT EXISTS idx_feedme_examples_conversation_id ON feedme_examples (conversation_id);
CREATE INDEX IF NOT EXISTS idx_feedme_examples_is_active ON feedme_examples (is_active) WHERE is_active = true;
CREATE INDEX IF NOT EXISTS idx_feedme_examples_tags ON feedme_examples USING GIN (tags);
CREATE INDEX IF NOT EXISTS idx_feedme_examples_issue_type ON feedme_examples (issue_type);
CREATE INDEX IF NOT EXISTS idx_feedme_examples_confidence_score ON feedme_examples (confidence_score DESC);
CREATE INDEX IF NOT EXISTS idx_feedme_examples_usefulness_score ON feedme_examples (usefulness_score DESC);
CREATE INDEX IF NOT EXISTS idx_feedme_examples_version ON feedme_examples (version DESC);
CREATE INDEX IF NOT EXISTS idx_feedme_examples_retrieval_weight ON feedme_examples (retrieval_weight DESC);
CREATE INDEX IF NOT EXISTS idx_feedme_examples_usage_count ON feedme_examples (usage_count DESC);
CREATE INDEX IF NOT EXISTS idx_feedme_examples_last_used ON feedme_examples (last_used_at DESC);

-- Vector similarity search indexes (conditional creation for safety)
DO $$
BEGIN
    -- Check if vector extension is available before creating vector indexes
    IF EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'vector') THEN
        -- Create vector indexes if they don't exist
        BEGIN
            CREATE INDEX IF NOT EXISTS idx_feedme_examples_question_embedding
                ON feedme_examples USING ivfflat (question_embedding vector_cosine_ops) WITH (lists = 100);
        EXCEPTION WHEN OTHERS THEN
            RAISE NOTICE 'Could not create question_embedding index: %', SQLERRM;
        END;
        
        BEGIN
            CREATE INDEX IF NOT EXISTS idx_feedme_examples_answer_embedding
                ON feedme_examples USING ivfflat (answer_embedding vector_cosine_ops) WITH (lists = 100);
        EXCEPTION WHEN OTHERS THEN
            RAISE NOTICE 'Could not create answer_embedding index: %', SQLERRM;
        END;
        
        BEGIN
            CREATE INDEX IF NOT EXISTS idx_feedme_examples_combined_embedding
                ON feedme_examples USING ivfflat (combined_embedding vector_cosine_ops) WITH (lists = 100);
        EXCEPTION WHEN OTHERS THEN
            RAISE NOTICE 'Could not create combined_embedding index: %', SQLERRM;
        END;
        
        RAISE NOTICE 'Vector indexes created successfully';
    ELSE
        RAISE NOTICE 'Vector extension not available, skipping vector indexes';
    END IF;
END $$;

-- 4. Enhanced functions and triggers for v2.0
CREATE OR REPLACE FUNCTION update_feedme_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ language 'plpgsql';

-- Create or replace function to update version and track changes
CREATE OR REPLACE FUNCTION increment_feedme_version()
RETURNS TRIGGER AS $$
BEGIN
    -- Increment version for any content changes
    IF OLD.question_text IS DISTINCT FROM NEW.question_text 
       OR OLD.answer_text IS DISTINCT FROM NEW.answer_text 
       OR OLD.tags IS DISTINCT FROM NEW.tags
       OR OLD.issue_type IS DISTINCT FROM NEW.issue_type
       OR OLD.resolution_type IS DISTINCT FROM NEW.resolution_type THEN
        NEW.version = OLD.version + 1;
    END IF;
    
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ language 'plpgsql';

-- Create or replace function to update retrieval weights based on feedback
CREATE OR REPLACE FUNCTION update_retrieval_weight()
RETURNS TRIGGER AS $$
DECLARE
    total_feedback INTEGER;
    positive_ratio FLOAT;
BEGIN
    -- Calculate new retrieval weight based on feedback
    total_feedback = NEW.positive_feedback + NEW.negative_feedback;
    
    IF total_feedback > 0 THEN
        positive_ratio = NEW.positive_feedback::FLOAT / total_feedback;
        -- Weight ranges from 0.1 (all negative) to 2.0 (all positive)
        NEW.retrieval_weight = 0.1 + (positive_ratio * 1.9);
    END IF;
    
    RETURN NEW;
END;
$$ language 'plpgsql';

-- 5. Create triggers for automatic updates
CREATE TRIGGER trigger_feedme_conversations_updated_at
    BEFORE UPDATE ON feedme_conversations
    FOR EACH ROW
    EXECUTE FUNCTION update_feedme_updated_at();

CREATE TRIGGER trigger_feedme_examples_updated_at
    BEFORE UPDATE ON feedme_examples
    FOR EACH ROW
    EXECUTE FUNCTION increment_feedme_version();

CREATE TRIGGER trigger_feedme_examples_retrieval_weight
    BEFORE UPDATE ON feedme_examples
    FOR EACH ROW
    WHEN (OLD.positive_feedback IS DISTINCT FROM NEW.positive_feedback 
          OR OLD.negative_feedback IS DISTINCT FROM NEW.negative_feedback)
    EXECUTE FUNCTION update_retrieval_weight();

-- 6. Create views for common queries
CREATE OR REPLACE VIEW feedme_active_examples AS
SELECT 
    e.*,
    c.title as conversation_title,
    c.uploaded_by as conversation_uploaded_by,
    c.uploaded_at as conversation_uploaded_at,
    c.quality_score as conversation_quality_score
FROM feedme_examples e
JOIN feedme_conversations c ON e.conversation_id = c.id
WHERE e.is_active = true AND c.is_active = true
ORDER BY e.retrieval_weight DESC, e.usefulness_score DESC;

CREATE OR REPLACE VIEW feedme_conversation_stats AS
SELECT 
    c.id,
    c.title,
    c.processing_status,
    c.total_examples,
    COUNT(e.id) as actual_examples,
    AVG(e.confidence_score) as avg_confidence,
    AVG(e.usefulness_score) as avg_usefulness,
    AVG(e.retrieval_weight) as avg_retrieval_weight,
    SUM(e.usage_count) as total_usage,
    MAX(e.last_used_at) as last_example_used
FROM feedme_conversations c
LEFT JOIN feedme_examples e ON c.id = e.conversation_id AND e.is_active = true
GROUP BY c.id, c.title, c.processing_status, c.total_examples;

-- 7. Grant permissions (if needed)
-- These grants are conditional and may not be necessary in all environments
DO $$
BEGIN
    -- Grant permissions to authenticated users
    GRANT SELECT, INSERT, UPDATE, DELETE ON feedme_conversations TO authenticated;
    GRANT SELECT, INSERT, UPDATE, DELETE ON feedme_examples TO authenticated;
    GRANT USAGE ON SEQUENCE feedme_conversations_id_seq TO authenticated;
    GRANT USAGE ON SEQUENCE feedme_examples_id_seq TO authenticated;
    GRANT SELECT ON feedme_active_examples TO authenticated;
    GRANT SELECT ON feedme_conversation_stats TO authenticated;
EXCEPTION WHEN insufficient_privilege THEN
    RAISE NOTICE 'Could not grant permissions - may not be necessary in this environment';
END $$;

-- 8. Insert migration record
INSERT INTO _sqlx_migrations (version, description, installed_on, success) 
VALUES (
    20250625000001, 
    'FeedMe v2.0 Phase 1: Database Unification',
    NOW(),
    true
) ON CONFLICT (version) DO NOTHING;