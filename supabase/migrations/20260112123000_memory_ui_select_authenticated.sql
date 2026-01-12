-- Allow all authenticated users to read memories (editing stays admin-only).
drop policy if exists memories_select_authenticated on public.memories;

create policy memories_select_authenticated
  on public.memories
  for select
  to authenticated
  using (true);
