"""
Primary Agent Connector for FeedMe Integration

Provides integration between the Primary Agent and FeedMe knowledge retrieval system.
"""

import logging
import asyncio
import time
from typing import List, Dict, Any, Optional
from datetime import datetime

from app.db.session import get_db
from app.core.settings import settings

logger = logging.getLogger(__name__)


class PrimaryAgentConnector:
    """Connector for integrating FeedMe knowledge with the Primary Agent."""
    
    def __init__(self):
        """Initialize the connector with necessary configurations."""
        self.enabled = settings.feedme_enabled
        self.similarity_threshold = settings.feedme_similarity_threshold
        self.max_results = settings.feedme_max_retrieval_results
        # Default include saved web snapshots
        self.include_web = True
        
    async def search_feedme_examples(
        self,
        query: str,
        limit: Optional[int] = None,
        min_similarity: Optional[float] = None
    ) -> List[Dict[str, Any]]:
        """
        Search FeedMe examples for relevant Q&A pairs.
        
        Args:
            query: The search query
            limit: Maximum number of results to return
            min_similarity: Minimum similarity score threshold
            
        Returns:
            List of relevant FeedMe examples with metadata
        """
        if not self.enabled:
            logger.debug("FeedMe integration is disabled")
            return []
            
        try:
            # For now, return empty list as the actual implementation
            # would require database queries and embeddings
            # Avoid logging raw user queries at info level (PII risk)
            try:
                qlen = len(query or "")
            except Exception:
                qlen = 0
            logger.debug("FeedMe search called (query_len=%d)", qlen)
            return []
            
        except Exception as e:
            logger.error(f"Error searching FeedMe examples: {e}")
            return []
            
    async def get_example_context(
        self,
        example_id: int
    ) -> Optional[Dict[str, Any]]:
        """
        Get full context for a specific FeedMe example.
        
        Args:
            example_id: The ID of the example to retrieve
            
        Returns:
            Full example data with context or None if not found
        """
        if not self.enabled:
            return None
            
        try:
            # Placeholder implementation
            logger.info(f"Getting context for example ID: {example_id}")
            return None
            
        except Exception as e:
            logger.error(f"Error getting example context: {e}")
            return None
            
    def format_feedme_results(
        self,
        examples: List[Dict[str, Any]]
    ) -> str:
        """
        Format FeedMe examples for inclusion in agent responses.
        
        Args:
            examples: List of FeedMe examples
            
        Returns:
            Formatted string representation
        """
        if not examples:
            return ""
            
        formatted_parts = []
        for idx, example in enumerate(examples, 1):
            parts = [
                f"**Example {idx}:**",
                f"Question: {example.get('question_text', 'N/A')}",
                f"Answer: {example.get('answer_text', 'N/A')}",
                f"Confidence: {example.get('confidence_score', 0):.2f}",
                ""
            ]
            formatted_parts.extend(parts)
            
        return "\n".join(formatted_parts)

    async def search_conversations(
        self,
        params: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Search FeedMe stored conversations via feedme_text_chunks embeddings.

        Args:
            params: Search parameters, may include:
              - query: override free-text query
              - error_signatures: list[str]
              - max_results: int
              - folder_id: Optional[int]

        Returns:
            Dict with shape { conversations: [..], total: int }
        """
        if not self.enabled:
            logger.debug("FeedMe integration is disabled")
            return {"conversations": [], "total": 0}

        try:
            from app.db.supabase_client import SupabaseClient
            from app.db.embedding_utils import get_embedding_model

            max_results = int(params.get("max_results", self.max_results or 5))
            folder_id = params.get("folder_id")

            # Build a query string
            query_text = params.get("query")
            if not query_text:
                sigs = params.get("error_signatures") or []
                types = params.get("error_types") or []
                query_text = " ".join([*sigs[:3], *types[:2]]) or "Mailbird error"

            # Embed
            emb_model = get_embedding_model()
            loop = asyncio.get_running_loop()
            qv = await loop.run_in_executor(None, emb_model.embed_query, query_text)

            client = SupabaseClient()
            # Fetch more chunks than conversations to aggregate
            chunk_rows = await client.search_text_chunks(qv, match_count=max(20, max_results * 4), folder_id=folder_id)

            # Group by conversation id and aggregate scores/snippets
            by_conv: Dict[int, Dict[str, Any]] = {}
            for row in chunk_rows or []:
                conv_id = row.get("conversation_id") or row.get("conversationId")
                if conv_id is None:
                    continue
                entry = by_conv.setdefault(int(conv_id), {
                    "id": int(conv_id),
                    "title": None,
                    "summary": "",
                    "resolution": "",
                    "error_patterns": [],
                    "resolution_status": "unknown",
                    "created_at": None,
                    "top_similarity": 0.0,
                    "snippets": []
                })
                sim = float(row.get("similarity") or row.get("similarity_score") or 0.0)
                entry["top_similarity"] = max(entry["top_similarity"], sim)
                content = (row.get("content") or "")[:280]
                if content:
                    entry["snippets"].append(content)

            if not by_conv:
                return {"conversations": [], "total": 0}

            # Fetch conversation titles/metadata
            conv_ids = list(by_conv.keys())
            conv_details = await client.get_conversations_by_ids(conv_ids)
            for cid, c in (conv_details or {}).items():
                if cid in by_conv:
                    by_conv[cid]["title"] = c.get("title") or by_conv[cid]["title"] or "Conversation"
                    by_conv[cid]["created_at"] = c.get("created_at")
                    # Prefer AI-generated note or extracted_text for summary
                    meta = c.get("metadata") or {}
                    ai_note = None
                    try:
                        if isinstance(meta, dict):
                            ai_note = meta.get("ai_note") or meta.get("summary")
                    except Exception:
                        ai_note = None
                    extracted_text = c.get("extracted_text") or ""
                    # Build summary: ai_note else first 400 chars of extracted_text
                    pref_summary = None
                    if ai_note and isinstance(ai_note, str):
                        pref_summary = ai_note.strip()
                    elif isinstance(extracted_text, str) and extracted_text:
                        pref_summary = extracted_text[:400]
                    if pref_summary:
                        by_conv[cid]["snippets"] = [pref_summary]
                    # If conversation has resolution fields present (optional)
                    by_conv[cid]["resolution"] = c.get("resolution") or by_conv[cid].get("resolution", "")
                    by_conv[cid]["resolution_status"] = c.get("resolution_status") or by_conv[cid].get("resolution_status", ("resolved" if by_conv[cid].get("resolution") else "unresolved"))

            # Rank by top similarity
            ranked = sorted(by_conv.values(), key=lambda x: x["top_similarity"], reverse=True)
            # Trim and shape response
            conversations = []
            for conv in ranked[:max_results]:
                conversations.append({
                    "id": conv["id"],
                    "title": conv.get("title") or f"Conversation {conv['id']}",
                    "summary": ("\n".join(conv.get("snippets", [])[:3]))[:600],
                    "resolution": conv.get("resolution") or "",
                    "error_patterns": conv.get("error_patterns", []),
                    "resolution_status": conv.get("resolution_status", "unknown"),
                    "created_at": conv.get("created_at"),
                    "confidence": conv.get("top_similarity", 0.0)
                })

            return {"conversations": conversations, "total": len(ranked)}

        except Exception as e:
            logger.error(f"Error searching conversations: {e}")
            return {"conversations": [], "total": 0}

    async def retrieve_knowledge(
        self,
        query: Dict[str, Any],
        max_results: int = 5,
        track_performance: bool = False,
    ) -> List[Dict[str, Any]]:
        """Unified knowledge retrieval for Enhanced KB search.

        Aggregates results from:
         - Knowledge Base (pgvector)
         - FeedMe stored conversations (feedme_text_chunks with 3072-d embeddings)
         - Tavily saved web research snapshots (web_research_snapshots)
        """
        if not self.enabled:
            logger.debug("FeedMe integration disabled; returning empty results")
            return []

        perf_start = time.perf_counter() if track_performance else None

        try:
            from app.db.supabase_client import SupabaseClient
            from app.db.embedding_utils import get_embedding_model

            text = str(query.get("query_text") or query.get("query") or "").strip()
            if not text:
                return []

            # Build embedding
            emb_model = get_embedding_model()
            loop = asyncio.get_running_loop()
            query_vec = await loop.run_in_executor(None, emb_model.embed_query, text)

            client = SupabaseClient()

            results: List[Dict[str, Any]] = []

            # 1) Knowledge Base articles
            kb_rows = await client.search_kb_articles(
                query_embedding=query_vec,
                limit=max_results,
                similarity_threshold=0.25,
            )
            for r in kb_rows or []:
                sim = float(r.get("similarity") or 0.0)
                results.append(
                    {
                        "source": "knowledge_base",
                        "title": r.get("url") or "Knowledge Base Article",
                        "content": (r.get("markdown") or r.get("content") or ""),
                        "relevance_score": sim,
                        "metadata": {
                            "kb_id": r.get("id"),
                            "url": r.get("url"),
                            "original_metadata": r.get("metadata"),
                        },
                        "quality_indicators": {
                            "high_confidence": sim >= 0.8,
                        },
                    }
                )

            # 2) FeedMe stored conversations via text chunks
            chunk_rows = await client.search_text_chunks(query_vec, match_count=max(max_results * 4, 20))
            # Aggregate by conversation
            by_conv: Dict[int, Dict[str, Any]] = {}
            for row in chunk_rows or []:
                conv_id = row.get("conversation_id") or row.get("conversationId")
                if conv_id is None:
                    continue
                entry = by_conv.setdefault(int(conv_id), {
                    "id": int(conv_id),
                    "title": None,
                    "top_similarity": 0.0,
                    "snippets": []
                })
                sim = float(row.get("similarity") or row.get("similarity_score") or 0.0)
                entry["top_similarity"] = max(entry["top_similarity"], sim)
                content = (row.get("content") or "")[:280]
                if content:
                    entry["snippets"].append(content)

            if by_conv:
                details = await client.get_conversations_by_ids(list(by_conv.keys()))
                for cid, agg in by_conv.items():
                    conv_row = (details or {}).get(cid, {})
                    title = conv_row.get("title") or f"Conversation {cid}"
                    sim = agg.get("top_similarity", 0.0)
                    # Prefer AI note / extracted_text if available
                    meta = conv_row.get("metadata") or {}
                    ai_note = None
                    try:
                        if isinstance(meta, dict):
                            ai_note = meta.get("ai_note") or meta.get("summary")
                    except Exception:
                        ai_note = None
                    extracted_text = conv_row.get("extracted_text") or ""
                    content = (ai_note or extracted_text or ("\n".join(agg.get("snippets", [])[:3])))
                    content = (content or "")[:600]
                    results.append(
                        {
                            "source": "feedme",
                            "title": title,
                            "content": content,
                            "relevance_score": sim,
                            "metadata": {
                                "conversation_id": cid,
                            },
                            "quality_indicators": {
                                "high_confidence": sim >= 0.8,
                            },
                        }
                    )

            # 3) Saved web research snapshots
            if self.include_web:
                web_rows = await client.search_web_snapshots(
                    query_embedding=query_vec,
                    match_count=max_results,
                    match_threshold=0.4,
                )
                for r in web_rows or []:
                    sim = float(r.get("similarity") or 0.0)
                    results.append(
                        {
                            "source": "saved_web",
                            "title": r.get("title") or r.get("url") or "Web Resource",
                            "content": (r.get("content") or "")[:1000],
                            "relevance_score": sim,
                            "metadata": {
                                "url": r.get("url"),
                                "source_domain": r.get("source_domain") or r.get("domain"),
                                "published_at": r.get("published_at"),
                                "snapshot_id": r.get("id"),
                            },
                            "quality_indicators": {
                                "high_confidence": sim >= 0.8,
                            },
                        }
                    )

            if track_performance and perf_start is not None:
                duration_ms = (time.perf_counter() - perf_start) * 1000
                logger.info(
                    "FeedMe knowledge retrieval completed in %.2f ms (track_performance enabled)",
                    duration_ms,
                )
                latency_value = round(duration_ms, 2)
                for item in results:
                    item.setdefault("diagnostics", {})["retrieval_latency_ms"] = latency_value

            return results

        except Exception as e:
            logger.error(f"retrieve_knowledge failed: {e}")
            return []
