from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import pytest

from app.agents.harness.store.workspace_store import (
    SparrowWorkspaceStore,
    _IMPORT_FAILED,
)


@pytest.mark.asyncio
async def test_search_root_empty_namespace_prefix_returns_matches() -> None:
    store = SparrowWorkspaceStore(
        session_id="sess-root-search",
        user_id="user-1",
        supabase_client=_IMPORT_FAILED,  # cache-only
    )
    await store.write_file("/scratch/a.md", "hello world")
    await store.write_file("/playbooks/b.md", "hello playbooks")

    results = await store.asearch((), query="hello", limit=10)
    pairs = {(tuple(item.namespace), item.key) for item in results}
    assert (("scratch",), "a.md") in pairs
    assert (("playbooks",), "b.md") in pairs


@pytest.mark.asyncio
async def test_search_root_respects_offset_pagination() -> None:
    store = SparrowWorkspaceStore(
        session_id="sess-root-offset",
        user_id="user-1",
        supabase_client=_IMPORT_FAILED,  # cache-only
    )
    await store.write_file("/scratch/a.md", "one")
    await store.write_file("/scratch/b.md", "two")

    page1 = await store.asearch((), limit=1, offset=0)
    page2 = await store.asearch((), limit=1, offset=1)

    assert len(page1) == 1
    assert len(page2) == 1
    assert page1[0].key == "a.md"
    assert page2[0].key == "b.md"


@dataclass
class _SessionIndexItem:
    key: str
    value: dict
    updated_at: datetime


@pytest.mark.asyncio
async def test_prune_user_sessions_deletes_oldest() -> None:
    # Provide a non-None client so prune_user_sessions doesn't early-return.
    store = SparrowWorkspaceStore(
        session_id="sess-current",
        user_id="user-1",
        supabase_client=object(),
    )

    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    entries = [
        _SessionIndexItem(
            key="s1.json",
            value={"last_used_at": (now.replace(day=3)).isoformat()},
            updated_at=now.replace(day=3),
        ),
        _SessionIndexItem(
            key="s2.json",
            value={"last_used_at": (now.replace(day=2)).isoformat()},
            updated_at=now.replace(day=2),
        ),
        _SessionIndexItem(
            key="s3.json",
            value={"last_used_at": (now.replace(day=1)).isoformat()},
            updated_at=now.replace(day=1),
        ),
    ]

    deleted_sessions: list[str] = []
    deleted_index_files: list[str] = []

    async def fake_asearch(namespace_prefix, /, **_kwargs):
        assert namespace_prefix == ("user", "sessions")
        return entries

    async def fake_delete_session_workspace(*, session_id: str) -> None:
        deleted_sessions.append(session_id)

    async def fake_delete_file(path: str) -> None:
        deleted_index_files.append(path)

    store.asearch = fake_asearch  # type: ignore[assignment]
    store._delete_session_workspace = fake_delete_session_workspace  # type: ignore[assignment]
    store.delete_file = fake_delete_file  # type: ignore[assignment]

    await store.prune_user_sessions(keep=2)

    assert deleted_sessions == ["s3"]
    assert deleted_index_files == ["/user/sessions/s3.json"]


@pytest.mark.asyncio
async def test_prune_user_sessions_paginates_over_large_indices() -> None:
    store = SparrowWorkspaceStore(
        session_id="sess-current",
        user_id="user-1",
        supabase_client=object(),
    )

    base = datetime(2026, 1, 1, tzinfo=timezone.utc)
    total = 250
    entries = []
    for i in range(total):
        ts = base + timedelta(minutes=i)
        entries.append(
            _SessionIndexItem(
                key=f"s{i:03d}.json",
                value={"last_used_at": ts.isoformat()},
                updated_at=ts,
            )
        )

    deleted_sessions: list[str] = []
    deleted_index_files: list[str] = []

    async def fake_asearch(namespace_prefix, /, *, limit=10, offset=0, **_kwargs):
        assert namespace_prefix == ("user", "sessions")
        return entries[offset : offset + limit]

    async def fake_delete_session_workspace(*, session_id: str) -> None:
        deleted_sessions.append(session_id)

    async def fake_delete_file(path: str) -> None:
        deleted_index_files.append(path)

    store.asearch = fake_asearch  # type: ignore[assignment]
    store._delete_session_workspace = fake_delete_session_workspace  # type: ignore[assignment]
    store.delete_file = fake_delete_file  # type: ignore[assignment]

    keep = 10
    await store.prune_user_sessions(keep=keep)

    expected_keep = {f"s{i:03d}" for i in range(total - 1, total - keep - 1, -1)}
    deleted_set = set(deleted_sessions)
    assert len(deleted_sessions) == total - keep
    assert expected_keep.isdisjoint(deleted_set)
    assert set(deleted_index_files) == {
        f"/user/sessions/{sid}.json" for sid in deleted_set
    }
