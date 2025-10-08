-- Migration: Harden KB RPC and enable RLS with proper grants

-- 1) Ensure RLS on knowledge tables
DO $$
BEGIN
  IF to_regclass('public.mailbird_knowledge') IS NOT NULL THEN
    EXECUTE 'ALTER TABLE public.mailbird_knowledge ENABLE ROW LEVEL SECURITY';
    -- Allow authenticated users to read
    IF NOT EXISTS (
      SELECT 1 FROM pg_policies WHERE schemaname='public' AND tablename='mailbird_knowledge' AND policyname='kb_select_authenticated'
    ) THEN
      EXECUTE 'CREATE POLICY kb_select_authenticated ON public.mailbird_knowledge FOR SELECT TO authenticated USING (true)';
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

-- 2) Recreate RPC as SECURITY INVOKER with pinned search_path
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
SET search_path = public
AS $$
  SELECT
    k.id,
    k.url,
    k.markdown,
    k.content,
    k.metadata,
    1 - (k.embedding <=> query_embedding) AS similarity
  FROM public.mailbird_knowledge k
  WHERE k.embedding IS NOT NULL
    AND (1 - (k.embedding <=> query_embedding)) >= COALESCE(match_threshold, 0)
  ORDER BY k.embedding <=> query_embedding
  LIMIT COALESCE(match_count, 5);
$$;

-- 3) Restrict EXECUTE grants
REVOKE ALL ON FUNCTION public.search_mailbird_knowledge(vector(3072), int, double precision) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION public.search_mailbird_knowledge(vector(3072), int, double precision) TO authenticated;
GRANT EXECUTE ON FUNCTION public.search_mailbird_knowledge(vector(3072), int, double precision) TO service_role;
