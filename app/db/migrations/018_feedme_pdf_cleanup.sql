-- Migration: FeedMe PDF Cleanup After Text Extraction
-- Date: 2025-08-03
-- Description: Add support for removing PDF content after text extraction and approval

-- =====================================================
-- SECTION 1: ADD PDF CLEANUP TRACKING
-- =====================================================

-- 1. Add column to track if PDF has been cleaned up
DO $$
BEGIN
    -- Add flag to track PDF cleanup status
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'feedme_conversations' AND column_name = 'pdf_cleaned') THEN
        ALTER TABLE feedme_conversations ADD COLUMN pdf_cleaned BOOLEAN DEFAULT FALSE;
    END IF;
    
    -- Add timestamp for when PDF was cleaned
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'feedme_conversations' AND column_name = 'pdf_cleaned_at') THEN
        ALTER TABLE feedme_conversations ADD COLUMN pdf_cleaned_at TIMESTAMPTZ;
    END IF;
    
    -- Add column to store original PDF size for analytics
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'feedme_conversations' AND column_name = 'original_pdf_size') THEN
        ALTER TABLE feedme_conversations ADD COLUMN original_pdf_size INTEGER;
    END IF;
END $$;

-- 2. Create index for finding conversations that need PDF cleanup
CREATE INDEX IF NOT EXISTS idx_feedme_conversations_pdf_cleanup 
    ON feedme_conversations(pdf_cleaned, approved_at) 
    WHERE pdf_cleaned = FALSE AND approved_at IS NOT NULL;

-- =====================================================
-- SECTION 2: CREATE PDF CLEANUP FUNCTION
-- =====================================================

-- 3. Function to clean PDF content after approval
CREATE OR REPLACE FUNCTION cleanup_approved_pdf(conversation_id INTEGER)
RETURNS BOOLEAN AS $$
DECLARE
    v_approved_at TIMESTAMPTZ;
    v_extracted_text TEXT;
    v_pdf_size INTEGER;
BEGIN
    -- Check if conversation exists and is approved
    SELECT approved_at, extracted_text, LENGTH(raw_transcript::text)
    INTO v_approved_at, v_extracted_text, v_pdf_size
    FROM feedme_conversations
    WHERE id = conversation_id;
    
    IF NOT FOUND THEN
        RAISE EXCEPTION 'Conversation % not found', conversation_id;
    END IF;
    
    IF v_approved_at IS NULL THEN
        RAISE EXCEPTION 'Conversation % is not approved yet', conversation_id;
    END IF;
    
    IF v_extracted_text IS NULL OR LENGTH(v_extracted_text) = 0 THEN
        RAISE EXCEPTION 'Conversation % has no extracted text', conversation_id;
    END IF;
    
    -- Store original size and clear PDF content
    UPDATE feedme_conversations
    SET 
        raw_transcript = NULL,  -- Clear PDF/binary content
        pdf_cleaned = TRUE,
        pdf_cleaned_at = NOW(),
        original_pdf_size = v_pdf_size
    WHERE id = conversation_id
    AND pdf_cleaned = FALSE;
    
    -- Return true if cleanup was performed
    RETURN FOUND;
END;
$$ LANGUAGE plpgsql;

-- 4. Batch cleanup function for multiple conversations
CREATE OR REPLACE FUNCTION cleanup_approved_pdfs_batch(limit_count INTEGER DEFAULT 100)
RETURNS TABLE(cleaned_count INTEGER, total_size_freed BIGINT) AS $$
DECLARE
    v_cleaned_count INTEGER := 0;
    v_total_size BIGINT := 0;
    v_conversation RECORD;
BEGIN
    -- Find approved conversations with uncleaned PDFs
    FOR v_conversation IN 
        SELECT id, LENGTH(raw_transcript::text) as pdf_size
        FROM feedme_conversations
        WHERE approved_at IS NOT NULL 
        AND pdf_cleaned = FALSE
        AND extracted_text IS NOT NULL
        AND processing_method = 'pdf_ocr'
        LIMIT limit_count
    LOOP
        -- Try to clean up this conversation
        BEGIN
            IF cleanup_approved_pdf(v_conversation.id) THEN
                v_cleaned_count := v_cleaned_count + 1;
                v_total_size := v_total_size + v_conversation.pdf_size;
            END IF;
        EXCEPTION WHEN OTHERS THEN
            -- Log error but continue with other conversations
            RAISE NOTICE 'Failed to cleanup conversation %: %', v_conversation.id, SQLERRM;
        END;
    END LOOP;
    
    -- Return results
    cleaned_count := v_cleaned_count;
    total_size_freed := v_total_size;
    RETURN NEXT;
END;
$$ LANGUAGE plpgsql;

-- =====================================================
-- SECTION 3: ADD ANALYTICS VIEW
-- =====================================================

-- 5. Create view for PDF storage analytics
CREATE OR REPLACE VIEW feedme_pdf_storage_analytics AS
SELECT 
    COUNT(*) FILTER (WHERE pdf_cleaned = FALSE AND approved_at IS NOT NULL) as pending_cleanup,
    COUNT(*) FILTER (WHERE pdf_cleaned = TRUE) as cleaned_count,
    SUM(original_pdf_size) FILTER (WHERE pdf_cleaned = TRUE) / 1024.0 / 1024.0 as total_mb_freed,
    AVG(original_pdf_size) FILTER (WHERE original_pdf_size IS NOT NULL) / 1024.0 / 1024.0 as avg_pdf_size_mb,
    COUNT(*) FILTER (WHERE processing_method = 'pdf_ocr') as total_pdf_conversations
FROM feedme_conversations;

-- =====================================================
-- SECTION 4: UPDATE COMMENTS
-- =====================================================

COMMENT ON COLUMN feedme_conversations.pdf_cleaned IS 'Flag indicating if original PDF content has been removed after approval';
COMMENT ON COLUMN feedme_conversations.pdf_cleaned_at IS 'Timestamp when PDF content was cleaned up';
COMMENT ON COLUMN feedme_conversations.original_pdf_size IS 'Original size of PDF content in bytes before cleanup';
COMMENT ON FUNCTION cleanup_approved_pdf IS 'Removes PDF content from approved conversations to save storage';
COMMENT ON FUNCTION cleanup_approved_pdfs_batch IS 'Batch process to clean up multiple approved PDFs';
COMMENT ON VIEW feedme_pdf_storage_analytics IS 'Analytics view for PDF storage and cleanup metrics';

-- =====================================================
-- SECTION 5: MIGRATION VALIDATION
-- =====================================================

DO $$
BEGIN
    -- Verify new columns exist
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'feedme_conversations' AND column_name = 'pdf_cleaned') THEN
        RAISE EXCEPTION 'pdf_cleaned column was not created';
    END IF;
    
    -- Verify function exists
    IF NOT EXISTS (SELECT 1 FROM pg_proc WHERE proname = 'cleanup_approved_pdf') THEN
        RAISE EXCEPTION 'cleanup_approved_pdf function was not created';
    END IF;
    
    RAISE NOTICE 'FeedMe PDF cleanup migration completed successfully!';
END $$;