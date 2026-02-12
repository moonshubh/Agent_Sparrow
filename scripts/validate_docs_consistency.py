#!/usr/bin/env python3
"""
Validate documentation consistency against repository paths and FastAPI routes.

Checks:
1) Path-like markdown code spans resolve to existing files/directories.
2) `/api/v1/...` endpoint mentions match routes registered on `app.main`.
"""

from __future__ import annotations

import re
import sys
import os
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

DOC_FILES = [
    ROOT / "AGENTS.md",
    ROOT / "CLAUDE.md",
    *sorted((ROOT / "docs").rglob("*.md")),
]

PATH_TOKEN_RE = re.compile(r"`([^`\n]{1,220})`")
ENDPOINT_RE = re.compile(r"/api/v1/[A-Za-z0-9_./{}:-]+")
PARAM_RE = re.compile(r"\{[^}]+\}")

PATH_PREFIXES = ("app/", "frontend/", "docs/", "scripts/", "tests/", "docker/")
KNOWN_PATH_TOKENS = {
    "requirements.txt",
    "requirements-lock.txt",
    "runtime.txt",
    "railway.json",
    "railway.worker.json",
    "railpack.json",
    "frontend/railway.toml",
    "frontend/package.json",
    "frontend/eslint.config.mjs",
    "frontend/middleware.ts",
    "frontend/next.config.js",
    "frontend/next.config.ts",
    "pyproject.toml",
    "mypy.ini",
}


def _is_path_token(token: str) -> bool:
    token = token.strip()
    return token.startswith(PATH_PREFIXES) or token in KNOWN_PATH_TOKENS


def _normalize_endpoint(path: str) -> str:
    path = path.rstrip("/") if path != "/api/v1/" else path
    return PARAM_RE.sub("{param}", path)


def check_path_tokens() -> list[tuple[str, int, str]]:
    missing: list[tuple[str, int, str]] = []
    for doc in DOC_FILES:
        text = doc.read_text(encoding="utf-8", errors="ignore")
        for lineno, line in enumerate(text.splitlines(), start=1):
            for token in PATH_TOKEN_RE.findall(line):
                token = token.strip()
                if not _is_path_token(token):
                    continue
                if "::" in token:
                    token = token.split("::", 1)[0]
                if not (ROOT / token).exists():
                    missing.append((doc.relative_to(ROOT).as_posix(), lineno, token))
    return missing


def load_api_routes() -> set[str]:
    if os.getenv("DOCS_VALIDATE_SKIP_ROUTE_IMPORT", "").strip().lower() in {
        "1",
        "true",
        "yes",
    }:
        print("[info] Skipping app.main import for route validation (DOCS_VALIDATE_SKIP_ROUTE_IMPORT=1).")
        return set()

    # Import app.main lazily so path checks can still run if imports fail.
    try:
        if str(ROOT) not in sys.path:
            sys.path.insert(0, str(ROOT))
        from app.main import app  # type: ignore
    except Exception as exc:  # pragma: no cover - best effort for local env differences
        print(f"[warn] Could not import app.main for endpoint validation: {exc}")
        return set()

    return {
        getattr(route, "path", "")
        for route in app.routes
        if getattr(route, "path", "").startswith("/api/v1/")
    }


def check_endpoint_mentions(routes: set[str]) -> list[tuple[str, int, str]]:
    if not routes:
        return []

    normalized_routes = {_normalize_endpoint(route) for route in routes}
    unmatched: list[tuple[str, int, str]] = []

    for doc in DOC_FILES:
        text = doc.read_text(encoding="utf-8", errors="ignore")
        for lineno, line in enumerate(text.splitlines(), start=1):
            for endpoint in ENDPOINT_RE.findall(line):
                # Skip file-path mentions like /api/v1/endpoints/foo.py
                if ".py" in endpoint or "/endpoints/" in endpoint:
                    continue
                normalized = _normalize_endpoint(endpoint)
                if endpoint in routes or normalized in normalized_routes:
                    continue
                unmatched.append(
                    (doc.relative_to(ROOT).as_posix(), lineno, endpoint)
                )
    return unmatched


def main() -> int:
    missing_paths = check_path_tokens()
    routes = load_api_routes()
    unmatched_endpoints = check_endpoint_mentions(routes)

    if missing_paths:
        print("Missing path references:")
        for doc, lineno, token in missing_paths:
            print(f"  {doc}:{lineno}: {token}")

    if unmatched_endpoints:
        print("Unmatched /api/v1 endpoint mentions:")
        for doc, lineno, endpoint in unmatched_endpoints:
            print(f"  {doc}:{lineno}: {endpoint}")

    print(
        "Summary:",
        f"missing_paths={len(missing_paths)}",
        f"unmatched_endpoints={len(unmatched_endpoints)}",
        f"routes_loaded={len(routes)}",
    )

    return 1 if missing_paths or unmatched_endpoints else 0


if __name__ == "__main__":
    raise SystemExit(main())
