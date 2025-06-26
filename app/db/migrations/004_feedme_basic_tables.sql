-- FeedMe v2.0 Phase 1: Basic Tables Creation
-- Simple migration to create core FeedMe tables

-- Enable required extensions
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- 1. Create FeedMe conversations table
CREATE TABLE IF NOT EXISTS feedme_conversations (
    id                  BIGSERIAL PRIMARY KEY,
    uuid                UUID DEFAULT uuid_generate_v4() UNIQUE,
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
    version             INTEGER DEFAULT 1 NOT NULL,
    is_active           BOOLEAN DEFAULT true,
    updated_by          TEXT,
    source_type         TEXT DEFAULT 'manual' CHECK (source_type IN ('manual', 'api', 'bulk_import')),
    file_size_bytes     BIGINT,
    processing_time_ms  INTEGER,
    quality_score       FLOAT DEFAULT 0.0 CHECK (quality_score >= 0.0 AND quality_score <= 1.0),
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- 2. Create FeedMe examples table
CREATE TABLE IF NOT EXISTS feedme_examples (
    id                  BIGSERIAL PRIMARY KEY,
    uuid                UUID DEFAULT uuid_generate_v4() UNIQUE,
    conversation_id     BIGINT NOT NULL REFERENCES feedme_conversations(id) ON DELETE CASCADE,
    question_text       TEXT NOT NULL,
    answer_text         TEXT NOT NULL,
    context_before      TEXT,
    context_after       TEXT,
    question_embedding  VECTOR(768),
    answer_embedding    VECTOR(768),
    combined_embedding  VECTOR(768),
    tags                TEXT[],
    issue_type          TEXT,
    resolution_type     TEXT,
    confidence_score    FLOAT DEFAULT 0.0 CHECK (confidence_score >= 0.0 AND confidence_score <= 1.0),
    usefulness_score    FLOAT DEFAULT 0.0 CHECK (usefulness_score >= 0.0 AND usefulness_score <= 1.0),
    is_active           BOOLEAN DEFAULT true,
    version             INTEGER DEFAULT 1 NOT NULL,
    updated_by          TEXT,
    retrieval_weight    FLOAT DEFAULT 1.0 CHECK (retrieval_weight >= 0.0 AND retrieval_weight <= 2.0),
    usage_count         INTEGER DEFAULT 0,
    positive_feedback   INTEGER DEFAULT 0,
    negative_feedback   INTEGER DEFAULT 0,
    last_used_at        TIMESTAMPTZ,
    source_position     INTEGER,
    extraction_method   TEXT DEFAULT 'ai' CHECK (extraction_method IN ('ai', 'manual', 'semi_auto')),
    extraction_confidence FLOAT DEFAULT 0.0 CHECK (extraction_confidence >= 0.0 AND extraction_confidence <= 1.0),
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);