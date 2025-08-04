-- Migration: FeedMe System Restructure for PDF+Text Processing
-- Date: 2025-08-02
-- Description: Remove HTML parsing and search infrastructure, restructure for PDF OCR + manual text workflow

-- =====================================================
-- SECTION 1: REMOVE SEARCH INFRASTRUCTURE
-- =====================================================

-- 1. Remove vector embedding columns from examples table
DO $$
BEGIN
    -- Remove vector embedding columns if they exist
    IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'feedme_examples' AND column_name = 'question_embedding') THEN
        ALTER TABLE feedme_examples DROP COLUMN IF EXISTS question_embedding;
    END IF;
    
    IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'feedme_examples' AND column_name = 'answer_embedding') THEN
        ALTER TABLE feedme_examples DROP COLUMN IF EXISTS answer_embedding;
    END IF;
    
    IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'feedme_examples' AND column_name = 'combined_embedding') THEN
        ALTER TABLE feedme_examples DROP COLUMN IF EXISTS combined_embedding;
    END IF;

    -- Remove search optimization column
    IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'feedme_examples' AND column_name = 'search_text') THEN
        ALTER TABLE feedme_examples DROP COLUMN IF EXISTS search_text;
    END IF;
    
    -- Also remove from v2 table if it exists
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'feedme_examples_v2') THEN
        ALTER TABLE feedme_examples_v2 DROP COLUMN IF EXISTS question_embedding;
        ALTER TABLE feedme_examples_v2 DROP COLUMN IF EXISTS answer_embedding;
        ALTER TABLE feedme_examples_v2 DROP COLUMN IF EXISTS combined_embedding;
        ALTER TABLE feedme_examples_v2 DROP COLUMN IF EXISTS search_text;
    END IF;
END $$;

-- 2. Remove vector indexes if they exist
DROP INDEX IF EXISTS idx_feedme_examples_question_embedding;
DROP INDEX IF EXISTS idx_feedme_examples_answer_embedding;
DROP INDEX IF EXISTS idx_feedme_examples_combined_embedding;
DROP INDEX IF EXISTS idx_feedme_examples_search_text;
DROP INDEX IF EXISTS idx_feedme_examples_v2_question_embedding;
DROP INDEX IF EXISTS idx_feedme_examples_v2_answer_embedding;
DROP INDEX IF EXISTS idx_feedme_examples_v2_combined_embedding;
DROP INDEX IF EXISTS idx_feedme_examples_v2_search_text;

-- =====================================================
-- SECTION 2: RESTRUCTURE FOR UNIFIED TEXT WORKFLOW
-- =====================================================

-- 3. Add new columns for PDF+text workflow to conversations table
DO $$
BEGIN
    -- Add extracted_text column for unified text storage
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'feedme_conversations' AND column_name = 'extracted_text') THEN
        ALTER TABLE feedme_conversations ADD COLUMN extracted_text TEXT;
    END IF;
    
    -- Add extraction confidence score
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'feedme_conversations' AND column_name = 'extraction_confidence') THEN
        ALTER TABLE feedme_conversations ADD COLUMN extraction_confidence FLOAT CHECK (extraction_confidence >= 0 AND extraction_confidence <= 1);
    END IF;
    
    -- Add human approval tracking
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'feedme_conversations' AND column_name = 'approved_by') THEN
        ALTER TABLE feedme_conversations ADD COLUMN approved_by TEXT;
    END IF;
    
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'feedme_conversations' AND column_name = 'approved_at') THEN
        ALTER TABLE feedme_conversations ADD COLUMN approved_at TIMESTAMPTZ;
    END IF;
    
    -- Add processing method tracking
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'feedme_conversations' AND column_name = 'processing_method') THEN
        ALTER TABLE feedme_conversations ADD COLUMN processing_method VARCHAR(20) DEFAULT 'pdf_ocr' 
            CHECK (processing_method IN ('pdf_ocr', 'manual_text', 'text_paste'));
    END IF;
    
    -- Mark HTML-related fields as deprecated (keep for data migration)
    -- Don't drop raw_transcript yet - may contain data we need to migrate
END $$;

