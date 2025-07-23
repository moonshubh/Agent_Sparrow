-- Migration: 014_supabase_auth_integration.sql
-- Purpose: Integrate Supabase Auth with user_api_keys and add auth tracking

-- Enable RLS on user_api_keys if not already enabled
ALTER TABLE user_api_keys ENABLE ROW LEVEL SECURITY;

-- Drop existing RLS policies if they exist
DROP POLICY IF EXISTS "Users can view own API keys" ON user_api_keys;
DROP POLICY IF EXISTS "Users can insert own API keys" ON user_api_keys;
DROP POLICY IF EXISTS "Users can update own API keys" ON user_api_keys;
DROP POLICY IF EXISTS "Users can delete own API keys" ON user_api_keys;

-- Create RLS policies using Supabase auth.uid()
CREATE POLICY "Users can view own API keys" ON user_api_keys
    FOR SELECT USING (user_id = auth.uid()::text);

CREATE POLICY "Users can insert own API keys" ON user_api_keys
    FOR INSERT WITH CHECK (user_id = auth.uid()::text);

CREATE POLICY "Users can update own API keys" ON user_api_keys
    FOR UPDATE USING (user_id = auth.uid()::text);

CREATE POLICY "Users can delete own API keys" ON user_api_keys
    FOR DELETE USING (user_id = auth.uid()::text);

-- Create auth session tracking table
CREATE TABLE IF NOT EXISTS auth_sessions (
    id SERIAL PRIMARY KEY,
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    session_token TEXT NOT NULL UNIQUE,
    refresh_token TEXT,
    expires_at TIMESTAMP WITH TIME ZONE NOT NULL,
    ip_address INET,
    user_agent TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    last_activity TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    revoked_at TIMESTAMP WITH TIME ZONE,
    INDEX idx_auth_sessions_user_id (user_id),
    INDEX idx_auth_sessions_token (session_token),
    INDEX idx_auth_sessions_expires (expires_at)
);

-- Enable RLS on auth_sessions
ALTER TABLE auth_sessions ENABLE ROW LEVEL SECURITY;

-- RLS policies for auth_sessions
CREATE POLICY "Users can view own sessions" ON auth_sessions
    FOR SELECT USING (user_id = auth.uid());

CREATE POLICY "Service role can manage all sessions" ON auth_sessions
    FOR ALL USING (auth.jwt() ->> 'role' = 'service_role');

-- Create auth audit log table
CREATE TABLE IF NOT EXISTS auth_audit_log (
    id SERIAL PRIMARY KEY,
    user_id UUID REFERENCES auth.users(id) ON DELETE SET NULL,
    event_type VARCHAR(50) NOT NULL, -- sign_up, sign_in, sign_out, password_reset, etc.
    event_details JSONB,
    ip_address INET,
    user_agent TEXT,
    success BOOLEAN NOT NULL DEFAULT true,
    error_message TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_auth_audit_user_id (user_id),
    INDEX idx_auth_audit_event_type (event_type),
    INDEX idx_auth_audit_created_at (created_at)
);

-- Update user_api_keys to use UUID for user_id (matching Supabase auth.users)
-- First, add a new column
ALTER TABLE user_api_keys ADD COLUMN user_uuid UUID;

-- Create a temporary mapping (in production, you'd migrate existing data)
-- For now, we'll allow both until migration is complete
ALTER TABLE user_api_keys ALTER COLUMN user_id DROP NOT NULL;

-- Add index for performance
CREATE INDEX idx_user_api_keys_user_uuid ON user_api_keys(user_uuid);

-- Update api_key_audit_log similarly
ALTER TABLE api_key_audit_log ADD COLUMN user_uuid UUID;
CREATE INDEX idx_api_key_audit_log_user_uuid ON api_key_audit_log(user_uuid);

-- Create a view for backward compatibility
CREATE OR REPLACE VIEW user_api_keys_compat AS
SELECT 
    id,
    COALESCE(user_id, user_uuid::text) as user_id,
    user_uuid,
    api_key_type,
    encrypted_key,
    key_name,
    is_active,
    created_at,
    updated_at,
    last_used_at
FROM user_api_keys;

-- Function to clean up expired sessions
CREATE OR REPLACE FUNCTION cleanup_expired_sessions()
RETURNS void AS $$
BEGIN
    UPDATE auth_sessions 
    SET revoked_at = CURRENT_TIMESTAMP 
    WHERE expires_at < CURRENT_TIMESTAMP 
    AND revoked_at IS NULL;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- Create a scheduled job to clean up sessions (requires pg_cron extension)
-- Uncomment if pg_cron is available:
-- SELECT cron.schedule('cleanup-expired-sessions', '0 * * * *', 'SELECT cleanup_expired_sessions();');

-- Grant necessary permissions
GRANT USAGE ON SCHEMA public TO authenticated;
GRANT ALL ON user_api_keys TO authenticated;
GRANT ALL ON auth_sessions TO authenticated;
GRANT SELECT ON auth_audit_log TO authenticated;

-- Comments for documentation
COMMENT ON TABLE auth_sessions IS 'Tracks active user sessions with JWT tokens';
COMMENT ON TABLE auth_audit_log IS 'Audit trail for all authentication events';
COMMENT ON COLUMN user_api_keys.user_uuid IS 'UUID reference to auth.users, replacing string user_id';