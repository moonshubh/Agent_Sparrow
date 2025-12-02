"""Zendesk Macros Export Script.

Exports all active macros from Zendesk and stores them in Supabase for Agent Sparrow
to use as knowledge. Macros contain pre-defined responses for common support scenarios.

Usage:
    python -m app.db.zendesk_macros_export

Environment variables:
    ZENDESK_SUBDOMAIN - Zendesk instance subdomain (e.g., 'mailbird' for mailbird.zendesk.com)
    ZENDESK_EMAIL     - API user email
    ZENDESK_API_TOKEN - API token
    SUPABASE_URL      - Supabase project URL
    SUPABASE_KEY      - Supabase service role key (or anon key with insert permissions)
    GEMINI_API_KEY    - Google Gemini API key for embeddings
"""

from __future__ import annotations

import os
import re
import json
import time
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv
import requests

# Load environment variables
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
load_dotenv(os.path.join(PROJECT_ROOT, ".env"), override=True)
load_dotenv(os.path.join(PROJECT_ROOT, ".env.local"), override=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


# --- Environment helpers ---
def _env(name: str) -> Optional[str]:
    v = os.getenv(name)
    return v.strip() if isinstance(v, str) and v.strip() else None


def _env_float(name: str, default: float) -> float:
    v = _env(name)
    if not v:
        return default
    try:
        parsed = float(v)
        return parsed if parsed > 0 else default
    except Exception:
        return default


def _env_bool(name: str, default: bool) -> bool:
    v = _env(name)
    if v is None:
        return default
    v = v.strip().lower()
    if v in ("1", "true", "yes", "y", "on"):
        return True
    if v in ("0", "false", "no", "n", "off"):
        return False
    return default


# --- Configuration ---
EMBED_MIN_INTERVAL_SEC = _env_float("GEMINI_MIN_INTERVAL_SEC", 4.0)
DRY_RUN = _env_bool("MACROS_DRY_RUN", False)
ACTIVE_ONLY = _env_bool("MACROS_ACTIVE_ONLY", True)
ENGLISH_ONLY = _env_bool("MACROS_ENGLISH_ONLY", True)  # Default: English only


def strip_html(text: str) -> str:
    """Strip HTML tags from text."""
    if not text:
        return ""
    try:
        return re.sub(r"<[^>]+>", " ", text)
    except Exception:
        return text


def get_zendesk_client_config() -> Dict[str, str]:
    """Get Zendesk configuration from environment."""
    subdomain = _env("ZENDESK_SUBDOMAIN")
    email = _env("ZENDESK_EMAIL")
    api_token = _env("ZENDESK_API_TOKEN")

    if not subdomain or not email or not api_token:
        raise RuntimeError(
            "Missing Zendesk credentials. Set ZENDESK_SUBDOMAIN, ZENDESK_EMAIL, ZENDESK_API_TOKEN"
        )

    return {
        "subdomain": subdomain,
        "email": email,
        "api_token": api_token,
    }


def create_zendesk_headers(email: str, api_token: str) -> Dict[str, str]:
    """Create headers for Zendesk API requests."""
    import base64
    auth_bytes = f"{email}/token:{api_token}".encode("utf-8")
    b64 = base64.b64encode(auth_bytes).decode("ascii")
    return {
        "Authorization": f"Basic {b64}",
        "Content-Type": "application/json",
        "User-Agent": "agent-sparrow-macros-export/1.0",
    }


def fetch_all_macros(
    subdomain: str,
    headers: Dict[str, str],
    active_only: bool = True
) -> List[Dict[str, Any]]:
    """Fetch all macros from Zendesk API with pagination.

    Raises:
        requests.RequestException: When the Zendesk API request fails.
    """
    base_url = f"https://{subdomain}.zendesk.com/api/v2"
    all_macros: List[Dict[str, Any]] = []

    # Use /macros/active for active only, /macros for all
    endpoint = "macros/active" if active_only else "macros"
    next_url: Optional[str] = f"{base_url}/{endpoint}.json?per_page=100"
    page = 1
    max_pages = 50  # Safety guard

    while next_url and page <= max_pages:
        try:
            logger.info(f"Fetching macros page {page}...")
            resp = requests.get(next_url, headers=headers, timeout=30)
            resp.raise_for_status()
            payload = resp.json()
        except requests.RequestException as exc:
            logger.exception(
                "Zendesk API error during macros fetch",
                extra={"page": page, "fetched": len(all_macros)},
            )
            raise

        macros = payload.get("macros", [])
        if not macros:
            break

        all_macros.extend(macros)
        next_url = payload.get("next_page")
        page += 1

        # Rate limit respect
        time.sleep(0.5)

    logger.info(f"Fetched {len(all_macros)} macros from Zendesk")
    return all_macros


def extract_comment_from_actions(actions: List[Dict[str, Any]]) -> tuple[str, str]:
    """Extract comment text from macro actions.

    Returns:
        Tuple of (plain_text, html_text)
    """
    plain_text = ""
    html_text = ""

    for action in actions:
        field = action.get("field")
        value = action.get("value")

        if not value:
            continue

        # Comment actions
        if field in ("comment_value", "comment_value_html"):
            if field == "comment_value":
                plain_text = str(value)
            elif field == "comment_value_html":
                html_text = str(value)
                if not plain_text:
                    plain_text = strip_html(str(value))

    return plain_text.strip(), html_text.strip()


# Non-English language indicators for filtering
NON_ENGLISH_INDICATORS = [
    # German
    "in German", "(German)", "auf Deutsch", "Hallo!", "Mein Name ist", "ich bin ein Agent",
    "Kundenzufriedenheit", "Entschuldigung", "Vielen Dank",
    # French
    "in French", "(French)", "en français", "Bonjour!", "Je m'appelle", "je suis agent",
    "bonheur client", "Merci",
    # Spanish
    "in Spanish", "(Spanish)", "en español", "Hola!", "Mi nombre es", "soy un agente",
    "felicidad del cliente", "Gracias",
    # Italian
    "in Italian", "(Italian)", "in italiano", "Ciao!", "Mi chiamo", "sono un agente",
    "felicità del cliente", "Grazie",
    # Portuguese
    "in Portuguese", "(Portuguese)", "em português", "Olá!", "Meu nome é",
    # Dutch
    "in Dutch", "(Dutch)", "in het Nederlands", "Hallo!", "Mijn naam is",
]


def is_english_macro(title: str, comment_value: str) -> bool:
    """Check if a macro appears to be in English.

    Returns True if the macro doesn't contain non-English indicators.
    """
    combined_text = f"{title} {comment_value}".lower()

    for indicator in NON_ENGLISH_INDICATORS:
        if indicator.lower() in combined_text:
            return False

    return True


def get_supabase_client():
    """Create Supabase client."""
    from supabase import create_client

    url = _env("SUPABASE_URL")
    key = _env("SUPABASE_KEY") or _env("SUPABASE_ANON_KEY")

    if not url or not key:
        raise RuntimeError("Missing Supabase credentials. Set SUPABASE_URL and SUPABASE_KEY")

    return create_client(url, key)


def get_embedding_model():
    """Create Gemini embedding model."""
    from langchain_google_genai import embeddings as gen_embeddings
    from app.db.embedding_config import MODEL_NAME

    api_key = _env("GEMINI_API_KEY") or _env("GOOGLE_API_KEY")
    if not api_key:
        raise RuntimeError("Missing Gemini API key. Set GEMINI_API_KEY or GOOGLE_API_KEY")

    return gen_embeddings.GoogleGenerativeAIEmbeddings(
        model=MODEL_NAME,
        google_api_key=api_key
    )


def generate_embedding(embed_model, text: str, context: str = "macro") -> Optional[List[float]]:
    """Generate embedding for text with rate limiting and retry."""
    from app.db.embedding_config import EXPECTED_DIM

    if not text or len(text.strip()) < 10:
        logger.warning(f"Skipping embedding for {context}: text too short")
        return None

    max_attempts = 3
    for attempt in range(1, max_attempts + 1):
        try:
            time.sleep(EMBED_MIN_INTERVAL_SEC)
            vectors = embed_model.embed_documents([text])
            if vectors and len(vectors) > 0:
                vec = vectors[0]
                if len(vec) != EXPECTED_DIM:
                    logger.error(f"Dimension mismatch for {context}: got {len(vec)}, expected {EXPECTED_DIM}")
                    return None
                return vec
        except Exception as e:
            msg = str(e).lower()
            if "rate" in msg or "quota" in msg or "429" in msg:
                wait = min(60, 10 * attempt)
                logger.warning(f"Rate limit on {context} (attempt {attempt}); waiting {wait}s")
                time.sleep(wait)
            else:
                logger.error(f"Embedding error for {context}: {e}")
                if attempt == max_attempts:
                    return None
                time.sleep(5)

    return None


def export_macros():
    """Main export function."""
    logger.info("=" * 60)
    logger.info("Zendesk Macros Export")
    logger.info("=" * 60)

    if DRY_RUN:
        logger.info("[DRY_RUN MODE] No data will be written to Supabase")
    if ENGLISH_ONLY:
        logger.info("[ENGLISH_ONLY MODE] Only English macros will be exported")

    # Get Zendesk config
    config = get_zendesk_client_config()
    headers = create_zendesk_headers(config["email"], config["api_token"])

    # Fetch macros
    try:
        macros = fetch_all_macros(
            subdomain=config["subdomain"],
            headers=headers,
            active_only=ACTIVE_ONLY
        )
    except requests.RequestException:
        logger.error("Failed to fetch macros; export aborted.")
        return

    if not macros:
        logger.warning("No macros found. Exiting.")
        return

    # Initialize Supabase and embedding model
    supabase = get_supabase_client()
    embed_model = get_embedding_model()

    # Process each macro
    success_count = 0
    skip_count = 0
    non_english_count = 0
    error_count = 0

    for i, macro in enumerate(macros, 1):
        zendesk_id = macro.get("id")
        title = macro.get("title", "Untitled")
        description = macro.get("description", "")
        actions = macro.get("actions", [])
        active = macro.get("active", True)
        restriction = macro.get("restriction")
        usage_7d = macro.get("usage_7d", 0)
        usage_30d = macro.get("usage_30d", 0)

        # Extract comment text first for language check
        comment_value, comment_value_html = extract_comment_from_actions(actions)

        # Filter non-English macros if enabled
        if ENGLISH_ONLY and not is_english_macro(title, comment_value):
            logger.debug(f"  Skipping non-English macro: {title}")
            non_english_count += 1
            continue

        logger.info(f"[{i}/{len(macros)}] Processing: {title} (ID: {zendesk_id})")

        if not comment_value:
            logger.info("  Skipping: No comment/reply content in macro")
            skip_count += 1
            continue

        # Generate embedding from title + description + comment
        embed_text = f"{title}\n\n{description}\n\n{comment_value}"
        embedding = generate_embedding(embed_model, embed_text, f"macro-{zendesk_id}")

        if embedding is None:
            logger.warning(f"  Failed to generate embedding for macro {zendesk_id}")
            error_count += 1
            continue

        # Prepare row for Supabase
        row = {
            "zendesk_id": zendesk_id,
            "title": title,
            "description": description,
            "comment_value": comment_value,
            "comment_value_html": comment_value_html or None,
            "actions": actions,
            "active": active,
            "restriction": restriction,
            "usage_7d": usage_7d or 0,
            "usage_30d": usage_30d or 0,
            "embedding": embedding,
            "metadata": {
                "source": "zendesk_macros",
                "exported_at": datetime.now(timezone.utc).isoformat(),
            },
            "synced_at": datetime.now(timezone.utc).isoformat(),
        }

        if DRY_RUN:
            logger.info(f"  [DRY_RUN] Would upsert macro: {title}")
            success_count += 1
            continue

        # Upsert to Supabase
        try:
            supabase.table("zendesk_macros").upsert(
                row,
                on_conflict="zendesk_id"
            ).execute()
            logger.info(f"  Upserted: {title}")
            success_count += 1
        except Exception as e:
            logger.error(f"  Failed to upsert macro {zendesk_id}: {e}")
            error_count += 1

    # Summary
    logger.info("=" * 60)
    logger.info("Export Complete")
    logger.info(f"  Total macros:     {len(macros)}")
    logger.info(f"  Successful:       {success_count}")
    logger.info(f"  Skipped (empty):  {skip_count}")
    if ENGLISH_ONLY:
        logger.info(f"  Non-English:      {non_english_count}")
    logger.info(f"  Errors:           {error_count}")
    logger.info("=" * 60)


def list_macros_preview():
    """Preview macros without exporting (useful for testing connection)."""
    logger.info("Previewing Zendesk macros (no export)...")

    config = get_zendesk_client_config()
    headers = create_zendesk_headers(config["email"], config["api_token"])

    try:
        macros = fetch_all_macros(
            subdomain=config["subdomain"],
            headers=headers,
            active_only=ACTIVE_ONLY
        )
    except requests.RequestException:
        logger.error("Failed to fetch macros for preview.")
        return

    print(f"\nFound {len(macros)} macros:\n")
    for macro in macros[:20]:  # Show first 20
        zendesk_id = macro.get("id")
        title = macro.get("title", "Untitled")
        active = macro.get("active", True)
        actions = macro.get("actions", [])
        comment_value, _ = extract_comment_from_actions(actions)

        status = "active" if active else "inactive"
        has_reply = "yes" if comment_value else "no"
        preview = comment_value[:80] + "..." if len(comment_value) > 80 else comment_value

        print(f"  [{zendesk_id}] {title}")
        print(f"      Status: {status}, Has Reply: {has_reply}")
        if preview:
            print(f"      Preview: {preview}")
        print()

    if len(macros) > 20:
        print(f"  ... and {len(macros) - 20} more macros")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Export Zendesk macros to Supabase")
    parser.add_argument(
        "--preview",
        action="store_true",
        help="Preview macros without exporting"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Run without writing to Supabase"
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Include inactive macros (default: active only)"
    )
    parser.add_argument(
        "--all-languages",
        action="store_true",
        help="Include all languages (default: English only)"
    )

    args = parser.parse_args()

    if args.dry_run:
        DRY_RUN = True
    if args.all:
        ACTIVE_ONLY = False
    if args.all_languages:
        ENGLISH_ONLY = False

    if args.preview:
        list_macros_preview()
    else:
        export_macros()
