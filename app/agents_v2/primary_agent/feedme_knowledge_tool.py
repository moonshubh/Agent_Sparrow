"""
Enhanced Knowledge Base Search Tool with FeedMe Integration

Replaces the placeholder mailbird_kb_search tool with comprehensive knowledge retrieval
from both traditional knowledge base and FeedMe customer support examples.
"""

import logging
import asyncio
from typing import Dict, Any, List, Optional
from pydantic import BaseModel, Field
from langchain_core.tools import tool

from app.db.embedding_utils import find_combined_similar_content
from app.feedme.integration.primary_agent_connector import PrimaryAgentConnector
from app.core.settings import settings

logger = logging.getLogger(__name__)


class EnhancedKBSearchInput(BaseModel):
    """Enhanced input schema for knowledge base search with FeedMe integration"""
    query: str = Field(..., description="The search query to find relevant articles and support examples")
    context: Optional[Dict[str, Any]] = Field(
        default=None, 
        description="Additional context from Primary Agent (emotional state, platform, etc.)"
    )
    max_results: int = Field(
        default=5, 
        description="Maximum number of results to return (3-10)",
        ge=1,
        le=10
    )
    search_sources: List[str] = Field(
        default=["knowledge_base", "feedme"],
        description="Sources to search: knowledge_base, feedme, or both"
    )
    min_confidence: Optional[float] = Field(
        default=None,
        description="Minimum confidence threshold for FeedMe results (0.0-1.0)",
        ge=0.0,
        le=1.0
    )


class SearchResultSummary(BaseModel):
    """Summary of search results for Primary Agent consumption"""
    total_results: int
    kb_results: int
    feedme_results: int
    avg_relevance: float
    search_time_ms: int
    sources_used: List[str]
    fallback_used: bool = False
    
    
# Initialize FeedMe connector (global instance for efficiency)
_feedme_connector = None


def get_feedme_connector() -> PrimaryAgentConnector:
    """Get or create FeedMe connector instance"""
    global _feedme_connector
    if _feedme_connector is None:
        try:
            _feedme_connector = PrimaryAgentConnector()
            logger.info("Initialized FeedMe Primary Agent connector")
        except Exception as e:
            logger.error(f"Failed to initialize FeedMe connector: {e}")
            _feedme_connector = None
    return _feedme_connector


@tool("enhanced-mailbird-kb-search", args_schema=EnhancedKBSearchInput)
def enhanced_mailbird_kb_search(
    query: str,
    context: Optional[Dict[str, Any]] = None,
    max_results: int = 5,
    search_sources: List[str] = ["knowledge_base", "feedme"],
    min_confidence: Optional[float] = None
) -> str:
    """
    Enhanced knowledge base search with FeedMe integration.
    
    Searches both traditional knowledge base articles and FeedMe customer support examples
    to provide comprehensive, relevant information for customer support queries.
    
    Args:
        query: Search query text
        context: Additional context from Primary Agent
        max_results: Maximum number of results (1-10)
        search_sources: Sources to search ("knowledge_base", "feedme", or both)
        min_confidence: Minimum confidence for FeedMe results
        
    Returns:
        Formatted search results with relevance scores and source information
    """
    import time
    start_time = time.time()
    
    try:
        logger.info(f"Enhanced KB search: '{query[:50]}...' sources={search_sources}")
        
        # Validate inputs
        max_results = max(1, min(10, max_results))
        if not search_sources:
            search_sources = ["knowledge_base", "feedme"]
        
        # Initialize results
        all_results = []
        kb_count = 0
        feedme_count = 0
        fallback_used = False
        
        # Determine search strategy
        use_kb = "knowledge_base" in search_sources
        use_feedme = "feedme" in search_sources and settings.feedme_enabled
        
        # Strategy 1: Use FeedMe integration if available and requested
        if use_feedme:
            try:
                feedme_results = _search_with_feedme(
                    query=query,
                    context=context or {},
                    max_results=max_results,
                    min_confidence=min_confidence
                )
                all_results.extend(feedme_results)
                feedme_count = len(feedme_results)
                logger.debug(f"FeedMe search returned {feedme_count} results")
                
            except Exception as e:
                logger.warning(f"FeedMe search failed, falling back: {e}")
                fallback_used = True
        
        # Strategy 2: Use traditional KB search if needed or requested
        if use_kb and (not all_results or len(all_results) < max_results):
            try:
                kb_results = _search_traditional_kb(
                    query=query,
                    max_results=max_results - len(all_results)
                )
                all_results.extend(kb_results)
                kb_count = len(kb_results)
                logger.debug(f"Traditional KB search returned {kb_count} results")
                
            except Exception as e:
                logger.warning(f"Traditional KB search failed: {e}")
                fallback_used = True
        
        # Strategy 3: Combined search fallback
        if not all_results or fallback_used:
            try:
                logger.info("Using combined search fallback")
                combined_results = _search_combined_fallback(query, max_results)
                if combined_results:
                    all_results = combined_results
                    # Count by source type
                    kb_count = len([r for r in combined_results if r.get('source') == 'knowledge_base'])
                    feedme_count = len([r for r in combined_results if r.get('source') == 'feedme'])
                    fallback_used = True
                
            except Exception as e:
                logger.error(f"All search methods failed: {e}")
                return _format_error_response(query, str(e))
        
        # Limit and format results
        all_results = all_results[:max_results]
        
        # Calculate metrics
        search_time_ms = int((time.time() - start_time) * 1000)
        avg_relevance = _calculate_average_relevance(all_results)
        
        # Create summary
        summary = SearchResultSummary(
            total_results=len(all_results),
            kb_results=kb_count,
            feedme_results=feedme_count,
            avg_relevance=avg_relevance,
            search_time_ms=search_time_ms,
            sources_used=search_sources,
            fallback_used=fallback_used
        )
        
        # Format final response
        return _format_search_response(all_results, summary, query)
        
    except Exception as e:
        logger.error(f"Critical error in enhanced KB search: {e}")
        return _format_error_response(query, str(e))


