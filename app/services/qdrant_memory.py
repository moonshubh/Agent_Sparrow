"""QdrantMemory: wrapper around Qdrant for storing and retrieving
conversation embeddings per session.
"""
from __future__ import annotations

import os
import uuid
from typing import List

from qdrant_client import QdrantClient
from qdrant_client.http.models import PointStruct, Distance, VectorParams, SearchParams
from qdrant_client.http.exceptions import UnexpectedResponse
import requests
import structlog
from langchain_google_genai import GoogleGenerativeAIEmbeddings

QDRANT_URL = os.getenv("QDRANT_URL", "http://localhost:6333")
QDRANT_API_KEY = os.getenv("QDRANT_API_KEY")
_COLLECTION_PREFIX = os.getenv("QDRANT_COLLECTION_PREFIX", "conversation_")

# Logger
logger = structlog.get_logger()


class QdrantMemory:
    """Simple wrapper to write/read conversation vectors to Qdrant."""

    def __init__(self) -> None:
        self.client = QdrantClient(url=QDRANT_URL, api_key=QDRANT_API_KEY)
        # Gemini embedding model; 768-dimensional
        self.embedder = GoogleGenerativeAIEmbeddings(
            model="models/embedding-001",
            google_api_key=os.getenv("GEMINI_API_KEY"),
        )

    # ---------------------------------------------------------------------
    # Internal helpers
    # ---------------------------------------------------------------------

    def _collection_name(self, session_id: str) -> str:
        return f"{_COLLECTION_PREFIX}{session_id}"

    def _ensure_collection(self, name: str, dim: int = 768) -> None:
        """Create collection if it does not exist.
        Falls back silently if Qdrant is unreachable."""
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
        return self.embedder.embed_query(text)

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
            payload={"text": combined},
        )
        try:
            self.client.upsert(collection, points=[point])
        except (requests.exceptions.ConnectionError, UnexpectedResponse, Exception) as e:
            logger.warning("qdrant_upsert_failed", error=str(e))

    def retrieve_context(
        self, session_id: str, query_embedding: List[float], top_k: int = 3
    ) -> List[str]:
        """Return top_k similar past interactions' texts."""
        collection = self._collection_name(session_id)
        try:
            if not any(c.name == collection for c in self.client.get_collections().collections):
                return []

            res = self.client.search(
                collection_name=collection,
                query_vector=query_embedding,
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
