"""
Embeddings utility for pattern matching and semantic search.

Supports Gemini embeddings with Matryoshka dimension reduction capability.
Used by the router for fast pattern-based query classification.
"""

import logging
from typing import List, Optional, Dict, Any
import numpy as np
from functools import lru_cache
import asyncio

import google.generativeai as genai
from google.generativeai.types import HarmCategory, HarmBlockThreshold

from app.core.settings import settings
from app.core.rate_limiting.embedding_limiter import EmbeddingRateLimiter

logger = logging.getLogger(__name__)

# Initialize rate limiter for embeddings
_embedding_limiter: Optional[EmbeddingRateLimiter] = None

def get_embedding_limiter() -> EmbeddingRateLimiter:
    """Get or create embedding rate limiter."""
    global _embedding_limiter
    if _embedding_limiter is None:
        _embedding_limiter = EmbeddingRateLimiter()
    return _embedding_limiter


class GeminiEmbeddings:
    """
    Gemini embeddings wrapper with dimension reduction support.
    
    Features:
    - Uses gemini-embedding-001 model
    - Supports Matryoshka dimension reduction (768 or 1536)
    - Rate limiting integration
    - Batch processing for efficiency
    - Caching for repeated queries
    """
    
    def __init__(self, api_key: Optional[str] = None, dimension: int = 768):
        """
        Initialize Gemini embeddings.
        
        Args:
            api_key: Google API key (uses env var if not provided)
            dimension: Embedding dimension (768 or 1536)
        """
        self.api_key = api_key or settings.google_api_key
        self.dimension = dimension
        self.model_name = "models/embedding-001"
        
        if dimension not in [768, 1536]:
            raise ValueError(f"Unsupported dimension {dimension}. Use 768 or 1536.")
            
        # Configure genai
        genai.configure(api_key=self.api_key)
        
        # Embedding cache for common queries
        self._cache: Dict[str, np.ndarray] = {}
        self._cache_size = 1000
        
        logger.info(f"Initialized Gemini embeddings with dimension {dimension}")
    
    async def embed_texts(self, texts: List[str], task_type: str = "retrieval_document") -> List[np.ndarray]:
        """
        Embed a list of texts asynchronously.
        
        Args:
            texts: List of texts to embed
            task_type: Task type for embeddings (retrieval_document, retrieval_query, etc.)
            
        Returns:
            List of embedding vectors as numpy arrays
        """
        if not texts:
            return []
            
        # Check cache for any hits
        embeddings = []
        texts_to_embed = []
        text_indices = []
        
        for i, text in enumerate(texts):
            cache_key = f"{text}:{task_type}:{self.dimension}"
            if cache_key in self._cache:
                embeddings.append((i, self._cache[cache_key]))
            else:
                texts_to_embed.append(text)
                text_indices.append(i)
        
        # Embed uncached texts
        if texts_to_embed:
            # Rate limit check
            limiter = get_embedding_limiter()
            allowed = await limiter.check_and_consume("embedding", tokens=len(texts_to_embed))
            
            if not allowed:
                raise Exception("Embedding rate limit exceeded")
            
            try:
                # Batch embed
                result = genai.embed_content(
                    model=self.model_name,
                    content=texts_to_embed,
                    task_type=task_type,
                    title=None  # Not using title for now
                )
                
                # Process results
                for idx, embedding in enumerate(result['embedding']):
                    # Apply dimension reduction if needed
                    if self.dimension == 768 and len(embedding) > 768:
                        # Matryoshka: take first 768 dimensions
                        embedding = embedding[:768]
                    
                    np_embedding = np.array(embedding, dtype=np.float32)
                    
                    # Normalize for cosine similarity
                    norm = np.linalg.norm(np_embedding)
                    if norm > 0:
                        np_embedding = np_embedding / norm
                    
                    # Cache the result
                    text = texts_to_embed[idx]
                    cache_key = f"{text}:{task_type}:{self.dimension}"
                    self._add_to_cache(cache_key, np_embedding)
                    
                    # Add to results
                    original_idx = text_indices[idx]
                    embeddings.append((original_idx, np_embedding))
                    
            except Exception as e:
                logger.error(f"Error embedding texts: {e}")
                raise
        
        # Sort by original index and return just embeddings
        embeddings.sort(key=lambda x: x[0])
        return [emb for _, emb in embeddings]
    
    def embed_texts_sync(self, texts: List[str], task_type: str = "retrieval_document") -> List[np.ndarray]:
        """Synchronous wrapper for embed_texts."""
        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(self.embed_texts(texts, task_type))
        finally:
            loop.close()
    
    async def embed_query(self, query: str) -> np.ndarray:
        """
        Embed a single query for retrieval.
        
        Args:
            query: Query text to embed
            
        Returns:
            Embedding vector as numpy array
        """
        embeddings = await self.embed_texts([query], task_type="retrieval_query")
        return embeddings[0] if embeddings else np.zeros(self.dimension)
    
    def _add_to_cache(self, key: str, embedding: np.ndarray):
        """Add embedding to cache with size limit."""
        if len(self._cache) >= self._cache_size:
            # Remove oldest entry (simple FIFO)
            oldest_key = next(iter(self._cache))
            del self._cache[oldest_key]
        
        self._cache[key] = embedding
    
    @staticmethod
    def cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
        """
        Calculate cosine similarity between two vectors.
        
        Assumes vectors are already normalized.
        """
        return float(np.dot(a, b))
    
    @staticmethod
    def cosine_similarities(query: np.ndarray, documents: List[np.ndarray]) -> List[float]:
        """
        Calculate cosine similarities between query and multiple documents.
        
        Args:
            query: Query embedding (normalized)
            documents: List of document embeddings (normalized)
            
        Returns:
            List of similarity scores
        """
        if not documents:
            return []
            
        # Stack documents for efficient computation
        doc_matrix = np.vstack(documents)
        
        # Compute similarities
        similarities = np.dot(doc_matrix, query)
        
        return similarities.tolist()


# Convenience functions
@lru_cache(maxsize=1)
def get_embeddings_client(dimension: int = 768) -> GeminiEmbeddings:
    """Get a cached embeddings client."""
    return GeminiEmbeddings(dimension=dimension)


async def embed_texts(texts: List[str], dimension: int = 768) -> List[np.ndarray]:
    """
    Convenience function to embed texts.
    
    Args:
        texts: List of texts to embed
        dimension: Embedding dimension (768 or 1536)
        
    Returns:
        List of embedding vectors
    """
    client = get_embeddings_client(dimension)
    return await client.embed_texts(texts)


async def embed_query(query: str, dimension: int = 768) -> np.ndarray:
    """
    Convenience function to embed a query.
    
    Args:
        query: Query text
        dimension: Embedding dimension
        
    Returns:
        Query embedding vector
    """
    client = get_embeddings_client(dimension)
    return await client.embed_query(query)