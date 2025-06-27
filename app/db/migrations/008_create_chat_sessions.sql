-- Migration 008: Create Chat Sessions and Messages Tables
-- This migration creates the database tables for chat session persistence
-- following the established MB-Sparrow patterns

-- 1. Create chat_sessions table
CREATE TABLE IF NOT EXISTS chat_sessions (
    id SERIAL PRIMARY KEY,
    user_id VARCHAR(255) NOT NULL,
    title VARCHAR(255) NOT NULL,
    agent_type VARCHAR(50) NOT NULL DEFAULT 'primary',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    last_message_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    is_active BOOLEAN DEFAULT TRUE,
    metadata JSONB DEFAULT '{}',
    message_count INTEGER DEFAULT 0,
    
    -- Constraints
    CONSTRAINT chat_sessions_title_not_empty CHECK (LENGTH(TRIM(title)) > 0),
    CONSTRAINT chat_sessions_user_id_not_empty CHECK (LENGTH(TRIM(user_id)) > 0),
    CONSTRAINT chat_sessions_agent_type_valid CHECK (
        agent_type IN ('primary', 'log_analysis', 'research', 'router')
    )
);

-- 2. Create chat_messages table
CREATE TABLE IF NOT EXISTS chat_messages (
    id SERIAL PRIMARY KEY,
    session_id INTEGER NOT NULL REFERENCES chat_sessions(id) ON DELETE CASCADE,
    message_type VARCHAR(20) NOT NULL DEFAULT 'user',
    content TEXT NOT NULL,
    agent_type VARCHAR(50),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    metadata JSONB DEFAULT '{}',
    
    -- Constraints
    CONSTRAINT chat_messages_content_not_empty CHECK (LENGTH(TRIM(content)) > 0),
    CONSTRAINT chat_messages_type_valid CHECK (
        message_type IN ('user', 'assistant', 'system')
    ),
    CONSTRAINT chat_messages_agent_type_valid CHECK (
        agent_type IS NULL OR agent_type IN ('primary', 'log_analysis', 'research', 'router')
    )
);

-- 3. Create indexes for performance
CREATE INDEX IF NOT EXISTS idx_chat_sessions_user_id ON chat_sessions(user_id);
CREATE INDEX IF NOT EXISTS idx_chat_sessions_user_agent ON chat_sessions(user_id, agent_type);
CREATE INDEX IF NOT EXISTS idx_chat_sessions_active ON chat_sessions(is_active) WHERE is_active = TRUE;
CREATE INDEX IF NOT EXISTS idx_chat_sessions_last_message ON chat_sessions(last_message_at DESC);
CREATE INDEX IF NOT EXISTS idx_chat_messages_session_id ON chat_messages(session_id);
CREATE INDEX IF NOT EXISTS idx_chat_messages_created_at ON chat_messages(created_at DESC);

-- 4. Create constraint to limit active sessions per user per agent_type (max 5)
CREATE UNIQUE INDEX IF NOT EXISTS idx_chat_sessions_user_agent_active_limit 
ON chat_sessions(user_id, agent_type, (
    CASE WHEN is_active THEN 
        ROW_NUMBER() OVER (
            PARTITION BY user_id, agent_type, is_active 
            ORDER BY last_message_at DESC
        ) 
    END
)) 
WHERE is_active = TRUE AND (
    ROW_NUMBER() OVER (
        PARTITION BY user_id, agent_type, is_active 
        ORDER BY last_message_at DESC
    ) <= 5
);

-- 5. Create triggers for automatic timestamp updates
CREATE OR REPLACE FUNCTION update_chat_session_timestamp()
RETURNS TRIGGER AS $$
BEGIN
    SET search_path = '';
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ language 'plpgsql' SECURITY DEFINER;

CREATE OR REPLACE FUNCTION update_session_on_message()
RETURNS TRIGGER AS $$
BEGIN
    SET search_path = '';
    
    -- Update parent session's last_message_at and message_count
    UPDATE chat_sessions 
    SET 
        last_message_at = NOW(),
        message_count = (
            SELECT COUNT(*) 
            FROM chat_messages 
            WHERE session_id = NEW.session_id
        )
    WHERE id = NEW.session_id;
    
    RETURN NEW;
END;
$$ language 'plpgsql' SECURITY DEFINER;

-- 6. Create triggers
DROP TRIGGER IF EXISTS trigger_chat_sessions_updated_at ON chat_sessions;
CREATE TRIGGER trigger_chat_sessions_updated_at
    BEFORE UPDATE ON chat_sessions
    FOR EACH ROW
    EXECUTE FUNCTION update_chat_session_timestamp();

DROP TRIGGER IF EXISTS trigger_update_session_on_message ON chat_messages;
CREATE TRIGGER trigger_update_session_on_message
    AFTER INSERT ON chat_messages
    FOR EACH ROW
    EXECUTE FUNCTION update_session_on_message();

-- 7. Add comments for documentation
COMMENT ON TABLE chat_sessions IS 'Chat sessions for persistent conversation management';
COMMENT ON TABLE chat_messages IS 'Individual messages within chat sessions';
COMMENT ON COLUMN chat_sessions.user_id IS 'User identifier from JWT token (TokenPayload.sub)';
COMMENT ON COLUMN chat_sessions.agent_type IS 'Type of agent handling this session';
COMMENT ON COLUMN chat_sessions.message_count IS 'Cached count of messages in this session';
COMMENT ON COLUMN chat_messages.message_type IS 'Type of message: user, assistant, or system';
COMMENT ON COLUMN chat_messages.agent_type IS 'Specific agent that generated assistant messages';

-- 8. Create function to cleanup old inactive sessions (optional maintenance)
CREATE OR REPLACE FUNCTION cleanup_old_chat_sessions(days_old INTEGER DEFAULT 30)
RETURNS INTEGER AS $$
DECLARE
    deleted_count INTEGER;
BEGIN
    SET search_path = '';
    
    DELETE FROM chat_sessions 
    WHERE 
        is_active = FALSE 
        AND updated_at < NOW() - INTERVAL '1 day' * days_old;
    
    GET DIAGNOSTICS deleted_count = ROW_COUNT;
    RETURN deleted_count;
END;
$$ language 'plpgsql' SECURITY DEFINER;

COMMENT ON FUNCTION cleanup_old_chat_sessions(INTEGER) IS 'Cleanup inactive chat sessions older than specified days';