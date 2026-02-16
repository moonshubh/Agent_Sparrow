-- Server-side edited-state memory listing with pagination + exact total.
-- Prevents app-layer full scans for edited/unedited filters.

create or replace function public.list_memories_with_edited_state(
    p_agent_id text default null,
    p_tenant_id text default null,
    p_source_type text default null,
    p_edited_state text default 'all',
    p_limit integer default 50,
    p_offset integer default 0,
    p_sort_order text default 'desc'
)
returns table (
    id uuid,
    content text,
    metadata jsonb,
    source_type character varying,
    review_status text,
    reviewed_by uuid,
    reviewed_at timestamp with time zone,
    confidence_score numeric,
    retrieval_count integer,
    last_retrieved_at timestamp with time zone,
    feedback_positive integer,
    feedback_negative integer,
    resolution_success_count integer,
    resolution_failure_count integer,
    agent_id character varying,
    tenant_id character varying,
    created_at timestamp with time zone,
    updated_at timestamp with time zone,
    total_count bigint
)
language sql
security definer
set search_path = public
as $$
with normalized as (
    select
        case
            when lower(coalesce(p_edited_state, 'all')) in ('edited', 'unedited')
                then lower(coalesce(p_edited_state, 'all'))
            else 'all'
        end as edited_state,
        greatest(1, least(coalesce(p_limit, 50), 500)) as limit_rows,
        greatest(coalesce(p_offset, 0), 0) as offset_rows,
        case
            when lower(coalesce(p_sort_order, 'desc')) = 'asc' then 'asc'
            else 'desc'
        end as sort_order
),
filtered as (
    select m.*
    from public.memories m
    cross join normalized n
    where (p_agent_id is null or m.agent_id = p_agent_id)
      and (p_tenant_id is null or m.tenant_id = p_tenant_id)
      and (p_source_type is null or m.source_type = p_source_type)
      and (
          n.edited_state = 'all'
          or (
              n.edited_state = 'edited'
              and m.updated_at > m.created_at
              and (
                  m.reviewed_by is not null
                  or coalesce(btrim(m.metadata->>'edited_by_email'), '') <> ''
                  or coalesce(btrim(m.metadata->>'updated_by_email'), '') <> ''
                  or coalesce(btrim(m.metadata->>'editor_email'), '') <> ''
                  or coalesce(btrim(m.metadata->>'edited_by'), '') <> ''
                  or coalesce(btrim(m.metadata->>'updated_by'), '') <> ''
                  or coalesce(btrim(m.metadata->>'edited_by_name'), '') <> ''
                  or coalesce(btrim(m.metadata->>'updated_by_name'), '') <> ''
              )
          )
          or (
              n.edited_state = 'unedited'
              and not (
                  m.updated_at > m.created_at
                  and (
                      m.reviewed_by is not null
                      or coalesce(btrim(m.metadata->>'edited_by_email'), '') <> ''
                      or coalesce(btrim(m.metadata->>'updated_by_email'), '') <> ''
                      or coalesce(btrim(m.metadata->>'editor_email'), '') <> ''
                      or coalesce(btrim(m.metadata->>'edited_by'), '') <> ''
                      or coalesce(btrim(m.metadata->>'updated_by'), '') <> ''
                      or coalesce(btrim(m.metadata->>'edited_by_name'), '') <> ''
                      or coalesce(btrim(m.metadata->>'updated_by_name'), '') <> ''
                  )
              )
          )
      )
),
ranked as (
    select
        f.*,
        count(*) over() as total_count
    from filtered f
)
select
    r.id,
    r.content,
    r.metadata,
    r.source_type,
    r.review_status,
    r.reviewed_by,
    r.reviewed_at,
    r.confidence_score,
    r.retrieval_count,
    r.last_retrieved_at,
    r.feedback_positive,
    r.feedback_negative,
    r.resolution_success_count,
    r.resolution_failure_count,
    r.agent_id,
    r.tenant_id,
    r.created_at,
    r.updated_at,
    r.total_count
from ranked r
cross join normalized n
order by
    case when n.sort_order = 'asc' then r.created_at end asc,
    case when n.sort_order = 'desc' then r.created_at end desc
offset (select offset_rows from normalized)
limit (select limit_rows from normalized);
$$;

revoke all on function public.list_memories_with_edited_state(
    text, text, text, text, integer, integer, text
) from public;
grant execute on function public.list_memories_with_edited_state(
    text, text, text, text, integer, integer, text
) to service_role;
