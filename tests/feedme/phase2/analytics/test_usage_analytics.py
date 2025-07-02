"""
Comprehensive tests for FeedMe Usage Analytics System
Tests the core analytics engine with real-time metrics collection and event tracking.
"""

import pytest
import asyncio
from datetime import datetime, timedelta
from unittest.mock import Mock, AsyncMock, patch
from typing import Dict, List, Any
import json

# Import the modules we'll implement
from app.feedme.analytics.usage_tracker import UsageAnalytics, SearchEvent, AnalyticsInsights
from app.feedme.analytics.analytics_engine import AnalyticsEngine
from app.feedme.analytics.schemas import (
    UsageMetrics, 
    SearchAnalytics, 
    UserBehaviorAnalytics,
    SystemPerformanceMetrics
)


class TestUsageAnalytics:
    """Test suite for core usage analytics tracking"""
    
    @pytest.fixture
    def mock_db(self):
        """Mock database connection"""
        db = AsyncMock()
        return db
    
    @pytest.fixture
    def mock_redis(self):
        """Mock Redis client for real-time metrics"""
        redis = AsyncMock()
        redis.get.return_value = None
        redis.setex.return_value = True
        redis.incr.return_value = 1
        return redis
    
    @pytest.fixture
    def usage_analytics(self, mock_db, mock_redis):
        """Create UsageAnalytics instance with mocked dependencies"""
        return UsageAnalytics(
            db=mock_db,
            redis_client=mock_redis,
            enable_real_time=True
        )
    
    @pytest.fixture
    def sample_search_event(self):
        """Sample search event for testing"""
        return SearchEvent(
            user_id="test_user_123",
            query="email sync issues",
            timestamp=datetime.utcnow(),
            results_count=5,
            response_time_ms=250,
            clicked_results=[1, 3],
            conversation_id=456,
            search_type="hybrid",
            context_data={
                "agent_type": "primary",
                "session_id": "session_789"
            }
        )
    
    @pytest.mark.asyncio
    async def test_track_search_event(self, usage_analytics, sample_search_event, mock_redis):
        """Test search event tracking with metrics collection"""
        # Act
        await usage_analytics.track_search_event(sample_search_event)
        
        # Assert
        # Verify Redis metrics were updated
        mock_redis.incr.assert_called()
        mock_redis.setex.assert_called()
        
        # Verify event was stored for batch processing
        assert len(usage_analytics._event_buffer) == 1
        stored_event = usage_analytics._event_buffer[0]
        assert stored_event.user_id == "test_user_123"
        assert stored_event.query == "email sync issues"
    
    @pytest.mark.asyncio
    async def test_real_time_metrics_collection(self, usage_analytics, mock_redis):
        """Test real-time metrics collection and aggregation"""
        # Arrange
        events = [
            SearchEvent(
                user_id=f"user_{i}",
                query=f"test query {i}",
                timestamp=datetime.utcnow(),
                results_count=5,
                response_time_ms=100 + i * 50,
                clicked_results=[1],
                conversation_id=i,
                search_type="vector"
            )
            for i in range(5)
        ]
        
        # Act
        for event in events:
            await usage_analytics.track_search_event(event)
        
        # Assert
        # Verify multiple metrics were tracked
        assert mock_redis.incr.call_count >= 5  # At least one per event
        assert mock_redis.setex.call_count >= 5  # Timing metrics
        
        # Verify event buffer contains all events
        assert len(usage_analytics._event_buffer) == 5
    
    @pytest.mark.asyncio
    async def test_generate_usage_insights(self, usage_analytics, mock_db):
        """Test analytics insights generation from historical data"""
        # Arrange
        mock_db.fetch_all.return_value = [
            {
                'date': datetime.utcnow().date(),
                'total_searches': 100,
                'avg_response_time': 200.5,
                'click_through_rate': 0.75,
                'unique_users': 25
            }
        ]
        
        # Act
        insights = await usage_analytics.generate_insights(
            start_date=datetime.utcnow() - timedelta(days=7),
            end_date=datetime.utcnow()
        )
        
        # Assert
        assert isinstance(insights, AnalyticsInsights)
        assert insights.total_searches == 100
        assert insights.avg_response_time == 200.5
        assert insights.click_through_rate == 0.75
        assert insights.unique_users == 25
        
        # Verify database query was executed
        mock_db.fetch_one.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_batch_event_processing(self, usage_analytics, mock_db):
        """Test batch processing of accumulated events"""
        # Arrange
        events = [
            SearchEvent(
                user_id=f"user_{i}",
                query=f"query {i}",
                timestamp=datetime.utcnow(),
                results_count=3,
                response_time_ms=150,
                clicked_results=[1],
                conversation_id=i,
                search_type="text"
            )
            for i in range(10)
        ]
        
        # Add events to buffer
        for event in events:
            await usage_analytics.track_search_event(event)
        
        # Act
        await usage_analytics.flush_events_to_database()
        
        # Assert
        # Verify batch insert was called
        mock_db.execute_many.assert_called_once()
        call_args = mock_db.execute_many.call_args
        assert "INSERT INTO feedme_search_events" in call_args[0][0]
        assert len(call_args[0][1]) == 10  # All events processed
        
        # Verify buffer was cleared
        assert len(usage_analytics._event_buffer) == 0
    
    @pytest.mark.asyncio
    async def test_search_pattern_analysis(self, usage_analytics, mock_db):
        """Test search pattern analysis for user behavior insights"""
        # Arrange
        mock_db.fetch_all.return_value = [
            {
                'query': 'email sync',
                'frequency': 15,
                'avg_results': 4.2,
                'success_rate': 0.8
            },
            {
                'query': 'account setup',
                'frequency': 12,
                'avg_results': 3.8,
                'success_rate': 0.9
            }
        ]
        
        # Act
        patterns = await usage_analytics.analyze_search_patterns(
            time_window_hours=24
        )
        
        # Assert
        assert len(patterns) == 2
        assert patterns[0]['query'] == 'email sync'
        assert patterns[0]['frequency'] == 15
        assert patterns[1]['success_rate'] == 0.9
    
    @pytest.mark.asyncio
    async def test_performance_metrics_tracking(self, usage_analytics, mock_redis):
        """Test performance metrics tracking and alerting"""
        # Arrange
        slow_event = SearchEvent(
            user_id="user_test",
            query="slow query",
            timestamp=datetime.utcnow(),
            results_count=10,
            response_time_ms=5000,  # Slow response
            clicked_results=[],
            conversation_id=123,
            search_type="hybrid"
        )
        
        # Act
        await usage_analytics.track_search_event(slow_event)
        
        # Assert
        # Verify performance alert was triggered
        mock_redis.lpush.assert_called_with(
            "feedme:performance_alerts",
            json.dumps({
                "type": "slow_search",
                "response_time": 5000,
                "threshold": 2000,
                "timestamp": slow_event.timestamp.isoformat()
            })
        )
    
    @pytest.mark.asyncio
    async def test_user_behavior_analytics(self, usage_analytics, mock_db):
        """Test user behavior analytics and segmentation"""
        # Arrange
        mock_db.fetch_all.return_value = [
            {
                'user_id': 'user_1',
                'search_count': 50,
                'avg_session_length': 15.5,
                'preferred_search_type': 'hybrid',
                'success_rate': 0.85
            },
            {
                'user_id': 'user_2',
                'search_count': 25,
                'avg_session_length': 8.2,
                'preferred_search_type': 'text',
                'success_rate': 0.72
            }
        ]
        
        # Act
        behavior_analytics = await usage_analytics.analyze_user_behavior(
            time_period_days=30
        )
        
        # Assert
        assert isinstance(behavior_analytics, UserBehaviorAnalytics)
        assert len(behavior_analytics.user_segments) == 2
        assert behavior_analytics.user_segments[0]['user_id'] == 'user_1'
        assert behavior_analytics.user_segments[0]['success_rate'] == 0.85
    
    @pytest.mark.asyncio
    async def test_anomaly_detection(self, usage_analytics):
        """Test anomaly detection in usage patterns"""
        # Arrange
        normal_events = [
            SearchEvent(
                user_id=f"user_{i}",
                query="normal query",
                timestamp=datetime.utcnow(),
                results_count=5,
                response_time_ms=200,
                clicked_results=[1],
                conversation_id=i,
                search_type="hybrid"
            )
            for i in range(100)
        ]
        
        # Add anomalous event
        anomalous_event = SearchEvent(
            user_id="anomaly_user",
            query="anomaly query",
            timestamp=datetime.utcnow(),
            results_count=0,  # No results - anomaly
            response_time_ms=10000,  # Very slow - anomaly
            clicked_results=[],
            conversation_id=999,
            search_type="hybrid"
        )
        
        # Act
        for event in normal_events:
            await usage_analytics.track_search_event(event)
        
        anomalies = await usage_analytics.detect_anomalies([anomalous_event])
        
        # Assert
        assert len(anomalies) == 1
        assert anomalies[0]['type'] == 'performance_anomaly'
        assert anomalies[0]['severity'] == 'high'
        assert anomalies[0]['user_id'] == 'anomaly_user'


