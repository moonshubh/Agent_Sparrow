-- Migration: Fix LangGraph Checkpointer Issues
-- Description: Fixes double counting, search_path security, unique constraints, and NULL session_id issues
-- Author: MB-Sparrow Development Team
-- Date: 2025-01-08

-- ============================================================================
-- FIX 1: Remove double checkpoint counting by modifying the trigger
-- ============================================================================

-- Drop the existing trigger that causes double counting
DROP TRIGGER IF EXISTS trigger_update_thread_checkpoint_stats ON langgraph_checkpoints;

-- Recreate the trigger function to NOT increment checkpoint_count
-- (since save_checkpoint already does this)
CREATE OR REPLACE FUNCTION update_thread_checkpoint_stats()
RETURNS TRIGGER AS $$
BEGIN
    -- Only update last checkpoint info, NOT the count
    UPDATE langgraph_threads
    SET last_checkpoint_id = NEW.id,
        last_checkpoint_at = NEW.created_at,
        last_activity_at = NOW()
    WHERE id = NEW.thread_id;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Recreate the trigger
CREATE TRIGGER trigger_update_thread_checkpoint_stats
    AFTER INSERT ON langgraph_checkpoints
    FOR EACH ROW
    EXECUTE FUNCTION update_thread_checkpoint_stats();

-- ============================================================================
-- FIX 2: Add search_path to SECURITY DEFINER functions
-- ============================================================================

-- Update get_or_create_thread function with secure search_path
CREATE OR REPLACE FUNCTION get_or_create_thread(
    p_user_id UUID,
    p_session_id INTEGER DEFAULT NULL,
    p_title TEXT DEFAULT 'New Conversation'
)
RETURNS UUID AS $$
DECLARE
    v_thread_id UUID;
    v_auth_user_id UUID;
BEGIN
    -- Set secure search path
    SET search_path = public, pg_temp;
    
    -- Verify the user is authenticated and matches the requested user_id
    v_auth_user_id := auth.uid();
    IF v_auth_user_id IS NULL OR v_auth_user_id != p_user_id THEN
        RAISE EXCEPTION 'Unauthorized: User mismatch or not authenticated';
    END IF;
    
    -- Sanitize title to prevent injection
    p_title := REPLACE(p_title, E'\n', ' ');
    p_title := REPLACE(p_title, E'\r', ' ');
    p_title := LEFT(p_title, 255); -- Limit length
    
    -- Try to get existing thread with row-level locking to prevent race conditions
    SELECT id INTO v_thread_id
    FROM langgraph_threads
    WHERE user_id = p_user_id 
        AND (session_id = p_session_id OR (p_session_id IS NULL AND session_id IS NULL))
        AND status = 'active'
    FOR UPDATE SKIP LOCKED
    LIMIT 1;
    
    -- Create new thread if not exists
    IF v_thread_id IS NULL THEN
        INSERT INTO langgraph_threads (user_id, session_id, title)
        VALUES (p_user_id, p_session_id, p_title)
        ON CONFLICT (user_id, session_id) DO UPDATE
        SET last_activity_at = NOW()
        RETURNING id INTO v_thread_id;
    END IF;
    
    -- Update last activity
    UPDATE langgraph_threads 
    SET last_activity_at = NOW()
    WHERE id = v_thread_id AND user_id = p_user_id; -- Double-check ownership
    
    RETURN v_thread_id;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- Update save_checkpoint function with secure search_path
CREATE OR REPLACE FUNCTION save_checkpoint(
    p_thread_id UUID,
    p_state JSONB,
    p_channel VARCHAR DEFAULT 'main',
    p_metadata JSONB DEFAULT '{}'
)
RETURNS UUID AS $$
DECLARE
    v_checkpoint_id UUID;
    v_parent_id UUID;
    v_version INTEGER;
    v_checkpoint_type VARCHAR;
    v_state_size INTEGER;
    v_thread_owner UUID;
    v_auth_user_id UUID;
