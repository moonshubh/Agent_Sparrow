-- Ensure RLS is enabled and vector indexes exist for performant, secure searches

-- Enable RLS (idempotent)
alter table if exists public.feedme_conversations enable row level security;
alter table if exists public.feedme_text_chunks enable row level security;
alter table if exists public.web_research_snapshots enable row level security;

-- Optional: tighten EXECUTE privileges can be handled separately if needed

-- Create IVFFlat indexes for vector columns (if not already present)
-- Requires pgvector extension installed
create index if not exists idx_feedme_text_chunks_embedding_ivfflat
  on public.feedme_text_chunks using ivfflat (embedding vector_cosine_ops) with (lists = 100);

create index if not exists idx_web_research_snapshots_embedding_ivfflat
  on public.web_research_snapshots using ivfflat (embedding vector_cosine_ops) with (lists = 100);
