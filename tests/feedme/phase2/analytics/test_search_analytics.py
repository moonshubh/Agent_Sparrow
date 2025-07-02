"""
Comprehensive tests for FeedMe Search Analytics System
Tests search behavior analysis, query patterns, and search optimization.
"""

import pytest
import asyncio
from datetime import datetime, timedelta
from unittest.mock import Mock, AsyncMock, patch
from typing import Dict, List, Any
import json
from collections import Counter

# Import the modules we'll implement
from app.feedme.analytics.search_analytics import (
    SearchAnalyzer,
    QueryPatternAnalyzer,
    SearchOptimizer
)
from app.feedme.analytics.schemas import (
    SearchBehaviorMetrics,
    QueryPattern,
    SearchSession,
    OptimizationInsight
)


class TestSearchAnalyzer:
    """Test suite for search behavior analysis"""
    
    @pytest.fixture
    def mock_db(self):
        """Mock database connection"""
        db = AsyncMock()
        return db
    
    @pytest.fixture
    def mock_redis(self):
        """Mock Redis client for search analytics"""
        redis = AsyncMock()
        return redis
    
    @pytest.fixture
    def search_analyzer(self, mock_db, mock_redis):
        """Create SearchAnalyzer instance with mocked dependencies"""
        return SearchAnalyzer(
            db=mock_db,
            redis=mock_redis,
            config={
                'session_timeout_minutes': 30,
                'min_pattern_frequency': 5,
                'semantic_similarity_threshold': 0.8
            }
        )
    
    @pytest.fixture
    def sample_search_sessions(self):
        """Sample search sessions for testing"""
        base_time = datetime.utcnow()
        return [
            SearchSession(
                session_id="session_1",
                user_id="user_1",
                start_time=base_time,
                end_time=base_time + timedelta(minutes=15),
                searches=[
                    {
                        'query': 'email sync issues',
                        'timestamp': base_time,
                        'results_count': 5,
                        'clicked_results': [1, 3],
                        'search_type': 'hybrid'
                    },
                    {
                        'query': 'email not syncing',
                        'timestamp': base_time + timedelta(minutes=2),
                        'results_count': 8,
                        'clicked_results': [1],
                        'search_type': 'vector'
                    }
                ],
                success_rate=0.8,
                avg_response_time=250.0
            ),
            SearchSession(
                session_id="session_2",
                user_id="user_2",
                start_time=base_time + timedelta(hours=1),
                end_time=base_time + timedelta(hours=1, minutes=20),
                searches=[
                    {
                        'query': 'account setup guide',
                        'timestamp': base_time + timedelta(hours=1),
                        'results_count': 12,
                        'clicked_results': [1, 2, 5],
                        'search_type': 'text'
                    }
                ],
                success_rate=1.0,
                avg_response_time=180.0
            )
        ]
    
    @pytest.mark.asyncio
    async def test_analyze_search_behavior(self, search_analyzer, sample_search_sessions, mock_db):
        """Test comprehensive search behavior analysis"""
        # Arrange
        mock_db.fetch_all.return_value = [
            {
                'session_id': 'session_1',
                'user_id': 'user_1',
                'query_count': 2,
                'success_rate': 0.8,
                'avg_response_time': 250.0,
                'session_duration': 15,
                'search_types': ['hybrid', 'vector']
            },
            {
                'session_id': 'session_2',
                'user_id': 'user_2',
                'query_count': 1,
                'success_rate': 1.0,
                'avg_response_time': 180.0,
                'session_duration': 20,
                'search_types': ['text']
            }
        ]
        
        # Act
        behavior_metrics = await search_analyzer.analyze_search_behavior(
            time_period_days=7
        )
        
        # Assert
        assert isinstance(behavior_metrics, SearchBehaviorMetrics)
        assert behavior_metrics.total_sessions == 2
        assert behavior_metrics.avg_session_duration_minutes >= 15
        assert behavior_metrics.avg_queries_per_session >= 1.0
        assert 0.0 <= behavior_metrics.overall_success_rate <= 1.0
        
        # Verify database query was executed
        mock_db.fetch_all.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_query_refinement_analysis(self, search_analyzer, mock_db):
        """Test analysis of query refinement patterns"""
        # Arrange
        mock_db.fetch_all.return_value = [
            {
                'original_query': 'email sync',
                'refined_query': 'email sync issues',
                'refinement_type': 'expansion',
                'improvement_score': 0.3,
                'frequency': 15
            },
            {
                'original_query': 'setup account mailbird',
                'refined_query': 'account setup',
                'refinement_type': 'simplification',
                'improvement_score': 0.5,
                'frequency': 8
            }
        ]
        
        # Act
        refinement_patterns = await search_analyzer.analyze_query_refinements()
        
        # Assert
        assert len(refinement_patterns) == 2
        assert refinement_patterns[0]['refinement_type'] == 'expansion'
        assert refinement_patterns[0]['improvement_score'] == 0.3
        assert refinement_patterns[1]['refinement_type'] == 'simplification'
        assert refinement_patterns[1]['frequency'] == 8
    
    @pytest.mark.asyncio
    async def test_search_result_click_analysis(self, search_analyzer, mock_db):
        """Test analysis of search result click patterns"""
        # Arrange
        mock_db.fetch_all.return_value = [
            {
                'result_position': 1,
                'click_count': 150,
                'total_impressions': 200,
                'click_through_rate': 0.75
            },
            {
                'result_position': 2,
                'click_count': 80,
                'total_impressions': 200,
                'click_through_rate': 0.40
            },
            {
                'result_position': 3,
                'click_count': 40,
                'total_impressions': 200,
                'click_through_rate': 0.20
            }
        ]
        
        # Act
        click_patterns = await search_analyzer.analyze_click_patterns()
        
        # Assert
        assert len(click_patterns) == 3
        assert click_patterns[0]['result_position'] == 1
        assert click_patterns[0]['click_through_rate'] == 0.75
        
        # Verify descending click-through rate by position
        ctr_values = [p['click_through_rate'] for p in click_patterns]
        assert ctr_values == sorted(ctr_values, reverse=True)
    
    @pytest.mark.asyncio
    async def test_search_type_effectiveness_analysis(self, search_analyzer, mock_db):
        """Test analysis of different search type effectiveness"""
        # Arrange
        mock_db.fetch_all.return_value = [
            {
                'search_type': 'hybrid',
                'avg_response_time': 300.0,
                'avg_results_count': 6.8,
                'success_rate': 0.85,
                'usage_count': 500
            },
            {
                'search_type': 'vector',
                'avg_response_time': 450.0,
                'avg_results_count': 5.2,
                'success_rate': 0.78,
                'usage_count': 300
            },
            {
                'search_type': 'text',
                'avg_response_time': 150.0,
                'avg_results_count': 8.5,
                'success_rate': 0.72,
                'usage_count': 200
            }
        ]
        
        # Act
        effectiveness_analysis = await search_analyzer.analyze_search_type_effectiveness()
        
        # Assert
        assert len(effectiveness_analysis) == 3
        
        # Find the most effective search type overall
        hybrid_data = next(d for d in effectiveness_analysis if d['search_type'] == 'hybrid')
        assert hybrid_data['success_rate'] == 0.85  # Highest success rate
        
        # Find the fastest search type
        text_data = next(d for d in effectiveness_analysis if d['search_type'] == 'text')
        assert text_data['avg_response_time'] == 150.0  # Fastest
    
    @pytest.mark.asyncio
    async def test_user_search_segmentation(self, search_analyzer, mock_db):
        """Test user segmentation based on search behavior"""
        # Arrange
        mock_db.fetch_all.return_value = [
            {
                'user_id': 'power_user_1',
                'total_searches': 100,
                'avg_session_length': 25.5,
                'preferred_search_type': 'hybrid',
                'success_rate': 0.9,
                'segment': 'expert'
            },
            {
                'user_id': 'casual_user_1',
                'total_searches': 15,
                'avg_session_length': 5.2,
                'preferred_search_type': 'text',
                'success_rate': 0.65,
                'segment': 'beginner'
            },
            {
                'user_id': 'regular_user_1',
                'total_searches': 45,
                'avg_session_length': 12.8,
                'preferred_search_type': 'vector',
                'success_rate': 0.8,
                'segment': 'intermediate'
            }
        ]
        
        # Act
        user_segments = await search_analyzer.segment_users_by_behavior()
        
        # Assert
        assert len(user_segments) == 3
        
        # Verify segment characteristics
        expert_users = [u for u in user_segments if u['segment'] == 'expert']
        beginner_users = [u for u in user_segments if u['segment'] == 'beginner']
        
        assert len(expert_users) == 1
        assert expert_users[0]['total_searches'] == 100
        assert expert_users[0]['success_rate'] == 0.9
        
        assert len(beginner_users) == 1
        assert beginner_users[0]['total_searches'] == 15
        assert beginner_users[0]['success_rate'] == 0.65
    
    @pytest.mark.asyncio
    async def test_seasonal_search_pattern_detection(self, search_analyzer, mock_db):
        """Test detection of seasonal and temporal search patterns"""
        # Arrange
        # Mock data showing different patterns by time of day/week
        mock_db.fetch_all.return_value = [
            {
                'hour': 9,
                'day_of_week': 1,  # Monday
                'search_volume': 45,
                'avg_success_rate': 0.8
            },
            {
                'hour': 14,
                'day_of_week': 1,  # Monday
                'search_volume': 60,
                'avg_success_rate': 0.85
            },
            {
                'hour': 10,
                'day_of_week': 6,  # Saturday
                'search_volume': 15,
                'avg_success_rate': 0.7
            }
        ]
        
        # Act
        temporal_patterns = await search_analyzer.detect_temporal_patterns()
        
        # Assert
        assert len(temporal_patterns) == 3
        
        # Verify peak hours identification
        peak_pattern = max(temporal_patterns, key=lambda x: x['search_volume'])
        assert peak_pattern['hour'] == 14
        assert peak_pattern['search_volume'] == 60
    
    @pytest.mark.asyncio
    async def test_no_results_query_analysis(self, search_analyzer, mock_db):
        """Test analysis of queries that return no results"""
        # Arrange
        mock_db.fetch_all.return_value = [
            {
                'query': 'mailbird mobile app',
                'frequency': 25,
                'last_searched': datetime.utcnow() - timedelta(days=1),
                'query_length': 3,
                'contains_typos': False
            },
            {
                'query': 'emial synchronization',  # Typo
                'frequency': 8,
                'last_searched': datetime.utcnow() - timedelta(days=2),
                'query_length': 2,
                'contains_typos': True
            },
            {
                'query': 'very specific obscure feature request',
                'frequency': 2,
                'last_searched': datetime.utcnow() - timedelta(days=5),
                'query_length': 6,
                'contains_typos': False
            }
        ]
        
        # Act
        no_results_analysis = await search_analyzer.analyze_no_results_queries()
        
        # Assert
        assert len(no_results_analysis) == 3
        
        # Verify high-frequency no-results queries are identified
        high_freq_query = next(q for q in no_results_analysis if q['frequency'] == 25)
        assert high_freq_query['query'] == 'mailbird mobile app'
        
        # Verify typo detection
        typo_query = next(q for q in no_results_analysis if q['contains_typos'])
        assert typo_query['query'] == 'emial synchronization'


