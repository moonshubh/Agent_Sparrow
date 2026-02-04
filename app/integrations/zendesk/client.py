from __future__ import annotations

import base64
import json
import logging
import threading
import time
from pathlib import Path
from typing import Optional, Dict, Any, List, Generator, Mapping
from datetime import datetime, timezone
from urllib.parse import quote

import requests

from app.core.settings import settings

logger = logging.getLogger(__name__)

_ZENDESK_RPM_LOCK = threading.Lock()
_ZENDESK_LAST_REQUEST_AT = 0.0


def zendesk_throttle(rpm_limit: int | None = None) -> None:
    """Best-effort process-wide Zendesk RPM throttle (thread-safe).

    This does not protect across multiple replicas/processes, but it prevents a single
    worker from bursting above the configured per-minute rate.
    """
    rpm = (
        int(rpm_limit)
        if rpm_limit is not None
        else int(getattr(settings, "zendesk_rpm_limit", 240))
    )
    if rpm <= 0:
        return
    min_interval_sec = 60.0 / float(rpm)

    global _ZENDESK_LAST_REQUEST_AT
    with _ZENDESK_RPM_LOCK:
        now = time.monotonic()
        elapsed = now - _ZENDESK_LAST_REQUEST_AT
        if elapsed < min_interval_sec:
            time.sleep(max(0.0, min_interval_sec - elapsed))
        _ZENDESK_LAST_REQUEST_AT = time.monotonic()


def _retry_after_seconds(headers: Mapping[str, str]) -> float | None:
    """Parse Retry-After / rate-limit reset headers into seconds."""
    ra = headers.get("Retry-After") or headers.get("retry-after")
    if ra:
        try:
            sec = float(str(ra).strip())
            return max(0.0, sec)
        except Exception:
            # RFC 7231 allows HTTP-date; handle best-effort.
            try:
                from email.utils import parsedate_to_datetime

                dt = parsedate_to_datetime(str(ra).strip())
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                return max(0.0, (dt - datetime.now(timezone.utc)).total_seconds())
            except Exception:
                return None

    reset = headers.get("X-Rate-Limit-Reset") or headers.get("x-rate-limit-reset")
    if reset:
        try:
            reset_epoch = float(str(reset).strip())
            return max(0.0, reset_epoch - time.time())
        except Exception:
            return None

    return None


class ZendeskRateLimitError(RuntimeError):
    def __init__(
        self,
        *,
        operation: str,
        status_code: int = 429,
        retry_after_seconds: float | None = None,
        request_id: str | None = None,
    ) -> None:
        self.operation = operation
        self.status_code = int(status_code)
        self.retry_after_seconds = retry_after_seconds
        self.request_id = request_id
        super().__init__(
            f"Zendesk rate limited: {self.status_code} op={operation} "
            f"retry_after={retry_after_seconds} req_id={request_id}"
        )

    @classmethod
    def from_response(
        cls, resp: requests.Response, *, operation: str
    ) -> "ZendeskRateLimitError":
        rid = resp.headers.get("X-Request-Id") or resp.headers.get(
            "X-Zendesk-Request-Id"
        )
        return cls(
            operation=operation,
            status_code=int(resp.status_code),
            retry_after_seconds=_retry_after_seconds(resp.headers),
            request_id=rid,
        )


