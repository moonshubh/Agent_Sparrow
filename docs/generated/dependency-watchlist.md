# Dependency Watchlist

High-drift dependencies to monitor for API/behavior changes.

Cadence: biweekly review + event-driven refresh when `requirements.txt`,
`frontend/package.json`, or `app/core/config/models.yaml` changes.

Refresh command: `python scripts/refresh_ref_docs.py`.

## Backend Watchlist

| Package | Pinned Version | Why It Is Monitored |
|---------|----------------|---------------------|
| `ag-ui-langgraph` | `==0.0.24` | Protocol adapter for AG-UI stream/event conversion. |
| `ag-ui-protocol` | `==0.1.10` | Wire-level event schema for frontend/backend streaming compatibility. |
| `celery` | `==5.6.2` | Background task execution semantics and retry behavior. |
| `deepagents` | `==0.3.10` | Primary middleware pattern library used by coordinator/subagents. |
| `google-genai` | `==1.61.0` | Direct Gemini SDK used in FeedMe and supporting services. |
| `langchain` | `==1.2.8` | Agent middleware/tool orchestration behavior can change with v1 updates. |
| `langchain-core` | `==1.2.8` | Message/tool runtime contracts used throughout unified agent stack. |
| `langchain-google-genai` | `==4.2.0` | Provider integration layer for Gemini routing and tool usage. |
| `langgraph` | `==1.0.7` | Core orchestration behavior and checkpoint APIs can shift across minors. |
| `mem0ai` | `==1.0.3` | Long-term memory backend semantics and write/retrieval behavior. |
| `openai` | `==2.16.0` | OpenAI-compatible clients used by provider wrappers. |
| `pgvector` | `==0.3.6` | Vector index/query behavior for embeddings. |
| `redis` | `==6.4.0` | Rate limiting, queues, and cache stability under concurrency. |
| `supabase` | `==2.27.3` | DB/auth/storage client contracts and API behavior. |
| `vecs` | `==0.4.5` | Vector collection/index behavior for mem0 on Supabase. |

## Frontend Watchlist

| Package | Pinned Version | Why It Is Monitored |
|---------|----------------|---------------------|
| `@react-three/drei` | `^10.7.7` | Helper abstractions for scene/camera/interaction. |
| `@react-three/fiber` | `^9.5.0` | 3D rendering/event lifecycle for Memory graph. |
| `@supabase/supabase-js` | `^2.94.0` | Auth/session and edge-safe client behavior. |
| `@tanstack/react-query` | `5.90.20` | Data cache invalidation and async state behavior. |
| `@tiptap/core` | `3.19.0` | Editor schema/extension APIs used by FeedMe and Memory UI. |
| `@tiptap/react` | `3.19.0` | TipTap React bindings used in editors. |
| `framer-motion` | `^12.31.0` | Animation APIs used by FeedMe/LibreChat interactive components. |
| `next` | `^16.1.6` | App Router, middleware, and runtime behavior change frequently. |
| `react` | `19.2.4` | Core rendering/state APIs used across all feature modules. |
| `react-dom` | `19.2.4` | Server/client rendering integration and hooks behavior. |
| `react-hook-form` | `^7.71.1` | Form validation/resolver behavior for settings/auth screens. |
| `streamdown` | `2.1.0` | Streaming markdown rendering in chat responses. |
| `three` | `^0.182.0` | Rendering engine core; major updates can affect scene code. |
| `zod` | `^4.3.6` | Runtime validation contracts for frontend API payloads. |

## Cost Policy

- Default to Ref GitHub resource sync for internal docs (incremental and low-overhead).
- Keep active Ref verification usage in a budget band of ~150-250 credits/month.
- Prefer targeted Ref lookups at implementation time over broad periodic sweeps.

## Related Docs

- `docs/references/ref-source-registry.md`
- `docs/references/ref-gaps.md`
- `docs/references/ref-index-plan.md`
- `docs/generated/model-catalog.md`