-- 4. Update conversations v2 table if it exists
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'feedme_conversations_v2') THEN
        -- Add new columns to v2 table
        ALTER TABLE feedme_conversations_v2 ADD COLUMN IF NOT EXISTS extracted_text TEXT;
        ALTER TABLE feedme_conversations_v2 ADD COLUMN IF NOT EXISTS extraction_confidence FLOAT CHECK (extraction_confidence >= 0 AND extraction_confidence <= 1);
        ALTER TABLE feedme_conversations_v2 ADD COLUMN IF NOT EXISTS approved_by TEXT;
        ALTER TABLE feedme_conversations_v2 ADD COLUMN IF NOT EXISTS approved_at TIMESTAMPTZ;
        ALTER TABLE feedme_conversations_v2 ADD COLUMN IF NOT EXISTS processing_method VARCHAR(20) DEFAULT 'pdf_ocr' 
            CHECK (processing_method IN ('pdf_ocr', 'manual_text', 'text_paste'));
    END IF;
END $$;

-- =====================================================
-- SECTION 3: UPDATE INDEXES FOR NEW WORKFLOW
-- =====================================================

-- 5. Create indexes for new workflow
CREATE INDEX IF NOT EXISTS idx_feedme_conversations_processing_method 
    ON feedme_conversations(processing_method);

CREATE INDEX IF NOT EXISTS idx_feedme_conversations_approved 
    ON feedme_conversations(approved_at) WHERE approved_at IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_feedme_conversations_extraction_confidence 
    ON feedme_conversations(extraction_confidence) WHERE extraction_confidence IS NOT NULL;

-- If v2 table exists, add indexes there too
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'feedme_conversations_v2') THEN
        CREATE INDEX IF NOT EXISTS idx_feedme_conversations_v2_processing_method 
            ON feedme_conversations_v2(processing_method);
        CREATE INDEX IF NOT EXISTS idx_feedme_conversations_v2_approved 
            ON feedme_conversations_v2(approved_at) WHERE approved_at IS NOT NULL;
        CREATE INDEX IF NOT EXISTS idx_feedme_conversations_v2_extraction_confidence 
            ON feedme_conversations_v2(extraction_confidence) WHERE extraction_confidence IS NOT NULL;
    END IF;
END $$;

-- =====================================================
-- SECTION 4: CLEANUP DEPRECATED FUNCTIONS
-- =====================================================

-- 6. Drop search-related functions if they exist
DROP FUNCTION IF EXISTS search_feedme_examples(text, integer);
DROP FUNCTION IF EXISTS hybrid_search_feedme(text, integer, float);
DROP FUNCTION IF EXISTS get_similar_examples(vector, integer);

-- =====================================================
-- SECTION 5: UPDATE COMMENTS AND DOCUMENTATION
-- =====================================================

-- 7. Update table comments to reflect new purpose
COMMENT ON COLUMN feedme_conversations.extracted_text IS 'Unified text content extracted from PDF or manually entered';
COMMENT ON COLUMN feedme_conversations.extraction_confidence IS 'OCR confidence score (0-1) for PDF extractions';
COMMENT ON COLUMN feedme_conversations.approved_by IS 'User who approved the extracted text for storage';
COMMENT ON COLUMN feedme_conversations.approved_at IS 'Timestamp when text was approved for permanent storage';
COMMENT ON COLUMN feedme_conversations.processing_method IS 'Method used to process content: pdf_ocr, manual_text, or text_paste';

-- Update table comment
COMMENT ON TABLE feedme_conversations IS 'Customer support conversations processed via PDF OCR or manual text entry (HTML parsing removed)';

-- =====================================================
-- SECTION 6: MIGRATION VALIDATION
-- =====================================================

DO $$
BEGIN
    -- Verify new columns exist
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'feedme_conversations' AND column_name = 'extracted_text') THEN
        RAISE EXCEPTION 'extracted_text column was not created';
    END IF;
    
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'feedme_conversations' AND column_name = 'processing_method') THEN
        RAISE EXCEPTION 'processing_method column was not created';
    END IF;
    
    -- Verify vector columns are removed
    IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'feedme_examples' AND column_name = 'question_embedding') THEN
        RAISE EXCEPTION 'Vector embedding columns still exist - removal failed';
    END IF;
    
    RAISE NOTICE 'FeedMe PDF+Text restructure migration completed successfully!';
END $$;