BEGIN
    -- Set secure search path
    SET search_path = public, pg_temp;
    
    -- Verify the user owns the thread
    v_auth_user_id := auth.uid();
    SELECT user_id INTO v_thread_owner
    FROM langgraph_threads
    WHERE id = p_thread_id;
    
    IF v_thread_owner IS NULL THEN
        RAISE EXCEPTION 'Thread not found';
    END IF;
    
    IF v_auth_user_id IS NULL OR v_auth_user_id != v_thread_owner THEN
        RAISE EXCEPTION 'Unauthorized: User does not own this thread';
    END IF;
    
    -- Validate channel parameter
    IF p_channel !~ '^[a-zA-Z0-9_-]+$' THEN
        RAISE EXCEPTION 'Invalid channel name';
    END IF;
    
    -- Get parent checkpoint and version with lock
    SELECT id, version 
    INTO v_parent_id, v_version
    FROM langgraph_checkpoints
    WHERE thread_id = p_thread_id 
        AND channel = p_channel
        AND is_latest = true
    FOR UPDATE
    LIMIT 1;
    
    -- Calculate new version
    v_version := COALESCE(v_version, 0) + 1;
    
    -- Determine checkpoint type (full every 10 versions or if state > 100KB)
    v_state_size := pg_column_size(p_state);
    IF v_version % 10 = 0 OR v_state_size > 102400 OR v_version = 1 THEN
        v_checkpoint_type := 'full';
    ELSE
        v_checkpoint_type := 'delta';
    END IF;
    
    -- Mark previous checkpoint as not latest
    UPDATE langgraph_checkpoints 
    SET is_latest = false
    WHERE thread_id = p_thread_id 
        AND channel = p_channel
        AND is_latest = true;
    
    -- Insert new checkpoint
    INSERT INTO langgraph_checkpoints (
        thread_id, parent_checkpoint_id, version, channel,
        checkpoint_type, state, metadata, is_latest
    ) VALUES (
        p_thread_id, v_parent_id, v_version, p_channel,
        v_checkpoint_type, p_state, p_metadata, true
    ) RETURNING id INTO v_checkpoint_id;
    
    -- Update thread stats (checkpoint_count is incremented here ONLY)
    UPDATE langgraph_threads
    SET checkpoint_count = checkpoint_count + 1,
        last_checkpoint_id = v_checkpoint_id,
        last_checkpoint_at = NOW(),
        last_activity_at = NOW()
    WHERE id = p_thread_id AND user_id = v_auth_user_id; -- Double-check ownership
    
    RETURN v_checkpoint_id;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- Update fork_thread function with secure search_path
CREATE OR REPLACE FUNCTION fork_thread(
    p_source_thread_id UUID,
    p_checkpoint_id UUID,
    p_new_title TEXT DEFAULT NULL
)
RETURNS UUID AS $$
DECLARE
    v_new_thread_id UUID;
    v_user_id UUID;
    v_auth_user_id UUID;
    v_checkpoint_data RECORD;
BEGIN
    -- Set secure search path
    SET search_path = public, pg_temp;
    
    -- Verify the user is authenticated
    v_auth_user_id := auth.uid();
    IF v_auth_user_id IS NULL THEN
        RAISE EXCEPTION 'Unauthorized: User not authenticated';
    END IF;
    
    -- Get source thread user and verify ownership
    SELECT user_id INTO v_user_id
    FROM langgraph_threads
    WHERE id = p_source_thread_id;
    
    IF v_user_id IS NULL THEN
        RAISE EXCEPTION 'Source thread not found';
    END IF;
    
    IF v_auth_user_id != v_user_id THEN
        RAISE EXCEPTION 'Unauthorized: User does not own source thread';
    END IF;
    
    -- Get checkpoint data with verification
    SELECT * INTO v_checkpoint_data
    FROM langgraph_checkpoints
    WHERE id = p_checkpoint_id AND thread_id = p_source_thread_id;
    
    IF v_checkpoint_data IS NULL THEN
        RAISE EXCEPTION 'Checkpoint not found or does not belong to source thread';
    END IF;
    
    -- Sanitize title
    IF p_new_title IS NOT NULL THEN
        p_new_title := REPLACE(p_new_title, E'\n', ' ');
        p_new_title := REPLACE(p_new_title, E'\r', ' ');
        p_new_title := LEFT(p_new_title, 255);
    END IF;
    
    -- Create new thread
    INSERT INTO langgraph_threads (
        user_id, parent_thread_id, title, metadata
    ) VALUES (
        v_user_id, 
        p_source_thread_id,
        COALESCE(p_new_title, 'Fork: ' || (SELECT LEFT(title, 200) FROM langgraph_threads WHERE id = p_source_thread_id)),
        jsonb_build_object('forked_from_checkpoint', p_checkpoint_id)
    ) RETURNING id INTO v_new_thread_id;
    
    -- Copy checkpoint to new thread
    INSERT INTO langgraph_checkpoints (
        thread_id, version, channel, checkpoint_type,
        state, metadata, is_latest
    ) VALUES (
        v_new_thread_id, 1, v_checkpoint_data.channel, 'full',
        v_checkpoint_data.state, 
        v_checkpoint_data.metadata || jsonb_build_object('forked_from', p_checkpoint_id),
        true
    );
    
    RETURN v_new_thread_id;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- ============================================================================
