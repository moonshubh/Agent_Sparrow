"""
Comprehensive tests for FeedMe Health Monitoring System
Tests system health checks, automated alerting, and monitoring infrastructure.
"""

import pytest
import asyncio
from datetime import datetime, timedelta
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from typing import Dict, List, Any
import json

# Import the modules we'll implement
from app.feedme.analytics.health_monitor import (
    HealthMonitor,
    SystemHealthChecker,
    AlertManager
)
from app.feedme.analytics.schemas import (
    HealthStatus,
    SystemComponents,
    HealthAlert,
    MonitoringConfig
)


class TestHealthMonitor:
    """Test suite for comprehensive system health monitoring"""
    
    @pytest.fixture
    def mock_db(self):
        """Mock database connection"""
        db = AsyncMock()
        return db
    
    @pytest.fixture
    def mock_redis(self):
        """Mock Redis client for health monitoring"""
        redis = AsyncMock()
        return redis
    
    @pytest.fixture
    def health_monitor(self, mock_db, mock_redis):
        """Create HealthMonitor instance with mocked dependencies"""
        return HealthMonitor(
            db=mock_db,
            redis=mock_redis,
            config=MonitoringConfig(
                check_interval_seconds=30,
                alert_thresholds={
                    'database_response_time_ms': 1000,
                    'memory_usage_percent': 80,
                    'cpu_usage_percent': 85,
                    'disk_usage_percent': 90,
                    'error_rate_percent': 5
                },
                critical_services=['database', 'redis', 'search_engine', 'ai_models']
            )
        )
    
    @pytest.fixture
    def sample_health_status(self):
        """Sample health status for testing"""
        return HealthStatus(
            timestamp=datetime.utcnow(),
            overall_status='healthy',
            components={
                'database': {
                    'status': 'healthy',
                    'response_time_ms': 50,
                    'connection_count': 10,
                    'last_error': None
                },
                'redis': {
                    'status': 'healthy',
                    'response_time_ms': 5,
                    'memory_usage_mb': 128,
                    'last_error': None
                },
                'search_engine': {
                    'status': 'healthy',
                    'avg_search_time_ms': 250,
                    'cache_hit_rate': 0.75,
                    'last_error': None
                },
                'ai_models': {
                    'status': 'healthy',
                    'model_response_time_ms': 800,
                    'requests_per_minute': 45,
                    'last_error': None
                }
            },
            system_metrics={
                'cpu_usage_percent': 25.5,
                'memory_usage_percent': 65.0,
                'disk_usage_percent': 45.0,
                'network_io_mbps': 12.5
            }
        )
    
    @pytest.mark.asyncio
    async def test_comprehensive_health_check(self, health_monitor, mock_db, mock_redis):
        """Test comprehensive system health check"""
        # Arrange
        mock_db.fetch_one.return_value = {'status': 'ok', 'response_time': 45}
        mock_redis.ping.return_value = True
        
        with patch('psutil.cpu_percent', return_value=30.0), \
             patch('psutil.virtual_memory') as mock_memory, \
             patch('psutil.disk_usage') as mock_disk:
            
            mock_memory.return_value.percent = 60.0
            mock_disk.return_value.percent = 40.0
            
            # Act
            health_status = await health_monitor.perform_health_check()
            
            # Assert
            assert isinstance(health_status, HealthStatus)
            assert health_status.overall_status in ['healthy', 'warning', 'critical']
            assert 'database' in health_status.components
            assert 'redis' in health_status.components
            assert health_status.system_metrics['cpu_usage_percent'] == 30.0
            assert health_status.system_metrics['memory_usage_percent'] == 60.0
    
    @pytest.mark.asyncio
    async def test_database_health_monitoring(self, health_monitor, mock_db):
        """Test database-specific health monitoring"""
        # Arrange - Simulate slow database response
        mock_db.fetch_one.return_value = {'status': 'ok', 'response_time': 1500}  # Slow
        
        # Act
        db_health = await health_monitor.check_database_health()
        
        # Assert
        assert db_health['status'] == 'warning'  # Should detect slow response
        assert db_health['response_time_ms'] == 1500
        assert 'alert_triggered' in db_health
        
        # Verify database query was executed
        mock_db.fetch_one.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_redis_health_monitoring(self, health_monitor, mock_redis):
        """Test Redis health monitoring and memory usage"""
        # Arrange
        mock_redis.ping.return_value = True
        mock_redis.info.return_value = {
            'used_memory': 256 * 1024 * 1024,  # 256MB
            'maxmemory': 512 * 1024 * 1024,    # 512MB max
            'connected_clients': 50,
            'keyspace_hits': 1000,
            'keyspace_misses': 200
        }
        
        # Act
        redis_health = await health_monitor.check_redis_health()
        
        # Assert
        assert redis_health['status'] == 'healthy'
        assert redis_health['memory_usage_percent'] == 50.0
        assert redis_health['cache_hit_rate'] == 1000 / 1200  # hits / (hits + misses)
        assert redis_health['connected_clients'] == 50
    
    @pytest.mark.asyncio
    async def test_search_engine_health_monitoring(self, health_monitor):
        """Test search engine health and performance monitoring"""
        # Arrange
        search_metrics = {
            'avg_response_time_ms': 350,
            'total_searches_last_hour': 250,
            'error_count_last_hour': 5,
            'cache_hit_rate': 0.68,
            'index_size_mb': 1024
        }
        
        with patch.object(health_monitor, '_get_search_metrics', return_value=search_metrics):
            # Act
            search_health = await health_monitor.check_search_engine_health()
            
            # Assert
            assert search_health['status'] == 'healthy'
            assert search_health['avg_response_time_ms'] == 350
            assert search_health['error_rate'] == 5 / 250  # 2% error rate
            assert search_health['cache_hit_rate'] == 0.68
    
    @pytest.mark.asyncio
    async def test_ai_models_health_monitoring(self, health_monitor):
        """Test AI models health and availability monitoring"""
        # Arrange
        ai_metrics = {
            'gemini_model_status': 'available',
            'avg_response_time_ms': 1200,
            'requests_last_hour': 150,
            'errors_last_hour': 2,
            'rate_limit_status': 'ok',
            'quota_remaining': 80
        }
        
        with patch.object(health_monitor, '_get_ai_model_metrics', return_value=ai_metrics):
            # Act
            ai_health = await health_monitor.check_ai_models_health()
            
            # Assert
            assert ai_health['status'] == 'healthy'
            assert ai_health['model_response_time_ms'] == 1200
            assert ai_health['error_rate'] == 2 / 150
            assert ai_health['quota_remaining'] == 80
    
    @pytest.mark.asyncio
    async def test_system_resource_monitoring(self, health_monitor):
        """Test system resource monitoring (CPU, memory, disk)"""
        # Arrange
        with patch('psutil.cpu_percent', return_value=85.5), \
             patch('psutil.virtual_memory') as mock_memory, \
             patch('psutil.disk_usage') as mock_disk, \
             patch('psutil.net_io_counters') as mock_net:
            
            mock_memory.return_value.percent = 82.0  # High memory usage
            mock_disk.return_value.percent = 75.0
            mock_net.return_value.bytes_sent = 1024 * 1024 * 100  # 100MB
            mock_net.return_value.bytes_recv = 1024 * 1024 * 150  # 150MB
            
            # Act
            resource_health = await health_monitor.check_system_resources()
            
            # Assert
            assert resource_health['cpu_usage_percent'] == 85.5
            assert resource_health['memory_usage_percent'] == 82.0
            assert resource_health['disk_usage_percent'] == 75.0
            
            # Should trigger alerts for high CPU and memory usage
            assert resource_health['alerts']['cpu_high'] == True
            assert resource_health['alerts']['memory_high'] == True
    
    @pytest.mark.asyncio
    async def test_health_trend_analysis(self, health_monitor, mock_db):
        """Test health trend analysis over time"""
        # Arrange
        mock_db.fetch_all.return_value = [
            {
                'timestamp': datetime.utcnow() - timedelta(minutes=30),
                'cpu_usage': 20.0,
                'memory_usage': 60.0,
                'response_time': 200
            },
            {
                'timestamp': datetime.utcnow() - timedelta(minutes=20),
                'cpu_usage': 35.0,
                'memory_usage': 65.0,
                'response_time': 250
            },
            {
                'timestamp': datetime.utcnow() - timedelta(minutes=10),
                'cpu_usage': 50.0,
                'memory_usage': 70.0,
                'response_time': 300
            }
        ]
        
        # Act
        trend_analysis = await health_monitor.analyze_health_trends(
            time_window_hours=1
        )
        
        # Assert
        assert trend_analysis['cpu_trend'] == 'increasing'
        assert trend_analysis['memory_trend'] == 'increasing'
        assert trend_analysis['response_time_trend'] == 'increasing'
        assert trend_analysis['overall_trend'] == 'degrading'
        assert 'predicted_alerts' in trend_analysis
    
    @pytest.mark.asyncio
    async def test_automated_health_recovery(self, health_monitor):
        """Test automated health recovery actions"""
        # Arrange
        unhealthy_status = HealthStatus(
            timestamp=datetime.utcnow(),
            overall_status='critical',
            components={
                'database': {
                    'status': 'critical',
                    'response_time_ms': 5000,
                    'connection_count': 100,
                    'last_error': 'Connection timeout'
                }
            },
            system_metrics={
                'cpu_usage_percent': 95.0,
                'memory_usage_percent': 90.0,
                'disk_usage_percent': 95.0
            }
        )
        
        # Act
        recovery_actions = await health_monitor.execute_recovery_actions(unhealthy_status)
        
        # Assert
        assert len(recovery_actions) > 0
        
        # Should include actions for each critical issue
        action_types = [action['type'] for action in recovery_actions]
        assert 'restart_db_connections' in action_types
        assert 'clear_memory_cache' in action_types
        assert 'cleanup_temp_files' in action_types
    
    @pytest.mark.asyncio
    async def test_health_monitoring_alerts(self, health_monitor, mock_redis):
        """Test health monitoring alert generation and delivery"""
        # Arrange
        critical_health = HealthStatus(
            timestamp=datetime.utcnow(),
            overall_status='critical',
            components={
                'search_engine': {
                    'status': 'critical',
                    'avg_search_time_ms': 3000,
                    'error_rate': 0.15,
                    'last_error': 'Index corruption detected'
                }
            },
            system_metrics={
                'memory_usage_percent': 95.0
            }
        )
        
        # Act
        alerts = await health_monitor.generate_alerts(critical_health)
        
        # Assert
        assert len(alerts) >= 2  # Search engine + memory alerts
        
        # Verify critical alert properties
        critical_alerts = [a for a in alerts if a.severity == 'critical']
        assert len(critical_alerts) >= 1
        
        search_alert = next(a for a in alerts if 'search_engine' in a.component)
        assert search_alert.severity == 'critical'
        assert 'Index corruption' in search_alert.message
        
        # Verify alerts were sent to Redis
        mock_redis.lpush.assert_called()


