-- Migration 013: FeedMe Supabase Sync Metadata
-- Adds Supabase sync tracking fields for dual persistence support

-- Add Supabase sync fields to conversations
ALTER TABLE feedme_conversations 
ADD COLUMN IF NOT EXISTS supabase_sync_status TEXT DEFAULT 'pending' 
    CHECK (supabase_sync_status IN ('pending', 'synced', 'failed', 'skipped'));

ALTER TABLE feedme_conversations 
ADD COLUMN IF NOT EXISTS supabase_sync_at TIMESTAMPTZ;

ALTER TABLE feedme_conversations 
ADD COLUMN IF NOT EXISTS supabase_conversation_id UUID;

ALTER TABLE feedme_conversations 
ADD COLUMN IF NOT EXISTS supabase_sync_error TEXT;

-- Add Supabase sync fields to examples
ALTER TABLE feedme_examples 
ADD COLUMN IF NOT EXISTS supabase_sync_status TEXT DEFAULT 'pending' 
    CHECK (supabase_sync_status IN ('pending', 'synced', 'failed', 'skipped'));

ALTER TABLE feedme_examples 
ADD COLUMN IF NOT EXISTS supabase_sync_at TIMESTAMPTZ;

ALTER TABLE feedme_examples 
ADD COLUMN IF NOT EXISTS supabase_example_id UUID;

ALTER TABLE feedme_examples 
ADD COLUMN IF NOT EXISTS supabase_sync_error TEXT;

-- Create indexes for efficient sync queries
CREATE INDEX IF NOT EXISTS idx_feedme_conversations_supabase_sync 
    ON feedme_conversations (supabase_sync_status) 
    WHERE supabase_sync_status IN ('pending', 'failed');

CREATE INDEX IF NOT EXISTS idx_feedme_conversations_supabase_id 
    ON feedme_conversations (supabase_conversation_id) 
    WHERE supabase_conversation_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_feedme_examples_supabase_sync 
    ON feedme_examples (supabase_sync_status) 
    WHERE supabase_sync_status IN ('pending', 'failed');

CREATE INDEX IF NOT EXISTS idx_feedme_examples_supabase_id 
    ON feedme_examples (supabase_example_id) 
    WHERE supabase_example_id IS NOT NULL;

-- Create view for sync monitoring
CREATE OR REPLACE VIEW feedme_supabase_sync_status AS
SELECT 
    'conversations' as entity_type,
    supabase_sync_status,
    COUNT(*) as count,
    MAX(supabase_sync_at) as last_sync_at
FROM feedme_conversations
GROUP BY supabase_sync_status
UNION ALL
SELECT 
    'examples' as entity_type,
    supabase_sync_status,
    COUNT(*) as count,
    MAX(supabase_sync_at) as last_sync_at
FROM feedme_examples
GROUP BY supabase_sync_status
ORDER BY entity_type, supabase_sync_status;