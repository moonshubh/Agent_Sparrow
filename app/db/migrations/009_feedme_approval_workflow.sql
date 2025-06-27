-- Migration 009: FeedMe Approval Workflow Enhancement
-- Adds approval states, reviewer tracking, and processing fields for complete workflow management

-- Add approval workflow fields to feedme_conversations
ALTER TABLE feedme_conversations 
ADD COLUMN IF NOT EXISTS approval_status TEXT DEFAULT 'pending' 
    CHECK (approval_status IN ('pending', 'processed', 'approved', 'rejected', 'published'));

ALTER TABLE feedme_conversations 
ADD COLUMN IF NOT EXISTS approved_by TEXT;

ALTER TABLE feedme_conversations 
ADD COLUMN IF NOT EXISTS approved_at TIMESTAMPTZ;

ALTER TABLE feedme_conversations 
ADD COLUMN IF NOT EXISTS rejected_at TIMESTAMPTZ;

ALTER TABLE feedme_conversations 
ADD COLUMN IF NOT EXISTS reviewer_notes TEXT;

-- Add processing timeline fields
ALTER TABLE feedme_conversations 
ADD COLUMN IF NOT EXISTS processing_started_at TIMESTAMPTZ;

ALTER TABLE feedme_conversations 
ADD COLUMN IF NOT EXISTS processing_completed_at TIMESTAMPTZ;

ALTER TABLE feedme_conversations 
ADD COLUMN IF NOT EXISTS processing_error TEXT;

ALTER TABLE feedme_conversations 
ADD COLUMN IF NOT EXISTS processing_time_ms INTEGER;

-- Add quality and statistics fields
ALTER TABLE feedme_conversations 
ADD COLUMN IF NOT EXISTS quality_score FLOAT DEFAULT 0.0 CHECK (quality_score >= 0.0 AND quality_score <= 1.0);

ALTER TABLE feedme_conversations 
ADD COLUMN IF NOT EXISTS high_quality_examples INTEGER DEFAULT 0;

ALTER TABLE feedme_conversations 
ADD COLUMN IF NOT EXISTS medium_quality_examples INTEGER DEFAULT 0;

ALTER TABLE feedme_conversations 
ADD COLUMN IF NOT EXISTS low_quality_examples INTEGER DEFAULT 0;

-- Add UUID field if not exists for external references
ALTER TABLE feedme_conversations 
ADD COLUMN IF NOT EXISTS uuid UUID DEFAULT gen_random_uuid();

-- Create unique index on UUID
CREATE UNIQUE INDEX IF NOT EXISTS idx_feedme_conversations_uuid 
    ON feedme_conversations (uuid);

-- Add processing fields to feedme_examples
ALTER TABLE feedme_examples 
ADD COLUMN IF NOT EXISTS extraction_method TEXT DEFAULT 'ai';

ALTER TABLE feedme_examples 
ADD COLUMN IF NOT EXISTS extraction_confidence FLOAT DEFAULT 0.0 
    CHECK (extraction_confidence >= 0.0 AND extraction_confidence <= 1.0);

ALTER TABLE feedme_examples 
ADD COLUMN IF NOT EXISTS source_position INTEGER DEFAULT 0;

ALTER TABLE feedme_examples 
ADD COLUMN IF NOT EXISTS reviewed_by TEXT;

ALTER TABLE feedme_examples 
ADD COLUMN IF NOT EXISTS reviewed_at TIMESTAMPTZ;

ALTER TABLE feedme_examples 
ADD COLUMN IF NOT EXISTS review_status TEXT DEFAULT 'pending' 
    CHECK (review_status IN ('pending', 'approved', 'rejected', 'edited'));

-- Add indexes for approval workflow queries
CREATE INDEX IF NOT EXISTS idx_feedme_conversations_approval_status 
    ON feedme_conversations (approval_status);

CREATE INDEX IF NOT EXISTS idx_feedme_conversations_approved_by 
    ON feedme_conversations (approved_by) WHERE approved_by IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_feedme_conversations_processing_timeline 
    ON feedme_conversations (processing_started_at, processing_completed_at);

CREATE INDEX IF NOT EXISTS idx_feedme_examples_review_status 
    ON feedme_examples (review_status);

CREATE INDEX IF NOT EXISTS idx_feedme_examples_extraction_method 
    ON feedme_examples (extraction_method);

-- Create approval workflow statistics view
CREATE OR REPLACE VIEW feedme_approval_stats AS
SELECT 
    COUNT(*) as total_conversations,
    COUNT(*) FILTER (WHERE approval_status = 'pending') as pending_approval,
    COUNT(*) FILTER (WHERE approval_status = 'processed') as awaiting_review,
    COUNT(*) FILTER (WHERE approval_status = 'approved') as approved,
    COUNT(*) FILTER (WHERE approval_status = 'rejected') as rejected,
    COUNT(*) FILTER (WHERE approval_status = 'published') as published,
    COUNT(*) FILTER (WHERE processing_status = 'processing') as currently_processing,
    COUNT(*) FILTER (WHERE processing_status = 'failed') as processing_failed,
    AVG(quality_score) FILTER (WHERE quality_score > 0) as avg_quality_score,
    AVG(processing_time_ms) FILTER (WHERE processing_time_ms > 0) as avg_processing_time_ms