class TestAnalyticsEngine:
    """Test suite for the main analytics orchestration engine"""
    
    @pytest.fixture
    def analytics_engine(self):
        """Create AnalyticsEngine instance with mocked dependencies"""
        return AnalyticsEngine(
            usage_tracker=Mock(spec=UsageAnalytics),
            db=AsyncMock(),
            redis=AsyncMock(),
            config={
                'alert_thresholds': {
                    'slow_search_ms': 2000,
                    'low_results_count': 2,
                    'high_error_rate': 0.1
                }
            }
        )
    
    @pytest.mark.asyncio
    async def test_orchestrate_analytics_pipeline(self, analytics_engine):
        """Test main analytics pipeline orchestration"""
        # Arrange
        analytics_engine.usage_tracker.generate_insights = AsyncMock(
            return_value=AnalyticsInsights(
                total_searches=500,
                avg_response_time=300.0,
                click_through_rate=0.68,
                unique_users=75
            )
        )
        
        # Act
        result = await analytics_engine.run_analytics_pipeline()
        
        # Assert
        assert result['status'] == 'completed'
        assert result['insights']['total_searches'] == 500
        assert result['insights']['avg_response_time'] == 300.0
        
        # Verify analytics tracker was called
        analytics_engine.usage_tracker.generate_insights.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_real_time_dashboard_data(self, analytics_engine):
        """Test real-time dashboard data aggregation"""
        # Arrange
        analytics_engine.redis.get.side_effect = [
            '150',  # current_searches
            '285.5',  # avg_response_time
            '0.72',  # click_through_rate
            '25'  # active_users
        ]
        
        # Act
        dashboard_data = await analytics_engine.get_real_time_dashboard_data()
        
        # Assert
        assert dashboard_data['current_searches'] == 150
        assert dashboard_data['avg_response_time'] == 285.5
        assert dashboard_data['click_through_rate'] == 0.72
        assert dashboard_data['active_users'] == 25
    
    @pytest.mark.asyncio
    async def test_performance_alerting(self, analytics_engine):
        """Test automated performance alerting system"""
        # Arrange
        analytics_engine.redis.lrange.return_value = [
            json.dumps({
                'type': 'slow_search',
                'response_time': 5000,
                'threshold': 2000,
                'timestamp': datetime.utcnow().isoformat()
            })
        ]
        
        # Act
        alerts = await analytics_engine.check_performance_alerts()
        
        # Assert
        assert len(alerts) == 1
        assert alerts[0]['type'] == 'slow_search'
        assert alerts[0]['response_time'] == 5000
        assert alerts[0]['severity'] == 'high'
    
    @pytest.mark.asyncio
    async def test_automated_optimization_recommendations(self, analytics_engine):
        """Test automated optimization recommendations generation"""
        # Arrange
        analytics_engine.usage_tracker.analyze_search_patterns = AsyncMock(
            return_value=[
                {
                    'query': 'slow query pattern',
                    'avg_response_time': 3000,
                    'frequency': 20,
                    'optimization_potential': 0.8
                }
            ]
        )
        
        # Act
        recommendations = await analytics_engine.generate_optimization_recommendations()
        
        # Assert
        assert len(recommendations) == 1
        assert recommendations[0]['type'] == 'query_optimization'
        assert recommendations[0]['priority'] == 'high'
        assert 'slow query pattern' in recommendations[0]['description']