class TestQueryPatternAnalyzer:
    """Test suite for query pattern analysis and clustering"""
    
    @pytest.fixture
    def pattern_analyzer(self):
        """Create QueryPatternAnalyzer instance"""
        return QueryPatternAnalyzer(
            similarity_threshold=0.8,
            min_cluster_size=3,
            max_clusters=20
        )
    
    @pytest.fixture
    def sample_queries(self):
        """Sample queries for pattern analysis"""
        return [
            "email sync issues",
            "email synchronization problems",
            "sync not working",
            "emails not syncing",
            "account setup guide",
            "how to setup account",
            "setting up new account",
            "mailbird installation",
            "install mailbird windows",
            "installation guide"
        ]
    
    @pytest.mark.asyncio
    async def test_query_clustering(self, pattern_analyzer, sample_queries):
        """Test clustering of similar queries"""
        # Act
        clusters = await pattern_analyzer.cluster_queries(sample_queries)
        
        # Assert
        assert len(clusters) >= 2  # Should identify distinct clusters
        
        # Verify sync-related queries are clustered together
        sync_cluster = None
        setup_cluster = None
        
        for cluster in clusters:
            cluster_queries = [q.lower() for q in cluster['queries']]
            if any('sync' in q for q in cluster_queries):
                sync_cluster = cluster
            elif any('setup' in q or 'account' in q for q in cluster_queries):
                setup_cluster = cluster
        
        assert sync_cluster is not None
        assert setup_cluster is not None
        assert len(sync_cluster['queries']) >= 3
        assert len(setup_cluster['queries']) >= 2
    
    @pytest.mark.asyncio
    async def test_semantic_similarity_calculation(self, pattern_analyzer):
        """Test semantic similarity calculation between queries"""
        # Arrange
        query1 = "email sync problems"
        query2 = "email synchronization issues"
        query3 = "account setup guide"
        
        # Act
        similarity_1_2 = await pattern_analyzer.calculate_semantic_similarity(query1, query2)
        similarity_1_3 = await pattern_analyzer.calculate_semantic_similarity(query1, query3)
        
        # Assert
        assert 0.0 <= similarity_1_2 <= 1.0
        assert 0.0 <= similarity_1_3 <= 1.0
        assert similarity_1_2 > similarity_1_3  # More similar queries should have higher score
        assert similarity_1_2 >= 0.8  # Should be highly similar
    
    @pytest.mark.asyncio
    async def test_intent_classification(self, pattern_analyzer):
        """Test classification of query intent"""
        # Arrange
        test_queries = [
            "how to setup email account",  # Setup intent
            "email not syncing fix",       # Troubleshooting intent
            "mailbird features list",      # Information intent
            "cancel subscription",         # Account management intent
            "install mailbird mac"         # Installation intent
        ]
        
        # Act
        classified_queries = []
        for query in test_queries:
            intent = await pattern_analyzer.classify_query_intent(query)
            classified_queries.append({'query': query, 'intent': intent})
        
        # Assert
        assert len(classified_queries) == 5
        
        # Verify specific intent classifications
        intents = [cq['intent'] for cq in classified_queries]
        assert 'setup' in intents
        assert 'troubleshooting' in intents
        assert 'information' in intents
    
    @pytest.mark.asyncio
    async def test_query_complexity_analysis(self, pattern_analyzer):
        """Test analysis of query complexity levels"""
        # Arrange
        test_queries = [
            "help",  # Simple
            "email sync",  # Medium
            "configure IMAP settings for Gmail with OAuth",  # Complex
            "troubleshoot email synchronization issues with Exchange server authentication"  # Very complex
        ]
        
        # Act
        complexity_scores = []
        for query in test_queries:
            complexity = await pattern_analyzer.analyze_query_complexity(query)
            complexity_scores.append({'query': query, 'complexity': complexity})
        
        # Assert
        assert len(complexity_scores) == 4
        
        # Verify complexity ordering
        complexities = [cs['complexity']['score'] for cs in complexity_scores]
        assert complexities[0] < complexities[1] < complexities[2] < complexities[3]
        
        # Verify complexity levels
        assert complexity_scores[0]['complexity']['level'] == 'simple'
        assert complexity_scores[3]['complexity']['level'] == 'complex'
    
    @pytest.mark.asyncio
    async def test_trending_query_detection(self, pattern_analyzer, mock_db):
        """Test detection of trending queries"""
        # This would require mocking database or time-series data
        # to test trend detection algorithms
        pass
    
    @pytest.mark.asyncio
    async def test_query_expansion_suggestions(self, pattern_analyzer):
        """Test query expansion suggestions"""
        # Arrange
        short_query = "sync"
        
        # Act
        expansions = await pattern_analyzer.suggest_query_expansions(short_query)
        
        # Assert
        assert len(expansions) > 0
        assert all(short_query in expansion['expanded_query'] for expansion in expansions)
        assert all('relevance_score' in expansion for expansion in expansions)
        
        # Verify expansions are relevant
        relevant_expansions = [e for e in expansions if e['relevance_score'] > 0.7]
        assert len(relevant_expansions) > 0


