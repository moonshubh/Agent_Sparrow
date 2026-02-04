"""OpenRouter-specific ChatOpenAI wrapper.

OpenRouter's MiniMax M2.1 (and some other reasoning models) recommend preserving
`reasoning_details` across turns, especially around tool-calling.

LangChain's ChatOpenAI currently drops `reasoning_details` fields in both:
- chat completion responses (choices[].message.reasoning_details)
- streaming deltas (choices[].delta.reasoning_details)

This wrapper:
1) Captures `reasoning_details` into AIMessage.additional_kwargs
2) Emits `reasoning_details` on streaming chunks via AIMessageChunk.additional_kwargs
3) Re-injects `reasoning_details` into outbound assistant messages when present
"""

from __future__ import annotations

from typing import Any, Dict, List

from langchain_core.messages import AIMessage
from langchain_core.outputs import ChatGenerationChunk, ChatResult
from langchain_openai import ChatOpenAI


class OpenRouterChatOpenAI(ChatOpenAI):
    """ChatOpenAI variant that preserves OpenRouter `reasoning_details`."""

    def _get_request_payload(
        self,
        input_: Any,
        *,
        stop: List[str] | None = None,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        payload = super()._get_request_payload(input_, stop=stop, **kwargs)
        raw_messages = payload.get("messages")
        if not isinstance(raw_messages, list) or not isinstance(input_, list):
            return payload

        patched: list[dict[str, Any]] = []
        for msg_obj, msg_dict in zip(input_, raw_messages):
            if isinstance(msg_dict, dict) and isinstance(msg_obj, AIMessage):
                reasoning_details = msg_obj.additional_kwargs.get("reasoning_details")
                if reasoning_details is not None:
                    msg_dict = {**msg_dict, "reasoning_details": reasoning_details}
            patched.append(msg_dict)

        # If for some reason lengths diverge, fall back to the original.
        if len(patched) == len(raw_messages):
            payload["messages"] = patched
        return payload

    def _create_chat_result(
        self,
        response: dict | Any,
        generation_info: dict | None = None,
    ) -> ChatResult:
        result = super()._create_chat_result(response, generation_info=generation_info)

        response_dict = (
            response if isinstance(response, dict) else response.model_dump()
        )
        choices = response_dict.get("choices")
        if not isinstance(choices, list):
            return result

        for gen, choice in zip(result.generations, choices):
            if not isinstance(choice, dict):
                continue
            msg_dict = choice.get("message")
            if not isinstance(msg_dict, dict):
                continue

            if isinstance(gen.message, AIMessage):
                reasoning_details = msg_dict.get("reasoning_details")
                if reasoning_details is not None:
                    gen.message.additional_kwargs["reasoning_details"] = (
                        reasoning_details
                    )

        return result

    def _convert_chunk_to_generation_chunk(
        self,
        chunk: dict,
        default_chunk_class: type,
        base_generation_info: dict | None,
    ) -> ChatGenerationChunk | None:
        generation_chunk = super()._convert_chunk_to_generation_chunk(
            chunk, default_chunk_class, base_generation_info
        )
        if generation_chunk is None:
            return None

        # OpenRouter streams reasoning_details under choices[].delta.reasoning_details
        try:
            choices = chunk.get("choices") or chunk.get("chunk", {}).get("choices", [])
            if not choices:
                return generation_chunk
            choice0 = choices[0]
            if not isinstance(choice0, dict):
                return generation_chunk
            delta = choice0.get("delta")
            if not isinstance(delta, dict):
                return generation_chunk
            reasoning_details = delta.get("reasoning_details")
            if reasoning_details is None:
                return generation_chunk

            msg = generation_chunk.message
            if isinstance(msg, AIMessage):
                msg.additional_kwargs["reasoning_details"] = reasoning_details
        except Exception:
            # Never fail streaming due to a provider-specific optional field.
            return generation_chunk

        return generation_chunk
