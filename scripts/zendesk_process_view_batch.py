from __future__ import annotations

import argparse
import asyncio
import base64
import logging
import sys
import time
from pathlib import Path
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

import requests

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app.core.settings import settings
from app.integrations.zendesk.client import ZendeskClient
from app.integrations.zendesk.scheduler import _generate_reply, _quality_gate_issues


logger = logging.getLogger("zendesk_batch")


@dataclass(frozen=True)
class ViewMatch:
    view_id: int
    title: str


def _require_settings() -> Tuple[str, str, str]:
    subdomain = getattr(settings, "zendesk_subdomain", None)
    email = getattr(settings, "zendesk_email", None)
    api_token = getattr(settings, "zendesk_api_token", None)
    missing = [k for k, v in (("ZENDESK_SUBDOMAIN", subdomain), ("ZENDESK_EMAIL", email), ("ZENDESK_API_TOKEN", api_token)) if not v]
    if missing:
        raise SystemExit(f"Missing required env vars: {', '.join(missing)}")
    return str(subdomain), str(email), str(api_token)


def _auth_headers(email: str, api_token: str) -> Dict[str, str]:
    auth = f"{email}/token:{api_token}".encode("utf-8")
    b64 = base64.b64encode(auth).decode("ascii")
    return {
        "Authorization": f"Basic {b64}",
        "Content-Type": "application/json",
        "User-Agent": "mb-sparrow-zendesk-batch/1.0",
    }


def _zendesk_get_json(session: requests.Session, url: str, headers: Dict[str, str]) -> Dict[str, Any]:
    resp = session.get(url, headers=headers, timeout=30)
    resp.raise_for_status()
    data = resp.json() if resp.headers.get("Content-Type", "").startswith("application/json") else {}
    return data if isinstance(data, dict) else {}


def _pick_view(matches: Sequence[ViewMatch], needle: str) -> ViewMatch:
    if not matches:
        raise ValueError("no matches")
    needle_norm = needle.strip().lower()
    exact = [m for m in matches if m.title.strip().lower() == needle_norm]
    if exact:
        return exact[0]
    # Prefer shorter titles when multiple substring matches exist.
    return sorted(matches, key=lambda m: (len(m.title), m.title.lower(), m.view_id))[0]


def find_view_id_by_title(
    *,
    subdomain: str,
    email: str,
    api_token: str,
    title_contains: str,
) -> ViewMatch:
    base = f"https://{subdomain}.zendesk.com/api/v2"
    url: Optional[str] = f"{base}/views/active.json?per_page=100"
    session = requests.Session()
    headers = _auth_headers(email, api_token)

    needle = title_contains.strip().lower()
    matches: List[ViewMatch] = []

    while url:
        payload = _zendesk_get_json(session, url, headers)
        views = payload.get("views") or []
        if isinstance(views, list):
            for v in views:
                if not isinstance(v, dict):
                    continue
                title = v.get("title")
                view_id = v.get("id")
                if not isinstance(title, str) or not isinstance(view_id, int):
                    continue
                if needle in title.lower():
                    matches.append(ViewMatch(view_id=view_id, title=title))
        url = payload.get("next_page")

    try:
        chosen = _pick_view(matches, title_contains)
    except ValueError as exc:
        raise RuntimeError(f'No Zendesk view matched title "{title_contains}"') from exc
    return chosen


def iter_view_ticket_ids(
    *,
    subdomain: str,
    email: str,
    api_token: str,
    view_id: int,
    per_page: int = 100,
) -> Iterable[int]:
    base = f"https://{subdomain}.zendesk.com/api/v2"
    url: Optional[str] = f"{base}/views/{view_id}/tickets.json?per_page={max(1, min(100, int(per_page)))}"
    session = requests.Session()
    headers = _auth_headers(email, api_token)

    while url:
        payload = _zendesk_get_json(session, url, headers)
        tickets = payload.get("tickets") or []
        if isinstance(tickets, list):
            for t in tickets:
                if not isinstance(t, dict):
                    continue
                tid = t.get("id")
                if isinstance(tid, int):
                    yield tid
        url = payload.get("next_page")


async def process_tickets(
    *,
    ticket_ids: Sequence[int],
    max_successes: int,
    provider: str,
    model: str,
    post: bool,
    add_tag: str,
    skip_if_tagged: Optional[str],
    sleep_sec: float,
    max_runtime_sec: float | None,
) -> Dict[str, List[int]]:
    subdomain, email, api_token = _require_settings()

    zc = ZendeskClient(
        subdomain=subdomain,
        email=email,
        api_token=api_token,
        dry_run=not post,
    )

    processed: List[int] = []
    skipped: List[int] = []
    failed: List[int] = []

    max_successes = max(1, int(max_successes))
    started_at = time.monotonic()

    for i, ticket_id in enumerate(ticket_ids, start=1):
        if max_runtime_sec is not None and (time.monotonic() - started_at) >= float(max_runtime_sec):
            logger.info("Time limit reached (%.1fs); stopping early", float(max_runtime_sec))
            break
        if len(processed) >= max_successes:
            break
        logger.info("(%d/%d) ticket=%s starting", i, len(ticket_ids), ticket_id)
        try:
            ticket = await asyncio.to_thread(zc.get_ticket, ticket_id)
            if skip_if_tagged:
                tags = ticket.get("tags") if isinstance(ticket, dict) else None
                if isinstance(tags, list) and any(isinstance(t, str) and t == skip_if_tagged for t in tags):
                    logger.info("ticket=%s skipped (tagged=%s)", ticket_id, skip_if_tagged)
                    skipped.append(ticket_id)
                    continue

            subject = ticket.get("subject") if isinstance(ticket, dict) else None
            description = ticket.get("description") if isinstance(ticket, dict) else None
            run = await _generate_reply(ticket_id, subject, description, provider=provider, model=model)
            reply = run.reply
            use_html = bool(getattr(settings, "zendesk_use_html", True))
            gate_issues = _quality_gate_issues(reply, use_html=use_html)
            if gate_issues:
                raise RuntimeError(f"quality_gate_failed: {','.join(gate_issues)}")
            await asyncio.to_thread(
                zc.add_internal_note,
                ticket_id,
                reply,
                add_tag=add_tag,
                use_html=use_html,
            )
            processed.append(ticket_id)
            logger.info("ticket=%s done", ticket_id)
        except Exception as e:
            failed.append(ticket_id)
            logger.exception("ticket=%s failed: %s", ticket_id, e)

        if sleep_sec > 0:
            await asyncio.sleep(sleep_sec)

    return {"processed": processed, "skipped": skipped, "failed": failed}


