#!/usr/bin/env python3
"""Generate deterministic documentation artifacts for Ref-first maintenance.

Outputs:
- docs/model-catalog.md
- docs/dependency-watchlist.md
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
MODELS_PATH = ROOT / "app" / "core" / "config" / "models.yaml"
REQS_PATH = ROOT / "requirements.txt"
PACKAGE_PATH = ROOT / "frontend" / "package.json"

MODEL_CATALOG_PATH = ROOT / "docs" / "model-catalog.md"
DEPENDENCY_WATCHLIST_PATH = ROOT / "docs" / "dependency-watchlist.md"

BACKEND_WATCHLIST = {
    "langgraph": "Core orchestration behavior and checkpoint APIs can shift across minors.",
    "langchain": "Agent middleware/tool orchestration behavior can change with v1 updates.",
    "langchain-core": "Message/tool runtime contracts used throughout unified agent stack.",
    "langchain-google-genai": "Provider integration layer for Gemini routing and tool usage.",
    "deepagents": "Primary middleware pattern library used by coordinator/subagents.",
    "ag-ui-langgraph": "Protocol adapter for AG-UI stream/event conversion.",
    "ag-ui-protocol": "Wire-level event schema for frontend/backend streaming compatibility.",
    "google-genai": "Direct Gemini SDK used in FeedMe and supporting services.",
    "supabase": "DB/auth/storage client contracts and API behavior.",
    "mem0ai": "Long-term memory backend semantics and write/retrieval behavior.",
    "vecs": "Vector collection/index behavior for mem0 on Supabase.",
    "pgvector": "Vector index/query behavior for embeddings.",
    "celery": "Background task execution semantics and retry behavior.",
    "redis": "Rate limiting, queues, and cache stability under concurrency.",
    "openai": "OpenAI-compatible clients used by provider wrappers.",
}

FRONTEND_WATCHLIST = {
    "next": "App Router, middleware, and runtime behavior change frequently.",
    "react": "Core rendering/state APIs used across all feature modules.",
    "react-dom": "Server/client rendering integration and hooks behavior.",
    "@supabase/supabase-js": "Auth/session and edge-safe client behavior.",
    "@tiptap/core": "Editor schema/extension APIs used by FeedMe and Memory UI.",
    "@tiptap/react": "TipTap React bindings used in editors.",
    "@react-three/fiber": "3D rendering/event lifecycle for Memory graph.",
    "@react-three/drei": "Helper abstractions for scene/camera/interaction.",
    "three": "Rendering engine core; major updates can affect scene code.",
    "@tanstack/react-query": "Data cache invalidation and async state behavior.",
    "zod": "Runtime validation contracts for frontend API payloads.",
    "react-hook-form": "Form validation/resolver behavior for settings/auth screens.",
    "framer-motion": "Animation APIs used by FeedMe/LibreChat interactive components.",
    "streamdown": "Streaming markdown rendering in chat responses.",
}

# Intentionally scoped to standard requirement specifiers used in this repo.
# URL/editable/include-style entries are ignored by design.
_REQ_LINE_RE = re.compile(r"^([A-Za-z0-9_.-]+)(\[[^\]]+\])?\s*(==|>=|<=|~=|>|<)?\s*([^\s#]+)?")


def _normalize_requirement_name(name: str) -> str:
    return name.lower().replace("_", "-")


def _parse_requirements(path: Path) -> dict[str, str]:
    parsed: dict[str, str] = {}

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or line.startswith("--"):
            continue

        # Ignore environment markers (e.g., "; python_version >= '3.11'") for version display.
        line = line.split(";", 1)[0].strip()

        match = _REQ_LINE_RE.match(line)
        if not match:
            continue

        name, _extras, op, version = match.groups()
        norm_name = _normalize_requirement_name(name)

        # Track pinned or constrained versions for visibility.
        if op and version:
            parsed[norm_name] = f"{op}{version}"
        else:
            parsed[norm_name] = "(unpinned)"

    return parsed


def _infer_provider(model_id: str, explicit_provider: str | None) -> str:
    if explicit_provider:
        return explicit_provider
    if model_id.startswith("gemini-") or model_id.startswith("models/"):
        return "google"
    if model_id.startswith("grok-"):
        return "xai"
    if "/" in model_id:
        return "openrouter"
    return "google"


def _collect_models(node: Any, path: list[str], out: list[dict[str, Any]]) -> None:
    if isinstance(node, dict):
        if isinstance(node.get("model_id"), str):
            model_id = node["model_id"]
            out.append(
                {
                    "key": ".".join(path),
                    "model_id": model_id,
                    "provider": _infer_provider(model_id, node.get("provider")),
                    "temperature": node.get("temperature", "--"),
                    "context_window": node.get("context_window", "--"),
                    "rpm": node.get("rate_limits", {}).get("rpm", "--"),
                    "rpd": node.get("rate_limits", {}).get("rpd", "--"),
                }
            )

        for key, value in node.items():
            _collect_models(value, path + [str(key)], out)


def _load_models() -> list[dict[str, Any]]:
    data = yaml.safe_load(MODELS_PATH.read_text(encoding="utf-8"))
    collected: list[dict[str, Any]] = []
    _collect_models(data, [], collected)
    return sorted(collected, key=lambda item: item["key"])


def _render_model_catalog(models: list[dict[str, Any]]) -> str:
    lines = [
        "# Model Catalog",
        "",
        "Canonical snapshot of runtime model configuration from `app/core/config/models.yaml`.",
        "",
        "Refresh command: `python scripts/refresh_ref_docs.py`.",
        "",
        "## Active Model Entries",
        "",
        "| Config Key | Model ID | Provider | Temp | Context Window | RPM | RPD |",
        "|------------|----------|----------|------|----------------|-----|-----|",
    ]

    for model in models:
        lines.append(
            "| {key} | `{model_id}` | `{provider}` | {temperature} | {context_window} | {rpm} | {rpd} |".format(
                **model
            )
        )

    lines.extend(
        [
            "",
            "## Notes",
            "",
            "- This file is generated and should stay aligned with `app/core/config/models.yaml`.",
            "- Unknown provider/model drift should be fixed in `models.yaml`, then regenerated.",
            "- Use this catalog as the source for Ref indexing and operational reviews.",
        ]
    )

    return "\n".join(lines) + "\n"


def _load_frontend_dependencies() -> dict[str, str]:
    package_data = json.loads(PACKAGE_PATH.read_text(encoding="utf-8"))
    merged: dict[str, str] = {}
    for section in ("dependencies", "devDependencies"):
        merged.update(package_data.get(section, {}))
    return merged


def _render_dependency_watchlist(
    backend: dict[str, str], frontend: dict[str, str]
) -> str:
    lines = [
        "# Dependency Watchlist",
        "",
        "High-drift dependencies to monitor for API/behavior changes.",
        "",
        "Cadence: biweekly review + event-driven refresh when `requirements.txt`,",
        "`frontend/package.json`, or `app/core/config/models.yaml` changes.",
        "",
        "Refresh command: `python scripts/refresh_ref_docs.py`.",
        "",
        "## Backend Watchlist",
        "",
        "| Package | Pinned Version | Why It Is Monitored |",
        "|---------|----------------|---------------------|",
    ]

    for package, reason in sorted(BACKEND_WATCHLIST.items()):
        version = backend.get(_normalize_requirement_name(package), "(not found)")
        lines.append(f"| `{package}` | `{version}` | {reason} |")

    lines.extend(
        [
            "",
            "## Frontend Watchlist",
            "",
            "| Package | Pinned Version | Why It Is Monitored |",
            "|---------|----------------|---------------------|",
        ]
    )

    for package, reason in sorted(FRONTEND_WATCHLIST.items()):
        version = frontend.get(package, "(not found)")
        lines.append(f"| `{package}` | `{version}` | {reason} |")

    lines.extend(
        [
            "",
            "## Cost Policy",
            "",
            "- Default to Ref GitHub resource sync for internal docs (incremental and low-overhead).",
            "- Keep active Ref verification usage in a budget band of ~150-250 credits/month.",
            "- Prefer targeted Ref lookups at implementation time over broad periodic sweeps.",
            "",
            "## Related Docs",
            "",
            "- `docs/ref-source-registry.md`",
            "- `docs/ref-gaps.md`",
            "- `docs/ref-index-plan.md`",
            "- `docs/model-catalog.md`",
        ]
    )

    return "\n".join(lines) + "\n"


def _write_if_changed(path: Path, content: str) -> bool:
    existing = path.read_text(encoding="utf-8") if path.exists() else None
    if existing == content:
        return False

    path.write_text(content, encoding="utf-8")
    return True


def main() -> int:
    models = _load_models()
    backend = _parse_requirements(REQS_PATH)
    frontend = _load_frontend_dependencies()

    changed = []

    if _write_if_changed(MODEL_CATALOG_PATH, _render_model_catalog(models)):
        changed.append(MODEL_CATALOG_PATH.relative_to(ROOT).as_posix())

    if _write_if_changed(
        DEPENDENCY_WATCHLIST_PATH,
        _render_dependency_watchlist(backend, frontend),
    ):
        changed.append(DEPENDENCY_WATCHLIST_PATH.relative_to(ROOT).as_posix())

    if changed:
        print("Updated:")
        for item in changed:
            print(f"  - {item}")
    else:
        print("No changes needed.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
