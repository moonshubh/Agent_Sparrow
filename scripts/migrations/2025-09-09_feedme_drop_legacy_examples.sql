-- FeedMe: Drop legacy Q&A example flows (tables/functions/indexes)
-- Safe to run multiple times; uses IF EXISTS and dynamic drops.

-- 1) Drop RPC/functions named search_feedme_examples (any signature)
DO $$
DECLARE f RECORD;
BEGIN
  FOR f IN (
    SELECT (p.oid::regprocedure)::text AS signature
    FROM pg_proc p
    JOIN pg_namespace n ON n.oid = p.pronamespace
    WHERE p.proname = 'search_feedme_examples'
  ) LOOP
    EXECUTE format('DROP FUNCTION IF EXISTS %s CASCADE;', f.signature);
  END LOOP;
END $$;

-- 2) Drop indexes on feedme_examples if present (best-effort)
DO $$
DECLARE idx RECORD;
BEGIN
  FOR idx IN (
    SELECT indexrelid::regclass AS idxname
    FROM pg_index i
    JOIN pg_class t ON t.oid = i.indrelid
    JOIN pg_class ix ON ix.oid = i.indexrelid
    JOIN pg_namespace n ON n.oid = t.relnamespace
    WHERE t.relname = 'feedme_examples'
  ) LOOP
    EXECUTE format('DROP INDEX IF EXISTS %s;', idx.idxname);
  END LOOP;
END $$;

-- 3) Drop the legacy table itself
DROP TABLE IF EXISTS public.feedme_examples CASCADE;

-- 4) Optional: remove columns on conversations that reference examples counts
-- Uncomment if you want to clean these up as well.
-- ALTER TABLE public.feedme_conversations DROP COLUMN IF EXISTS total_examples;
-- ALTER TABLE public.feedme_conversations DROP COLUMN IF EXISTS high_quality_examples;
-- ALTER TABLE public.feedme_conversations DROP COLUMN IF EXISTS medium_quality_examples;
-- ALTER TABLE public.feedme_conversations DROP COLUMN IF EXISTS low_quality_examples;

-- 5) Optional: clean views referencing feedme_examples (best-effort)
-- This block will drop dependent views automatically when table is dropped with CASCADE. 
-- If you keep the table for archival, search and update views manually.

