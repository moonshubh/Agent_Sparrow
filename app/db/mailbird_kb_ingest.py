import os
import re
import json
import time
import base64
import hashlib
import logging
import threading
from datetime import datetime, timezone
from typing import List, Dict, Any, Set, Tuple, Optional, Callable
from concurrent.futures import ThreadPoolExecutor, as_completed

from dotenv import load_dotenv
from bs4 import BeautifulSoup

# External SDKs
from firecrawl import Firecrawl  # type: ignore
from supabase import create_client, Client  # type: ignore

# Embeddings (Gemini)
from langchain_google_genai import embeddings as gen_embeddings  # type: ignore

import requests

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
# Force .env values to load even if variables are set (possibly empty) in env
load_dotenv(os.path.join(PROJECT_ROOT, ".env"), override=True)


# --- Config ---
SEED_URL = "https://support.getmailbird.com/hc/en-us"
HOST_ALLOW = "support.getmailbird.com"
ARTICLE_PATH_FRAGMENT = "/hc/en-us/articles/"
INCLUDE_PREFIXES = [
    "https://support.getmailbird.com/hc/en-us/articles/",
    "https://support.getmailbird.com/hc/en-us/categories/",
]
EXCLUDE_SUBSTRINGS = ["/signin", "/search?", "/requests", "/attachments/"]

ZENDESK_API_BASE = "https://support.getmailbird.com/api/v2"
ZENDESK_LOCALE = "en-us"
ZENDESK_ARTICLES_ENDPOINT = (
    f"{ZENDESK_API_BASE}/help_center/{ZENDESK_LOCALE}/articles.json"
)
ZENDESK_PER_PAGE = 100


def normalize_url(url: str) -> str:
    return url.rstrip("/").lower()


def fetch_zendesk_article_map() -> Dict[str, Dict[str, Any]]:
    articles: Dict[str, Dict[str, Any]] = {}
    next_url: Optional[str] = (
        f"{ZENDESK_ARTICLES_ENDPOINT}?per_page={ZENDESK_PER_PAGE}&page=1"
    )
    page = 1
    max_pages = 100  # safety guard

    while next_url and page <= max_pages:
        try:
            resp = requests.get(next_url, timeout=30)
            resp.raise_for_status()
            payload = resp.json()
        except Exception as e:
            logger.warning(f"Zendesk API fetch failed (page {page}): {e}")
            break

        for article in payload.get("articles", []) or []:
            html_url = article.get("html_url")
            if not html_url:
                continue
            if article.get("draft"):
                continue

            norm = normalize_url(html_url)
            articles[norm] = {
                "id": article.get("id"),
                "html_url": html_url.rstrip("/"),
                "title": article.get("title") or article.get("name") or "",
                "section_id": article.get("section_id"),
                "author_id": article.get("author_id"),
                "label_names": article.get("label_names") or [],
                "locale": article.get("locale"),
                "source_locale": article.get("source_locale"),
                "created_at": article.get("created_at"),
                "updated_at": article.get("updated_at"),
                "edited_at": article.get("edited_at"),
                "outdated": article.get("outdated"),
                "body": article.get("body") or "",
            }

        next_url = payload.get("next_page")
        page += 1

    if next_url:
        logger.warning("Zendesk pagination stopped early; additional pages may exist")

    logger.info(f"Zendesk API discovered {len(articles)} published articles")
    return articles


def _env(name: str) -> Optional[str]:
    v = os.getenv(name)
    return v.strip() if isinstance(v, str) else None


def _env_int(name: str, default: int) -> int:
    v = _env(name)
    if not v:
        return default
    try:
        parsed = int(v)
        return parsed if parsed > 0 else default
    except Exception:
        return default


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


CONCURRENCY = _env_int(
    "FIRECRAWL_CONCURRENCY", 5
)  # upgraded plan supports higher parallelism
REQUEST_MIN_INTERVAL_SEC = _env_float(
    "FIRECRAWL_MIN_INTERVAL_SEC", 2.0
)  # throttle to stay within RPM limits
EMBED_MIN_INTERVAL_SEC = _env_float(
    "GEMINI_MIN_INTERVAL_SEC", 4.0
)  # Gemini often limited to ~15 RPM on default quota
PAGE_CAP = 320  # ample for >200 articles + indexes

PREWIPE = _env_bool("PREWIPE", True)
INGEST_LIMIT = _env_int("INGEST_LIMIT", 0)  # 0 = no limit
INGEST_OFFSET = _env_int("INGEST_OFFSET", 0)

