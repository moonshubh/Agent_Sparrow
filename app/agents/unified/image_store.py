"""Image storage helpers (Supabase Storage + URL emission).

Phase V: remove base64 images end-to-end by storing image bytes in a retrievable
location and returning stable URLs for UI embedding.
"""

from __future__ import annotations

import asyncio
import base64
import os
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from io import BytesIO
from typing import Any
from typing import Optional
from uuid import uuid4

from loguru import logger

from app.db.supabase.client import SupabaseClient, get_supabase_client

DEFAULT_IMAGE_BUCKET = (
    os.getenv("AGENT_IMAGE_BUCKET", "agent-images").strip() or "agent-images"
)
DEFAULT_BUCKET_PUBLIC = os.getenv(
    "AGENT_IMAGE_BUCKET_PUBLIC", "true"
).strip().lower() in {
    "1",
    "true",
    "yes",
    "y",
    "on",
}
DEFAULT_MAX_DIM_PX = int(os.getenv("AGENT_IMAGE_MAX_DIM_PX", "2048"))
DEFAULT_SIGNED_URL_TTL_SEC = int(
    os.getenv("AGENT_IMAGE_SIGNED_URL_TTL_SEC", "604800")
)  # 7d
DEFAULT_MAX_REWRITES = int(os.getenv("AGENT_IMAGE_MAX_REWRITES", "50"))

_BUCKET_READY: set[str] = set()
_BUCKET_READY_LOCK = asyncio.Lock()


@dataclass(frozen=True)
class StoredImage:
    url: str
    bucket: str
    path: str
    mime_type: str
    width: Optional[int] = None
    height: Optional[int] = None


def _guess_extension(mime_type: str) -> str:
    normalized = (mime_type or "").split(";")[0].strip().lower()
    return {
        "image/png": "png",
        "image/jpeg": "jpg",
        "image/jpg": "jpg",
        "image/webp": "webp",
        "image/gif": "gif",
        "image/svg+xml": "svg",
    }.get(normalized, "png")


def _is_raster_image(mime_type: str) -> bool:
    normalized = (mime_type or "").split(";")[0].strip().lower()
    return normalized in {"image/png", "image/jpeg", "image/jpg", "image/webp"}


def _maybe_downscale_image(
    data: bytes,
    *,
    mime_type: str,
    max_dim_px: int,
) -> tuple[bytes, str, int | None, int | None]:
    if not data or max_dim_px <= 0:
        return data, mime_type, None, None

    if not _is_raster_image(mime_type):
        return data, mime_type, None, None

    try:
        from PIL import Image

        img = Image.open(BytesIO(data))
        width, height = img.size
        max_dim = max(width, height)
        if max_dim <= max_dim_px:
            return data, mime_type, width, height

        scale = max_dim_px / float(max_dim)
        new_width = max(1, int(round(width * scale)))
        new_height = max(1, int(round(height * scale)))
        resample_base = getattr(Image, "Resampling", Image)
        fallback_filter = getattr(Image, "BICUBIC", 0)
        resample_filter = getattr(resample_base, "LANCZOS", fallback_filter)
        resized = img.resize((new_width, new_height), resample=resample_filter)

        out = BytesIO()
        normalized = (mime_type or "").split(";")[0].strip().lower() or mime_type
        effective_mime_type = normalized
        if normalized in {"image/jpeg", "image/jpg"}:
            if resized.mode in {"RGBA", "LA"}:
                resized = resized.convert("RGB")
            resized.save(out, format="JPEG", quality=85, optimize=True)
        elif normalized == "image/webp":
            resized.save(out, format="WEBP", quality=85, method=6)
        else:
            resized.save(out, format="PNG", optimize=True)
            effective_mime_type = "image/png"

        return out.getvalue(), effective_mime_type, new_width, new_height
    except Exception as exc:  # pragma: no cover - best effort
        logger.warning("image_downscale_failed", error=str(exc))
        return data, mime_type, None, None


