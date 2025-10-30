from __future__ import annotations

from typing import Any, Dict, List, Optional

from copilotkit.langgraph_agent import LangGraphAgent  # type: ignore

from app.core.settings import get_settings


def _sanitize_attachments(payload: Any) -> List[Dict[str, Any]]:
    """Normalize attachment payloads into a predictable list of dicts."""
    attachments: List[Dict[str, Any]] = []
    if not isinstance(payload, list):
        return attachments
    for item in payload:
        if not isinstance(item, dict):
            continue
        data_url = item.get("data_url")
        media_type = item.get("media_type")
        if not isinstance(data_url, str) or not data_url.startswith("data:"):
            continue
        attachments.append(
            {
                "filename": item.get("filename"),
                "media_type": str(media_type or ""),
                "data_url": data_url,
            }
        )
    return attachments


class SparrowLangGraphAgent(LangGraphAgent):
    """LangGraph agent wrapper that hydrates CopilotKit context into graph state."""

    def __init__(
        self,
        *,
        context_properties: Optional[Dict[str, Any]] = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        self._context_properties = context_properties or {}

    def _merge_context(self, state: Dict[str, Any], config: Dict[str, Any]) -> None:
        """Inject per-request context (provider, session, attachments) into state/config."""
        properties = dict(self._context_properties or {})

        def _get_first(*keys: str) -> Optional[Any]:
            for key in keys:
                if key in properties and properties[key] not in (None, ""):
                    return properties[key]
            return None

        session_id = _get_first("session_id")
        trace_id = _get_first("trace_id")
        provider = _get_first("provider")
        model = _get_first("model")
        agent_type = _get_first("agent_type")
        force_websearch = _get_first("force_websearch")
        websearch_max_results = _get_first("websearch_max_results")
        websearch_profile = _get_first("websearch_profile")
        formatting_mode = _get_first("formatting", "formatting_mode")

        if not provider or not model:
            settings = get_settings()
            provider = provider or getattr(settings, "primary_agent_provider", "google")
            model = model or getattr(settings, "primary_agent_model", "gemini-2.5-flash")

        attachments = _sanitize_attachments(properties.get("attachments") or [])

        configurable = config.setdefault("configurable", {})
        if session_id:
            configurable["session_id"] = str(session_id)
            state.setdefault("session_id", str(session_id))
        if trace_id:
            configurable["trace_id"] = str(trace_id)
            state.setdefault("trace_id", str(trace_id))
        if provider:
            configurable["provider"] = str(provider)
            state.setdefault("provider", str(provider))
        if model:
            configurable["model"] = str(model)
            state.setdefault("model", str(model))
        if agent_type:
            configurable["agent_type"] = str(agent_type)
            state.setdefault("agent_type", str(agent_type))
        if force_websearch is not None:
            configurable["force_websearch"] = force_websearch
            state.setdefault("force_websearch", force_websearch)
        if websearch_max_results is not None:
            configurable["websearch_max_results"] = websearch_max_results
            state.setdefault("websearch_max_results", websearch_max_results)
        if websearch_profile:
            configurable["websearch_profile"] = str(websearch_profile)
            state.setdefault("websearch_profile", str(websearch_profile))
        if formatting_mode:
            configurable["formatting"] = str(formatting_mode).lower()
            state.setdefault("formatting", str(formatting_mode).lower())
        if attachments:
            configurable["attachments"] = attachments
            state.setdefault("attachments", attachments)

    def execute(  # type: ignore[override]
        self,
        *,
        state: Dict[str, Any],
        config: Optional[Dict[str, Any]] = None,
        messages: List[Any],
        thread_id: str,
        actions: Optional[List[Dict[str, Any]]] = None,
        meta_events: Optional[List[Dict[str, Any]]] = None,
        **kwargs: Any,
    ):
        adjusted_state = dict(state or {})
        adjusted_config: Dict[str, Any] = dict(config or {})
        self._merge_context(adjusted_state, adjusted_config)
        return super().execute(
            state=adjusted_state,
            config=adjusted_config,
            messages=messages,
            thread_id=thread_id,
            actions=actions,
            meta_events=meta_events,
            **kwargs,
        )

    def dict_repr(self) -> Dict[str, Any]:  # type: ignore[override]
        base = super().dict_repr()
        base.setdefault("type", "langgraph")
        return base
