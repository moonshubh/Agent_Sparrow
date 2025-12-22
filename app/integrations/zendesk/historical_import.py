from __future__ import annotations

import argparse
import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
import html
import logging
import re
from typing import Any, Dict, List, Optional

from app.agents.harness.store import IssueResolutionStore
from app.agents.unified.playbooks import PlaybookEnricher
from app.core.settings import settings
from app.integrations.zendesk.client import ZendeskClient
from app.security.pii_redactor import redact_pii

logger = logging.getLogger(__name__)


DEFAULT_ALLOWED_CATEGORIES: tuple[str, ...] = ("sending", "features", "licensing")

DEFAULT_NATURE_LABEL_MAP: Dict[str, str] = {
    "issue with sending and receiving emails": "sending",
    "i want to know how to do certain thing in mailbird": "features",
    "i want to know how to do certain think in mailbird": "features",
    "question regarding subscription and licensing": "licensing",
    "subscription and licensing": "licensing",
}

DEFAULT_NATURE_KEYWORDS: Dict[str, tuple[str, ...]] = {
    "sending": ("send", "sending", "receive", "receiving", "smtp", "imap", "inbox", "outbox"),
    "features": ("how to", "how do i", "how can i", "feature", "does mailbird", "is it possible"),
    "licensing": ("license", "licence", "subscription", "billing", "payment", "refund", "renew", "trial", "upgrade"),
}


@dataclass(frozen=True, slots=True)
class ImportConfig:
    days_back: int = 30
    batch_size: int = 50
    sleep_between_batches: float = 0.0
    sleep_between_pages: float = 0.0
    rpm_limit: int = 10
    start_dt: Optional[datetime] = None
    end_dt: Optional[datetime] = None
    min_comments: int = 2
    min_agent_words: int = 50
    dry_run: bool = True
    skip_existing: bool = True
    require_nature_field: bool = True
    windows_brand_ids: List[str] = field(default_factory=list)
    nature_field_ids: List[str] = field(default_factory=list)
    nature_category_map: Dict[str, str] = field(default_factory=dict)
    allowed_categories: tuple[str, ...] = DEFAULT_ALLOWED_CATEGORIES


@dataclass(frozen=True, slots=True)
class ExtractedResolution:
    ticket_id: str
    assignee_id: str
    category: str
    problem_summary: str
    solution_summary: str
    macros_used: List[str]
    kb_articles_used: List[str]
    was_escalated: bool
    conversation_messages: List[Dict[str, Any]]


