-- Idempotency guard table for Zendesk webhooks (replay protection)
CREATE TABLE IF NOT EXISTS public.zendesk_webhook_events (
  sig_key TEXT PRIMARY KEY,
  ts BIGINT NOT NULL,
  seen_at TIMESTAMPTZ NOT NULL DEFAULT timezone('utc', now())
);

ALTER TABLE IF NOT EXISTS public.zendesk_webhook_events ENABLE ROW LEVEL SECURITY;

-- Defense in depth: deny anon/auth roles explicitly (service role bypasses RLS)
REVOKE ALL ON public.zendesk_webhook_events FROM anon, authenticated;