class TestSystemHealthChecker:
    """Test suite for individual health check components"""
    
    @pytest.fixture
    def health_checker(self):
        """Create SystemHealthChecker instance"""
        return SystemHealthChecker(
            timeout_seconds=5,
            retry_attempts=3
        )
    
    @pytest.mark.asyncio
    async def test_connection_health_check(self, health_checker):
        """Test connection health checking with timeout and retry"""
        # Test successful connection
        async def mock_successful_connection():
            await asyncio.sleep(0.1)
            return {'status': 'ok', 'latency': 100}
        
        result = await health_checker.check_connection(
            mock_successful_connection,
            service_name='test_service'
        )
        
        assert result['status'] == 'healthy'
        assert result['latency'] == 100
    
    @pytest.mark.asyncio
    async def test_connection_timeout_handling(self, health_checker):
        """Test connection timeout handling"""
        # Test connection timeout
        async def mock_slow_connection():
            await asyncio.sleep(10)  # Longer than timeout
            return {'status': 'ok'}
        
        result = await health_checker.check_connection(
            mock_slow_connection,
            service_name='slow_service'
        )
        
        assert result['status'] == 'timeout'
        assert 'error' in result
    
    @pytest.mark.asyncio
    async def test_service_availability_check(self, health_checker):
        """Test service availability checking"""
        # Mock service endpoints
        services = {
            'api_service': 'http://localhost:8000/health',
            'search_service': 'http://localhost:9200/_health',
            'cache_service': 'redis://localhost:6379'
        }
        
        with patch('aiohttp.ClientSession.get') as mock_get:
            mock_response = AsyncMock()
            mock_response.status = 200
            mock_response.json.return_value = {'status': 'healthy'}
            mock_get.return_value.__aenter__.return_value = mock_response
            
            availability_results = await health_checker.check_services_availability(services)
            
            assert len(availability_results) == 3
            assert all(result['available'] for result in availability_results.values())
    
    def test_resource_threshold_validation(self, health_checker):
        """Test resource usage threshold validation"""
        # Test normal resource usage
        normal_resources = {
            'cpu_percent': 45.0,
            'memory_percent': 60.0,
            'disk_percent': 50.0
        }
        
        thresholds = {
            'cpu_percent': 80.0,
            'memory_percent': 85.0,
            'disk_percent': 90.0
        }
        
        validation_result = health_checker.validate_resource_thresholds(
            normal_resources, thresholds
        )
        
        assert validation_result['status'] == 'healthy'
        assert not validation_result['violations']
        
        # Test threshold violations
        high_resources = {
            'cpu_percent': 85.0,  # Above threshold
            'memory_percent': 90.0,  # Above threshold
            'disk_percent': 45.0
        }
        
        violation_result = health_checker.validate_resource_thresholds(
            high_resources, thresholds
        )
        
        assert violation_result['status'] == 'warning'
        assert len(violation_result['violations']) == 2
        assert 'cpu_percent' in violation_result['violations']
        assert 'memory_percent' in violation_result['violations']