class HistoricalImporter:
    def __init__(
        self,
        *,
        config: Optional[ImportConfig] = None,
        client: Optional[ZendeskClient] = None,
        store: Optional[IssueResolutionStore] = None,
        enricher: Optional[PlaybookEnricher] = None,
    ) -> None:
        if client is None:
            client = ZendeskClient(
                subdomain=str(settings.zendesk_subdomain or ""),
                email=str(settings.zendesk_email or ""),
                api_token=str(settings.zendesk_api_token or ""),
                dry_run=bool(getattr(settings, "zendesk_dry_run", False)),
                rpm_limit=int(getattr(settings, "zendesk_import_rpm_limit", 10)),
            )

        if config is None:
            windows_ids = list(settings.zendesk_windows_brand_ids or [])
            if not windows_ids and settings.zendesk_brand_id:
                windows_ids = [str(settings.zendesk_brand_id)]
            nature_field_ids = list(settings.zendesk_nature_field_ids or [])
            if not nature_field_ids and settings.zendesk_nature_field_id:
                nature_field_ids = [str(settings.zendesk_nature_field_id)]
            config = ImportConfig(
                dry_run=True,
                windows_brand_ids=[str(v) for v in windows_ids if str(v).strip()],
                nature_field_ids=[str(v) for v in nature_field_ids if str(v).strip()],
                nature_category_map=dict(settings.zendesk_nature_category_map or {}),
                require_nature_field=bool(getattr(settings, "zendesk_nature_require_field", True)),
                rpm_limit=int(getattr(settings, "zendesk_import_rpm_limit", 10)),
            )

        self.client = client
        self.config = config
        self.store = store or IssueResolutionStore()
        self.enricher = enricher or PlaybookEnricher()

    async def run_import(self) -> Dict[str, Any]:
        start_dt = self.config.start_dt or (datetime.now(timezone.utc) - timedelta(days=max(1, int(self.config.days_back))))
        end_dt = self.config.end_dt
        start_time = int(start_dt.timestamp())

        if not self.config.windows_brand_ids:
            logger.warning("zendesk_windows_brand_ids not set; no tickets will be imported")
        if not self.config.nature_field_ids:
            logger.warning("zendesk_nature_field_ids not set; nature filtering will likely skip tickets")

        stats: Dict[str, int] = {
            "fetched": 0,
            "skipped_brand": 0,
            "skipped_category": 0,
            "skipped_satisfaction": 0,
            "skipped_existing": 0,
            "skipped_quality": 0,
            "stored": 0,
            "playbook_queued": 0,
            "errors": 0,
        }

        batch: List[Dict[str, Any]] = []
        for ticket in self._fetch_resolved_tickets(start_time, end_dt):
            stats["fetched"] += 1

            if not self._is_windows_brand(ticket):
                stats["skipped_brand"] += 1
                continue

            if not self._is_within_window(ticket, start_dt, end_dt):
                continue

            category = self._infer_category(ticket)
            if not category:
                stats["skipped_category"] += 1
                continue

            if self._has_bad_satisfaction(ticket):
                stats["skipped_satisfaction"] += 1
                continue

            ticket["_historical_category"] = category
            batch.append(ticket)
            if len(batch) >= max(1, int(self.config.batch_size)):
                await self._process_batch(batch, stats)
                print(f"historical_import_progress={stats}")
                batch.clear()
                if self.config.sleep_between_batches:
                    await asyncio.sleep(max(0.1, float(self.config.sleep_between_batches)))

        if batch:
            await self._process_batch(batch, stats)
            print(f"historical_import_progress={stats}")

        stats["dry_run"] = int(self.config.dry_run)
        logger.info("historical_import_complete stats=%s", stats)
        print(f"historical_import_stats={stats}")
        return stats

    def _fetch_resolved_tickets(self, start_time: int, end_dt: Optional[datetime]):
        end_time = int(end_dt.timestamp()) if end_dt else None
        return self.client.export_resolved_tickets_cursor(
            start_time=start_time,
            per_page=100,
            sleep_between_pages=self.config.sleep_between_pages,
            end_time=end_time,
        )

    async def _process_batch(self, tickets: List[Dict[str, Any]], stats: Dict[str, int]) -> None:
        for ticket in tickets:
            ticket_id = str(ticket.get("id") or "").strip()
            if not ticket_id:
                continue

            if self.config.skip_existing:
                try:
                    existing = await self.store.get_resolution_by_ticket(ticket_id)
                except Exception:
                    existing = None
                if existing:
                    stats["skipped_existing"] += 1
                    continue

            try:
                resolution = await self._extract_resolution(ticket)
            except Exception as exc:
                stats["errors"] += 1
                logger.warning("historical_extract_failed ticket_id=%s error=%s", ticket_id, str(exc)[:180])
                continue

            if resolution is None:
                stats["skipped_quality"] += 1
                continue

            if self.config.dry_run:
                continue

            try:
                stored = await self._store_resolution(resolution)
                if stored:
                    stats["stored"] += 1
            except Exception as exc:
                stats["errors"] += 1
                logger.warning("historical_store_failed ticket_id=%s error=%s", ticket_id, str(exc)[:180])

            try:
                queued = await self._queue_playbook_extraction(resolution)
                if queued:
                    stats["playbook_queued"] += 1
            except Exception as exc:
                stats["errors"] += 1
                logger.warning("historical_playbook_failed ticket_id=%s error=%s", ticket_id, str(exc)[:180])

    async def _extract_resolution(self, ticket: Dict[str, Any]) -> Optional[ExtractedResolution]:
        ticket_id = str(ticket.get("id") or "").strip()
        if not ticket_id:
            return None

        category = str(ticket.get("_historical_category") or "").strip()
        if category not in self.config.allowed_categories:
            return None

        audits = self.client.get_ticket_audits(ticket_id, limit=100)
        messages, agent_word_count = self._extract_conversation_messages(audits)

        if len(messages) < max(1, int(self.config.min_comments)):
            return None
        if agent_word_count < max(1, int(self.config.min_agent_words)):
            return None

        subject = str(ticket.get("subject") or "").strip()
        description = str(ticket.get("description") or "").strip()
        problem_summary = self._build_problem_summary(subject, description, messages)
        solution_summary = self._extract_solution_summary(messages)

        if not self._passes_quality_gate(problem_summary, solution_summary):
            return None

        macros_used = self._extract_macros_used(audits)
        kb_articles_used = self._extract_kb_links(messages)

        assignee_id = str(ticket.get("assignee_id") or "").strip()

        return ExtractedResolution(
            ticket_id=ticket_id,
            assignee_id=assignee_id,
            category=category,
            problem_summary=problem_summary,
            solution_summary=solution_summary,
            macros_used=macros_used,
            kb_articles_used=kb_articles_used,
            was_escalated=False,
            conversation_messages=messages,
        )

    async def _store_resolution(self, resolution: ExtractedResolution) -> bool:
        stored = await self.store.store_resolution(
            ticket_id=resolution.ticket_id,
            category=resolution.category,
            problem_summary=resolution.problem_summary,
            solution_summary=resolution.solution_summary,
            was_escalated=resolution.was_escalated,
            kb_articles_used=resolution.kb_articles_used,
            macros_used=resolution.macros_used,
            dedupe=True,
            prune=False,
        )
        return bool(stored)

    async def _queue_playbook_extraction(self, resolution: ExtractedResolution) -> bool:
        entry_id = await self.enricher.extract_from_conversation(
            conversation_id=f"zendesk-{resolution.ticket_id}",
            messages=resolution.conversation_messages,
            category=resolution.category,
        )
        return bool(entry_id)

    def _is_windows_brand(self, ticket: Dict[str, Any]) -> bool:
        brand_id = str(ticket.get("brand_id") or "").strip()
        if not brand_id:
            return False
        allowed = [str(b).strip() for b in (self.config.windows_brand_ids or []) if str(b).strip()]
        if not allowed:
            return False
        return brand_id in allowed

    def _is_within_window(self, ticket: Dict[str, Any], start_dt: datetime, end_dt: Optional[datetime]) -> bool:
        solved_at = ticket.get("solved_at") or ticket.get("closed_at") or ticket.get("updated_at")
        if not solved_at:
            return True
        solved_dt = _parse_datetime(str(solved_at))
        if solved_dt is None:
            return True
        if solved_dt < start_dt:
            return False
        if end_dt and solved_dt > end_dt:
            return False
        return True

    def _infer_category(self, ticket: Dict[str, Any]) -> Optional[str]:
        values: List[str] = []
        for field_id in self.config.nature_field_ids:
            field_value = _get_custom_field_value(ticket, field_id)
            values.extend(_normalize_values(field_value))

        if values:
            for value in values:
                mapped = self._map_nature_value(value)
                if mapped in self.config.allowed_categories:
                    return mapped

        if self.config.require_nature_field:
            return None

        tags = ticket.get("tags") or []
        for tag in _normalize_values(tags):
            mapped = self._map_nature_value(tag)
            if mapped in self.config.allowed_categories:
                return mapped

        return None

    def _map_nature_value(self, value: str) -> Optional[str]:
        normalized = _normalize_text(value)
        if not normalized:
            return None

        custom_map = {str(k).strip().lower(): str(v).strip().lower() for k, v in (self.config.nature_category_map or {}).items()}
        if normalized in custom_map:
            return custom_map[normalized]

        if normalized in DEFAULT_NATURE_LABEL_MAP:
            return DEFAULT_NATURE_LABEL_MAP[normalized]

        for category, keywords in DEFAULT_NATURE_KEYWORDS.items():
            if any(k in normalized for k in keywords):
                return category

        return None

    def _has_bad_satisfaction(self, ticket: Dict[str, Any]) -> bool:
        satisfaction = ticket.get("satisfaction_rating")
        if not isinstance(satisfaction, dict):
            return False
        score = str(satisfaction.get("score") or "").lower()
        return score == "bad"

    def _extract_conversation_messages(self, audits: List[Dict[str, Any]]) -> tuple[List[Dict[str, Any]], int]:
        items: List[tuple[datetime, int, int, str, str]] = []
        for idx, audit in enumerate(audits or []):
            created = _parse_datetime(str(audit.get("created_at") or "")) or datetime.min.replace(tzinfo=timezone.utc)
            author_id = audit.get("author_id")
            role = "user"
            if author_id is not None:
                user = self.client.get_user_cached(author_id)
                if user.get("role") in {"agent", "admin"}:
                    role = "assistant"

            events = audit.get("events") or []
            if not isinstance(events, list):
                continue
            for e_idx, event in enumerate(events):
                if not isinstance(event, dict):
                    continue
                if str(event.get("type") or "") != "Comment":
                    continue
                if not bool(event.get("public", False)):
                    continue
                body = event.get("body") or event.get("html_body") or ""
                if not isinstance(body, str):
                    continue
                content = _truncate_text(_sanitize_text(body), 8000)
                if not content:
                    continue
                items.append((created, idx, e_idx, role, content))

        items.sort(key=lambda v: (v[0], v[1], v[2]))

        messages: List[Dict[str, Any]] = []
        agent_word_count = 0
        for _, _, _, role, content in items:
            messages.append({"role": role, "content": content})
            if role == "assistant":
                agent_word_count += len(content.split())

        return messages, agent_word_count

    def _build_problem_summary(
        self,
        subject: str,
        description: str,
        messages: List[Dict[str, Any]],
    ) -> str:
        first_customer = ""
        for msg in messages:
            if msg.get("role") == "user":
                first_customer = str(msg.get("content") or "").strip()
                if first_customer:
                    break
        pieces = [p for p in [subject, first_customer or description] if p]
        summary = "\n\n".join(pieces).strip()
        return _trim_summary(summary, 800)

    def _extract_solution_summary(self, messages: List[Dict[str, Any]]) -> str:
        for msg in reversed(messages):
            if msg.get("role") == "assistant":
                return _trim_summary(str(msg.get("content") or ""), 1200)
        return ""

    def _passes_quality_gate(self, problem_summary: str, solution_summary: str) -> bool:
        p_len = len(problem_summary)
        s_len = len(solution_summary)
        if p_len < 40 or s_len < 60:
            return False
        return True

    def _extract_macros_used(self, audits: List[Dict[str, Any]]) -> List[str]:
        macros: List[str] = []
        for audit in audits or []:
            events = audit.get("events") or []
            if not isinstance(events, list):
                continue
            for event in events:
                if not isinstance(event, dict):
                    continue
                event_type = str(event.get("type") or "")
                if event_type in {"Macro", "MacroReference"}:
                    macro_id = event.get("macro_id") or event.get("id") or event.get("value")
                    if macro_id:
                        macros.append(str(macro_id))
                    continue
                if event_type != "Comment":
                    continue
                via = event.get("via") or {}
                if not isinstance(via, dict):
                    continue
                source = via.get("source") or {}
                if not isinstance(source, dict):
                    continue
                source_type = str(source.get("type") or source.get("rel") or "").lower()
                if source_type != "macro":
                    continue
                macro_id = source.get("id") or source.get("macro_id")
                if not macro_id:
                    from_obj = source.get("from") or {}
                    if isinstance(from_obj, dict):
                        macro_id = from_obj.get("id") or from_obj.get("macro_id")
                if macro_id:
                    macros.append(str(macro_id))
        return sorted(set(macros))

    def _extract_kb_links(self, messages: List[Dict[str, Any]]) -> List[str]:
        domains = [d.strip().lower() for d in (settings.zendesk_firecrawl_support_domains or []) if d]
        if not domains:
            domains = ["support.getmailbird.com", "www.getmailbird.com/help"]
        urls: List[str] = []
        pattern = re.compile(r"https?://[^\s)>\"]+", re.IGNORECASE)
        for msg in messages:
            content = str(msg.get("content") or "")
            for match in pattern.findall(content):
                lowered = match.lower()
                if any(domain in lowered for domain in domains):
                    urls.append(match)
        return sorted(set(urls))


