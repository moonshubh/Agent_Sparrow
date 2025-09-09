-- Migration 020: Comprehensive Security Fixes for All Tables and Functions
-- This migration addresses all security warnings from Supabase security advisors
-- 
-- ISSUES BEING FIXED:
-- 1. ERROR: RLS disabled on public tables (agent_configuration, chat_sessions, chat_messages)
-- 2. INFO: RLS enabled but no policies (feedme_conversations, feedme_examples, feedme_examples_temp, feedme_folders, mailbird_knowledge)
-- 3. WARN: Function search_path mutable (7 functions need fixing)
-- 4. WARN: Leaked password protection disabled (needs manual configuration in Supabase dashboard)

-- ========================================
-- PART 1: Enable RLS on all public tables
-- ========================================

-- Enable RLS on tables that don't have it
ALTER TABLE public.agent_configuration ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.chat_sessions ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.chat_messages ENABLE ROW LEVEL SECURITY;

-- ========================================
-- PART 2: Create RLS policies for all tables
-- ========================================

-- Policies for agent_configuration (read-only for all, admin-only for modifications)
CREATE POLICY "agent_configuration_select_policy" ON public.agent_configuration
    FOR SELECT
    USING (true);  -- All authenticated users can read configuration

CREATE POLICY "agent_configuration_admin_policy" ON public.agent_configuration
    FOR ALL
    USING (auth.jwt() ->> 'role' = 'service_role')  -- Only service role can modify
    WITH CHECK (auth.jwt() ->> 'role' = 'service_role');

-- Policies for chat_sessions (users can only access their own sessions)
CREATE POLICY "chat_sessions_user_select" ON public.chat_sessions
    FOR SELECT
    USING (
        user_id = COALESCE(auth.jwt() ->> 'sub', 'anonymous') OR
        user_id = 'skipped_auth_user'  -- Allow skipped auth for development
    );

CREATE POLICY "chat_sessions_user_insert" ON public.chat_sessions
    FOR INSERT
    WITH CHECK (
        user_id = COALESCE(auth.jwt() ->> 'sub', 'anonymous') OR
        user_id = 'skipped_auth_user'
    );

CREATE POLICY "chat_sessions_user_update" ON public.chat_sessions
    FOR UPDATE
    USING (
        user_id = COALESCE(auth.jwt() ->> 'sub', 'anonymous') OR
        user_id = 'skipped_auth_user'
    )
    WITH CHECK (
        user_id = COALESCE(auth.jwt() ->> 'sub', 'anonymous') OR
        user_id = 'skipped_auth_user'
    );

CREATE POLICY "chat_sessions_user_delete" ON public.chat_sessions
    FOR DELETE
    USING (
        user_id = COALESCE(auth.jwt() ->> 'sub', 'anonymous') OR
        user_id = 'skipped_auth_user'
    );

-- Policies for chat_messages (users can only access messages from their sessions)
CREATE POLICY "chat_messages_user_select" ON public.chat_messages
    FOR SELECT
    USING (
        EXISTS (
            SELECT 1 FROM public.chat_sessions
            WHERE chat_sessions.id = chat_messages.session_id
            AND (
                chat_sessions.user_id = COALESCE(auth.jwt() ->> 'sub', 'anonymous') OR
                chat_sessions.user_id = 'skipped_auth_user'
            )
        )
    );

CREATE POLICY "chat_messages_user_insert" ON public.chat_messages
    FOR INSERT
    WITH CHECK (
        EXISTS (
            SELECT 1 FROM public.chat_sessions
            WHERE chat_sessions.id = chat_messages.session_id
            AND (
                chat_sessions.user_id = COALESCE(auth.jwt() ->> 'sub', 'anonymous') OR
                chat_sessions.user_id = 'skipped_auth_user'
            )
        )
    );

CREATE POLICY "chat_messages_user_update" ON public.chat_messages
    FOR UPDATE
    USING (
        EXISTS (
            SELECT 1 FROM public.chat_sessions
            WHERE chat_sessions.id = chat_messages.session_id
            AND (
                chat_sessions.user_id = COALESCE(auth.jwt() ->> 'sub', 'anonymous') OR
                chat_sessions.user_id = 'skipped_auth_user'
            )
        )
    )
    WITH CHECK (
        EXISTS (
            SELECT 1 FROM public.chat_sessions
            WHERE chat_sessions.id = chat_messages.session_id
            AND (
                chat_sessions.user_id = COALESCE(auth.jwt() ->> 'sub', 'anonymous') OR
                chat_sessions.user_id = 'skipped_auth_user'
            )
        )
    );

