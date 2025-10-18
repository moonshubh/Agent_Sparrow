import json
import logging
import re
from dataclasses import is_dataclass
from datetime import datetime
from typing import Any, Pattern

logger = logging.getLogger(__name__)

# Precompiled regex patterns for performance
SELF_CRITIQUE_RE: Pattern[str] = re.compile(r"<self_critique>.*?</self_critique>", flags=re.DOTALL)

SYSTEM_PATTERNS: list[Pattern[str]] = [
    re.compile(r"<system>.*?</system>", flags=re.DOTALL | re.IGNORECASE),
    re.compile(r"<internal>.*?</internal>", flags=re.DOTALL | re.IGNORECASE),
    re.compile(r"<self_critique>.*?</self_critique>", flags=re.DOTALL | re.IGNORECASE),
    re.compile(r"loyalty relationship(?: disclosure)?", flags=re.IGNORECASE),
]


def filter_system_text(text: str | None) -> str:
    """Strip internal/system markers before they reach the UI stream."""
    if not text:
        return ""
    filtered = SELF_CRITIQUE_RE.sub("", text)
    for pattern in SYSTEM_PATTERNS:
        filtered = pattern.sub("", filtered)
    if filtered.strip():
        return filtered
    # Fallback to original content if sanitization stripped everything to avoid blank streams.
    return text


def safe_json_serializer(obj: Any):
    """Serialize common complex objects for JSON payloads."""
    if isinstance(obj, datetime):
        return obj.isoformat()
    if hasattr(obj, "model_dump"):
        return obj.model_dump()
    if hasattr(obj, "dict"):
        return obj.dict()
    if isinstance(obj, (list, tuple)):
        return [safe_json_serializer(x) for x in obj]
    if isinstance(obj, dict):
        return {k: safe_json_serializer(v) for k, v in obj.items()}
    try:
        json.dumps(obj)
        return obj
    except (TypeError, ValueError):
        return str(obj)


def serialize_analysis_results(final_report: Any) -> dict | Any:
    """Safely serialize analysis results for JSON streaming/response."""
    try:
        if is_dataclass(final_report):
            structured_output = getattr(final_report, "structured_output_dict", None)
            if structured_output is None and getattr(final_report, "structured_output", None):
                try:
                    structured_output = final_report.structured_output.to_dict()  # type: ignore[union-attr]
                except Exception:
                    structured_output = None

            metadata = getattr(final_report, "metadata", None)
            system_metadata: dict[str, Any] = {}
            ingestion_metadata: dict[str, Any] = {}

            if metadata is not None:
                system_metadata = {
                    "app_version": getattr(metadata, "mailbird_version", None),
                    "os_version": getattr(metadata, "os_version", None),
                    "account_count": getattr(metadata, "account_count", None),
                    "database_size": getattr(metadata, "database_size_mb", None),
                    "error_count": getattr(metadata, "error_count", None),
                    "warning_count": getattr(metadata, "warning_count", None),
                    "time_range": {
                        "start": getattr(metadata, "session_start", None),
                        "end": getattr(metadata, "session_end", None),
                    },
                }
                ingestion_metadata = {
                    "line_count": getattr(metadata, "total_entries", None),
                    "time_range": {
                        "start": getattr(metadata, "session_start", None),
                        "end": getattr(metadata, "session_end", None),
                    },
                }

            markdown = getattr(final_report, "conversational_markdown", None) or getattr(
                final_report, "executive_summary", ""
            )

            findings_legacy: list[dict[str, Any]] = []
            if structured_output:
                for finding in structured_output.get("findings", []):
                    findings_legacy.append(
                        {
                            "title": finding.get("title"),
                            "details": finding.get("details"),
                            "severity": finding.get("severity"),
                            "occurrences": finding.get("occurrences"),
                            "evidence_refs": finding.get("evidence_refs", []),
                        }
                    )

            serialized = {
                "markdown": markdown,
                "structured_output": structured_output,
                "system_metadata": system_metadata,
                "ingestion_metadata": ingestion_metadata,
                "identified_issues": findings_legacy,
                "overall_summary": getattr(final_report, "executive_summary", markdown),
                "redactions_applied": structured_output.get("redactions_applied", []) if structured_output else [],
            }

            return safe_json_serializer(serialized)

        if hasattr(final_report, 'model_dump'):
            serialized = final_report.model_dump()
        elif hasattr(final_report, 'dict'):
            serialized = final_report.dict()
        elif isinstance(final_report, dict):
            serialized = final_report
        else:
            serialized = {"summary": str(final_report)}
        return safe_json_serializer(serialized)
    except Exception as e:  # pragma: no cover
        logger.error(f"Error serializing analysis results: {e}")
        return {
            "overall_summary": "Analysis completed but serialization failed",
            "error": str(e),
            "system_metadata": {},
            "identified_issues": [],
            "proposed_solutions": []
        }


