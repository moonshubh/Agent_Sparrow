#!/usr/bin/env python3
"""Cost-aware AG-UI scenario runner for Gemini + Grok validation.

Runs a fixed matrix of 10 complex scenarios (7 Gemini base, 3 Grok 4.1 fast reasoning)
against `/api/v1/agui/stream`, captures SSE lifecycle/quality signals, and writes JSON
results for RCA and failed-only reruns.
"""

from __future__ import annotations

import argparse
import json
import time
import uuid
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, Iterable

import httpx


@dataclass
class Scenario:
    id: str
    name: str
    provider: str
    model: str
    prompt: str
    min_chars: int
    expected_keywords: list[str]
    min_keyword_hits: int


@dataclass
class ScenarioResult:
    id: str
    name: str
    provider: str
    model: str
    ok: bool
    fail_reasons: list[str]
    http_status: int | None
    duration_sec: float
    first_token_sec: float | None
    text_chars: int
    keyword_hits: int
    run_error: bool
    run_error_message: str | None
    run_finished: bool
    event_counts: dict[str, int]
    text_preview: str


def _scenario_matrix() -> list[Scenario]:
    return [
        Scenario(
            id="G1",
            name="zendesk_outage_triage",
            provider="google",
            model="gemini-3-flash-preview",
            prompt=(
                "You are handling a Zendesk escalation. Customer reports a full outage "
                "after a release: email sync fails, attachments timeout, and dashboard is blank. "
                "Write: (1) customer-facing response, (2) internal triage plan with owners and ETA, "
                "(3) risk assessment and immediate rollback criteria."
            ),
            min_chars=650,
            expected_keywords=["customer", "internal", "risk", "rollback", "eta"],
            min_keyword_hits=4,
        ),
        Scenario(
            id="G2",
            name="billing_duplicate_charge_rca",
            provider="google",
            model="gemini-3-flash-preview",
            prompt=(
                "Zendesk ticket: enterprise user was charged twice after a plan upgrade. "
                "Provide a root cause hypothesis tree, verification steps, and safe remediation plan "
                "with no downtime. Include what to communicate to finance and support."
            ),
            min_chars=520,
            expected_keywords=[
                "root cause",
                "verification",
                "remediation",
                "finance",
                "support",
            ],
            min_keyword_hits=4,
        ),
        Scenario(
            id="G3",
            name="oauth_regression_incident",
            provider="google",
            model="gemini-3-flash-preview",
            prompt=(
                "Analyze this support incident and produce a response plan.\n"
                "Symptoms: OAuth logins fail only for SSO users after Monday deploy; "
                "error spikes from 0.2% to 14%; rollback restored partial service.\n"
                "Need: customer-safe explanation, engineering diagnosis workflow, "
                "and measurable next checks."
            ),
            min_chars=520,
            expected_keywords=[
                "oauth",
                "customer",
                "engineering",
                "checks",
                "rollback",
            ],
            min_keyword_hits=4,
        ),
        Scenario(
            id="G4",
            name="multi_ticket_priority_coordination",
            provider="google",
            model="gemini-3-flash-preview",
            prompt=(
                "You are the primary coordinator. Prioritize these tickets:\n"
                "- Ticket A: data loss risk for 3 enterprise tenants\n"
                "- Ticket B: login slowness for free users\n"
                "- Ticket C: export job failed for finance admin\n"
                "Output a ranked action plan, ownership map, and communication cadence."
            ),
            min_chars=480,
            expected_keywords=[
                "priority",
                "ownership",
                "communication",
                "enterprise",
                "finance",
            ],
            min_keyword_hits=4,
        ),
        Scenario(
            id="G5",
            name="short_term_vs_long_term_fix",
            provider="google",
            model="gemini-3-flash-preview",
            prompt=(
                "Customer query from Zendesk: app crashes when attaching >25MB files. "
                "Give immediate mitigation, medium-term fix, and long-term architecture hardening. "
                "Include rollback safety and monitoring signals."
            ),
            min_chars=480,
            expected_keywords=[
                "mitigation",
                "medium-term",
                "long-term",
                "rollback",
                "monitoring",
            ],
            min_keyword_hits=4,
        ),
        Scenario(
            id="G6",
            name="log_pattern_diagnosis",
            provider="google",
            model="gemini-3-flash-preview",
            prompt=(
                "Diagnose this log pattern and produce a customer-ready + internal response.\n"
                "Logs: 503 upstream timeout, DB pool saturation, cache miss storm, retry queue growing.\n"
                "Need likely root causes, confidence level, and 24-hour stabilization plan."
            ),
            min_chars=520,
            expected_keywords=[
                "root cause",
                "confidence",
                "stabilization",
                "customer",
                "internal",
            ],
            min_keyword_hits=4,
        ),
        Scenario(
            id="G7",
            name="conflicting_playbook_resolution",
            provider="google",
            model="gemini-3-flash-preview",
            prompt=(
                "Two internal playbooks conflict: one says force reset tokens, another says preserve sessions. "
                "Create a decisive policy recommendation for a Zendesk incident workflow, with decision criteria, "
                "fallback path, and what to log for postmortem."
            ),
            min_chars=480,
            expected_keywords=[
                "decision",
                "criteria",
                "fallback",
                "postmortem",
                "zendesk",
            ],
            min_keyword_hits=4,
        ),
        Scenario(
            id="X1",
            name="grok_incident_comms",
            provider="xai",
            model="grok-4-1-fast-reasoning",
            prompt=(
                "Prepare a fast but accurate incident communication package for Zendesk: "
                "customer summary, likely technical cause, temporary workaround, and next update ETA."
            ),
            min_chars=420,
            expected_keywords=[
                "customer",
                "cause",
                "workaround",
                "eta",
                "update",
            ],
            min_keyword_hits=4,
        ),
        Scenario(
            id="X2",
            name="grok_root_cause_from_signals",
            provider="xai",
            model="grok-4-1-fast-reasoning",
            prompt=(
                "Given this signal set: API latency doubled, queue depth tripled, write failures at 3%, "
                "and one region unstable. Provide ranked hypotheses, immediate mitigations, and validation checks."
            ),
            min_chars=420,
            expected_keywords=[
                "hypotheses",
                "mitigation",
                "validation",
                "latency",
                "queue",
            ],
            min_keyword_hits=4,
        ),
        Scenario(
            id="X3",
            name="grok_zendesk_engineering_alignment",
            provider="xai",
            model="grok-4-1-fast-reasoning",
            prompt=(
                "Draft a Zendesk response that aligns support + engineering: mention SLA impact, "
                "current engineering status, and QA verification steps before closing."
            ),
            min_chars=380,
            expected_keywords=["sla", "engineering", "qa", "verification", "support"],
            min_keyword_hits=4,
        ),
    ]