def _parse_datetime(value: str) -> Optional[datetime]:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except Exception:
        return None


def _sanitize_text(text: str) -> str:
    if not text:
        return ""
    cleaned = html.unescape(str(text))
    cleaned = re.sub(r"<[^>]+>", " ", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    cleaned = redact_pii(cleaned)
    return cleaned


def _normalize_text(value: str) -> str:
    cleaned = re.sub(r"[^a-z0-9]+", " ", str(value or "").lower())
    return " ".join(cleaned.split()).strip()


def _normalize_values(value: Any) -> List[str]:
    if value is None:
        return []
    if isinstance(value, list):
        out: List[str] = []
        for item in value:
            if item is None:
                continue
            out.append(str(item))
        return out
    return [str(value)]


def _get_custom_field_value(ticket: Dict[str, Any], field_id: str) -> Any:
    fields = ticket.get("custom_fields") or []
    if not isinstance(fields, list):
        return None
    for field in fields:
        if not isinstance(field, dict):
            continue
        if str(field.get("id") or "") == str(field_id):
            return field.get("value")
    return None


def _trim_summary(text: str, max_chars: int) -> str:
    summary = _sanitize_text(text)
    if len(summary) <= max_chars:
        return summary
    return summary[: max_chars - 1].rstrip() + "..."


def _parse_date_arg(value: str, *, is_end: bool) -> datetime:
    try:
        dt = datetime.strptime(value.strip(), "%Y-%m-%d")
    except Exception as exc:
        raise SystemExit(f"Invalid date '{value}'. Use YYYY-MM-DD.") from exc
    if is_end:
        return datetime(dt.year, dt.month, dt.day, 23, 59, 59, 999000, tzinfo=timezone.utc)
    return datetime(dt.year, dt.month, dt.day, 0, 0, 0, tzinfo=timezone.utc)


def _truncate_text(text: str, max_chars: int) -> str:
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 1].rstrip() + "..."


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Import historical Zendesk tickets for context learning.")
    parser.add_argument("--days", type=int, default=30, help="How many days back to import (default: 30).")
    parser.add_argument("--start-date", type=str, help="Start date (YYYY-MM-DD, inclusive).")
    parser.add_argument("--end-date", type=str, help="End date (YYYY-MM-DD, inclusive).")
    parser.add_argument("--dry-run", action="store_true", help="Run extraction without storing results.")
    parser.add_argument("--no-dry-run", action="store_true", help="Persist results (overrides ZENDESK_DRY_RUN).")
    parser.add_argument("--skip-existing", action="store_true", help="Skip tickets already stored.")
    parser.add_argument("--no-skip-existing", action="store_true", help="Process even if already stored.")
    parser.add_argument("--require-nature-field", action="store_true", help="Require nature-of-inquiry field match.")
    parser.add_argument("--allow-heuristic", action="store_true", help="Allow tag/keyword fallback for category.")
    return parser.parse_args()


