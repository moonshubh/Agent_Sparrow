"""
Comprehensive tests for FeedMe Performance Metrics Collection
Tests performance monitoring, tracking, and optimization analytics.
"""

import pytest
import asyncio
import time
from datetime import datetime, timedelta
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from typing import Dict, List, Any
import numpy as np

# Import the modules we'll implement
from app.feedme.analytics.performance_monitor import PerformanceMonitor, MetricCollector
from app.feedme.analytics.schemas import (
    PerformanceMetrics,
    SearchPerformanceData,
    SystemHealthMetrics,
    OptimizationRecommendation
)


class TestPerformanceMonitor:
    """Test suite for performance monitoring and metrics collection"""
    
    @pytest.fixture
    def mock_db(self):
        """Mock database connection"""
        db = AsyncMock()
        return db
    
    @pytest.fixture
    def mock_redis(self):
        """Mock Redis client for performance metrics"""
        redis = AsyncMock()
        redis.get.return_value = None
        redis.setex.return_value = True
        redis.lpush.return_value = 1
        return redis
    
    @pytest.fixture
    def performance_monitor(self, mock_db, mock_redis):
        """Create PerformanceMonitor instance with mocked dependencies"""
        return PerformanceMonitor(
            db=mock_db,
            redis=mock_redis,
            config={
                'collection_interval_seconds': 5,
                'retention_days': 30,
                'alert_thresholds': {
                    'response_time_p95_ms': 1000,
                    'error_rate_threshold': 0.05,
                    'memory_usage_threshold': 0.8
                }
            }
        )
    
    @pytest.fixture
    def sample_performance_data(self):
        """Sample performance data for testing"""
        return SearchPerformanceData(
            timestamp=datetime.utcnow(),
            search_id="search_123",
            query="test query",
            search_type="hybrid",
            response_time_ms=450,
            results_count=5,
            cache_hit=True,
            database_query_time_ms=120,
            embedding_time_ms=80,
            ranking_time_ms=50,
            memory_usage_mb=256,
            cpu_usage_percent=15.5,
            error_occurred=False,
            error_type=None
        )
    
    @pytest.mark.asyncio
    async def test_collect_search_performance_metrics(self, performance_monitor, sample_performance_data):
        """Test collection of search performance metrics"""
        # Act
        await performance_monitor.collect_search_metrics(sample_performance_data)
        
        # Assert
        # Verify metrics were stored in Redis for real-time access
        performance_monitor.redis.lpush.assert_called()
        performance_monitor.redis.setex.assert_called()
        
        # Verify performance data was added to buffer
        assert len(performance_monitor._metrics_buffer) == 1
        stored_metric = performance_monitor._metrics_buffer[0]
        assert stored_metric.search_id == "search_123"
        assert stored_metric.response_time_ms == 450
    
    @pytest.mark.asyncio
    async def test_system_health_monitoring(self, performance_monitor):
        """Test comprehensive system health monitoring"""
        # Arrange
        with patch('psutil.cpu_percent', return_value=25.5), \
             patch('psutil.virtual_memory') as mock_memory, \
             patch('psutil.disk_usage') as mock_disk:
            
            mock_memory.return_value.percent = 60.0
            mock_memory.return_value.used = 8 * 1024**3  # 8GB
            mock_disk.return_value.percent = 45.0
            
            # Act
            health_metrics = await performance_monitor.collect_system_health()
            
            # Assert
            assert isinstance(health_metrics, SystemHealthMetrics)
            assert health_metrics.cpu_usage_percent == 25.5
            assert health_metrics.memory_usage_percent == 60.0
            assert health_metrics.disk_usage_percent == 45.0
            assert health_metrics.timestamp is not None
    
    @pytest.mark.asyncio
    async def test_performance_percentile_calculation(self, performance_monitor):
        """Test calculation of performance percentiles (P50, P95, P99)"""
        # Arrange
        response_times = [100, 150, 200, 250, 300, 400, 500, 800, 1200, 2000]
        
        for i, response_time in enumerate(response_times):
            perf_data = SearchPerformanceData(
                timestamp=datetime.utcnow(),
                search_id=f"search_{i}",
                query=f"query {i}",
                search_type="hybrid",
                response_time_ms=response_time,
                results_count=5,
                cache_hit=True,
                database_query_time_ms=response_time * 0.4,
                embedding_time_ms=response_time * 0.3,
                ranking_time_ms=response_time * 0.3,
                memory_usage_mb=200,
                cpu_usage_percent=10.0,
                error_occurred=False
            )
            await performance_monitor.collect_search_metrics(perf_data)
        
        # Act
        percentiles = await performance_monitor.calculate_response_time_percentiles()
        
        # Assert
        assert 'p50' in percentiles
        assert 'p95' in percentiles
        assert 'p99' in percentiles
        assert percentiles['p50'] <= percentiles['p95'] <= percentiles['p99']
        assert percentiles['p95'] >= 800  # Should be high due to outliers
    
    @pytest.mark.asyncio
    async def test_error_rate_tracking(self, performance_monitor):
        """Test error rate tracking and alerting"""
        # Arrange
        # Create mix of successful and failed searches
        search_data = []
        for i in range(20):
            error_occurred = i < 3  # First 3 are errors (15% error rate)
            search_data.append(SearchPerformanceData(
                timestamp=datetime.utcnow(),
                search_id=f"search_{i}",
                query=f"query {i}",
                search_type="hybrid",
                response_time_ms=300,
                results_count=0 if error_occurred else 5,
                cache_hit=False,
                database_query_time_ms=100,
                embedding_time_ms=100,
                ranking_time_ms=100,
                memory_usage_mb=200,
                cpu_usage_percent=10.0,
                error_occurred=error_occurred,
                error_type="timeout" if error_occurred else None
            ))
        
        # Act
        for data in search_data:
            await performance_monitor.collect_search_metrics(data)
        
        error_rate = await performance_monitor.calculate_error_rate(
            time_window_minutes=60
        )
        
        # Assert
        assert error_rate >= 0.14  # Should be around 15%
        assert error_rate <= 0.16
        
        # Verify alert was triggered if error rate exceeds threshold
        if error_rate > 0.05:  # Threshold from config
            performance_monitor.redis.lpush.assert_called_with(
                "feedme:performance_alerts",
                pytest.any()
            )
    
    @pytest.mark.asyncio
    async def test_cache_performance_analysis(self, performance_monitor):
        """Test cache hit rate analysis and optimization recommendations"""
        # Arrange
        cache_data = []
        for i in range(50):
            cache_hit = i % 3 != 0  # ~67% cache hit rate
            cache_data.append(SearchPerformanceData(
                timestamp=datetime.utcnow(),
                search_id=f"search_{i}",
                query=f"query {i}",
                search_type="hybrid",
                response_time_ms=150 if cache_hit else 400,  # Faster with cache
                results_count=5,
                cache_hit=cache_hit,
                database_query_time_ms=50 if cache_hit else 200,
                embedding_time_ms=50,
                ranking_time_ms=50,
                memory_usage_mb=200,
                cpu_usage_percent=10.0,
                error_occurred=False
            ))
        
        # Act
        for data in cache_data:
            await performance_monitor.collect_search_metrics(data)
        
        cache_analysis = await performance_monitor.analyze_cache_performance()
        
        # Assert
        assert cache_analysis['hit_rate'] >= 0.65
        assert cache_analysis['hit_rate'] <= 0.70
        assert cache_analysis['avg_response_time_with_cache'] < cache_analysis['avg_response_time_without_cache']
        assert 'optimization_potential' in cache_analysis
    
    @pytest.mark.asyncio
    async def test_database_query_optimization_analysis(self, performance_monitor, mock_db):
        """Test database query performance analysis"""
        # Arrange
        mock_db.fetch_all.return_value = [
            {
                'query_type': 'vector_search',
                'avg_execution_time_ms': 250.0,
                'execution_count': 1000,
                'p95_execution_time_ms': 500.0,
                'slow_query_count': 25
            },
            {
                'query_type': 'text_search',
                'avg_execution_time_ms': 150.0,
                'execution_count': 800,
                'p95_execution_time_ms': 300.0,
                'slow_query_count': 10
            }
        ]
        
        # Act
        query_analysis = await performance_monitor.analyze_database_performance()
        
        # Assert
        assert len(query_analysis) == 2
        assert query_analysis[0]['query_type'] == 'vector_search'
        assert query_analysis[0]['avg_execution_time_ms'] == 250.0
        assert query_analysis[1]['slow_query_count'] == 10
        
        # Verify database was queried
        mock_db.fetch_all.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_memory_usage_tracking(self, performance_monitor):
        """Test memory usage tracking and leak detection"""
        # Arrange
        memory_data = []
        base_memory = 200
        for i in range(100):
            # Simulate gradual memory increase (potential leak)
            memory_usage = base_memory + (i * 2)  # 2MB increase per operation
            memory_data.append(SearchPerformanceData(
                timestamp=datetime.utcnow() + timedelta(seconds=i),
                search_id=f"search_{i}",
                query=f"query {i}",
                search_type="hybrid",
                response_time_ms=300,
                results_count=5,
                cache_hit=True,
                database_query_time_ms=100,
                embedding_time_ms=100,
                ranking_time_ms=100,
                memory_usage_mb=memory_usage,
                cpu_usage_percent=10.0,
                error_occurred=False
            ))
        
        # Act
        for data in memory_data:
            await performance_monitor.collect_search_metrics(data)
        
        memory_analysis = await performance_monitor.analyze_memory_usage()
        
        # Assert
        assert memory_analysis['trend'] == 'increasing'
        assert memory_analysis['leak_detected'] == True
        assert memory_analysis['growth_rate_mb_per_hour'] > 0
        assert 'alert_triggered' in memory_analysis
    
    @pytest.mark.asyncio
    async def test_concurrent_search_monitoring(self, performance_monitor):
        """Test monitoring of concurrent search performance"""
        # Arrange
        concurrent_searches = []
        start_time = datetime.utcnow()
        
        # Simulate 10 concurrent searches
        for i in range(10):
            search_data = SearchPerformanceData(
                timestamp=start_time + timedelta(milliseconds=i * 10),
                search_id=f"concurrent_search_{i}",
                query=f"concurrent query {i}",
                search_type="hybrid",
                response_time_ms=200 + (i * 50),  # Increasing response time
                results_count=5,
                cache_hit=True,
                database_query_time_ms=80,
                embedding_time_ms=60,
                ranking_time_ms=60,
                memory_usage_mb=200 + (i * 10),
                cpu_usage_percent=10.0 + (i * 2),
                error_occurred=False
            )
            concurrent_searches.append(search_data)
        
        # Act
        tasks = [
            performance_monitor.collect_search_metrics(data)
            for data in concurrent_searches
        ]
        await asyncio.gather(*tasks)
        
        concurrency_analysis = await performance_monitor.analyze_concurrency_impact()
        
        # Assert
        assert concurrency_analysis['peak_concurrent_searches'] == 10
        assert 'response_time_degradation' in concurrency_analysis
        assert 'cpu_usage_impact' in concurrency_analysis
    
    @pytest.mark.asyncio
    async def test_optimization_recommendations_generation(self, performance_monitor):
        """Test generation of automated optimization recommendations"""
        # Arrange
        # Simulate poor performance conditions
        poor_performance_data = SearchPerformanceData(
            timestamp=datetime.utcnow(),
            search_id="slow_search",
            query="complex query",
            search_type="hybrid",
            response_time_ms=2500,  # Very slow
            results_count=10,
            cache_hit=False,  # Cache miss
            database_query_time_ms=1500,  # Slow DB query
            embedding_time_ms=800,  # Slow embedding
            ranking_time_ms=200,
            memory_usage_mb=800,  # High memory usage
            cpu_usage_percent=85.0,  # High CPU usage
            error_occurred=False
        )
        
        await performance_monitor.collect_search_metrics(poor_performance_data)
        
        # Act
        recommendations = await performance_monitor.generate_optimization_recommendations()
        
        # Assert
        assert len(recommendations) > 0
        
        # Check for specific recommendations
        recommendation_types = [r.type for r in recommendations]
        assert 'database_optimization' in recommendation_types
        assert 'caching_improvement' in recommendation_types
        assert 'memory_optimization' in recommendation_types
        
        # Verify recommendations have priority and impact scores
        for rec in recommendations:
            assert hasattr(rec, 'priority')
            assert hasattr(rec, 'impact_score')
            assert hasattr(rec, 'implementation_effort')
    
    @pytest.mark.asyncio
    async def test_performance_alerting_system(self, performance_monitor, mock_redis):
        """Test automated performance alerting system"""
        # Arrange
        # Create alert conditions
        alert_conditions = [
            # High response time
            SearchPerformanceData(
                timestamp=datetime.utcnow(),
                search_id="alert_1",
                query="slow query",
                search_type="hybrid",
                response_time_ms=3000,  # Above threshold
                results_count=5,
                cache_hit=True,
                database_query_time_ms=2000,
                embedding_time_ms=500,
                ranking_time_ms=500,
                memory_usage_mb=300,
                cpu_usage_percent=20.0,
                error_occurred=False
            ),
            # High error rate
            SearchPerformanceData(
                timestamp=datetime.utcnow(),
                search_id="alert_2",
                query="error query",
                search_type="vector",
                response_time_ms=500,
                results_count=0,
                cache_hit=False,
                database_query_time_ms=200,
                embedding_time_ms=200,
                ranking_time_ms=100,
                memory_usage_mb=400,
                cpu_usage_percent=30.0,
                error_occurred=True,
                error_type="timeout"
            )
        ]
        
        # Act
        for data in alert_conditions:
            await performance_monitor.collect_search_metrics(data)
        
        alerts = await performance_monitor.check_and_send_alerts()
        
        # Assert
        assert len(alerts) >= 2  # Should have at least 2 alerts
        
        # Verify alerts were sent to Redis
        assert mock_redis.lpush.call_count >= 2
        
        # Check alert content
        alert_types = [alert['type'] for alert in alerts]
        assert 'slow_response' in alert_types
        assert 'search_error' in alert_types