def _search_with_feedme(
    query: str,
    context: Dict[str, Any],
    max_results: int,
    min_confidence: Optional[float]
) -> List[Dict[str, Any]]:
    """Search using FeedMe integration"""
    
    # Get FeedMe connector
    connector = get_feedme_connector()
    if not connector:
        raise Exception("FeedMe connector not available")
    
    # Build query object for FeedMe
    feedme_query = {
        'query_text': query,
        **context
    }
    
    # Add confidence threshold to context if specified
    if min_confidence is not None:
        feedme_query['min_confidence'] = min_confidence
    
    # Perform async search (run in thread pool if needed)
    try:
        # Use asyncio if available, otherwise fallback
        loop = asyncio.get_event_loop()
        if loop.is_running():
            # Create a new task in the background
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as executor:
                future = executor.submit(
                    lambda: asyncio.run(
                        connector.retrieve_knowledge(
                            query=feedme_query,
                            max_results=max_results,
                            track_performance=True
                        )
                    )
                )
                results = future.result(timeout=30)  # 30 second timeout
        else:
            results = asyncio.run(
                connector.retrieve_knowledge(
                    query=feedme_query,
                    max_results=max_results,
                    track_performance=True
                )
            )
        
        return results
        
    except Exception as e:
        logger.error(f"Error in FeedMe search execution: {e}")
        raise


def _search_traditional_kb(query: str, max_results: int) -> List[Dict[str, Any]]:
    """Search traditional knowledge base"""
    
    try:
        from app.db.embedding_utils import find_similar_documents
        
        # Search traditional KB
        kb_results = find_similar_documents(query, top_k=max_results)
        
        # Convert to standard format
        formatted_results = []
        for result in kb_results:
            formatted_result = {
                'source': 'knowledge_base',
                'title': result.url or 'Knowledge Base Article',
                'content': result.markdown or result.content or '',
                'relevance_score': result.similarity_score,
                'confidence': result.similarity_score,  # Use similarity as confidence
                'metadata': {
                    'kb_id': result.id,
                    'url': result.url,
                    'original_metadata': result.metadata,
                    'search_type': 'traditional_kb'
                },
                'context': {},
                'quality_indicators': {
                    'high_confidence': result.similarity_score >= 0.8,
                    'semantic_match': True,
                    'source_authority': 'official'
                }
            }
            formatted_results.append(formatted_result)
        
        return formatted_results
        
    except Exception as e:
        logger.error(f"Error in traditional KB search: {e}")
        raise


def _search_combined_fallback(query: str, max_results: int) -> List[Dict[str, Any]]:
    """Fallback to combined search using embedding_utils"""
    
    try:
        # Use the combined search from embedding_utils
        combined_results = find_combined_similar_content(
            query=query,
            top_k_total=max_results,
            kb_weight=0.6,
            feedme_weight=0.4,
            min_kb_similarity=0.25,
            min_feedme_similarity=0.6
        )
        
        # Convert to standard format
        formatted_results = []
        for result in combined_results:
            formatted_result = {
                'source': result.source_type,
                'title': result.title,
                'content': result.content,
                'relevance_score': result.similarity_score,
                'confidence': result.additional_data.get('original_score', result.similarity_score),
                'metadata': {
                    'combined_id': result.id,
                    'url': result.url,
                    'original_metadata': result.metadata,
                    'search_type': 'combined_fallback',
                    'additional_data': result.additional_data
                },
                'context': {},
                'quality_indicators': {
                    'high_confidence': result.similarity_score >= 0.7,
                    'semantic_match': True,
                    'fallback_result': True
                }
            }
            formatted_results.append(formatted_result)
        
        return formatted_results
        
    except Exception as e:
        logger.error(f"Error in combined fallback search: {e}")
        raise


