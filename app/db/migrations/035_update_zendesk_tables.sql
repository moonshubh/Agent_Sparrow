-- Update Zendesk integration tables with retry metadata and Gemini usage tracking

ALTER TABLE IF EXISTS public.zendesk_pending_tickets
    ADD COLUMN IF NOT EXISTS retry_count INTEGER NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS next_attempt_at TIMESTAMPTZ NULL,
    ADD COLUMN IF NOT EXISTS last_error TEXT NULL,
    ADD COLUMN IF NOT EXISTS last_attempt_at TIMESTAMPTZ NULL,
    ADD COLUMN IF NOT EXISTS status_details JSONB NOT NULL DEFAULT '{}'::jsonb;

CREATE INDEX IF NOT EXISTS idx_zpt_status_retry_window
  ON public.zendesk_pending_tickets (status, next_attempt_at);


CREATE TABLE IF NOT EXISTS public.zendesk_daily_usage (
  usage_date DATE PRIMARY KEY,
  gemini_calls_used INT NOT NULL DEFAULT 0,
  gemini_daily_limit INT NOT NULL DEFAULT 1000,
  updated_at TIMESTAMPTZ NOT NULL DEFAULT timezone('utc', now())
);

ALTER TABLE IF EXISTS public.zendesk_daily_usage ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.zendesk_daily_usage FROM anon, authenticated;