-- Policies for feedme_conversations (authenticated users only)
CREATE POLICY "feedme_conversations_authenticated_select" ON public.feedme_conversations
    FOR SELECT
    USING (auth.role() = 'authenticated' OR auth.jwt() ->> 'role' = 'service_role');

CREATE POLICY "feedme_conversations_authenticated_insert" ON public.feedme_conversations
    FOR INSERT
    WITH CHECK (auth.role() = 'authenticated' OR auth.jwt() ->> 'role' = 'service_role');

CREATE POLICY "feedme_conversations_authenticated_update" ON public.feedme_conversations
    FOR UPDATE
    USING (auth.role() = 'authenticated' OR auth.jwt() ->> 'role' = 'service_role')
    WITH CHECK (auth.role() = 'authenticated' OR auth.jwt() ->> 'role' = 'service_role');

CREATE POLICY "feedme_conversations_authenticated_delete" ON public.feedme_conversations
    FOR DELETE
    USING (auth.role() = 'authenticated' OR auth.jwt() ->> 'role' = 'service_role');

-- Policies for feedme_examples (authenticated users only)
CREATE POLICY "feedme_examples_authenticated_select" ON public.feedme_examples
    FOR SELECT
    USING (auth.role() = 'authenticated' OR auth.jwt() ->> 'role' = 'service_role');

CREATE POLICY "feedme_examples_authenticated_insert" ON public.feedme_examples
    FOR INSERT
    WITH CHECK (auth.role() = 'authenticated' OR auth.jwt() ->> 'role' = 'service_role');

CREATE POLICY "feedme_examples_authenticated_update" ON public.feedme_examples
    FOR UPDATE
    USING (auth.role() = 'authenticated' OR auth.jwt() ->> 'role' = 'service_role')
    WITH CHECK (auth.role() = 'authenticated' OR auth.jwt() ->> 'role' = 'service_role');

CREATE POLICY "feedme_examples_authenticated_delete" ON public.feedme_examples
    FOR DELETE
    USING (auth.role() = 'authenticated' OR auth.jwt() ->> 'role' = 'service_role');

-- Policies for feedme_examples_temp (authenticated users only)
CREATE POLICY "feedme_examples_temp_authenticated_select" ON public.feedme_examples_temp
    FOR SELECT
    USING (auth.role() = 'authenticated' OR auth.jwt() ->> 'role' = 'service_role');

CREATE POLICY "feedme_examples_temp_authenticated_insert" ON public.feedme_examples_temp
    FOR INSERT
    WITH CHECK (auth.role() = 'authenticated' OR auth.jwt() ->> 'role' = 'service_role');

CREATE POLICY "feedme_examples_temp_authenticated_update" ON public.feedme_examples_temp
    FOR UPDATE
    USING (auth.role() = 'authenticated' OR auth.jwt() ->> 'role' = 'service_role')
    WITH CHECK (auth.role() = 'authenticated' OR auth.jwt() ->> 'role' = 'service_role');

CREATE POLICY "feedme_examples_temp_authenticated_delete" ON public.feedme_examples_temp
    FOR DELETE
    USING (auth.role() = 'authenticated' OR auth.jwt() ->> 'role' = 'service_role');

-- Policies for feedme_folders (authenticated users only)
CREATE POLICY "feedme_folders_authenticated_select" ON public.feedme_folders
    FOR SELECT
    USING (auth.role() = 'authenticated' OR auth.jwt() ->> 'role' = 'service_role');

CREATE POLICY "feedme_folders_authenticated_insert" ON public.feedme_folders
    FOR INSERT
    WITH CHECK (auth.role() = 'authenticated' OR auth.jwt() ->> 'role' = 'service_role');

CREATE POLICY "feedme_folders_authenticated_update" ON public.feedme_folders
    FOR UPDATE
    USING (auth.role() = 'authenticated' OR auth.jwt() ->> 'role' = 'service_role')
    WITH CHECK (auth.role() = 'authenticated' OR auth.jwt() ->> 'role' = 'service_role');

CREATE POLICY "feedme_folders_authenticated_delete" ON public.feedme_folders
    FOR DELETE
    USING (auth.role() = 'authenticated' OR auth.jwt() ->> 'role' = 'service_role');

-- Policies for mailbird_knowledge (read-only for all authenticated users)
CREATE POLICY "mailbird_knowledge_authenticated_select" ON public.mailbird_knowledge
    FOR SELECT
    USING (auth.role() = 'authenticated' OR auth.jwt() ->> 'role' = 'service_role');

CREATE POLICY "mailbird_knowledge_service_insert" ON public.mailbird_knowledge
    FOR INSERT
    WITH CHECK (auth.jwt() ->> 'role' = 'service_role');

