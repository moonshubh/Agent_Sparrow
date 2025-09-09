-- Migration: Create mailbird_knowledge table with pgvector embedding column
-- Run this script once against your PostgreSQL database after enabling the
-- pgvector extension (CREATE EXTENSION IF NOT EXISTS pgvector;)

-- 1. Ensure the pgvector extension is installed (Postgres ≥ 13)
CREATE EXTENSION IF NOT EXISTS pgvector;

-- 2. Main knowledge base table
CREATE TABLE IF NOT EXISTS mailbird_knowledge (
    id           BIGSERIAL PRIMARY KEY,
    url          TEXT        NOT NULL UNIQUE,
    content      TEXT,                    -- Raw HTML/plain text fallback
    markdown     TEXT,                    -- Preferred cleaned markdown from Firecrawl
    scraped_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    embedding    VECTOR(768),             -- Embedding from Google embedding-001 (768 dims)
    metadata     JSONB                    -- Arbitrary metadata (e.g., title, author)
);

-- 3. Vector index for efficient similarity search (cosine distance)
-- NOTE: Adjust `lists` based on data scale; 100 is a reasonable starting point.
CREATE INDEX IF NOT EXISTS idx_mailbird_knowledge_embedding
    ON mailbird_knowledge USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);

-- 4. Auxiliary index to speed up look-ups by URL (optional, UNIQUE already helps)
CREATE INDEX IF NOT EXISTS idx_mailbird_knowledge_url ON mailbird_knowledge (url);
