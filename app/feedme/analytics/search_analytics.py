"""
Search Analytics for FeedMe v2.0 Phase 2
Search behavior analysis, query patterns, and search optimization.
"""

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Tuple
from collections import defaultdict, Counter
import re

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.cluster import DBSCAN

from .schemas import (
    SearchBehaviorMetrics, QueryPattern, SearchAnalytics,
    UserBehaviorAnalytics, SearchType, OptimizationRecommendation
)

logger = logging.getLogger(__name__)


class SearchAnalyzer:
    """
    Comprehensive search behavior analysis system with pattern recognition,
    user segmentation, and optimization recommendations.
    """
    
    def __init__(
        self,
        db: AsyncSession,
        redis_client,
        config: Optional[Dict[str, Any]] = None
    ):
        self.db = db
        self.redis = redis_client
        self.config = config or {
            'session_timeout_minutes': 30,
            'min_pattern_frequency': 5,
            'semantic_similarity_threshold': 0.8
        }
        
        # Query pattern analysis
        self._query_clusters = {}
        self._pattern_cache = {}
        
        # User behavior tracking
        self._user_sessions = defaultdict(list)
        self._user_segments = {}
    
    async def analyze_search_behavior(
        self, 
        time_period_days: int = 7
    ) -> SearchBehaviorMetrics:
        """Analyze comprehensive search behavior patterns"""
        try:
            start_date = datetime.utcnow() - timedelta(days=time_period_days)
            
            # Get session-level metrics
            session_query = text("""
                WITH search_sessions AS (
                    SELECT 
                        user_id,
                        DATE_TRUNC('hour', timestamp) as session_hour,
                        COUNT(*) as queries_in_session,
                        AVG(response_time_ms) as avg_response_time,
                        AVG(CASE WHEN results_count > 0 THEN 1.0 ELSE 0.0 END) as success_rate,
                        MIN(timestamp) as session_start,
                        MAX(timestamp) as session_end
                    FROM feedme_search_events 
                    WHERE timestamp >= :start_date
                    GROUP BY user_id, DATE_TRUNC('hour', timestamp)
                )
                SELECT 
                    COUNT(*) as total_sessions,
                    AVG(EXTRACT(EPOCH FROM (session_end - session_start))/60) as avg_session_duration_minutes,
                    AVG(queries_in_session) as avg_queries_per_session,
                    AVG(success_rate) as overall_success_rate
                FROM search_sessions
            """)
            
            result = await self.db.fetch_one(session_query, {'start_date': start_date})
            
            # Calculate query refinement rate
            refinement_rate = await self._calculate_query_refinement_rate(start_date)
            
            return SearchBehaviorMetrics(
                total_sessions=result['total_sessions'] or 0,
                avg_session_duration_minutes=float(result['avg_session_duration_minutes'] or 0),
                avg_queries_per_session=float(result['avg_queries_per_session'] or 0),
                overall_success_rate=float(result['overall_success_rate'] or 0),
                query_refinement_rate=refinement_rate,
                timestamp=datetime.utcnow()
            )
            
        except Exception as e:
            logger.error(f"Error analyzing search behavior: {e}")
            raise
    
    async def _calculate_query_refinement_rate(self, start_date: datetime) -> float:
        """Calculate the rate at which users refine their queries"""
        try:
            refinement_query = text("""
                WITH sequential_queries AS (
                    SELECT 
                        user_id,
                        query,
                        timestamp,
                        LAG(query) OVER (PARTITION BY user_id ORDER BY timestamp) as prev_query,
                        LAG(timestamp) OVER (PARTITION BY user_id ORDER BY timestamp) as prev_timestamp
                    FROM feedme_search_events 
                    WHERE timestamp >= :start_date
                ),
                refinements AS (
                    SELECT *
                    FROM sequential_queries
                    WHERE prev_query IS NOT NULL 
                        AND query != prev_query
                        AND EXTRACT(EPOCH FROM (timestamp - prev_timestamp)) < 300  -- Within 5 minutes
                )
                SELECT 
                    COUNT(DISTINCT user_id || '_' || DATE_TRUNC('hour', timestamp)) as refined_sessions,
                    COUNT(DISTINCT user_id || '_' || DATE_TRUNC('hour', prev_timestamp)) as total_sessions
                FROM refinements
            """)
            
            result = await self.db.fetch_one(refinement_query, {'start_date': start_date})
            
            if result and result['total_sessions'] and result['total_sessions'] > 0:
                return float(result['refined_sessions']) / float(result['total_sessions'])
            
            return 0.0
            
        except Exception as e:
            logger.error(f"Error calculating refinement rate: {e}")
            return 0.0
    
    async def analyze_query_refinements(self) -> List[Dict[str, Any]]:
        """Analyze query refinement patterns"""
        try:
            refinement_query = text("""
                WITH sequential_queries AS (
                    SELECT 
                        user_id,
                        query,
                        timestamp,
                        LAG(query) OVER (PARTITION BY user_id ORDER BY timestamp) as prev_query,
                        LAG(results_count) OVER (PARTITION BY user_id ORDER BY timestamp) as prev_results
                    FROM feedme_search_events 
                    WHERE timestamp >= NOW() - INTERVAL '7 days'
                ),
                refinement_pairs AS (
                    SELECT 
                        prev_query as original_query,
                        query as refined_query,
                        CASE 
                            WHEN LENGTH(query) > LENGTH(prev_query) THEN 'expansion'
                            WHEN LENGTH(query) < LENGTH(prev_query) THEN 'simplification'
                            ELSE 'modification'
                        END as refinement_type,
                        CASE 
                            WHEN prev_results = 0 AND results_count > 0 THEN 1.0
                            WHEN prev_results > 0 AND results_count > prev_results THEN 0.5
                            ELSE 0.0
                        END as improvement_score
                    FROM sequential_queries
                    WHERE prev_query IS NOT NULL 
                        AND query != prev_query
                        AND EXTRACT(EPOCH FROM (timestamp - LAG(timestamp) OVER (PARTITION BY user_id ORDER BY timestamp))) < 300
                )
                SELECT 
                    original_query,
                    refined_query,
                    refinement_type,
                    AVG(improvement_score) as improvement_score,
                    COUNT(*) as frequency
                FROM refinement_pairs
                GROUP BY original_query, refined_query, refinement_type
                HAVING COUNT(*) >= 2
                ORDER BY frequency DESC
                LIMIT 50
            """)
            
            results = await self.db.fetch_all(refinement_query)
            return [dict(result) for result in results]
            
        except Exception as e:
            logger.error(f"Error analyzing query refinements: {e}")
            return []
    
    async def analyze_click_patterns(self) -> List[Dict[str, Any]]:
        """Analyze search result click patterns"""
        try:
            click_query = text("""
                WITH click_analysis AS (
                    SELECT 
                        CASE 
                            WHEN array_length(clicked_results, 1) > 0 THEN 
                                UNNEST(clicked_results)
                            ELSE NULL 
                        END as clicked_position,
                        results_count
                    FROM feedme_search_events 
                    WHERE timestamp >= NOW() - INTERVAL '7 days'
                        AND results_count > 0
                ),
                position_stats AS (
                    SELECT 
                        clicked_position as result_position,
                        COUNT(*) as click_count,
                        COUNT(*) OVER () as total_searches_with_clicks
                    FROM click_analysis
                    WHERE clicked_position IS NOT NULL
                    GROUP BY clicked_position
                ),
                impression_stats AS (
                    SELECT 
                        generate_series(1, 10) as result_position,
                        COUNT(*) as total_impressions
                    FROM feedme_search_events 
                    WHERE timestamp >= NOW() - INTERVAL '7 days'
                        AND results_count >= generate_series(1, 10)
                    GROUP BY generate_series(1, 10)
                )
                SELECT 
                    p.result_position,
                    COALESCE(ps.click_count, 0) as click_count,
                    p.total_impressions,
                    CASE 
                        WHEN p.total_impressions > 0 THEN 
                            COALESCE(ps.click_count, 0)::FLOAT / p.total_impressions
                        ELSE 0.0 
                    END as click_through_rate
                FROM impression_stats p
                LEFT JOIN position_stats ps ON p.result_position = ps.result_position
                WHERE p.total_impressions > 0
                ORDER BY p.result_position
                LIMIT 10
            """)
            
            results = await self.db.fetch_all(click_query)
            return [dict(result) for result in results]
            
        except Exception as e:
            logger.error(f"Error analyzing click patterns: {e}")
            return []
    
    async def analyze_search_type_effectiveness(self) -> List[Dict[str, Any]]:
        """Analyze effectiveness of different search types"""
        try:
            effectiveness_query = text("""
                SELECT 
                    search_type,
                    AVG(response_time_ms) as avg_response_time,
                    AVG(results_count) as avg_results_count,
                    AVG(CASE WHEN results_count > 0 THEN 1.0 ELSE 0.0 END) as success_rate,
                    AVG(CASE WHEN array_length(clicked_results, 1) > 0 THEN 1.0 ELSE 0.0 END) as click_through_rate,
                    COUNT(*) as usage_count
                FROM feedme_search_events 
                WHERE timestamp >= NOW() - INTERVAL '7 days'
                GROUP BY search_type
                ORDER BY usage_count DESC
            """)
            
            results = await self.db.fetch_all(effectiveness_query)
            return [dict(result) for result in results]
            
        except Exception as e:
            logger.error(f"Error analyzing search type effectiveness: {e}")
            return []
    
    async def segment_users_by_behavior(self) -> List[Dict[str, Any]]:
        """Segment users based on search behavior patterns"""
        try:
            segmentation_query = text("""
                WITH user_behavior AS (
                    SELECT 
                        user_id,
                        COUNT(*) as total_searches,
                        AVG(EXTRACT(EPOCH FROM (
                            MAX(timestamp) OVER (PARTITION BY user_id, DATE_TRUNC('hour', timestamp)) - 
                            MIN(timestamp) OVER (PARTITION BY user_id, DATE_TRUNC('hour', timestamp))
                        ))/60) as avg_session_length,
                        MODE() WITHIN GROUP (ORDER BY search_type) as preferred_search_type,
                        AVG(CASE WHEN results_count > 0 THEN 1.0 ELSE 0.0 END) as success_rate,
                        COUNT(DISTINCT DATE(timestamp)) as active_days
                    FROM feedme_search_events 
                    WHERE timestamp >= NOW() - INTERVAL '30 days'
                    GROUP BY user_id
                    HAVING COUNT(*) >= 5
                ),
                user_segments AS (
                    SELECT 
                        *,
                        CASE 
                            WHEN total_searches >= 50 AND success_rate >= 0.8 THEN 'expert'
                            WHEN total_searches >= 20 AND success_rate >= 0.7 THEN 'intermediate'
                            ELSE 'beginner'
                        END as segment
                    FROM user_behavior
                )
                SELECT 
                    user_id,
                    total_searches,
                    avg_session_length,
                    preferred_search_type,
                    success_rate,
                    active_days,
                    segment
                FROM user_segments
                ORDER BY total_searches DESC
            """)
            
            results = await self.db.fetch_all(segmentation_query)
            return [dict(result) for result in results]
            
        except Exception as e:
            logger.error(f"Error segmenting users: {e}")
            return []
    
    async def detect_temporal_patterns(self) -> Dict[str, Any]:
        """Detect temporal patterns in search behavior"""
        try:
            temporal_query = text("""
                SELECT 
                    EXTRACT(hour FROM timestamp) as hour,
                    EXTRACT(dow FROM timestamp) as day_of_week,
                    COUNT(*) as search_count,
                    AVG(CASE WHEN results_count > 0 THEN 1.0 ELSE 0.0 END) as avg_success_rate,
                    AVG(response_time_ms) as avg_response_time
                FROM feedme_search_events 
                WHERE timestamp >= NOW() - INTERVAL '30 days'
                GROUP BY EXTRACT(hour FROM timestamp), EXTRACT(dow FROM timestamp)
                ORDER BY search_count DESC
            """)
            
            results = await self.db.fetch_all(temporal_query)
            
            # Process temporal patterns
            hourly_totals = defaultdict(int)
            daily_totals = defaultdict(int)
            
            for result in results:
                hourly_totals[int(result['hour'])] += result['search_count']
                daily_totals[int(result['day_of_week'])] += result['search_count']
            
            # Find peak times
            peak_hours = sorted(hourly_totals.items(), key=lambda x: x[1], reverse=True)[:3]
            peak_days = sorted(daily_totals.items(), key=lambda x: x[1], reverse=True)[:3]
            
            return {
                'peak_hours': [hour for hour, count in peak_hours],
                'peak_days': [day for day, count in peak_days],
                'hourly_distribution': dict(hourly_totals),
                'daily_distribution': dict(daily_totals),
                'detailed_patterns': [dict(result) for result in results]
            }
            
        except Exception as e:
            logger.error(f"Error detecting temporal patterns: {e}")
            return {}
    
    async def analyze_no_results_queries(self) -> List[Dict[str, Any]]:
        """Analyze queries that return no results"""
        try:
            no_results_query = text("""
                WITH no_results_analysis AS (
                    SELECT 
                        query,
                        COUNT(*) as frequency,
                        MAX(timestamp) as last_searched,
                        ARRAY_LENGTH(STRING_TO_ARRAY(query, ' '), 1) as query_length,
                        CASE 
                            WHEN query ~ '[0-9]' AND query ~ '[a-zA-Z]' THEN true
                            WHEN query ILIKE '%emial%' OR query ILIKE '%recieve%' THEN true
                            ELSE false
                        END as contains_typos
                    FROM feedme_search_events 
                    WHERE timestamp >= NOW() - INTERVAL '30 days'
                        AND results_count = 0
                    GROUP BY query
                    HAVING COUNT(*) >= 2
                )
                SELECT 
                    query,
                    frequency,
                    last_searched,
                    query_length,
                    contains_typos
                FROM no_results_analysis
                ORDER BY frequency DESC
                LIMIT 100
            """)
            
            results = await self.db.fetch_all(no_results_query)
            return [dict(result) for result in results]
            
        except Exception as e:
            logger.error(f"Error analyzing no results queries: {e}")
            return []


