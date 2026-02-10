from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.memory import service as memory_service_module
from app.memory.service import MemoryService


@pytest.mark.asyncio
async def test_mem0_async_mode_falls_back_to_sync_signature() -> None:
    svc = MemoryService()

    class _FakeClient:
        def search(self, *args, **kwargs):
            if "async_mode" in kwargs:
                raise TypeError("search() got an unexpected keyword argument 'async_mode'")
            return {"results": [{"id": "mem-1", "memory": "hello"}]}

    result = await svc._call_mem0_method(_FakeClient(), "search", "hello")

    assert result["results"][0]["id"] == "mem-1"



def test_mem0_result_unwrap_handles_list_and_results_dict() -> None:
    svc = MemoryService()

    direct = svc._extract_results([{"id": "a"}, {"id": "b"}])
    wrapped = svc._extract_results({"results": [{"id": "c"}]})

    assert [item["id"] for item in direct] == ["a", "b"]
    assert [item["id"] for item in wrapped] == ["c"]



def test_build_client_uses_public_mem0_api_and_clamps_dims_for_index_limits(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    svc = MemoryService()

    captured: dict[str, object] = {}

    class _FakeMem0Memory:
        @staticmethod
        def from_config(config):
            captured["config"] = config
            return {"ok": True}

    monkeypatch.setattr(memory_service_module, "Mem0Memory", _FakeMem0Memory)
    monkeypatch.setattr(
        memory_service_module,
        "get_models_config",
        lambda: SimpleNamespace(
            internal={
                "embedding": SimpleNamespace(
                    embedding_dims=3072,
                    provider="google",
                    model_id="models/gemini-embedding-001",
                )
            },
            coordinators={"google": SimpleNamespace(model_id="gemini-3-flash-preview")},
        ),
    )

    from app.core.settings import settings

    monkeypatch.setattr(settings, "memory_backend", "supabase")
    monkeypatch.setattr(settings, "gemini_api_key", "test-key")
    monkeypatch.setattr(settings, "supabase_db_conn", "postgres://localhost/test")

    client = svc._build_client("mem_primary")

    assert client == {"ok": True}
    cfg = captured["config"]
    assert isinstance(cfg, dict)
    assert cfg["vector_store"]["config"]["embedding_model_dims"] == 2000
    assert cfg["vector_store"]["config"]["collection_name"] == "mem_primary"
    assert cfg["vector_store"]["config"]["index_method"] == "ivfflat"
    assert cfg["embedder"]["provider"] == "gemini"
    assert cfg["embedder"]["config"]["output_dimensionality"] == 2000
