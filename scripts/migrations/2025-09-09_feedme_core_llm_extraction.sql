-- FeedMe Core Schema for LLM-based PDF Extraction (Markdown)
-- Safe to run multiple times; uses IF EXISTS/IF NOT EXISTS.

-- Extensions required
create extension if not exists pgcrypto; -- for gen_random_uuid()
create extension if not exists vector;   -- pgvector for embeddings

-- ============================================================
-- FOLDERS
-- ============================================================
create table if not exists public.feedme_folders (
  id            bigserial primary key,
  uuid          uuid not null default gen_random_uuid(),
  name          text not null,
  color         text not null default '#0095ff',
  description   text,
  created_by    text,
  created_at    timestamptz not null default now(),
  updated_at    timestamptz not null default now()
);

-- ============================================================
-- CONVERSATIONS (Markdown extraction)
-- ============================================================
create table if not exists public.feedme_conversations (
  id                   bigserial primary key,
  uuid                 uuid not null default gen_random_uuid(),
  title                text not null,
  original_filename    text,
  raw_transcript       text,                  -- base64 PDF payload (nullable after cleanup)
  extracted_text       text,                  -- Markdown
  processing_method    text,                  -- 'pdf_ai', 'manual_text', 'text_paste', 'pdf_ocr'
  extraction_confidence double precision,
  processing_status    text not null default 'pending',
  processed_at         timestamptz,
  processing_time_ms   integer,
  error_message        text,
  approval_status      text not null default 'pending',
  approved_by          text,
  approved_at          timestamptz,
  uploaded_by          text,
  mime_type            text,
  pages                integer,
  pdf_metadata         jsonb,
  metadata             jsonb not null default '{}'::jsonb,
  folder_id            bigint references public.feedme_folders(id) on delete set null,
  pdf_cleaned          boolean not null default false,
  pdf_cleaned_at       timestamptz,
  original_pdf_size    bigint,
  created_at           timestamptz not null default now(),
  updated_at           timestamptz not null default now()
);

create index if not exists idx_feedme_conversations_folder_id on public.feedme_conversations(folder_id);
create index if not exists idx_feedme_conversations_processing_status on public.feedme_conversations(processing_status);
create index if not exists idx_feedme_conversations_approval_status on public.feedme_conversations(approval_status);
create index if not exists idx_feedme_conversations_created_at on public.feedme_conversations(created_at);

-- ============================================================
-- TEXT CHUNKS + EMBEDDINGS (unified text retrieval)
-- ============================================================
create table if not exists public.feedme_text_chunks (
  id              bigserial primary key,
  conversation_id bigint not null references public.feedme_conversations(id) on delete cascade,
  folder_id       bigint references public.feedme_folders(id) on delete set null,
  chunk_index     integer not null,
  content         text not null,
  metadata        jsonb not null default '{}'::jsonb,
  embedding       vector(768),                 -- adjust dimension if your embedding model differs
  created_at      timestamptz not null default now(),
  unique (conversation_id, chunk_index)
);

create index if not exists idx_feedme_text_chunks_conversation on public.feedme_text_chunks(conversation_id);
create index if not exists idx_feedme_text_chunks_folder on public.feedme_text_chunks(folder_id);
-- Vector index (requires vector extension). Choose distance op as appropriate (cosine):
do $$ begin
  begin
    execute 'create index if not exists idx_feedme_text_chunks_embedding on public.feedme_text_chunks using ivfflat (embedding vector_cosine_ops)';
  exception when others then
    -- Index creation may fail if ivfflat not configured; ignore to keep migration idempotent
    null;
  end;
end $$;

-- ============================================================
-- FOLDER STATS VIEW (used by UI listings)
-- ============================================================
drop view if exists public.feedme_folder_stats cascade;
create view public.feedme_folder_stats as
select
  f.id,
  f.uuid,
  f.name,
  f.color,
  f.description,
  f.created_by,
  f.created_at,
  f.updated_at,
  coalesce(c.cnt, 0) as conversation_count,
  f.name as folder_path
from public.feedme_folders f
left join (
  select folder_id, count(*) as cnt
  from public.feedme_conversations
  where folder_id is not null
  group by folder_id
) c on c.folder_id = f.id;

-- ============================================================
-- PDF STORAGE ANALYTICS VIEW (used by analytics endpoint)
-- ============================================================
drop view if exists public.feedme_pdf_storage_analytics cascade;
create view public.feedme_pdf_storage_analytics as
select
  -- Total pdf conversations observed
  (select count(*) from public.feedme_conversations where mime_type = 'application/pdf') as total_pdf_conversations,
  -- Cleaned PDFs (payload removed)
  (select count(*) from public.feedme_conversations where pdf_cleaned is true) as cleaned_count,
  -- PDFs pending cleanup (if any policy retains raw_transcript until approval)
  (select count(*) from public.feedme_conversations where mime_type = 'application/pdf' and coalesce(pdf_cleaned, false) = false) as pending_cleanup,
  -- Total MB freed (sum of original_pdf_size for cleaned rows)
  (select coalesce(sum(original_pdf_size),0)::numeric / 1024.0 / 1024.0 from public.feedme_conversations where pdf_cleaned is true) as total_mb_freed,
  -- Average PDF size MB (for reference)
  (select coalesce(avg(original_pdf_size),0)::numeric / 1024.0 / 1024.0 from public.feedme_conversations where mime_type = 'application/pdf') as avg_pdf_size_mb;

-- ============================================================
-- UPDATED_AT TRIGGERS
-- ============================================================
create or replace function public.set_updated_at()
returns trigger as $$
begin
  new.updated_at = now();
  return new;
end;
$$ language plpgsql;

do $$ begin
  if not exists (
    select 1 from pg_trigger where tgname = 'trg_set_updated_at_conversations'
  ) then
    create trigger trg_set_updated_at_conversations
    before update on public.feedme_conversations
    for each row execute function public.set_updated_at();
  end if;
  if not exists (
    select 1 from pg_trigger where tgname = 'trg_set_updated_at_folders'
  ) then
    create trigger trg_set_updated_at_folders
    before update on public.feedme_folders
    for each row execute function public.set_updated_at();
  end if;
end $$;

