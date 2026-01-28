"""Message preparation module for Agent Sparrow.

Extracted from agent_sparrow.py to provide a clean, testable interface
for all pre-agent message transformations.
"""

from __future__ import annotations

import asyncio
import json
import re
import time
from typing import Any, Dict, List, Optional, Tuple, TYPE_CHECKING

from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage
from loguru import logger

from .attachment_processor import AttachmentProcessor, get_attachment_processor
from .multimodal_processor import MultimodalProcessor, get_multimodal_processor, ProcessedAttachments
from app.agents.unified.model_context import get_model_context_window
from app.agents.unified.provider_factory import build_chat_model
from app.core.config import get_models_config, resolve_coordinator_config
from app.core.config.model_registry import get_model_by_id
from app.core.settings import settings
from app.security.pii_redactor import redact_sensitive_from_dict

if TYPE_CHECKING:
    from app.agents.helpers.gemma_helper import GemmaHelper
    from app.agents.orchestration.orchestration.state import GraphState


# Constants
HELPER_TIMEOUT_SECONDS = 8.0
LONG_HISTORY_THRESHOLD = 8  # Number of messages before summarization
TOKEN_LIMIT_BEFORE_COMPACT = 9000  # Estimated tokens before compaction
_BASE64_SAMPLE_RE = re.compile(r"^[A-Za-z0-9+/]+$")


