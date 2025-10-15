-- Enforce status enum on zendesk_pending_tickets
DO $$
BEGIN
  -- Drop existing check if present
  IF EXISTS (
    SELECT 1 FROM pg_constraint c
    JOIN pg_class t ON t.oid = c.conrelid
    WHERE t.relname = 'zendesk_pending_tickets' AND c.conname = 'zendesk_pending_tickets_status_check'
  ) THEN
    ALTER TABLE public.zendesk_pending_tickets DROP CONSTRAINT zendesk_pending_tickets_status_check;
  END IF;

  ALTER TABLE public.zendesk_pending_tickets
  ADD CONSTRAINT zendesk_pending_tickets_status_check
  CHECK (status IN ('pending','retry','processing','processed','failed'));
END $$;
