-- Migration 021: Optimize RLS Policies for Performance
-- This migration fixes performance issues with RLS policies that re-evaluate auth functions for each row
-- Issue: auth.role() and auth.jwt() are being called for every row instead of once per query
-- Solution: Wrap auth functions in SELECT statements for single evaluation

-- Drop and recreate all policies with performance optimizations

-- ========================================
-- Optimize feedme_conversations policies
-- ========================================

DROP POLICY IF EXISTS "feedme_conversations_authenticated_select" ON public.feedme_conversations;
CREATE POLICY "feedme_conversations_authenticated_select" ON public.feedme_conversations
    FOR SELECT
    USING ((SELECT auth.role()) = 'authenticated' OR (SELECT auth.jwt() ->> 'role') = 'service_role');

DROP POLICY IF EXISTS "feedme_conversations_authenticated_insert" ON public.feedme_conversations;
CREATE POLICY "feedme_conversations_authenticated_insert" ON public.feedme_conversations
    FOR INSERT
    WITH CHECK ((SELECT auth.role()) = 'authenticated' OR (SELECT auth.jwt() ->> 'role') = 'service_role');

DROP POLICY IF EXISTS "feedme_conversations_authenticated_update" ON public.feedme_conversations;
CREATE POLICY "feedme_conversations_authenticated_update" ON public.feedme_conversations
    FOR UPDATE
    USING ((SELECT auth.role()) = 'authenticated' OR (SELECT auth.jwt() ->> 'role') = 'service_role')
    WITH CHECK ((SELECT auth.role()) = 'authenticated' OR (SELECT auth.jwt() ->> 'role') = 'service_role');

DROP POLICY IF EXISTS "feedme_conversations_authenticated_delete" ON public.feedme_conversations;
CREATE POLICY "feedme_conversations_authenticated_delete" ON public.feedme_conversations
    FOR DELETE
    USING ((SELECT auth.role()) = 'authenticated' OR (SELECT auth.jwt() ->> 'role') = 'service_role');

-- ========================================
-- Optimize feedme_examples policies
-- ========================================

DROP POLICY IF EXISTS "feedme_examples_authenticated_select" ON public.feedme_examples;
CREATE POLICY "feedme_examples_authenticated_select" ON public.feedme_examples
    FOR SELECT
    USING ((SELECT auth.role()) = 'authenticated' OR (SELECT auth.jwt() ->> 'role') = 'service_role');

DROP POLICY IF EXISTS "feedme_examples_authenticated_insert" ON public.feedme_examples;
CREATE POLICY "feedme_examples_authenticated_insert" ON public.feedme_examples
    FOR INSERT
    WITH CHECK ((SELECT auth.role()) = 'authenticated' OR (SELECT auth.jwt() ->> 'role') = 'service_role');

DROP POLICY IF EXISTS "feedme_examples_authenticated_update" ON public.feedme_examples;
CREATE POLICY "feedme_examples_authenticated_update" ON public.feedme_examples
    FOR UPDATE
    USING ((SELECT auth.role()) = 'authenticated' OR (SELECT auth.jwt() ->> 'role') = 'service_role')
    WITH CHECK ((SELECT auth.role()) = 'authenticated' OR (SELECT auth.jwt() ->> 'role') = 'service_role');

DROP POLICY IF EXISTS "feedme_examples_authenticated_delete" ON public.feedme_examples;
CREATE POLICY "feedme_examples_authenticated_delete" ON public.feedme_examples
    FOR DELETE
    USING ((SELECT auth.role()) = 'authenticated' OR (SELECT auth.jwt() ->> 'role') = 'service_role');

-- ========================================
-- Optimize feedme_examples_temp policies
-- ========================================

DROP POLICY IF EXISTS "feedme_examples_temp_authenticated_select" ON public.feedme_examples_temp;
CREATE POLICY "feedme_examples_temp_authenticated_select" ON public.feedme_examples_temp
    FOR SELECT
    USING ((SELECT auth.role()) = 'authenticated' OR (SELECT auth.jwt() ->> 'role') = 'service_role');

DROP POLICY IF EXISTS "feedme_examples_temp_authenticated_insert" ON public.feedme_examples_temp;
CREATE POLICY "feedme_examples_temp_authenticated_insert" ON public.feedme_examples_temp
    FOR INSERT
    WITH CHECK ((SELECT auth.role()) = 'authenticated' OR (SELECT auth.jwt() ->> 'role') = 'service_role');

