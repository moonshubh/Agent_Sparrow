-- Migration 019: Update Chat Session Limits per Agent Type (IMPROVED VERSION)
-- This migration updates the chat session limits to enforce different limits for different agent types
-- Primary agent: 5 sessions max
-- Log analysis agent: 3 sessions max
-- Research agent: 5 sessions max
-- 
-- IMPROVEMENTS APPLIED:
-- 1. Removed SET search_path = '' to avoid table resolution errors
-- 2. Changed trigger from BEFORE to AFTER to prevent recursion
-- 3. Added updated_at trigger for agent_configuration table
-- 4. Fixed metadata key from 'auto_activated_at' to 'auto_deactivated_at'
-- 5. Fixed data types to match actual table structure (VARCHAR instead of UUID)

-- 1. Drop the existing constraint that enforces a single limit for all agent types
DROP INDEX IF EXISTS idx_chat_sessions_user_agent_active_limit;

-- 2. Create or replace the timestamp update function (reusable)
CREATE OR REPLACE FUNCTION set_timestamp()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- 3. Add agent-specific configuration table for future flexibility
CREATE TABLE IF NOT EXISTS agent_configuration (
    agent_type VARCHAR(50) PRIMARY KEY,
    max_active_sessions INTEGER NOT NULL DEFAULT 5,
    max_message_length INTEGER DEFAULT 10000,
    session_timeout_hours INTEGER DEFAULT 24,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    
    CONSTRAINT agent_configuration_max_sessions_positive CHECK (max_active_sessions > 0),
    CONSTRAINT agent_configuration_max_message_length_positive CHECK (max_message_length > 0),
    CONSTRAINT agent_configuration_timeout_positive CHECK (session_timeout_hours > 0)
);

-- 4. Create trigger to automatically update updated_at on agent_configuration
DROP TRIGGER IF EXISTS trg_agent_cfg_set_timestamp ON agent_configuration;
CREATE TRIGGER trg_agent_cfg_set_timestamp
    BEFORE UPDATE ON agent_configuration
    FOR EACH ROW
    EXECUTE FUNCTION set_timestamp();

-- 5. Insert default agent configurations
INSERT INTO agent_configuration (agent_type, max_active_sessions, max_message_length, session_timeout_hours)
VALUES 
    ('primary', 5, 10000, 24),
    ('log_analysis', 3, 50000, 12),
    ('research', 5, 15000, 24),
    ('router', 10, 5000, 6)
ON CONFLICT (agent_type) DO UPDATE SET
    max_active_sessions = EXCLUDED.max_active_sessions,
    updated_at = NOW();

-- 6. Create function to deactivate oldest session (separate from trigger to avoid recursion)
CREATE OR REPLACE FUNCTION deactivate_oldest_session(
    p_user_id VARCHAR(255),  -- Using VARCHAR to match actual table structure
    p_agent_type VARCHAR(50)
) RETURNS VOID AS $$
BEGIN
    -- Deactivate the oldest active session for this user and agent type
    UPDATE chat_sessions
    SET is_active = FALSE, 
        updated_at = NOW(),
        metadata = COALESCE(metadata, '{}'::jsonb) || jsonb_build_object(
            'auto_deactivated_at', NOW(),  -- Fixed: renamed from auto_activated_at
            'deactivated_reason', 'session_limit_exceeded'
        )
    WHERE user_id = p_user_id
        AND agent_type = p_agent_type
        AND is_active = TRUE
        AND id = (
            SELECT id 
            FROM chat_sessions
            WHERE user_id = p_user_id
                AND agent_type = p_agent_type
                AND is_active = TRUE
            ORDER BY last_message_at ASC NULLS FIRST
            LIMIT 1
        );
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- 7. Create AFTER trigger function to enforce session limits (prevents recursion)
CREATE OR REPLACE FUNCTION enforce_chat_session_limits_after()
RETURNS TRIGGER AS $$
DECLARE
    active_count INTEGER;
    max_allowed INTEGER;
BEGIN
    -- Only check for newly activated sessions
    IF NEW.is_active = TRUE AND (OLD IS NULL OR OLD.is_active = FALSE) THEN
        
        -- Get max allowed sessions from configuration table
        SELECT max_active_sessions INTO max_allowed
        FROM agent_configuration
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
        
        -- Count current active sessions for this user and agent type (including the new one)
        SELECT COUNT(*) INTO active_count
        FROM chat_sessions
        WHERE user_id = NEW.user_id 
            AND agent_type = NEW.agent_type
            AND is_active = TRUE;
        
        -- If we now exceed the limit, deactivate the oldest session
        IF active_count > max_allowed THEN
            -- Call separate function to avoid recursion
            PERFORM deactivate_oldest_session(NEW.user_id, NEW.agent_type);
        END IF;
    END IF;
    
    RETURN NEW;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- 8. Drop old trigger if exists and create new AFTER trigger
