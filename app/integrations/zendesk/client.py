from __future__ import annotations

import base64
import json
import logging
from typing import Optional, Dict, Any, List

import requests


logger = logging.getLogger(__name__)


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
        session: Optional[requests.Session] = None,
    ) -> None:
        if not subdomain or not email or not api_token:
            raise ValueError("ZendeskClient requires subdomain, email, and api_token")
        self.base_url = f"https://{subdomain}.zendesk.com/api/v2"
        self.email = email
        self.api_token = api_token
        self.dry_run = dry_run
        self.session = session or requests.Session()

        # Prepare Basic auth header: base64("email/token:api_token")
        auth_bytes = f"{email}/token:{api_token}".encode("utf-8")
        b64 = base64.b64encode(auth_bytes).decode("ascii")
        self._headers = {
            "Authorization": f"Basic {b64}",
            "Content-Type": "application/json",
            "User-Agent": "mb-sparrow-zendesk-integrator/1.0",
        }

    def add_internal_note(self, ticket_id: int | str, body: str, add_tag: Optional[str] = None, use_html: bool = False) -> Dict[str, Any]:
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
        # Auto-detect if string appears to contain HTML when use_html not explicitly set
        is_html_candidate = bool(use_html and isinstance(body, str) and ("<" in body and ">" in body))
        if is_html_candidate:
            comment["html_body"] = body or ""
        else:
            comment["body"] = body or ""
        ticket: Dict[str, Any] = {"comment": comment}
        if add_tag:
            ticket["additional_tags"] = [add_tag]

        payload = {"ticket": ticket}
        if self.dry_run:
            logger.info("[DRY_RUN] Would add internal note to ticket %s", ticket_id)
            return {"dry_run": True, "ticket_id": ticket_id}

        # First attempt (maybe with html_body)
        resp = self.session.put(url, headers=self._headers, data=json.dumps(payload), timeout=20)
        if resp.status_code >= 400 and "html_body" in comment:
            # Fallback to plain body if HTML rejected
            try:
                comment.pop("html_body", None)
                comment["body"] = body or ""
                payload = {"ticket": ticket}
                resp = self.session.put(url, headers=self._headers, data=json.dumps(payload), timeout=20)
            except Exception:
                pass
        if resp.status_code >= 400:
            rid = resp.headers.get("X-Request-Id") or resp.headers.get("X-Zendesk-Request-Id")
            logger.warning("Zendesk PUT failed (%s) req_id=%s", resp.status_code, rid)
            raise RuntimeError(f"Zendesk update failed: {resp.status_code}")
        try:
            return resp.json()
        except Exception:
            return {"status": "ok", "code": resp.status_code}

    def get_ticket_comments(self, ticket_id: int | str, limit: int = 5) -> List[Dict[str, Any]]:
        """Return up to 'limit' most recent comments for a ticket (best-effort).

        Notes:
        - Uses Basic auth prepared in __init__
        - Returns an empty list on any failure; callers should treat as optional context
        """
        url = f"{self.base_url}/tickets/{ticket_id}/comments.json?sort_order=desc"
        try:
            resp = self.session.get(url, headers=self._headers, timeout=20)
            if resp.status_code >= 400:
                return []
            data = resp.json() if resp.headers.get("Content-Type", "").startswith("application/json") else {}
            comments = data.get("comments") or []
            if not isinstance(comments, list):
                return []
            # Return only the top-N recent items
            return comments[: max(1, int(limit))]
        except Exception:
            return []

    def get_last_public_comment_snippet(self, ticket_id: int | str, max_chars: int = 600) -> Optional[str]:
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
                snippet = body[: max_chars]
                return snippet
            except Exception:
                continue
        return None