DROP POLICY IF EXISTS "feedme_examples_temp_authenticated_update" ON public.feedme_examples_temp;
CREATE POLICY "feedme_examples_temp_authenticated_update" ON public.feedme_examples_temp
    FOR UPDATE
    USING ((SELECT auth.role()) = 'authenticated' OR (SELECT auth.jwt() ->> 'role') = 'service_role')
    WITH CHECK ((SELECT auth.role()) = 'authenticated' OR (SELECT auth.jwt() ->> 'role') = 'service_role');

DROP POLICY IF EXISTS "feedme_examples_temp_authenticated_delete" ON public.feedme_examples_temp;
CREATE POLICY "feedme_examples_temp_authenticated_delete" ON public.feedme_examples_temp
    FOR DELETE
    USING ((SELECT auth.role()) = 'authenticated' OR (SELECT auth.jwt() ->> 'role') = 'service_role');

-- ========================================
-- Optimize feedme_folders policies
-- ========================================

DROP POLICY IF EXISTS "feedme_folders_authenticated_select" ON public.feedme_folders;
CREATE POLICY "feedme_folders_authenticated_select" ON public.feedme_folders
    FOR SELECT
    USING ((SELECT auth.role()) = 'authenticated' OR (SELECT auth.jwt() ->> 'role') = 'service_role');

DROP POLICY IF EXISTS "feedme_folders_authenticated_insert" ON public.feedme_folders;
CREATE POLICY "feedme_folders_authenticated_insert" ON public.feedme_folders
    FOR INSERT
    WITH CHECK ((SELECT auth.role()) = 'authenticated' OR (SELECT auth.jwt() ->> 'role') = 'service_role');

DROP POLICY IF EXISTS "feedme_folders_authenticated_update" ON public.feedme_folders;
CREATE POLICY "feedme_folders_authenticated_update" ON public.feedme_folders
    FOR UPDATE
    USING ((SELECT auth.role()) = 'authenticated' OR (SELECT auth.jwt() ->> 'role') = 'service_role')
    WITH CHECK ((SELECT auth.role()) = 'authenticated' OR (SELECT auth.jwt() ->> 'role') = 'service_role');

DROP POLICY IF EXISTS "feedme_folders_authenticated_delete" ON public.feedme_folders;
CREATE POLICY "feedme_folders_authenticated_delete" ON public.feedme_folders
    FOR DELETE
    USING ((SELECT auth.role()) = 'authenticated' OR (SELECT auth.jwt() ->> 'role') = 'service_role');

-- ========================================
-- Optimize mailbird_knowledge policies
-- ========================================

DROP POLICY IF EXISTS "mailbird_knowledge_authenticated_select" ON public.mailbird_knowledge;
CREATE POLICY "mailbird_knowledge_authenticated_select" ON public.mailbird_knowledge
    FOR SELECT
    USING ((SELECT auth.role()) = 'authenticated' OR (SELECT auth.jwt() ->> 'role') = 'service_role');

DROP POLICY IF EXISTS "mailbird_knowledge_service_insert" ON public.mailbird_knowledge;
CREATE POLICY "mailbird_knowledge_service_insert" ON public.mailbird_knowledge
    FOR INSERT
    WITH CHECK ((SELECT auth.jwt() ->> 'role') = 'service_role');

DROP POLICY IF EXISTS "mailbird_knowledge_service_update" ON public.mailbird_knowledge;
CREATE POLICY "mailbird_knowledge_service_update" ON public.mailbird_knowledge
    FOR UPDATE
    USING ((SELECT auth.jwt() ->> 'role') = 'service_role')
    WITH CHECK ((SELECT auth.jwt() ->> 'role') = 'service_role');

DROP POLICY IF EXISTS "mailbird_knowledge_service_delete" ON public.mailbird_knowledge;
CREATE POLICY "mailbird_knowledge_service_delete" ON public.mailbird_knowledge
    FOR DELETE
    USING ((SELECT auth.jwt() ->> 'role') = 'service_role');

-- ========================================
-- Optimize agent_configuration policies
-- ========================================

DROP POLICY IF EXISTS "agent_configuration_admin_policy" ON public.agent_configuration;
CREATE POLICY "agent_configuration_admin_policy" ON public.agent_configuration
    FOR ALL
    USING ((SELECT auth.jwt() ->> 'role') = 'service_role')
    WITH CHECK ((SELECT auth.jwt() ->> 'role') = 'service_role');

