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

    def add_internal_note(self, ticket_id: int | str, body: str, add_tag: Optional[str] = None) -> Dict[str, Any]:
        """Add a private (internal) note to a ticket. Optionally add a tag.

        Uses PUT /tickets/{id}.json with payload:
        {
          "ticket": {
            "comment": {"body": "...", "public": false},
            "additional_tags": ["mb_auto_triaged"]
          }
        }
        """
        url = f"{self.base_url}/tickets/{ticket_id}.json"
        ticket: Dict[str, Any] = {
            "comment": {"body": body or "", "public": False},
        }
        if add_tag:
            ticket["additional_tags"] = [add_tag]

        payload = {"ticket": ticket}
        if self.dry_run:
            logger.info("[DRY_RUN] Would add internal note to ticket %s", ticket_id)
            return {"dry_run": True, "ticket_id": ticket_id}

        resp = self.session.put(url, headers=self._headers, data=json.dumps(payload), timeout=20)
        if resp.status_code >= 400:
            rid = resp.headers.get("X-Request-Id") or resp.headers.get("X-Zendesk-Request-Id")
            logger.warning("Zendesk PUT failed (%s) req_id=%s", resp.status_code, rid)
            raise RuntimeError(f"Zendesk update failed: {resp.status_code}")
        try:
            return resp.json()
        except Exception:
            return {"status": "ok", "code": resp.status_code}
