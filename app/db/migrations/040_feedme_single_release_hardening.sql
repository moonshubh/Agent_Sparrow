-- Migration: Feed Me single-release hardening primitives
-- Adds deterministic, additive schema needed for reliability/UX/performance rollout.

BEGIN;

-- =====================================================
-- feedme_conversations hardening: os_category + upload_sha256
-- =====================================================
ALTER TABLE IF EXISTS public.feedme_conversations
    ADD COLUMN IF NOT EXISTS os_category TEXT,
    ADD COLUMN IF NOT EXISTS upload_sha256 TEXT;

-- Keep os_category values constrained to the canonical set.
ALTER TABLE IF EXISTS public.feedme_conversations
    DROP CONSTRAINT IF EXISTS feedme_conversations_os_category_check;

ALTER TABLE IF EXISTS public.feedme_conversations
    ADD CONSTRAINT feedme_conversations_os_category_check
    CHECK (os_category IN ('windows', 'macos', 'both', 'uncategorized')) NOT VALID;

-- Normalize existing rows to deterministic default.
UPDATE public.feedme_conversations
SET os_category = 'uncategorized'
WHERE os_category IS NULL
   OR os_category NOT IN ('windows', 'macos', 'both', 'uncategorized');

ALTER TABLE IF EXISTS public.feedme_conversations
    ALTER COLUMN os_category SET DEFAULT 'uncategorized';

ALTER TABLE IF EXISTS public.feedme_conversations
    VALIDATE CONSTRAINT feedme_conversations_os_category_check;

CREATE INDEX IF NOT EXISTS idx_feedme_conversations_upload_sha256
    ON public.feedme_conversations (upload_sha256);

CREATE INDEX IF NOT EXISTS idx_feedme_conversations_upload_sha256_created_at
    ON public.feedme_conversations (upload_sha256, created_at DESC)
    WHERE upload_sha256 IS NOT NULL;

-- =====================================================
-- Feed Me runtime settings (singleton/tenant scoped)
-- =====================================================
CREATE TABLE IF NOT EXISTS public.feedme_settings (
    id BIGSERIAL PRIMARY KEY,
    tenant_id TEXT NOT NULL DEFAULT 'default',
    kb_ready_folder_id BIGINT REFERENCES public.feedme_folders(id) ON DELETE RESTRICT,
    sla_warning_minutes INTEGER NOT NULL DEFAULT 60 CHECK (sla_warning_minutes > 0),
    sla_breach_minutes INTEGER NOT NULL DEFAULT 180 CHECK (sla_breach_minutes > sla_warning_minutes),
    created_by TEXT,
    updated_by TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (tenant_id)
);

CREATE INDEX IF NOT EXISTS idx_feedme_settings_kb_ready_folder_id
    ON public.feedme_settings (kb_ready_folder_id);

-- Seed deterministic default row (tenant scoped, no generated IDs hardcoded).
INSERT INTO public.feedme_settings (tenant_id)
SELECT 'default'
WHERE NOT EXISTS (
    SELECT 1 FROM public.feedme_settings WHERE tenant_id = 'default'
);

CREATE OR REPLACE FUNCTION public.set_feedme_settings_updated_at()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_feedme_settings_updated_at ON public.feedme_settings;
CREATE TRIGGER trg_feedme_settings_updated_at
BEFORE UPDATE ON public.feedme_settings
FOR EACH ROW
EXECUTE FUNCTION public.set_feedme_settings_updated_at();

-- =====================================================
-- Action audit trail for Feed Me mutations
-- =====================================================
CREATE TABLE IF NOT EXISTS public.feedme_action_audit (
    id BIGSERIAL PRIMARY KEY,
    conversation_id BIGINT REFERENCES public.feedme_conversations(id) ON DELETE SET NULL,
    folder_id BIGINT REFERENCES public.feedme_folders(id) ON DELETE SET NULL,
    actor_id TEXT,
    action TEXT NOT NULL,
    reason TEXT,
    before_state JSONB,
    after_state JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_feedme_action_audit_conversation_created
    ON public.feedme_action_audit (conversation_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_feedme_action_audit_action_created
    ON public.feedme_action_audit (action, created_at DESC);

-- =====================================================
-- Persisted conversation version history (canonical source)
-- =====================================================
CREATE TABLE IF NOT EXISTS public.feedme_conversation_versions (
    id BIGSERIAL PRIMARY KEY,
    conversation_id BIGINT NOT NULL REFERENCES public.feedme_conversations(id) ON DELETE CASCADE,
    version_number INTEGER NOT NULL CHECK (version_number > 0),
    transcript_content TEXT NOT NULL,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    change_description TEXT,
    created_by TEXT,
    is_revert BOOLEAN NOT NULL DEFAULT FALSE,
    source_version_number INTEGER,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (conversation_id, version_number)
);

CREATE INDEX IF NOT EXISTS idx_feedme_conversation_versions_conversation_created
    ON public.feedme_conversation_versions (conversation_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_feedme_conversation_versions_conversation_version
    ON public.feedme_conversation_versions (conversation_id, version_number DESC);

-- Deterministic backfill of current state into version history (one snapshot per conversation).
INSERT INTO public.feedme_conversation_versions (
    conversation_id,
    version_number,
    transcript_content,
    metadata,
    change_description,
    created_by,
    created_at
)
SELECT
    c.id,
    GREATEST(COALESCE(c.version, 1), 1),
    COALESCE(NULLIF(c.extracted_text, ''), COALESCE(c.raw_transcript, '')),
    COALESCE(c.metadata, '{}'::jsonb),
    'Initial persisted version snapshot',
    c.uploaded_by,
    COALESCE(c.updated_at, c.created_at, NOW())
FROM public.feedme_conversations AS c
WHERE NOT EXISTS (
    SELECT 1
    FROM public.feedme_conversation_versions AS v
    WHERE v.conversation_id = c.id
);

COMMIT;