class QueryPatternAnalyzer:
    """Advanced query pattern analysis with clustering and semantic understanding"""
    
    def __init__(
        self,
        similarity_threshold: float = 0.8,
        min_cluster_size: int = 3,
        max_clusters: int = 20
    ):
        self.similarity_threshold = similarity_threshold
        self.min_cluster_size = min_cluster_size
        self.max_clusters = max_clusters
        
        # NLP components
        self.vectorizer = TfidfVectorizer(
            max_features=1000,
            stop_words='english',
            ngram_range=(1, 2)
        )
        
        # Intent classification keywords
        self.intent_keywords = {
            'setup': ['setup', 'configure', 'install', 'create', 'add'],
            'troubleshooting': ['error', 'problem', 'issue', 'fix', 'not working', 'failed'],
            'information': ['how to', 'what is', 'where', 'when', 'list', 'show'],
            'account': ['account', 'password', 'login', 'subscription', 'profile'],
            'installation': ['install', 'download', 'update', 'upgrade', 'version']
        }
    
    async def cluster_queries(self, queries: List[str]) -> List[Dict[str, Any]]:
        """Cluster similar queries using TF-IDF and DBSCAN"""
        try:
            if len(queries) < self.min_cluster_size:
                return []
            
            # Vectorize queries
            X = self.vectorizer.fit_transform(queries)
            
            # Cluster using DBSCAN
            clustering = DBSCAN(
                eps=1 - self.similarity_threshold,
                min_samples=self.min_cluster_size,
                metric='cosine'
            )
            
            cluster_labels = clustering.fit_predict(X.toarray())
            
            # Group queries by cluster
            clusters = defaultdict(list)
            for i, label in enumerate(cluster_labels):
                if label != -1:  # -1 indicates noise/outlier
                    clusters[label].append(queries[i])
            
            # Format cluster results
            cluster_results = []
            for cluster_id, cluster_queries in clusters.items():
                if len(cluster_queries) >= self.min_cluster_size:
                    # Find representative query (most central)
                    representative = self._find_representative_query(cluster_queries)
                    
                    cluster_results.append({
                        'cluster_id': int(cluster_id),
                        'queries': cluster_queries,
                        'representative_query': representative,
                        'size': len(cluster_queries),
                        'intent': await self.classify_query_intent(representative)
                    })
            
            return cluster_results[:self.max_clusters]
            
        except Exception as e:
            logger.error(f"Error clustering queries: {e}")
            return []
    
    def _find_representative_query(self, queries: List[str]) -> str:
        """Find the most representative query in a cluster"""
        if len(queries) == 1:
            return queries[0]
        
        # Simple heuristic: query with median length
        lengths = [(len(q), q) for q in queries]
        lengths.sort()
        median_idx = len(lengths) // 2
        return lengths[median_idx][1]
    
    async def calculate_semantic_similarity(self, query1: str, query2: str) -> float:
        """Calculate semantic similarity between two queries"""
        try:
            # Simple approach using TF-IDF vectors
            vectors = self.vectorizer.fit_transform([query1, query2])
            similarity = (vectors[0] * vectors[1].T).toarray()[0, 0]
            return float(similarity)
            
        except Exception as e:
            logger.error(f"Error calculating similarity: {e}")
            return 0.0
    
    async def classify_query_intent(self, query: str) -> str:
        """Classify the intent of a query"""
        query_lower = query.lower()
        
        # Count keyword matches for each intent
        intent_scores = {}
        for intent, keywords in self.intent_keywords.items():
            score = sum(1 for keyword in keywords if keyword in query_lower)
            if score > 0:
                intent_scores[intent] = score
        
        # Return the intent with highest score, or 'general' if no match
        if intent_scores:
            return max(intent_scores.items(), key=lambda x: x[1])[0]
        return 'general'
    
    async def analyze_query_complexity(self, query: str) -> Dict[str, Any]:
        """Analyze the complexity level of a query"""
        # Simple complexity metrics
        word_count = len(query.split())
        char_count = len(query)
        has_special_chars = bool(re.search(r'[^a-zA-Z0-9\s]', query))
        has_quotes = '"' in query or "'" in query
        
        # Calculate complexity score
        complexity_score = (
            word_count * 0.2 +
            char_count * 0.01 +
            (2 if has_special_chars else 0) +
            (1 if has_quotes else 0)
        )
        
        # Classify complexity level
        if complexity_score <= 2:
            level = 'simple'
        elif complexity_score <= 5:
            level = 'medium'
        else:
            level = 'complex'
        
        return {
            'score': complexity_score,
            'level': level,
            'metrics': {
                'word_count': word_count,
                'char_count': char_count,
                'has_special_chars': has_special_chars,
                'has_quotes': has_quotes
            }
        }
    
    async def suggest_query_expansions(self, query: str) -> List[Dict[str, Any]]:
        """Suggest query expansions for better search results"""
        query_lower = query.lower()
        
        # Common expansion patterns
        expansions = []
        
        # If query is very short, suggest more specific versions
        if len(query.split()) <= 2:
            base_expansions = [
                f"{query} setup",
                f"{query} troubleshooting", 
                f"{query} configuration",
                f"how to {query}",
                f"{query} not working"
            ]
            
            for expansion in base_expansions:
                expansions.append({
                    'expanded_query': expansion,
                    'relevance_score': 0.8,
                    'expansion_type': 'specificity'
                })
        
        # Add contextual expansions based on domain
        if 'email' in query_lower:
            expansions.extend([
                {
                    'expanded_query': f"{query} IMAP",
                    'relevance_score': 0.7,
                    'expansion_type': 'technical'
                },
                {
                    'expanded_query': f"{query} sync",
                    'relevance_score': 0.9,
                    'expansion_type': 'contextual'
                }
            ])
        
        return expansions[:5]  # Return top 5 suggestions