DROP TRIGGER IF EXISTS trigger_enforce_chat_session_limits ON chat_sessions;
CREATE TRIGGER trigger_enforce_chat_session_limits
    AFTER INSERT OR UPDATE OF is_active ON chat_sessions
    FOR EACH ROW
    EXECUTE FUNCTION enforce_chat_session_limits_after();

-- 9. Add function to get agent configuration
CREATE OR REPLACE FUNCTION get_agent_config(p_agent_type VARCHAR(50))
RETURNS TABLE (
    agent_type VARCHAR(50),
    max_active_sessions INTEGER,
    max_message_length INTEGER,
    session_timeout_hours INTEGER
) AS $$
BEGIN
    RETURN QUERY
    SELECT 
        ac.agent_type,
        ac.max_active_sessions,
        ac.max_message_length,
        ac.session_timeout_hours
    FROM agent_configuration ac
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
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- 10. Add helpful comments
COMMENT ON TABLE agent_configuration IS 'Configuration settings for different agent types including session limits';
COMMENT ON COLUMN agent_configuration.max_active_sessions IS 'Maximum number of active sessions allowed per user for this agent type';
COMMENT ON COLUMN agent_configuration.max_message_length IS 'Maximum length of a single message for this agent type';
COMMENT ON COLUMN agent_configuration.session_timeout_hours IS 'Hours of inactivity before a session is considered stale';
COMMENT ON FUNCTION deactivate_oldest_session(VARCHAR, VARCHAR) IS 'Deactivates the oldest active session for a user and agent type when limit is exceeded';
COMMENT ON FUNCTION enforce_chat_session_limits_after() IS 'AFTER trigger function to enforce session limits without recursion';

-- 11. Create index for performance
CREATE INDEX IF NOT EXISTS idx_chat_sessions_user_agent_active 
ON chat_sessions(user_id, agent_type, is_active) 
WHERE is_active = TRUE;

-- 12. Create index for finding oldest sessions efficiently
CREATE INDEX IF NOT EXISTS idx_chat_sessions_oldest_active
ON chat_sessions(user_id, agent_type, last_message_at)
WHERE is_active = TRUE;

-- 13. Clean up any violations of the new limits (optional, can be run manually)
-- This will deactivate excess sessions for users who currently have too many
DO $$
DECLARE
    user_agent_record RECORD;
    max_allowed INTEGER;
    excess_count INTEGER;
BEGIN
    -- Find users with too many active sessions
    FOR user_agent_record IN 
        SELECT cs.user_id, cs.agent_type, COUNT(*) as active_count
        FROM chat_sessions cs
        WHERE cs.is_active = TRUE
        GROUP BY cs.user_id, cs.agent_type
    LOOP
        -- Get max allowed for this agent type
        SELECT max_active_sessions INTO max_allowed
        FROM agent_configuration
        WHERE agent_type = user_agent_record.agent_type;
        
        IF max_allowed IS NULL THEN
            max_allowed := 5; -- Default
        END IF;
        
        -- Calculate excess sessions
        excess_count := user_agent_record.active_count - max_allowed;
        
        -- Deactivate excess sessions (oldest first)
        IF excess_count > 0 THEN
            UPDATE chat_sessions
            SET is_active = FALSE,
                updated_at = NOW(),
                metadata = COALESCE(metadata, '{}'::jsonb) || 
                          jsonb_build_object(
                              'deactivated_by_migration', true,
                              'migration_date', NOW(),
                              'auto_deactivated_at', NOW()  -- Fixed: using correct key name
                          )
            WHERE id IN (
                SELECT id
                FROM chat_sessions
                WHERE user_id = user_agent_record.user_id
                    AND agent_type = user_agent_record.agent_type
                    AND is_active = TRUE
                ORDER BY last_message_at ASC NULLS FIRST
                LIMIT excess_count
            );
            
            RAISE NOTICE 'Deactivated % excess sessions for user % agent %', 
                         excess_count, user_agent_record.user_id, user_agent_record.agent_type;
        END IF;
    END LOOP;
END $$;

-- 14. Add monitoring function to check session health
CREATE OR REPLACE FUNCTION check_session_limits_health()
RETURNS TABLE (
    agent_type VARCHAR(50),
    user_id VARCHAR(255),  -- Using VARCHAR to match actual table structure
    active_sessions_count INTEGER,
    max_allowed INTEGER,
    status TEXT
) AS $$
BEGIN
    RETURN QUERY
    WITH session_counts AS (
        SELECT 
            cs.agent_type,
            cs.user_id,
            COUNT(*) as active_count
        FROM chat_sessions cs
        WHERE cs.is_active = TRUE
        GROUP BY cs.agent_type, cs.user_id
    ),
    config AS (
        SELECT 
            ac.agent_type,
            ac.max_active_sessions
        FROM agent_configuration ac
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
$$ LANGUAGE plpgsql SECURITY DEFINER;

COMMENT ON FUNCTION check_session_limits_health() IS 'Monitoring function to check if any users exceed their session limits';