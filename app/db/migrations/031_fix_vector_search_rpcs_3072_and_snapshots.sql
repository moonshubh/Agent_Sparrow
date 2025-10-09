-- Fix vector search RPCs to use vector(3072) and align with actual schema
-- Use inner product operator (<#>) for broad pgvector compatibility (fallback when <=> is unavailable)
-- Also compute source_domain from URL and map created_at -> published_at for web snapshots

-- 0) Enable RLS (idempotent)
DO $$
BEGIN
  IF to_regclass('public.mailbird_knowledge') IS NOT NULL THEN
    EXECUTE 'ALTER TABLE public.mailbird_knowledge ENABLE ROW LEVEL SECURITY';
    IF NOT EXISTS (
      SELECT 1 FROM pg_policies WHERE schemaname='public' AND tablename='mailbird_knowledge' AND policyname='kb_select_authenticated'
    ) THEN
      EXECUTE 'CREATE POLICY kb_select_authenticated ON public.mailbird_knowledge FOR SELECT TO authenticated USING (true)';
    END IF;
  END IF;

  IF to_regclass('public.feedme_text_chunks') IS NOT NULL THEN
    EXECUTE 'ALTER TABLE public.feedme_text_chunks ENABLE ROW LEVEL SECURITY';
    IF NOT EXISTS (
      SELECT 1 FROM pg_policies WHERE schemaname='public' AND tablename='feedme_text_chunks' AND policyname='feedme_text_chunks_select_authenticated'
    ) THEN
      EXECUTE 'CREATE POLICY feedme_text_chunks_select_authenticated ON public.feedme_text_chunks FOR SELECT TO authenticated USING (true)';
    END IF;
  END IF;

  IF to_regclass('public.web_research_snapshots') IS NOT NULL THEN
    EXECUTE 'ALTER TABLE public.web_research_snapshots ENABLE ROW LEVEL SECURITY';
    IF NOT EXISTS (
      SELECT 1 FROM pg_policies WHERE schemaname='public' AND tablename='web_research_snapshots' AND policyname='web_snapshots_select_authenticated'
    ) THEN
      EXECUTE 'CREATE POLICY web_snapshots_select_authenticated ON public.web_research_snapshots FOR SELECT TO authenticated USING (true)';
    END IF;
  END IF;
END $$;

-- 1) Drop any old variants (avoid ambiguity)
DROP FUNCTION IF EXISTS public.search_mailbird_knowledge(vector, int, double precision);
DROP FUNCTION IF EXISTS public.search_mailbird_knowledge(vector(3072), int, double precision);

DROP FUNCTION IF EXISTS public.search_feedme_text_chunks(vector, int, bigint);
DROP FUNCTION IF EXISTS public.search_feedme_text_chunks(vector(3072), int, int);
DROP FUNCTION IF EXISTS public.search_feedme_text_chunks(vector(3072), int, bigint);

DROP FUNCTION IF EXISTS public.search_web_research_snapshots(vector, int, float);
DROP FUNCTION IF EXISTS public.search_web_research_snapshots(vector(3072), int, float);
DROP FUNCTION IF EXISTS public.search_web_research_snapshots(vector(3072), int, double precision);

-- 2) Recreate search_mailbird_knowledge with vector(3072)
CREATE OR REPLACE FUNCTION public.search_mailbird_knowledge(
  query_embedding vector(3072),
  match_count int DEFAULT 5,
  match_threshold double precision DEFAULT 0.0
)
RETURNS TABLE (
  id bigint,
  url text,
  markdown text,
  content text,
  metadata jsonb,
  similarity double precision
)
LANGUAGE sql
SECURITY INVOKER
SET search_path = public, extensions
AS $$
  SELECT
    k.id,
    k.url,
    k.markdown,
    k.content,
    k.metadata,
    -(k.embedding <#> query_embedding) AS similarity
  FROM public.mailbird_knowledge k
  WHERE k.embedding IS NOT NULL
    AND (-(k.embedding <#> query_embedding)) >= COALESCE(match_threshold, 0)
  ORDER BY k.embedding <#> query_embedding
  LIMIT COALESCE(match_count, 5);
$$;

REVOKE ALL ON FUNCTION public.search_mailbird_knowledge(vector(3072), int, double precision) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION public.search_mailbird_knowledge(vector(3072), int, double precision) TO authenticated;
GRANT EXECUTE ON FUNCTION public.search_mailbird_knowledge(vector(3072), int, double precision) TO service_role;

-- 3) Recreate search_feedme_text_chunks with vector(3072)
CREATE OR REPLACE FUNCTION public.search_feedme_text_chunks(
  query_embedding vector(3072),
  match_count int DEFAULT 10,
  filter_folder_id int DEFAULT NULL
)
RETURNS TABLE (
  id bigint,
  conversation_id bigint,
  folder_id bigint,
  chunk_index int,
  content text,
  metadata jsonb,
  similarity double precision
)
LANGUAGE sql
SECURITY INVOKER
SET search_path = public, extensions
AS $$
  SELECT
    t.id,
    t.conversation_id,
    t.folder_id,
    t.chunk_index,
    t.content,
    t.metadata,
    -(t.embedding <#> query_embedding) AS similarity
  FROM public.feedme_text_chunks t
  WHERE t.embedding IS NOT NULL
    AND (filter_folder_id IS NULL OR t.folder_id = filter_folder_id)
  ORDER BY t.embedding <#> query_embedding
  LIMIT COALESCE(match_count, 10);
$$;

REVOKE ALL ON FUNCTION public.search_feedme_text_chunks(vector(3072), int, int) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION public.search_feedme_text_chunks(vector(3072), int, int) TO authenticated;
GRANT EXECUTE ON FUNCTION public.search_feedme_text_chunks(vector(3072), int, int) TO service_role;

-- 4) Recreate search_web_research_snapshots aligned with actual schema
CREATE OR REPLACE FUNCTION public.search_web_research_snapshots(
  query_embedding vector(3072),
  match_count int DEFAULT 5,
  match_threshold double precision DEFAULT 0.4
)
RETURNS TABLE (
  id bigint,
  url text,
  title text,
  content text,
  source_domain text,
  published_at timestamptz,
  similarity double precision
)
LANGUAGE sql
SECURITY INVOKER
SET search_path = public, extensions
AS $$
  SELECT
    w.id,
    w.url,
    w.title,
    left(w.content, 2000) AS content,
    regexp_replace(
      split_part(replace(replace(w.url, 'https://', ''), 'http://', ''), '/', 1),
      '^www\\.',
      ''
    ) AS source_domain,
    w.created_at AS published_at,
    -(w.embedding <#> query_embedding) AS similarity
  FROM public.web_research_snapshots w
  WHERE w.embedding IS NOT NULL
    AND (-(w.embedding <#> query_embedding)) >= COALESCE(match_threshold, 0.4)
  ORDER BY w.embedding <#> query_embedding ASC
  LIMIT COALESCE(match_count, 5);
$$;

REVOKE ALL ON FUNCTION public.search_web_research_snapshots(vector(3072), int, double precision) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION public.search_web_research_snapshots(vector(3072), int, double precision) TO authenticated;
GRANT EXECUTE ON FUNCTION public.search_web_research_snapshots(vector(3072), int, double precision) TO service_role;
