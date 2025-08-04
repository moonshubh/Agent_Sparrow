-- Migration: 003_create_user_api_keys.sql
-- Create secure API key storage for user-specific configurations

-- Create user_api_keys table for encrypted API key storage
CREATE TABLE IF NOT EXISTS user_api_keys (
    id SERIAL PRIMARY KEY,
    user_id VARCHAR(255) NOT NULL, -- JWT subject from authentication
    api_key_type VARCHAR(50) NOT NULL, -- 'gemini', 'tavily', 'firecrawl'
    encrypted_key TEXT NOT NULL, -- Base64-encoded encrypted API key
    key_name VARCHAR(100), -- Optional user-friendly name
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    last_used_at TIMESTAMP WITH TIME ZONE,
    
    -- Constraints
    CONSTRAINT unique_user_api_key_type UNIQUE (user_id, api_key_type),
    CONSTRAINT valid_api_key_type CHECK (api_key_type IN ('gemini', 'tavily', 'firecrawl')),
    CONSTRAINT non_empty_encrypted_key CHECK (LENGTH(encrypted_key) > 0),
    CONSTRAINT non_empty_user_id CHECK (LENGTH(user_id) > 0)
);

-- Create indexes for performance
CREATE INDEX IF NOT EXISTS idx_user_api_keys_user_id ON user_api_keys(user_id);
CREATE INDEX IF NOT EXISTS idx_user_api_keys_type ON user_api_keys(api_key_type);
CREATE INDEX IF NOT EXISTS idx_user_api_keys_active ON user_api_keys(is_active);
CREATE INDEX IF NOT EXISTS idx_user_api_keys_last_used ON user_api_keys(last_used_at);

-- Create audit log table for API key operations (without exposing keys)
CREATE TABLE IF NOT EXISTS api_key_audit_log (
    id SERIAL PRIMARY KEY,
    user_id VARCHAR(255) NOT NULL,
    api_key_type VARCHAR(50) NOT NULL,
    operation VARCHAR(50) NOT NULL, -- 'CREATE', 'UPDATE', 'DELETE', 'USE'
    operation_details JSONB, -- Additional context (without sensitive data)
    ip_address INET,
    user_agent TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    
    -- Constraints
    CONSTRAINT valid_audit_operation CHECK (operation IN ('CREATE', 'UPDATE', 'DELETE', 'USE', 'VALIDATE')),
    CONSTRAINT non_empty_audit_user_id CHECK (LENGTH(user_id) > 0)
);

-- Create indexes for audit log
CREATE INDEX IF NOT EXISTS idx_audit_user_id ON api_key_audit_log(user_id);
CREATE INDEX IF NOT EXISTS idx_audit_operation ON api_key_audit_log(operation);
CREATE INDEX IF NOT EXISTS idx_audit_created_at ON api_key_audit_log(created_at);

-- Create updated_at trigger for user_api_keys
CREATE OR REPLACE FUNCTION update_user_api_keys_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trigger_user_api_keys_updated_at
    BEFORE UPDATE ON user_api_keys
    FOR EACH ROW
    EXECUTE FUNCTION update_user_api_keys_updated_at();

-- Create RLS (Row Level Security) policies for user isolation
ALTER TABLE user_api_keys ENABLE ROW LEVEL SECURITY;
ALTER TABLE api_key_audit_log ENABLE ROW LEVEL SECURITY;

-- Policy: Users can only access their own API keys
CREATE POLICY user_api_keys_isolation ON user_api_keys
    FOR ALL TO authenticated
    USING (user_id = current_setting('app.current_user_id', true));

-- Policy: Users can only access their own audit logs
CREATE POLICY api_key_audit_log_isolation ON api_key_audit_log
    FOR ALL TO authenticated
    USING (user_id = current_setting('app.current_user_id', true));

-- Grant appropriate permissions (adjust based on your app's user roles)
GRANT SELECT, INSERT, UPDATE, DELETE ON user_api_keys TO authenticated;
GRANT SELECT, INSERT ON api_key_audit_log TO authenticated;
GRANT USAGE ON SEQUENCE user_api_keys_id_seq TO authenticated;
GRANT USAGE ON SEQUENCE api_key_audit_log_id_seq TO authenticated;

-- Add comments for documentation
COMMENT ON TABLE user_api_keys IS 'Stores encrypted API keys for users with complete isolation';
COMMENT ON COLUMN user_api_keys.encrypted_key IS 'AES-256 encrypted API key using user-specific encryption key';
COMMENT ON COLUMN user_api_keys.api_key_type IS 'Type of API key: gemini, tavily, or firecrawl';
COMMENT ON TABLE api_key_audit_log IS 'Audit log for API key operations without exposing sensitive data';