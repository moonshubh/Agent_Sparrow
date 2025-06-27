-- FeedMe v2.0 Phase 2: Temporary Examples Table for Preview & Approval Workflow
-- This migration adds support for preview and approval workflow before Q&A pairs are finalized

-- Add fields to conversations table for content type and extraction method
ALTER TABLE feedme_conversations
ADD COLUMN IF NOT EXISTS content_type VARCHAR(20) DEFAULT 'text',
ADD COLUMN IF NOT EXISTS extraction_method VARCHAR(20),
ADD COLUMN IF NOT EXISTS approval_status VARCHAR(20) DEFAULT 'pending',
ADD COLUMN IF NOT EXISTS approved_by VARCHAR(255),
ADD COLUMN IF NOT EXISTS approved_at TIMESTAMP;

-- Create temporary examples table for pre-approval storage
CREATE TABLE IF NOT EXISTS feedme_examples_temp (
    id SERIAL PRIMARY KEY,
    conversation_id INTEGER REFERENCES feedme_conversations(id) ON DELETE CASCADE,
    question_text TEXT NOT NULL,
    answer_text TEXT NOT NULL,
    context_before TEXT,
    context_after TEXT,
    confidence_score FLOAT DEFAULT 0.5,
    quality_score FLOAT DEFAULT 0.5,
    tags TEXT[] DEFAULT '{}',
    issue_type VARCHAR(50),
    resolution_type VARCHAR(50),
    extraction_method VARCHAR(20) DEFAULT 'html',
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Create indexes for performance
CREATE INDEX IF NOT EXISTS idx_feedme_examples_temp_conversation 
ON feedme_examples_temp(conversation_id);

CREATE INDEX IF NOT EXISTS idx_feedme_examples_temp_confidence 
ON feedme_examples_temp(confidence_score DESC);

CREATE INDEX IF NOT EXISTS idx_feedme_conversations_approval 
ON feedme_conversations(approval_status);

-- Function to move approved examples from temp to main table
CREATE OR REPLACE FUNCTION approve_conversation_examples(
    p_conversation_id INTEGER,
    p_approved_by VARCHAR(255),
    p_selected_example_ids INTEGER[] DEFAULT NULL
) RETURNS INTEGER AS $$
DECLARE
    v_count INTEGER;
    v_example_condition TEXT;
BEGIN
    -- Build condition for selected examples
    IF p_selected_example_ids IS NOT NULL AND array_length(p_selected_example_ids, 1) > 0 THEN
        v_example_condition = ' AND id = ANY($3)';
    ELSE
        v_example_condition = '';
    END IF;
    
    -- Copy temp examples to main table (selected ones or all)
    IF p_selected_example_ids IS NOT NULL AND array_length(p_selected_example_ids, 1) > 0 THEN
        INSERT INTO feedme_examples (
            conversation_id,
            question_text,
            answer_text,
            context_before,
            context_after,
            confidence_score,
            tags,
            issue_type,
            resolution_type,
            extraction_method,
            extraction_confidence,
            source_position,
            is_active,
            created_at,
            updated_at
        )
        SELECT 
            conversation_id,
            question_text,
            answer_text,
            context_before,
            context_after,
            confidence_score,
            tags,
            issue_type,
            resolution_type,
            extraction_method,
            confidence_score,  -- Use confidence_score as extraction_confidence
            row_number() OVER (ORDER BY confidence_score DESC),
            true,
            created_at,
            NOW()
        FROM feedme_examples_temp
        WHERE conversation_id = p_conversation_id
        AND id = ANY(p_selected_example_ids);
    ELSE
        INSERT INTO feedme_examples (
            conversation_id,
            question_text,
            answer_text,
            context_before,
            context_after,
            confidence_score,
            tags,
            issue_type,
            resolution_type,
            extraction_method,
            extraction_confidence,
            source_position,
            is_active,
            created_at,
            updated_at
        )
        SELECT 
            conversation_id,
            question_text,
            answer_text,
            context_before,
            context_after,
            confidence_score,
            tags,
            issue_type,
            resolution_type,
            extraction_method,
            confidence_score,  -- Use confidence_score as extraction_confidence
            row_number() OVER (ORDER BY confidence_score DESC),
            true,
            created_at,
            NOW()
        FROM feedme_examples_temp
        WHERE conversation_id = p_conversation_id;
    END IF;
    
    GET DIAGNOSTICS v_count = ROW_COUNT;
    
    -- Delete approved temp examples
    IF p_selected_example_ids IS NOT NULL AND array_length(p_selected_example_ids, 1) > 0 THEN
        DELETE FROM feedme_examples_temp 
        WHERE conversation_id = p_conversation_id
        AND id = ANY(p_selected_example_ids);
    ELSE
        DELETE FROM feedme_examples_temp 
        WHERE conversation_id = p_conversation_id;
    END IF;
    
    -- Update conversation status
    UPDATE feedme_conversations
    SET approval_status = 'approved',
        approved_by = p_approved_by,
        approved_at = NOW(),
        total_examples = COALESCE(total_examples, 0) + v_count,
        updated_at = NOW()
    WHERE id = p_conversation_id;
    
    RETURN v_count;
END;
$$ LANGUAGE plpgsql;

-- Function to reject conversation examples
CREATE OR REPLACE FUNCTION reject_conversation_examples(
    p_conversation_id INTEGER,
    p_rejected_by VARCHAR(255),
    p_rejection_reason TEXT DEFAULT NULL
) RETURNS INTEGER AS $$
DECLARE
    v_count INTEGER;
BEGIN
    -- Count examples to be rejected
    SELECT COUNT(*) INTO v_count
    FROM feedme_examples_temp
    WHERE conversation_id = p_conversation_id;
    
    -- Delete temp examples
    DELETE FROM feedme_examples_temp 
    WHERE conversation_id = p_conversation_id;
    
    -- Update conversation status
    UPDATE feedme_conversations
    SET approval_status = 'rejected',
        approved_by = p_rejected_by,
        approved_at = NOW(),
        metadata = COALESCE(metadata, '{}') || jsonb_build_object(
            'rejection_reason', p_rejection_reason,
            'rejected_examples_count', v_count
        ),
        updated_at = NOW()
    WHERE id = p_conversation_id;
    
    RETURN v_count;
END;
$$ LANGUAGE plpgsql;

-- Function to get conversation processing summary
CREATE OR REPLACE FUNCTION get_conversation_summary(p_conversation_id INTEGER)
RETURNS TABLE (
    conversation_id INTEGER,
    title TEXT,
    processing_status TEXT,
    approval_status TEXT,
    temp_examples_count BIGINT,
    approved_examples_count BIGINT,
    content_type TEXT,
    extraction_method TEXT,
    uploaded_at TIMESTAMP,
    processed_at TIMESTAMP,
    approved_at TIMESTAMP
) AS $$
BEGIN
    RETURN QUERY
    SELECT 
        c.id,
        c.title,
        c.processing_status,
        c.approval_status,
        COALESCE(t.temp_count, 0),
        COALESCE(a.approved_count, 0),
        c.content_type,
        c.extraction_method,
        c.uploaded_at,
        c.processed_at,
        c.approved_at
    FROM feedme_conversations c
    LEFT JOIN (
        SELECT conversation_id, COUNT(*) as temp_count
        FROM feedme_examples_temp
        GROUP BY conversation_id
    ) t ON c.id = t.conversation_id
    LEFT JOIN (
        SELECT conversation_id, COUNT(*) as approved_count
        FROM feedme_examples
        WHERE is_active = true
        GROUP BY conversation_id
    ) a ON c.id = a.conversation_id
    WHERE c.id = p_conversation_id;
END;
$$ LANGUAGE plpgsql;

-- Add comment for tracking
COMMENT ON TABLE feedme_examples_temp IS 'Temporary storage for extracted Q&A examples before human approval';
COMMENT ON FUNCTION approve_conversation_examples IS 'Approve and move selected examples from temp to main table';
COMMENT ON FUNCTION reject_conversation_examples IS 'Reject and delete temp examples for a conversation';
COMMENT ON FUNCTION get_conversation_summary IS 'Get comprehensive summary of conversation processing status';