-- FIX 3: Add unique index for latest checkpoint per thread/channel
-- ============================================================================

-- Create unique index to ensure only one latest checkpoint per thread/channel
CREATE UNIQUE INDEX CONCURRENTLY IF NOT EXISTS uniq_latest_checkpoint 
ON langgraph_checkpoints(thread_id, channel) 
WHERE is_latest = true;

-- ============================================================================
-- FIX 4: Fix NULL session_id uniqueness issue
-- ============================================================================

-- Drop the existing problematic unique constraint
ALTER TABLE langgraph_threads DROP CONSTRAINT IF EXISTS unique_user_session;

-- Create a partial unique index for non-NULL session_id values
CREATE UNIQUE INDEX CONCURRENTLY IF NOT EXISTS uniq_user_session_not_null 
ON langgraph_threads(user_id, session_id) 
WHERE session_id IS NOT NULL;

-- Create a partial unique index for NULL session_id values
-- This ensures only one active thread per user when session_id is NULL
CREATE UNIQUE INDEX CONCURRENTLY IF NOT EXISTS uniq_user_null_session_active 
ON langgraph_threads(user_id) 
WHERE session_id IS NULL AND status = 'active';

-- ============================================================================
-- FIX 5: Add view for backward compatibility with user_id column
-- ============================================================================

-- Create a view that exposes user_id as an alias for user_uuid in user_api_keys
CREATE OR REPLACE VIEW user_api_keys_compat AS
SELECT 
    id,
    user_uuid,
    user_uuid AS user_id,  -- Alias for backward compatibility
    api_key_type,
    encrypted_key,
    masked_key,
    key_name,
    is_active,
    created_at,
    updated_at,
    last_used_at
FROM user_api_keys;

-- Grant appropriate permissions on the view
GRANT SELECT, INSERT, UPDATE, DELETE ON user_api_keys_compat TO authenticated;
GRANT SELECT ON user_api_keys_compat TO anon;

-- ============================================================================
-- VERIFICATION QUERIES (Run these to confirm fixes)
-- ============================================================================

-- Verify no duplicate latest checkpoints exist
DO $$
DECLARE
    duplicate_count INTEGER;
BEGIN
    SELECT COUNT(*) INTO duplicate_count
    FROM (
        SELECT thread_id, channel, COUNT(*) as cnt
        FROM langgraph_checkpoints
        WHERE is_latest = true
        GROUP BY thread_id, channel
        HAVING COUNT(*) > 1
    ) dups;
    
    IF duplicate_count > 0 THEN
        RAISE WARNING 'Found % thread/channel combinations with multiple latest checkpoints', duplicate_count;
    ELSE
        RAISE NOTICE 'No duplicate latest checkpoints found - constraint is working correctly';
    END IF;
END $$;

-- Verify checkpoint counts are accurate
DO $$
DECLARE
    mismatched_count INTEGER;
BEGIN
    SELECT COUNT(*) INTO mismatched_count
    FROM langgraph_threads t
    WHERE t.checkpoint_count != (
        SELECT COUNT(*) 
        FROM langgraph_checkpoints c 
        WHERE c.thread_id = t.id
    );
    
    IF mismatched_count > 0 THEN
        RAISE WARNING 'Found % threads with incorrect checkpoint counts', mismatched_count;
        -- Fix the counts
        UPDATE langgraph_threads t
        SET checkpoint_count = (
            SELECT COUNT(*) 
            FROM langgraph_checkpoints c 
            WHERE c.thread_id = t.id
        )
        WHERE t.checkpoint_count != (
            SELECT COUNT(*) 
            FROM langgraph_checkpoints c 
            WHERE c.thread_id = t.id
        );
        RAISE NOTICE 'Fixed checkpoint counts for % threads', mismatched_count;
    ELSE
        RAISE NOTICE 'All checkpoint counts are accurate';
    END IF;
END $$;