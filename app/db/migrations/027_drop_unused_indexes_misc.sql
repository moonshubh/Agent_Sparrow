-- 027_drop_unused_indexes_misc.sql
-- Purpose: Drop advisor-flagged unused indexes on project-owned tables

-- api_key_audit_log
DROP INDEX IF EXISTS public.idx_api_key_audit_log_user_operation;
DROP INDEX IF EXISTS public.idx_api_key_audit_log_uuid_operation;
DROP INDEX IF EXISTS public.idx_audit_user_uuid;

-- user_api_keys
DROP INDEX IF EXISTS public.ix_user_api_keys_api_key_type;
DROP INDEX IF EXISTS public.ix_user_api_keys_id;
DROP INDEX IF EXISTS public.ix_user_api_keys_is_active;
DROP INDEX IF EXISTS public.ix_user_api_keys_last_used_at;
DROP INDEX IF EXISTS public.ix_user_api_keys_user_id;
