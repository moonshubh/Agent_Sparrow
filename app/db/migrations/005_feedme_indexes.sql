-- FeedMe v2.0 Phase 1: Indexes and Functions
-- Create indexes and functions for FeedMe tables

-- Conversation indexes
CREATE INDEX IF NOT EXISTS idx_feedme_conversations_uuid ON feedme_conversations (uuid);
CREATE INDEX IF NOT EXISTS idx_feedme_conversations_status ON feedme_conversations (processing_status);
CREATE INDEX IF NOT EXISTS idx_feedme_conversations_uploaded_at ON feedme_conversations (uploaded_at DESC);
CREATE INDEX IF NOT EXISTS idx_feedme_conversations_uploaded_by ON feedme_conversations (uploaded_by);
CREATE INDEX IF NOT EXISTS idx_feedme_conversations_active ON feedme_conversations (is_active) WHERE is_active = true;
CREATE INDEX IF NOT EXISTS idx_feedme_conversations_version ON feedme_conversations (version DESC);
CREATE INDEX IF NOT EXISTS idx_feedme_conversations_source_type ON feedme_conversations (source_type);
CREATE INDEX IF NOT EXISTS idx_feedme_conversations_quality ON feedme_conversations (quality_score DESC);

-- Example indexes for filtering
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