class TestMetricCollector:
    """Test suite for detailed metric collection utilities"""
    
    @pytest.fixture
    def metric_collector(self):
        """Create MetricCollector instance"""
        return MetricCollector(
            collection_interval=1.0,
            buffer_size=1000
        )
    
    @pytest.mark.asyncio
    async def test_real_time_metric_collection(self, metric_collector):
        """Test real-time metric collection with timing"""
        # Act
        with metric_collector.measure_time() as timer:
            await asyncio.sleep(0.1)  # Simulate work
        
        # Assert
        elapsed_time = timer.elapsed_ms
        assert elapsed_time >= 90  # Should be around 100ms
        assert elapsed_time <= 150  # Allow for some variance
    
    @pytest.mark.asyncio
    async def test_memory_profiling(self, metric_collector):
        """Test memory usage profiling"""
        # Arrange
        initial_memory = metric_collector.get_current_memory_usage()
        
        # Simulate memory allocation
        large_data = [i for i in range(100000)]  # Allocate some memory
        
        # Act
        peak_memory = metric_collector.get_current_memory_usage()
        
        # Clean up
        del large_data
        
        final_memory = metric_collector.get_current_memory_usage()
        
        # Assert
        assert peak_memory > initial_memory
        assert final_memory <= peak_memory
    
    def test_cpu_usage_sampling(self, metric_collector):
        """Test CPU usage sampling and averaging"""
        # Act
        cpu_samples = []
        for _ in range(10):
            cpu_usage = metric_collector.get_current_cpu_usage()
            cpu_samples.append(cpu_usage)
            time.sleep(0.01)  # Small delay between samples
        
        avg_cpu = metric_collector.calculate_average_cpu(cpu_samples)
        
        # Assert
        assert all(0 <= sample <= 100 for sample in cpu_samples)
        assert 0 <= avg_cpu <= 100
    
    @pytest.mark.asyncio
    async def test_batch_metric_processing(self, metric_collector):
        """Test batch processing of collected metrics"""
        # Arrange
        metrics = []
        for i in range(50):
            metric = {
                'timestamp': datetime.utcnow(),
                'metric_type': 'search_performance',
                'value': i * 10,
                'tags': {'search_type': 'hybrid'}
            }
            metrics.append(metric)
        
        # Act
        processed_batch = await metric_collector.process_metrics_batch(metrics)
        
        # Assert
        assert len(processed_batch) == 50
        assert processed_batch[0]['aggregated'] == True
        assert 'batch_id' in processed_batch[0]
    
    def test_metric_validation(self, metric_collector):
        """Test metric data validation"""
        # Test valid metric
        valid_metric = {
            'timestamp': datetime.utcnow(),
            'metric_type': 'response_time',
            'value': 250.5,
            'tags': {'search_type': 'vector'}
        }
        
        assert metric_collector.validate_metric(valid_metric) == True
        
        # Test invalid metric (missing required fields)
        invalid_metric = {
            'timestamp': datetime.utcnow(),
            'value': 250.5
            # Missing metric_type
        }
        
        assert metric_collector.validate_metric(invalid_metric) == False
        
        # Test invalid metric (wrong data type)
        invalid_type_metric = {
            'timestamp': "not_a_datetime",
            'metric_type': 'response_time',
            'value': 250.5,
            'tags': {'search_type': 'vector'}
        }
        
        assert metric_collector.validate_metric(invalid_type_metric) == False


class TestPerformanceIntegration:
    """Integration tests for performance monitoring system"""
    
    @pytest.mark.asyncio
    async def test_end_to_end_performance_monitoring(self):
        """Test complete performance monitoring flow"""
        # This would test the full flow from metric collection
        # to analysis to alerting in an integration environment
        pass
    
    @pytest.mark.asyncio
    async def test_high_throughput_metric_collection(self):
        """Test performance monitoring under high load"""
        # This would test system behavior under high metric throughput
        pass
    
    @pytest.mark.asyncio
    async def test_performance_dashboard_integration(self):
        """Test integration with performance dashboard"""
        # This would test real-time dashboard updates
        pass


if __name__ == "__main__":
    pytest.main([__file__, "-v"])