class MessagePreparer:
    """Handles all pre-agent message transformations.

    This class is responsible for preparing messages before they're sent
    to the agent, including:
    - Memory context injection
    - Query rewriting for retrieval optimization
    - History summarization for long conversations
    - Attachment processing and inlining
    - Context compaction when approaching token limits

    Usage:
        preparer = MessagePreparer(
            helper=GemmaHelper(),
            session_cache=session_cache,
        )

        prepared_messages, stats = await preparer.prepare_messages(
            state=graph_state,
            memory_context="Relevant memories...",
        )
    """

    def __init__(
        self,
        helper: Optional["GemmaHelper"] = None,
        session_cache: Optional[Dict[str, Dict[str, Any]]] = None,
        attachment_processor: Optional[AttachmentProcessor] = None,
        multimodal_processor: Optional[MultimodalProcessor] = None,
        cache_ttl_seconds: float = 1800.0,
    ):
        """Initialize the preparer.

        Args:
            helper: GemmaHelper for summarization and rewriting.
            session_cache: Session cache for caching rewrites.
            attachment_processor: Attachment processor instance.
            multimodal_processor: Multimodal processor for images/PDFs.
            cache_ttl_seconds: TTL for cached rewrites/summaries in seconds.
        """
        self.helper = helper
        self.session_cache = session_cache or {}
        self.attachment_processor = attachment_processor or get_attachment_processor()
        self.multimodal_processor = multimodal_processor or get_multimodal_processor()
        self._cache_ttl = max(60.0, cache_ttl_seconds)

    async def prepare_messages(
        self,
        state: "GraphState",
        memory_context: Optional[str] = None,
    ) -> Tuple[List[BaseMessage], Dict[str, Any]]:
        """Prepare messages for agent invocation.

        Args:
            state: Current graph state.
            memory_context: Optional memory context to prepend.

        Returns:
            Tuple of (prepared_messages, stats_dict).
        """
        stats: Dict[str, Any] = {
            "original_message_count": len(state.messages),
            "memory_prepended": False,
            "thread_state_prepended": False,
            "query_rewritten": False,
            "history_summarized": False,
            "attachments_inlined": 0,
            "context_compacted": False,
        }

        messages = list(state.messages)

        # 1. Prepend memory context if provided
        if memory_context:
            memory_msg = SystemMessage(
                content=memory_context,
                name="server_memory_context",
            )
            messages = [memory_msg, *messages]
            stats["memory_prepended"] = True

        # 2. Extract and rewrite user query
        last_user_query = self._extract_last_user_query(messages)
        if last_user_query and self.helper:
            rewritten = await self._rewrite_query(last_user_query, state.scratchpad)
            if rewritten and rewritten != last_user_query:
                messages.append(
                    SystemMessage(content=f"Rewritten query for retrieval: {rewritten}")
                )
                stats["query_rewritten"] = True
                stats["rewritten_query"] = rewritten

        # 3. Summarize long history
        if len(messages) > LONG_HISTORY_THRESHOLD and self.helper:
            messages = await self._summarize_history(messages)
            stats["history_summarized"] = True

        # 4. Process attachments (multimodal for images/PDFs, text inline)
        if state.attachments:
            attachments = list(state.attachments or [])
            safe_attachments: List[Any] = []
            deferred_log_names: List[str] = []
            deferred_log_items: List[Tuple[str, Any]] = []
            deferred_sensitive_names: List[str] = []

            for idx, attachment in enumerate(attachments):
                name = self._get_attachment_attr(attachment, "name")
                mime = self._get_attachment_attr(attachment, "mime_type")
                name_str = str(name or "").strip()
                display_name = name_str or f"attachment_{idx + 1}"

                is_log, _ = self.attachment_processor.is_log_attachment(attachment)
                if is_log:
                    deferred_log_names.append(display_name)
                    deferred_log_items.append((display_name, attachment))
                    continue

                if self._is_sensitive_text_attachment(name_str, mime):
                    deferred_sensitive_names.append(display_name)
                    continue

                safe_attachments.append(attachment)

            stored_log_paths: List[str] = []
            if deferred_log_items:
                try:
                    from app.agents.harness.store import SparrowWorkspaceStore

                    session_id = getattr(state, "session_id", None) or getattr(state, "trace_id", None)
                    forwarded = getattr(state, "forwarded_props", {}) or {}
                    customer_id = None
                    if isinstance(forwarded, dict):
                        customer_id = forwarded.get("customer_id") or forwarded.get("customerId")

                    if session_id:
                        store = SparrowWorkspaceStore(
                            session_id=str(session_id),
                            customer_id=customer_id,
                        )
                        used_paths: set[str] = set()
                        for idx, (display_name, attachment) in enumerate(deferred_log_items):
                            data_url = self._get_attachment_attr(attachment, "data_url")
                            if not data_url:
                                continue
                            decoded = self.attachment_processor.decode_data_url(str(data_url))
                            if not decoded:
                                continue
                            content = self.attachment_processor.extract_log_content(decoded)
                            if not content:
                                continue
                            safe_name = self._sanitize_attachment_name(display_name, idx)
                            path = f"/knowledge/attachments/{safe_name}"
                            if path in used_paths:
                                path = f"/knowledge/attachments/{safe_name}_{idx + 1}"
                            used_paths.add(path)
                            await store.write_file(
                                path,
                                content,
                                metadata={
                                    "source": "user_attachment",
                                    "original_name": display_name,
                                },
                            )
                            stored_log_paths.append(f"- {display_name} -> {path}")
                except Exception as exc:
                    logger.debug("log_attachment_workspace_write_failed", error=str(exc))

            if deferred_log_names:
                messages.append(
                    SystemMessage(
                        content=(
                            "Log files attached (contents withheld from prompt). "
                            "They will be analyzed via the log_diagnoser tool.\n"
                            + "\n".join(f"- {name}" for name in deferred_log_names)
                            + (("\n\nStored in workspace:\n" + "\n".join(stored_log_paths)) if stored_log_paths else "")
                        ),
                        name="log_attachment_notice",
                    )
                )
                stats["log_attachments_deferred"] = len(deferred_log_names)

            if deferred_sensitive_names:
                messages.append(
                    SystemMessage(
                        content=(
                            "Sensitive text attachments detected (contents withheld from prompt):\n"
                            + "\n".join(f"- {name}" for name in deferred_sensitive_names)
                        ),
                        name="sensitive_attachment_notice",
                    )
                )
                stats["sensitive_attachments_deferred"] = len(deferred_sensitive_names)

            # Attachment processing (especially image re-encoding) can be CPU-heavy.
            # Run in a worker thread to avoid blocking the event loop.
            processed = await asyncio.to_thread(
                self.multimodal_processor.process_attachments,
                safe_attachments,
            )

            if processed.has_multimodal:
                supports_vision = self._model_supports_vision(state)
                stats["model_supports_vision"] = supports_vision

                if supports_vision:
                    # Build multimodal HumanMessage with images/PDFs
                    human_message_replaced = False
                    for i in range(len(messages) - 1, -1, -1):
                        if isinstance(messages[i], HumanMessage):
                            user_text = self._coerce_message_text(messages[i])
                            messages[i] = self._build_multimodal_human_message(
                                user_text, processed
                            )
                            stats["multimodal_attachments"] = len(
                                processed.multimodal_blocks
                            )
                            human_message_replaced = True
                            break

                    if not human_message_replaced:
                        fallback_text = (
                            self._coerce_message_text(messages[-1])
                            if messages
                            else "User provided attachments."
                        )
                        messages.append(
                            self._build_multimodal_human_message(
                                fallback_text, processed
                            )
                        )
                        stats["multimodal_attachments"] = len(
                            processed.multimodal_blocks
                        )

                    stats["attachments_inlined"] = (
                        len(processed.multimodal_blocks)
                        + (1 if processed.text_content else 0)
                    )
                else:
                    # Non-vision model selected: run a vision sub-model to extract
                    # a concise textual description that can be fed to the chosen model.
                    user_query_for_vision = last_user_query or "User provided attachments."
                    extracted = await self._vision_fallback_extract(
                        user_query=user_query_for_vision,
                        processed=processed,
                    )
                    inlined_blocks = 0
                    if extracted:
                        messages.append(
                            SystemMessage(
                                content=(
                                    "Attached image/PDF context (extracted with a vision model):\n"
                                    f"{extracted}"
                                ),
                                name="attachment_vision_summary",
                            )
                        )
                        stats["vision_fallback_used"] = True
                        inlined_blocks += 1
                    else:
                        messages.append(
                            SystemMessage(
                                content=(
                                    "User attached images/PDFs, but the selected model does not "
                                    "support vision and no vision fallback was available. "
                                    "Ask the user to switch to a vision-capable model or re-upload "
                                    "as text."
                                ),
                                name="attachment_vision_unavailable",
                            )
                        )
                        stats["vision_fallback_used"] = False
                        inlined_blocks += 1

                    if processed.text_content:
                        messages.append(
                            SystemMessage(
                                content=f"Attached files:\n{processed.text_content}",
                                name="attachment_text_inline",
                            )
                        )
                        inlined_blocks += 1
                    stats["multimodal_attachments"] = len(processed.multimodal_blocks)
                    stats["attachments_inlined"] = inlined_blocks
            elif processed.text_content:
                # Text-only: use existing SystemMessage approach
                messages.append(
                    SystemMessage(content=f"Attached files:\n{processed.text_content}")
                )
                stats["attachments_inlined"] = 1

            if processed.skipped:
                stats["attachments_skipped"] = len(processed.skipped)

        # 5. Compact context if too large (dynamic threshold based on model context window)
        estimated_tokens = self._estimate_tokens(messages)
        dynamic_threshold = self._context_threshold(state)
        stats["compact_threshold_tokens"] = dynamic_threshold

        if estimated_tokens > dynamic_threshold and self.helper:
            messages = await self._compact_context(messages)
            stats["context_compacted"] = True

        # 6. Append thread_state as a recent system message after compaction,
        # ensuring it's included in the final message list for the agent.
        thread_state = getattr(state, "thread_state", None)
        if thread_state is not None:
            try:
                if hasattr(thread_state, "model_dump"):
                    raw_state = thread_state.model_dump()  # type: ignore[union-attr]
                    sanitized_state = redact_sensitive_from_dict(raw_state)
                    if sanitized_state != raw_state:
                        stats["thread_state_redacted"] = True
                    rendered = json.dumps(
                        sanitized_state,
                        ensure_ascii=False,
                        indent=2,
                    )
                else:
                    rendered = str(thread_state)
            except Exception:
                rendered = str(thread_state)

            if len(rendered) > 12000:
                rendered = rendered[:12000] + "\n\n[...thread_state truncated...]"

            messages.append(
                SystemMessage(
                    content=f"[Thread State (compressed truth)]\n{rendered}",
                    name="thread_state",
                )
            )
            stats["thread_state_prepended"] = True

        stats["final_message_count"] = len(messages)
        stats["estimated_tokens"] = self._estimate_tokens(messages)

        return messages, stats

    def _model_supports_vision(self, state: "GraphState") -> bool:
        """Best-effort vision capability check for the currently-selected model."""
        model = (getattr(state, "model", None) or "").strip()
        if not model:
            return False
        spec = get_model_by_id(model)
        if spec is not None:
            return bool(spec.supports_vision)
        model_lower = model.lower()
        # Heuristics for custom/unregistered model IDs.
        if "gemini" in model_lower:
            return True
        if "grok" in model_lower:
            return True
        return False

    async def _vision_fallback_extract(
        self,
        *,
        user_query: str,
        processed: ProcessedAttachments,
    ) -> Optional[str]:
        """Extract text context from multimodal attachments using a vision model."""
        if not processed.multimodal_blocks:
            return None

        config = get_models_config()
        vision_candidates: list[tuple[str, str]] = []
        if settings.gemini_api_key:
            vision_candidates.append(
                ("google", resolve_coordinator_config(config, "google").model_id)
            )
        if settings.xai_api_key:
            vision_candidates.append(
                ("xai", resolve_coordinator_config(config, "xai").model_id)
            )
        if getattr(settings, "openrouter_api_key", None):
            vision_candidates.append(
                ("openrouter", resolve_coordinator_config(config, "openrouter").model_id)
            )

        if not vision_candidates:
            return None

        vision_prompt = (
            "You are a vision assistant. The user question is:\n\n"
            f"{user_query}\n\n"
            "You will be given one or more attachments (images and/or PDFs). "
            "Extract all details that are relevant to answering the question.\n\n"
            "Return:\n"
            "1) A short per-attachment summary (what it shows)\n"
            "2) Any text you can read (OCR), preserving key numbers/labels\n"
            "3) Any error messages, UI labels, or structured data\n"
            "Be concise but include everything needed to answer accurately."
        )

        vision_human = HumanMessage(
            content=[{"type": "text", "text": vision_prompt}, *processed.multimodal_blocks]
        )

        for provider, model in vision_candidates:
            spec = get_model_by_id(model)
            if spec is not None and not spec.supports_vision:
                continue
            try:
                vision_model = build_chat_model(provider=provider, model=model, role="coordinator")
                response = await vision_model.ainvoke(
                    [
                        SystemMessage(
                            content="Extract factual visual context from attachments for downstream reasoning.",
                            name="vision_fallback_system",
                        ),
                        vision_human,
                    ]
                )
                extracted = self._coerce_message_text(response).strip()
                if extracted:
                    return extracted
            except Exception as exc:
                logger.warning(
                    "vision_fallback_extract_failed",
                    provider=provider,
                    model=model,
                    error=str(exc),
                )
                continue

        return None

    async def _rewrite_query(
        self,
        query: str,
        scratchpad: Optional[Dict[str, Any]] = None,
    ) -> Optional[str]:
        """Rewrite user query for improved retrieval.

        Args:
            query: Original user query.
            scratchpad: State scratchpad for storing rewritten query.

        Returns:
            Rewritten query, or None if rewriting failed.
        """
        # Check cache first
        rewrite_key = f"rewrite:{query.lower().strip()}"
        cached = self._get_cache(rewrite_key)
        if cached:
            return cached

        # Rewrite with timeout
        rewritten = await self._with_timeout(
            self.helper.rewrite_query(query),
            "gemma_rewrite_query",
        )

        if rewritten:
            # Cache the result
            self._set_cache(rewrite_key, rewritten)

            # Store in scratchpad
            if scratchpad is not None:
                system_bucket = scratchpad.setdefault("_system", {})
                system_bucket["rewritten_query"] = rewritten

        return rewritten

    async def _summarize_history(
        self,
        messages: List[BaseMessage],
    ) -> List[BaseMessage]:
        """Summarize older history messages.

        Keeps the most recent messages and summarizes the rest.

        Args:
            messages: Full message list.

        Returns:
            Message list with older messages summarized.
        """
        # Keep last 4 messages, summarize the rest
        keep_count = 4
        to_summarize = messages[:-keep_count]
        to_keep = messages[-keep_count:]

        history_text = "\n\n".join(
            self._coerce_message_text(msg) for msg in to_summarize
        )

        if not history_text:
            return messages

        cache_key = f"history_summary:{hash(history_text)}"
        summary = self._get_cache(cache_key)

        if summary is None:
            summary = await self._with_timeout(
                self.helper.summarize(history_text, budget_tokens=800),
                "gemma_history_summarize",
            )
            if summary:
                self._set_cache(cache_key, summary)

        if summary:
            return [
                SystemMessage(content=f"Conversation so far (summarized):\n{summary}"),
                *to_keep,
            ]

        return messages

    async def _compact_context(
        self,
        messages: List[BaseMessage],
    ) -> List[BaseMessage]:
        """Compact context when approaching token limits.

        Args:
            messages: Message list to compact.

        Returns:
            Compacted message list.
        """
        # Keep last 3 messages, summarize everything else
        keep_count = 3
        combined = "\n\n".join(
            f"{getattr(m, 'type', 'message')}: {self._coerce_message_text(m)}"
            for m in messages
        )

        cache_key = f"context_compact:{hash(combined)}"
        summary = self._get_cache(cache_key)

        if summary is None:
            summary = await self._with_timeout(
                self.helper.summarize(combined, budget_tokens=1200),
                "gemma_context_compact",
            )
            if summary:
                self._set_cache(cache_key, summary)

        if summary:
            return [
                SystemMessage(content=f"Conversation summary (compacted):\n{summary}"),
                *messages[-keep_count:],
            ]

        return messages

    async def _with_timeout(
        self,
        coro: Any,
        label: str,
        timeout: float = HELPER_TIMEOUT_SECONDS,
    ) -> Optional[Any]:
        """Apply a timeout to helper calls."""
        try:
            return await asyncio.wait_for(coro, timeout=timeout)
        except asyncio.TimeoutError:
            logger.warning(f"{label}_timeout", timeout=timeout)
        except Exception as exc:
            logger.warning(f"{label}_failed", error=str(exc))
        return None

    def _extract_last_user_query(self, messages: List[BaseMessage]) -> str:
        """Extract the last human message text."""
        for message in reversed(messages or []):
            if isinstance(message, HumanMessage):
                text = self._coerce_message_text(message).strip()
                if text:
                    return text
        return ""

    def _coerce_message_text(self, message: BaseMessage) -> str:
        """Convert message content to plain text."""
        content = getattr(message, "content", "")

        if isinstance(content, str):
            return content

        if isinstance(content, list):
            parts = []
            for chunk in content:
                if isinstance(chunk, dict) and chunk.get("type") == "text":
                    parts.append(str(chunk.get("text") or ""))
                else:
                    parts.append(str(chunk))
            return "".join(parts)

        return str(content) if content is not None else ""

    def _build_multimodal_human_message(
        self,
        user_text: str,
        processed: ProcessedAttachments,
    ) -> HumanMessage:
        """Build a multimodal HumanMessage with text and image/PDF content blocks.

        Args:
            user_text: The original user message text.
            processed: ProcessedAttachments with multimodal_blocks and text_content.

        Returns:
            HumanMessage with list-based content for Gemini vision API.
        """
        content: List[Dict[str, Any]] = []

        # Combine user text with any text attachments
        text_parts = [user_text]
        if processed.text_content:
            text_parts.append(f"\n\n--- Attached Files ---\n{processed.text_content}")

        combined_text = "".join(text_parts)
        content.append({"type": "text", "text": combined_text})

        # Add multimodal blocks (images, PDFs)
        content.extend(processed.multimodal_blocks)

        logger.info(
            "multimodal_message_built",
            text_length=len(combined_text),
            multimodal_blocks=len(processed.multimodal_blocks),
        )

        return HumanMessage(content=content)

    @staticmethod
    def _get_attachment_attr(attachment: Any, attr: str) -> Optional[Any]:
        if isinstance(attachment, dict):
            return attachment.get(attr)
        return getattr(attachment, attr, None)

    @staticmethod
    def _sanitize_attachment_name(name: str, index: int) -> str:
        safe = re.sub(r"[^a-zA-Z0-9._-]+", "_", (name or "").strip())
        safe = safe.strip("._") or f"attachment_{index + 1}.log"
        if not safe.lower().endswith((".log", ".txt")):
            safe = f"{safe}.log"
        return safe

    def _is_sensitive_text_attachment(self, name: str, mime: Optional[str]) -> bool:
        if not name:
            return False
        if not self.attachment_processor.is_text_mime(mime, name):
            return False
        lower = name.strip().lower()
        lock_names = {
            "pnpm-lock.yaml",
            "package-lock.json",
            "yarn.lock",
            "bun.lockb",
            "poetry.lock",
            "pipfile.lock",
            "composer.lock",
            "cargo.lock",
        }
        if lower in lock_names:
            return True
        if lower.endswith(".lock"):
            return True
        if "lock" in lower and lower.endswith((".yaml", ".yml", ".json")):
            return True
        return False

    def _estimate_tokens(self, messages: List[BaseMessage]) -> int:
        """Rough token estimation (~4 chars per token, ~1000 tokens per image)."""
        total_tokens = 0

        for msg in messages:
            content = getattr(msg, "content", "")

            if isinstance(content, str):
                total_tokens += self._estimate_text_tokens(content)
            elif isinstance(content, list):
                for part in content:
                    if isinstance(part, dict):
                        if part.get("type") == "text":
                            total_tokens += self._estimate_text_tokens(
                                str(part.get("text", ""))
                            )
                        elif part.get("type") == "image_url":
                            # Conservative estimate: ~1000 tokens per image/PDF
                            total_tokens += 1000
                    else:
                        total_tokens += self._estimate_text_tokens(str(part))
            else:
                total_tokens += self._estimate_text_tokens(str(content)) if content else 0

        return total_tokens

    def _estimate_text_tokens(self, text: str) -> int:
        """Estimate tokens for text content with base64-aware heuristics."""
        if self._looks_like_base64(text):
            return max(1, len(text))
        return max(1, len(text) // 4)

    @staticmethod
    def _looks_like_base64(text: str) -> bool:
        """Detect base64-like blobs to avoid undercounting tokens."""
        if not text or len(text) < 2000:
            return False

        sample = text.strip().replace("\n", "").replace(" ", "")
        if len(sample) < 2000:
            return False

        sample = sample[:2000].rstrip("=")
        if not sample:
            return False

        return bool(_BASE64_SAMPLE_RE.match(sample))

    def _context_threshold(self, state: "GraphState") -> int:
        """Compute a dynamic compaction threshold based on model context window."""
        context_window = get_model_context_window(
            getattr(state, "model", None) or "",
            getattr(state, "provider", None),
        )
        # Trigger compaction at 50% of window, but never below static floor.
        return max(TOKEN_LIMIT_BEFORE_COMPACT, int(context_window * 0.5))

    def _get_cache(self, key: str) -> Optional[Any]:
        """Fetch from session cache with TTL enforcement."""
        entry = self.session_cache.get(key)
        if not entry:
            return None
        ts = entry.get("ts")
        if ts is None or (time.time() - ts) > self._cache_ttl:
            self.session_cache.pop(key, None)
            return None
        return entry.get("value")

    def _set_cache(self, key: str, value: Any) -> None:
        """Store in session cache with timestamp."""
        self.session_cache[key] = {"value": value, "ts": time.time()}


# Module-level instance for convenience
_default_preparer: Optional[MessagePreparer] = None


def get_message_preparer(
    helper: Optional["GemmaHelper"] = None,
    session_cache: Optional[Dict[str, Dict[str, Any]]] = None,
) -> MessagePreparer:
    """Get a message preparer instance."""
    if helper is None and session_cache is None:
        global _default_preparer
        if _default_preparer is None:
            _default_preparer = MessagePreparer()
        return _default_preparer

    return MessagePreparer(helper=helper, session_cache=session_cache)