FROM feedme_conversations;

-- Create function to update conversation quality metrics
CREATE OR REPLACE FUNCTION update_conversation_quality_metrics()
RETURNS TRIGGER AS $$
BEGIN
    -- Update quality counts when examples are inserted/updated
    UPDATE feedme_conversations 
    SET 
        high_quality_examples = (
            SELECT COUNT(*) FROM feedme_examples 
            WHERE conversation_id = NEW.conversation_id 
            AND confidence_score >= 0.8
        ),
        medium_quality_examples = (
            SELECT COUNT(*) FROM feedme_examples 
            WHERE conversation_id = NEW.conversation_id 
            AND confidence_score >= 0.5 AND confidence_score < 0.8
        ),
        low_quality_examples = (
            SELECT COUNT(*) FROM feedme_examples 
            WHERE conversation_id = NEW.conversation_id 
            AND confidence_score < 0.5
        ),
        quality_score = (
            SELECT AVG(confidence_score) FROM feedme_examples 
            WHERE conversation_id = NEW.conversation_id
        )
    WHERE id = NEW.conversation_id;
    
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Create trigger to automatically update quality metrics
DROP TRIGGER IF EXISTS trigger_feedme_examples_quality_update ON feedme_examples;
CREATE TRIGGER trigger_feedme_examples_quality_update
    AFTER INSERT OR UPDATE OF confidence_score ON feedme_examples
    FOR EACH ROW
    EXECUTE FUNCTION update_conversation_quality_metrics();

-- Create function to automatically transition approval status
CREATE OR REPLACE FUNCTION auto_transition_approval_status()
RETURNS TRIGGER AS $$
BEGIN
    -- When processing is completed, move to processed status if not already approved/rejected
    IF NEW.processing_status = 'completed' AND OLD.processing_status != 'completed' THEN
        IF NEW.approval_status IN ('pending') THEN
            NEW.approval_status = 'processed';
            NEW.processing_completed_at = NOW();
        END IF;
    END IF;
    
    -- When processing starts, ensure we're not in processed status
    IF NEW.processing_status = 'processing' AND OLD.processing_status != 'processing' THEN
        NEW.processing_started_at = NOW();
        NEW.processing_error = NULL;
    END IF;
    
    -- When processing fails, reset approval status if appropriate
    IF NEW.processing_status = 'failed' AND OLD.processing_status != 'failed' THEN
        IF NEW.approval_status = 'processed' THEN
            NEW.approval_status = 'pending';
        END IF;
    END IF;
    
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Create trigger for automatic approval status transitions
DROP TRIGGER IF EXISTS trigger_feedme_auto_approval_transition ON feedme_conversations;
CREATE TRIGGER trigger_feedme_auto_approval_transition
    BEFORE UPDATE ON feedme_conversations
    FOR EACH ROW
    EXECUTE FUNCTION auto_transition_approval_status();

-- Add comments for documentation
COMMENT ON COLUMN feedme_conversations.approval_status IS 'Approval workflow status: pending -> processed -> approved/rejected -> published';
COMMENT ON COLUMN feedme_conversations.approved_by IS 'User who approved/rejected the conversation';
COMMENT ON COLUMN feedme_conversations.reviewer_notes IS 'Notes from the reviewer about the approval/rejection';
COMMENT ON COLUMN feedme_conversations.quality_score IS 'Average quality score of all examples in this conversation';
COMMENT ON COLUMN feedme_conversations.processing_time_ms IS 'Time taken to process the conversation in milliseconds';

COMMENT ON VIEW feedme_approval_stats IS 'Real-time statistics for approval workflow management';

-- Sample queries for testing (commented out)
/*
-- Check approval workflow status
SELECT approval_status, COUNT(*) 
FROM feedme_conversations 
GROUP BY approval_status;

-- Get conversations awaiting review
SELECT id, title, approval_status, processing_status, quality_score, total_examples
FROM feedme_conversations 
WHERE approval_status = 'processed'
ORDER BY processing_completed_at DESC;

-- Get approval workflow statistics
SELECT * FROM feedme_approval_stats;

-- Update a conversation to approved status
UPDATE feedme_conversations 
SET approval_status = 'approved', 
    approved_by = 'admin@mailbird.com', 
    approved_at = NOW(),
    reviewer_notes = 'High quality examples extracted successfully'
WHERE id = 1;
*/