BUCKET_NAME = "kb-screenshots"


def get_supabase() -> Client:
    url = _env("SUPABASE_URL")
    key = _env("SUPABASE_SERVICE_KEY") or _env("SUPABASE_ANON_KEY")
    if not url or not key:
        raise RuntimeError(
            "Supabase not configured (SUPABASE_URL, SUPABASE_SERVICE_KEY/ANON missing)"
        )
    return create_client(url, key)


def ensure_bucket_public(supabase: Client, bucket: str) -> None:
    try:
        supabase.storage.get_bucket(bucket)
    except Exception:
        try:
            supabase.storage.create_bucket(bucket, options={"public": True})
        except Exception as e:
            logger.warning(f"create_bucket failed or exists: {e}")
    try:
        supabase.storage.update_bucket(bucket, options={"public": True})
    except Exception:
        pass


def upload_png_bytes(supabase: Client, data: bytes, key_hint: str) -> Optional[str]:
    try:
        digest = hashlib.sha256(key_hint.encode("utf-8") + data).hexdigest()[:16]
        path = f"mailbird/{digest}.png"
        ensure_bucket_public(supabase, BUCKET_NAME)
        supabase.storage.from_(BUCKET_NAME).upload(
            file=data,
            path=path,
            file_options={"content-type": "image/png", "x-upsert": "true"},
        )
        url = supabase.storage.from_(BUCKET_NAME).get_public_url(path)
        if isinstance(url, dict):
            return url.get("publicUrl") or url.get("public_url")
        return str(url)
    except Exception as e:
        logger.warning(f"screenshot upload failed: {e}")
        return None


def extract_links_from_html(html: str) -> List[str]:
    soup = BeautifulSoup(html or "", "lxml")
    links: List[str] = []
    for a in soup.find_all("a", href=True):
        href_value = a.get("href")
        if not href_value:
            continue
        href = str(href_value).strip()
        if href.startswith("//"):
            href = "https:" + href
        if href.startswith("/"):
            href = "https://support.getmailbird.com" + href
        links.append(href)
    return links


def is_allowed_url(u: str) -> bool:
    if HOST_ALLOW not in u:
        return False
    if any(s in u for s in EXCLUDE_SUBSTRINGS):
        return False
    return u.startswith("https://support.getmailbird.com/hc/en-us/")


def is_article_url(u: str) -> bool:
    return ARTICLE_PATH_FRAGMENT in u


def platform_from_text(text: str) -> str:
    t = text.lower()
    has_win = any(w in t for w in ["windows", "win10", "win11", "win7", "win8"])
    has_mac = any(
        m in t for m in ["macos", "mac os", "os x", "mac "]
    )  # space to avoid "machine"
    if has_win and has_mac:
        return "both"
    if has_win:
        return "windows"
    if has_mac:
        return "macos"
    return "unknown"


def build_plain_text(article_json: Dict[str, Any]) -> str:
    parts: List[str] = []
    a = article_json
    if a.get("title"):
        parts.append(str(a["title"]))
    if a.get("summary"):
        parts.append(str(a["summary"]))
    for sec in a.get("sections", []) or []:
        h = sec.get("heading")
        if h:
            parts.append(str(h))
        for p in sec.get("paragraphs", []) or []:
            parts.append(str(p))
        for s in sec.get("steps", []) or []:
            parts.append(str(s))
    for faq in a.get("faqs", []) or []:
        q = faq.get("q")
        a_ = faq.get("a")
        if q:
            parts.append(f"Q: {q}")
        if a_:
            parts.append(f"A: {a_}")
    return "\n\n".join(p for p in parts if p)


def get_embedding_model():
    api_key = _env("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY missing")
    from app.db.embedding_config import MODEL_NAME

    return gen_embeddings.GoogleGenerativeAIEmbeddings(
        model=MODEL_NAME, google_api_key=api_key
    )


