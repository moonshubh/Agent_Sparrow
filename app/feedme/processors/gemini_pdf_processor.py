from __future__ import annotations

"""
Gemini PDF → Markdown processor (LLM vision, no OCR)

Renders PDF pages to images, sends small batches of pages to
`gemini-2.5-flash-lite-preview-09-2025` and requests strict Markdown output.
Concatenates chunk outputs into a final Markdown transcript.

Budget controls:
- Max pages per PDF (default: 10)
- Pages per call (default: 3)
- Simple per-minute and daily pacing via gemini_tracker

Note: This module is best-effort and aims to stay within free-tier quotas.
"""

import base64
import io
import logging
from typing import List, Dict, Any, Optional, Tuple

from pdf2image import convert_from_bytes
from PIL import Image

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

from app.core.settings import settings
from app.feedme.rate_limiting.gemini_tracker import get_tracker

logger = logging.getLogger(__name__)

# Module-level client for google.genai SDK
_genai_client = None
_genai_client_api_key: Optional[str] = None


def _to_jpeg_bytes(img: Image.Image, width: int = 1024, quality: int = 80) -> bytes:
    # downscale maintaining aspect
    w, h = img.size
    if w > width:
        scale = width / float(w)
        new_h = int(h * scale)
        img = img.resize((width, new_h), Image.LANCZOS)
    buf = io.BytesIO()
    img.convert("RGB").save(buf, format="JPEG", quality=quality, optimize=True)
    return buf.getvalue()


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
        "- Preserve original order and clearly mark speakers (e.g., **Customer:**, **Mailbird Support:**).\n"
        "- Use readable paragraphs, headings, and lists where appropriate.\n"
        "- Remove repeated page headers/footers or frame artifacts.\n"
        "- Include links and code/commands as Markdown.\n"
        "- Do not fabricate content. If a portion is unreadable, note it briefly.\n"
    )


def _final_merge_prompt() -> str:
    return (
        "You are given multiple Markdown segments extracted from the same ticket.\n"
        "Merge them into one coherent Markdown document while:\n"
        "- Preserving chronological order of the conversation.\n"
        "- Removing duplicates and repeated headers/footers.\n"
        "- Keeping formatting and links.\n"
        "Output ONLY the merged Markdown."
    )


def _ensure_model(api_key: str) -> str:
    """Initialize the Gemini client and return the model name."""
    global _genai_client, _genai_client_api_key
    model_name = getattr(settings, "feedme_model_name", None) or "gemini-2.5-flash-lite-preview-09-2025"

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
                contents.append(types.Part.from_bytes(
                    data=base64.b64decode(part["data"]),
                    mime_type=part["mime_type"]
                ))
            else:
                contents.append(part)

        resp = _genai_client.models.generate_content(
            model=model_name,
            contents=contents
        )
        # Extract text from response
        if hasattr(resp, 'text'):
            return resp.text or ""
        elif hasattr(resp, 'candidates') and resp.candidates:
            candidate = resp.candidates[0]
            if hasattr(candidate, 'content') and candidate.content:
                if hasattr(candidate.content, 'parts') and candidate.content.parts:
                    return candidate.content.parts[0].text or ""
        return ""
    else:
        # Old SDK: use model.generate_content directly
        resp = _genai_client.generate_content(parts)
        text = getattr(resp, "text", None)
        if not text and getattr(resp, "candidates", None):
            text = resp.candidates[0].content.parts[0].text if resp.candidates[0].content.parts else ""
        return text or ""


def process_pdf_to_markdown(
    pdf_bytes: bytes,
    *,
    max_pages: Optional[int] = None,
    pages_per_call: Optional[int] = None,
    api_key: Optional[str] = None,
    rpm_limit: Optional[int] = None,
    rpd_limit: Optional[int] = None,
) -> Tuple[str, Dict[str, Any]]:
    """
    Render PDF → images → Gemini calls → Markdown.

    Returns (markdown, info) where info contains pages_processed, total_pages,
    truncated, calls_used, and any warnings.
    """
    max_pages = max_pages or settings.feedme_ai_max_pages
    pages_per_call = pages_per_call or settings.feedme_ai_pages_per_call
    rpm = rpm_limit or settings.gemini_flash_rpm_limit
    rpd = rpd_limit or settings.gemini_flash_rpd_limit

    if not api_key:
        if not settings.gemini_api_key:
            raise ValueError("No Gemini API key available")
        api_key = settings.gemini_api_key

    model_name = _ensure_model(api_key)
    tracker = get_tracker(daily_limit=rpd, rpm_limit=rpm)

    # Render pages
    images = convert_from_bytes(pdf_bytes, dpi=144)
    total_pages = len(images)
    use_pages = min(total_pages, max_pages)
    images = images[:use_pages]
    truncated = total_pages > use_pages

    # Prepare JPEG parts
    jpeg_parts: List[Dict[str, Any]] = []
    for i, img in enumerate(images):
        try:
            jpeg = _to_jpeg_bytes(img)
            jpeg_parts.append(_mk_image_part(jpeg))
        except Exception as e:
            logger.warning(f"Failed to convert page {i+1} to JPEG: {e}")
            continue

    chunks: List[List[Dict[str, Any]]] = []
    for i in range(0, len(jpeg_parts), pages_per_call):
        chunks.append(jpeg_parts[i:i + pages_per_call])

    prompt = _default_prompt()
    md_segments: List[str] = []
    calls_used = 0

    for idx, chunk in enumerate(chunks):
        if not tracker.can_request():
            logger.warning("Gemini daily limit reached; stopping early")
            break
        tracker.throttle()
        try:
            parts = [prompt] + chunk
            text = _generate_content(model_name, parts)
            md_segments.append(text or "")
            calls_used += 1
            tracker.record()
        except Exception as e:
            logger.error(f"Gemini extraction failed on chunk {idx+1}/{len(chunks)}: {e}")
            md_segments.append("\n> [Extraction failed for this chunk]\n")

    # Concatenate segments
    concatenated = "\n\n".join(s.strip() for s in md_segments if s and s.strip())

    # Optional: final micro-merge if more than 1 segment and non-empty
    if len(md_segments) > 1 and concatenated:
        if tracker.can_request():
            tracker.throttle()
            try:
                merge_prompt = _final_merge_prompt()
                final_text = _generate_content(model_name, [merge_prompt, concatenated])
                if final_text:
                    concatenated = final_text
                tracker.record()
            except Exception as e:
                logger.warning(f"Gemini final merge failed, using concatenated: {e}")

    info: Dict[str, Any] = {
        "pages_processed": use_pages,
        "total_pages": total_pages,
        "truncated": truncated,
        "calls_used": calls_used + (1 if len(md_segments) > 1 else 0),
        "warnings": [
            "Extraction truncated to page budget" if truncated else None
        ]
    }
    # strip None warnings
    info["warnings"] = [w for w in info["warnings"] if w]

    return concatenated or "", info