async def _ensure_bucket_ready(
    supabase: SupabaseClient,
    *,
    bucket: str,
    public: bool,
) -> None:
    if not bucket:
        raise ValueError("bucket is required")

    async with _BUCKET_READY_LOCK:
        if bucket in _BUCKET_READY:
            return

        try:
            await supabase._exec(lambda: supabase.client.storage.get_bucket(bucket))
        except Exception:
            try:
                await supabase._exec(
                    lambda: supabase.client.storage.create_bucket(
                        bucket, options={"public": public}
                    )
                )
            except Exception as exc:  # pragma: no cover - best effort
                logger.warning(
                    "create_bucket_failed_or_exists", bucket=bucket, error=str(exc)
                )

        try:
            await supabase._exec(
                lambda: supabase.client.storage.update_bucket(
                    bucket, options={"public": public}
                )
            )
        except Exception:
            # Some projects restrict bucket updates; ignore.
            pass

        _BUCKET_READY.add(bucket)


def _extract_signed_url(result: object) -> Optional[str]:
    if isinstance(result, dict):
        signed = result.get("signedURL") or result.get("signedUrl")
        if isinstance(signed, str) and signed.strip():
            return signed.strip()
    return None


def _extract_public_url(result: object) -> Optional[str]:
    if isinstance(result, dict):
        url = (
            result.get("publicUrl")
            or result.get("publicURL")
            or result.get("public_url")
        )
        if isinstance(url, str) and url.strip():
            return url.strip()
    if isinstance(result, str) and result.strip():
        return result.strip()
    return None


def _decode_base64_payload(payload: str) -> bytes:
    cleaned = (payload or "").strip()
    if not cleaned:
        return b""

    if cleaned.startswith("data:"):
        parts = cleaned.split(",", 1)
        cleaned = parts[1] if len(parts) == 2 else ""

    cleaned = "".join(cleaned.split())
    pad = (-len(cleaned)) % 4
    if pad:
        cleaned = cleaned + ("=" * pad)
    return base64.b64decode(cleaned, validate=False)


_DATA_URI_IMAGE_RE = re.compile(
    r"data:(image/[a-zA-Z0-9.+-]+);base64,([A-Za-z0-9+/=\s]+)",
    flags=re.IGNORECASE,
)


async def rewrite_base64_images_in_text(
    text: str,
    *,
    path_prefix: str,
    max_images: int = DEFAULT_MAX_REWRITES,
) -> tuple[str, int]:
    """Replace data: image URIs with stored URLs (best-effort).

    Returns:
        Tuple of (rewritten_text, replaced_count)
    """
    if not text or "data:image" not in text.lower():
        return text, 0

    if max_images <= 0:
        return _DATA_URI_IMAGE_RE.sub("", text), 0

    rewritten: list[str] = []
    last_end = 0
    replaced = 0

    for match in _DATA_URI_IMAGE_RE.finditer(text):
        if replaced >= max_images:
            break

        mime_type = match.group(1)
        payload = match.group(2)

        rewritten.append(text[last_end : match.start()])
        try:
            stored = await store_image_base64(
                payload,
                mime_type=mime_type,
                path_prefix=path_prefix,
            )
        except Exception as exc:  # pragma: no cover - best effort
            logger.warning("rewrite_base64_image_failed", error=str(exc))
            stored = None

        rewritten.append(stored.url if stored else "")
        last_end = match.end()
        if stored:
            replaced += 1

    if replaced == 0 and last_end == 0:
        return text, 0

    rewritten.append(text[last_end:])

    # If we hit the cap, strip remaining data URIs to avoid base64 leakage.
    remainder = "".join(rewritten)
    if replaced >= max_images and "data:image" in remainder.lower():
        remainder = _DATA_URI_IMAGE_RE.sub("", remainder)

    return remainder, replaced


