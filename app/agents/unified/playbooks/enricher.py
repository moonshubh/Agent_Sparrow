"""Playbook Enricher for learning from resolved conversations.

This module extracts playbook entries from resolved support conversations by
using an LLM to analyze the conversation and extract structured resolution data.

Uses the Model Registry for model selection, ensuring consistency with the
rest of the system and enabling single-line model updates.

All extracted entries are created with status='pending_review' to prevent
hallucinated solutions from being surfaced without human verification.

Usage:
    from app.agents.unified.playbooks import PlaybookEnricher

    enricher = PlaybookEnricher()

    # Extract from a resolved conversation
    entry_id = await enricher.extract_from_conversation(
        conversation_id="session-123",
        messages=conversation_messages,
        category="account_setup",
    )

    # Entry is now in pending_review status, awaiting approval
"""

from __future__ import annotations

import asyncio
import json
from typing import TYPE_CHECKING, Any, Dict, List, Optional

from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage
from loguru import logger

if TYPE_CHECKING:
    from app.db.supabase.client import SupabaseClient

# Table name for playbook learned entries
LEARNED_ENTRIES_TABLE = "playbook_learned_entries"

# Sentinel for import failure detection
_IMPORT_FAILED = object()

# Extraction prompt template
EXTRACTION_PROMPT = """You are a support resolution analyst. Analyze the following conversation
between a support agent and a customer to extract a playbook entry that can help resolve
similar issues in the future.

The conversation has been marked as RESOLVED. Extract the key information about:
1. What problem the customer had
2. What steps were taken to diagnose and resolve it
3. What the final solution was
4. Why it worked
5. What questions could help diagnose similar issues

Respond with a JSON object matching this schema:
{{
    "problem_summary": "1-2 sentence summary of the customer's problem",
    "resolution_steps": [
        {{"step": 1, "action": "What was done first", "rationale": "Why this was done"}},
        {{"step": 2, "action": "What was done next", "rationale": "Why this was done"}}
    ],
    "diagnostic_questions": ["Question 1 to ask?", "Question 2 to ask?"],
    "final_solution": "The specific solution that resolved the issue",
    "why_it_worked": "Explanation of why this solution worked",
    "key_learnings": "Key takeaways for handling similar issues"
}}

IMPORTANT:
- Be specific and actionable in the resolution steps
- The problem_summary should be what the customer was experiencing, not their words
- diagnostic_questions should help identify if a new ticket has the same issue
- Focus on the successful resolution path, not dead ends
- If the conversation includes TOOL logs/results, treat them as background context only.
  Do NOT copy tool output verbatim and do NOT include internal identifiers (macro IDs, KB IDs,
  tool names, tool_call_id values, internal file paths) in the extracted entry.

Category: {category}

Conversation:
{conversation}
"""


