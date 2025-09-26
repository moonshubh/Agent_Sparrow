-- Migration: FeedMe Text Chunks for Embeddings
-- Date: 2025-09-08

-- Ensure pgvector extension exists
CREATE EXTENSION IF NOT EXISTS vector;

-- Create chunks table
CREATE TABLE IF NOT EXISTS feedme_text_chunks (
  id BIGSERIAL PRIMARY KEY,
  conversation_id BIGINT NOT NULL REFERENCES feedme_conversations(id) ON DELETE CASCADE,
  folder_id BIGINT NULL,
  chunk_index INT NOT NULL,
  content TEXT NOT NULL,
  embedding VECTOR(768),
  metadata JSONB DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_feedme_text_chunks_conversation ON feedme_text_chunks(conversation_id, chunk_index);

-- Optional: IVF Flat index for similarity search (requires appropriate distance ops)
-- CREATE INDEX IF NOT EXISTS idx_feedme_text_chunks_embedding ON feedme_text_chunks USING ivfflat (embedding vector_l2_ops) WITH (lists = 100);

-- Trigger to update updated_at
CREATE OR REPLACE FUNCTION set_updated_at_timestamp() RETURNS TRIGGER AS $$
BEGIN
  NEW.updated_at = NOW();
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_feedme_text_chunks_updated_at ON feedme_text_chunks;
CREATE TRIGGER trg_feedme_text_chunks_updated_at
BEFORE UPDATE ON feedme_text_chunks
FOR EACH ROW EXECUTE PROCEDURE set_updated_at_timestamp();

-- RPC: search chunks by embedding using L2 distance
CREATE OR REPLACE FUNCTION search_feedme_text_chunks(
  query_embedding vector(768),
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
