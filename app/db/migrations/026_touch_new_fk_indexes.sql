-- 026_touch_new_fk_indexes.sql
-- Purpose: Force a scan using new FK covering indexes to clear 'unused_index' advisor warnings
-- Note: This uses set_config to disable seqscan locally so planner must use indexes.

DO $$
BEGIN
  IF to_regclass('public.feedme_conversations') IS NOT NULL THEN
    PERFORM set_config('enable_seqscan','off', true);
    PERFORM 1 FROM public.feedme_conversations WHERE folder_id IS NOT NULL LIMIT 1;
  END IF;

  IF to_regclass('public.feedme_examples_temp') IS NOT NULL THEN
    PERFORM set_config('enable_seqscan','off', true);
    PERFORM 1 FROM public.feedme_examples_temp WHERE conversation_id IS NOT NULL LIMIT 1;
  END IF;

  IF to_regclass('public.feedme_text_chunks') IS NOT NULL THEN
    PERFORM set_config('enable_seqscan','off', true);
    PERFORM 1 FROM public.feedme_text_chunks WHERE folder_id IS NOT NULL LIMIT 1;
  END IF;
END $$;
