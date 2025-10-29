from __future__ import annotations

from typing import Any, Dict, List, Optional

from ag_ui_langgraph.agent import LangGraphAgent  # type: ignore
from ag_ui.core.types import RunAgentInput  # type: ignore

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

    def _prepare_input(self, input_obj: RunAgentInput) -> RunAgentInput:
        properties = self._context_properties or {}
        forwarded = dict(input_obj.forwarded_props or {})

        def _get_first(*keys: str) -> Optional[Any]:
            for key in keys:
                if key in forwarded and forwarded[key] not in (None, ""):
                    return forwarded[key]
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

        attachments = _sanitize_attachments(_get_first("attachments") or [])

        merged_forwarded: Dict[str, Any] = dict(forwarded)
        if session_id:
            merged_forwarded["session_id"] = str(session_id)
        if trace_id:
            merged_forwarded["trace_id"] = str(trace_id)
        if provider:
            merged_forwarded["provider"] = str(provider)
        if model:
            merged_forwarded["model"] = str(model)
        if agent_type:
            merged_forwarded["agent_type"] = str(agent_type)
        if force_websearch is not None:
            merged_forwarded["force_websearch"] = force_websearch
        if websearch_max_results is not None:
            merged_forwarded["websearch_max_results"] = websearch_max_results
        if websearch_profile:
            merged_forwarded["websearch_profile"] = str(websearch_profile)
        if formatting_mode:
            merged_forwarded["formatting"] = str(formatting_mode).lower()
        if attachments:
            merged_forwarded["attachments"] = attachments
        else:
            merged_forwarded.pop("attachments", None)

        state_payload: Dict[str, Any] = dict(input_obj.state or {})
        if session_id and "session_id" not in state_payload:
            state_payload["session_id"] = str(session_id)
        if trace_id and "trace_id" not in state_payload:
            state_payload["trace_id"] = str(trace_id)
        if provider and "provider" not in state_payload:
            state_payload["provider"] = str(provider)
        if model and "model" not in state_payload:
            state_payload["model"] = str(model)
        if agent_type and "agent_type" not in state_payload:
            state_payload["agent_type"] = str(agent_type)
        if force_websearch is not None and "force_websearch" not in state_payload:
            state_payload["force_websearch"] = force_websearch
        if websearch_max_results is not None and "websearch_max_results" not in state_payload:
            state_payload["websearch_max_results"] = websearch_max_results
        if websearch_profile and "websearch_profile" not in state_payload:
            state_payload["websearch_profile"] = str(websearch_profile)
        if formatting_mode and "formatting" not in state_payload:
            state_payload["formatting"] = str(formatting_mode).lower()
        if attachments:
            state_payload["attachments"] = attachments

        thread_id = str(session_id) if session_id else input_obj.thread_id

        return input_obj.copy(
            update={
                "forwarded_props": merged_forwarded,
                "state": state_payload,
                "thread_id": thread_id,
            }
        )

    async def prepare_stream(self, input: RunAgentInput, agent_state, config):
        hydrated = self._prepare_input(input)
        if isinstance(config, dict):
            config.setdefault("configurable", {})
            if hydrated.thread_id:
                config["configurable"]["thread_id"] = hydrated.thread_id
        return await super().prepare_stream(hydrated, agent_state, config)

    def langgraph_default_merge_state(self, state, messages, input: RunAgentInput):
        merged = super().langgraph_default_merge_state(state, messages, input)
        forwarded = input.forwarded_props or {}
        for key in (
            "session_id",
            "trace_id",
            "provider",
            "model",
            "agent_type",
            "force_websearch",
            "websearch_max_results",
            "websearch_profile",
        ):
            if key in forwarded and key not in merged:
                merged[key] = forwarded[key]
        attachments = forwarded.get("attachments")
        if attachments:
            merged["attachments"] = attachments
        return merged
