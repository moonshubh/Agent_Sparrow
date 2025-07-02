"""
FeedMe v2.0 Text Search Engine
Full-text search using PostgreSQL's text search capabilities
"""

import logging
import time
import re
from typing import List, Dict, Any, Optional

from app.db.connection_manager import get_connection_manager

logger = logging.getLogger(__name__)


class TextSearchEngine:
    """Full-text search engine using PostgreSQL text search"""
    
    # SQL query template for full-text search
    SEARCH_QUERY_TEMPLATE = """
    SELECT 
        e.id,
        e.question_text,
        e.answer_text,
        e.confidence_score,
        e.issue_category,
        e.tags,
        e.usage_count,
        e.created_at,
        COALESCE(e.overall_quality_score, 0) as overall_quality_score,
        {rank_expr} as text_score,
        ts_headline('english', e.question_text, {search_func}('english', %(query)s)) as question_headline,
        ts_headline('english', e.answer_text, {search_func}('english', %(query)s)) as answer_headline
    FROM feedme_examples_v2 e
    WHERE e.search_text @@ {search_func}('english', %(query)s)
      AND {where_clause}
    ORDER BY {rank_expr} DESC
    LIMIT %(limit)s
    """
    
    # Stop words for query optimization and performance analysis
    STOP_WORDS = {
        'the', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for', 'of', 'with', 'by', 
        'is', 'are', 'was', 'were', 'this', 'that', 'they', 'have', 'will', 'your', 
        'what', 'when', 'from'
    }
    
    def __init__(self):
        self.connection_manager = get_connection_manager()
    
    def search(
        self,
        query: str,
        limit: int = 10,
        enable_stemming: bool = False,
        filters: Optional[Dict[str, Any]] = None,
        boost_recent: bool = True
    ) -> List[Dict[str, Any]]:
        """
        Perform full-text search
        
        Args:
            query: Search query text
            limit: Maximum number of results
            enable_stemming: Enable stemming for query expansion
            filters: Additional filters to apply
            boost_recent: Boost more recent examples in ranking
            
        Returns:
            List of search results with text scores
        """
        if not query or len(query.strip()) < 2:
            raise ValueError("Query must be at least 2 characters long")
        
        # Clean and prepare query
        clean_query = self._clean_query(query)
        
        # Build filter conditions
        filter_conditions = ["e.is_active = true"]
        params = {
            'query': clean_query,
            'limit': limit
        }
        
        if filters:
            if 'issue_category' in filters:
                filter_conditions.append("e.issue_category = %(issue_category)s")
                params['issue_category'] = filters['issue_category']
            
            if 'min_confidence' in filters:
                filter_conditions.append("e.confidence_score >= %(min_confidence)s")
                params['min_confidence'] = filters['min_confidence']
                
            if 'created_after' in filters:
                filter_conditions.append("e.created_at >= %(created_after)s")
                params['created_after'] = filters['created_after']
        
        where_clause = " AND ".join(filter_conditions)
        
        # Choose search function based on stemming
        search_func = "to_tsquery" if enable_stemming else "plainto_tsquery"
        
        # Build ranking expression
        rank_expr = f"ts_rank(e.search_text, {search_func}('english', %(query)s))"
        
        if boost_recent:
            # Boost recent examples (within last 30 days get 1.2x boost)
            rank_expr = f"""
            {rank_expr} * 
            CASE 
                WHEN e.created_at >= NOW() - INTERVAL '30 days' THEN 1.2
                WHEN e.created_at >= NOW() - INTERVAL '90 days' THEN 1.1
                ELSE 1.0
            END
            """
        
        sql = self.SEARCH_QUERY_TEMPLATE.format(
            rank_expr=rank_expr,
            search_func=search_func,
            where_clause=where_clause
        )
        
        try:
            start_time = time.time()
            
            with self.connection_manager.get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(sql, params)
                    results = cur.fetchall()
            
            search_time = time.time() - start_time
            
            processed_results = []
            for row in results:
                result = dict(row)
                
                # Convert arrays to lists
                if result.get('tags'):
                    result['tags'] = list(result['tags'])
                
                # Add search metadata
                result['search_type'] = 'text'
                result['search_time_ms'] = int(search_time * 1000)
                result['query_terms'] = self._extract_query_terms(clean_query)
                
                processed_results.append(result)
            
            logger.debug(f"Text search found {len(processed_results)} results in {search_time:.3f}s")
            return processed_results
            
        except Exception as e:
            logger.error(f"Error in text search: {e}")
            raise

    def search_with_suggestions(
        self,
        query: str,
        limit: int = 10,
        suggestion_limit: int = 5
    ) -> Dict[str, Any]:
        """
        Search with query suggestions for no/low results
        
        Args:
            query: Search query
            limit: Maximum results
            suggestion_limit: Maximum suggestions
            
        Returns:
            Dict with results and suggestions
        """
        # Perform initial search
        results = self.search(query, limit=limit)
        
        response = {
            'results': results,
            'suggestions': [],
            'original_query': query
        }
        
        # If few results, provide suggestions
        if len(results) < 3:
            suggestions = self._generate_suggestions(query, suggestion_limit)
            response['suggestions'] = suggestions
        
        return response

    def _clean_query(self, query: str) -> str:
        """Clean and normalize search query"""
        # Remove special characters that could break tsquery
        cleaned = re.sub(r'[^\w\s\-]', ' ', query)
        
        # Normalize whitespace
        cleaned = re.sub(r'\s+', ' ', cleaned).strip()
        
        # Ensure minimum length
        if len(cleaned) < 2:
            raise ValueError("Query too short after cleaning")
        
        return cleaned

    def _extract_query_terms(self, query: str) -> List[str]:
        """Extract individual terms from query"""
        return [term.strip() for term in query.split() if len(term.strip()) > 1]

    def _generate_suggestions(self, query: str, limit: int) -> List[str]:
        """Generate query suggestions based on existing content"""
        
        # Format stop words for SQL query
        stop_words_formatted = "'" + "', '".join(self.STOP_WORDS) + "'"
        
        # Get common terms from the database
        sql = f"""
        SELECT word, nentry as frequency
        FROM ts_stat('SELECT search_text FROM feedme_examples_v2 WHERE is_active = true')
        WHERE char_length(word) > 3
          AND word NOT IN ({stop_words_formatted})
        ORDER BY nentry DESC
        LIMIT 50
        """
        
        try:
            with self.connection_manager.get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(sql)
                    common_terms = cur.fetchall()
            
            # Simple suggestion logic - find terms similar to query words
            query_words = set(query.lower().split())
            suggestions = []
            
            for term_row in common_terms:
                term = term_row['word']
                
                # Check if term is similar to any query word
                for query_word in query_words:
                    if (query_word in term or term in query_word) and term not in query_words:
                        suggestions.append(term)
                        break
                
                if len(suggestions) >= limit:
                    break
            
            return suggestions
            
        except Exception as e:
            logger.error(f"Error generating suggestions: {e}")
            return []

    def get_popular_queries(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Get popular search terms from usage patterns"""
        
        sql = """
        SELECT 
            issue_category,
            COUNT(*) as category_count,
            array_agg(DISTINCT tags[1:3]) as common_tags
        FROM feedme_examples_v2
        WHERE is_active = true
          AND usage_count > 0
        GROUP BY issue_category
        ORDER BY category_count DESC
        LIMIT %(limit)s
        """
        
        try:
            with self.connection_manager.get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(sql, {'limit': limit})
                    results = cur.fetchall()
            
            return [dict(row) for row in results]
            
        except Exception as e:
            logger.error(f"Error getting popular queries: {e}")
            return []

    def analyze_query_performance(self, query: str) -> Dict[str, Any]:
        """Analyze query performance and suggest optimizations"""
        
        # Check if query has stop words that might reduce performance
        
        query_words = set(query.lower().split())
        stop_word_count = len(query_words.intersection(self.STOP_WORDS))
        
        analysis = {
            'query': query,
            'word_count': len(query_words),
            'stop_word_count': stop_word_count,
            'stop_word_ratio': stop_word_count / len(query_words) if query_words else 0,
            'estimated_selectivity': 'high' if len(query_words) > 3 else 'low',
            'recommendations': []
        }
        
        # Add recommendations
        if analysis['stop_word_ratio'] > 0.5:
            analysis['recommendations'].append("Consider removing common words for better performance")
        
        if len(query_words) < 2:
            analysis['recommendations'].append("Add more specific terms for better results")
        
        if len(query) > 100:
            analysis['recommendations'].append("Consider shortening query for better performance")
        
        return analysis

    def search_categories(self, limit: int = 20) -> List[Dict[str, Any]]:
        """Get available search categories"""
        
        sql = """
        WITH tag_unnested AS (
            SELECT 
                issue_category,
                confidence_score,
                unnest(tags) as individual_tag
            FROM feedme_examples_v2
            WHERE is_active = true
              AND issue_category IS NOT NULL
              AND tags IS NOT NULL
        )
        SELECT 
            issue_category,
            COUNT(DISTINCT individual_tag) as example_count,
            AVG(confidence_score) as avg_confidence,
            array_agg(DISTINCT individual_tag ORDER BY individual_tag)[1:5] as sample_tags
        FROM tag_unnested
        GROUP BY issue_category
        HAVING COUNT(DISTINCT individual_tag) >= 3  -- Only categories with meaningful content
        ORDER BY example_count DESC
        LIMIT %(limit)s
        """
        
        try:
            with self.connection_manager.get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(sql, {'limit': limit})
                    results = cur.fetchall()
            
            processed_results = []
            for row in results:
                result = dict(row)
                if result.get('sample_tags'):
                    # Flatten nested arrays and remove nulls
                    flattened_tags = []
                    for tag_group in result['sample_tags']:
                        if tag_group:
                            flattened_tags.extend([tag for tag in tag_group if tag])
                    result['sample_tags'] = list(set(flattened_tags))[:5]  # Unique tags, max 5
                processed_results.append(result)
            
            return processed_results
            
        except Exception as e:
            logger.error(f"Error getting search categories: {e}")
            return []