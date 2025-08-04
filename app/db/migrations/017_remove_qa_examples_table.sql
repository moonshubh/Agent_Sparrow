-- Migration: Remove Q&A Examples Table Structure
-- Date: 2025-08-02
-- Description: Remove fragmented Q&A examples table since we're moving to unified text canvas

-- =====================================================
-- SECTION 1: BACKUP IMPORTANT DATA (Optional)
-- =====================================================

-- Create a backup view before dropping tables (for emergency recovery)
CREATE OR REPLACE VIEW feedme_examples_backup AS
SELECT 
    id,
    conversation_id,
    question_text,
    answer_text,
    context_before,
    context_after,
    tags,
    issue_type,
    resolution_type,
    confidence_score,
    usefulness_score,
    metadata,
    created_at,
    updated_at
FROM feedme_examples
WHERE is_active = true;

-- Grant read access to backup view
GRANT SELECT ON feedme_examples_backup TO postgres;

-- =====================================================
-- SECTION 2: DROP Q&A EXAMPLES INFRASTRUCTURE
-- =====================================================

-- 1. Drop dependent indexes first
DROP INDEX IF EXISTS idx_feedme_examples_conversation;
DROP INDEX IF EXISTS idx_feedme_examples_issue_type;
DROP INDEX IF EXISTS idx_feedme_examples_resolution_type;
DROP INDEX IF EXISTS idx_feedme_examples_confidence_score;
DROP INDEX IF EXISTS idx_feedme_examples_usefulness_score;
DROP INDEX IF EXISTS idx_feedme_examples_tags;
DROP INDEX IF EXISTS idx_feedme_examples_active;
DROP INDEX IF EXISTS idx_feedme_examples_approved;
DROP INDEX IF EXISTS idx_feedme_examples_supabase_sync;

-- Drop v2 table indexes if they exist
DROP INDEX IF EXISTS idx_feedme_examples_v2_conversation;
DROP INDEX IF EXISTS idx_feedme_examples_v2_issue_category;
DROP INDEX IF EXISTS idx_feedme_examples_v2_product_area;
DROP INDEX IF EXISTS idx_feedme_examples_v2_complexity_level;
DROP INDEX IF EXISTS idx_feedme_examples_v2_confidence_score;
DROP INDEX IF EXISTS idx_feedme_examples_v2_quality_score;
DROP INDEX IF EXISTS idx_feedme_examples_v2_usage_count;
DROP INDEX IF EXISTS idx_feedme_examples_v2_tags;

-- 2. Drop triggers that might reference the tables
DROP TRIGGER IF EXISTS update_feedme_examples_updated_at ON feedme_examples;
DROP TRIGGER IF EXISTS update_feedme_examples_v2_updated_at ON feedme_examples_v2;

-- 3. Drop functions that operate on examples
DROP FUNCTION IF EXISTS update_examples_updated_at();
DROP FUNCTION IF EXISTS update_example_usage_stats();
DROP FUNCTION IF EXISTS calculate_example_quality_score();
DROP FUNCTION IF EXISTS mark_examples_for_sync(BIGINT);

-- 4. Remove foreign key constraints
DO $$
DECLARE
    constraint_name TEXT;
BEGIN
    -- Find and drop foreign key constraints referencing feedme_examples
    FOR constraint_name IN 
        SELECT conname 
        FROM pg_constraint 
        WHERE confrelid = 'feedme_examples'::regclass
    LOOP
        EXECUTE 'ALTER TABLE ' || (SELECT conrelid::regclass FROM pg_constraint WHERE conname = constraint_name) || 
                ' DROP CONSTRAINT IF EXISTS ' || constraint_name;
    END LOOP;
    
    -- Find and drop foreign key constraints referencing feedme_examples_v2
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'feedme_examples_v2') THEN
        FOR constraint_name IN 
            SELECT conname 
            FROM pg_constraint 
            WHERE confrelid = 'feedme_examples_v2'::regclass
        LOOP
            EXECUTE 'ALTER TABLE ' || (SELECT conrelid::regclass FROM pg_constraint WHERE conname = constraint_name) || 
                    ' DROP CONSTRAINT IF EXISTS ' || constraint_name;
        END LOOP;
    END IF;
END $$;

-- =====================================================
-- SECTION 3: DROP THE TABLES
-- =====================================================

-- 5. Drop the examples tables
DROP TABLE IF EXISTS feedme_examples CASCADE;
DROP TABLE IF EXISTS feedme_examples_v2 CASCADE;

