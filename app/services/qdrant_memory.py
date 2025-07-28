"""QdrantMemory: wrapper around Qdrant for storing and retrieving
conversation embeddings per session.
"""
from __future__ import annotations

import os
import uuid
from typing import List
from datetime import datetime
import numpy as np

from qdrant_client import QdrantClient
from qdrant_client.http.models import PointStruct, Distance, VectorParams, SearchParams, Filter, FieldCondition, MatchValue
from qdrant_client.http.exceptions import UnexpectedResponse
import requests
import structlog
from langchain_google_genai import GoogleGenerativeAIEmbeddings

from app.core.settings import settings

QDRANT_URL = os.getenv("QDRANT_URL", "http://localhost:6333")
QDRANT_API_KEY = os.getenv("QDRANT_API_KEY")
_COLLECTION_PREFIX = os.getenv("QDRANT_COLLECTION_PREFIX", "conversation_")

# Logger
logger = structlog.get_logger()


class QdrantMemory:
    """Simple wrapper to write/read conversation vectors to Qdrant."""

    def __init__(self) -> None:
        self.client = QdrantClient(url=QDRANT_URL, api_key=QDRANT_API_KEY)
        # Using Gemini embedding-001 model (GA since July 2025)
        # Supports Matryoshka Representation Learning with 768 dimensions for balanced performance/accuracy
        self.embedder = GoogleGenerativeAIEmbeddings(
            model="models/gemini-embedding-001",
            google_api_key=settings.gemini_api_key,
            task_type="SEMANTIC_SIMILARITY",  # Optimized for chat memory
        )
        self.embedding_dimensions = 768  # Configurable dimension size

    # ---------------------------------------------------------------------
    # Internal helpers
    # ---------------------------------------------------------------------

    def _collection_name(self, session_id: str) -> str:
        return f"{_COLLECTION_PREFIX}{session_id}"

    def _ensure_collection(self, name: str, dim: int = None) -> None:
        """Create collection if it does not exist.
        Falls back silently if Qdrant is unreachable."""
        if dim is None:
            dim = self.embedding_dimensions
        try:
            if name in (c.name for c in self.client.get_collections().collections):
                return
            self.client.create_collection(
                collection_name=name,
                vectors_config=VectorParams(size=dim, distance=Distance.COSINE),
            )
        except (requests.exceptions.ConnectionError, UnexpectedResponse, Exception) as e:
            logger.warning("qdrant_unavailable", error=str(e))

    def _embed(self, text: str) -> List[float]:
        """Embed text using Gemini with normalization for cosine similarity."""
        embedding = self.embedder.embed_query(text)
        # Normalize embedding for cosine similarity (best practice)
        embedding_array = np.array(embedding)
        normalized = embedding_array / np.linalg.norm(embedding_array)
        return normalized.tolist()

    # ---------------------------------------------------------------------
    # Public API
    # ---------------------------------------------------------------------

    def add_interaction(self, session_id: str, user_query: str, agent_response: str) -> None:
        """Embed query + response and upsert into session collection."""
        collection = self._collection_name(session_id)
        self._ensure_collection(collection)

        combined = f"User: {user_query}\nAssistant: {agent_response}"
        vector = self._embed(combined)

        point = PointStruct(
            id=str(uuid.uuid4()),
            vector=vector,
            payload={
                "text": combined,
                "session_id": session_id,  # Add for filtering
                "user_query": user_query,
                "agent_response": agent_response,
                "timestamp": datetime.now().isoformat()
            },
        )
        try:
            self.client.upsert(collection, points=[point])
        except (requests.exceptions.ConnectionError, UnexpectedResponse, Exception) as e:
            logger.warning("qdrant_upsert_failed", error=str(e))

    def retrieve_context(
        self, session_id: str, query_embedding: List[float], top_k: int = 3
    ) -> List[str]:
        """Return top_k similar past interactions' texts with strict session filtering."""
        collection = self._collection_name(session_id)
        try:
            if not any(c.name == collection for c in self.client.get_collections().collections):
                return []

            # Normalize query embedding for consistency
            query_array = np.array(query_embedding)
            normalized_query = query_array / np.linalg.norm(query_array)

            # Search within session-specific collection (no additional filtering needed)
            res = self.client.search(
                collection_name=collection,
                query_vector=normalized_query.tolist(),
                limit=top_k,
                search_params=SearchParams(hnsw_ef=64),
            )
            return [point.payload.get("text", "") for point in res]
        except (requests.exceptions.ConnectionError, UnexpectedResponse, Exception) as e:
            logger.warning("qdrant_search_failed", error=str(e))
            return []

    def embed_query(self, text: str) -> List[float]:
        """Expose embedding of arbitrary text (for external callers)."""
        return self._embed(text)
