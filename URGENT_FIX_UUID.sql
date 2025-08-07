-- URGENT FIX: UUID Mismatch for API Keys
-- Run this in Supabase SQL Editor to fix the UUID issue

-- The problem: The API key was saved with wrong UUID ending
-- Wrong:   86c5eeb9-367c-4948-82ba-52132596c846
-- Correct: 86c5eeb9-367c-4948-82ba-5213259c684f

-- Step 1: Show current state
SELECT 
    id,
    user_uuid,
    user_id,
    api_key_type,
    masked_key,
    is_active,
    created_at,
    last_used_at
FROM user_api_keys
WHERE user_uuid IN (
    '86c5eeb9-367c-4948-82ba-52132596c846',  -- Wrong UUID
    '86c5eeb9-367c-4948-82ba-5213259c684f'   -- Correct UUID
);

-- Step 2: Update to correct UUID
-- Note: This will fix the UUID, but the encryption might be broken
-- because it was encrypted with the wrong UUID as the key
UPDATE user_api_keys
SET 
    user_uuid = '86c5eeb9-367c-4948-82ba-5213259c684f',
    user_id = '86c5eeb9-367c-4948-82ba-5213259c684f',
    updated_at = NOW()
WHERE user_uuid = '86c5eeb9-367c-4948-82ba-52132596c846';

-- Step 3: Verify the fix
SELECT 
    id,
    user_uuid,
    user_id,
    api_key_type,
    masked_key,
    is_active,
    last_used_at,
    updated_at
FROM user_api_keys
WHERE user_uuid = '86c5eeb9-367c-4948-82ba-5213259c684f';

-- Expected result: 
-- You should see your API key with the correct UUID
-- If last_used_at starts updating, the key is working!

-- IMPORTANT NOTE:
-- After running this, if the API key doesn't work (due to encryption mismatch),
-- you'll need to re-enter your API key through the frontend Settings page.
-- The system will then encrypt it with the correct UUID.