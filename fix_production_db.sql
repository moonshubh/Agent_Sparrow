-- Fix production database issues
-- Run this in Supabase SQL Editor

-- 1. Add the missing masked_key column
ALTER TABLE user_api_keys ADD COLUMN IF NOT EXISTS masked_key VARCHAR(50);

-- 2. Create index for masked_key
CREATE INDEX IF NOT EXISTS idx_user_api_keys_masked ON user_api_keys(masked_key);

-- 3. Add comment for documentation
COMMENT ON COLUMN user_api_keys.masked_key IS 'Pre-computed masked version of API key for display purposes';

-- 4. Update the user_uuid column to use UUID type instead of VARCHAR
-- First, we need to update the existing data
-- Since we're in production and SKIP_AUTH was true, there might be invalid UUIDs
-- Let's check what data exists first
SELECT user_uuid, COUNT(*) FROM user_api_keys GROUP BY user_uuid;

-- If there are any non-UUID values, we'll need to delete them or update them
-- For now, let's just ensure the column can accept UUIDs properly

-- 5. Create a migration to fix the user_uuid column type (only if needed)
-- This is commented out for safety - run only if needed after checking data
-- ALTER TABLE user_api_keys ALTER COLUMN user_uuid TYPE UUID USING user_uuid::UUID;