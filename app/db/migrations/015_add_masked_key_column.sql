-- Migration: 015_add_masked_key_column.sql
-- Purpose: Add masked_key column to improve performance and security

-- Add masked_key column to user_api_keys table
ALTER TABLE user_api_keys ADD COLUMN IF NOT EXISTS masked_key VARCHAR(50);

-- Create index for potential searching by masked key
CREATE INDEX IF NOT EXISTS idx_user_api_keys_masked ON user_api_keys(masked_key);

-- Add comment for documentation
COMMENT ON COLUMN user_api_keys.masked_key IS 'Pre-computed masked version of API key for display purposes';

-- Update RLS policies to include the new column in SELECT operations
-- (The existing policies will automatically cover this column)

-- Note: The application code will populate this column when creating/updating keys
-- This avoids the need to decrypt keys just for display purposes