class SearchOptimizer:
    """Search optimization recommendations and improvements"""
    
    def __init__(
        self,
        optimization_threshold: float = 0.7,
        min_sample_size: int = 50
    ):
        self.optimization_threshold = optimization_threshold
        self.min_sample_size = min_sample_size
    
    async def analyze_ranking_opportunities(
        self,
        query: str,
        db: AsyncSession = None
    ) -> List[Dict[str, Any]]:
        """Analyze search result ranking optimization opportunities"""
        try:
            # Mock ranking analysis - in real implementation would analyze click data
            opportunities = [
                {
                    'result_id': 'result_1',
                    'current_position': 3,
                    'suggested_position': 1,
                    'click_count': 25,
                    'relevance_score': 0.9,
                    'impact_score': 0.8,
                    'reason': 'High click-through rate despite lower position'
                },
                {
                    'result_id': 'result_2', 
                    'current_position': 1,
                    'suggested_position': 2,
                    'click_count': 10,
                    'relevance_score': 0.7,
                    'impact_score': 0.3,
                    'reason': 'Lower engagement than expected for top position'
                }
            ]
            
            return opportunities
            
        except Exception as e:
            logger.error(f"Error analyzing ranking opportunities: {e}")
            return []
    
    async def recommend_algorithm_improvements(
        self,
        performance_data: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """Recommend search algorithm improvements"""
        recommendations = []
        
        for search_type, metrics in performance_data.items():
            if metrics['avg_response_time'] > 1000:  # Slow searches
                recommendations.append({
                    'type': 'performance_optimization',
                    'search_type': search_type,
                    'priority': 'high',
                    'description': f'Optimize {search_type} search performance',
                    'current_avg_time': metrics['avg_response_time'],
                    'target_improvement': '50% faster'
                })
            
            if metrics['success_rate'] < 0.8:  # Low success rate
                recommendations.append({
                    'type': 'relevance_improvement',
                    'search_type': search_type,
                    'priority': 'medium',
                    'description': f'Improve {search_type} search relevance',
                    'current_success_rate': metrics['success_rate'],
                    'target_improvement': '85% success rate'
                })
        
        return recommendations
    
    async def optimize_caching_strategy(self, redis_client=None) -> List[Dict[str, Any]]:
        """Optimize caching strategy based on usage patterns"""
        recommendations = []
        
        # Mock cache analysis - would use real Redis data
        current_hit_rate = 0.65
        target_hit_rate = 0.80
        
        if current_hit_rate < target_hit_rate:
            recommendations.append({
                'type': 'cache_optimization',
                'priority': 'medium',
                'description': 'Increase cache coverage for common queries',
                'current_hit_rate': current_hit_rate,
                'target_hit_rate': target_hit_rate,
                'expected_improvement': '20% faster response times'
            })
        
        return recommendations
    
    async def optimize_query_suggestions(
        self,
        suggestion_data: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Optimize query suggestions based on acceptance rates"""
        optimizations = []
        
        for suggestion in suggestion_data:
            if suggestion['acceptance_rate'] > 0.8:
                optimizations.append({
                    **suggestion,
                    'recommendation': 'keep_current',
                    'confidence': 'high'
                })
            elif suggestion['acceptance_rate'] < 0.5:
                optimizations.append({
                    **suggestion,
                    'recommendation': 'improve' if suggestion['acceptance_rate'] > 0.2 else 'replace',
                    'confidence': 'medium'
                })
            else:
                optimizations.append({
                    **suggestion,
                    'recommendation': 'monitor',
                    'confidence': 'medium'
                })
        
        return optimizations