class TestAnalyticsSchemas:
    """Test suite for analytics data models and validation"""
    
    def test_usage_metrics_model(self):
        """Test UsageMetrics model validation"""
        # Arrange & Act
        metrics = UsageMetrics(
            total_searches=1000,
            unique_users=150,
            avg_response_time=275.5,
            click_through_rate=0.68,
            success_rate=0.92,
            timestamp=datetime.utcnow()
        )
        
        # Assert
        assert metrics.total_searches == 1000
        assert metrics.unique_users == 150
        assert metrics.click_through_rate == 0.68
        assert 0.0 <= metrics.click_through_rate <= 1.0
        assert 0.0 <= metrics.success_rate <= 1.0
    
    def test_search_analytics_model(self):
        """Test SearchAnalytics model with query patterns"""
        # Arrange & Act
        search_analytics = SearchAnalytics(
            query_patterns=[
                {'query': 'email setup', 'frequency': 25},
                {'query': 'sync issues', 'frequency': 18}
            ],
            popular_search_types=['hybrid', 'vector', 'text'],
            avg_results_per_search=4.2,
            no_results_rate=0.05
        )
        
        # Assert
        assert len(search_analytics.query_patterns) == 2
        assert search_analytics.query_patterns[0]['frequency'] == 25
        assert search_analytics.avg_results_per_search == 4.2
        assert 0.0 <= search_analytics.no_results_rate <= 1.0
    
    def test_system_performance_metrics(self):
        """Test SystemPerformanceMetrics model validation"""
        # Arrange & Act
        perf_metrics = SystemPerformanceMetrics(
            avg_search_time_ms=245.0,
            p95_search_time_ms=580.0,
            p99_search_time_ms=1200.0,
            error_rate=0.02,
            cache_hit_rate=0.85,
            concurrent_searches=12,
            peak_concurrent_searches=28
        )
        
        # Assert
        assert perf_metrics.avg_search_time_ms == 245.0
        assert perf_metrics.p95_search_time_ms == 580.0
        assert perf_metrics.p99_search_time_ms == 1200.0
        assert 0.0 <= perf_metrics.error_rate <= 1.0
        assert 0.0 <= perf_metrics.cache_hit_rate <= 1.0
    
    def test_invalid_metrics_validation(self):
        """Test validation of invalid metrics data"""
        # Test invalid click_through_rate (> 1.0)
        with pytest.raises(ValueError):
            UsageMetrics(
                total_searches=100,
                unique_users=50,
                avg_response_time=200.0,
                click_through_rate=1.5,  # Invalid: > 1.0
                success_rate=0.9,
                timestamp=datetime.utcnow()
            )
        
        # Test negative response time
        with pytest.raises(ValueError):
            SystemPerformanceMetrics(
                avg_search_time_ms=-10.0,  # Invalid: negative
                p95_search_time_ms=500.0,
                p99_search_time_ms=1000.0,
                error_rate=0.05,
                cache_hit_rate=0.8,
                concurrent_searches=5,
                peak_concurrent_searches=10
            )


class TestAnalyticsIntegration:
    """Integration tests for the complete analytics system"""
    
    @pytest.mark.asyncio
    async def test_end_to_end_analytics_flow(self):
        """Test complete analytics flow from event to insights"""
        # This test would be implemented with actual database connections
        # in a full integration test environment
        pass
    
    @pytest.mark.asyncio
    async def test_real_time_websocket_updates(self):
        """Test real-time analytics updates via WebSocket"""
        # This test would verify WebSocket integration
        # with real-time analytics updates
        pass
    
    @pytest.mark.asyncio
    async def test_performance_under_load(self):
        """Test analytics system performance under high load"""
        # This test would verify system behavior
        # under high event throughput
        pass


if __name__ == "__main__":
    pytest.main([__file__, "-v"])