-- Migration: FeedMe v2.0 Phase 2 Database Optimization
-- This migration implements advanced optimization features including:
-- 1. Table partitioning for scalability
-- 2. Enhanced indexing strategies
-- 3. Materialized views for analytics
-- 4. Approval workflow tables

-- =====================================================
-- SECTION 1: ENHANCED SCHEMA WITH PARTITIONING
-- =====================================================

-- 1. Create enhanced conversations table with partitioning
CREATE TABLE IF NOT EXISTS feedme_conversations_v2 (
    id BIGSERIAL,
    uuid UUID DEFAULT uuid_generate_v4(),
    title TEXT NOT NULL,
    
    -- Enhanced metadata
    platform VARCHAR(50),
    ticket_id VARCHAR(255),
    customer_id VARCHAR(255),
    
    -- File management
    original_filename TEXT,
    raw_transcript TEXT NOT NULL,
    parsed_content TEXT,
    
    -- Processing tracking with enhanced stages
    processing_status VARCHAR(20) DEFAULT 'pending' 
        CHECK (processing_status IN ('pending', 'processing', 'completed', 'failed', 'cancelled')),
    processing_stages JSONB DEFAULT '{}',
    extraction_stats JSONB DEFAULT '{}',
    
    -- Folder organization
    folder_id BIGINT,
    folder_path TEXT[],  -- Hierarchical path
    
    -- Quality metrics
    extraction_quality_score FLOAT DEFAULT 0.0,
    total_examples INTEGER DEFAULT 0,
    approved_examples INTEGER DEFAULT 0,
    
    -- Versioning support
    version INTEGER DEFAULT 1,
    version_history JSONB DEFAULT '[]',
    
    -- Performance optimization fields
    word_count INTEGER,
    message_count INTEGER,
    processing_time_ms INTEGER,
    
    -- User tracking
    uploaded_by TEXT,
    processed_by TEXT,
    
    -- Timestamps
    uploaded_at TIMESTAMPTZ DEFAULT NOW(),
    processed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    
    PRIMARY KEY (id, created_at)
) PARTITION BY RANGE (created_at);

-- Create monthly partitions for current and future periods
CREATE TABLE IF NOT EXISTS feedme_conversations_v2_2024_01 
    PARTITION OF feedme_conversations_v2
    FOR VALUES FROM ('2024-01-01') TO ('2024-02-01');

CREATE TABLE IF NOT EXISTS feedme_conversations_v2_2024_02
    PARTITION OF feedme_conversations_v2
    FOR VALUES FROM ('2024-02-01') TO ('2024-03-01');

CREATE TABLE IF NOT EXISTS feedme_conversations_v2_2024_03
    PARTITION OF feedme_conversations_v2
    FOR VALUES FROM ('2024-03-01') TO ('2024-04-01');

-- Add partitions for next 6 months (can be automated in production)
CREATE TABLE IF NOT EXISTS feedme_conversations_v2_2024_04
    PARTITION OF feedme_conversations_v2
    FOR VALUES FROM ('2024-04-01') TO ('2024-05-01');

CREATE TABLE IF NOT EXISTS feedme_conversations_v2_2024_05
    PARTITION OF feedme_conversations_v2
    FOR VALUES FROM ('2024-05-01') TO ('2024-06-01');

CREATE TABLE IF NOT EXISTS feedme_conversations_v2_2024_06
    PARTITION OF feedme_conversations_v2
    FOR VALUES FROM ('2024-06-01') TO ('2024-07-01');