def to_canonical_json(
    url: str,
    scraped: Dict[str, Any],
    screenshot_url: Optional[str],
    zendesk_meta: Optional[Dict[str, Any]] = None,
) -> Tuple[Dict[str, Any], str]:
    meta = scraped.get("metadata", {}) or {}
    title = meta.get("title") or ""
    markdown = scraped.get("markdown") or ""
    html = scraped.get("html") or ""
    zendesk_meta = zendesk_meta or {}
    labels = list(zendesk_meta.get("label_names") or [])

    # Outline and sections from markdown
    headings_outline: List[Dict[str, Any]] = []
    sections: List[Dict[str, Any]] = []
    current: Dict[str, Any] | None = None
    for line in (markdown or "").splitlines():
        if line.startswith("#"):
            level = len(line) - len(line.lstrip("#"))
            text = line.lstrip("# ").strip()
            headings_outline.append({"level": int(level), "text": text})
            if level <= 2:
                if current:
                    sections.append(current)
                current = {
                    "heading": text,
                    "type": "general",
                    "paragraphs": [],
                    "steps": [],
                }
        elif re.match(r"^\d+\.", line.strip()):
            if not current:
                current = {
                    "heading": None,
                    "type": "howto",
                    "paragraphs": [],
                    "steps": [],
                }
            current.setdefault("steps", []).append(line.strip())
        elif line.strip():
            if not current:
                current = {
                    "heading": None,
                    "type": "general",
                    "paragraphs": [],
                    "steps": [],
                }
            current.setdefault("paragraphs", []).append(line.strip())
    if current:
        sections.append(current)

    label_text = " ".join(labels)
    text_for_platform = (
        f"{title}\n\n{label_text}\n\n{markdown}"
        if markdown
        else (meta.get("description") or label_text)
    )
    platform = platform_from_text(text_for_platform)

    summary = meta.get("description") or (
        sections[0]["paragraphs"][0]
        if sections and sections[0].get("paragraphs")
        else None
    )
    last_updated = (
        meta.get("date")
        or meta.get("lastModified")
        or zendesk_meta.get("updated_at")
        or None
    )
    article_id = zendesk_meta.get("id")
    if not article_id:
        m = re.search(r"/articles/(\d+)", url)
        if m:
            try:
                article_id = int(m.group(1))
            except Exception:
                article_id = None

    images: List[Dict[str, Any]] = []
    try:
        soup = BeautifulSoup(html or "", "lxml")
        for img in soup.find_all("img"):
            src_value = img.get("src")
            alt = img.get("alt")
            if src_value:
                src = str(src_value)
                if src.startswith("/"):
                    src = f"https://{HOST_ALLOW}{src}"
                images.append({"alt": alt, "src": src})
    except Exception:
        pass

    article_json = {
        "source": "mailbird_support",
        "lang": "en-US",
        "article_id": article_id,
        "title": title,
        "url": url,
        "platform": platform,
        "breadcrumbs": meta.get("breadcrumbs") or [],
        "categories": meta.get("categories") or [],
        "last_updated": last_updated,
        "summary": summary,
        "sections": sections,
        "faqs": [],
        "anchors": [],
        "images": images,
        "screenshot_urls": [screenshot_url] if screenshot_url else [],
        "checksum_sha256": hashlib.sha256(
            (markdown or html or title or url).encode("utf-8")
        ).hexdigest(),
        "kb_json_version": "v1",
        "labels": labels,
        "zendesk": {
            "id": zendesk_meta.get("id"),
            "section_id": zendesk_meta.get("section_id"),
            "author_id": zendesk_meta.get("author_id"),
            "label_names": labels,
            "locale": zendesk_meta.get("locale"),
            "source_locale": zendesk_meta.get("source_locale"),
            "created_at": zendesk_meta.get("created_at"),
            "updated_at": zendesk_meta.get("updated_at"),
            "edited_at": zendesk_meta.get("edited_at"),
            "outdated": zendesk_meta.get("outdated"),
        },
    }

    plain_text = build_plain_text(article_json)
    return article_json, plain_text


def parse_data_uri_png(data_uri: str) -> Optional[bytes]:
    if not data_uri or not data_uri.startswith("data:image"):
        return None
    try:
        header, b64 = data_uri.split(",", 1)
        return base64.b64decode(b64)
    except Exception:
        return None


def download_binary(url: str) -> Optional[bytes]:
    try:
        resp = requests.get(url, timeout=30)
        resp.raise_for_status()
        return resp.content
    except Exception as e:
        logger.warning(f"screenshot download failed: {url} err={e}")
        return None


def extract_screenshot_url(
    doc_dict: Dict[str, Any], supabase: Client, article_url: str
) -> Optional[str]:
    raw_shot = (doc_dict or {}).get("screenshot") or (doc_dict or {}).get(
        "metadata", {}
    ).get("screenshot")
    if not isinstance(raw_shot, str):
        return None

    png: Optional[bytes] = None
    if raw_shot.startswith("data:image"):
        png = parse_data_uri_png(raw_shot)
    elif raw_shot.startswith("http"):
        png = download_binary(raw_shot)

    if png:
        uploaded = upload_png_bytes(supabase, png, key_hint=article_url)
        if uploaded:
            return uploaded

    if isinstance(raw_shot, str) and raw_shot.startswith("http"):
        return raw_shot
    return None


