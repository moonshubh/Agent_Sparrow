from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from app.agents.streaming.handler import StreamEventHandler
from app.agents.unified.tools import write_article_tool
from app.agents.unified import tools as unified_tools


@pytest.mark.asyncio
async def test_write_article_rewrites_non_image_markdown_urls(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _fake_validate(url: str) -> tuple[bool, str | None, str, str]:
        return False, "https://instagram.com/p/demo-post", "text/html", "content_type_not_image"

    monkeypatch.setattr(
        unified_tools,
        "_validate_article_image_markdown_url",
        _fake_validate,
    )

    content = (
        "## Headline\n\n"
        '![Incident photo](https://cdn.example.com/not-an-image "https://news.example.com/story")\n'
    )
    result = await write_article_tool.coroutine(
        title="Incident recap",
        content=content,
        images=None,
        runtime=None,
    )

    assert result["success"] is True
    rewritten = str(result["content"])
    assert "> **Image reference**" in rewritten
    assert "Source page: [https://news.example.com/story](https://news.example.com/story)" in rewritten
    assert "content_type_not_image" not in rewritten  # internal reason should stay out of user markdown
    assert "![Incident photo]" not in rewritten


@pytest.mark.asyncio
async def test_write_article_keeps_valid_inline_image_markdown(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _fake_validate(url: str) -> tuple[bool, str | None, str, str]:
        return True, url, "image/jpeg", ""

    monkeypatch.setattr(
        unified_tools,
        "_validate_article_image_markdown_url",
        _fake_validate,
    )

    content = "![Chart](https://images.example.com/chart.jpg)"
    result = await write_article_tool.coroutine(
        title="Metrics",
        content=content,
        images=None,
        runtime=None,
    )

    assert result["success"] is True
    assert result["content"] == content


class _FakeEmitter:
    def __init__(self) -> None:
        self.article_calls: list[dict[str, Any]] = []
        self.image_calls: list[dict[str, Any]] = []

    def emit_article_artifact(self, **kwargs: Any) -> None:
        self.article_calls.append(dict(kwargs))

    def emit_image_artifact(self, **kwargs: Any) -> None:
        self.image_calls.append(dict(kwargs))


@pytest.mark.asyncio
async def test_handle_article_generation_emits_article_and_per_image_artifacts() -> None:
    emitter = _FakeEmitter()
    handler = StreamEventHandler(
        agent=SimpleNamespace(),
        emitter=emitter,  # type: ignore[arg-type]
        config={"configurable": {}},
        state=SimpleNamespace(attachments=[], scratchpad={}),
        messages=[],
    )

    await handler._handle_article_generation(
        {
            "success": True,
            "title": "Release notes",
            "content": "## Highlights",
            "images": [
                {
                    "url": "https://images.example.com/hero.png",
                    "alt": "Hero",
                    "page_url": "https://example.com/release",
                }
            ],
        }
    )

    assert len(emitter.article_calls) == 1
    assert emitter.article_calls[0]["title"] == "Release notes"
    assert len(emitter.image_calls) == 1
    assert emitter.image_calls[0]["title"] == "Release notes - Visual 1"
    assert emitter.image_calls[0]["image_url"] == "https://images.example.com/hero.png"
    assert emitter.image_calls[0]["page_url"] == "https://example.com/release"
