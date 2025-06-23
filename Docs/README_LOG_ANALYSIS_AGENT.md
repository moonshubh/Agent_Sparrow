# Log Analysis Agent – Technical Documentation

This document explains the architecture, configuration, and usage of the **Mailbird Log Analysis Agent** (Task 4).

## Overview
The Log Analysis Agent ingests Mailbird log files, parses them, and employs Google Gemini 2.5 Pro to generate a structured health report containing:
* Executive summary
* Identified issues with root-cause reasoning
* Proposed solutions (optionally enriched via web search)

## Key Components
| File/Module | Purpose |
|-------------|---------|
| `app/agents_v2/log_analysis_agent/agent.py` | LangGraph node orchestrating parsing → LLM analysis, now with structured `structlog` audit logs. |
| `parsers.py` | Regex-based parser converting raw log lines to structured JSON suitable for the prompt. |
| `chunk_processor.py` | Multiprocessing helper for large logs (10 k lines/chunk by default). |
| `error_patterns_schema.py` | Pydantic schema + YAML loader for configurable error patterns. |
| `app/config/error_patterns.yaml` | Initial set of 5 common error patterns. |
| `app/core/logging_config.py` | Central structured logging setup using **structlog**. |

## Environment Variables
| Variable | Description |
|----------|-------------|
| `GEMINI_API_KEY` | API key for Google Gemini model. |
| `LOG_LEVEL` | Optional. Default `INFO`. Controls structlog verbosity. |

## Execution Flow
1. **Parsing** – Raw log content is parsed (`parsers.py` or `chunk_processor.py`).
2. **LLM Analysis** – Gemini 1.5 Pro analyzes parsed JSON via prompt template.
3. **Web Search (optional)** – If `enable_websearch=true`, Tavily tool is bound.
4. **Report** – The agent returns `StructuredLogAnalysisOutput` JSON.
5. **Audit Logs** – Each run emits JSON lines with a shared `trace_id` for correlation.

Example log entry:
```json
{
  "timestamp": "2025-06-11T07:10:00.123Z",
  "level": "info",
  "event": "analysis_complete",
  "trace_id": "b77d9c...",
  "logger": "log_analysis_agent"
}
```

## Running Tests
```bash
pytest -q
```
Benchmarks (requires pytest-benchmark) will execute `chunk_processor` on a 50 k-line sample.

## Extending Error Patterns
Add entries to `app/config/error_patterns.yaml` following the same keys. The loader validates regex and metadata.

## Performance Benchmarks
Initial benchmark (M1 Pro): ~1.8 s to parse 50 k lines across six CPU cores.

## Future Work
* Integrate solution database (Task 4.2 – skipped for now).
* Enhance parser heuristics for multiline stack traces.
* Expose the agent via REST endpoint with file upload.
