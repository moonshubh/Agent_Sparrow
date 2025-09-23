-- Migration: Allow 'openai' as a valid api_key_type
-- Safe to run multiple times (drops then recreates constraint)
-- Apply this in Supabase SQL editor or your migration runner.

ALTER TABLE user_api_keys
  DROP CONSTRAINT IF EXISTS valid_api_key_type;

ALTER TABLE user_api_keys
  ADD CONSTRAINT valid_api_key_type
  CHECK (api_key_type IN ('gemini', 'openai', 'tavily', 'firecrawl'));