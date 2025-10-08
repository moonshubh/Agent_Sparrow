import json
import logging
import re
from datetime import datetime
from typing import Any, Pattern

logger = logging.getLogger(__name__)

# Precompiled regex patterns for performance
SELF_CRITIQUE_RE: Pattern[str] = re.compile(r"<self_critique>.*?</self_critique>", flags=re.DOTALL)

SYSTEM_PATTERNS: list[Pattern[str]] = [
    re.compile(r"<system>.*?</system>", flags=re.DOTALL | re.IGNORECASE),
    re.compile(r"<internal>.*?</internal>", flags=re.DOTALL | re.IGNORECASE),
    re.compile(r"<self_critique>.*?</self_critique>", flags=re.DOTALL | re.IGNORECASE),
    re.compile(r".*loyalty relationship.*", flags=re.IGNORECASE),
]


def filter_system_text(text: str | None) -> str:
    """Strip internal/system markers before they reach the UI stream."""
    if not text:
        return ""
    filtered = SELF_CRITIQUE_RE.sub("", text)
    for pattern in SYSTEM_PATTERNS:
        filtered = pattern.sub("", filtered)
    return filtered


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