def discover_article_urls_via_bfs(
    fc: Firecrawl, rate_limiter: Optional[Callable[[], None]] = None
) -> List[str]:
    seen: Set[str] = set()
    queue: List[str] = [SEED_URL]
    articles: List[str] = []

    while queue and len(seen) < 200:  # allow more index/section pages for full coverage
        url = queue.pop(0)
        if url in seen:
            continue
        seen.add(url)
        try:
            if rate_limiter:
                rate_limiter()
            data = fc.scrape(url=url, formats=["html"], only_main_content=True)
        except Exception as e:
            logger.warning(f"index scrape failed: {url} err={e}")
            continue
        doc = data
        try:
            doc_dict = doc.model_dump()  # type: ignore[attr-defined]
        except Exception:
            doc_dict = doc if isinstance(doc, dict) else {}
        html = (doc_dict or {}).get("html") or ""
        for href in extract_links_from_html(html):
            if not is_allowed_url(href):
                continue
            if is_article_url(href):
                articles.append(href.split("#")[0])
            else:
                if any(href.startswith(p) for p in INCLUDE_PREFIXES):
                    queue.append(href)

        if not rate_limiter:
            # fallback politeness when no shared limiter is provided
            time.sleep(0.5)

    # dedupe and cap
    uniq = []
    added: Set[str] = set()
    for u in articles:
        if u not in added:
            uniq.append(u)
            added.add(u)
        if len(uniq) >= PAGE_CAP:
            break
    return uniq


def make_rate_limiter(min_interval_sec: float) -> Callable[[], None]:
    if min_interval_sec <= 0:

        def no_op() -> None:
            return

        return no_op

    lock = threading.Lock()
    state = {"last_call": 0.0, "interval": float(min_interval_sec)}

    def wait() -> None:
        with lock:
            now = time.time()
            wait_for = state["interval"] - (now - state["last_call"])
            if wait_for > 0:
                time.sleep(wait_for)
            state["last_call"] = time.time()

    return wait


