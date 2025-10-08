-- 024_supabase_advisors_remediation.sql
-- Purpose: Remediate Supabase advisor findings (RLS initplan, permissive duplicates, unused indexes)
-- Notes:
-- - Only drop or create with IF EXISTS/guarded logic
-- - Do not widen access; service_role bypasses RLS already
-- - Keep pre-existing mailbird_knowledge_read (or kb_select_authenticated) policy; remove duplicate permissive one

-- 1) mailbird_knowledge: drop duplicate permissive read policy; keep the dedicated read policy
DO $$
BEGIN
  IF to_regclass('public.mailbird_knowledge') IS NOT NULL THEN
    -- Advisor flagged multiple_permissive_policies: {"Enable read access for all users", mailbird_knowledge_read}
    IF EXISTS (
      SELECT 1 FROM pg_policies
      WHERE schemaname = 'public'
        AND tablename = 'mailbird_knowledge'
        AND policyname = 'Enable read access for all users'
    ) THEN
      EXECUTE 'DROP POLICY "Enable read access for all users" ON public.mailbird_knowledge';
    END IF;
    -- If both legacy and new policies exist, keep the new one for consistency
    IF EXISTS (
      SELECT 1 FROM pg_policies
      WHERE schemaname = 'public' AND tablename = 'mailbird_knowledge' AND policyname = 'mailbird_knowledge_read'
    )
    AND EXISTS (
      SELECT 1 FROM pg_policies
      WHERE schemaname = 'public' AND tablename = 'mailbird_knowledge' AND policyname = 'kb_select_authenticated'
    ) THEN
      EXECUTE 'DROP POLICY "mailbird_knowledge_read" ON public.mailbird_knowledge';
    END IF;
  END IF;
END $$;

-- 2) api_key_audit_log: remediate policy using per-row auth/current_setting
-- Advisor: auth_rls_initplan WARN on policy "Service role full access"
-- Service role bypasses RLS, so this policy is unnecessary and can be dropped if present.
-- Else, create a harmless service_role-only policy with constant predicate (no auth.* in row context).
DO $$
BEGIN
  IF to_regclass('public.api_key_audit_log') IS NOT NULL THEN
    IF EXISTS (
      SELECT 1 FROM pg_policies
      WHERE schemaname = 'public'
        AND tablename = 'api_key_audit_log'
        AND policyname = 'Service role full access'
    ) THEN
      EXECUTE 'DROP POLICY "Service role full access" ON public.api_key_audit_log';
    END IF;
  END IF;
END $$;

-- 3) agent_configuration_admin_policy: MANUAL rewrite suggestion
-- Advisor: auth_rls_initplan WARN on "agent_configuration_admin_policy"
-- Current repo version uses SELECT wrappers around auth.jwt(), but rewrite to uid/claim-based checks is recommended.
-- MANUAL: If the intended administrator predicate is unknown, apply the following pattern (after defining your admin logic):
/*
-- MANUAL ACTION REQUIRED:
-- Replace <ADMIN_ROLE_CLAIM> or <ORG/OWNER_PREDICATE> with your actual predicate.
-- Keep auth.* calls inside SELECT to avoid per-row re-evaluation (initplan).
DROP POLICY IF EXISTS "agent_configuration_admin_policy" ON public.agent_configuration;
CREATE POLICY "agent_configuration_admin_policy" ON public.agent_configuration
  FOR ALL
  USING (
    -- Example patterns (choose one):
    -- (SELECT auth.uid()) = '<ADMIN_USER_UUID>'::uuid
    -- (SELECT (auth.jwt() ->> 'role')) = 'admin'
    -- <ORG/OWNER_PREDICATE_REFERENCING_COLUMNS_AND (SELECT auth.uid())>
  )
  WITH CHECK (
    -- Mirror the USING predicate
    (
      -- Same as above
      -- (SELECT auth.uid()) = '<ADMIN_USER_UUID>'::uuid
      -- OR (SELECT (auth.jwt() ->> 'role')) = 'admin'
      -- OR <ORG/OWNER_PREDICATE_REFERENCING_COLUMNS_AND (SELECT auth.uid())>
    )
  );
*/

-- 4) Drop unused feedme_* indexes (advisor 'unused_index' INFO)
-- Target only feedme_* per instruction; use IF EXISTS guards only.
-- These were specifically flagged by the advisor as unused.

-- feedme_conversations
DROP INDEX IF EXISTS public.idx_feedme_conversations_folder_created;
DROP INDEX IF EXISTS public.idx_feedme_conversations_id_covering;
DROP INDEX IF EXISTS public.idx_feedme_conversations_null_folder_created;
DROP INDEX IF EXISTS public.idx_feedme_conversations_status;

-- feedme_examples_temp
DROP INDEX IF EXISTS public.idx_feedme_examples_temp_conversation;
DROP INDEX IF EXISTS public.idx_feedme_examples_temp_created_at;

-- feedme_folders
DROP INDEX IF EXISTS public.idx_feedme_folders_created;
DROP INDEX IF EXISTS public.idx_feedme_folders_stats;
DROP INDEX IF EXISTS public.idx_feedme_folders_updated_at;

-- feedme_text_chunks
DROP INDEX IF EXISTS public.idx_feedme_text_chunks_conversation_id;
DROP INDEX IF EXISTS public.idx_feedme_text_chunks_created_at;
DROP INDEX IF EXISTS public.idx_feedme_text_chunks_folder;
DROP INDEX IF EXISTS public.idx_feedme_text_chunks_folder_conversation;

-- Note: Do NOT drop: idx_feedme_text_chunks_embedding (actively used for vector search).
