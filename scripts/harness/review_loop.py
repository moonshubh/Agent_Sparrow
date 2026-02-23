#!/usr/bin/env python3
"""Run the mandatory 3-pass harness review loop.

Loop per cycle:
1) Architecture review
2) Quality review
3) Security review (must run every cycle)

The script expects each reviewer command to emit JSON to stdout:
{
  "summary": "short text",
  "findings": [
    {
      "id": "ARCH-001",
      "severity": "high|medium|low",
      "title": "...",
      "path": "optional/path.py:10",
      "status": "open|fixed|accepted-risk"
    }
  ]
}
"""

from __future__ import annotations

import argparse
import json
import os
import shlex
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SEVERITY_ORDER = {"high": 3, "medium": 2, "low": 1}


@dataclass
class ReviewResult:
    reviewer: str
    summary: str
    findings: list[dict[str, Any]]
    raw_stdout: str
    raw_stderr: str
    return_code: int


def _now_ts() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")


def _normalize_findings(findings: list[dict[str, Any]], reviewer: str) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    for idx, finding in enumerate(findings, start=1):
        severity = str(finding.get("severity", "low")).strip().lower()
        if severity not in SEVERITY_ORDER:
            severity = "low"
        normalized.append(
            {
                "id": str(finding.get("id") or f"{reviewer.upper()}-{idx:03d}"),
                "severity": severity,
                "title": str(finding.get("title") or "Untitled finding"),
                "path": str(finding.get("path") or ""),
                "status": str(finding.get("status") or "open").strip().lower(),
            }
        )
    return normalized


def _run_reviewer(
    reviewer: str,
    command: str | None,
    dry_run: bool,
    cycle: int,
    task_id: str,
) -> ReviewResult:
    if dry_run:
        payload = {
            "summary": f"Dry-run {reviewer} review cycle {cycle}: clean.",
            "findings": [],
        }
        return ReviewResult(
            reviewer=reviewer,
            summary=payload["summary"],
            findings=[],
            raw_stdout=json.dumps(payload),
            raw_stderr="",
            return_code=0,
        )

    if not command:
        raise RuntimeError(
            f"Missing command for reviewer '{reviewer}'. "
            "Set --<reviewer>-cmd or environment variable."
        )

    env = os.environ.copy()
    env["HARNESS_TASK_ID"] = task_id
    env["HARNESS_REVIEWER"] = reviewer
    env["HARNESS_CYCLE"] = str(cycle)

    proc = subprocess.run(
        command,
        shell=True,
        text=True,
        capture_output=True,
        env=env,
    )

    stdout = (proc.stdout or "").strip()
    stderr = (proc.stderr or "").strip()

    if proc.returncode != 0:
        findings = [
            {
                "id": f"{reviewer.upper()}-CMD-FAIL",
                "severity": "high",
                "title": f"Reviewer command failed with exit code {proc.returncode}",
                "path": "",
                "status": "open",
            }
        ]
        summary = f"{reviewer} reviewer command failed."
        return ReviewResult(reviewer, summary, findings, stdout, stderr, proc.returncode)

    parsed: dict[str, Any]
    try:
        parsed = json.loads(stdout) if stdout else {}
    except json.JSONDecodeError:
        findings = [
            {
                "id": f"{reviewer.upper()}-PARSE-FAIL",
                "severity": "high",
                "title": "Reviewer output was not valid JSON",
                "path": "",
                "status": "open",
            }
        ]
        summary = f"{reviewer} reviewer output parsing failed."
        return ReviewResult(reviewer, summary, findings, stdout, stderr, proc.returncode)

    findings = _normalize_findings(list(parsed.get("findings") or []), reviewer)
    summary = str(parsed.get("summary") or f"{reviewer} review completed.")

    return ReviewResult(reviewer, summary, findings, stdout, stderr, proc.returncode)


def _render_markdown(result: ReviewResult) -> str:
    lines = [
        f"# {result.reviewer.title()} Review",
        "",
        f"Summary: {result.summary}",
        "",
    ]

    if not result.findings:
        lines.append("No findings.")
        lines.append("")
    else:
        lines.extend([
            "| ID | Severity | Status | Path | Title |",
            "|---|---|---|---|---|",
        ])
        for finding in sorted(
            result.findings,
            key=lambda f: SEVERITY_ORDER.get(str(f.get("severity")), 0),
            reverse=True,
        ):
            lines.append(
                "| {id} | {severity} | {status} | {path} | {title} |".format(
                    **finding
                )
            )
        lines.append("")

    lines.extend(
        [
            "## Raw Command Output",
            "",
            "```text",
            result.raw_stdout or "(empty)",
            "```",
        ]
    )

    if result.raw_stderr:
        lines.extend(
            [
                "",
                "## Raw Command Error",
                "",
                "```text",
                result.raw_stderr,
                "```",
            ]
        )

    lines.append("")
    return "\n".join(lines)


