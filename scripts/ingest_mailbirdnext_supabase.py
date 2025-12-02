"""Load MailbirdNext knowledge files into the Supabase mailbird_knowledge table.

Run locally with access to SUPABASE_SERVICE_KEY so the service role can bypass
RLS and upsert the rows. Embeddings are computed inline (Gemini 3072-dim) so
the entries are immediately searchable by vector RPCs and the Supabase
subagent.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

from dotenv import load_dotenv
from supabase import Client, create_client  # type: ignore

from app.db.embedding.utils import get_embedding_model
from app.db.embedding_config import EXPECTED_DIM, assert_dim


PROJECT_ROOT = Path(__file__).resolve().parent.parent
KNOWLEDGE_DIR = PROJECT_ROOT / "knowledge_mailbirdnext"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def load_provider_settings(path: Path) -> Dict[str, Any]:
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def provider_markdown(slug: str, data: Dict[str, Any]) -> str:
    incoming = data.get("incoming", {}) or {}
    outgoing = data.get("outgoing", {}) or {}

    def _fmt_incoming() -> List[str]:
        lines: List[str] = []
        for proto in ("imap", "pop3"):
            cfg = incoming.get(proto)
            if not cfg:
                continue
            lines.append(f"- {proto.upper()}: {cfg.get('host')}:{cfg.get('port')} ({cfg.get('security')})")
        return lines

    def _fmt_outgoing() -> str:
        if not outgoing:
            return ""
        return f"SMTP: {outgoing.get('host')}:{outgoing.get('port')} ({outgoing.get('security')})"

    lines: List[str] = [
        f"# {data.get('displayName') or slug} ({slug})",
        "",
        f"- Identity: {data.get('identity')} | Server: {data.get('serverType')} | Auth: {data.get('authType')}",
        f"- OAuth required: {data.get('requiresOAuth')}",
    ]

    inc_lines = _fmt_incoming()
    if inc_lines:
        lines.append("\n## Incoming")
        lines.extend(inc_lines)

    out_line = _fmt_outgoing()
    if out_line:
        lines.append("\n## Outgoing")
        lines.append(f"- {out_line}")

    notes = data.get("notes") or []
    if notes:
        lines.append("\n## Notes")
        lines.extend([f"- {n}" for n in notes])

    errors = data.get("commonErrors") or []
    if errors:
        lines.append("\n## Common Errors")
        lines.extend([f"- {err}" for err in errors])

    return "\n".join(lines).strip()


def build_entries() -> List[Dict[str, Any]]:
    md_technical = load_text(KNOWLEDGE_DIR / "mailbird_technical_knowledge.md")
    md_troubleshoot = load_text(KNOWLEDGE_DIR / "mailbird_troubleshooting_guide.md")
    providers_data = load_provider_settings(KNOWLEDGE_DIR / "mailbird_provider_settings.json")

    entries: List[Dict[str, Any]] = [
        {
            "url": "mailbirdnext://technical-reference",
            "markdown": md_technical,
            "content": None,
            "metadata": {
                "title": "MailbirdNext Technical Reference",
                "source": "mailbirdnext",
                "tags": ["mailbird", "technical", "reference"],
            },
            "scraped_at": _now_iso(),
        },
        {
            "url": "mailbirdnext://troubleshooting-guide",
            "markdown": md_troubleshoot,
            "content": None,
            "metadata": {
                "title": "MailbirdNext Troubleshooting Guide",
                "source": "mailbirdnext",
                "tags": ["mailbird", "troubleshooting", "guide"],
            },
            "scraped_at": _now_iso(),
        },
        {
            "url": "mailbirdnext://provider-settings/full",
            "markdown": json.dumps(providers_data, indent=2),
            "content": None,
            "metadata": {
                "title": "Mailbird Provider Settings (JSON)",
                "source": "mailbirdnext",
                "tags": ["mailbird", "providers", "json"],
                "version": providers_data.get("version"),
            },
            "scraped_at": _now_iso(),
        },
    ]

    providers = providers_data.get("providers", {}) or {}
    for slug, data in providers.items():
        entries.append(
            {
                "url": f"mailbirdnext://provider/{slug.lower()}",
                "markdown": provider_markdown(slug, data),
                "content": None,
                "metadata": {
                    "title": f"Mailbird Provider: {data.get('displayName') or slug}",
                    "provider": slug,
                    "source": "mailbirdnext",
                    "tags": ["mailbird", "provider", slug.lower()],
                    "authType": data.get("authType"),
                    "requiresOAuth": data.get("requiresOAuth"),
                    "version": providers_data.get("version"),
                },
                "scraped_at": _now_iso(),
            }
        )

    return entries


def embed_entries(embedder, entries: List[Dict[str, Any]]) -> None:
    for entry in entries:
        text = entry.get("markdown") or entry.get("content") or ""
        text = (text or "").strip()
        # Trim overly long blobs to keep embedding request size reasonable
        if len(text) > 8000:
            text = text[:8000]
        vector = embedder.embed_query(text)
        assert_dim(vector, f"embedding for {entry['url']}")
        entry["embedding"] = vector


def upsert_entries(client: Client, entries: List[Dict[str, Any]]) -> None:
    # Use on_conflict=url to avoid duplicates if rerun
    resp = client.table("mailbird_knowledge").upsert(entries, on_conflict="url").execute()
    if getattr(resp, "error", None):
        raise RuntimeError(f"Supabase upsert failed: {resp.error}")


def main() -> None:
    load_dotenv(PROJECT_ROOT / ".env")

    url = os.getenv("SUPABASE_URL")
    key = os.getenv("SUPABASE_SERVICE_KEY") or os.getenv("SUPABASE_ANON_KEY")
    if not url or not key:
        raise RuntimeError("SUPABASE_URL and SUPABASE_SERVICE_KEY (or SUPABASE_ANON_KEY) must be set in .env")

    embedder = get_embedding_model()
    entries = build_entries()
    embed_entries(embedder, entries)

    client = create_client(url, key)
    upsert_entries(client, entries)

    print(f"Upserted {len(entries)} MailbirdNext knowledge rows with embeddings (dim={EXPECTED_DIM})")


if __name__ == "__main__":
    main()
