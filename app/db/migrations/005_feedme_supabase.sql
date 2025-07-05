-- Migration: FeedMe Supabase Integration
-- This migration creates Supabase-specific tables for folder management,
-- conversation persistence, and approved Q&A examples with vector search

-- Enable required extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "vector";

-- =====================================================
-- SECTION 1: FOLDER MANAGEMENT
-- =====================================================

-- Create folders table for hierarchical organization
CREATE TABLE IF NOT EXISTS feedme_folders (
    id BIGSERIAL PRIMARY KEY,
    parent_id BIGINT REFERENCES feedme_folders(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    path TEXT[] NOT NULL DEFAULT '{}', -- Array path for efficient queries
    color VARCHAR(7) DEFAULT '#0095ff',
    description TEXT,
    created_by TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    
    -- Constraints
    CONSTRAINT valid_color CHECK (color ~ '^#[0-9A-Fa-f]{6}$'),
    CONSTRAINT unique_folder_name_per_parent UNIQUE (parent_id, name)
);

-- Create efficient indexes for folder operations
CREATE INDEX idx_feedme_folders_parent ON feedme_folders(parent_id);
CREATE INDEX idx_feedme_folders_path ON feedme_folders USING GIN(path);
CREATE INDEX idx_feedme_folders_created_by ON feedme_folders(created_by);

-- =====================================================
-- SECTION 2: ENHANCED CONVERSATIONS TABLE
-- =====================================================

-- Update conversations table to include folder relationship
ALTER TABLE feedme_conversations 
ADD COLUMN IF NOT EXISTS folder_id BIGINT REFERENCES feedme_folders(id) ON DELETE SET NULL;

CREATE INDEX IF NOT EXISTS idx_feedme_conversations_folder 
ON feedme_conversations(folder_id);

-- =====================================================
-- SECTION 3: APPROVED EXAMPLES TRACKING
-- =====================================================

-- Add approval tracking to examples table
ALTER TABLE feedme_examples
ADD COLUMN IF NOT EXISTS approved_at TIMESTAMPTZ,
ADD COLUMN IF NOT EXISTS approved_by TEXT,
ADD COLUMN IF NOT EXISTS supabase_synced BOOLEAN DEFAULT FALSE,
ADD COLUMN IF NOT EXISTS supabase_sync_at TIMESTAMPTZ;

CREATE INDEX IF NOT EXISTS idx_feedme_examples_approved 
ON feedme_examples(approved_at) WHERE approved_at IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_feedme_examples_supabase_sync 
ON feedme_examples(supabase_synced) WHERE supabase_synced = FALSE;

-- =====================================================
-- SECTION 4: FOLDER STATISTICS VIEW
-- =====================================================

-- Create a view for folder conversation counts
CREATE OR REPLACE VIEW feedme_folder_stats AS
SELECT 
    f.id as folder_id,
    f.name as folder_name,
    f.path as folder_path,
    COUNT(DISTINCT c.id) as conversation_count,
    COUNT(DISTINCT e.id) as example_count,
    COUNT(DISTINCT e.id) FILTER (WHERE e.approved_at IS NOT NULL) as approved_example_count,
    MAX(c.created_at) as last_conversation_added,
    MAX(e.approved_at) as last_example_approved
FROM feedme_folders f
LEFT JOIN feedme_conversations c ON c.folder_id = f.id
LEFT JOIN feedme_examples e ON e.conversation_id = c.id
GROUP BY f.id, f.name, f.path;

-- =====================================================
-- SECTION 5: HELPER FUNCTIONS
-- =====================================================

-- Function to update folder paths when parent changes
CREATE OR REPLACE FUNCTION update_folder_path() RETURNS TRIGGER AS $$
DECLARE
    parent_path TEXT[];
BEGIN
    IF NEW.parent_id IS NULL THEN
        NEW.path = ARRAY[NEW.name];
    ELSE
        SELECT path INTO parent_path FROM feedme_folders WHERE id = NEW.parent_id;
        NEW.path = parent_path || NEW.name;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Trigger to maintain folder paths
CREATE TRIGGER trigger_update_folder_path
BEFORE INSERT OR UPDATE OF parent_id, name ON feedme_folders
FOR EACH ROW EXECUTE FUNCTION update_folder_path();

-- Function to recursively update child folder paths
CREATE OR REPLACE FUNCTION update_child_folder_paths(folder_id BIGINT) RETURNS VOID AS $$
DECLARE
    child_record RECORD;
BEGIN
    FOR child_record IN 
        SELECT id FROM feedme_folders WHERE parent_id = folder_id
    LOOP
        -- Update will trigger the path update
        UPDATE feedme_folders SET updated_at = NOW() WHERE id = child_record.id;
        -- Recursively update children
        PERFORM update_child_folder_paths(child_record.id);
    END LOOP;
END;
$$ LANGUAGE plpgsql;

-- Function to mark examples as needing Supabase sync
CREATE OR REPLACE FUNCTION mark_examples_for_sync(conversation_id BIGINT) RETURNS VOID AS $$
BEGIN
    UPDATE feedme_examples 
    SET supabase_synced = FALSE, updated_at = NOW()
    WHERE conversation_id = conversation_id 
    AND approved_at IS NOT NULL;
END;
$$ LANGUAGE plpgsql;

-- =====================================================
-- SECTION 6: ROW LEVEL SECURITY (RLS) PREPARATION
-- =====================================================

-- Note: These policies would be enabled in Supabase dashboard
-- Example policies for reference:

-- Enable RLS on tables (to be done in Supabase dashboard)
-- ALTER TABLE feedme_folders ENABLE ROW LEVEL SECURITY;
-- ALTER TABLE feedme_conversations ENABLE ROW LEVEL SECURITY;
-- ALTER TABLE feedme_examples ENABLE ROW LEVEL SECURITY;

-- Example policies (to be created in Supabase dashboard):
-- CREATE POLICY "Users can view all folders" ON feedme_folders FOR SELECT USING (true);
-- CREATE POLICY "Users can create folders" ON feedme_folders FOR INSERT WITH CHECK (auth.uid() IS NOT NULL);
-- CREATE POLICY "Users can update their own folders" ON feedme_folders FOR UPDATE USING (created_by = auth.email());
-- CREATE POLICY "Users can delete their own folders" ON feedme_folders FOR DELETE USING (created_by = auth.email());

-- =====================================================
-- SECTION 7: INITIAL DATA
-- =====================================================

-- Create default root folders if they don't exist
INSERT INTO feedme_folders (name, color, description, created_by) 
VALUES 
    ('General', '#0095ff', 'General customer inquiries', 'system'),
    ('Bugs', '#ef4444', 'Bug reports and issues', 'system'),
    ('Features', '#10b981', 'Feature requests and suggestions', 'system'),
    ('Account', '#f59e0b', 'Account and billing issues', 'system')
ON CONFLICT (parent_id, name) DO NOTHING;

-- =====================================================
-- SECTION 8: MIGRATION VALIDATION
-- =====================================================

DO $$
BEGIN
    -- Verify folders table exists
    IF NOT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'feedme_folders') THEN
        RAISE EXCEPTION 'feedme_folders table was not created';
    END IF;
    
    -- Verify folder_id column exists on conversations
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'feedme_conversations' AND column_name = 'folder_id'
    ) THEN
        RAISE EXCEPTION 'folder_id column was not added to feedme_conversations';
    END IF;
    
    -- Verify approval columns exist on examples
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'feedme_examples' AND column_name = 'approved_at'
    ) THEN
        RAISE EXCEPTION 'approval columns were not added to feedme_examples';
    END IF;
    
    RAISE NOTICE 'FeedMe Supabase migration completed successfully!';
END $$;