-- Update RPC to truncate content payloads for safer transport and smaller responses

create or replace function public.search_web_research_snapshots(
  query_embedding vector(3072),
  match_count int default 5,
  match_threshold float default 0.4
)
returns table (
  id bigint,
  url text,
  title text,
  content text,
  source_domain text,
  published_at timestamptz,
  similarity float8
)
language plpgsql
security invoker
as $$
begin
  return query
  select
    w.id,
    w.url,
    w.title,
    left(w.content, 2000) as content,
    w.source_domain,
    w.published_at,
    1 - (w.embedding <=> query_embedding) as similarity
  from public.web_research_snapshots w
  where w.embedding is not null
    and 1 - (w.embedding <=> query_embedding) >= match_threshold
  order by w.embedding <=> query_embedding asc
  limit match_count;
end;
$$;

comment on function public.search_web_research_snapshots(vector, int, float)
  is 'RLS-safe search over saved web research snapshots; SECURITY INVOKER; returns similarity (cosine); content truncated to 2000 chars.';