-- ========================================
-- Optimize chat_sessions policies
-- ========================================

DROP POLICY IF EXISTS "chat_sessions_user_select" ON public.chat_sessions;
CREATE POLICY "chat_sessions_user_select" ON public.chat_sessions
    FOR SELECT
    USING (
        user_id = COALESCE((SELECT auth.jwt() ->> 'sub'), 'anonymous') OR
        user_id = 'skipped_auth_user'
    );

DROP POLICY IF EXISTS "chat_sessions_user_insert" ON public.chat_sessions;
CREATE POLICY "chat_sessions_user_insert" ON public.chat_sessions
    FOR INSERT
    WITH CHECK (
        user_id = COALESCE((SELECT auth.jwt() ->> 'sub'), 'anonymous') OR
        user_id = 'skipped_auth_user'
    );

DROP POLICY IF EXISTS "chat_sessions_user_update" ON public.chat_sessions;
CREATE POLICY "chat_sessions_user_update" ON public.chat_sessions
    FOR UPDATE
    USING (
        user_id = COALESCE((SELECT auth.jwt() ->> 'sub'), 'anonymous') OR
        user_id = 'skipped_auth_user'
    )
    WITH CHECK (
        user_id = COALESCE((SELECT auth.jwt() ->> 'sub'), 'anonymous') OR
        user_id = 'skipped_auth_user'
    );

DROP POLICY IF EXISTS "chat_sessions_user_delete" ON public.chat_sessions;
CREATE POLICY "chat_sessions_user_delete" ON public.chat_sessions
    FOR DELETE
    USING (
        user_id = COALESCE((SELECT auth.jwt() ->> 'sub'), 'anonymous') OR
        user_id = 'skipped_auth_user'
    );

-- ========================================
-- Optimize chat_messages policies
-- ========================================

DROP POLICY IF EXISTS "chat_messages_user_select" ON public.chat_messages;
CREATE POLICY "chat_messages_user_select" ON public.chat_messages
    FOR SELECT
    USING (
        EXISTS (
            SELECT 1 FROM public.chat_sessions
            WHERE chat_sessions.id = chat_messages.session_id
            AND (
                chat_sessions.user_id = COALESCE((SELECT auth.jwt() ->> 'sub'), 'anonymous') OR
                chat_sessions.user_id = 'skipped_auth_user'
            )
        )
    );

DROP POLICY IF EXISTS "chat_messages_user_insert" ON public.chat_messages;
CREATE POLICY "chat_messages_user_insert" ON public.chat_messages
    FOR INSERT
    WITH CHECK (
        EXISTS (
            SELECT 1 FROM public.chat_sessions
            WHERE chat_sessions.id = chat_messages.session_id
            AND (
                chat_sessions.user_id = COALESCE((SELECT auth.jwt() ->> 'sub'), 'anonymous') OR
                chat_sessions.user_id = 'skipped_auth_user'
            )
        )
    );

DROP POLICY IF EXISTS "chat_messages_user_update" ON public.chat_messages;
CREATE POLICY "chat_messages_user_update" ON public.chat_messages
    FOR UPDATE
    USING (
        EXISTS (
            SELECT 1 FROM public.chat_sessions
            WHERE chat_sessions.id = chat_messages.session_id
            AND (
                chat_sessions.user_id = COALESCE((SELECT auth.jwt() ->> 'sub'), 'anonymous') OR
                chat_sessions.user_id = 'skipped_auth_user'
            )
        )
    )
    WITH CHECK (
        EXISTS (
            SELECT 1 FROM public.chat_sessions
            WHERE chat_sessions.id = chat_messages.session_id
            AND (
                chat_sessions.user_id = COALESCE((SELECT auth.jwt() ->> 'sub'), 'anonymous') OR
                chat_sessions.user_id = 'skipped_auth_user'
            )
        )
    );

-- ========================================
-- Clean up duplicate indexes (performance improvement)
-- ========================================

-- Remove duplicate index on feedme_conversations
DROP INDEX IF EXISTS idx_feedme_conversations_active;  -- Keep idx_feedme_conversations_is_active

-- Add comments
COMMENT ON POLICY "feedme_conversations_authenticated_select" ON public.feedme_conversations IS 'Optimized: Uses SELECT wrapper for single auth evaluation';
COMMENT ON POLICY "chat_sessions_user_select" ON public.chat_sessions IS 'Optimized: Uses SELECT wrapper for single JWT evaluation per query';