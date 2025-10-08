-- Migration: Migrate embeddings to 3072 dims (Gemini embedding-001)
-- Applies to: mailbird_knowledge, feedme_text_chunks, and related search RPCs
-- Notes:
-- - Requires pgvector extension
-- - Rebuilds vector indexes

-- Ensure pgvector
CREATE EXTENSION IF NOT EXISTS vector;

-- 1) Mailbird knowledge base: VECTOR(3072)
-- Drop existing index if any
DROP INDEX IF EXISTS idx_mailbird_knowledge_embedding;

-- Clear incompatible embeddings to avoid typmod conversion issues
UPDATE mailbird_knowledge SET embedding = NULL WHERE embedding IS NOT NULL;

-- Alter column to 3072 dims
ALTER TABLE mailbird_knowledge ALTER COLUMN embedding TYPE vector(3072);

-- Re-create vector index using cosine distance
CREATE INDEX IF NOT EXISTS idx_mailbird_knowledge_embedding
  ON mailbird_knowledge USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);


-- 2) FeedMe text chunks: VECTOR(3072)
-- Create table if not present (no-op if exists)
CREATE TABLE IF NOT EXISTS feedme_text_chunks (
  id BIGSERIAL PRIMARY KEY,
  conversation_id BIGINT NOT NULL,
  folder_id BIGINT NULL,
  chunk_index INT NOT NULL,
  content TEXT NOT NULL,
  embedding VECTOR(3072),
  metadata JSONB DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Null out incompatible embeddings then alter typmod
UPDATE feedme_text_chunks SET embedding = NULL WHERE embedding IS NOT NULL;
ALTER TABLE feedme_text_chunks ALTER COLUMN embedding TYPE vector(3072);

-- Optional performance index for similarity search
DROP INDEX IF EXISTS idx_feedme_text_chunks_embedding;
CREATE INDEX IF NOT EXISTS idx_feedme_text_chunks_embedding
  ON feedme_text_chunks USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);

-- Update RPC to accept 3072-dim vector
DROP FUNCTION IF EXISTS search_feedme_text_chunks(vector, integer, bigint);
CREATE OR REPLACE FUNCTION search_feedme_text_chunks(
  query_embedding vector(3072),
  match_count integer DEFAULT 10,
  filter_folder_id BIGINT DEFAULT NULL
)
RETURNS TABLE (
  id BIGINT,
  conversation_id BIGINT,
  chunk_index INT,
  content TEXT,
  similarity DOUBLE PRECISION
) AS $$
  SELECT c.id, c.conversation_id, c.chunk_index, c.content,
         1 - (c.embedding <=> query_embedding) AS similarity
  FROM feedme_text_chunks c
  WHERE c.embedding IS NOT NULL
    AND (filter_folder_id IS NULL OR c.folder_id = filter_folder_id)
  ORDER BY c.embedding <-> query_embedding
  LIMIT match_count;
$$ LANGUAGE SQL STABLE;


-- 3) Validation notices (best-effort, non-fatal)
DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM information_schema.columns 
    WHERE table_name = 'mailbird_knowledge' AND column_name = 'embedding'
  ) THEN
    RAISE EXCEPTION 'mailbird_knowledge.embedding column not found';
  END IF;
  RAISE NOTICE 'Embeddings migrated to 3072 dims; rebuild of indexes completed.';
END $$;
