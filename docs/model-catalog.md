# Model Catalog

Canonical snapshot of runtime model configuration from `app/core/config/models.yaml`.

Refresh command: `python scripts/refresh_ref_docs.py`.

## Active Model Entries

| Config Key | Model ID | Provider | Temp | Context Window | RPM | RPD |
|------------|----------|----------|------|----------------|-----|-----|
| coordinators.google | `gemini-3-flash-preview` | `google` | 0.3 | 1048576 | 1000 | 10000 |
| coordinators.google_with_subagents | `gemini-3-flash-preview` | `google` | 0.3 | 1048576 | 1000 | 10000 |
| coordinators.minimax | `minimax/MiniMax-M2.5` | `openrouter` | 1.0 | 204800 | 100 | 5000 |
| coordinators.minimax_with_subagents | `minimax/MiniMax-M2.5` | `openrouter` | 1.0 | 204800 | 80 | 4000 |
| coordinators.openrouter | `x-ai/grok-4.1-fast` | `openrouter` | 0.2 | 2000000 | 60 | 1000 |
| coordinators.openrouter_with_subagents | `x-ai/grok-4.1-fast` | `openrouter` | 0.2 | 2000000 | 45 | 750 |
| coordinators.xai | `grok-4-1-fast-reasoning` | `xai` | 0.2 | 2000000 | 60 | 1000 |
| coordinators.xai_with_subagents | `grok-4-1-fast-reasoning` | `xai` | 0.2 | 2000000 | 45 | 750 |
| internal.embedding | `models/gemini-embedding-001` | `google` | -- | 2048 | 3000 | 1000000 |
| internal.feedme | `gemini-2.5-flash-lite` | `google` | 0.3 | 1048576 | 4000 | 1000000 |
| internal.grounding | `gemini-2.5-flash` | `google` | 0.2 | 1048576 | 1000 | 10000 |
| internal.helper | `gemini-2.5-flash-lite` | `google` | 0.2 | 1048576 | 4000 | 1000000 |
| internal.image | `gemini-3-pro-image-preview` | `google` | 1.0 | 1048576 | 20 | 250 |
| internal.minimax_tools | `minimax/MiniMax-M2.5` | `openrouter` | 1.0 | 204800 | 120 | 5000 |
| internal.summarizer | `gemini-2.5-flash-preview-09-2025` | `google` | 0.2 | 1048576 | 1000 | 10000 |
| subagents._default | `minimax/MiniMax-M2.5` | `openrouter` | 1.0 | 204800 | 60 | 1000 |
| zendesk.coordinators.google | `gemini-3-flash-preview` | `google` | 0.3 | 1048576 | 150 | 5000 |
| zendesk.coordinators.google_with_subagents | `gemini-3-flash-preview` | `google` | 0.3 | 1048576 | 120 | 4000 |
| zendesk.coordinators.openrouter | `x-ai/grok-4.1-fast` | `openrouter` | 0.2 | 2000000 | 45 | 750 |
| zendesk.coordinators.openrouter_with_subagents | `x-ai/grok-4.1-fast` | `openrouter` | 0.2 | 2000000 | 35 | 600 |
| zendesk.coordinators.xai | `grok-4-1-fast-reasoning` | `xai` | 0.2 | 2000000 | 45 | 750 |
| zendesk.coordinators.xai_with_subagents | `grok-4-1-fast-reasoning` | `xai` | 0.2 | 2000000 | 35 | 600 |
| zendesk.subagents._default | `minimax/MiniMax-M2.5` | `openrouter` | 1.0 | 204800 | 60 | 1000 |

## Notes

- This file is generated and should stay aligned with `app/core/config/models.yaml`.
- Unknown provider/model drift should be fixed in `models.yaml`, then regenerated.
- Use this catalog as the source for Ref indexing and operational reviews.
