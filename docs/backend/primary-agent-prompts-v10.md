# Primary Agent — v10 System Prompt Migration

This note documents the switch to the v10 system prompt and the removal of legacy prompt modules.

## What changed

- Added v10 prompt implementation:
  - File: `app/agents/primary/primary_agent/prompts/agent_sparrow_v10.py`
  - Exports: `AgentSparrowV10`, `V10Config`
- Removed legacy prompt modules and loader:
  - `app/agents/primary/primary_agent/prompts/agent_sparrow_v9_prompts.py` (deleted)
  - `app/agents/primary/primary_agent/prompts/agent_sparrow_prompts.py` (deleted)
  - `app/agents/primary/primary_agent/prompts/prompt_loader.py` (deleted)
- Simplified prompt exports:
  - `app/agents/primary/primary_agent/prompts/__init__.py` now exports only `AgentSparrowV10`, `V10Config`, `EmotionTemplates`, `ResponseFormatter`.
- Reasoning engine now composes v10 by default for all phases (analysis, generation, refinement):
  - File: `app/agents/primary/primary_agent/reasoning/reasoning_engine.py`
  - Method: `_compose_system_prompt()` selects v10 (no v9 fallback).
- Cleaned unused prompt import in primary agent entry:
  - File: `app/agents/primary/primary_agent/agent.py`

## Configuration

- New setting: `PRIMARY_AGENT_PROMPT_VERSION` (default: `v10`).
  - Field: `settings.primary_agent_prompt_version` in `app/core/settings.py`.
  - Note: Legacy values are ignored; v10 is always used after this migration.

## Runtime behavior (prompt/output contract)

The v10 system prompt enforces this Markdown structure in user‑visible answers:
- Empathetic Opening → Solution Overview → Try Now — Immediate Actions → Full Fix (step‑by‑step) → Additional Context → Pro Tips → Supportive Closing.
- “Quick Fix” was replaced by “Try Now — Immediate Actions”.
- Guardrails reiterated: no chain‑of‑thought exposure, no external URLs in final text, no sensitive credentials; ask for minimal targeted details when evidence is insufficient.

## Source of truth / APIs touched

- Prompt classes: `prompts/agent_sparrow_v10.py` (new), old classes removed.
- Reasoning pipeline: `reasoning_engine._compose_system_prompt*()` uses v10 for:
  - Unified analysis, enhanced generation, self‑critique/refinement.
- Primary agent runtime: unchanged transport; prompt selection now centralized to v10.

## Migration & rollback

- Existing deployments automatically use v10 (default setting). No code changes required in callers.
- Rolling back to v9 is not supported (v9 modules were removed). If rollback is required, restore those files and rewire `_compose_system_prompt()` accordingly.

## Developer notes

- To inspect the active system prompt at runtime: see `_compose_system_prompt()` in `reasoning_engine.py`.
- To customize brand/agent labels or omit emotion examples, use `V10Config` when building via `AgentSparrowV10.build_system_prompt()`.