class PlaybookEnricher:
    """Learns new playbook entries from resolved conversations.

    Uses an LLM to analyze resolved support conversations and extract
    structured playbook entries. All entries are created with
    status='pending_review' to require human verification.

    Example:
        enricher = PlaybookEnricher()
        entry_id = await enricher.extract_from_conversation(
            conversation_id="session-123",
            messages=messages,
            category="account_setup",
        )
    """

    def __init__(
        self,
        supabase_client: Optional["SupabaseClient"] = None,
        min_message_count: int = 2,
        min_word_count: int = 100,
    ) -> None:
        """Initialize the playbook enricher.

        Args:
            supabase_client: Optional Supabase client. If not provided,
                             will be lazy-loaded from app.db.supabase.
            min_message_count: Minimum messages required for extraction.
            min_word_count: Minimum word count required for extraction.
        """
        self._client = supabase_client
        self._extraction_model = None
        self.min_message_count = min_message_count
        self.min_word_count = min_word_count

    @property
    def client(self) -> Optional["SupabaseClient"]:
        """Lazy-load the Supabase client.

        Returns None if import failed or client unavailable.
        """
        if self._client is _IMPORT_FAILED:
            return None

        if self._client is None:
            try:
                from app.db.supabase.client import get_supabase_client

                self._client = get_supabase_client()
            except ImportError:
                logger.warning("Supabase client not available for PlaybookEnricher")
                self._client = _IMPORT_FAILED  # type: ignore
                return None
            except Exception as exc:
                logger.warning(
                    "Supabase client initialization failed",
                    error=str(exc),
                )
                self._client = _IMPORT_FAILED  # type: ignore
                return None

        return self._client

    def _get_extraction_model(self):
        """Lazy-load the extraction model using the registry.

        Uses the feedme model from the registry (cost-effective, suitable
        for structured extraction tasks).

        Returns:
            Configured chat model, or None if unavailable.
        """
        if self._extraction_model is _IMPORT_FAILED:
            return None

        if self._extraction_model is None:
            try:
                from app.agents.unified.provider_factory import build_chat_model
                from app.core.config import get_registry

                registry = get_registry()

                # Use FeedMe model (cost-effective for extraction)
                # Role "feedme" sets temperature to 0.3
                self._extraction_model = build_chat_model(
                    provider="google",
                    model=registry.feedme.id,
                    role="feedme",
                )

                logger.debug(
                    "extraction_model_initialized",
                    model=registry.feedme.id,
                    role="feedme",
                )

            except ImportError as exc:
                logger.warning(
                    "Extraction model not available",
                    error=str(exc),
                )
                self._extraction_model = _IMPORT_FAILED  # type: ignore
                return None
            except Exception as exc:
                logger.warning(
                    "Extraction model initialization failed",
                    error=str(exc),
                )
                self._extraction_model = _IMPORT_FAILED  # type: ignore
                return None

        return self._extraction_model

    def _format_conversation(
        self,
        messages: List[BaseMessage] | List[Dict[str, Any]],
    ) -> tuple[str, int, int]:
        """Format conversation messages into a string for the prompt.

        Args:
            messages: List of messages (LangChain or dict format).

        Returns:
            Tuple of (formatted_string, message_count, word_count).
        """
        lines = []
        word_count = 0

        for msg in messages:
            # Handle both LangChain messages and dicts
            if isinstance(msg, BaseMessage):
                role = msg.type
                content = msg.content
            else:
                role = msg.get("role", msg.get("type", "unknown"))
                content = msg.get("content", "")

            # Skip empty messages
            if not content or not isinstance(content, str):
                continue

            # Format role label
            if role in ("human", "user"):
                label = "CUSTOMER"
            elif role in ("ai", "assistant"):
                label = "AGENT"
            elif role == "system":
                continue  # Skip system messages
            else:
                label = role.upper()

            lines.append(f"[{label}]: {content}")
            word_count += len(content.split())

        return "\n\n".join(lines), len(lines), word_count

    async def extract_from_conversation(
        self,
        conversation_id: str,
        messages: List[BaseMessage] | List[Dict[str, Any]],
        category: str,
    ) -> Optional[str]:
        """Extract a playbook entry from a resolved conversation.

        Analyzes the conversation using an LLM and stores the extracted
        entry with status='pending_review'.

        Args:
            conversation_id: Unique identifier for the conversation.
            messages: List of conversation messages.
            category: Issue category for the entry.

        Returns:
            The entry ID if successful, None otherwise.
        """
        # Format and validate conversation
        formatted, message_count, word_count = self._format_conversation(messages)

        if message_count < self.min_message_count:
            logger.debug(
                "conversation_too_short",
                conversation_id=conversation_id,
                message_count=message_count,
                min_required=self.min_message_count,
            )
            return None

        if word_count < self.min_word_count:
            logger.debug(
                "conversation_too_brief",
                conversation_id=conversation_id,
                word_count=word_count,
                min_required=self.min_word_count,
            )
            return None

        # Get extraction model
        model = self._get_extraction_model()
        if model is None:
            logger.warning("extract_from_conversation: model unavailable")
            return None

        # Build extraction prompt
        prompt = EXTRACTION_PROMPT.format(
            category=category,
            conversation=formatted,
        )

        try:
            # Run extraction
            response = await model.ainvoke(
                [
                    SystemMessage(
                        content="You are a support resolution analyst. "
                        "Extract structured playbook entries from conversations."
                    ),
                    HumanMessage(content=prompt),
                ]
            )

            # Parse JSON response
            content = response.content
            if isinstance(content, str):
                # Try to extract JSON from the response
                if "```json" in content:
                    content = content.split("```json")[1].split("```")[0]
                elif "```" in content:
                    content = content.split("```")[1].split("```")[0]

                extracted = json.loads(content.strip())
            else:
                logger.warning(
                    "unexpected_response_format",
                    conversation_id=conversation_id,
                    content_type=type(content).__name__,
                )
                return None

            # Validate required fields
            required_fields = ["problem_summary", "resolution_steps", "final_solution"]
            for field in required_fields:
                if not extracted.get(field):
                    logger.warning(
                        "missing_required_field",
                        conversation_id=conversation_id,
                        field=field,
                    )
                    return None

            # Store the entry
            return await self._store_entry(
                conversation_id=conversation_id,
                category=category,
                extracted=extracted,
                word_count=word_count,
                message_count=message_count,
            )

        except json.JSONDecodeError as exc:
            logger.warning(
                "json_parse_error",
                conversation_id=conversation_id,
                error=str(exc),
            )
            return None
        except Exception as exc:
            logger.warning(
                "extraction_error",
                conversation_id=conversation_id,
                error=str(exc),
            )
            return None

    async def _store_entry(
        self,
        conversation_id: str,
        category: str,
        extracted: Dict[str, Any],
        word_count: int,
        message_count: int,
    ) -> Optional[str]:
        """Store an extracted playbook entry.

        Args:
            conversation_id: Original conversation ID.
            category: Issue category.
            extracted: Extracted data from LLM.
            word_count: Source conversation word count.
            message_count: Source conversation message count.

        Returns:
            Entry ID if successful, None otherwise.
        """
        client = self.client
        if not client:
            logger.warning("_store_entry: no client")
            return None

        data = {
            "conversation_id": conversation_id,
            "category": category,
            "problem_summary": extracted["problem_summary"],
            "resolution_steps": extracted["resolution_steps"],
            "diagnostic_questions": extracted.get("diagnostic_questions"),
            "final_solution": extracted["final_solution"],
            "why_it_worked": extracted.get("why_it_worked"),
            "key_learnings": extracted.get("key_learnings"),
            "source_word_count": word_count,
            "source_message_count": message_count,
            "status": "pending_review",  # Always pending - requires human approval
        }

        try:
            table_client = getattr(client, "client", client)
            response = await asyncio.to_thread(
                lambda: table_client.table(LEARNED_ENTRIES_TABLE)
                .upsert(data, on_conflict="conversation_id")  # Update if exists
                .execute()
            )

            if isinstance(response.data, list) and response.data:
                row = response.data[0]
                entry_id = row.get("id") if isinstance(row, dict) else None
                entry_id_str = str(entry_id) if entry_id is not None else None
                logger.info(
                    "playbook_entry_created",
                    entry_id=entry_id_str,
                    conversation_id=conversation_id,
                    category=category,
                    status="pending_review",
                    word_count=word_count,
                    message_count=message_count,
                )

                # Best-effort: also write a reviewable Memory UI entry (separate from playbook compilation).
                try:
                    from app.core.settings import settings

                    if getattr(settings, "enable_memory_ui_capture", False):
                        from app.memory.memory_ui_service import get_memory_ui_service

                        service = get_memory_ui_service()
                        agent_id = (
                            getattr(settings, "memory_ui_agent_id", "sparrow")
                            or "sparrow"
                        )
                        tenant_id = (
                            getattr(settings, "memory_ui_tenant_id", "mailbot")
                            or "mailbot"
                        )

                        steps = extracted.get("resolution_steps") or []
                        step_lines: List[str] = []
                        if isinstance(steps, list):
                            for raw in steps[:5]:
                                if not isinstance(raw, dict):
                                    continue
                                action = str(raw.get("action") or "").strip()
                                rationale = str(raw.get("rationale") or "").strip()
                                if not action:
                                    continue
                                step_lines.append(
                                    f"- {action}{f' — {rationale}' if rationale else ''}"
                                )

                        content_lines = [
                            f"Category: {category}",
                            f"Problem: {extracted.get('problem_summary', '')}",
                            f"Solution: {extracted.get('final_solution', '')}",
                        ]
                        why = str(extracted.get("why_it_worked") or "").strip()
                        if why:
                            content_lines.append(f"Why it worked: {why}")
                        learnings = str(extracted.get("key_learnings") or "").strip()
                        if learnings:
                            content_lines.append(f"Key learnings: {learnings}")
                        if step_lines:
                            content_lines.append(
                                "Resolution steps:\n" + "\n".join(step_lines)
                            )

                        async def _capture_memory_ui() -> None:
                            try:
                                from app.security.pii_redactor import (
                                    redact_pii,
                                    redact_pii_from_dict,
                                )

                                content = "\n".join(
                                    line for line in content_lines if line
                                ).strip()
                                content = redact_pii(content)
                                metadata = redact_pii_from_dict(
                                    {
                                        "source": "playbook_learned_entry",
                                        "playbook_entry_id": entry_id,
                                        "conversation_id": conversation_id,
                                        "category": category,
                                        "status": "pending_review",
                                    }
                                )

                                embedding = await service.generate_embedding(content)
                                supabase = service._get_supabase()
                                await supabase._exec(
                                    lambda: supabase.client.table("memories")
                                    .insert(
                                        {
                                            "id": entry_id,
                                            "content": content,
                                            "metadata": metadata,
                                            "source_type": "auto_extracted",
                                            "agent_id": agent_id,
                                            "tenant_id": tenant_id,
                                            "embedding": embedding,
                                        }
                                    )
                                    .execute()
                                )
                            except Exception as capture_exc:
                                logger.debug(
                                    "memory_ui_capture_playbook_insert_failed",
                                    error=str(capture_exc)[:180],
                                )

                        asyncio.create_task(_capture_memory_ui())
                except Exception as exc:
                    logger.debug(
                        "memory_ui_capture_playbook_failed", error=str(exc)[:180]
                    )

                return entry_id_str

        except Exception as exc:
            logger.warning(
                "store_entry_error",
                conversation_id=conversation_id,
                category=category,
                error=str(exc),
            )

        return None

    async def enrich_from_session(
        self,
        session_id: str,
        category: str,
    ) -> Optional[str]:
        """Extract playbook entry from a stored session.

        Loads messages from the database and extracts a playbook entry.

        Args:
            session_id: The session ID to load messages from.
            category: Issue category for the entry.

        Returns:
            Entry ID if successful, None otherwise.
        """
        client = self.client
        if not client:
            return None

        try:
            # Load messages from chat_sessions table
            response = (
                client.client.table("chat_sessions")
                .select("messages")
                .eq("id", session_id)
                .single()
                .execute()
            )

            row = response.data
            if not isinstance(row, dict):
                logger.warning(
                    "session_not_found",
                    session_id=session_id,
                )
                return None

            messages = row.get("messages")
            if not isinstance(messages, list) or not messages:
                logger.warning(
                    "session_has_no_messages",
                    session_id=session_id,
                )
                return None

            return await self.extract_from_conversation(
                conversation_id=session_id,
                messages=messages,
                category=category,
            )

        except Exception as exc:
            logger.warning(
                "enrich_from_session_error",
                session_id=session_id,
                error=str(exc),
            )
            return None

    async def get_extraction_stats(self) -> Dict[str, Any]:
        """Get statistics about playbook extraction.

        Returns:
            Dict with extraction stats per category and status.
        """
        client = self.client
        if not client:
            return {}

        try:
            response = (
                client.client.table(LEARNED_ENTRIES_TABLE)
                .select("category, status")
                .execute()
            )

            # Aggregate stats
            stats: Dict[str, Dict[str, int]] = {}
            total = {"pending_review": 0, "approved": 0, "rejected": 0, "total": 0}

            for row in response.data or []:
                if not isinstance(row, dict):
                    continue
                category = row.get("category")
                if not isinstance(category, str) or not category:
                    continue
                status = row.get("status")
                if not isinstance(status, str) or not status:
                    status = "pending_review"

                if category not in stats:
                    stats[category] = {
                        "pending_review": 0,
                        "approved": 0,
                        "rejected": 0,
                        "total": 0,
                    }

                stats[category][status] = stats[category].get(status, 0) + 1
                stats[category]["total"] += 1
                total[status] = total.get(status, 0) + 1
                total["total"] += 1

            return {
                "by_category": stats,
                "total": total,
            }

        except Exception as exc:
            logger.warning(
                "get_extraction_stats_error",
                error=str(exc),
            )
            return {}
