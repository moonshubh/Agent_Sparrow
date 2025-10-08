-- Migration: Harden FeedMe RPCs and enable RLS

DO $$
BEGIN
  -- Enable RLS on feedme_text_chunks if table exists
  IF to_regclass('public.feedme_text_chunks') IS NOT NULL THEN
    EXECUTE 'ALTER TABLE public.feedme_text_chunks ENABLE ROW LEVEL SECURITY';
    IF NOT EXISTS (
      SELECT 1 FROM pg_policies WHERE schemaname='public' AND tablename='feedme_text_chunks' AND policyname='feedme_text_chunks_select_authenticated'
    ) THEN
      EXECUTE 'CREATE POLICY feedme_text_chunks_select_authenticated ON public.feedme_text_chunks FOR SELECT TO authenticated USING (true)';
    END IF;
  END IF;
END $$;

-- Recreate FeedMe text chunk search RPC with SECURITY INVOKER and pinned search_path
CREATE OR REPLACE FUNCTION public.search_feedme_text_chunks(
  query_embedding vector(3072),
  match_count int DEFAULT 10,
  filter_folder_id int DEFAULT NULL
)
RETURNS TABLE (
  id bigint,
  conversation_id int,
  folder_id int,
  chunk_index int,
  content text,
  metadata jsonb,
  similarity double precision
)
LANGUAGE sql
SECURITY INVOKER
SET search_path = public
AS $$
  SELECT
    t.id,
    t.conversation_id,
    t.folder_id,
    t.chunk_index,
    t.content,
    t.metadata,
    1 - (t.embedding <=> query_embedding) AS similarity
  FROM public.feedme_text_chunks t
  WHERE t.embedding IS NOT NULL
    AND (filter_folder_id IS NULL OR t.folder_id = filter_folder_id)
  ORDER BY t.embedding <=> query_embedding
  LIMIT COALESCE(match_count, 10);
$$;

-- Restrict EXECUTE grants
REVOKE ALL ON FUNCTION public.search_feedme_text_chunks(vector(3072), int, int) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION public.search_feedme_text_chunks(vector(3072), int, int) TO authenticated;
GRANT EXECUTE ON FUNCTION public.search_feedme_text_chunks(vector(3072), int, int) TO service_role;
