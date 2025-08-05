-- Migration 019: Update Chat Session Limits per Agent Type
-- This migration updates the chat session limits to enforce different limits for different agent types
-- Primary agent: 5 sessions max
-- Log analysis agent: 3 sessions max
-- Research agent: 5 sessions max

-- 1. Drop the existing constraint that enforces a single limit for all agent types
DROP INDEX IF EXISTS idx_chat_sessions_user_agent_active_limit;

-- 2. Create a function to enforce different session limits per agent type
CREATE OR REPLACE FUNCTION enforce_chat_session_limits()
RETURNS TRIGGER AS $$
DECLARE
    active_count INTEGER;
    max_allowed INTEGER;
BEGIN
    SET search_path = '';
    
    -- Only check for active sessions
    IF NEW.is_active = FALSE THEN
        RETURN NEW;
    END IF;
    
    -- Determine max allowed sessions based on agent type
    CASE NEW.agent_type
        WHEN 'primary' THEN max_allowed := 5;
        WHEN 'log_analysis' THEN max_allowed := 3;
        WHEN 'research' THEN max_allowed := 5;
        WHEN 'router' THEN max_allowed := 10; -- Router can have more sessions
        ELSE max_allowed := 5; -- Default limit
    END CASE;
    
    -- Count current active sessions for this user and agent type
    SELECT COUNT(*) INTO active_count
    FROM chat_sessions
    WHERE user_id = NEW.user_id 
        AND agent_type = NEW.agent_type
        AND is_active = TRUE
        AND id != COALESCE(NEW.id, -1); -- Exclude current session on update
    
    -- If at or above limit, deactivate the oldest session
    IF active_count >= max_allowed THEN
        UPDATE chat_sessions
        SET is_active = FALSE, 
            updated_at = NOW()
        WHERE user_id = NEW.user_id
            AND agent_type = NEW.agent_type
            AND is_active = TRUE
            AND id = (
                SELECT id 
                FROM chat_sessions
                WHERE user_id = NEW.user_id
                    AND agent_type = NEW.agent_type
                    AND is_active = TRUE
                ORDER BY last_message_at ASC
                LIMIT 1
            );
            
        -- Log the auto-deactivation in metadata
        IF NEW.metadata IS NULL THEN
            NEW.metadata = '{}'::jsonb;
        END IF;
        NEW.metadata = NEW.metadata || jsonb_build_object(
            'auto_activated_at', NOW(),
            'previous_session_deactivated', true
        );
    END IF;
    
    RETURN NEW;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- 3. Create trigger to enforce session limits on insert and update
DROP TRIGGER IF EXISTS trigger_enforce_chat_session_limits ON chat_sessions;
CREATE TRIGGER trigger_enforce_chat_session_limits
    BEFORE INSERT OR UPDATE OF is_active ON chat_sessions
    FOR EACH ROW
    EXECUTE FUNCTION enforce_chat_session_limits();

-- 4. Add agent-specific configuration table for future flexibility
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

-- 6. Update the enforce function to use the configuration table
CREATE OR REPLACE FUNCTION enforce_chat_session_limits()
RETURNS TRIGGER AS $$
DECLARE
    active_count INTEGER;
    max_allowed INTEGER;
BEGIN
    SET search_path = '';
    
    -- Only check for active sessions
    IF NEW.is_active = FALSE THEN
        RETURN NEW;
    END IF;
    
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
    
    -- Count current active sessions for this user and agent type
    SELECT COUNT(*) INTO active_count
    FROM chat_sessions
    WHERE user_id = NEW.user_id 
        AND agent_type = NEW.agent_type
        AND is_active = TRUE
        AND id != COALESCE(NEW.id, -1); -- Exclude current session on update
    
    -- If at or above limit, deactivate the oldest session
    IF active_count >= max_allowed THEN
        UPDATE chat_sessions
        SET is_active = FALSE, 
            updated_at = NOW()
        WHERE user_id = NEW.user_id
            AND agent_type = NEW.agent_type
            AND is_active = TRUE
            AND id = (
                SELECT id 
                FROM chat_sessions
                WHERE user_id = NEW.user_id
                    AND agent_type = NEW.agent_type
                    AND is_active = TRUE
                ORDER BY last_message_at ASC
                LIMIT 1
            );
            
        -- Log the auto-deactivation in metadata
        IF NEW.metadata IS NULL THEN
            NEW.metadata = '{}'::jsonb;
        END IF;
        NEW.metadata = NEW.metadata || jsonb_build_object(
            'auto_activated_at', NOW(),
            'previous_session_deactivated', true
        );
    END IF;
    
    RETURN NEW;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- 7. Add function to get agent configuration
CREATE OR REPLACE FUNCTION get_agent_config(p_agent_type VARCHAR(50))
RETURNS TABLE (
    agent_type VARCHAR(50),
    max_active_sessions INTEGER,
    max_message_length INTEGER,
    session_timeout_hours INTEGER
) AS $$
BEGIN
    SET search_path = '';
    
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

-- 8. Add helpful comments
COMMENT ON TABLE agent_configuration IS 'Configuration settings for different agent types including session limits';
COMMENT ON COLUMN agent_configuration.max_active_sessions IS 'Maximum number of active sessions allowed per user for this agent type';
COMMENT ON COLUMN agent_configuration.max_message_length IS 'Maximum length of a single message for this agent type';
COMMENT ON COLUMN agent_configuration.session_timeout_hours IS 'Hours of inactivity before a session is considered stale';

-- 9. Create index for performance
CREATE INDEX IF NOT EXISTS idx_chat_sessions_user_agent_active 
ON chat_sessions(user_id, agent_type, is_active) 
WHERE is_active = TRUE;

-- 10. Clean up any violations of the new limits (optional, can be run manually)
-- This will deactivate excess sessions for users who currently have too many
DO $$
DECLARE
    user_agent_record RECORD;
    max_allowed INTEGER;
    excess_count INTEGER;
BEGIN
    SET search_path = '';
    
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
                          jsonb_build_object('deactivated_by_migration', true, 'migration_date', NOW())
            WHERE id IN (
                SELECT id
                FROM chat_sessions
                WHERE user_id = user_agent_record.user_id
                    AND agent_type = user_agent_record.agent_type
                    AND is_active = TRUE
                ORDER BY last_message_at ASC
                LIMIT excess_count
            );
            
            RAISE NOTICE 'Deactivated % excess sessions for user % agent %', 
                         excess_count, user_agent_record.user_id, user_agent_record.agent_type;
        END IF;
    END LOOP;
END $$;