class TestSearchOptimizer:
    """Test suite for search optimization recommendations"""
    
    @pytest.fixture
    def search_optimizer(self):
        """Create SearchOptimizer instance"""
        return SearchOptimizer(
            optimization_threshold=0.7,
            min_sample_size=50
        )
    
    @pytest.mark.asyncio
    async def test_search_ranking_optimization(self, search_optimizer, mock_db):
        """Test search result ranking optimization analysis"""
        # Arrange
        mock_db.fetch_all.return_value = [
            {
                'query': 'email sync',
                'result_id': 'result_1',
                'current_position': 3,
                'click_count': 25,
                'relevance_score': 0.9,
                'suggested_position': 1
            },
            {
                'query': 'email sync',
                'result_id': 'result_2',
                'current_position': 1,
                'click_count': 10,
                'relevance_score': 0.7,
                'suggested_position': 2
            }
        ]
        
        # Act
        ranking_optimizations = await search_optimizer.analyze_ranking_opportunities(
            query="email sync"
        )
        
        # Assert
        assert len(ranking_optimizations) > 0
        
        # Verify optimization suggestions
        high_impact_opt = next(
            opt for opt in ranking_optimizations 
            if opt['result_id'] == 'result_1'
        )
        assert high_impact_opt['current_position'] == 3
        assert high_impact_opt['suggested_position'] == 1
        assert high_impact_opt['impact_score'] > 0.5
    
    @pytest.mark.asyncio
    async def test_search_algorithm_recommendations(self, search_optimizer):
        """Test recommendations for search algorithm improvements"""
        # Arrange
        performance_data = {
            'hybrid_search': {
                'avg_response_time': 300,
                'success_rate': 0.85,
                'user_satisfaction': 0.8
            },
            'vector_search': {
                'avg_response_time': 450,
                'success_rate': 0.78,
                'user_satisfaction': 0.75
            },
            'text_search': {
                'avg_response_time': 150,
                'success_rate': 0.72,
                'user_satisfaction': 0.7
            }
        }
        
        # Act
        algorithm_recommendations = await search_optimizer.recommend_algorithm_improvements(
            performance_data
        )
        
        # Assert
        assert len(algorithm_recommendations) > 0
        
        # Should recommend optimizing slower algorithms
        vector_opt = next(
            (rec for rec in algorithm_recommendations 
             if 'vector' in rec['description'].lower()), 
            None
        )
        assert vector_opt is not None
        assert vector_opt['priority'] in ['high', 'medium']
    
    @pytest.mark.asyncio
    async def test_caching_strategy_optimization(self, search_optimizer, mock_redis):
        """Test caching strategy optimization recommendations"""
        # Arrange
        mock_redis.get.side_effect = [
            '0.65',  # Current cache hit rate
            '250',   # Average cached response time
            '400'    # Average uncached response time
        ]
        
        # Act
        caching_recommendations = await search_optimizer.optimize_caching_strategy()
        
        # Assert
        assert len(caching_recommendations) > 0
        
        # Should identify improvement opportunities
        cache_improvement = next(
            rec for rec in caching_recommendations 
            if rec['type'] == 'cache_optimization'
        )
        assert cache_improvement['current_hit_rate'] == 0.65
        assert cache_improvement['target_hit_rate'] > 0.65
    
    @pytest.mark.asyncio
    async def test_query_suggestion_optimization(self, search_optimizer):
        """Test optimization of query suggestions"""
        # Arrange
        suggestion_data = [
            {
                'original_query': 'emial',  # Typo
                'suggestion': 'email',
                'acceptance_rate': 0.9,
                'improvement_score': 0.8
            },
            {
                'original_query': 'sync',
                'suggestion': 'email sync issues',
                'acceptance_rate': 0.6,
                'improvement_score': 0.4
            }
        ]
        
        # Act
        suggestion_optimizations = await search_optimizer.optimize_query_suggestions(
            suggestion_data
        )
        
        # Assert
        assert len(suggestion_optimizations) == 2
        
        # Verify high-performing suggestions are identified
        typo_suggestion = next(
            opt for opt in suggestion_optimizations 
            if opt['original_query'] == 'emial'
        )
        assert typo_suggestion['acceptance_rate'] == 0.9
        assert typo_suggestion['recommendation'] == 'keep_current'
        
        # Verify low-performing suggestions get improvement recommendations
        low_perf_suggestion = next(
            opt for opt in suggestion_optimizations 
            if opt['acceptance_rate'] < 0.7
        )
        assert low_perf_suggestion['recommendation'] in ['improve', 'replace']


class TestSearchAnalyticsIntegration:
    """Integration tests for search analytics system"""
    
    @pytest.mark.asyncio
    async def test_comprehensive_search_analysis_pipeline(self):
        """Test complete search analysis pipeline"""
        # This would test the end-to-end flow from raw search data
        # to actionable insights in an integration environment
        pass
    
    @pytest.mark.asyncio
    async def test_real_time_search_analytics_updates(self):
        """Test real-time updates of search analytics"""
        # This would test WebSocket or streaming updates
        # of search analytics data
        pass
    
    @pytest.mark.asyncio
    async def test_search_analytics_dashboard_integration(self):
        """Test integration with search analytics dashboard"""
        # This would test dashboard data feeds and visualizations
        pass


if __name__ == "__main__":
    pytest.main([__file__, "-v"])