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
import threading
from collections import OrderedDict

import google.generativeai as genai
from google.generativeai.types import HarmCategory, HarmBlockThreshold

from app.core.settings import settings
from app.core.rate_limiting.embedding_limiter import EmbeddingRateLimiter

logger = logging.getLogger(__name__)


class EmbeddingRateLimitError(Exception):
    """Custom exception for embedding rate limit exceeded."""
    pass


# Initialize rate limiter for embeddings with thread safety
_embedding_limiter: Optional[EmbeddingRateLimiter] = None
_embedding_limiter_lock = threading.Lock()

def get_embedding_limiter() -> EmbeddingRateLimiter:
    """Get or create embedding rate limiter with thread safety."""
    global _embedding_limiter
    
    # Fast path: if already initialized, return immediately
    if _embedding_limiter is not None:
        return _embedding_limiter
    
    # Slow path: acquire lock and initialize if needed
    with _embedding_limiter_lock:
        # Double-check pattern to avoid race conditions
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
        self.model_name = "gemini-embedding-001"
        
        if dimension not in [768, 1536]:
            raise ValueError(f"Unsupported dimension {dimension}. Use 768 or 1536.")
            
        # Configure genai
        genai.configure(api_key=self.api_key)
        
        # Embedding cache for common queries with thread safety
        self._cache: OrderedDict[str, np.ndarray] = OrderedDict()
        self._cache_size = 1000
        self._cache_lock = threading.Lock()
        
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
            with self._cache_lock:
                if cache_key in self._cache:
                    # Move to end (mark as recently used)
                    embedding = self._cache.pop(cache_key)
                    self._cache[cache_key] = embedding
                    embeddings.append((i, embedding))
                else:
                    texts_to_embed.append(text)
                    text_indices.append(i)
        
        # Embed uncached texts
        if texts_to_embed:
            # Rate limit check
            limiter = get_embedding_limiter()
            allowed = await limiter.check_and_consume("embedding", tokens=len(texts_to_embed))
            
            if not allowed:
                raise EmbeddingRateLimitError("Embedding rate limit exceeded")
            
            try:
                # Batch embed
                result = genai.embed_content(
                    model=self.model_name,
                    content=texts_to_embed,
                    task_type=task_type,
                    title=None  # Not using title for now
                )
                
                # Process results - access values from nested structure
                embedding_values = result['embedding']['values'] if 'values' in result['embedding'] else result['embedding']
                for idx, embedding in enumerate(embedding_values):
                    # Validate embedding length before dimension reduction
                    if len(embedding) < self.dimension:
                        logger.warning(f"Embedding length {len(embedding)} is less than requested dimension {self.dimension}")
                        # Zero-padding behavior: Pad with zeros if embedding is shorter than expected
                        # This maintains consistent dimensionality but may reduce embedding quality
                        # as the padded zeros don't carry semantic meaning
                        embedding = embedding + [0.0] * (self.dimension - len(embedding))
                    
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
        """Synchronous wrapper for embed_texts with event loop handling."""
        try:
            # Check if there's already a running event loop
            loop = asyncio.get_running_loop()
            # If we're in an async context, we need to use a different approach
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as executor:
                future = executor.submit(asyncio.run, self.embed_texts(texts, task_type))
                return future.result()
        except RuntimeError:
            # No running loop, safe to create a new one
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
        """Add embedding to cache with LRU eviction strategy and thread safety."""
        with self._cache_lock:
            if key in self._cache:
                # Move to end (mark as recently used)
                self._cache.move_to_end(key)
                self._cache[key] = embedding
            else:
                # Add new entry
                if len(self._cache) >= self._cache_size:
                    # Remove least recently used entry (LRU eviction)
                    self._cache.popitem(last=False)
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
@lru_cache(maxsize=8)  # Support multiple dimensions and configurations
def get_embeddings_client(dimension: int = 768) -> GeminiEmbeddings:
    """Get a cached embeddings client for the specified dimension."""
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