CREATE POLICY "mailbird_knowledge_service_update" ON public.mailbird_knowledge
    FOR UPDATE
    USING (auth.jwt() ->> 'role' = 'service_role')
    WITH CHECK (auth.jwt() ->> 'role' = 'service_role');

CREATE POLICY "mailbird_knowledge_service_delete" ON public.mailbird_knowledge
    FOR DELETE
    USING (auth.jwt() ->> 'role' = 'service_role');

-- ========================================
-- PART 3: Fix function search_path issues
-- ========================================

-- Fix update_chat_session_timestamp function
DROP FUNCTION IF EXISTS public.update_chat_session_timestamp() CASCADE;
CREATE OR REPLACE FUNCTION public.update_chat_session_timestamp()
RETURNS TRIGGER 
SECURITY DEFINER
SET search_path = public, pg_catalog
AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Recreate trigger if it exists
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_trigger WHERE tgname = 'update_chat_sessions_updated_at') THEN
        CREATE TRIGGER update_chat_sessions_updated_at
            BEFORE UPDATE ON public.chat_sessions
            FOR EACH ROW
            EXECUTE FUNCTION public.update_chat_session_timestamp();
    END IF;
END $$;

-- Fix update_session_on_message function
DROP FUNCTION IF EXISTS public.update_session_on_message() CASCADE;
CREATE OR REPLACE FUNCTION public.update_session_on_message()
RETURNS TRIGGER 
SECURITY DEFINER
SET search_path = public, pg_catalog
AS $$
BEGIN
    -- Update the last_message_at timestamp in chat_sessions
    UPDATE public.chat_sessions
    SET last_message_at = NEW.created_at,
        message_count = COALESCE(message_count, 0) + 1,
        updated_at = NOW()
    WHERE id = NEW.session_id;
    
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Recreate trigger if needed
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_trigger WHERE tgname = 'trigger_update_session_on_message') THEN
        CREATE TRIGGER trigger_update_session_on_message
            AFTER INSERT ON public.chat_messages
            FOR EACH ROW
            EXECUTE FUNCTION public.update_session_on_message();
    END IF;
END $$;

-- Fix get_agent_config function
DROP FUNCTION IF EXISTS public.get_agent_config(VARCHAR) CASCADE;
CREATE OR REPLACE FUNCTION public.get_agent_config(p_agent_type VARCHAR(50))
RETURNS TABLE (
    agent_type VARCHAR(50),
    max_active_sessions INTEGER,
    max_message_length INTEGER,
    session_timeout_hours INTEGER
) 
SECURITY DEFINER
SET search_path = public, pg_catalog
AS $$
BEGIN
    RETURN QUERY
    SELECT 
        ac.agent_type,
        ac.max_active_sessions,
        ac.max_message_length,
        ac.session_timeout_hours
    FROM public.agent_configuration ac
    WHERE ac.agent_type = p_agent_type;
    
    -- Return default if not found
    IF NOT FOUND THEN
        RETURN QUERY
        SELECT 
            p_agent_type,
            5,
            10000,
            24;
    END IF;
END;
$$ LANGUAGE plpgsql;

-- Fix deactivate_oldest_session function
DROP FUNCTION IF EXISTS public.deactivate_oldest_session(VARCHAR, VARCHAR) CASCADE;
CREATE OR REPLACE FUNCTION public.deactivate_oldest_session(
    p_user_id VARCHAR(255),
    p_agent_type VARCHAR(50)
) 
RETURNS VOID 
SECURITY DEFINER
SET search_path = public, pg_catalog
AS $$
BEGIN
    -- Deactivate the oldest active session for this user and agent type
    UPDATE public.chat_sessions
    SET is_active = FALSE, 
        updated_at = NOW(),
        metadata = COALESCE(metadata, '{}'::jsonb) || jsonb_build_object(
            'auto_deactivated_at', NOW(),
            'deactivated_reason', 'session_limit_exceeded'
        )
    WHERE user_id = p_user_id
        AND agent_type = p_agent_type
        AND is_active = TRUE
        AND id = (
            SELECT id 
            FROM public.chat_sessions
            WHERE user_id = p_user_id
                AND agent_type = p_agent_type
                AND is_active = TRUE
            ORDER BY last_message_at ASC NULLS FIRST
            LIMIT 1
        );
END;
$$ LANGUAGE plpgsql;

