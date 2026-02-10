# mypy: ignore-errors
"""
Gemini PDF → Markdown processor (LLM vision, no OCR)

Renders PDF pages to images, sends small batches of pages to the FeedMe model
configured in the centralized model registry, and requests strict Markdown output.
Concatenates chunk outputs into a final Markdown transcript.

Budget controls:
- Max pages per PDF (default: 10)
- Pages per call (default: 3)
- Bucket-based rate limiting via models.yaml

Memory optimization:
- Pages are streamed in batches instead of loading all at once
- Explicit cleanup of image buffers after processing

Note: This module is best-effort and aims to stay within free-tier quotas.
"""

from __future__ import annotations

import asyncio
import base64
import gc
import io
import logging
from typing import List, Dict, Any, Optional, Tuple

from pdf2image import convert_from_bytes
from PIL import Image

from app.core.settings import settings
from app.core.config import get_models_config
from app.core.rate_limiting.agent_wrapper import get_rate_limiter
from app.core.rate_limiting.exceptions import RateLimitExceededException

try:
    from google import genai  # type: ignore
    from google.genai import types  # type: ignore

    GENAI_SDK = "google.genai"
except ImportError:  # pragma: no cover
    try:
        import google.generativeai as genai  # type: ignore

        types = None  # Old SDK doesn't have types module
        GENAI_SDK = "google.generativeai"
    except ImportError:
        raise ImportError(
            "Neither google.genai nor google.generativeai is available. "
            "Install one of: pip install google-genai or pip install google-generativeai"
        )

logger = logging.getLogger(__name__)
FALLBACK_FEEDME_MODEL_ID = "gemini-2.5-flash-preview-09-2025"

# Module-level client for google.genai SDK
_genai_client = None
_genai_client_api_key: Optional[str] = None


def _to_jpeg_bytes(img: Image.Image, width: int = 1024, quality: int = 80) -> bytes:
    """Convert PIL Image to JPEG bytes with explicit resource cleanup."""
    resized = None
    rgb_img = None
    buf = io.BytesIO()
    try:
        # Downscale maintaining aspect ratio
        w, h = img.size
        if w > width:
            scale = width / float(w)
            new_h = int(h * scale)
            resized = img.resize((width, new_h), Image.Resampling.LANCZOS)
            rgb_img = resized.convert("RGB")
        else:
            rgb_img = img.convert("RGB")

        rgb_img.save(buf, format="JPEG", quality=quality, optimize=True)
        return buf.getvalue()
    finally:
        # Explicitly close buffer to release memory
        buf.close()
        # Close rgb_img if it's a new object (convert() creates new image)
        if rgb_img is not None and rgb_img is not img:
            rgb_img.close()
        # Close resized image if created
        if resized is not None:
            resized.close()


def _mk_image_part(jpeg_bytes: bytes) -> Dict[str, Any]:
    return {
        "mime_type": "image/jpeg",
        "data": base64.b64encode(jpeg_bytes).decode("utf-8"),
    }


def _default_prompt() -> str:
    return (
        "You are given images of a Zendesk support ticket. "
        "Extract the full customer ↔ Mailbird support conversation in strict Markdown.\n\n"
        "Rules:\n"
        "- Output ONLY Markdown (no HTML).\n"
        "- Do NOT emit escaped/encoded HTML tags (for example &lt;pre&gt; or &amp;lt;code&amp;gt;).\n"
        "- Preserve original order and clearly mark speakers (e.g., **Customer:**, **Mailbird Support:**).\n"
        "- Use readable paragraphs, headings, and lists where appropriate.\n"
        "- Use fenced Markdown code blocks for command output and logs.\n"
        "- Remove repeated page headers/footers or frame artifacts.\n"
        "- Avoid duplicating content already captured in earlier lines.\n"
        "- Include links and code/commands as Markdown.\n"
        "- Do not fabricate content. If a portion is unreadable, note it briefly.\n"
    )


def _final_merge_prompt() -> str:
    return (
        "You are given multiple Markdown segments extracted from the same ticket.\n"
        "Merge them into one coherent Markdown document while:\n"
        "- Preserving chronological order of the conversation.\n"
        "- Removing duplicates and repeated headers/footers.\n"
        "- Preserving log/command blocks as fenced Markdown code blocks.\n"
        "- Avoiding escaped HTML entities/tags in the final output.\n"
        "- Keeping formatting and links.\n"
        "Output ONLY the merged Markdown."
    )