class ZendeskClient:
    """Minimal Zendesk REST client for posting internal notes.

    Auth: API token with Basic auth where username is "{email}/token" and password is the API token.
    """

    def __init__(
        self,
        *,
        subdomain: str,
        email: str,
        api_token: str,
        dry_run: bool = False,
        rpm_limit: Optional[int] = None,
        session: Optional[requests.Session] = None,
    ) -> None:
        if not subdomain or not email or not api_token:
            raise ValueError("ZendeskClient requires subdomain, email, and api_token")
        self.base_url = f"https://{subdomain}.zendesk.com/api/v2"
        self.email = email
        self.api_token = api_token
        self.dry_run = dry_run
        self.session = session or requests.Session()
        self._user_cache: Dict[str, Dict[str, Any]] = {}
        self._rpm_limit = int(rpm_limit) if rpm_limit and int(rpm_limit) > 0 else None

        # Prepare Basic auth header: base64("email/token:api_token")
        auth_bytes = f"{email}/token:{api_token}".encode("utf-8")
        b64 = base64.b64encode(auth_bytes).decode("ascii")
        self._headers = {
            "Authorization": f"Basic {b64}",
            "Content-Type": "application/json",
            "User-Agent": "mb-sparrow-zendesk-integrator/1.0",
        }

    def _throttle(self) -> None:
        zendesk_throttle(self._rpm_limit)

    def upload_file(
        self,
        file_path: str | Path,
        *,
        filename: str | None = None,
    ) -> Dict[str, Any]:
        """Upload a file to Zendesk and return the upload token.

        Uses: POST /uploads.json?filename={name}
        """

        path = Path(file_path)
        if not path.exists() or not path.is_file():
            raise FileNotFoundError(str(path))

        name = (filename or path.name or "upload").strip() or "upload"
        url = f"{self.base_url}/uploads.json?filename={quote(name)}"

        if self.dry_run:
            logger.info("[DRY_RUN] Would upload file to Zendesk: %s", name)
            return {"dry_run": True, "file_name": name, "token": "dry_run"}

        headers = dict(self._headers)
        headers["Content-Type"] = "application/binary"

        with path.open("rb") as f:
            self._throttle()
            resp = self.session.post(url, headers=headers, data=f, timeout=60)

        if resp.status_code == 429:
            raise ZendeskRateLimitError.from_response(resp, operation="upload_file")
        if resp.status_code >= 400:
            rid = resp.headers.get("X-Request-Id") or resp.headers.get(
                "X-Zendesk-Request-Id"
            )
            logger.warning(
                "Zendesk upload failed (%s) req_id=%s", resp.status_code, rid
            )
            raise RuntimeError(f"Zendesk upload failed: {resp.status_code}")

        # Zendesk sometimes returns JSON with a `text/plain` content-type.
        try:
            data = resp.json()
        except Exception:
            try:
                data = json.loads(resp.text or "{}")
            except Exception:
                data = {}
        upload = data.get("upload") if isinstance(data, dict) else {}
        upload = upload if isinstance(upload, dict) else {}

        token = upload.get("token")
        attachment = upload.get("attachment")
        attachments = upload.get("attachments")

        attachment_dict: Dict[str, Any] | None = None
        if isinstance(attachment, dict):
            attachment_dict = attachment
        elif (
            isinstance(attachments, list)
            and attachments
            and isinstance(attachments[0], dict)
        ):
            attachment_dict = attachments[0]

        return {
            "token": token,
            "attachment": attachment_dict,
            "raw": data,
        }

    def add_internal_note(
        self,
        ticket_id: int | str,
        body: str,
        add_tag: Optional[str] = None,
        use_html: bool = False,
        uploads: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """Add a private (internal) note to a ticket. Optionally add a tag.

        Uses PUT /tickets/{id}.json with payload:
        {
          "ticket": {
            "comment": {"body" or "html_body": "...", "public": false},
            "additional_tags": ["mb_auto_triaged"]
          }
        }
        """
        url = f"{self.base_url}/tickets/{ticket_id}.json"
        # Build comment with optional HTML
        comment: Dict[str, Any] = {"public": False}
        if uploads:
            comment["uploads"] = [
                u for u in uploads if isinstance(u, str) and u.strip()
            ]
        # Auto-detect if string appears to contain HTML when use_html not explicitly set
        is_html_candidate = bool(
            use_html and isinstance(body, str) and ("<" in body and ">" in body)
        )
        if is_html_candidate:
            comment["html_body"] = body or ""
        else:
            comment["body"] = body or ""
        ticket: Dict[str, Any] = {"comment": comment}
        if add_tag:
            # Best-effort tag add. Some Zendesk accounts ignore `additional_tags` on update,
            # so we merge into the explicit `tags` list when we can.
            try:
                cur = self.get_ticket(ticket_id) or {}
                existing = cur.get("tags") if isinstance(cur, dict) else None
                existing_tags = (
                    [t for t in existing if isinstance(t, str)]
                    if isinstance(existing, list)
                    else []
                )
                merged = list(existing_tags)
                if add_tag not in merged:
                    merged.append(add_tag)
                if merged:
                    ticket["tags"] = merged
            except ZendeskRateLimitError:
                raise
            except Exception:
                ticket["additional_tags"] = [add_tag]

        payload = {"ticket": ticket}
        if self.dry_run:
            logger.info("[DRY_RUN] Would add internal note to ticket %s", ticket_id)
            return {
                "dry_run": True,
                "ticket_id": ticket_id,
                "uploads": comment.get("uploads"),
            }

        # First attempt (maybe with html_body)
        self._throttle()
        resp = self.session.put(
            url, headers=self._headers, data=json.dumps(payload), timeout=20
        )
        if resp.status_code == 429:
            raise ZendeskRateLimitError.from_response(
                resp, operation="add_internal_note"
            )
        if resp.status_code >= 400 and "html_body" in comment:
            # Fallback to plain body if HTML rejected
            try:
                comment.pop("html_body", None)
                comment["body"] = body or ""
                payload = {"ticket": ticket}
                self._throttle()
                resp = self.session.put(
                    url, headers=self._headers, data=json.dumps(payload), timeout=20
                )
                if resp.status_code == 429:
                    raise ZendeskRateLimitError.from_response(
                        resp, operation="add_internal_note_fallback_plain"
                    )
            except Exception:
                pass
        if resp.status_code >= 400:
            rid = resp.headers.get("X-Request-Id") or resp.headers.get(
                "X-Zendesk-Request-Id"
            )
            logger.warning("Zendesk PUT failed (%s) req_id=%s", resp.status_code, rid)
            raise RuntimeError(f"Zendesk update failed: {resp.status_code}")
        try:
            return resp.json()
        except Exception:
            return {"status": "ok", "code": resp.status_code}

    def get_ticket_comments(
        self, ticket_id: int | str, limit: int = 5
    ) -> List[Dict[str, Any]]:
        """Return up to 'limit' most recent comments for a ticket (best-effort).

        Notes:
        - Uses Basic auth prepared in __init__
        - Returns an empty list on any failure; callers should treat as optional context
        """
        url = f"{self.base_url}/tickets/{ticket_id}/comments.json?sort_order=desc"
        try:
            self._throttle()
            resp = self.session.get(url, headers=self._headers, timeout=20)
            if resp.status_code >= 400:
                return []
            data = (
                resp.json()
                if resp.headers.get("Content-Type", "").startswith("application/json")
                else {}
            )
            comments = data.get("comments") or []
            if not isinstance(comments, list):
                return []
            # Return only the top-N recent items
            return comments[: max(1, int(limit))]
        except Exception:
            return []

    def get_ticket_comments_all(
        self, ticket_id: int | str, *, public_only: bool = False
    ) -> List[Dict[str, Any]]:
        """Return all comments for a ticket in chronological order."""
        url = f"{self.base_url}/tickets/{ticket_id}/comments.json?sort_order=asc&include=attachments"
        try:
            self._throttle()
            resp = self.session.get(url, headers=self._headers, timeout=30)
            if resp.status_code == 429:
                raise ZendeskRateLimitError.from_response(
                    resp, operation="get_ticket_comments_all"
                )
            if resp.status_code >= 400:
                return []
            data = (
                resp.json()
                if resp.headers.get("Content-Type", "").startswith("application/json")
                else {}
            )
            comments = data.get("comments") or []
            if not isinstance(comments, list):
                return []
            if public_only:
                return [
                    c
                    for c in comments
                    if isinstance(c, dict) and c.get("public") is True
                ]
            return comments
        except ZendeskRateLimitError:
            raise
        except Exception:
            return []

    def search_tickets(
        self,
        query: str,
        *,
        per_page: int = 100,
        max_pages: int = 10,
    ) -> List[Dict[str, Any]]:
        """Search Zendesk tickets using the Search API (best-effort)."""
        q = (query or "").strip()
        if not q:
            return []

        page_limit = max(1, min(int(per_page), 100))
        max_pages = max(1, int(max_pages))

        results: List[Dict[str, Any]] = []
        next_url: Optional[str] = (
            f"{self.base_url}/search.json?query={quote(q)}&per_page={page_limit}"
        )
        pages = 0

        while next_url and pages < max_pages:
            self._throttle()
            resp = self.session.get(next_url, headers=self._headers, timeout=30)
            if resp.status_code == 429:
                raise ZendeskRateLimitError.from_response(
                    resp, operation="search_tickets"
                )
            if resp.status_code >= 400:
                break
            data = (
                resp.json()
                if resp.headers.get("Content-Type", "").startswith("application/json")
                else {}
            )
            batch = data.get("results") or []
            if isinstance(batch, list):
                for item in batch:
                    if isinstance(item, dict) and item.get("result_type") == "ticket":
                        results.append(item)
            next_url = data.get("next_page")
            pages += 1

        return results

    def get_last_public_comment_snippet(
        self, ticket_id: int | str, max_chars: int = 600
    ) -> Optional[str]:
        """Return the latest public comment body (plain text) truncated to max_chars.

        HTML bodies are stripped naively; sensitive data should be redacted by callers if needed.
        """
        import re

        def strip_html(text: str) -> str:
            try:
                return re.sub(r"<[^>]+>", " ", text)
            except Exception:
                return text

        comments = self.get_ticket_comments(ticket_id, limit=5)
        for c in comments:
            try:
                if not c.get("public", False):
                    continue
                body = c.get("body") or c.get("html_body") or ""
                if not isinstance(body, str):
                    continue
                body = strip_html(body).strip()
                if not body:
                    continue
                snippet = body[:max_chars]
                return snippet
            except Exception:
                continue
        return None

    def get_ticket(self, ticket_id: int | str) -> Dict[str, Any]:
        """Fetch ticket details (subject, description, etc.).

        Returns an empty dict on failure so callers can gracefully fall back.
        """
        url = f"{self.base_url}/tickets/{ticket_id}.json"
        try:
            self._throttle()
            resp = self.session.get(url, headers=self._headers, timeout=20)
            if resp.status_code == 429:
                raise ZendeskRateLimitError.from_response(resp, operation="get_ticket")
            if resp.status_code >= 400:
                return {}
            data = (
                resp.json()
                if resp.headers.get("Content-Type", "").startswith("application/json")
                else {}
            )
            return data.get("ticket") or {}
        except ZendeskRateLimitError:
            raise
        except Exception:
            return {}

    def export_resolved_tickets_cursor(
        self,
        start_time: int,
        per_page: int = 100,
        sleep_between_pages: float = 6.5,
        end_time: Optional[int] = None,
    ) -> Generator[Dict[str, Any], None, None]:
        """Cursor-based incremental export of resolved tickets.

        Uses: GET /api/v2/incremental/tickets/cursor.json?start_time={unix}
        Rate limit: caller-configured (sleep_between_pages used as a fallback throttle).
        Filters: status in ("solved", "closed")
        """

        def _ticket_epoch(ticket: Dict[str, Any]) -> Optional[int]:
            for key in ("updated_at", "solved_at", "closed_at", "created_at"):
                raw = ticket.get(key)
                if not raw:
                    continue
                try:
                    dt = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
                    if dt.tzinfo is None:
                        dt = dt.replace(tzinfo=timezone.utc)
                    return int(dt.timestamp())
                except Exception:
                    continue
            return None

        last_seen_time: Optional[int] = None
        can_stop_early = True
        url = f"{self.base_url}/incremental/tickets/cursor.json?start_time={int(start_time)}&per_page={int(per_page)}"
        while url:
            try:
                self._throttle()
                resp = self.session.get(url, headers=self._headers, timeout=30)
                if resp.status_code >= 400:
                    rid = resp.headers.get("X-Request-Id") or resp.headers.get(
                        "X-Zendesk-Request-Id"
                    )
                    logger.warning(
                        "Zendesk export failed (%s) req_id=%s", resp.status_code, rid
                    )
                    break
                data = (
                    resp.json()
                    if resp.headers.get("Content-Type", "").startswith(
                        "application/json"
                    )
                    else {}
                )
            except Exception:
                break

            tickets = data.get("tickets") or []
            if isinstance(tickets, list):
                page_times: List[int] = []
                for ticket in tickets:
                    if not isinstance(ticket, dict):
                        continue
                    t_epoch = _ticket_epoch(ticket)
                    if t_epoch is not None:
                        page_times.append(t_epoch)
                        if last_seen_time is not None and t_epoch < last_seen_time:
                            can_stop_early = False
                        last_seen_time = t_epoch
                if (
                    end_time
                    and page_times
                    and len(page_times) == len(tickets)
                    and can_stop_early
                ):
                    if min(page_times) > int(end_time):
                        break

                for ticket in tickets:
                    if not isinstance(ticket, dict):
                        continue
                    status = str(ticket.get("status") or "").lower()
                    if status in {"solved", "closed"}:
                        yield ticket

            if data.get("end_of_stream") is True:
                break

            next_page = data.get("next_page")
            if isinstance(next_page, str) and next_page.strip():
                url = next_page.strip()
            else:
                after_cursor = data.get("after_cursor")
                if after_cursor:
                    url = f"{self.base_url}/incremental/tickets/cursor.json?cursor={after_cursor}"
                else:
                    break

            if sleep_between_pages:
                time.sleep(max(0.1, float(sleep_between_pages)))

    def get_ticket_audits(
        self,
        ticket_id: int | str,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        """Get ticket audit trail (comments, macro applications, field changes).

        Uses: GET /api/v2/tickets/{ticket_id}/audits.json
        """
        audits: List[Dict[str, Any]] = []
        url = f"{self.base_url}/tickets/{ticket_id}/audits.json"
        while url:
            try:
                self._throttle()
                resp = self.session.get(url, headers=self._headers, timeout=30)
                if resp.status_code >= 400:
                    break
                data = (
                    resp.json()
                    if resp.headers.get("Content-Type", "").startswith(
                        "application/json"
                    )
                    else {}
                )
            except Exception:
                break

            batch = data.get("audits") or []
            if isinstance(batch, list):
                audits.extend([a for a in batch if isinstance(a, dict)])

            next_page = data.get("next_page")
            if isinstance(next_page, str) and next_page.strip():
                url = next_page.strip()
            else:
                break

        max_limit = max(1, int(limit))
        if len(audits) <= max_limit:
            return audits
        return audits[-max_limit:]

    def get_user_cached(self, user_id: int | str) -> Dict[str, Any]:
        """Get user details with in-memory caching.

        Uses: GET /api/v2/users/{user_id}.json
        Returns: {role: "agent"|"admin"|"end-user", name: "..."}
        """
        key = str(user_id)
        cached = self._user_cache.get(key)
        if cached:
            return cached

        url = f"{self.base_url}/users/{user_id}.json"
        data: Dict[str, Any] = {}
        try:
            self._throttle()
            resp = self.session.get(url, headers=self._headers, timeout=20)
            if resp.status_code >= 400:
                data = {}
            else:
                data = (
                    resp.json()
                    if resp.headers.get("Content-Type", "").startswith(
                        "application/json"
                    )
                    else {}
                )
        except Exception:
            data = {}

        user = data.get("user") if isinstance(data, dict) else {}
        if not isinstance(user, dict):
            user = {}
        profile = {
            "role": str(user.get("role") or "").lower(),
            "name": str(user.get("name") or "").strip(),
            "id": user.get("id"),
        }
        self._user_cache[key] = profile
        return profile
