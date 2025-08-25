-- Migration: Create LangGraph Checkpointer Tables
-- Description: Implements persistent memory for LangGraph with thread management,
--              versioned checkpoints, and performance optimizations
-- Author: MB-Sparrow Development Team
-- Date: 2025-01-08

-- ============================================================================
-- CORE TABLES
-- ============================================================================

-- Thread management table
CREATE TABLE IF NOT EXISTS langgraph_threads (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL,
    session_id INTEGER REFERENCES chat_sessions(id) ON DELETE CASCADE,
    parent_thread_id UUID REFERENCES langgraph_threads(id) ON DELETE SET NULL,
    
    -- Thread metadata
    title TEXT NOT NULL,
    status VARCHAR(20) DEFAULT 'active' CHECK (status IN ('active', 'paused', 'completed', 'archived')),
    thread_type VARCHAR(50) DEFAULT 'conversation',
    
    -- Performance tracking
    checkpoint_count INTEGER DEFAULT 0,
    last_checkpoint_id UUID,
    last_checkpoint_at TIMESTAMPTZ,
    last_activity_at TIMESTAMPTZ DEFAULT NOW(),
    
    -- Metadata storage
    metadata JSONB DEFAULT '{}',
    config JSONB DEFAULT '{}',
    
    -- Timestamps
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    archived_at TIMESTAMPTZ,
    
    -- Constraints
    CONSTRAINT unique_user_session UNIQUE(user_id, session_id)
);

-- Checkpoints table with versioning and delta storage
CREATE TABLE IF NOT EXISTS langgraph_checkpoints (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    thread_id UUID NOT NULL REFERENCES langgraph_threads(id) ON DELETE CASCADE,
    parent_checkpoint_id UUID REFERENCES langgraph_checkpoints(id) ON DELETE CASCADE,
    
    -- Versioning
    version INTEGER NOT NULL,
    channel VARCHAR(100) DEFAULT 'main',
    checkpoint_type VARCHAR(20) DEFAULT 'delta' CHECK (checkpoint_type IN ('full', 'delta')),
    
    -- State storage
    state JSONB NOT NULL,
    state_size_bytes INTEGER GENERATED ALWAYS AS (pg_column_size(state)) STORED,
    is_compressed BOOLEAN DEFAULT FALSE,
    
    -- Checkpoint metadata
    metadata JSONB DEFAULT '{}',
    is_latest BOOLEAN DEFAULT FALSE,
    
    -- Timestamps
    created_at TIMESTAMPTZ DEFAULT NOW(),
    
    -- Constraints
    CONSTRAINT unique_thread_version_channel UNIQUE(thread_id, version, channel)
);

-- Write-ahead log for checkpoint operations
CREATE TABLE IF NOT EXISTS langgraph_checkpoint_writes (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    thread_id UUID NOT NULL REFERENCES langgraph_threads(id) ON DELETE CASCADE,
    checkpoint_id UUID REFERENCES langgraph_checkpoints(id) ON DELETE SET NULL,
    
    -- Write operation details
    sequence_number BIGSERIAL,
    operation_type VARCHAR(20) CHECK (operation_type IN ('create', 'update', 'fork', 'restore')),
    channel VARCHAR(100) DEFAULT 'main',
    
    -- Write data
    write_data JSONB NOT NULL,
    status VARCHAR(20) DEFAULT 'pending' CHECK (status IN ('pending', 'processing', 'completed', 'failed')),
    error_message TEXT,
    retry_count INTEGER DEFAULT 0,
    
    -- Timestamps
    created_at TIMESTAMPTZ DEFAULT NOW(),
    processed_at TIMESTAMPTZ,
    
    -- Performance
    processing_time_ms INTEGER
);

-- Thread access log for analytics
CREATE TABLE IF NOT EXISTS langgraph_thread_access (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    thread_id UUID NOT NULL REFERENCES langgraph_threads(id) ON DELETE CASCADE,
    user_id UUID NOT NULL,
    
    -- Access details
    access_type VARCHAR(20) CHECK (access_type IN ('read', 'write', 'switch', 'fork')),
    checkpoint_id UUID REFERENCES langgraph_checkpoints(id) ON DELETE SET NULL,
    
    -- Performance metrics
    response_time_ms INTEGER,
    metadata JSONB DEFAULT '{}',
    
    -- Timestamp
    accessed_at TIMESTAMPTZ DEFAULT NOW()
);

-- ============================================================================
-- INDEXES FOR PERFORMANCE
-- ============================================================================

