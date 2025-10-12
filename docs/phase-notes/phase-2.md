# Phase 2 – Global Knowledge Dual Write Summary

- Added Supabase migrations (`032_create_sparrow_feedback.sql`, `033_create_sparrow_corrections.sql`) establishing feedback and corrections tables with RLS policies, jsonb metadata, pgvector embeddings, and supporting indexes.
- Introduced the global knowledge service package (`app/services/global_knowledge/`) with submission models, a `FeedbackEnhancer` for normalising slash command payloads, deterministic store keys, store helpers, and async persistence utilities that dual-write to Supabase and, when configured, the LangGraph Postgres store.
- Extended `SupabaseClient` with insert helpers for both tables and wired persistence flows to compute embeddings, validate vector dimensions, merge enhanced metadata/attachments, and upsert into the async store while remaining feature-flag driven.
- Implemented backend tests (`tests/backend/test_global_knowledge_persistence.py`) covering enhancer outputs, Supabase persistence behaviour, store flag gating, embedding dimension enforcement, and store upsert success paths.
