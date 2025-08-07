-- Fix UUID mismatch for user API keys
-- The user's actual UUID ends with: 5213259c684f
-- But the database has: 52132596c846 (wrong!)

-- First, let's verify the issue
SELECT 
    id,
    user_uuid,
    api_key_type,
    is_active,
    created_at,
    last_used_at
FROM user_api_keys
WHERE user_uuid LIKE '86c5eeb9-367c-4948-82ba-%';

-- Update the incorrect UUID to the correct one
UPDATE user_api_keys
SET 
    user_uuid = '86c5eeb9-367c-4948-82ba-5213259c684f',
    user_id = '86c5eeb9-367c-4948-82ba-5213259c684f'  -- Also update user_id column
WHERE user_uuid = '86c5eeb9-367c-4948-82ba-52132596c846';

-- Verify the update
SELECT 
    id,
    user_uuid,
    user_id,
    api_key_type,
    is_active,
    last_used_at
FROM user_api_keys
WHERE user_uuid = '86c5eeb9-367c-4948-82ba-5213259c684f';

-- Note: After running this, the API key might need to be re-encrypted
-- because the encryption uses the user_id as part of the key.
-- If decryption fails after this update, the user may need to re-enter their API key.