def _count_blocking(findings: list[dict[str, Any]]) -> int:
    count = 0
    for finding in findings:
        severity = str(finding.get("severity", "low")).lower()
        status = str(finding.get("status", "open")).lower()
        if severity in {"high", "medium"} and status not in {"fixed"}:
            count += 1
    return count


def _run_fix_command(command: str) -> tuple[int, str, str]:
    proc = subprocess.run(command, shell=True, text=True, capture_output=True)
    return proc.returncode, (proc.stdout or "").strip(), (proc.stderr or "").strip()


def main() -> int:
    parser = argparse.ArgumentParser(description="Run harness review loop.")
    parser.add_argument("--task-id", default=f"task-{_now_ts()}")
    parser.add_argument("--max-cycles", type=int, default=3)
    parser.add_argument("--output-dir", default="reports/reviews")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--fix-command", default="")

    parser.add_argument(
        "--architecture-cmd",
        default=os.getenv("HARNESS_ARCH_REVIEW_CMD", ""),
    )
    parser.add_argument(
        "--quality-cmd",
        default=os.getenv("HARNESS_QUALITY_REVIEW_CMD", ""),
    )
    parser.add_argument(
        "--security-cmd",
        default=os.getenv("HARNESS_SECURITY_REVIEW_CMD", ""),
    )

    args = parser.parse_args()

    if args.max_cycles < 1:
        raise SystemExit("--max-cycles must be >= 1")

    task_dir = Path(args.output_dir) / args.task_id
    task_dir.mkdir(parents=True, exist_ok=True)

    final_summary: dict[str, Any] = {
        "task_id": args.task_id,
        "started_at": datetime.now(timezone.utc).isoformat(),
        "max_cycles": args.max_cycles,
        "dry_run": args.dry_run,
        "cycles": [],
        "status": "failed",
    }

    passed = False

    review_steps = [
        ("architecture", args.architecture_cmd),
        ("quality", args.quality_cmd),
        ("security", args.security_cmd),
    ]

    for cycle in range(1, args.max_cycles + 1):
        cycle_dir = task_dir / f"cycle-{cycle}"
        cycle_dir.mkdir(parents=True, exist_ok=True)

        cycle_results: list[ReviewResult] = []
        all_findings: list[dict[str, Any]] = []

        for reviewer, command in review_steps:
            result = _run_reviewer(
                reviewer=reviewer,
                command=command,
                dry_run=args.dry_run,
                cycle=cycle,
                task_id=args.task_id,
            )
            cycle_results.append(result)
            all_findings.extend(result.findings)

            md_path = cycle_dir / f"{reviewer}.md"
            md_path.write_text(_render_markdown(result), encoding="utf-8")

        blocking_count = _count_blocking(all_findings)
        cycle_summary = {
            "cycle": cycle,
            "blocking_findings": blocking_count,
            "findings": all_findings,
            "reviewers": [
                {
                    "name": result.reviewer,
                    "summary": result.summary,
                    "return_code": result.return_code,
                }
                for result in cycle_results
            ],
        }

        (cycle_dir / "summary.json").write_text(
            json.dumps(cycle_summary, indent=2),
            encoding="utf-8",
        )

        final_summary["cycles"].append(cycle_summary)

        if blocking_count == 0:
            passed = True
            break

        if cycle < args.max_cycles and args.fix_command:
            code, stdout, stderr = _run_fix_command(args.fix_command)
            (cycle_dir / "fix-command.log").write_text(
                "\n".join(
                    [
                        f"command: {args.fix_command}",
                        f"exit_code: {code}",
                        "stdout:",
                        stdout,
                        "stderr:",
                        stderr,
                    ]
                ),
                encoding="utf-8",
            )

    final_summary["ended_at"] = datetime.now(timezone.utc).isoformat()
    final_summary["status"] = "passed" if passed else "failed"

    (task_dir / "summary.json").write_text(
        json.dumps(final_summary, indent=2),
        encoding="utf-8",
    )

    final_report_lines = [
        f"# Review Loop Final Report - {args.task_id}",
        "",
        f"Status: {final_summary['status']}",
        f"Cycles executed: {len(final_summary['cycles'])}",
        "",
    ]

    for cycle in final_summary["cycles"]:
        final_report_lines.append(
            f"- Cycle {cycle['cycle']}: blocking findings={cycle['blocking_findings']}"
        )

    final_report_lines.extend(
        [
            "",
            "Outputs:",
            f"- `{task_dir.as_posix()}`",
            "",
            "Blocking means any unresolved high/medium finding.",
        ]
    )

    (task_dir / "final-report.md").write_text(
        "\n".join(final_report_lines) + "\n",
        encoding="utf-8",
    )

    print(json.dumps({"task_id": args.task_id, "status": final_summary["status"]}))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
