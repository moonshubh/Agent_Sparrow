#!/usr/bin/env python3
"""Run six live AG-UI capability probes and capture evidence-rich pass/fail matrix.

This script sends real `/api/v1/agui/stream` requests (not direct tool invocations),
captures SSE events, slices backend logs for each query, and writes a JSON report that
includes verdicts and raw evidence snippets.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import uuid
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import httpx


DEFAULT_BASE_URL = "http://127.0.0.1:8000"
DEFAULT_BACKEND_LOG = Path("system_logs/backend/backend.log")
REPO_ROOT = Path(__file__).resolve().parents[1]

if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

KEYWORD_PATTERN = re.compile(
    r"web_search|search|firecrawl|tavily|minimax|mcp|image|generate|gemini|"
    r"google_ai|ai_studio|nano-banana|nano-banana-pro|artifact|skill|tool_call|"
    r"tool_use|function_call|error|failed|timeout|401|403|429|500",
    re.IGNORECASE,
)


@dataclass
class CaseSpec:
    id: str
    category: str
    prompt: str
    provider: str
    model: str
    agent_mode: str
    force_websearch: bool


@dataclass
class CaseResult:
    id: str
    category: str
    timestamp_start: float
    timestamp_end: float
    thread_id: str
    run_id: str
    http_status: int | None
    run_finished: bool
    run_error_messages: list[str]
    event_counts: dict[str, int]
    tool_calls: list[str]
    custom_events: list[str]
    text_preview: str
    matched_log_lines: list[str]
    degraded_fallback: bool
    verdict: str
    verdict_reasons: list[str]


def _build_cases() -> list[CaseSpec]:
    return [
        CaseSpec(
            id="C1",
            category="web_search_minimax",
            prompt=(
                "Use web search: latest cricket news today February 13 2026. "
                "Cite source URLs."
            ),
            provider="minimax",
            model="minimax/MiniMax-M2.5",
            agent_mode="general",
            force_websearch=True,
        ),
        CaseSpec(
            id="C2",
            category="web_search_escalation",
            prompt=(
                "Research this deeply: compare at least 3 sources on AI chip export "
                "controls updates in 2026, include any policy differences, and cite "
                "URLs. Use deeper crawling when snippets are insufficient."
            ),
            provider="minimax",
            model="minimax/MiniMax-M2.5",
            agent_mode="research_expert",
            force_websearch=True,
        ),
        CaseSpec(
            id="C3",
            category="image_generation_primary",
            prompt=(
                "Generate an image of a small solid blue square on white background "
                "and return it as an image artifact."
            ),
            provider="google",
            model="gemini-3-flash-preview",
            agent_mode="general",
            force_websearch=False,
        ),
        CaseSpec(
            id="C4",
            category="image_generation_fallback",
            prompt=(
                "Generate an image of a minimal red circle and return it as an image "
                "artifact. If the primary image model is unavailable, use automatic "
                "fallback and still return the image."
            ),
            provider="google",
            model="gemini-3-flash-preview",
            agent_mode="general",
            force_websearch=False,
        ),
        CaseSpec(
            id="C5",
            category="artifact_generation",
            prompt=(
                "Create an article artifact titled 'AG-UI Verification Artifact' with "
                "sections Summary, Findings, and Next Steps. Return only a short confirmation "
                "in chat."
            ),
            provider="minimax",
            model="minimax/MiniMax-M2.5",
            agent_mode="general",
            force_websearch=False,
        ),
        CaseSpec(
            id="C6",
            category="dynamic_skill_loading",
            prompt=(
                "Use root-cause-tracing skill to analyze intermittent OAuth login failures "
                "and give a concise diagnosis + next checks."
            ),
            provider="minimax",
            model="minimax/MiniMax-M2.5",
            agent_mode="general",
            force_websearch=False,
        ),
    ]


def _event_type(event: dict[str, Any]) -> str:
    value = event.get("type")
    if isinstance(value, str) and value:
        return value
    return "UNKNOWN"


def _build_payload(spec: CaseSpec, thread_id: str, run_id: str) -> dict[str, Any]:
    return {
        "threadId": thread_id,
        "runId": run_id,
        "messages": [
            {
                "id": f"user-{uuid.uuid4()}",
                "role": "user",
                "content": spec.prompt,
            }
        ],
        "state": {},
        "tools": [],
        "context": [],
        "forwardedProps": {
            "session_id": thread_id,
            "trace_id": run_id,
            "provider": spec.provider,
            "model": spec.model,
            "agent_type": "primary",
            "agent_mode": spec.agent_mode,
            "use_server_memory": False,
            "force_websearch": spec.force_websearch,
        },
    }


def _slice_log_lines(log_path: Path, start_offset: int, max_lines: int = 500) -> list[str]:
    if not log_path.exists():
        return []
    with log_path.open("rb") as f:
        f.seek(start_offset)
        chunk = f.read()
    text = chunk.decode("utf-8", errors="replace")
    lines = [line.rstrip("\n") for line in text.splitlines()]
    if len(lines) > max_lines:
        lines = lines[-max_lines:]
    return lines


def _match_keywords(lines: list[str], run_id: str, thread_id: str) -> list[str]:
    matched: list[str] = []
    for line in lines:
        if run_id in line or thread_id in line or KEYWORD_PATTERN.search(line):
            matched.append(line)
    return matched


def _evaluate_verdict(spec: CaseSpec, result: CaseResult) -> tuple[str, list[str]]:
    reasons: list[str] = []

    if result.http_status != 200:
        reasons.append(f"HTTP status was {result.http_status}")
    if not result.run_finished:
        reasons.append("RUN_FINISHED event missing")

    tools = {name for name in result.tool_calls if name}
    custom = {name for name in result.custom_events if name}
    log_blob = "\n".join(result.matched_log_lines).lower()

    if spec.category == "web_search_minimax":
        if not (
            "minimax_web_search_invoked" in log_blob
            or "firecrawl_search_tool_invoked" in log_blob
            or "tavily_search_tool" in log_blob
            or any("search" in t.lower() for t in tools)
        ):
            reasons.append("No web search tool evidence found")

    elif spec.category == "web_search_escalation":
        if not (
            "firecrawl_search_tool_invoked" in log_blob
            or "tavily_search_tool_invoked" in log_blob
            or "tavily_extract_tool_invoked" in log_blob
        ):
            reasons.append("No Firecrawl/Tavily escalation evidence found")

    elif spec.category == "image_generation_primary":
        if "generate_image_tool_invoked" not in log_blob and "generate_image" not in tools:
            reasons.append("Image generation tool was not invoked")
        if "gemini-3-pro-image-preview" not in log_blob and "nano-banana-pro" not in log_blob:
            reasons.append("Primary image model evidence missing")
        if "image_artifact" not in custom and "image_artifact_emitted" not in log_blob:
            reasons.append("No image artifact evidence emitted")

    elif spec.category == "image_generation_fallback":
        fallback_indicators = [
            "fallback_used",
            "model_used=gemini-2.5-flash",
            "fallback_model",
            "generate_image_model_failed",
        ]
        if not any(ind in log_blob for ind in fallback_indicators):
            reasons.append("No automatic fallback evidence captured")
        if "generate_image_tool_invoked" not in log_blob and "generate_image" not in tools:
            reasons.append("Image generation tool was not invoked")

    elif spec.category == "artifact_generation":
        if "write_article" not in tools and "write_article" not in log_blob:
            reasons.append("write_article tool not invoked")
        if "article_artifact" not in custom and "article_artifact_emitted" not in log_blob:
            reasons.append("No article artifact event emitted")

    elif spec.category == "dynamic_skill_loading":
        skill_log_evidence = (
            "auto-detected skills" in log_blob
            or "loaded skill: root-cause-tracing" in log_blob
        )
        if not skill_log_evidence and "read_skill" not in {t.lower() for t in tools}:
            reasons.append("No dynamic skill loading evidence logged")
        if "root-cause-tracing" not in log_blob and "read_skill" not in {
            t.lower() for t in tools
        }:
            reasons.append("Expected root-cause-tracing skill was not loaded")

    if result.degraded_fallback:
        reasons.append("Degraded fallback path was emitted during run")

    return ("PASS", []) if not reasons else ("FAIL", reasons)


def _run_case(base_url: str, spec: CaseSpec, backend_log: Path, timeout_sec: float) -> CaseResult:
    run_id = f"verify-{spec.id.lower()}-{uuid.uuid4()}"
    thread_id = f"verify-thread-{spec.id.lower()}-{int(time.time())}"
    payload = _build_payload(spec, thread_id, run_id)

    start_offset = backend_log.stat().st_size if backend_log.exists() else 0

    started = time.time()
    http_status: int | None = None
    run_finished = False
    run_error_messages: list[str] = []
    event_counts: dict[str, int] = {}
    tool_calls: list[str] = []
    custom_events: list[str] = []
    text_chunks: list[str] = []

    url = f"{base_url.rstrip('/')}/api/v1/agui/stream"
    timeout = httpx.Timeout(timeout_sec, connect=20.0)

    try:
        with httpx.Client(timeout=timeout) as client:
            with client.stream("POST", url, json=payload) as response:
                http_status = response.status_code
                for raw_line in response.iter_lines():
                    if not raw_line:
                        continue
                    line = raw_line if isinstance(raw_line, str) else raw_line.decode()
                    if not line.startswith("data:"):
                        continue
                    data_part = line[5:].strip()
                    if not data_part:
                        continue
                    try:
                        event = json.loads(data_part)
                    except json.JSONDecodeError:
                        continue

                    event_type = _event_type(event)
                    event_counts[event_type] = event_counts.get(event_type, 0) + 1

                    if event_type == "TOOL_CALL_START":
                        tool_name = event.get("toolCallName") or event.get("toolName")
                        if isinstance(tool_name, str):
                            tool_calls.append(tool_name)
                    elif event_type == "CUSTOM":
                        name = event.get("name")
                        if isinstance(name, str):
                            custom_events.append(name)
                    elif event_type == "RUN_ERROR":
                        msg = str(event.get("message") or "")
                        if msg:
                            run_error_messages.append(msg)
                    elif event_type == "TEXT_MESSAGE_CONTENT":
                        delta = event.get("delta")
                        if isinstance(delta, str) and delta:
                            text_chunks.append(delta)
                    elif event_type == "RUN_FINISHED":
                        run_finished = True
                        break
    except Exception as exc:
        run_error_messages.append(f"transport_error:{type(exc).__name__}:{exc}")

    # Give logger a brief flush window.
    time.sleep(0.5)

    ended = time.time()
    log_slice = _slice_log_lines(backend_log, start_offset)
    matched = _match_keywords(log_slice, run_id=run_id, thread_id=thread_id)
    degraded = any("agui_stream_degraded_fallback_emitted" in line for line in matched)

    result = CaseResult(
        id=spec.id,
        category=spec.category,
        timestamp_start=started,
        timestamp_end=ended,
        thread_id=thread_id,
        run_id=run_id,
        http_status=http_status,
        run_finished=run_finished,
        run_error_messages=run_error_messages,
        event_counts=event_counts,
        tool_calls=tool_calls,
        custom_events=custom_events,
        text_preview="".join(text_chunks).strip()[:500],
        matched_log_lines=matched,
        degraded_fallback=degraded,
        verdict="PENDING",
        verdict_reasons=[],
    )

    verdict, reasons = _evaluate_verdict(spec, result)
    result.verdict = verdict
    result.verdict_reasons = reasons
    return result


def _check_env_snapshot() -> dict[str, str]:
    from app.core.settings import get_settings

    settings = get_settings()
    keys = {
        "firecrawl_api_key": bool(getattr(settings, "firecrawl_api_key", None)),
        "tavily_api_key": bool(getattr(settings, "tavily_api_key", None)),
        "minimax_api_key": bool(getattr(settings, "minimax_api_key", None)),
        "minimax_coding_plan_api_key": bool(
            getattr(settings, "minimax_coding_plan_api_key", None)
        ),
        "minimax_group_id": bool(getattr(settings, "minimax_group_id", None)),
        "gemini_api_key": bool(getattr(settings, "gemini_api_key", None)),
    }
    return {k: ("present" if v else "missing") for k, v in keys.items()}


def main() -> int:
    parser = argparse.ArgumentParser(description="Run AG-UI live capability matrix")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--backend-log", type=Path, default=DEFAULT_BACKEND_LOG)
    parser.add_argument("--timeout-sec", type=float, default=300.0)
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args()

    cases = _build_cases()
    results: list[CaseResult] = []

    print(f"[matrix] base_url={args.base_url}")
    print(f"[matrix] backend_log={args.backend_log}")
    print(f"[matrix] running {len(cases)} cases")

    for spec in cases:
        print(f"[matrix] {spec.id} {spec.category} ...")
        result = _run_case(
            base_url=args.base_url,
            spec=spec,
            backend_log=args.backend_log,
            timeout_sec=args.timeout_sec,
        )
        print(
            f"[matrix] {spec.id} -> {result.verdict} "
            f"(tools={len(result.tool_calls)}, custom={len(result.custom_events)}, "
            f"degraded={result.degraded_fallback})"
        )
        if result.verdict_reasons:
            for reason in result.verdict_reasons:
                print(f"  - {reason}")
        results.append(result)

    passed = sum(1 for r in results if r.verdict == "PASS")
    failed = len(results) - passed

    output = args.output
    if output is None:
        output = Path("system_logs/qa_runs") / f"agui_live_matrix_{int(time.time())}.json"
    output.parent.mkdir(parents=True, exist_ok=True)

    payload = {
        "generated_at": int(time.time()),
        "base_url": args.base_url,
        "backend_log": str(args.backend_log),
        "env_snapshot": _check_env_snapshot(),
        "total": len(results),
        "passed": passed,
        "failed": failed,
        "results": [asdict(r) for r in results],
    }
    output.write_text(json.dumps(payload, indent=2))

    print(f"[matrix] wrote {output}")
    print(f"[matrix] summary passed={passed} failed={failed}")
    return 0 if failed == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