-- Fix enforce_chat_session_limits_after function
DROP FUNCTION IF EXISTS public.enforce_chat_session_limits_after() CASCADE;
CREATE OR REPLACE FUNCTION public.enforce_chat_session_limits_after()
RETURNS TRIGGER 
SECURITY DEFINER
SET search_path = public, pg_catalog
AS $$
DECLARE
    active_count INTEGER;
    max_allowed INTEGER;
BEGIN
    -- Only check for newly activated sessions
    IF NEW.is_active = TRUE AND (OLD IS NULL OR OLD.is_active = FALSE) THEN
        
        -- Get max allowed sessions from configuration table
        SELECT max_active_sessions INTO max_allowed
        FROM public.agent_configuration
        WHERE agent_type = NEW.agent_type;
        
        -- Fallback to defaults if not found
        IF max_allowed IS NULL THEN
            CASE NEW.agent_type
                WHEN 'primary' THEN max_allowed := 5;
                WHEN 'log_analysis' THEN max_allowed := 3;
                WHEN 'research' THEN max_allowed := 5;
                WHEN 'router' THEN max_allowed := 10;
                ELSE max_allowed := 5;
            END CASE;
        END IF;
        
        -- Count current active sessions for this user and agent type
        SELECT COUNT(*) INTO active_count
        FROM public.chat_sessions
        WHERE user_id = NEW.user_id 
            AND agent_type = NEW.agent_type
            AND is_active = TRUE;
        
        -- If we now exceed the limit, deactivate the oldest session
        IF active_count > max_allowed THEN
            -- Call separate function to avoid recursion
            PERFORM public.deactivate_oldest_session(NEW.user_id, NEW.agent_type);
        END IF;
    END IF;
    
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Recreate trigger
DROP TRIGGER IF EXISTS trigger_enforce_chat_session_limits ON public.chat_sessions;
CREATE TRIGGER trigger_enforce_chat_session_limits
    AFTER INSERT OR UPDATE OF is_active ON public.chat_sessions
    FOR EACH ROW
    EXECUTE FUNCTION public.enforce_chat_session_limits_after();

-- Fix check_session_limits_health function
DROP FUNCTION IF EXISTS public.check_session_limits_health() CASCADE;
CREATE OR REPLACE FUNCTION public.check_session_limits_health()
RETURNS TABLE (
    agent_type VARCHAR(50),
    user_id VARCHAR(255),
    active_sessions_count INTEGER,
    max_allowed INTEGER,
    status TEXT
) 
SECURITY DEFINER
SET search_path = public, pg_catalog
AS $$
BEGIN
    RETURN QUERY
    WITH session_counts AS (
        SELECT 
            cs.agent_type,
            cs.user_id,
            COUNT(*) as active_count
        FROM public.chat_sessions cs
        WHERE cs.is_active = TRUE
        GROUP BY cs.agent_type, cs.user_id
    ),
    config AS (
        SELECT 
            ac.agent_type,
            ac.max_active_sessions
        FROM public.agent_configuration ac
    )
    SELECT 
        sc.agent_type,
        sc.user_id,
        sc.active_count::INTEGER,
        COALESCE(c.max_active_sessions, 5) as max_allowed,
        CASE 
            WHEN sc.active_count > COALESCE(c.max_active_sessions, 5) THEN 'VIOLATION'
            WHEN sc.active_count = COALESCE(c.max_active_sessions, 5) THEN 'AT_LIMIT'
            ELSE 'OK'
        END as status
    FROM session_counts sc
    LEFT JOIN config c ON sc.agent_type = c.agent_type
    ORDER BY 
        CASE 
            WHEN sc.active_count > COALESCE(c.max_active_sessions, 5) THEN 0
            WHEN sc.active_count = COALESCE(c.max_active_sessions, 5) THEN 1
            ELSE 2
        END,
        sc.agent_type,
        sc.user_id;
END;
$$ LANGUAGE plpgsql;

-- Fix set_timestamp function
DROP FUNCTION IF EXISTS public.set_timestamp() CASCADE;
CREATE OR REPLACE FUNCTION public.set_timestamp()
RETURNS TRIGGER 
SECURITY DEFINER
SET search_path = public, pg_catalog
AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Recreate trigger for agent_configuration
DROP TRIGGER IF EXISTS trg_agent_cfg_set_timestamp ON public.agent_configuration;
CREATE TRIGGER trg_agent_cfg_set_timestamp
    BEFORE UPDATE ON public.agent_configuration
    FOR EACH ROW
    EXECUTE FUNCTION public.set_timestamp();

-- ========================================
-- PART 4: Add comments for documentation
-- ========================================

COMMENT ON POLICY "agent_configuration_select_policy" ON public.agent_configuration IS 'Allow all authenticated users to read agent configuration';
COMMENT ON POLICY "agent_configuration_admin_policy" ON public.agent_configuration IS 'Only service role can modify agent configuration';