-- Thread indexes
CREATE INDEX IF NOT EXISTS idx_langgraph_threads_user_session ON langgraph_threads(user_id, session_id);
CREATE INDEX IF NOT EXISTS idx_langgraph_threads_user_active ON langgraph_threads(user_id, status) WHERE status = 'active';
CREATE INDEX IF NOT EXISTS idx_langgraph_threads_last_activity ON langgraph_threads(last_activity_at DESC);
CREATE INDEX IF NOT EXISTS idx_langgraph_threads_parent ON langgraph_threads(parent_thread_id) WHERE parent_thread_id IS NOT NULL;

-- Checkpoint indexes
CREATE INDEX IF NOT EXISTS idx_langgraph_checkpoints_thread_version ON langgraph_checkpoints(thread_id, version DESC);
CREATE INDEX IF NOT EXISTS idx_langgraph_checkpoints_thread_latest ON langgraph_checkpoints(thread_id, is_latest) WHERE is_latest = true;
CREATE INDEX IF NOT EXISTS idx_langgraph_checkpoints_thread_channel ON langgraph_checkpoints(thread_id, channel, version DESC);
CREATE INDEX IF NOT EXISTS idx_langgraph_checkpoints_parent ON langgraph_checkpoints(parent_checkpoint_id) WHERE parent_checkpoint_id IS NOT NULL;

-- Write log indexes
CREATE INDEX IF NOT EXISTS idx_langgraph_writes_thread_pending ON langgraph_checkpoint_writes(thread_id, status) WHERE status = 'pending';
CREATE INDEX IF NOT EXISTS idx_langgraph_writes_sequence ON langgraph_checkpoint_writes(thread_id, sequence_number DESC);

-- Access log indexes
CREATE INDEX IF NOT EXISTS idx_langgraph_access_thread ON langgraph_thread_access(thread_id, accessed_at DESC);
CREATE INDEX IF NOT EXISTS idx_langgraph_access_user ON langgraph_thread_access(user_id, accessed_at DESC);

-- JSONB GIN indexes for metadata searches
CREATE INDEX IF NOT EXISTS idx_langgraph_threads_metadata_gin ON langgraph_threads USING GIN (metadata);
CREATE INDEX IF NOT EXISTS idx_langgraph_checkpoints_state_gin ON langgraph_checkpoints USING GIN (state) WHERE checkpoint_type = 'full';

-- ============================================================================
-- HELPER FUNCTIONS
-- ============================================================================

-- Get latest checkpoint for a thread
CREATE OR REPLACE FUNCTION get_latest_checkpoint(p_thread_id UUID, p_channel VARCHAR DEFAULT 'main')
RETURNS TABLE (
    checkpoint_id UUID,
    version INTEGER,
    checkpoint_type VARCHAR,
    state JSONB,
    metadata JSONB,
    created_at TIMESTAMPTZ
) AS $$
BEGIN
    RETURN QUERY
    SELECT 
        id AS checkpoint_id,
        version,
        checkpoint_type,
        state,
        metadata,
        created_at
    FROM langgraph_checkpoints
    WHERE thread_id = p_thread_id 
        AND channel = p_channel
        AND is_latest = true
    LIMIT 1;
END;
$$ LANGUAGE plpgsql;

-- Get or create thread with proper access control
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

-- Save checkpoint with automatic delta/full decision and access control
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
    
    -- Update thread stats
    UPDATE langgraph_threads
    SET checkpoint_count = checkpoint_count + 1,
        last_checkpoint_id = v_checkpoint_id,
        last_checkpoint_at = NOW(),
        last_activity_at = NOW()
    WHERE id = p_thread_id AND user_id = v_auth_user_id; -- Double-check ownership
    
    RETURN v_checkpoint_id;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- Fork thread at specific checkpoint with access control
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
-- ROW LEVEL SECURITY
-- ============================================================================

ALTER TABLE langgraph_threads ENABLE ROW LEVEL SECURITY;
ALTER TABLE langgraph_checkpoints ENABLE ROW LEVEL SECURITY;
ALTER TABLE langgraph_checkpoint_writes ENABLE ROW LEVEL SECURITY;
ALTER TABLE langgraph_thread_access ENABLE ROW LEVEL SECURITY;

-- Thread policies
CREATE POLICY "Users can view their own threads"
    ON langgraph_threads FOR SELECT
    USING (user_id = auth.uid() OR user_id::text = current_setting('request.jwt.claims', true)::json->>'sub');

