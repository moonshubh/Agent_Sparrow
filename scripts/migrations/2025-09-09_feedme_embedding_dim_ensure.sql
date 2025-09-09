-- Ensure embedding vector dimension aligns with gemini-embedding-001
-- If the column already has a different dimension and contains data,
-- this may fail; run when it's safe to alter.

do $$
begin
  -- Try to alter to vector(768); ignore on failure to keep idempotent
  begin
    alter table public.feedme_text_chunks
      alter column embedding type vector(768);
  exception when others then
    -- ignore if incompatible; you can manually migrate if needed
    null;
  end;
end $$;

