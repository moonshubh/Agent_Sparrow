"""
FeedMe Embedding Pipeline
Optimized embedding generation for Q&A pairs with multi-faceted embeddings
"""

import logging
import time
import json
from typing import List, Dict, Any, Optional
import numpy as np
from sentence_transformers import SentenceTransformer

from app.core.settings import settings

logger = logging.getLogger(__name__)


class FeedMeEmbeddingPipeline:
    """Optimized embedding generation for Q&A pairs"""
    
    # Configuration constants
    DEFAULT_CONTENT_LENGTH_NORMALIZATION_FACTOR = 100.0
    
    def __init__(self, model_name: str = 'all-MiniLM-L12-v2', 
                 content_length_normalization_factor: float = None):
        """Initialize embedding pipeline with specified model"""
        self.model_name = model_name
        self.dimension = 384  # Smaller, faster embeddings for production
        self.enable_semantic_optimization = False
        self.enable_quality_scoring = False
        self.domain = 'general'
        self.content_length_normalization_factor = (
            content_length_normalization_factor or 
            self.DEFAULT_CONTENT_LENGTH_NORMALIZATION_FACTOR
        )
        
        try:
            # Initialize embedding model
            self.model = SentenceTransformer(model_name)
            logger.info(f"Initialized embedding pipeline with model: {model_name}")
        except Exception as e:
            logger.error(f"Failed to initialize embedding model: {e}")
            raise

    async def generate_embeddings(self, qa_pairs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Generate multi-faceted embeddings for Q&A pairs"""
        
        if not qa_pairs:
            return []
        
        start_time = time.time()
        
        try:
            for i, pair in enumerate(qa_pairs):
                # Generate question embedding
                question_text = pair.get('question_text', '')
                if question_text:
                    pair['question_embedding'] = self.model.encode(
                        question_text,
                        normalize_embeddings=True
                    ).tolist()
                
                # Generate answer embedding
                answer_text = pair.get('answer_text', '')
                if answer_text:
                    pair['answer_embedding'] = self.model.encode(
                        answer_text,
                        normalize_embeddings=True
                    ).tolist()
                
                # Generate combined embedding with context
                combined_text = self._build_combined_text(pair)
                pair['combined_embedding'] = self.model.encode(
                    combined_text,
                    normalize_embeddings=True
                ).tolist()
                
                # Add semantic embeddings if enabled
                if self.enable_semantic_optimization:
                    pair['semantic_embedding'] = self._generate_semantic_embedding(pair)
                
                # Add quality scoring if enabled
                if self.enable_quality_scoring:
                    pair['embedding_quality_score'] = self._assess_embedding_quality(pair)
                
                # Dynamic embedding dimension validation
                if 'combined_embedding' in pair:
                    embedding_dim = len(pair['combined_embedding'])
                    if embedding_dim != self.dimension:
                        logger.warning(f"Embedding dimension mismatch: expected {self.dimension}, got {embedding_dim}")
                        # Pad or truncate to expected dimension
                        if embedding_dim < self.dimension:
                            pair['combined_embedding'].extend([0.0] * (self.dimension - embedding_dim))
                        else:
                            pair['combined_embedding'] = pair['combined_embedding'][:self.dimension]
                
                # Add domain processing metadata
                if self.domain == 'customer_support':
                    pair['metadata'] = pair.get('metadata', {})
                    pair['metadata']['domain_processed'] = True
                
                # Add processing time for first item (approximate)
                if i == 0:
                    processing_time = time.time() - start_time
                    pair['processing_time'] = processing_time
            
            logger.info(f"Generated embeddings for {len(qa_pairs)} Q&A pairs in {time.time() - start_time:.2f}s")
            return qa_pairs
            
        except Exception as e:
            logger.error(f"Error generating embeddings: {e}")
            return qa_pairs  # Return original pairs without embeddings

    def _build_combined_text(self, pair: Dict[str, Any]) -> str:
        """Build combined text for context-aware embedding"""
        
        question = pair.get('question_text', '')
        answer = pair.get('answer_text', '')
        context_before = pair.get('context_before') or ''
        context_after = pair.get('context_after') or ''
        
        # Build structured combined text
        combined_parts = []
        
        combined_parts.append(f"Question: {question}")
        
        if context_before:
            combined_parts.append(f"Context: {context_before}")
        
        combined_parts.append(f"Answer: {answer}")
        
        if context_after:
            combined_parts.append(f"Resolution: {context_after}")
        
        return '\n'.join(combined_parts)

    def _generate_semantic_embedding(self, pair: Dict[str, Any]) -> List[float]:
        """Generate semantic-optimized embedding"""
        
        # Extract semantic content (simplified implementation)
        semantic_text = f"{pair.get('question_text', '')} {pair.get('answer_text', '')}"
        
        # Process for semantic optimization
        semantic_embedding = self.model.encode(
            semantic_text,
            normalize_embeddings=True
        )
        
        return semantic_embedding.tolist()

    def _assess_embedding_quality(self, pair: Dict[str, Any]) -> float:
        """Assess quality of generated embeddings"""
        
        # Simple quality assessment based on embedding characteristics
        try:
            question_emb = np.array(pair.get('question_embedding', []))
            answer_emb = np.array(pair.get('answer_embedding', []))
            
            if len(question_emb) == 0 or len(answer_emb) == 0:
                return 0.0
            
            # Check embedding norms (should be close to 1.0 for normalized)
            q_norm = np.linalg.norm(question_emb)
            a_norm = np.linalg.norm(answer_emb)
            
            # Quality score based on normalization and content length
            norm_score = min(1.0, (q_norm + a_norm) / 2.0)
            
            # Content length factor
            content_length = len(pair.get('question_text', '')) + len(pair.get('answer_text', ''))
            length_score = min(1.0, content_length / self.content_length_normalization_factor)
            
            return (norm_score + length_score) / 2.0
            
        except Exception as e:
            logger.debug(f"Error assessing embedding quality: {e}")
            return 0.5  # Default middle score