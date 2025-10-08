-- 025_supabase_perf_advisors_cleanup.sql
-- Purpose: Address remaining performance advisor warnings
-- Fixes:
-- 1) Add covering indexes for foreign keys flagged as unindexed (feedme_* tables)
-- 2) Remove duplicate/permissive RLS policy on agent_configuration to resolve multiple_permissive_policies and initplan warnings
-- 3) Drop unused indexes on agent_configuration

-- 1) Covering indexes for FKs
DO $$
BEGIN
  IF to_regclass('public.feedme_conversations') IS NOT NULL THEN
    EXECUTE 'CREATE INDEX IF NOT EXISTS idx_feedme_conversations_folder_id ON public.feedme_conversations (folder_id)';
  END IF;

  IF to_regclass('public.feedme_examples_temp') IS NOT NULL THEN
    EXECUTE 'CREATE INDEX IF NOT EXISTS idx_feedme_examples_temp_conversation_id ON public.feedme_examples_temp (conversation_id)';
  END IF;

  IF to_regclass('public.feedme_text_chunks') IS NOT NULL THEN
    EXECUTE 'CREATE INDEX IF NOT EXISTS idx_feedme_text_chunks_folder_id ON public.feedme_text_chunks (folder_id)';
  END IF;
END $$;

-- 2) Agent configuration policies
-- Drop admin policy to avoid duplicate permissive SELECT and per-row auth/current_setting() evaluation
DO $$
BEGIN
  IF to_regclass('public.agent_configuration') IS NOT NULL THEN
    IF EXISTS (
      SELECT 1 FROM pg_policies
      WHERE schemaname='public' AND tablename='agent_configuration' AND policyname='agent_configuration_admin_policy'
    ) THEN
      EXECUTE 'DROP POLICY "agent_configuration_admin_policy" ON public.agent_configuration';
    END IF;
  END IF;
END $$;

-- 3) Drop unused indexes on agent_configuration
DROP INDEX IF EXISTS public.idx_agent_configuration_created_at;
DROP INDEX IF EXISTS public.idx_agent_configuration_updated_at;