def _build_config_from_args(args: argparse.Namespace) -> ImportConfig:
    if (args.start_date or args.end_date) and not (args.start_date and args.end_date):
        raise SystemExit("Both --start-date and --end-date are required together.")

    windows_ids = list(settings.zendesk_windows_brand_ids or [])
    if not windows_ids and settings.zendesk_brand_id:
        windows_ids = [str(settings.zendesk_brand_id)]
    nature_field_ids = list(settings.zendesk_nature_field_ids or [])
    if not nature_field_ids and settings.zendesk_nature_field_id:
        nature_field_ids = [str(settings.zendesk_nature_field_id)]
    rpm_limit = int(getattr(settings, "zendesk_import_rpm_limit", 10))
    dry_run = True
    if getattr(args, "no_dry_run", False):
        dry_run = False
    if getattr(args, "dry_run", False):
        dry_run = True
    skip_existing = bool(args.skip_existing or not args.no_skip_existing)
    require_field = bool(args.require_nature_field or settings.zendesk_nature_require_field)
    if args.allow_heuristic:
        require_field = False
    start_dt = _parse_date_arg(args.start_date, is_end=False) if args.start_date else None
    end_dt = _parse_date_arg(args.end_date, is_end=True) if args.end_date else None
    return ImportConfig(
        days_back=max(1, int(args.days)),
        dry_run=dry_run,
        skip_existing=skip_existing,
        require_nature_field=require_field,
        windows_brand_ids=[str(v) for v in windows_ids if str(v).strip()],
        nature_field_ids=[str(v) for v in nature_field_ids if str(v).strip()],
        nature_category_map=dict(settings.zendesk_nature_category_map or {}),
        rpm_limit=rpm_limit,
        start_dt=start_dt,
        end_dt=end_dt,
    )


def main() -> None:
    args = _parse_args()
    config = _build_config_from_args(args)
    importer = HistoricalImporter(config=config)
    asyncio.run(importer.run_import())


if __name__ == "__main__":
    main()
