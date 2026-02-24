-- Atomic helper for guarded memory cleanup scripts.
-- Deletes relationship rows tied to source memories, then deletes memories
-- in one database transaction per RPC call.

create or replace function public.delete_memories_with_relationship_cleanup(
    p_memory_ids uuid[]
)
returns table (
    deleted_relationships integer,
    deleted_memories integer
)
language plpgsql
security definer
set search_path = public
as $$
begin
    if p_memory_ids is null or array_length(p_memory_ids, 1) is null then
        deleted_relationships := 0;
        deleted_memories := 0;
        return next;
    end if;

    -- Retire duplicate-candidate rows that reference deleted memories.
    delete from public.memory_duplicate_candidates
    where memory_id_1 = any(p_memory_ids)
       or memory_id_2 = any(p_memory_ids)
       or merge_target_id = any(p_memory_ids);

    -- Preserve aggregated relationship rows and only detach representative pointers
    -- from memories being deleted.
    update public.memory_relationships
    set source_memory_id = null
    where source_memory_id = any(p_memory_ids);
    get diagnostics deleted_relationships = row_count;

    delete from public.memories
    where id = any(p_memory_ids);
    get diagnostics deleted_memories = row_count;

    return next;
end;
$$;

revoke all on function public.delete_memories_with_relationship_cleanup(uuid[]) from public;
grant execute on function public.delete_memories_with_relationship_cleanup(uuid[]) to service_role;