-- 2. Enhanced examples table with optimized structure
CREATE TABLE IF NOT EXISTS feedme_examples_v2 (
    id BIGSERIAL PRIMARY KEY,
    conversation_id BIGINT NOT NULL,
    
    -- Core content
    question_text TEXT NOT NULL,
    answer_text TEXT NOT NULL,
    context_before TEXT,
    context_after TEXT,
    
    -- Optimized embeddings (384 dimensions for performance)
    question_embedding VECTOR(384),
    answer_embedding VECTOR(384),
    combined_embedding VECTOR(384),
    
    -- Enhanced categorization
    issue_category VARCHAR(50),
    product_area VARCHAR(50),
    complexity_level INTEGER CHECK (complexity_level BETWEEN 1 AND 5),
    urgency_level VARCHAR(20) DEFAULT 'medium',
    
    -- Quality metrics with granular scoring
    confidence_score FLOAT CHECK (confidence_score >= 0 AND confidence_score <= 1),
    usefulness_score FLOAT CHECK (usefulness_score >= 0 AND usefulness_score <= 1),
    clarity_score FLOAT CHECK (clarity_score >= 0 AND clarity_score <= 1),
    completeness_score FLOAT CHECK (completeness_score >= 0 AND completeness_score <= 1),
    overall_quality_score FLOAT GENERATED ALWAYS AS (
        (COALESCE(confidence_score, 0) + COALESCE(usefulness_score, 0) + 
         COALESCE(clarity_score, 0) + COALESCE(completeness_score, 0)) / 4.0
    ) STORED,
    
    -- Usage analytics
    usage_count INTEGER DEFAULT 0,
    last_used_at TIMESTAMPTZ,
    positive_feedback INTEGER DEFAULT 0,
    negative_feedback INTEGER DEFAULT 0,
    feedback_score FLOAT GENERATED ALWAYS AS (
        CASE 
            WHEN (positive_feedback + negative_feedback) > 0 
            THEN positive_feedback::FLOAT / (positive_feedback + negative_feedback)
            ELSE 0.5
        END
    ) STORED,
    
    -- Search optimization
    search_text tsvector GENERATED ALWAYS AS (
        to_tsvector('english', COALESCE(question_text, '') || ' ' || COALESCE(answer_text, ''))
    ) STORED,
    
    -- Tags and metadata
    tags TEXT[],
    metadata JSONB DEFAULT '{}',
    
    -- Status and lifecycle
    is_active BOOLEAN DEFAULT true,
    approval_status VARCHAR(20) DEFAULT 'auto_approved',
    reviewed_by TEXT,
    reviewed_at TIMESTAMPTZ,
    
    -- Timestamps
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- =====================================================
-- SECTION 2: APPROVAL WORKFLOW TABLES
-- =====================================================

-- Temporary examples table for approval workflow
CREATE TABLE IF NOT EXISTS feedme_temp_examples (
    id BIGSERIAL PRIMARY KEY,
    conversation_id BIGINT NOT NULL,
    
    -- Same content structure as main examples table
    question_text TEXT NOT NULL,
    answer_text TEXT NOT NULL,
    context_before TEXT,
    context_after TEXT,
    
    -- Embeddings for similarity during review
    question_embedding VECTOR(384),
    answer_embedding VECTOR(384),
    combined_embedding VECTOR(384),
    
    -- Extraction metadata
    extraction_method VARCHAR(20) DEFAULT 'ai',
    extraction_confidence FLOAT,
    ai_model_used VARCHAR(50),
    extraction_timestamp TIMESTAMPTZ DEFAULT NOW(),
    
    -- Approval workflow fields
    approval_status VARCHAR(20) DEFAULT 'pending' 
        CHECK (approval_status IN ('pending', 'approved', 'rejected', 'revision_requested')),
    assigned_reviewer TEXT,
    priority VARCHAR(10) DEFAULT 'normal' 
        CHECK (priority IN ('low', 'normal', 'high', 'urgent')),
    
    -- Review information
    review_notes TEXT,
    rejection_reason VARCHAR(100),
    revision_instructions TEXT,
    reviewer_id TEXT,
    reviewed_at TIMESTAMPTZ,
    
    -- Quality assessment during review
    reviewer_confidence_score FLOAT,
    reviewer_usefulness_score FLOAT,
    
    -- Auto-approval logic
    auto_approved BOOLEAN DEFAULT false,
    auto_approval_reason VARCHAR(100),
    
    -- Timestamps
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Review history table for audit trail
CREATE TABLE IF NOT EXISTS feedme_review_history (
    id BIGSERIAL PRIMARY KEY,
    temp_example_id BIGINT NOT NULL REFERENCES feedme_temp_examples(id),
    reviewer_id TEXT NOT NULL,
    action VARCHAR(20) NOT NULL 
        CHECK (action IN ('approved', 'rejected', 'revision_requested', 'reassigned')),
    
    -- Review details
    review_notes TEXT,
    confidence_assessment FLOAT,
    time_spent_minutes INTEGER,
    
    -- Before/after states for change tracking
    previous_status VARCHAR(20),
    new_status VARCHAR(20),
    changes_made JSONB,
    
    -- Timestamps
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- =====================================================
-- SECTION 3: ADVANCED INDEXING STRATEGIES
-- =====================================================

-- Conversation table indexes
CREATE INDEX IF NOT EXISTS idx_conversations_v2_status_date 
    ON feedme_conversations_v2 (processing_status, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_conversations_v2_platform_date
    ON feedme_conversations_v2 (platform, created_at DESC) 
    WHERE platform IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_conversations_v2_folder_path
    ON feedme_conversations_v2 USING GIN (folder_path);

CREATE INDEX IF NOT EXISTS idx_conversations_v2_extraction_quality
    ON feedme_conversations_v2 (extraction_quality_score DESC)
    WHERE extraction_quality_score IS NOT NULL;

-- Enhanced examples table indexes for performance
CREATE INDEX IF NOT EXISTS idx_examples_v2_search_text 
    ON feedme_examples_v2 USING gin(search_text);

CREATE INDEX IF NOT EXISTS idx_examples_v2_category_quality
    ON feedme_examples_v2 (issue_category, overall_quality_score DESC)
    WHERE is_active = true;

CREATE INDEX IF NOT EXISTS idx_examples_v2_composite_scores
    ON feedme_examples_v2 (confidence_score DESC, usefulness_score DESC, feedback_score DESC)
    WHERE is_active = true;

CREATE INDEX IF NOT EXISTS idx_examples_v2_usage_analytics
    ON feedme_examples_v2 (usage_count DESC, last_used_at DESC)
    WHERE is_active = true;

CREATE INDEX IF NOT EXISTS idx_examples_v2_tags
    ON feedme_examples_v2 USING gin(tags);

-- Vector similarity indexes with optimal configuration for 384-dimensional embeddings
CREATE INDEX IF NOT EXISTS idx_examples_v2_question_embedding
    ON feedme_examples_v2 USING ivfflat (question_embedding vector_cosine_ops) 
    WITH (lists = 200);

CREATE INDEX IF NOT EXISTS idx_examples_v2_answer_embedding
    ON feedme_examples_v2 USING ivfflat (answer_embedding vector_cosine_ops) 
    WITH (lists = 200);

CREATE INDEX IF NOT EXISTS idx_examples_v2_combined_embedding
    ON feedme_examples_v2 USING ivfflat (combined_embedding vector_cosine_ops) 
    WITH (lists = 200);

-- Approval workflow indexes
CREATE INDEX IF NOT EXISTS idx_temp_examples_approval_status
    ON feedme_temp_examples (approval_status, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_temp_examples_assigned_reviewer
    ON feedme_temp_examples (assigned_reviewer, priority, created_at DESC)
    WHERE approval_status = 'pending';

CREATE INDEX IF NOT EXISTS idx_temp_examples_auto_approval
    ON feedme_temp_examples (extraction_confidence DESC, created_at DESC)
    WHERE auto_approved = false AND approval_status = 'pending';

CREATE INDEX IF NOT EXISTS idx_review_history_reviewer_action
    ON feedme_review_history (reviewer_id, action, created_at DESC);

-- =====================================================
-- SECTION 4: MATERIALIZED VIEWS FOR ANALYTICS
-- =====================================================

-- Analytics dashboard materialized view
CREATE MATERIALIZED VIEW IF NOT EXISTS feedme_analytics_dashboard AS
SELECT 
    DATE_TRUNC('day', created_at) as date,
    COUNT(*) as total_conversations,
    SUM(total_examples) as total_examples_extracted,
    AVG(extraction_quality_score) as avg_extraction_quality,
    AVG(processing_time_ms::FLOAT) as avg_processing_time_ms,
    COUNT(*) FILTER (WHERE processing_status = 'completed') as successful_extractions,
    COUNT(*) FILTER (WHERE processing_status = 'failed') as failed_extractions,
    AVG(word_count::FLOAT) as avg_word_count,
    AVG(message_count::FLOAT) as avg_message_count,
    COUNT(DISTINCT platform) as platforms_used
FROM feedme_conversations_v2
WHERE created_at >= NOW() - INTERVAL '90 days'
GROUP BY DATE_TRUNC('day', created_at)
ORDER BY date DESC
WITH DATA;

-- Quality metrics materialized view
CREATE MATERIALIZED VIEW IF NOT EXISTS feedme_quality_metrics AS
SELECT 
    issue_category,
    COUNT(*) as total_examples,
    AVG(overall_quality_score) as avg_quality_score,
    AVG(confidence_score) as avg_confidence,
    AVG(usefulness_score) as avg_usefulness,
    AVG(feedback_score) as avg_feedback,
    SUM(usage_count) as total_usage,
    COUNT(*) FILTER (WHERE overall_quality_score >= 0.8) as high_quality_count,
    COUNT(*) FILTER (WHERE feedback_score >= 0.7) as positive_feedback_count
FROM feedme_examples_v2
WHERE is_active = true
  AND created_at >= NOW() - INTERVAL '30 days'
GROUP BY issue_category
ORDER BY total_examples DESC
WITH DATA;

-- Approval workflow metrics view
CREATE MATERIALIZED VIEW IF NOT EXISTS feedme_approval_metrics AS
SELECT 
    DATE_TRUNC('day', created_at) as date,
    COUNT(*) as total_submissions,
    COUNT(*) FILTER (WHERE approval_status = 'approved') as approved_count,
    COUNT(*) FILTER (WHERE approval_status = 'rejected') as rejected_count,
    COUNT(*) FILTER (WHERE auto_approved = true) as auto_approved_count,
    AVG(EXTRACT(EPOCH FROM (reviewed_at - created_at))/3600.0) as avg_review_time_hours,
    COUNT(DISTINCT assigned_reviewer) as active_reviewers
FROM feedme_temp_examples
WHERE created_at >= NOW() - INTERVAL '30 days'
GROUP BY DATE_TRUNC('day', created_at)
ORDER BY date DESC
WITH DATA;

-- Create unique indexes on materialized views
CREATE UNIQUE INDEX IF NOT EXISTS idx_analytics_dashboard_date 
    ON feedme_analytics_dashboard (date);

CREATE UNIQUE INDEX IF NOT EXISTS idx_quality_metrics_category
    ON feedme_quality_metrics (issue_category);

CREATE UNIQUE INDEX IF NOT EXISTS idx_approval_metrics_date
    ON feedme_approval_metrics (date);

-- =====================================================
-- SECTION 5: PERFORMANCE OPTIMIZATION FUNCTIONS
-- =====================================================

-- Function to refresh materialized views
CREATE OR REPLACE FUNCTION refresh_feedme_analytics()
RETURNS void AS $$
BEGIN
    REFRESH MATERIALIZED VIEW CONCURRENTLY feedme_analytics_dashboard;
    REFRESH MATERIALIZED VIEW CONCURRENTLY feedme_quality_metrics;
    REFRESH MATERIALIZED VIEW CONCURRENTLY feedme_approval_metrics;
END;
$$ LANGUAGE plpgsql;

-- Function to optimize vector search performance
CREATE OR REPLACE FUNCTION optimize_vector_search()
RETURNS void AS $$
BEGIN
    -- Reindex vector indexes for optimal performance
    REINDEX INDEX CONCURRENTLY idx_examples_v2_question_embedding;
    REINDEX INDEX CONCURRENTLY idx_examples_v2_answer_embedding;
    REINDEX INDEX CONCURRENTLY idx_examples_v2_combined_embedding;
    
    -- Update statistics for better query planning
    ANALYZE feedme_examples_v2;
END;
$$ LANGUAGE plpgsql;

-- Function to auto-create partitions
CREATE OR REPLACE FUNCTION create_monthly_partition(partition_date DATE)
RETURNS void AS $$
DECLARE
    partition_name TEXT;
    start_date DATE;
    end_date DATE;
BEGIN
    -- Calculate partition boundaries
    start_date := DATE_TRUNC('month', partition_date);
    end_date := start_date + INTERVAL '1 month';
    
    -- Generate partition name
    partition_name := 'feedme_conversations_v2_' || TO_CHAR(start_date, 'YYYY_MM');
    
    -- Create partition
    EXECUTE format(
        'CREATE TABLE IF NOT EXISTS %I PARTITION OF feedme_conversations_v2 
         FOR VALUES FROM (%L) TO (%L)',
        partition_name, start_date, end_date
    );
END;
$$ LANGUAGE plpgsql;

-- =====================================================
-- SECTION 6: TRIGGERS AND AUTOMATION
-- =====================================================

-- Enhanced updated_at trigger function
CREATE OR REPLACE FUNCTION update_feedme_updated_at_v2()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    
    -- Auto-update version history for conversations
    IF TG_TABLE_NAME = 'feedme_conversations_v2' AND OLD.version != NEW.version THEN
        NEW.version_history = COALESCE(OLD.version_history, '[]'::jsonb) || 
            jsonb_build_object(
                'version', OLD.version,
                'updated_at', OLD.updated_at,
                'updated_by', NEW.processed_by
            );
    END IF;
    
    RETURN NEW;
END;
$$ language 'plpgsql';

-- Apply triggers to new tables
CREATE TRIGGER trigger_conversations_v2_updated_at
    BEFORE UPDATE ON feedme_conversations_v2
    FOR EACH ROW
    EXECUTE FUNCTION update_feedme_updated_at_v2();

CREATE TRIGGER trigger_examples_v2_updated_at
    BEFORE UPDATE ON feedme_examples_v2
    FOR EACH ROW
    EXECUTE FUNCTION update_feedme_updated_at();

CREATE TRIGGER trigger_temp_examples_updated_at
    BEFORE UPDATE ON feedme_temp_examples
    FOR EACH ROW
    EXECUTE FUNCTION update_feedme_updated_at();

-- =====================================================
-- SECTION 7: DATA MIGRATION AND COMPATIBILITY
-- =====================================================

-- Create migration function to move data from v1 to v2 tables
CREATE OR REPLACE FUNCTION migrate_feedme_v1_to_v2()
RETURNS TABLE(migrated_conversations INT, migrated_examples INT) AS $$
DECLARE
    conv_count INT := 0;
    example_count INT := 0;
BEGIN
    -- Migrate conversations
    INSERT INTO feedme_conversations_v2 (
        id, title, original_filename, raw_transcript, parsed_content,
        metadata, uploaded_by, uploaded_at, processed_at, processing_status,
        total_examples, created_at, updated_at
    )
    SELECT 
        id, title, original_filename, raw_transcript, parsed_content,
        metadata, uploaded_by, uploaded_at, processed_at, processing_status,
        total_examples, created_at, updated_at
    FROM feedme_conversations
    WHERE NOT EXISTS (
        SELECT 1 FROM feedme_conversations_v2 WHERE feedme_conversations_v2.id = feedme_conversations.id
    );
    
    GET DIAGNOSTICS conv_count = ROW_COUNT;
    
    -- Migrate examples
    INSERT INTO feedme_examples_v2 (
        id, conversation_id, question_text, answer_text, context_before, context_after,
        question_embedding, answer_embedding, combined_embedding, tags, issue_type,
        confidence_score, usefulness_score, is_active, created_at, updated_at
    )
    SELECT 
        id, conversation_id, question_text, answer_text, context_before, context_after,
        question_embedding, answer_embedding, combined_embedding, tags, issue_type,
        confidence_score, usefulness_score, is_active, created_at, updated_at
    FROM feedme_examples
    WHERE NOT EXISTS (
        SELECT 1 FROM feedme_examples_v2 WHERE feedme_examples_v2.id = feedme_examples.id
    );
    
    GET DIAGNOSTICS example_count = ROW_COUNT;
    
    RETURN QUERY SELECT conv_count, example_count;
END;
$$ LANGUAGE plpgsql;

-- =====================================================
-- SECTION 8: PERFORMANCE MONITORING
-- =====================================================

-- View for monitoring query performance
CREATE OR REPLACE VIEW feedme_query_performance AS
SELECT 
    query,
    calls,
    total_time,
    mean_time,
    min_time,
    max_time,
    stddev_time
FROM pg_stat_statements 
WHERE query LIKE '%feedme_%'
ORDER BY total_time DESC;

-- Function to get table statistics
CREATE OR REPLACE FUNCTION get_feedme_table_stats()
RETURNS TABLE(
    table_name TEXT,
    row_count BIGINT,
    table_size TEXT,
    index_size TEXT,
    total_size TEXT
) AS $$
BEGIN
    RETURN QUERY
    SELECT 
        t.table_name::TEXT,
        t.n_tup_ins - t.n_tup_del as row_count,
        pg_size_pretty(pg_total_relation_size(t.schemaname||'.'||t.tablename)) as table_size,
        pg_size_pretty(pg_indexes_size(t.schemaname||'.'||t.tablename)) as index_size,
        pg_size_pretty(pg_total_relation_size(t.schemaname||'.'||t.tablename) + 
                      pg_indexes_size(t.schemaname||'.'||t.tablename)) as total_size
    FROM pg_stat_user_tables t
    WHERE t.tablename LIKE 'feedme_%'
    ORDER BY pg_total_relation_size(t.schemaname||'.'||t.tablename) DESC;
END;
$$ LANGUAGE plpgsql;

-- =====================================================
-- SECTION 9: CLEANUP AND MAINTENANCE
-- =====================================================

-- Function to cleanup old partitions
CREATE OR REPLACE FUNCTION cleanup_old_partitions(retention_months INTEGER DEFAULT 12)
RETURNS void AS $$
DECLARE
    partition_record RECORD;
    cutoff_date DATE;
BEGIN
    cutoff_date := DATE_TRUNC('month', NOW() - (retention_months || ' months')::INTERVAL);
    
    FOR partition_record IN 
        SELECT tablename 
        FROM pg_tables 
        WHERE tablename LIKE 'feedme_conversations_v2_%'
          AND schemaname = 'public'
    LOOP
        -- Extract date from partition name and check if it's old enough
        DECLARE
            partition_date DATE;
        BEGIN
            partition_date := TO_DATE(
                SUBSTRING(partition_record.tablename FROM 'feedme_conversations_v2_(.*)'), 
                'YYYY_MM'
            );
            
            IF partition_date < cutoff_date THEN
                EXECUTE 'DROP TABLE IF EXISTS ' || partition_record.tablename;
                RAISE NOTICE 'Dropped old partition: %', partition_record.tablename;
            END IF;
        EXCEPTION
            WHEN OTHERS THEN
                RAISE NOTICE 'Could not process partition: %', partition_record.tablename;
        END;
    END LOOP;
END;
$$ LANGUAGE plpgsql;

-- Schedule automatic maintenance (requires pg_cron extension)
-- SELECT cron.schedule('refresh-feedme-analytics', '0 */6 * * *', 'SELECT refresh_feedme_analytics();');
-- SELECT cron.schedule('optimize-feedme-vectors', '0 2 * * 0', 'SELECT optimize_vector_search();');

-- =====================================================
-- FINAL NOTES AND VALIDATION
-- =====================================================

-- Validate migration
DO $$
BEGIN
    -- Check if tables exist
    IF NOT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'feedme_conversations_v2') THEN
        RAISE EXCEPTION 'feedme_conversations_v2 table was not created';
    END IF;
    
    IF NOT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'feedme_examples_v2') THEN
        RAISE EXCEPTION 'feedme_examples_v2 table was not created';
    END IF;
    
    -- Check if indexes exist
    IF NOT EXISTS (SELECT 1 FROM pg_indexes WHERE indexname = 'idx_examples_v2_combined_embedding') THEN
        RAISE EXCEPTION 'Vector indexes were not created properly';
    END IF;
    
    RAISE NOTICE 'FeedMe v2.0 Phase 2 database optimization completed successfully!';
END $$;