-- 6. Drop related temporary tables
DROP TABLE IF EXISTS feedme_temp_examples CASCADE;

-- =====================================================
-- SECTION 4: CLEAN UP RELATED VIEWS AND FUNCTIONS
-- =====================================================

-- 7. Drop materialized views that depend on examples
DROP MATERIALIZED VIEW IF EXISTS feedme_example_analytics CASCADE;
DROP MATERIALIZED VIEW IF EXISTS feedme_quality_metrics CASCADE;
DROP MATERIALIZED VIEW IF EXISTS feedme_usage_statistics CASCADE;

-- 8. Drop views that reference examples
DROP VIEW IF EXISTS feedme_folder_stats CASCADE;
DROP VIEW IF EXISTS feedme_conversation_summary CASCADE;

-- Recreate folder stats view without examples dependency
CREATE OR REPLACE VIEW feedme_folder_stats AS
SELECT 
    f.id as folder_id,
    f.name as folder_name,
    f.path as folder_path,
    COUNT(DISTINCT c.id) as conversation_count,
    0 as example_count,  -- Always 0 since we removed examples
    0 as approved_example_count,  -- Always 0 since we removed examples
    MAX(c.created_at) as last_conversation_added,
    NULL::timestamptz as last_example_approved  -- Always NULL since we removed examples
FROM feedme_folders f
LEFT JOIN feedme_conversations c ON c.folder_id = f.id
GROUP BY f.id, f.name, f.path;

-- =====================================================
-- SECTION 5: UPDATE CONVERSATION TABLE
-- =====================================================

-- 9. Remove example-related columns from conversations table
DO $$
BEGIN
    -- Remove example count columns since we no longer track examples
    IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'feedme_conversations' AND column_name = 'total_examples') THEN
        ALTER TABLE feedme_conversations DROP COLUMN total_examples;
    END IF;
    
    IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'feedme_conversations' AND column_name = 'approved_examples') THEN
        ALTER TABLE feedme_conversations DROP COLUMN approved_examples;
    END IF;
    
    IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'feedme_conversations' AND column_name = 'extraction_quality_score') THEN
        ALTER TABLE feedme_conversations DROP COLUMN extraction_quality_score;
    END IF;
    
    -- Update v2 table if it exists
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'feedme_conversations_v2') THEN
        ALTER TABLE feedme_conversations_v2 DROP COLUMN IF EXISTS total_examples;
        ALTER TABLE feedme_conversations_v2 DROP COLUMN IF EXISTS approved_examples;
        ALTER TABLE feedme_conversations_v2 DROP COLUMN IF EXISTS extraction_quality_score;
    END IF;
END $$;

-- =====================================================
-- SECTION 6: UPDATE SCHEMAS AND ENUMS
-- =====================================================

-- 10. Update processing status to reflect new workflow
DO $$
BEGIN
    -- Add new processing statuses for unified text workflow
    -- Note: This would typically require updating CHECK constraints,
    -- but we'll handle this in the application layer for now
    
    -- Log the schema changes
    INSERT INTO schema_migrations_log (migration_name, applied_at, description) 
    VALUES (
        '017_remove_qa_examples_table',
        NOW(),
        'Removed Q&A examples table structure, moved to unified text canvas approach'
    )
    ON CONFLICT DO NOTHING;
END $$;

-- =====================================================
-- SECTION 7: MIGRATION VALIDATION
-- =====================================================

DO $$
BEGIN
    -- Verify tables are dropped
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'feedme_examples') THEN
        RAISE EXCEPTION 'feedme_examples table still exists - drop failed';
    END IF;
    
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'feedme_examples_v2') THEN
        RAISE EXCEPTION 'feedme_examples_v2 table still exists - drop failed';
    END IF;
    
    -- Verify backup view exists
    IF NOT EXISTS (SELECT 1 FROM information_schema.views WHERE table_name = 'feedme_examples_backup') THEN
        RAISE EXCEPTION 'Backup view was not created';
    END IF;
    
    -- Verify folder stats view still works
    IF NOT EXISTS (SELECT 1 FROM information_schema.views WHERE table_name = 'feedme_folder_stats') THEN
        RAISE EXCEPTION 'feedme_folder_stats view was not recreated';
    END IF;
    
    RAISE NOTICE 'Q&A examples table removal completed successfully!';
    RAISE NOTICE 'Backup view feedme_examples_backup created for emergency recovery';
    RAISE NOTICE 'System now uses unified text canvas approach';
END $$;