def _calculate_average_relevance(results: List[Dict[str, Any]]) -> float:
    """Calculate average relevance score"""
    if not results:
        return 0.0
    
    total_relevance = sum(r.get('relevance_score', 0.0) for r in results)
    return total_relevance / len(results)


def _format_search_response(
    results: List[Dict[str, Any]], 
    summary: SearchResultSummary,
    original_query: str
) -> str:
    """Format search results for Primary Agent consumption"""
    
    if not results:
        return f"""# Knowledge Search Results

**Query:** {original_query}
**Status:** No relevant results found

I couldn't find any relevant information for your query. You may want to:
1. Try rephrasing your question
2. Use different keywords
3. Contact human support for specialized assistance

*Search performed across {', '.join(summary.sources_used)} in {summary.search_time_ms}ms*"""

    # Build formatted response
    response_parts = [
        f"# Knowledge Search Results",
        f"",
        f"**Query:** {original_query}",
        f"**Found:** {summary.total_results} results ({summary.kb_results} KB, {summary.feedme_results} support examples)",
        f"**Average Relevance:** {summary.avg_relevance:.2f}",
        f""
    ]
    
    # Format each result
    for i, result in enumerate(results, 1):
        source_icon = "📖" if result['source'] == 'knowledge_base' else "💬"
        confidence_icon = "🔥" if result.get('confidence', 0) >= 0.8 else "✅" if result.get('confidence', 0) >= 0.7 else "ℹ️"
        
        response_parts.extend([
            f"## {source_icon} Result {i}: {result.get('title', 'Knowledge Item')}",
            f"{confidence_icon} **Relevance:** {result.get('relevance_score', 0):.2f} | **Source:** {result['source']}",
            f"",
            f"{result.get('content', 'No content available')[:500]}{'...' if len(result.get('content', '')) > 500 else ''}",
            f""
        ])
        
        # Add metadata for high-quality results
        if result.get('confidence', 0) >= 0.8:
            quality_info = []
            qi = result.get('quality_indicators', {})
            
            if qi.get('frequently_used'):
                quality_info.append("Frequently used solution")
            if qi.get('recent_usage'):
                quality_info.append("Recently validated")
            if qi.get('high_confidence'):
                quality_info.append("High confidence match")
            
            if quality_info:
                response_parts.append(f"*{', '.join(quality_info)}*")
                response_parts.append("")
        
        # Add source-specific context
        if result['source'] == 'feedme':
            metadata = result.get('metadata', {})
            if metadata.get('issue_type'):
                response_parts.append(f"**Issue Type:** {metadata['issue_type']}")
            if metadata.get('tags'):
                response_parts.append(f"**Tags:** {', '.join(metadata['tags'][:3])}")
            response_parts.append("")
        
        response_parts.append("---")
        response_parts.append("")
    
    # Add search metadata
    response_parts.extend([
        f"*Search completed in {summary.search_time_ms}ms using {', '.join(summary.sources_used)}*",
        f"*{'Fallback search used due to primary method issues' if summary.fallback_used else 'Primary search methods successful'}*"
    ])
    
    return "\n".join(response_parts)


def _format_error_response(query: str, error_message: str) -> str:
    """Format error response for Primary Agent"""
    
    return f"""# Knowledge Search Error

**Query:** {query}
**Status:** Search temporarily unavailable

I encountered an issue while searching for information about your query. 

**Error:** {error_message}

**What you can do:**
1. Try rephrasing your question
2. Ask me to search again in a moment
3. For urgent issues, please contact human support

*The search system will attempt to recover automatically.*"""


# Legacy compatibility - maintain old function name as alias
@tool("mailbird-kb-search", args_schema=EnhancedKBSearchInput)
def mailbird_kb_search(query: str, **kwargs) -> str:
    """
    Legacy compatibility wrapper for enhanced knowledge base search.
    
    This maintains backward compatibility with existing Primary Agent code
    while providing enhanced functionality through FeedMe integration.
    """
    return enhanced_mailbird_kb_search(query=query, **kwargs)


# Export tool configuration for Primary Agent
ENHANCED_KB_SEARCH_TOOL = enhanced_mailbird_kb_search
LEGACY_KB_SEARCH_TOOL = mailbird_kb_search

__all__ = [
    'enhanced_mailbird_kb_search',
    'mailbird_kb_search',
    'EnhancedKBSearchInput',
    'SearchResultSummary',
    'ENHANCED_KB_SEARCH_TOOL',
    'LEGACY_KB_SEARCH_TOOL'
]