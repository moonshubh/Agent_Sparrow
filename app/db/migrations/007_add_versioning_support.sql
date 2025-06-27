-- Migration: Add versioning support to FeedMe conversations
-- This migration adds the necessary fields for conversation versioning and editing

-- Enable required extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- 1. Add versioning fields to feedme_conversations table
ALTER TABLE feedme_conversations
ADD COLUMN IF NOT EXISTS uuid UUID DEFAULT uuid_generate_v4(),
ADD COLUMN IF NOT EXISTS version INTEGER DEFAULT 1,
ADD COLUMN IF NOT EXISTS is_active BOOLEAN DEFAULT true;

-- 2. Update existing conversations to have proper UUIDs and version numbers
-- Each existing conversation becomes version 1 of itself
UPDATE feedme_conversations 
SET uuid = uuid_generate_v4(), version = 1, is_active = true 
WHERE uuid IS NULL;

-- 3. Add constraints
ALTER TABLE feedme_conversations
ALTER COLUMN uuid SET NOT NULL,
ALTER COLUMN version SET NOT NULL,
ALTER COLUMN is_active SET NOT NULL;

-- 4. Add unique constraint for active versions (only one active version per UUID)
CREATE UNIQUE INDEX IF NOT EXISTS idx_feedme_conversations_active_version
ON feedme_conversations (uuid) WHERE is_active = true;

-- 5. Add indexes for efficient versioning queries
CREATE INDEX IF NOT EXISTS idx_feedme_conversations_uuid 
ON feedme_conversations (uuid);

CREATE INDEX IF NOT EXISTS idx_feedme_conversations_version 
ON feedme_conversations (uuid, version DESC);

CREATE INDEX IF NOT EXISTS idx_feedme_conversations_is_active 
ON feedme_conversations (is_active) WHERE is_active = true;

-- 6. Add folder support for conversation organization
ALTER TABLE feedme_conversations
ADD COLUMN IF NOT EXISTS folder_id INTEGER,
ADD COLUMN IF NOT EXISTS folder_color TEXT DEFAULT '#0095ff';

-- Create folders table for organizing conversations
CREATE TABLE IF NOT EXISTS feedme_folders (
    id SERIAL PRIMARY KEY,
    name TEXT NOT NULL,
    color TEXT NOT NULL DEFAULT '#0095ff',
    description TEXT,
    created_by TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Add folder foreign key constraint
ALTER TABLE feedme_conversations
ADD CONSTRAINT fk_feedme_conversations_folder
FOREIGN KEY (folder_id) REFERENCES feedme_folders(id) ON DELETE SET NULL;

-- Add index for folder queries
CREATE INDEX IF NOT EXISTS idx_feedme_conversations_folder
ON feedme_conversations (folder_id);

-- Add trigger for folders updated_at
CREATE TRIGGER trigger_feedme_folders_updated_at
    BEFORE UPDATE ON feedme_folders
    FOR EACH ROW
    EXECUTE FUNCTION update_feedme_updated_at();

-- 7. Insert default folders with different colors
INSERT INTO feedme_folders (name, color, description, created_by) VALUES
('Email Issues', '#e74c3c', 'Email configuration and synchronization problems', 'system'),
('Account Setup', '#3498db', 'New account setup and configuration', 'system'),
('Performance', '#f39c12', 'Performance and speed related issues', 'system'),
('Features', '#9b59b6', 'Feature requests and usage questions', 'system'),
('Bugs', '#e67e22', 'Bug reports and error investigations', 'system'),
('General', '#95a5a6', 'General support conversations', 'system')
ON CONFLICT DO NOTHING;

-- 8. Comment explaining the versioning system
COMMENT ON COLUMN feedme_conversations.uuid IS 'Groups all versions of the same conversation together';
COMMENT ON COLUMN feedme_conversations.version IS 'Version number within the conversation group (starts at 1)';
COMMENT ON COLUMN feedme_conversations.is_active IS 'Whether this is the currently active version of the conversation';
COMMENT ON COLUMN feedme_conversations.folder_id IS 'Optional folder for organizing conversations';
COMMENT ON COLUMN feedme_conversations.folder_color IS 'Color override for this specific conversation (falls back to folder color)';
COMMENT ON TABLE feedme_folders IS 'Folders for organizing FeedMe conversations with colored categories';