async def main() -> None:
    parser = argparse.ArgumentParser(description="Process Zendesk tickets from a View and post internal notes.")
    parser.add_argument("--view-id", type=int, default=0, help="Zendesk view ID (preferred if known)")
    parser.add_argument("--view-title", type=str, default="New Win", help='Substring match for view title (default: "New Win")')
    parser.add_argument("--start-ticket", type=int, required=True, help="Ticket ID to start from (inclusive)")
    parser.add_argument("--count", type=int, default=10, help="Number of tickets to post notes to")
    parser.add_argument("--provider", type=str, default="google", help='Agent provider (default: "google")')
    parser.add_argument("--model", type=str, default="gemini-2.5-pro", help='Agent model (default: "gemini-2.5-pro")')
    parser.add_argument("--post", action="store_true", help="Actually post internal notes (otherwise dry-run)")
    parser.add_argument("--tag", type=str, default="mb_auto_triaged", help='Tag to add on update (default: "mb_auto_triaged")')
    parser.add_argument("--skip-if-tagged", type=str, default="mb_auto_triaged", help="Skip tickets that already have this tag")
    parser.add_argument("--sleep-sec", type=float, default=0.5, help="Sleep between tickets (seconds)")
    parser.add_argument("--max-minutes", type=float, default=0.0, help="Stop after N minutes (0 = no limit)")
    parser.add_argument("--log-level", type=str, default="INFO", help="Logging level (INFO, DEBUG, ...)")
    args = parser.parse_args()

    logging.basicConfig(
        level=getattr(logging, args.log_level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(message)s",
    )

    # Reduce extremely noisy dependency logs (keeps CLI output readable and avoids truncation).
    for noisy in ("httpx", "httpcore", "supabase", "postgrest"):
        try:
            logging.getLogger(noisy).setLevel(logging.WARNING)
        except Exception:
            pass

    # Normalize Loguru output volume (many core modules use Loguru directly).
    try:
        from loguru import logger as loguru_logger

        loguru_logger.remove()
        loguru_logger.add(sys.stdout, level=str(args.log_level).upper())
    except Exception:
        pass

    subdomain, email, api_token = _require_settings()

    if args.view_id and args.view_id > 0:
        view = ViewMatch(view_id=int(args.view_id), title=f"(id={args.view_id})")
    else:
        view = find_view_id_by_title(
            subdomain=subdomain,
            email=email,
            api_token=api_token,
            title_contains=str(args.view_title),
        )

    logger.info("Using view: id=%s title=%s", view.view_id, view.title)

    requested = max(1, int(args.count))
    start_ticket = int(args.start_ticket)

    window: List[int] = []
    started = False
    max_scan = max(200, requested * 25)

    for tid in iter_view_ticket_ids(
        subdomain=subdomain,
        email=email,
        api_token=api_token,
        view_id=view.view_id,
    ):
        if not started:
            if tid == start_ticket:
                started = True
            else:
                continue
        window.append(tid)
        if len(window) >= max_scan:
            break

    if not started:
        raise SystemExit(f"Start ticket {start_ticket} not found in view {view.view_id} ({view.title})")

    result = await process_tickets(
        ticket_ids=window,
        max_successes=requested,
        provider=str(args.provider),
        model=str(args.model),
        post=bool(args.post),
        add_tag=str(args.tag),
        skip_if_tagged=str(args.skip_if_tagged) if args.skip_if_tagged else None,
        sleep_sec=float(args.sleep_sec),
        max_runtime_sec=(float(args.max_minutes) * 60.0) if float(args.max_minutes) > 0 else None,
    )

    processed_ids = result["processed"]
    skipped_ids = result["skipped"]
    failed_ids = result["failed"]

    logger.info(
        "Run complete: processed=%d skipped=%d failed=%d post=%s provider=%s model=%s",
        len(processed_ids),
        len(skipped_ids),
        len(failed_ids),
        bool(args.post),
        args.provider,
        args.model,
    )
    if processed_ids:
        logger.info("Processed ticket IDs: %s", ",".join(str(i) for i in processed_ids))
    if skipped_ids:
        logger.info("Skipped ticket IDs: %s", ",".join(str(i) for i in skipped_ids))
    if failed_ids:
        logger.info("Failed ticket IDs: %s", ",".join(str(i) for i in failed_ids))

    # Non-zero exit code when we didn't reach the requested count in posting mode.
    if args.post and len(processed_ids) < requested:
        raise SystemExit(2)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.warning("Interrupted")
        sys.exit(130)