def _load_failed_ids(path: Path) -> set[str]:
    payload = json.loads(path.read_text())
    results = payload.get("results", [])
    return {str(item.get("id")) for item in results if not bool(item.get("ok"))}


def _iter_scenarios(selected_ids: set[str] | None) -> Iterable[Scenario]:
    for scenario in _scenario_matrix():
        if selected_ids is None or scenario.id in selected_ids:
            yield scenario


def _build_payload(s: Scenario) -> dict[str, Any]:
    run_id = f"run-{uuid.uuid4()}"
    thread_id = f"qa-thread-{s.id.lower()}-{int(time.time())}"
    return {
        "threadId": thread_id,
        "runId": run_id,
        "messages": [
            {
                "id": f"user-{uuid.uuid4()}",
                "role": "user",
                "content": s.prompt,
            }
        ],
        "state": {},
        "tools": [],
        "context": [],
        "forwardedProps": {
            "session_id": thread_id,
            "trace_id": run_id,
            "provider": s.provider,
            "model": s.model,
            "agent_type": "primary",
            "use_server_memory": False,
            "force_websearch": False,
        },
    }


def _extract_event_type(event: dict[str, Any]) -> str:
    value = event.get("type")
    if isinstance(value, str) and value:
        return value
    return "UNKNOWN"


