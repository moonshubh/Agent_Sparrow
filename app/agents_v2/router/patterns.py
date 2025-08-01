"""
Pattern definitions for router embedding-based classification.

Pre-defined patterns for common Mailbird support queries to enable
fast, LLM-free routing based on semantic similarity.
"""

from typing import List, Dict, Optional, Tuple, Any
import json
import os
import numpy as np
from pathlib import Path
import asyncio
import logging

from app.tools.embeddings import embed_texts, GeminiEmbeddings

logger = logging.getLogger(__name__)

def _load_pattern_definitions() -> Dict[str, Dict[str, Any]]:
    """Load pattern definitions from external configuration file."""
    config_file = Path(__file__).parent / "pattern_definitions.json"
    
    try:
        with open(config_file, 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        logger.error(f"Pattern definitions file not found: {config_file}")
        # Return minimal fallback configuration
        return {
            "primary_support": {
                "patterns": ["help with email", "mailbird support"],
                "confidence_threshold": 0.65
            }
        }
    except json.JSONDecodeError as e:
        logger.error(f"Invalid JSON in pattern definitions file: {e}")
        return {
            "primary_support": {
                "patterns": ["help with email", "mailbird support"],
                "confidence_threshold": 0.65
            }
        }
    except Exception as e:
        logger.error(f"Failed to load pattern definitions: {e}")
        return {
            "primary_support": {
                "patterns": ["help with email", "mailbird support"],
                "confidence_threshold": 0.65
            }
        }


# Load pattern definitions from external configuration
PATTERN_DEFINITIONS = _load_pattern_definitions()


class RouterPatternMatcher:
    """
    Manages pattern embeddings and similarity matching for the router.
    
    Features:
    - Pre-computed pattern embeddings for fast matching
    - Persistent storage of embeddings
    - Similarity-based routing decisions
    - Cache management for efficiency
    """
    
    def __init__(self, cache_dir: str = "app/cache/router_patterns"):
        """Initialize pattern matcher with cache directory."""
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        
        self.embeddings_client = GeminiEmbeddings(dimension=768)
        self.pattern_embeddings: Dict[str, Dict[str, Any]] = {}
        self.embeddings_file = self.cache_dir / "pattern_embeddings.json"
        
        # Load cached embeddings on init
        self._load_embeddings()
    
    async def initialize(self):
        """Initialize pattern embeddings, computing if necessary."""
        if not self.pattern_embeddings:
            logger.info("Computing pattern embeddings for router...")
            await self._compute_all_embeddings()
            self._save_embeddings()
        else:
            logger.info(f"Loaded {len(self.pattern_embeddings)} cached pattern embeddings")
    
    async def _compute_all_embeddings(self):
        """Compute embeddings for all patterns."""
        for category, config in PATTERN_DEFINITIONS.items():
            patterns = config["patterns"]
            logger.info(f"Computing embeddings for {category} ({len(patterns)} patterns)")
            
            try:
                # Batch embed all patterns for this category
                embeddings = await self.embeddings_client.embed_texts(
                    patterns, 
                    task_type="retrieval_document"
                )
                
                if not embeddings:
                    logger.warning(f"No embeddings generated for category {category}, skipping")
                    continue
                
                # Store with patterns
                self.pattern_embeddings[category] = {
                    "patterns": patterns,
                    "embeddings": [emb.tolist() for emb in embeddings],
                    "confidence_threshold": config["confidence_threshold"]
                }
                
            except Exception as e:
                logger.error(f"Failed to compute embeddings for category {category}: {e}")
                # Set default embeddings (zeros) to prevent complete failure
                default_embedding = [0.0] * 768  # Default dimension
                self.pattern_embeddings[category] = {
                    "patterns": patterns,
                    "embeddings": [default_embedding] * len(patterns),
                    "confidence_threshold": config["confidence_threshold"]
                }
                logger.warning(f"Using default embeddings for category {category}")
                continue
    
    def _save_embeddings(self):
        """Save embeddings to cache file."""
        try:
            with open(self.embeddings_file, 'w') as f:
                json.dump(self.pattern_embeddings, f)
            logger.info(f"Saved pattern embeddings to {self.embeddings_file}")
        except Exception as e:
            logger.error(f"Failed to save pattern embeddings: {e}")
    
    def _load_embeddings(self):
        """Load embeddings from cache file."""
        if self.embeddings_file.exists():
            try:
                with open(self.embeddings_file, 'r') as f:
                    data = json.load(f)
                
                # Convert lists back to numpy arrays
                # Create new dictionary to avoid modifying during iteration
                transformed_data = {}
                for category, config in data.items():
                    transformed_config = config.copy()
                    transformed_config["embeddings"] = [
                        np.array(emb, dtype=np.float32) 
                        for emb in config["embeddings"]
                    ]
                    transformed_data[category] = transformed_config
                
                self.pattern_embeddings = transformed_data
                logger.info(f"Loaded pattern embeddings from {self.embeddings_file}")
            except Exception as e:
                logger.error(f"Failed to load pattern embeddings: {e}")
                self.pattern_embeddings = {}
    
    async def match_query(self, query: str) -> Tuple[Optional[str], float, Optional[str]]:
        """
        Match a query against patterns to determine routing.
        
        Args:
            query: User query text
            
        Returns:
            Tuple of (category, confidence, matched_pattern)
            Returns (None, 0.0, None) if no match above threshold
        """
        # Ensure embeddings are initialized
        if not self.pattern_embeddings:
            await self.initialize()
        
        # Embed the query
        query_embedding = await self.embeddings_client.embed_query(query)
        
        # Find best match across all categories
        best_category = None
        best_confidence = 0.0
        best_pattern = None
        
        for category, config in self.pattern_embeddings.items():
            embeddings = config["embeddings"]
            patterns = config["patterns"]
            threshold = config["confidence_threshold"]
            
            # Calculate similarities
            similarities = GeminiEmbeddings.cosine_similarities(
                query_embedding, 
                embeddings
            )
            
            # Find best match in this category
            if similarities:
                max_idx = np.argmax(similarities)
                max_similarity = similarities[max_idx]
                
                if max_similarity >= threshold and max_similarity > best_confidence:
                    best_category = category
                    best_confidence = max_similarity
                    best_pattern = patterns[max_idx]
        
        return best_category, best_confidence, best_pattern
    
    async def add_pattern(self, category: str, pattern: str):
        """
        Add a new pattern to a category dynamically.
        
        Args:
            category: Category name
            pattern: New pattern text
        """
        if category not in self.pattern_embeddings:
            logger.warning(f"Unknown category {category}, creating new")
            self.pattern_embeddings[category] = {
                "patterns": [],
                "embeddings": [],
                "confidence_threshold": 0.7
            }
        
        # Embed the new pattern
        embeddings = await self.embeddings_client.embed_texts(
            [pattern],
            task_type="retrieval_document"
        )
        
        if embeddings:
            config = self.pattern_embeddings[category]
            config["patterns"].append(pattern)
            # Convert embedding to list for JSON serialization
            config["embeddings"].append(embeddings[0].tolist() if hasattr(embeddings[0], 'tolist') else embeddings[0])
            
            # Save updated embeddings
            self._save_embeddings()
            logger.info(f"Added new pattern to {category}: {pattern}")
    
    def get_category_info(self, category: str) -> Optional[Dict]:
        """Get information about a category."""
        return self.pattern_embeddings.get(category)
    
    def list_categories(self) -> List[str]:
        """List all available categories."""
        return list(self.pattern_embeddings.keys())


# Global pattern matcher instance and lock for thread safety
_pattern_matcher: Optional[RouterPatternMatcher] = None
_pattern_matcher_lock = asyncio.Lock()


async def get_pattern_matcher() -> RouterPatternMatcher:
    """Get or create the global pattern matcher with concurrency protection."""
    global _pattern_matcher
    
    # Fast path: if already initialized, return immediately
    if _pattern_matcher is not None:
        return _pattern_matcher
    
    # Slow path: acquire lock and initialize if needed
    async with _pattern_matcher_lock:
        # Double-check pattern to avoid race conditions
        if _pattern_matcher is None:
            _pattern_matcher = RouterPatternMatcher()
            await _pattern_matcher.initialize()
    
    return _pattern_matcher