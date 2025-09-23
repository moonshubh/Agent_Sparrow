-- Migration: 016_add_openai_api_key_type.sql
-- Purpose: Allow 'openai' as a valid api_key_type for user_api_keys
-- Safe, idempotent migration: drops existing CHECK constraint if present, then recreates with the expanded set.

BEGIN;

-- Drop the existing CHECK constraint if it exists
ALTER TABLE user_api_keys
  DROP CONSTRAINT IF EXISTS valid_api_key_type;

-- Recreate the CHECK constraint including 'openai'
ALTER TABLE user_api_keys
  ADD CONSTRAINT valid_api_key_type
  CHECK (api_key_type IN ('gemini', 'openai', 'tavily', 'firecrawl'));

-- Optional: comment updates for documentation clarity
COMMENT ON COLUMN user_api_keys.api_key_type IS 'Type of API key: gemini, openai, tavily, firecrawl';

COMMIT;