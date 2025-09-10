-- Migration: Change vector dimensions to 3072 for FeedMe embeddings
-- Context: If you switch to Google's text-embedding-004 (3072-dim),
-- you must update pgvector columns to match. This script performs a safe
-- zero-downtime-ish migration by adding a new column, then swapping.

-- Notes:
-- - Run in Supabase SQL editor or psql against your project DB.
-- - Backfill of existing vectors is not attempted (kept NULL).
-- - Recreate IVFFlat cosine index for the new column.

begin;

-- feedme_text_chunks.embedding -> vector(3072)
-- Drop dependent index if it exists
drop index if exists feedme_text_chunks_embedding_idx;

-- Add new column with desired dimension
alter table public.feedme_text_chunks add column embedding_new vector(3072);

-- Optional: copy existing data if already 3072-dim stored as array text (not typical)
-- update public.feedme_text_chunks set embedding_new = embedding where embedding is not null;

-- Swap columns
alter table public.feedme_text_chunks drop column embedding;
alter table public.feedme_text_chunks rename column embedding_new to embedding;

-- Recreate IVFFlat index (cosine distance). Adjust lists to your dataset size.
create index feedme_text_chunks_embedding_idx on public.feedme_text_chunks using ivfflat (embedding vector_cosine_ops) with (lists = 100);

-- If you also store embeddings in knowledge base, update that table too.
-- mailbird_knowledge.embedding -> vector(3072)
do $$
begin
  if exists (
    select 1 from information_schema.columns
    where table_schema = 'public' and table_name = 'mailbird_knowledge' and column_name = 'embedding'
  ) then
    -- drop possible index
    execute 'drop index if exists mailbird_knowledge_embedding_idx';

    -- add new column, swap
    execute 'alter table public.mailbird_knowledge add column embedding_new vector(3072)';
    execute 'alter table public.mailbird_knowledge drop column embedding';
    execute 'alter table public.mailbird_knowledge rename column embedding_new to embedding';
    -- recreate index
    execute 'create index mailbird_knowledge_embedding_idx on public.mailbird_knowledge using ivfflat (embedding vector_cosine_ops) with (lists = 100)';
  end if;
end $$;

commit;

-- Rollback (manual): restore from backup or change type back to vector(768)