def _ensure_model(api_key: str) -> str:
    """Initialize the Gemini client and return the model name from registry."""
    global _genai_client, _genai_client_api_key
    config = get_models_config()
    model_name = config.internal["feedme"].model_id

    if GENAI_SDK == "google.genai":
        # New SDK (google-genai 1.0+) uses Client pattern
        if _genai_client is None or _genai_client_api_key != api_key:
            _genai_client = genai.Client(api_key=api_key)
            _genai_client_api_key = api_key
    else:
        # Old SDK (google-generativeai) uses configure pattern
        genai.configure(api_key=api_key)
        if _genai_client is None or _genai_client_api_key != api_key:
            _genai_client = genai.GenerativeModel(model_name)
            _genai_client_api_key = api_key

    return model_name


def _resolve_model_candidates(primary_model_name: str) -> list[str]:
    candidates = [primary_model_name]
    if primary_model_name != FALLBACK_FEEDME_MODEL_ID:
        candidates.append(FALLBACK_FEEDME_MODEL_ID)
    return candidates


def _generate_content(model_name: str, parts: List[Any]) -> str:
    """Generate content using the appropriate SDK method."""
    global _genai_client

    if GENAI_SDK == "google.genai":
        # New SDK: use client.models.generate_content
        # Convert parts to the format expected by the new SDK
        contents = []
        for part in parts:
            if isinstance(part, str):
                contents.append(types.Part.from_text(text=part))
            elif isinstance(part, dict) and "mime_type" in part and "data" in part:
                # Image part - create inline data
                contents.append(
                    types.Part.from_bytes(
                        data=base64.b64decode(part["data"]), mime_type=part["mime_type"]
                    )
                )
            else:
                contents.append(part)

        resp = _genai_client.models.generate_content(
            model=model_name, contents=contents
        )
        # Extract text from response
        if hasattr(resp, "text"):
            return resp.text or ""
        elif hasattr(resp, "candidates") and resp.candidates:
            candidate = resp.candidates[0]
            if hasattr(candidate, "content") and candidate.content:
                if hasattr(candidate.content, "parts") and candidate.content.parts:
                    return candidate.content.parts[0].text or ""
        return ""
    else:
        # Old SDK: use model.generate_content directly
        resp = _genai_client.generate_content(parts)
        text = getattr(resp, "text", None)
        if not text and getattr(resp, "candidates", None):
            text = (
                resp.candidates[0].content.parts[0].text
                if resp.candidates[0].content.parts
                else ""
            )
        return text or ""