def _run_one(base_url: str, scenario: Scenario, timeout_sec: float) -> ScenarioResult:
    url = f"{base_url.rstrip('/')}/api/v1/agui/stream"
    payload = _build_payload(scenario)
    start = time.monotonic()
    first_token_sec: float | None = None
    event_counts: dict[str, int] = {}
    run_finished = False
    run_error = False
    run_error_message: str | None = None
    text_chunks: list[str] = []
    http_status: int | None = None
    fail_reasons: list[str] = []

    timeout = httpx.Timeout(timeout_sec, connect=20.0)

    try:
        with httpx.Client(timeout=timeout) as client:
            with client.stream("POST", url, json=payload) as response:
                http_status = response.status_code
                if response.status_code != 200:
                    fail_reasons.append(f"http_{response.status_code}")
                for raw_line in response.iter_lines():
                    if not raw_line:
                        continue
                    line = raw_line if isinstance(raw_line, str) else raw_line.decode()
                    if line.startswith(":"):
                        event_counts["HEARTBEAT"] = event_counts.get("HEARTBEAT", 0) + 1
                        continue
                    if not line.startswith("data:"):
                        continue
                    data_part = line[5:].strip()
                    if not data_part:
                        continue
                    try:
                        event = json.loads(data_part)
                    except json.JSONDecodeError:
                        event_counts["PARSE_ERROR"] = event_counts.get("PARSE_ERROR", 0) + 1
                        continue

                    event_type = _extract_event_type(event)
                    event_counts[event_type] = event_counts.get(event_type, 0) + 1

                    if event_type == "TEXT_MESSAGE_CONTENT":
                        delta = str(event.get("delta") or "")
                        if delta:
                            text_chunks.append(delta)
                            if first_token_sec is None:
                                first_token_sec = time.monotonic() - start
                    elif event_type == "RUN_ERROR":
                        run_error = True
                        run_error_message = str(event.get("message") or "") or None
                    elif event_type == "RUN_FINISHED":
                        run_finished = True
    except Exception as exc:  # pragma: no cover - network/transport diagnostics
        fail_reasons.append(f"transport_error:{type(exc).__name__}")
        run_error = True
        run_error_message = str(exc)

    duration_sec = time.monotonic() - start
    full_text = "".join(text_chunks).strip()
    lower_text = full_text.lower()
    keyword_hits = sum(
        1 for keyword in scenario.expected_keywords if keyword.lower() in lower_text
    )

    if http_status != 200:
        fail_reasons.append("non_200")
    if not run_finished:
        fail_reasons.append("missing_run_finished")
    if run_error:
        fail_reasons.append("run_error")
    if len(full_text) < scenario.min_chars:
        fail_reasons.append(
            f"text_too_short:{len(full_text)}<{scenario.min_chars}"
        )
    if keyword_hits < scenario.min_keyword_hits:
        fail_reasons.append(
            f"keyword_hits_too_low:{keyword_hits}<{scenario.min_keyword_hits}"
        )

    ok = len(fail_reasons) == 0
    return ScenarioResult(
        id=scenario.id,
        name=scenario.name,
        provider=scenario.provider,
        model=scenario.model,
        ok=ok,
        fail_reasons=fail_reasons,
        http_status=http_status,
        duration_sec=round(duration_sec, 3),
        first_token_sec=round(first_token_sec, 3) if first_token_sec is not None else None,
        text_chars=len(full_text),
        keyword_hits=keyword_hits,
        run_error=run_error,
        run_error_message=run_error_message,
        run_finished=run_finished,
        event_counts=event_counts,
        text_preview=full_text[:400],
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Run AG-UI scenario matrix")
    parser.add_argument(
        "--base-url",
        default="http://127.0.0.1:8000",
        help="API base URL (default: http://127.0.0.1:8000)",
    )
    parser.add_argument(
        "--timeout-sec",
        type=float,
        default=360.0,
        help="Per-scenario request timeout in seconds",
    )
    parser.add_argument(
        "--rerun-failed-from",
        type=Path,
        default=None,
        help="If set, run only failed scenarios from a previous result JSON",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Output JSON path (default: system_logs/qa_runs/agui_scenarios_<ts>.json)",
    )
    args = parser.parse_args()

    selected_ids: set[str] | None = None
    if args.rerun_failed_from is not None:
        selected_ids = _load_failed_ids(args.rerun_failed_from)
        print(f"[runner] rerun mode, failed IDs: {sorted(selected_ids)}")
        if not selected_ids:
            print("[runner] no failed scenarios found in source file; exiting")
            return 0

    scenarios = list(_iter_scenarios(selected_ids))
    if not scenarios:
        print("[runner] no scenarios selected")
        return 1

    print(f"[runner] running {len(scenarios)} scenario(s)")
    results: list[ScenarioResult] = []
    for scenario in scenarios:
        print(
            f"[runner] {scenario.id} {scenario.provider}/{scenario.model} :: {scenario.name}"
        )
        result = _run_one(args.base_url, scenario, args.timeout_sec)
        status = "PASS" if result.ok else "FAIL"
        print(
            f"[runner] {scenario.id} => {status} "
            f"(chars={result.text_chars}, hits={result.keyword_hits}, "
            f"finished={result.run_finished}, error={result.run_error})"
        )
        results.append(result)

    passed = sum(1 for item in results if item.ok)
    failed = len(results) - passed
    output_path = (
        args.output
        if args.output is not None
        else Path("system_logs/qa_runs")
        / f"agui_scenarios_{int(time.time())}.json"
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)

    payload: Dict[str, Any] = {
        "generated_at": int(time.time()),
        "base_url": args.base_url,
        "timeout_sec": args.timeout_sec,
        "total": len(results),
        "passed": passed,
        "failed": failed,
        "results": [asdict(item) for item in results],
    }
    output_path.write_text(json.dumps(payload, indent=2))
    print(f"[runner] wrote: {output_path}")
    print(f"[runner] summary: passed={passed} failed={failed}")
    return 0 if failed == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