class TestAlertManager:
    """Test suite for alert management and notification system"""
    
    @pytest.fixture
    def alert_manager(self):
        """Create AlertManager instance"""
        return AlertManager(
            notification_channels=['email', 'slack', 'webhook'],
            rate_limit_minutes=15,
            escalation_rules={
                'critical': {'immediate': True, 'channels': ['email', 'slack']},
                'warning': {'delay_minutes': 5, 'channels': ['slack']},
                'info': {'delay_minutes': 30, 'channels': ['email']}
            }
        )
    
    @pytest.fixture
    def sample_alerts(self):
        """Sample alerts for testing"""
        return [
            HealthAlert(
                id='alert_1',
                timestamp=datetime.utcnow(),
                severity='critical',
                component='database',
                message='Database connection pool exhausted',
                details={'connection_count': 100, 'max_connections': 100}
            ),
            HealthAlert(
                id='alert_2',
                timestamp=datetime.utcnow(),
                severity='warning',
                component='memory',
                message='High memory usage detected',
                details={'memory_percent': 85.0, 'threshold': 80.0}
            )
        ]
    
    @pytest.mark.asyncio
    async def test_alert_processing_and_routing(self, alert_manager, sample_alerts):
        """Test alert processing and routing to appropriate channels"""
        # Act
        processing_results = []
        for alert in sample_alerts:
            result = await alert_manager.process_alert(alert)
            processing_results.append(result)
        
        # Assert
        assert len(processing_results) == 2
        
        # Critical alert should be processed immediately
        critical_result = processing_results[0]
        assert critical_result['processed_immediately'] == True
        assert 'email' in critical_result['channels_notified']
        assert 'slack' in critical_result['channels_notified']
        
        # Warning alert should have delay
        warning_result = processing_results[1]
        assert warning_result['delay_minutes'] == 5
        assert critical_result['channels_notified'] == ['slack']
    
    @pytest.mark.asyncio
    async def test_alert_deduplication(self, alert_manager):
        """Test alert deduplication to prevent spam"""
        # Arrange
        duplicate_alert = HealthAlert(
            id='duplicate_1',
            timestamp=datetime.utcnow(),
            severity='warning',
            component='memory',
            message='High memory usage detected',
            details={'memory_percent': 82.0}
        )
        
        # Send same alert twice
        first_result = await alert_manager.process_alert(duplicate_alert)
        second_result = await alert_manager.process_alert(duplicate_alert)
        
        # Assert
        assert first_result['sent'] == True
        assert second_result['sent'] == False
        assert second_result['reason'] == 'duplicate_suppressed'
    
    @pytest.mark.asyncio
    async def test_alert_escalation(self, alert_manager):
        """Test alert escalation based on time and severity"""
        # Arrange
        persistent_alert = HealthAlert(
            id='persistent_1',
            timestamp=datetime.utcnow() - timedelta(minutes=30),
            severity='warning',
            component='cpu',
            message='High CPU usage sustained',
            details={'cpu_percent': 85.0}
        )
        
        # Act
        escalation_result = await alert_manager.check_escalation(persistent_alert)
        
        # Assert
        assert escalation_result['should_escalate'] == True
        assert escalation_result['new_severity'] == 'critical'
        assert escalation_result['reason'] == 'duration_threshold_exceeded'
    
    @pytest.mark.asyncio
    async def test_alert_notification_delivery(self, alert_manager):
        """Test alert notification delivery to multiple channels"""
        # Arrange
        urgent_alert = HealthAlert(
            id='urgent_1',
            timestamp=datetime.utcnow(),
            severity='critical',
            component='service_down',
            message='Primary service is down',
            details={'service': 'feedme_api', 'downtime_seconds': 120}
        )
        
        with patch.object(alert_manager, 'send_email_notification') as mock_email, \
             patch.object(alert_manager, 'send_slack_notification') as mock_slack, \
             patch.object(alert_manager, 'send_webhook_notification') as mock_webhook:
            
            mock_email.return_value = {'sent': True, 'message_id': 'email_123'}
            mock_slack.return_value = {'sent': True, 'channel': '#alerts'}
            mock_webhook.return_value = {'sent': True, 'response_code': 200}
            
            # Act
            delivery_results = await alert_manager.deliver_notifications(urgent_alert)
            
            # Assert
            assert delivery_results['email']['sent'] == True
            assert delivery_results['slack']['sent'] == True
            assert mock_email.call_count == 1
            assert mock_slack.call_count == 1
    
    @pytest.mark.asyncio
    async def test_alert_resolution_tracking(self, alert_manager):
        """Test tracking of alert resolution and recovery"""
        # Arrange
        resolved_alert = HealthAlert(
            id='resolved_1',
            timestamp=datetime.utcnow() - timedelta(minutes=10),
            severity='warning',
            component='database',
            message='Database slow queries detected',
            details={'avg_query_time': 1200}
        )
        
        # Act
        # Mark alert as resolved
        resolution_result = await alert_manager.resolve_alert(
            alert_id='resolved_1',
            resolution_message='Database performance restored after index optimization'
        )
        
        # Assert
        assert resolution_result['resolved'] == True
        assert resolution_result['resolution_time'] is not None
        assert 'Database performance restored' in resolution_result['resolution_message']
    
    @pytest.mark.asyncio
    async def test_alert_metrics_and_reporting(self, alert_manager):
        """Test alert metrics collection and reporting"""
        # Arrange
        # Simulate processing multiple alerts over time
        test_alerts = [
            HealthAlert(
                id=f'metric_alert_{i}',
                timestamp=datetime.utcnow() - timedelta(minutes=i*5),
                severity='critical' if i % 3 == 0 else 'warning',
                component='test_component',
                message=f'Test alert {i}',
                details={}
            )
            for i in range(10)
        ]
        
        # Process all alerts
        for alert in test_alerts:
            await alert_manager.process_alert(alert)
        
        # Act
        alert_metrics = await alert_manager.get_alert_metrics(
            time_window_hours=1
        )
        
        # Assert
        assert alert_metrics['total_alerts'] == 10
        assert alert_metrics['critical_alerts'] >= 3  # Every 3rd alert is critical
        assert alert_metrics['warning_alerts'] >= 6
        assert 'avg_resolution_time' in alert_metrics
        assert 'alert_frequency_per_hour' in alert_metrics


class TestHealthMonitoringIntegration:
    """Integration tests for health monitoring system"""
    
    @pytest.mark.asyncio
    async def test_end_to_end_health_monitoring_flow(self):
        """Test complete health monitoring flow from check to alert"""
        # This would test the full flow from health check detection
        # to alert delivery in an integration environment
        pass
    
    @pytest.mark.asyncio
    async def test_health_monitoring_under_system_stress(self):
        """Test health monitoring behavior under system stress"""
        # This would test monitoring system behavior when the
        # monitored system is under high load or stress
        pass
    
    @pytest.mark.asyncio
    async def test_health_dashboard_integration(self):
        """Test integration with health monitoring dashboard"""
        # This would test real-time dashboard updates and
        # health status visualization
        pass


if __name__ == "__main__":
    pytest.main([__file__, "-v"])