def process_pdf_to_markdown(
    pdf_bytes: bytes,
    *,
    max_pages: Optional[int] = None,
    pages_per_call: Optional[int] = None,
    api_key: Optional[str] = None,
) -> Tuple[str, Dict[str, Any]]:
    """
    Render PDF → images → Gemini calls → Markdown.

    Returns (markdown, info) where info contains pages_processed, total_pages,
    truncated, calls_used, and any warnings.
    """
    max_pages = max_pages or settings.feedme_ai_max_pages
    pages_per_call = pages_per_call or settings.feedme_ai_pages_per_call
    if not api_key:
        if not settings.gemini_api_key:
            raise ValueError("No Gemini API key available")
        api_key = settings.gemini_api_key

    model_name = _ensure_model(api_key)
    model_candidates = _resolve_model_candidates(model_name)
    logger.info(
        "FeedMe PDF extraction using Gemini models %s (sdk=%s, max_pages=%s, pages_per_call=%s)",
        model_candidates,
        GENAI_SDK,
        max_pages,
        pages_per_call,
    )
    limiter = get_rate_limiter()
    rate_limit_loop = asyncio.new_event_loop()

    # Get page count without loading all images into memory
    # Try pypdf first for efficiency, fallback to pdf2image
    try:
        from pypdf import PdfReader

        reader = PdfReader(io.BytesIO(pdf_bytes))
        total_pages = len(reader.pages)
        del reader  # Release reader
    except Exception:
        # Fallback: load first page to validate PDF and estimate
        try:
            test_images = convert_from_bytes(
                pdf_bytes, dpi=72, first_page=1, last_page=1
            )
            total_pages = 1  # We'll discover more as we go
            for img in test_images:
                img.close()
            del test_images
        except Exception as e:
            logger.error(f"Failed to read PDF: {e}")
            raise ValueError(f"Invalid PDF: {e}")

    use_pages = min(total_pages, max_pages)
    truncated = total_pages > use_pages

    # Stream pages in batches to reduce peak memory usage
    # Instead of loading all pages at once, load only pages_per_call at a time
    jpeg_parts: List[Dict[str, Any]] = []
    for batch_start in range(1, use_pages + 1, pages_per_call):
        batch_end = min(batch_start + pages_per_call - 1, use_pages)

        # Load only the pages needed for this batch
        try:
            batch_images = convert_from_bytes(
                pdf_bytes, dpi=144, first_page=batch_start, last_page=batch_end
            )
        except Exception as e:
            logger.warning(f"Failed to load pages {batch_start}-{batch_end}: {e}")
            continue

        for i, img in enumerate(batch_images):
            try:
                jpeg = _to_jpeg_bytes(img)
                jpeg_parts.append(_mk_image_part(jpeg))
            except Exception as e:
                logger.warning(f"Failed to convert page {batch_start + i} to JPEG: {e}")
            finally:
                # Explicitly close image to release memory immediately
                img.close()

        # Clear batch and trigger garbage collection
        del batch_images
        gc.collect()

    # Group jpeg_parts into chunks for API calls
    chunks: List[List[Dict[str, Any]]] = []
    for i in range(0, len(jpeg_parts), pages_per_call):
        chunks.append(jpeg_parts[i : i + pages_per_call])

    prompt = _default_prompt()
    md_segments: List[str] = []
    calls_used = 0
    model_usage: dict[str, int] = {candidate: 0 for candidate in model_candidates}
    limiter_fail_open = False

    def run_with_limit_or_fail_open(model_candidate: str, model_parts: List[Any]) -> str:
        nonlocal limiter_fail_open
        if limiter_fail_open:
            return _generate_content(model_candidate, model_parts)
        try:
            return rate_limit_loop.run_until_complete(
                limiter.execute_with_protection(
                    "internal.feedme",
                    _generate_content,
                    model_candidate,
                    model_parts,
                )
            )
        except RateLimitExceededException:
            raise
        except Exception as exc:
            err = str(exc).lower()
            fail_open_markers = (
                "event loop is closed",
                "different loop",
                "attached to a different loop",
                "rate limiting service unavailable",
            )
            if any(marker in err for marker in fail_open_markers):
                limiter_fail_open = True
                logger.warning(
                    "FeedMe extraction rate limiter unavailable; failing open for remaining calls: %s",
                    exc,
                )
                return _generate_content(model_candidate, model_parts)
            raise

    for idx, chunk in enumerate(chunks):
        try:
            parts = [prompt] + chunk
            text = ""
            last_error: Exception | None = None
            for model_candidate in model_candidates:
                try:
                    text = run_with_limit_or_fail_open(model_candidate, parts)
                    model_usage[model_candidate] = (
                        model_usage.get(model_candidate, 0) + 1
                    )
                    break
                except RateLimitExceededException:
                    raise
                except Exception as model_error:
                    last_error = model_error
                    logger.warning(
                        "FeedMe extraction model failed (model=%s chunk=%s/%s): %s",
                        model_candidate,
                        idx + 1,
                        len(chunks),
                        model_error,
                    )
            if not text and last_error is not None:
                raise last_error
            md_segments.append(text or "")
            calls_used += 1
        except RateLimitExceededException as exc:
            logger.warning("Gemini feedme rate limit reached: %s", exc)
            break
        except Exception as e:
            logger.error(
                "Gemini extraction failed on chunk %s/%s after fallback attempts: %s",
                idx + 1,
                len(chunks),
                e,
            )
            md_segments.append("\n> [Extraction failed for this chunk]\n")

    # Concatenate segments
    concatenated = "\n\n".join(s.strip() for s in md_segments if s and s.strip())

    # Optional: final micro-merge if more than 1 segment and non-empty
    if len(md_segments) > 1 and concatenated:
        try:
            merge_prompt = _final_merge_prompt()
            final_text = ""
            last_error: Exception | None = None
            for model_candidate in model_candidates:
                try:
                    final_text = run_with_limit_or_fail_open(
                        model_candidate,
                        [merge_prompt, concatenated],
                    )
                    model_usage[model_candidate] = (
                        model_usage.get(model_candidate, 0) + 1
                    )
                    break
                except RateLimitExceededException:
                    raise
                except Exception as model_error:
                    last_error = model_error
                    logger.warning(
                        "FeedMe merge model failed (model=%s): %s",
                        model_candidate,
                        model_error,
                    )
            if not final_text and last_error is not None:
                raise last_error
            if final_text:
                concatenated = final_text
        except RateLimitExceededException as exc:
            logger.warning("Gemini final merge rate limited: %s", exc)
        except Exception as e:
            logger.warning(f"Gemini final merge failed, using concatenated: {e}")

    info: Dict[str, Any] = {
        "pages_processed": use_pages,
        "total_pages": total_pages,
        "truncated": truncated,
        "calls_used": calls_used + (1 if len(md_segments) > 1 else 0),
        "models_attempted": model_candidates,
        "model_usage": model_usage,
        "warnings": ["Extraction truncated to page budget" if truncated else None],
    }
    # strip None warnings
    info["warnings"] = [w for w in info["warnings"] if w]
    rate_limit_loop.close()

    return concatenated or "", info