def ingest():
    firecrawl_key = _env("FIRECRAWL_API_KEY")
    if not firecrawl_key:
        raise RuntimeError("FIRECRAWL_API_KEY missing")
    supabase = get_supabase()
    fc = Firecrawl(api_key=firecrawl_key)
    emb_model = get_embedding_model()

    # Pre-wipe scoped rows (optional)
    if PREWIPE:
        try:
            or_filters = "url.like.https://support.getmailbird.com/hc/en-us/%,metadata->>source.eq.mailbird_support"
            supabase.table("mailbird_knowledge").delete().or_(or_filters).execute()
            logger.info("Pre-wipe completed for Mailbird Support rows")
        except Exception as e:
            logger.warning(f"Pre-wipe failed or no rows: {e}")
    else:
        logger.info("Skipping pre-wipe as PREWIPE is false")

    firecrawl_wait = make_rate_limiter(REQUEST_MIN_INTERVAL_SEC)
    embed_wait = make_rate_limiter(EMBED_MIN_INTERVAL_SEC)

    zendesk_map = fetch_zendesk_article_map()
    zendesk_api_count = len(zendesk_map)
    bfs_urls = discover_article_urls_via_bfs(fc, firecrawl_wait)
    bfs_added = 0
    for url in bfs_urls:
        key = normalize_url(url)
        if key not in zendesk_map:
            zendesk_map[key] = {
                "id": None,
                "html_url": url.rstrip("/"),
                "title": "",
                "section_id": None,
                "author_id": None,
                "label_names": [],
                "locale": ZENDESK_LOCALE,
                "source_locale": ZENDESK_LOCALE,
                "created_at": None,
                "updated_at": None,
                "edited_at": None,
                "outdated": None,
                "body": "",
            }
            bfs_added += 1

    if bfs_added:
        logger.info(f"BFS discovery contributed {bfs_added} additional article URLs")

    urls = sorted(
        {
            meta.get("html_url", "").rstrip("/")
            for meta in zendesk_map.values()
            if meta.get("html_url")
        }
    )

    if not urls:
        urls = discover_article_urls_via_bfs(fc, firecrawl_wait)
        logger.warning(
            "Zendesk API yielded no URLs; falling back to BFS-only discovery"
        )

    if PAGE_CAP and len(urls) > PAGE_CAP:
        logger.warning(f"URL count {len(urls)} exceeds PAGE_CAP {PAGE_CAP}; truncating")
        urls = urls[:PAGE_CAP]

    # Apply ingest offset/limit for batching
    total_before_slice = len(urls)
    if INGEST_OFFSET or INGEST_LIMIT:
        start = max(0, INGEST_OFFSET)
        end = start + INGEST_LIMIT if INGEST_LIMIT > 0 else None
        urls = urls[start:end]
        logger.info(
            f"Applying slice offset={INGEST_OFFSET} limit={INGEST_LIMIT} -> {len(urls)} of {total_before_slice} URLs"
        )

    logger.info(
        f"Preparing to ingest {len(urls)} article URLs (Zendesk={zendesk_api_count}, "
        f"BFS_added={bfs_added}, Combined={len(zendesk_map)})"
    )

    results: List[Tuple[str, bool, Optional[str]]] = []

    rate_limit_tokens = ("rate limit", "429", "quota", "resource_exhausted")
    max_attempts = 4

    def worker(u: str) -> Tuple[str, bool, Optional[str]]:
        last_error: Optional[str] = None
        for attempt in range(1, max_attempts + 1):
            try:
                firecrawl_wait()
                data = fc.scrape(
                    url=u,
                    formats=["markdown", "html", "screenshot"],
                    only_main_content=True,
                )
                try:
                    doc_dict = data.model_dump()  # type: ignore[attr-defined]
                except Exception:
                    doc_dict = data if isinstance(data, dict) else {}

                screenshot_url = extract_screenshot_url(doc_dict or {}, supabase, u)

                zendesk_meta = zendesk_map.get(normalize_url(u), {})

                article_json, plain_text = to_canonical_json(
                    u,
                    doc_dict or {},
                    screenshot_url,
                    zendesk_meta,
                )

                # Truncate for embedding and compute 3072‑dim vector
                text_for_embedding = plain_text[:15000]
                embed_wait()
                embedding = emb_model.embed_query(text_for_embedding)
                try:
                    from app.db.embedding_config import assert_dim

                    assert_dim(embedding, "mailbird_kb_ingest.embedding")
                except Exception as e:
                    logger.error(str(e))
                    raise

                row = {
                    "url": u,
                    "content": plain_text,  # plain text only for search; no HTML/Markdown persisted
                    "markdown": None,
                    "scraped_at": datetime.now(timezone.utc).isoformat(),
                    "embedding": embedding,
                    "metadata": {"source": "mailbird_support", "article": article_json},
                }

                supabase.table("mailbird_knowledge").upsert(
                    row, on_conflict="url"
                ).execute()
                return (u, True, None)
            except Exception as e:
                msg = str(e)
                last_error = msg
                lower_msg = msg.lower()
                if any(token in lower_msg for token in rate_limit_tokens):
                    wait_seconds = min(120, 15 * attempt)
                    logger.warning(
                        f"Rate limit on {u} (attempt {attempt}/{max_attempts}); sleeping {wait_seconds}s"
                    )
                    time.sleep(wait_seconds)
                    continue
                return (u, False, msg)
        return (u, False, f"rate-limited after {max_attempts} attempts: {last_error}")

    # Thread pool concurrency with shared RPM gates
    with ThreadPoolExecutor(max_workers=CONCURRENCY) as pool:
        futures = [pool.submit(worker, u) for u in urls]
        for f in as_completed(futures):
            u, ok, err = f.result()
            if ok:
                logger.info(f"ingested: {u}")
            else:
                logger.error(f"failed: {u} err={err}")
            results.append((u, ok, err))

    # Write manifest
    manifest = {
        "source": "mailbird_support",
        "discovered": len(urls),
        "zendesk_discovered": zendesk_api_count,
        "combined_unique": len(zendesk_map),
        "bfs_discovered": len(bfs_urls),
        "prewipe": PREWIPE,
        "ingest_offset": INGEST_OFFSET,
        "ingest_limit": INGEST_LIMIT,
        "ingested_ok": sum(1 for _, ok, _ in results if ok),
        "ingested_failed": [
            {"url": u, "error": err} for (u, ok, err) in results if not ok
        ],
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    try:
        logs_dir = os.path.join(PROJECT_ROOT, "system_logs")
        os.makedirs(logs_dir, exist_ok=True)
        with open(
            os.path.join(logs_dir, "mailbird_kb_manifest.json"), "w", encoding="utf-8"
        ) as f:
            json.dump(manifest, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.warning(f"failed to write manifest: {e}")


if __name__ == "__main__":
    ingest()
