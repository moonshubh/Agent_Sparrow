-- Migration: Fix memory system vector dimension error
-- Issue: HNSW index has 2000 dimension limit, but gemini-embedding-001 uses 3072
-- Solution: Switch to IVFFlat index which has no dimension limit

-- Drop existing HNSW index attempts if they exist (they likely failed, but be safe)
DO $$
BEGIN
    -- Drop any HNSW indexes on mem_primary collection
    EXECUTE 'DROP INDEX IF EXISTS vecs.ix_vector_cosine_ops_hnsw_m16_efc64_ed5fad8 CASCADE';

    -- Drop any HNSW indexes on mem_logs collection
    EXECUTE 'DROP INDEX IF EXISTS vecs.ix_vector_cosine_ops_hnsw_m16_efc64_ed5fad8_logs CASCADE';

    -- Drop any other potential HNSW indexes in vecs schema
    FOR r IN
        SELECT indexname
        FROM pg_indexes
        WHERE schemaname = 'vecs'
        AND indexdef LIKE '%hnsw%'
        AND tablename IN ('mem_primary', 'mem_logs')
    LOOP
        EXECUTE 'DROP INDEX IF EXISTS vecs.' || r.indexname || ' CASCADE';
    END LOOP;
EXCEPTION
    WHEN OTHERS THEN
        -- If any errors occur (e.g., schema doesn't exist), continue
        RAISE NOTICE 'Some indexes could not be dropped: %', SQLERRM;
END $$;

-- Note: mem0 will automatically create IVFFlat index on next startup
-- The index_method is now configured in app/memory/service.py

-- If you need to manually create the index, use:
-- CREATE INDEX ON vecs.mem_primary USING ivfflat (vec vector_cosine_ops) WITH (lists = 100);
-- CREATE INDEX ON vecs.mem_logs USING ivfflat (vec vector_cosine_ops) WITH (lists = 100);

-- Log completion
DO $$
BEGIN
    RAISE NOTICE 'Migration 036 completed: Switched from HNSW to IVFFlat for 3072-dimensional vectors';
END $$;