-- Migration: Restore FeedMe examples + approval workflow tables
-- Purpose: Ensure FeedMe processing/approval has required tables after schema drift.

-- Ensure pgvector is available for embedding columns.
CREATE EXTENSION IF NOT EXISTS vector;

-- =====================================================
-- Main approved examples table
-- =====================================================
CREATE TABLE IF NOT EXISTS public.feedme_examples (
    id BIGSERIAL PRIMARY KEY,
    conversation_id BIGINT REFERENCES public.feedme_conversations(id) ON DELETE CASCADE,
    question_text TEXT NOT NULL,
    answer_text TEXT NOT NULL,
    context_before TEXT,
    context_after TEXT,
    confidence_score DOUBLE PRECISION DEFAULT 0.5,
    usefulness_score DOUBLE PRECISION DEFAULT 0.5,
    tags TEXT[] DEFAULT '{}'::text[],
    issue_type VARCHAR(50),
    resolution_type VARCHAR(50),
    extraction_method TEXT DEFAULT 'ai',
    extraction_confidence DOUBLE PRECISION DEFAULT 0.0,
    source_position INTEGER DEFAULT 0,
    source_page INTEGER,
    source_format VARCHAR(10) DEFAULT 'text',
    is_active BOOLEAN DEFAULT TRUE,
    review_status TEXT DEFAULT 'pending',
    reviewed_by TEXT,
    reviewed_at TIMESTAMPTZ,
    reviewer_notes TEXT,
    approved_at TIMESTAMPTZ,
    approved_by TEXT,
    supabase_synced BOOLEAN DEFAULT FALSE,
    supabase_sync_status TEXT DEFAULT 'pending',
    supabase_sync_at TIMESTAMPTZ,
    metadata JSONB DEFAULT '{}'::jsonb,
    question_embedding VECTOR(3072),
    answer_embedding VECTOR(3072),
    combined_embedding VECTOR(3072),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

ALTER TABLE public.feedme_examples
    ADD COLUMN IF NOT EXISTS conversation_id BIGINT,
    ADD COLUMN IF NOT EXISTS question_text TEXT,
    ADD COLUMN IF NOT EXISTS answer_text TEXT,
    ADD COLUMN IF NOT EXISTS context_before TEXT,
    ADD COLUMN IF NOT EXISTS context_after TEXT,
    ADD COLUMN IF NOT EXISTS confidence_score DOUBLE PRECISION DEFAULT 0.5,
    ADD COLUMN IF NOT EXISTS usefulness_score DOUBLE PRECISION DEFAULT 0.5,
    ADD COLUMN IF NOT EXISTS tags TEXT[] DEFAULT '{}'::text[],
    ADD COLUMN IF NOT EXISTS issue_type VARCHAR(50),
    ADD COLUMN IF NOT EXISTS resolution_type VARCHAR(50),
    ADD COLUMN IF NOT EXISTS extraction_method TEXT DEFAULT 'ai',
    ADD COLUMN IF NOT EXISTS extraction_confidence DOUBLE PRECISION DEFAULT 0.0,
    ADD COLUMN IF NOT EXISTS source_position INTEGER DEFAULT 0,
    ADD COLUMN IF NOT EXISTS source_page INTEGER,
    ADD COLUMN IF NOT EXISTS source_format VARCHAR(10) DEFAULT 'text',
    ADD COLUMN IF NOT EXISTS is_active BOOLEAN DEFAULT TRUE,
    ADD COLUMN IF NOT EXISTS review_status TEXT DEFAULT 'pending',
    ADD COLUMN IF NOT EXISTS reviewed_by TEXT,
    ADD COLUMN IF NOT EXISTS reviewed_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS reviewer_notes TEXT,
    ADD COLUMN IF NOT EXISTS approved_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS approved_by TEXT,
    ADD COLUMN IF NOT EXISTS supabase_synced BOOLEAN DEFAULT FALSE,
    ADD COLUMN IF NOT EXISTS supabase_sync_status TEXT DEFAULT 'pending',
    ADD COLUMN IF NOT EXISTS supabase_sync_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS metadata JSONB DEFAULT '{}'::jsonb,
    ADD COLUMN IF NOT EXISTS question_embedding VECTOR(3072),
    ADD COLUMN IF NOT EXISTS answer_embedding VECTOR(3072),
    ADD COLUMN IF NOT EXISTS combined_embedding VECTOR(3072),
    ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ DEFAULT NOW(),
    ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ DEFAULT NOW();

-- Basic indexes for feedme_examples
CREATE INDEX IF NOT EXISTS idx_feedme_examples_conversation_id
    ON public.feedme_examples (conversation_id);
CREATE INDEX IF NOT EXISTS idx_feedme_examples_review_status
    ON public.feedme_examples (review_status);
CREATE INDEX IF NOT EXISTS idx_feedme_examples_approved_at
    ON public.feedme_examples (approved_at)
    WHERE approved_at IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_feedme_examples_is_active
    ON public.feedme_examples (is_active);

-- =====================================================
-- Temporary examples table for approval workflow
-- =====================================================
CREATE TABLE IF NOT EXISTS public.feedme_temp_examples (
    id BIGSERIAL PRIMARY KEY,
    conversation_id BIGINT NOT NULL REFERENCES public.feedme_conversations(id) ON DELETE CASCADE,
    question_text TEXT NOT NULL,
    answer_text TEXT NOT NULL,
    context_before TEXT,
    context_after TEXT,
    question_embedding VECTOR(384),
    answer_embedding VECTOR(384),
    combined_embedding VECTOR(384),
    extraction_method VARCHAR(20) DEFAULT 'ai',
    extraction_confidence FLOAT,
    ai_model_used VARCHAR(50),
    extraction_timestamp TIMESTAMPTZ DEFAULT NOW(),
    approval_status VARCHAR(20) DEFAULT 'pending',
    assigned_reviewer TEXT,
    priority VARCHAR(10) DEFAULT 'normal',
    review_notes TEXT,
    rejection_reason VARCHAR(100),
    revision_instructions TEXT,
    reviewer_id TEXT,
    reviewed_at TIMESTAMPTZ,
    reviewer_confidence_score FLOAT,
    reviewer_usefulness_score FLOAT,
    auto_approved BOOLEAN DEFAULT false,
    auto_approval_reason VARCHAR(100),
    confidence_score FLOAT,
    tags TEXT[] DEFAULT '{}'::text[],
    metadata JSONB DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

ALTER TABLE public.feedme_temp_examples
    ADD COLUMN IF NOT EXISTS conversation_id BIGINT,
    ADD COLUMN IF NOT EXISTS question_text TEXT,
    ADD COLUMN IF NOT EXISTS answer_text TEXT,
    ADD COLUMN IF NOT EXISTS context_before TEXT,
    ADD COLUMN IF NOT EXISTS context_after TEXT,
    ADD COLUMN IF NOT EXISTS question_embedding VECTOR(384),
    ADD COLUMN IF NOT EXISTS answer_embedding VECTOR(384),
    ADD COLUMN IF NOT EXISTS combined_embedding VECTOR(384),
    ADD COLUMN IF NOT EXISTS extraction_method VARCHAR(20) DEFAULT 'ai',
    ADD COLUMN IF NOT EXISTS extraction_confidence FLOAT,
    ADD COLUMN IF NOT EXISTS ai_model_used VARCHAR(50),
    ADD COLUMN IF NOT EXISTS extraction_timestamp TIMESTAMPTZ DEFAULT NOW(),
    ADD COLUMN IF NOT EXISTS approval_status VARCHAR(20) DEFAULT 'pending',
    ADD COLUMN IF NOT EXISTS assigned_reviewer TEXT,
    ADD COLUMN IF NOT EXISTS priority VARCHAR(10) DEFAULT 'normal',
    ADD COLUMN IF NOT EXISTS review_notes TEXT,
    ADD COLUMN IF NOT EXISTS rejection_reason VARCHAR(100),
    ADD COLUMN IF NOT EXISTS revision_instructions TEXT,
    ADD COLUMN IF NOT EXISTS reviewer_id TEXT,
    ADD COLUMN IF NOT EXISTS reviewed_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS reviewer_confidence_score FLOAT,
    ADD COLUMN IF NOT EXISTS reviewer_usefulness_score FLOAT,
    ADD COLUMN IF NOT EXISTS auto_approved BOOLEAN DEFAULT false,
    ADD COLUMN IF NOT EXISTS auto_approval_reason VARCHAR(100),
    ADD COLUMN IF NOT EXISTS confidence_score FLOAT,
    ADD COLUMN IF NOT EXISTS tags TEXT[] DEFAULT '{}'::text[],
    ADD COLUMN IF NOT EXISTS metadata JSONB DEFAULT '{}'::jsonb,
    ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ DEFAULT NOW(),
    ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ DEFAULT NOW();

-- Helpful indexes for workflow queries
CREATE INDEX IF NOT EXISTS idx_feedme_temp_examples_status_date
    ON public.feedme_temp_examples (approval_status, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_feedme_temp_examples_reviewer_priority
    ON public.feedme_temp_examples (assigned_reviewer, priority, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_feedme_temp_examples_confidence_date
    ON public.feedme_temp_examples (extraction_confidence DESC, created_at DESC);

-- =====================================================
-- Review history table (best-effort audit trail)
-- =====================================================
CREATE TABLE IF NOT EXISTS public.feedme_review_history (
    id BIGSERIAL PRIMARY KEY,
    temp_example_id BIGINT NOT NULL REFERENCES public.feedme_temp_examples(id) ON DELETE CASCADE,
    reviewer_id TEXT NOT NULL,
    action VARCHAR(20) NOT NULL,
    review_notes TEXT,
    confidence_assessment FLOAT,
    time_spent_minutes INTEGER,
    previous_status VARCHAR(20),
    new_status VARCHAR(20),
    changes_made JSONB,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

ALTER TABLE public.feedme_review_history
    ADD COLUMN IF NOT EXISTS temp_example_id BIGINT,
    ADD COLUMN IF NOT EXISTS reviewer_id TEXT,
    ADD COLUMN IF NOT EXISTS action VARCHAR(20),
    ADD COLUMN IF NOT EXISTS review_notes TEXT,
    ADD COLUMN IF NOT EXISTS confidence_assessment FLOAT,
    ADD COLUMN IF NOT EXISTS time_spent_minutes INTEGER,
    ADD COLUMN IF NOT EXISTS previous_status VARCHAR(20),
    ADD COLUMN IF NOT EXISTS new_status VARCHAR(20),
    ADD COLUMN IF NOT EXISTS changes_made JSONB,
    ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ DEFAULT NOW();

-- =====================================================
-- RLS + Policies (authenticated + service_role)
-- =====================================================
ALTER TABLE public.feedme_examples ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.feedme_temp_examples ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.feedme_review_history ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS feedme_examples_authenticated_select ON public.feedme_examples;
DROP POLICY IF EXISTS feedme_examples_authenticated_insert ON public.feedme_examples;
DROP POLICY IF EXISTS feedme_examples_authenticated_update ON public.feedme_examples;
DROP POLICY IF EXISTS feedme_examples_authenticated_delete ON public.feedme_examples;

CREATE POLICY feedme_examples_authenticated_select ON public.feedme_examples
    FOR SELECT
    USING (auth.role() = 'authenticated' OR auth.jwt() ->> 'role' = 'service_role');
CREATE POLICY feedme_examples_authenticated_insert ON public.feedme_examples
    FOR INSERT
    WITH CHECK (auth.role() = 'authenticated' OR auth.jwt() ->> 'role' = 'service_role');
CREATE POLICY feedme_examples_authenticated_update ON public.feedme_examples
    FOR UPDATE
    USING (auth.role() = 'authenticated' OR auth.jwt() ->> 'role' = 'service_role')
    WITH CHECK (auth.role() = 'authenticated' OR auth.jwt() ->> 'role' = 'service_role');
CREATE POLICY feedme_examples_authenticated_delete ON public.feedme_examples
    FOR DELETE
    USING (auth.role() = 'authenticated' OR auth.jwt() ->> 'role' = 'service_role');

DROP POLICY IF EXISTS feedme_temp_examples_authenticated_select ON public.feedme_temp_examples;
DROP POLICY IF EXISTS feedme_temp_examples_authenticated_insert ON public.feedme_temp_examples;
DROP POLICY IF EXISTS feedme_temp_examples_authenticated_update ON public.feedme_temp_examples;
DROP POLICY IF EXISTS feedme_temp_examples_authenticated_delete ON public.feedme_temp_examples;

CREATE POLICY feedme_temp_examples_authenticated_select ON public.feedme_temp_examples
    FOR SELECT
    USING (auth.role() = 'authenticated' OR auth.jwt() ->> 'role' = 'service_role');
CREATE POLICY feedme_temp_examples_authenticated_insert ON public.feedme_temp_examples
    FOR INSERT
    WITH CHECK (auth.role() = 'authenticated' OR auth.jwt() ->> 'role' = 'service_role');
CREATE POLICY feedme_temp_examples_authenticated_update ON public.feedme_temp_examples
    FOR UPDATE
    USING (auth.role() = 'authenticated' OR auth.jwt() ->> 'role' = 'service_role')
    WITH CHECK (auth.role() = 'authenticated' OR auth.jwt() ->> 'role' = 'service_role');
CREATE POLICY feedme_temp_examples_authenticated_delete ON public.feedme_temp_examples
    FOR DELETE
    USING (auth.role() = 'authenticated' OR auth.jwt() ->> 'role' = 'service_role');

DROP POLICY IF EXISTS feedme_review_history_authenticated_select ON public.feedme_review_history;
DROP POLICY IF EXISTS feedme_review_history_authenticated_insert ON public.feedme_review_history;
DROP POLICY IF EXISTS feedme_review_history_authenticated_update ON public.feedme_review_history;
DROP POLICY IF EXISTS feedme_review_history_authenticated_delete ON public.feedme_review_history;

CREATE POLICY feedme_review_history_authenticated_select ON public.feedme_review_history
    FOR SELECT
    USING (auth.role() = 'authenticated' OR auth.jwt() ->> 'role' = 'service_role');
CREATE POLICY feedme_review_history_authenticated_insert ON public.feedme_review_history
    FOR INSERT
    WITH CHECK (auth.role() = 'authenticated' OR auth.jwt() ->> 'role' = 'service_role');
CREATE POLICY feedme_review_history_authenticated_update ON public.feedme_review_history
    FOR UPDATE
    USING (auth.role() = 'authenticated' OR auth.jwt() ->> 'role' = 'service_role')
    WITH CHECK (auth.role() = 'authenticated' OR auth.jwt() ->> 'role' = 'service_role');
CREATE POLICY feedme_review_history_authenticated_delete ON public.feedme_review_history
    FOR DELETE
    USING (auth.role() = 'authenticated' OR auth.jwt() ->> 'role' = 'service_role');