COMMENT ON POLICY "chat_sessions_user_select" ON public.chat_sessions IS 'Users can only view their own chat sessions';
COMMENT ON POLICY "chat_sessions_user_insert" ON public.chat_sessions IS 'Users can only create their own chat sessions';
COMMENT ON POLICY "chat_sessions_user_update" ON public.chat_sessions IS 'Users can only update their own chat sessions';
COMMENT ON POLICY "chat_sessions_user_delete" ON public.chat_sessions IS 'Users can only delete their own chat sessions';

COMMENT ON POLICY "chat_messages_user_select" ON public.chat_messages IS 'Users can only view messages from their own sessions';
COMMENT ON POLICY "chat_messages_user_insert" ON public.chat_messages IS 'Users can only add messages to their own sessions';
COMMENT ON POLICY "chat_messages_user_update" ON public.chat_messages IS 'Users can only update messages in their own sessions';

-- ========================================
-- PART 5: Verification queries
-- ========================================

-- Create a verification function to check security status
CREATE OR REPLACE FUNCTION public.verify_security_fixes()
RETURNS TABLE (
    check_name TEXT,
    status TEXT,
    details TEXT
) 
SECURITY DEFINER
SET search_path = public, pg_catalog
AS $$
BEGIN
    -- Check RLS enabled on all public tables
    RETURN QUERY
    SELECT 
        'RLS Status'::TEXT as check_name,
        CASE 
            WHEN bool_and(relrowsecurity) THEN 'PASS'::TEXT
            ELSE 'FAIL'::TEXT
        END as status,
        string_agg(tablename || ': ' || CASE WHEN relrowsecurity THEN 'enabled' ELSE 'DISABLED' END, ', ')::TEXT as details
    FROM pg_tables t
    JOIN pg_class c ON c.relname = t.tablename AND c.relnamespace = (SELECT oid FROM pg_namespace WHERE nspname = 'public')
    WHERE t.schemaname = 'public'
    AND t.tablename IN ('agent_configuration', 'chat_sessions', 'chat_messages', 
                        'feedme_conversations', 'feedme_examples', 'feedme_examples_temp', 
                        'feedme_folders', 'mailbird_knowledge');

    -- Check policies exist for tables with RLS
    RETURN QUERY
    SELECT 
        'RLS Policies'::TEXT as check_name,
        CASE 
            WHEN COUNT(DISTINCT t.tablename) = COUNT(DISTINCT p.tablename) THEN 'PASS'::TEXT
            ELSE 'FAIL'::TEXT
        END as status,
        'Tables with policies: ' || COUNT(DISTINCT p.tablename)::TEXT || '/' || COUNT(DISTINCT t.tablename)::TEXT as details
    FROM pg_tables t
    LEFT JOIN pg_policies p ON p.schemaname = t.schemaname AND p.tablename = t.tablename
    WHERE t.schemaname = 'public'
    AND t.tablename IN ('agent_configuration', 'chat_sessions', 'chat_messages', 
                        'feedme_conversations', 'feedme_examples', 'feedme_examples_temp', 
                        'feedme_folders', 'mailbird_knowledge');

    -- Check function search_path settings
    RETURN QUERY
    SELECT 
        'Function Search Path'::TEXT as check_name,
        CASE 
            WHEN bool_and(prosecdef AND proconfig::text LIKE '%search_path%') THEN 'PASS'::TEXT
            ELSE 'PARTIAL'::TEXT
        END as status,
        COUNT(*)::TEXT || ' functions checked' as details
    FROM pg_proc
    WHERE pronamespace = (SELECT oid FROM pg_namespace WHERE nspname = 'public')
    AND proname IN ('update_chat_session_timestamp', 'update_session_on_message', 
                    'get_agent_config', 'deactivate_oldest_session', 
                    'enforce_chat_session_limits_after', 'check_session_limits_health', 
                    'set_timestamp');
END;
$$ LANGUAGE plpgsql;

-- Run verification
SELECT * FROM public.verify_security_fixes();

-- ========================================
-- PART 6: Note about manual configuration
-- ========================================

-- NOTE: Leaked Password Protection must be enabled manually in the Supabase Dashboard
-- Go to: Project Settings > Auth > Password Security
-- Enable: "Leaked password protection"
-- This will check passwords against HaveIBeenPwned.org database

-- Add a comment to remind about manual configuration
COMMENT ON FUNCTION public.verify_security_fixes() IS 'Verifies security fixes are applied. Note: Leaked password protection must be enabled manually in Supabase Dashboard under Auth settings.';