async def rewrite_base64_images(
    value: Any,
    *,
    path_prefix: str,
    max_images: int = DEFAULT_MAX_REWRITES,
) -> tuple[Any, int]:
    """Recursively replace base64 data URIs with stored URLs."""
    if isinstance(value, str):
        return await rewrite_base64_images_in_text(
            value,
            path_prefix=path_prefix,
            max_images=max_images,
        )

    if isinstance(value, list):
        total = 0
        rewritten_list: list[Any] = []
        for item in value:
            rewritten_item, used = await rewrite_base64_images(
                item, path_prefix=path_prefix, max_images=max_images - total
            )
            total += used
            rewritten_list.append(rewritten_item)
        return rewritten_list, total

    if isinstance(value, dict):
        total = 0
        rewritten_dict: dict[str, Any] = {}
        for key, item in value.items():
            rewritten_item, used = await rewrite_base64_images(
                item, path_prefix=path_prefix, max_images=max_images - total
            )
            total += used
            rewritten_dict[key] = rewritten_item
        return rewritten_dict, total

    return value, 0


async def store_image_bytes(
    data: bytes,
    *,
    mime_type: str = "image/png",
    bucket: str = DEFAULT_IMAGE_BUCKET,
    public: bool = DEFAULT_BUCKET_PUBLIC,
    signed_url_ttl_sec: int = DEFAULT_SIGNED_URL_TTL_SEC,
    max_dim_px: int = DEFAULT_MAX_DIM_PX,
    path_prefix: str = "generated",
) -> StoredImage:
    """Upload image bytes and return a retrievable URL.

    If `public=True`, the URL is a stable public URL. If `public=False`, this
    returns a signed URL (expires based on `signed_url_ttl_sec`).
    """
    supabase = get_supabase_client()
    await _ensure_bucket_ready(supabase, bucket=bucket, public=public)

    processed, effective_mime_type, width, height = _maybe_downscale_image(
        data, mime_type=mime_type, max_dim_px=max_dim_px
    )
    ext = _guess_extension(effective_mime_type)
    date_prefix = datetime.now(timezone.utc).strftime("%Y%m%d")
    object_path = f"{path_prefix}/{date_prefix}/{uuid4().hex}.{ext}"

    await supabase._exec(
        lambda: supabase.client.storage.from_(bucket).upload(
            object_path,
            processed,
            {
                "content-type": effective_mime_type,
                "x-upsert": "true",
            },
        )
    )

    if public:
        public_url = await supabase._exec(
            lambda: supabase.client.storage.from_(bucket).get_public_url(object_path)
        )
        url = _extract_public_url(public_url)
    else:
        signed = await supabase._exec(
            lambda: supabase.client.storage.from_(bucket).create_signed_url(
                object_path, int(signed_url_ttl_sec)
            )
        )
        url = _extract_signed_url(signed)

    if not url:
        raise RuntimeError("Failed to resolve a retrievable image URL")

    return StoredImage(
        url=url,
        bucket=bucket,
        path=object_path,
        mime_type=effective_mime_type,
        width=width,
        height=height,
    )


async def store_image_base64(
    image_base64: str,
    *,
    mime_type: str = "image/png",
    bucket: str = DEFAULT_IMAGE_BUCKET,
    public: bool = DEFAULT_BUCKET_PUBLIC,
    signed_url_ttl_sec: int = DEFAULT_SIGNED_URL_TTL_SEC,
    max_dim_px: int = DEFAULT_MAX_DIM_PX,
    path_prefix: str = "generated",
) -> StoredImage:
    data = _decode_base64_payload(image_base64)
    if not data:
        raise ValueError("Empty base64 image payload")
    return await store_image_bytes(
        data,
        mime_type=mime_type,
        bucket=bucket,
        public=public,
        signed_url_ttl_sec=signed_url_ttl_sec,
        max_dim_px=max_dim_px,
        path_prefix=path_prefix,
    )
