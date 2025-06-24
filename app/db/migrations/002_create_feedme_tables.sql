-- Migration: Create FeedMe tables for customer support transcript ingestion
-- This migration creates the feedme_conversations and feedme_examples tables
-- for storing customer support transcripts and extracting relevant examples

-- 1. Table for storing complete customer support conversations
CREATE TABLE IF NOT EXISTS feedme_conversations (
    id                  BIGSERIAL PRIMARY KEY,
    title               TEXT NOT NULL,                  -- Conversation title/subject
    original_filename   TEXT,                           -- Original uploaded filename
    raw_transcript      TEXT NOT NULL,                  -- Full transcript content
    parsed_content      TEXT,                           -- Cleaned/parsed transcript
    metadata            JSONB DEFAULT '{}',             -- Additional metadata (customer info, tags, etc.)
    uploaded_by         TEXT,                           -- User who uploaded (email/username)
    uploaded_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    processed_at        TIMESTAMPTZ,                    -- When processing completed
    processing_status   TEXT DEFAULT 'pending' CHECK (processing_status IN ('pending', 'processing', 'completed', 'failed')),
    error_message       TEXT,                           -- Error details if processing failed
    total_examples      INTEGER DEFAULT 0,              -- Number of examples extracted
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- 2. Table for storing individual Q&A examples extracted from conversations
CREATE TABLE IF NOT EXISTS feedme_examples (
    id                  BIGSERIAL PRIMARY KEY,
    conversation_id     BIGINT NOT NULL REFERENCES feedme_conversations(id) ON DELETE CASCADE,
    question_text       TEXT NOT NULL,                  -- Customer question/issue
    answer_text         TEXT NOT NULL,                  -- Support agent response/solution
    context_before      TEXT,                           -- Context preceding the Q&A
    context_after       TEXT,                           -- Context following the Q&A
    question_embedding  VECTOR(768),                    -- Question embedding for similarity search
    answer_embedding    VECTOR(768),                    -- Answer embedding for similarity search
    combined_embedding  VECTOR(768),                    -- Combined Q&A embedding for search
    tags                TEXT[],                         -- Categorical tags (e.g., ['account-setup', 'email-sync'])
    issue_type          TEXT,                           -- Issue category
    resolution_type     TEXT,                           -- Type of resolution provided
    confidence_score    FLOAT DEFAULT 0.0,              -- Quality/confidence score for the example
    usefulness_score    FLOAT DEFAULT 0.0,              -- Usefulness rating for retrieval
    is_active           BOOLEAN DEFAULT true,           -- Whether example is active for retrieval
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- 3. Indexes for efficient queries and similarity search

-- Conversation indexes
CREATE INDEX IF NOT EXISTS idx_feedme_conversations_status 
    ON feedme_conversations (processing_status);
CREATE INDEX IF NOT EXISTS idx_feedme_conversations_uploaded_at 
    ON feedme_conversations (uploaded_at DESC);
CREATE INDEX IF NOT EXISTS idx_feedme_conversations_uploaded_by 
    ON feedme_conversations (uploaded_by);

-- Example indexes for similarity search (using ivfflat with cosine distance)
CREATE INDEX IF NOT EXISTS idx_feedme_examples_question_embedding
    ON feedme_examples USING ivfflat (question_embedding vector_cosine_ops) WITH (lists = 100);
CREATE INDEX IF NOT EXISTS idx_feedme_examples_answer_embedding
    ON feedme_examples USING ivfflat (answer_embedding vector_cosine_ops) WITH (lists = 100);
CREATE INDEX IF NOT EXISTS idx_feedme_examples_combined_embedding
    ON feedme_examples USING ivfflat (combined_embedding vector_cosine_ops) WITH (lists = 100);

-- Example indexes for filtering
CREATE INDEX IF NOT EXISTS idx_feedme_examples_conversation_id 
    ON feedme_examples (conversation_id);
CREATE INDEX IF NOT EXISTS idx_feedme_examples_is_active 
    ON feedme_examples (is_active) WHERE is_active = true;
CREATE INDEX IF NOT EXISTS idx_feedme_examples_tags 
    ON feedme_examples USING GIN (tags);
CREATE INDEX IF NOT EXISTS idx_feedme_examples_issue_type 
    ON feedme_examples (issue_type);
CREATE INDEX IF NOT EXISTS idx_feedme_examples_confidence_score 
    ON feedme_examples (confidence_score DESC);

-- 4. Function to automatically update updated_at timestamp
CREATE OR REPLACE FUNCTION update_feedme_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ language 'plpgsql';

-- 5. Triggers to automatically update updated_at
CREATE TRIGGER trigger_feedme_conversations_updated_at
    BEFORE UPDATE ON feedme_conversations
    FOR EACH ROW
    EXECUTE FUNCTION update_feedme_updated_at();

CREATE TRIGGER trigger_feedme_examples_updated_at
    BEFORE UPDATE ON feedme_examples
    FOR EACH ROW
    EXECUTE FUNCTION update_feedme_updated_at();

-- 6. Sample queries for testing (commented out)
/*
-- Test conversation insertion
INSERT INTO feedme_conversations (title, raw_transcript, uploaded_by) 
VALUES ('Email Setup Issue', 'Customer: I cannot setup my email...', 'admin@mailbird.com');

-- Test example insertion
INSERT INTO feedme_examples (conversation_id, question_text, answer_text, tags, issue_type) 
VALUES (1, 'How do I setup IMAP?', 'To setup IMAP, go to Settings...', ARRAY['email-setup', 'imap'], 'configuration');

-- Test similarity search (after embeddings are generated)
SELECT id, question_text, answer_text, 1 - (question_embedding <=> '[embedding_vector]'::vector) AS similarity
FROM feedme_examples 
WHERE is_active = true 
ORDER BY question_embedding <=> '[embedding_vector]'::vector 
LIMIT 5;
*/