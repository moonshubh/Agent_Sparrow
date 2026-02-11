from __future__ import annotations

import asyncio

import pytest
from fastapi import HTTPException

from app.api.v1.endpoints import metadata_endpoints
from app.api.v1.endpoints.metadata_endpoints import (
    _LinkPreviewFetchError,
    _LinkPreviewMetadata,
    get_link_preview,
)
from app.core.auth import User


@pytest.fixture(autouse=True)
def _clear_link_preview_cache() -> None:
    with metadata_endpoints._LINK_PREVIEW_CACHE_LOCK:
        metadata_endpoints._LINK_PREVIEW_CACHE.clear()


@pytest.mark.asyncio
async def test_link_preview_rejects_private_url() -> None:
    with pytest.raises(HTTPException) as exc_info:
        await get_link_preview(
            url="http://127.0.0.1/internal",
            current_user=User(id="u-1", email="u@example.com"),
        )

    assert exc_info.value.status_code == 400
    assert "blocked for security reasons" in str(exc_info.value.detail)


@pytest.mark.asyncio
async def test_link_preview_returns_screenshot_mode(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _fake_screenshot(url: str) -> str | None:
        return "https://cdn.example.com/screenshot.png"

    async def _fake_metadata(url: str) -> _LinkPreviewMetadata:
        return _LinkPreviewMetadata(
            resolved_url="https://example.com/story",
            title="Example Story",
            description="Story description",
            site_name="example.com",
            image_url="https://cdn.example.com/og.png",
        )

    monkeypatch.setattr(metadata_endpoints, "_is_safe_public_url", lambda _url: (True, ""))
    monkeypatch.setattr(metadata_endpoints, "_attempt_screenshot_preview", _fake_screenshot)
    monkeypatch.setattr(metadata_endpoints, "_fetch_link_metadata", _fake_metadata)

    response = await get_link_preview(
        url="https://example.com/story",
        current_user=User(id="u-1", email="u@example.com"),
    )

    assert response.mode == "screenshot"
    assert response.status == "ok"
    assert response.retryable is False
    assert response.screenshotUrl == "https://cdn.example.com/screenshot.png"
    assert response.imageUrl == "https://cdn.example.com/og.png"


@pytest.mark.asyncio
async def test_link_preview_returns_degraded_fallback_on_metadata_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _fake_screenshot(url: str) -> str | None:
        return None

    async def _raise_metadata(url: str) -> _LinkPreviewMetadata:
        raise _LinkPreviewFetchError(
            "upstream timeout",
            retryable=True,
            resolved_url="https://example.com/redirected",
        )

    monkeypatch.setattr(metadata_endpoints, "_is_safe_public_url", lambda _url: (True, ""))
    monkeypatch.setattr(metadata_endpoints, "_attempt_screenshot_preview", _fake_screenshot)
    monkeypatch.setattr(metadata_endpoints, "_fetch_link_metadata", _raise_metadata)

    response = await get_link_preview(
        url="https://example.com/original",
        current_user=User(id="u-1", email="u@example.com"),
    )

    assert response.mode == "fallback"
    assert response.status == "degraded"
    assert response.retryable is True
    assert response.resolvedUrl == "https://example.com/redirected"


@pytest.mark.asyncio
async def test_link_preview_uses_fast_og_when_screenshot_is_slow(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _slow_screenshot(url: str) -> str | None:
        await asyncio.sleep(0.05)
        return "https://cdn.example.com/slow-screenshot.png"

    async def _fast_metadata(url: str) -> _LinkPreviewMetadata:
        return _LinkPreviewMetadata(
            resolved_url="https://example.com/story",
            title="Example Story",
            description="Story description",
            site_name="example.com",
            image_url="https://cdn.example.com/og.png",
        )

    monkeypatch.setattr(metadata_endpoints, "_is_safe_public_url", lambda _url: (True, ""))
    monkeypatch.setattr(metadata_endpoints, "_attempt_screenshot_preview", _slow_screenshot)
    monkeypatch.setattr(metadata_endpoints, "_fetch_link_metadata", _fast_metadata)
    monkeypatch.setattr(
        metadata_endpoints,
        "_LINK_PREVIEW_SCREENSHOT_SOFT_TIMEOUT_SECONDS",
        0.01,
    )

    response = await get_link_preview(
        url="https://example.com/story",
        current_user=User(id="u-1", email="u@example.com"),
    )

    assert response.mode == "og"
    assert response.status == "ok"
    assert response.retryable is False
    assert response.screenshotUrl is None
    assert response.imageUrl == "https://cdn.example.com/og.png"


@pytest.mark.asyncio
async def test_link_preview_metadata_only_is_not_degraded(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _no_screenshot(url: str) -> str | None:
        return None

    async def _metadata_without_image(url: str) -> _LinkPreviewMetadata:
        return _LinkPreviewMetadata(
            resolved_url="https://example.com/story",
            title="Example Story",
            description="Story description",
            site_name="example.com",
            image_url=None,
        )

    monkeypatch.setattr(metadata_endpoints, "_is_safe_public_url", lambda _url: (True, ""))
    monkeypatch.setattr(metadata_endpoints, "_attempt_screenshot_preview", _no_screenshot)
    monkeypatch.setattr(metadata_endpoints, "_fetch_link_metadata", _metadata_without_image)

    response = await get_link_preview(
        url="https://example.com/story",
        current_user=User(id="u-1", email="u@example.com"),
    )

    assert response.mode == "fallback"
    assert response.status == "ok"
    assert response.retryable is False
