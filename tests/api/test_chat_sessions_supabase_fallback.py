import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.v1.endpoints import chat_session_endpoints
from app.core.security import TokenPayload, get_optional_current_user


@pytest.fixture()
def client() -> TestClient:
    app = FastAPI()
    app.include_router(chat_session_endpoints.router, prefix="/api/v1")

    async def _fake_user() -> TokenPayload:
        return TokenPayload(sub="user-123", exp=9999999999, roles=[])

    app.dependency_overrides[get_optional_current_user] = _fake_user
    return TestClient(app)


def _session_row(*, session_id: int = 123) -> dict:
    return {
        "id": session_id,
        "user_id": "user-123",
        "title": "New Chat",
        "agent_type": "primary",
        "metadata": {},
        "is_active": True,
        "created_at": "2025-01-01T00:00:00Z",
        "updated_at": "2025-01-01T00:00:00Z",
        "last_message_at": "2025-01-01T00:00:00Z",
        "message_count": 0,
    }


def _message_row(*, message_id: int = 1, session_id: int = 123) -> dict:
    return {
        "id": message_id,
        "session_id": session_id,
        "content": "hello",
        "message_type": "user",
        "agent_type": None,
        "metadata": {},
        "created_at": "2025-01-01T00:00:01Z",
    }


def test_create_chat_session_uses_supabase_when_db_unavailable(
    monkeypatch: pytest.MonkeyPatch, client: TestClient
) -> None:
    monkeypatch.setattr(chat_session_endpoints, "get_db_connection", lambda: None)
    monkeypatch.setattr(
        chat_session_endpoints, "get_supabase_chat_storage", lambda: object()
    )

    called = {"count": 0}

    async def _fake_create(_client, *, session_data, user_id: str):
        called["count"] += 1
        assert user_id == "user-123"
        assert session_data.title == "New Chat"
        return _session_row(session_id=456)

    monkeypatch.setattr(
        chat_session_endpoints, "create_chat_session_in_supabase", _fake_create
    )

    res = client.post(
        "/api/v1/chat-sessions",
        json={"title": "New Chat", "agent_type": "primary"},
    )

    assert res.status_code == 200
    body = res.json()
    assert body["id"] == 456
    assert called["count"] == 1


def test_list_chat_sessions_uses_supabase_when_db_unavailable(
    monkeypatch: pytest.MonkeyPatch, client: TestClient
) -> None:
    monkeypatch.setattr(chat_session_endpoints, "get_db_connection", lambda: None)
    monkeypatch.setattr(
        chat_session_endpoints, "get_supabase_chat_storage", lambda: object()
    )

    async def _fake_list(_client, *, user_id: str, request):
        assert user_id == "user-123"
        assert request.page == 1
        return {
            "sessions": [_session_row(session_id=123)],
            "total_count": 1,
            "page": 1,
            "page_size": request.page_size,
            "has_next": False,
            "has_previous": False,
        }

    monkeypatch.setattr(
        chat_session_endpoints, "get_chat_sessions_for_user_in_supabase", _fake_list
    )

    res = client.get("/api/v1/chat-sessions")
    assert res.status_code == 200
    body = res.json()
    assert body["total_count"] == 1
    assert body["sessions"][0]["id"] == 123


def test_create_chat_message_uses_supabase_when_db_unavailable(
    monkeypatch: pytest.MonkeyPatch, client: TestClient
) -> None:
    monkeypatch.setattr(chat_session_endpoints, "get_db_connection", lambda: None)
    monkeypatch.setattr(
        chat_session_endpoints, "get_supabase_chat_storage", lambda: object()
    )

    async def _fake_create(_client, *, message_data, user_id: str):
        assert user_id == "user-123"
        assert message_data.session_id == 123
        assert message_data.message_type.value == "user"
        return _message_row(message_id=99, session_id=123)

    monkeypatch.setattr(
        chat_session_endpoints, "create_chat_message_in_supabase", _fake_create
    )

    res = client.post(
        "/api/v1/chat-sessions/123/messages",
        json={"message_type": "user", "content": "hello"},
    )
    assert res.status_code == 200
    body = res.json()
    assert body["id"] == 99
    assert body["session_id"] == 123


def test_list_chat_messages_uses_supabase_when_db_unavailable(
    monkeypatch: pytest.MonkeyPatch, client: TestClient
) -> None:
    monkeypatch.setattr(chat_session_endpoints, "get_db_connection", lambda: None)
    monkeypatch.setattr(
        chat_session_endpoints, "get_supabase_chat_storage", lambda: object()
    )

    async def _fake_list(_client, *, session_id: int, user_id: str, request):
        assert user_id == "user-123"
        assert session_id == 123
        return {
            "messages": [_message_row(message_id=1, session_id=123)],
            "total_count": 1,
            "page": 1,
            "page_size": 1,
            "has_next": False,
            "has_previous": False,
        }

    monkeypatch.setattr(
        chat_session_endpoints, "get_chat_messages_for_session_in_supabase", _fake_list
    )

    res = client.get("/api/v1/chat-sessions/123/messages")
    assert res.status_code == 200
    body = res.json()
    assert body["total_count"] == 1
    assert body["messages"][0]["id"] == 1