def augment_analysis_metadata(
    analysis_results: dict,
    raw_log: str | None,
    issues: list | None,
    ingestion_metadata: dict | None,
) -> dict:
    """Best-effort enrichment of analysis metadata for the overview card."""
    try:
        if not isinstance(analysis_results, dict):
            return analysis_results

        if not isinstance(analysis_results.get("system_metadata"), dict):
            analysis_results["system_metadata"] = {}
        if not isinstance(analysis_results.get("ingestion_metadata"), dict):
            analysis_results["ingestion_metadata"] = {}

        system_meta = analysis_results["system_metadata"]
        ingest_meta = analysis_results["ingestion_metadata"]

        if ingestion_metadata and isinstance(ingestion_metadata, dict):
            if ingestion_metadata.get("time_range") and not ingest_meta.get("time_range"):
                ingest_meta["time_range"] = ingestion_metadata.get("time_range")
            if ingestion_metadata.get("line_count") and not ingest_meta.get("line_count"):
                ingest_meta["line_count"] = ingestion_metadata.get("line_count")

        if isinstance(raw_log, str) and raw_log:
            lines = raw_log.splitlines()
            if ingest_meta.get("line_count") is None:
                ingest_meta["line_count"] = len(lines)
            if system_meta.get("error_count") is None:
                system_meta["error_count"] = sum(1 for ln in lines if "|ERROR|" in ln or " ERROR " in ln)
            if system_meta.get("warning_count") is None:
                system_meta["warning_count"] = sum(1 for ln in lines if "|WARN|" in ln or " WARNING " in ln)
            if system_meta.get("database_size") is None:
                import re as _re
                m = _re.search(r"(?:Store\.db\s+|Database size:\s*)([\d,.]+\s*[KMGTP]B)", raw_log, _re.IGNORECASE)
                if m:
                    system_meta["database_size"] = m.group(1).replace(",", "")

        if system_meta.get("accounts_with_errors") is None and isinstance(issues, list) and issues:
            import re as _re
            accs: set[str] = set()
            for it in issues:
                if not isinstance(it, dict):
                    continue
                text = " ".join(str(it.get(k, "")) for k in ("details", "description", "title"))
                for m in _re.findall(r"Account[:\s]+([^\s|]+@[^\s|]+)", text):
                    accs.add(m)
            if accs:
                system_meta["accounts_with_errors"] = len(accs)

        return analysis_results
    except Exception:  # pragma: no cover
        return analysis_results


def get_user_id_for_dev_mode(settings) -> str:
    """Get user ID for development mode or 'anonymous' in production w/o auth."""
    if getattr(settings, 'skip_auth', False) and getattr(settings, 'development_user_id', None):
        return settings.development_user_id
    return "anonymous"


def _format_log_analysis_content(analysis: dict | Any, question: str | None) -> str:
    """Build a cohesive markdown answer for log analysis results."""
    try:
        if not isinstance(analysis, dict):
            if hasattr(analysis, 'model_dump'):
                analysis = analysis.model_dump()  # type: ignore
            elif hasattr(analysis, 'dict'):
                analysis = analysis.dict()  # type: ignore
            else:
                analysis = {"overall_summary": str(analysis)}

        overall_summary = analysis.get("overall_summary") or analysis.get("summary") or "Log analysis complete."
        issues = analysis.get("identified_issues") or analysis.get("issues") or []
        solutions = analysis.get("proposed_solutions") or analysis.get("solutions") or analysis.get("actions") or []

        parts: list[str] = []
        if question:
            parts.append(
                f"Thanks for sharing the log file. I reviewed it in the context of your question: \"{question}\". Here's what I found and how to fix it."
            )
        else:
            parts.append(
                "Thanks for sharing the log file. I’ve completed the analysis — here’s what’s going on and how to fix it."
            )

        parts.append("## Problem analysis\n" + str(overall_summary))

        if isinstance(issues, list) and len(issues) > 0:
            findings: list[str] = []
            for issue in issues[:3]:
                title = issue.get("title") if isinstance(issue, dict) else None
                details = issue.get("details") if isinstance(issue, dict) else None
                severity = issue.get("severity") if isinstance(issue, dict) else None
                bullet = "- "
                if severity:
                    bullet += f"[{severity}] "
                if title:
                    bullet += f"{title}"
                if details:
                    bullet += f": {details}"
                findings.append(bullet)
            if findings:
                parts.append("### Critical findings\n" + "\n".join(findings))

        step_sections: list[str] = []
        if isinstance(solutions, list) and len(solutions) > 0:
            for idx, sol in enumerate(solutions[:3], start=1):
                if not isinstance(sol, dict):
                    continue
                title = sol.get("title") or f"Solution {idx}"
                steps = sol.get("steps") or []
                section_lines: list[str] = [f"### Solution {idx}: {title}"]
                if isinstance(steps, list) and steps:
                    section_lines.append("**Steps to resolve:**")
                    for j, step in enumerate(steps, start=1):
                        section_lines.append(f"{j}. {step}")
                step_sections.append("\n".join(section_lines))

        if step_sections:
            parts.append("## Step-by-step solution\n" + "\n\n".join(step_sections))

        return "\n\n".join(parts)
    except Exception:
        summary = analysis.get("overall_summary") if isinstance(analysis, dict) else None
        return f"Log analysis complete! {summary or ''}".strip()