CREATE POLICY "Users can create their own threads"
    ON langgraph_threads FOR INSERT
    WITH CHECK (user_id = auth.uid() OR user_id::text = current_setting('request.jwt.claims', true)::json->>'sub');

CREATE POLICY "Users can update their own threads"
    ON langgraph_threads FOR UPDATE
    USING (user_id = auth.uid() OR user_id::text = current_setting('request.jwt.claims', true)::json->>'sub');

-- Checkpoint policies (inherited from thread ownership)
CREATE POLICY "Users can view checkpoints of their threads"
    ON langgraph_checkpoints FOR SELECT
    USING (
        thread_id IN (
            SELECT id FROM langgraph_threads 
            WHERE user_id = auth.uid() OR user_id::text = current_setting('request.jwt.claims', true)::json->>'sub'
        )
    );

CREATE POLICY "Users can create checkpoints for their threads"
    ON langgraph_checkpoints FOR INSERT
    WITH CHECK (
        thread_id IN (
            SELECT id FROM langgraph_threads 
            WHERE user_id = auth.uid() OR user_id::text = current_setting('request.jwt.claims', true)::json->>'sub'
        )
    );

-- Write log policies
CREATE POLICY "Users can view writes for their threads"
    ON langgraph_checkpoint_writes FOR SELECT
    USING (
        thread_id IN (
            SELECT id FROM langgraph_threads 
            WHERE user_id = auth.uid() OR user_id::text = current_setting('request.jwt.claims', true)::json->>'sub'
        )
    );

-- Access log policies (read-only for users)
CREATE POLICY "Users can view their access logs"
    ON langgraph_thread_access FOR SELECT
    USING (user_id = auth.uid() OR user_id::text = current_setting('request.jwt.claims', true)::json->>'sub');

-- ============================================================================
-- MONITORING VIEWS
-- ============================================================================

CREATE OR REPLACE VIEW langgraph_thread_metrics AS
SELECT 
    t.user_id,
    COUNT(DISTINCT t.id) as thread_count,
    COUNT(DISTINCT CASE WHEN t.status = 'active' THEN t.id END) as active_threads,
    AVG(t.checkpoint_count) as avg_checkpoints_per_thread,
    MAX(t.last_activity_at) as last_activity,
    AVG(a.response_time_ms) as avg_response_time_ms
FROM langgraph_threads t
LEFT JOIN langgraph_thread_access a ON t.id = a.thread_id
GROUP BY t.user_id;

CREATE OR REPLACE VIEW langgraph_checkpoint_performance AS
SELECT 
    DATE_TRUNC('day', created_at) as date,
    COUNT(*) as checkpoint_count,
    AVG(state_size_bytes) as avg_size_bytes,
    COUNT(CASE WHEN checkpoint_type = 'full' THEN 1 END) as full_checkpoints,
    COUNT(CASE WHEN checkpoint_type = 'delta' THEN 1 END) as delta_checkpoints,
    AVG(CASE WHEN checkpoint_type = 'full' THEN state_size_bytes END) as avg_full_size,
    AVG(CASE WHEN checkpoint_type = 'delta' THEN state_size_bytes END) as avg_delta_size
FROM langgraph_checkpoints
GROUP BY DATE_TRUNC('day', created_at);

-- ============================================================================
-- TRIGGERS
-- ============================================================================

-- Update thread stats on checkpoint creation
CREATE OR REPLACE FUNCTION update_thread_checkpoint_stats()
RETURNS TRIGGER AS $$
BEGIN
    UPDATE langgraph_threads
    SET checkpoint_count = checkpoint_count + 1,
        last_checkpoint_id = NEW.id,
        last_checkpoint_at = NEW.created_at,
        last_activity_at = NOW()
    WHERE id = NEW.thread_id;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trigger_update_thread_checkpoint_stats
    AFTER INSERT ON langgraph_checkpoints
    FOR EACH ROW
    EXECUTE FUNCTION update_thread_checkpoint_stats();

-- Update updated_at timestamp
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER update_langgraph_threads_updated_at
    BEFORE UPDATE ON langgraph_threads
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- ============================================================================
-- GRANT PERMISSIONS (for Supabase service role)
-- ============================================================================

GRANT ALL ON ALL TABLES IN SCHEMA public TO service_role;
GRANT ALL ON ALL SEQUENCES IN SCHEMA public TO service_role;
GRANT ALL ON ALL FUNCTIONS IN SCHEMA public TO service_role;