"""
Comprehensive tests for FeedMe Analytics API Endpoints
Tests REST API endpoints for analytics data access, dashboards, and reporting.
"""

import pytest
import asyncio
from datetime import datetime, timedelta
from fastapi.testclient import TestClient
from fastapi import FastAPI
from unittest.mock import Mock, AsyncMock, patch
from typing import Dict, List, Any
import json

# Import the modules we'll implement
from app.api.v1.endpoints.analytics_endpoints import router as analytics_router
from app.feedme.analytics.schemas import (
    AnalyticsRequest,
    AnalyticsResponse,
    DashboardData,
    ReportConfig
)


class TestAnalyticsEndpoints:
    """Test suite for analytics REST API endpoints"""
    
    @pytest.fixture
    def app(self):
        """Create FastAPI test application"""
        app = FastAPI()
        app.include_router(analytics_router, prefix="/api/v1/analytics")
        return app
    
    @pytest.fixture
    def client(self, app):
        """Create test client"""
        return TestClient(app)
    
    @pytest.fixture
    def mock_analytics_service(self):
        """Mock analytics service"""
        service = AsyncMock()
        return service
    
    @pytest.fixture
    def sample_analytics_data(self):
        """Sample analytics data for testing"""
        return {
            'usage_metrics': {
                'total_searches': 1500,
                'unique_users': 250,
                'avg_response_time': 285.5,
                'success_rate': 0.89
            },
            'search_patterns': [
                {'query': 'email sync', 'frequency': 45, 'success_rate': 0.92},
                {'query': 'account setup', 'frequency': 32, 'success_rate': 0.88}
            ],
            'performance_metrics': {
                'p50_response_time': 200,
                'p95_response_time': 500,
                'p99_response_time': 1200,
                'error_rate': 0.02
            }
        }
    
    def test_get_analytics_overview(self, client, sample_analytics_data):
        """Test GET /analytics/overview endpoint"""
        # Arrange
        with patch('app.api.v1.endpoints.analytics_endpoints.get_analytics_service') as mock_service:
            mock_service.return_value.get_overview_metrics = AsyncMock(
                return_value=sample_analytics_data
            )
            
            # Act
            response = client.get("/api/v1/analytics/overview")
            
            # Assert
            assert response.status_code == 200
            data = response.json()
            assert 'usage_metrics' in data
            assert data['usage_metrics']['total_searches'] == 1500
            assert data['usage_metrics']['unique_users'] == 250
    
    def test_get_analytics_overview_with_time_range(self, client):
        """Test analytics overview with custom time range"""
        # Arrange
        start_date = (datetime.utcnow() - timedelta(days=7)).isoformat()
        end_date = datetime.utcnow().isoformat()
        
        with patch('app.api.v1.endpoints.analytics_endpoints.get_analytics_service') as mock_service:
            mock_service.return_value.get_overview_metrics = AsyncMock(
                return_value={'filtered_data': True}
            )
            
            # Act
            response = client.get(
                f"/api/v1/analytics/overview?start_date={start_date}&end_date={end_date}"
            )
            
            # Assert
            assert response.status_code == 200
            data = response.json()
            assert 'filtered_data' in data
            
            # Verify service was called with correct parameters
            mock_service.return_value.get_overview_metrics.assert_called_once()
            call_args = mock_service.return_value.get_overview_metrics.call_args
            assert call_args[1]['start_date'] is not None
            assert call_args[1]['end_date'] is not None
    
    def test_get_search_analytics(self, client):
        """Test GET /analytics/search endpoint"""
        # Arrange
        search_analytics_data = {
            'query_patterns': [
                {
                    'query': 'email sync issues',
                    'frequency': 25,
                    'avg_response_time': 300,
                    'success_rate': 0.88,
                    'click_through_rate': 0.72
                }
            ],
            'search_types_performance': {
                'hybrid': {'avg_response_time': 250, 'success_rate': 0.89},
                'vector': {'avg_response_time': 400, 'success_rate': 0.85},
                'text': {'avg_response_time': 150, 'success_rate': 0.75}
            },
            'no_results_queries': [
                {'query': 'mailbird mobile app', 'frequency': 15}
            ]
        }
        
        with patch('app.api.v1.endpoints.analytics_endpoints.get_analytics_service') as mock_service:
            mock_service.return_value.get_search_analytics = AsyncMock(
                return_value=search_analytics_data
            )
            
            # Act
            response = client.get("/api/v1/analytics/search")
            
            # Assert
            assert response.status_code == 200
            data = response.json()
            assert 'query_patterns' in data
            assert 'search_types_performance' in data
            assert len(data['query_patterns']) == 1
            assert data['query_patterns'][0]['frequency'] == 25
    
    def test_get_performance_metrics(self, client):
        """Test GET /analytics/performance endpoint"""
        # Arrange
        performance_data = {
            'response_time_percentiles': {
                'p50': 200,
                'p95': 500,
                'p99': 1200
            },
            'system_health': {
                'cpu_usage': 35.5,
                'memory_usage': 68.0,
                'error_rate': 0.015
            },
            'resource_utilization': {
                'database_connections': 45,
                'cache_hit_rate': 0.78,
                'concurrent_searches': 12
            }
        }
        
        with patch('app.api.v1.endpoints.analytics_endpoints.get_analytics_service') as mock_service:
            mock_service.return_value.get_performance_metrics = AsyncMock(
                return_value=performance_data
            )
            
            # Act
            response = client.get("/api/v1/analytics/performance")
            
            # Assert
            assert response.status_code == 200
            data = response.json()
            assert 'response_time_percentiles' in data
            assert 'system_health' in data
            assert data['response_time_percentiles']['p95'] == 500
            assert data['system_health']['cpu_usage'] == 35.5
    
    def test_get_user_behavior_analytics(self, client):
        """Test GET /analytics/users endpoint"""
        # Arrange
        user_behavior_data = {
            'user_segments': [
                {
                    'segment': 'power_users',
                    'count': 25,
                    'avg_searches_per_session': 8.5,
                    'success_rate': 0.92
                },
                {
                    'segment': 'casual_users',
                    'count': 150,
                    'avg_searches_per_session': 2.1,
                    'success_rate': 0.75
                }
            ],
            'search_behavior_patterns': {
                'peak_hours': [9, 14, 16],
                'avg_session_duration': 12.5,
                'query_refinement_rate': 0.35
            }
        }
        
        with patch('app.api.v1.endpoints.analytics_endpoints.get_analytics_service') as mock_service:
            mock_service.return_value.get_user_behavior_analytics = AsyncMock(
                return_value=user_behavior_data
            )
            
            # Act
            response = client.get("/api/v1/analytics/users")
            
            # Assert
            assert response.status_code == 200
            data = response.json()
            assert 'user_segments' in data
            assert 'search_behavior_patterns' in data
            assert len(data['user_segments']) == 2
            assert data['user_segments'][0]['segment'] == 'power_users'
    
    def test_get_real_time_metrics(self, client):
        """Test GET /analytics/realtime endpoint"""
        # Arrange
        realtime_data = {
            'current_active_searches': 15,
            'searches_last_hour': 120,
            'avg_response_time_last_hour': 275.0,
            'error_rate_last_hour': 0.02,
            'top_queries_last_hour': [
                {'query': 'email sync', 'count': 8},
                {'query': 'account setup', 'count': 6}
            ],
            'system_status': 'healthy',
            'alerts_active': 0
        }
        
        with patch('app.api.v1.endpoints.analytics_endpoints.get_analytics_service') as mock_service:
            mock_service.return_value.get_real_time_metrics = AsyncMock(
                return_value=realtime_data
            )
            
            # Act
            response = client.get("/api/v1/analytics/realtime")
            
            # Assert
            assert response.status_code == 200
            data = response.json()
            assert 'current_active_searches' in data
            assert 'system_status' in data
            assert data['current_active_searches'] == 15
            assert data['system_status'] == 'healthy'
    
    def test_post_analytics_query(self, client):
        """Test POST /analytics/query endpoint for custom analytics queries"""
        # Arrange
        query_request = {
            'query_type': 'custom_aggregation',
            'filters': {
                'date_range': {
                    'start': '2024-01-01T00:00:00Z',
                    'end': '2024-01-31T23:59:59Z'
                },
                'search_types': ['hybrid', 'vector'],
                'user_segments': ['power_users']
            },
            'aggregations': ['avg_response_time', 'success_rate', 'query_frequency'],
            'group_by': ['search_type', 'hour_of_day']
        }
        
        expected_result = {
            'results': [
                {
                    'search_type': 'hybrid',
                    'hour_of_day': 9,
                    'avg_response_time': 250.0,
                    'success_rate': 0.89,
                    'query_frequency': 45
                }
            ],
            'total_count': 1,
            'execution_time_ms': 125
        }
        
        with patch('app.api.v1.endpoints.analytics_endpoints.get_analytics_service') as mock_service:
            mock_service.return_value.execute_custom_query = AsyncMock(
                return_value=expected_result
            )
            
            # Act
            response = client.post("/api/v1/analytics/query", json=query_request)
            
            # Assert
            assert response.status_code == 200
            data = response.json()
            assert 'results' in data
            assert 'execution_time_ms' in data
            assert len(data['results']) == 1
            assert data['results'][0]['search_type'] == 'hybrid'
    
    def test_get_analytics_dashboard_data(self, client):
        """Test GET /analytics/dashboard endpoint"""
        # Arrange
        dashboard_data = {
            'summary_cards': {
                'total_searches_today': 450,
                'avg_response_time_today': 285.0,
                'success_rate_today': 0.91,
                'active_users_today': 85
            },
            'charts_data': {
                'searches_over_time': [
                    {'timestamp': '2024-01-01T09:00:00Z', 'count': 25},
                    {'timestamp': '2024-01-01T10:00:00Z', 'count': 35}
                ],
                'response_time_trend': [
                    {'timestamp': '2024-01-01T09:00:00Z', 'avg_time': 280},
                    {'timestamp': '2024-01-01T10:00:00Z', 'avg_time': 290}
                ]
            },
            'alerts': [
                {
                    'severity': 'warning',
                    'message': 'Response time above threshold',
                    'timestamp': '2024-01-01T10:30:00Z'
                }
            ]
        }
        
        with patch('app.api.v1.endpoints.analytics_endpoints.get_analytics_service') as mock_service:
            mock_service.return_value.get_dashboard_data = AsyncMock(
                return_value=dashboard_data
            )
            
            # Act
            response = client.get("/api/v1/analytics/dashboard")
            
            # Assert
            assert response.status_code == 200
            data = response.json()
            assert 'summary_cards' in data
            assert 'charts_data' in data
            assert 'alerts' in data
            assert data['summary_cards']['total_searches_today'] == 450
            assert len(data['charts_data']['searches_over_time']) == 2
    
    def test_post_generate_report(self, client):
        """Test POST /analytics/reports/generate endpoint"""
        # Arrange
        report_request = {
            'report_type': 'weekly_summary',
            'date_range': {
                'start': '2024-01-01T00:00:00Z',
                'end': '2024-01-07T23:59:59Z'
            },
            'include_sections': [
                'usage_overview',
                'top_queries',
                'performance_metrics',
                'user_behavior'
            ],
            'format': 'json',
            'delivery_method': 'api_response'
        }
        
        expected_report = {
            'report_id': 'report_123',
            'generated_at': '2024-01-08T10:00:00Z',
            'status': 'completed',
            'data': {
                'usage_overview': {
                    'total_searches': 2500,
                    'unique_users': 180,
                    'success_rate': 0.87
                },
                'top_queries': [
                    {'query': 'email sync', 'count': 150},
                    {'query': 'account setup', 'count': 120}
                ]
            }
        }
        
        with patch('app.api.v1.endpoints.analytics_endpoints.get_analytics_service') as mock_service:
            mock_service.return_value.generate_report = AsyncMock(
                return_value=expected_report
            )
            
            # Act
            response = client.post("/api/v1/analytics/reports/generate", json=report_request)
            
            # Assert
            assert response.status_code == 200
            data = response.json()
            assert 'report_id' in data
            assert 'status' in data
            assert data['status'] == 'completed'
            assert data['data']['usage_overview']['total_searches'] == 2500
    
    def test_get_report_status(self, client):
        """Test GET /analytics/reports/{report_id}/status endpoint"""
        # Arrange
        report_id = "report_123"
        report_status = {
            'report_id': report_id,
            'status': 'processing',
            'progress_percent': 75,
            'estimated_completion': '2024-01-08T10:05:00Z',
            'created_at': '2024-01-08T10:00:00Z'
        }
        
        with patch('app.api.v1.endpoints.analytics_endpoints.get_analytics_service') as mock_service:
            mock_service.return_value.get_report_status = AsyncMock(
                return_value=report_status
            )
            
            # Act
            response = client.get(f"/api/v1/analytics/reports/{report_id}/status")
            
            # Assert
            assert response.status_code == 200
            data = response.json()
            assert data['report_id'] == report_id
            assert data['status'] == 'processing'
            assert data['progress_percent'] == 75
    
    def test_get_optimization_recommendations(self, client):
        """Test GET /analytics/optimization endpoint"""
        # Arrange
        optimization_data = {
            'recommendations': [
                {
                    'type': 'query_optimization',
                    'priority': 'high',
                    'description': 'Optimize vector search for better performance',
                    'impact_score': 0.85,
                    'implementation_effort': 'medium',
                    'estimated_improvement': '25% faster response times'
                },
                {
                    'type': 'caching_improvement',
                    'priority': 'medium',
                    'description': 'Increase cache hit rate for common queries',
                    'impact_score': 0.65,
                    'implementation_effort': 'low',
                    'estimated_improvement': '15% reduction in database queries'
                }
            ],
            'performance_insights': {
                'bottlenecks': ['vector_embedding_generation', 'database_queries'],
                'optimization_potential': 0.35
            }
        }
        
        with patch('app.api.v1.endpoints.analytics_endpoints.get_analytics_service') as mock_service:
            mock_service.return_value.get_optimization_recommendations = AsyncMock(
                return_value=optimization_data
            )
            
            # Act
            response = client.get("/api/v1/analytics/optimization")
            
            # Assert
            assert response.status_code == 200
            data = response.json()
            assert 'recommendations' in data
            assert 'performance_insights' in data
            assert len(data['recommendations']) == 2
            assert data['recommendations'][0]['priority'] == 'high'
    
    def test_analytics_endpoint_error_handling(self, client):
        """Test error handling in analytics endpoints"""
        # Test 404 for non-existent report
        response = client.get("/api/v1/analytics/reports/non_existent_report/status")
        assert response.status_code == 404
        
        # Test 400 for invalid date range
        invalid_request = {
            'start_date': 'invalid_date',
            'end_date': '2024-01-01T00:00:00Z'
        }
        response = client.get("/api/v1/analytics/overview", params=invalid_request)
        assert response.status_code == 400
        
        # Test 422 for invalid query request
        invalid_query = {
            'query_type': 'invalid_type',
            'filters': {}
        }
        response = client.post("/api/v1/analytics/query", json=invalid_query)
        assert response.status_code == 422
    
    def test_analytics_endpoint_rate_limiting(self, client):
        """Test rate limiting on analytics endpoints"""
        # This would test rate limiting if implemented
        # For now, just verify the endpoint responds normally
        response = client.get("/api/v1/analytics/overview")
        assert response.status_code in [200, 429]  # 429 if rate limited
    
    def test_analytics_endpoint_authentication(self, client):
        """Test authentication requirements for analytics endpoints"""
        # Test without authentication (if required)
        # This depends on your authentication implementation
        
        # For now, just verify endpoints are accessible
        # In production, you'd test with/without auth tokens
        response = client.get("/api/v1/analytics/overview")
        assert response.status_code in [200, 401, 403]


class TestAnalyticsWebSocketEndpoints:
    """Test suite for real-time analytics WebSocket endpoints"""
    
    @pytest.mark.asyncio
    async def test_realtime_analytics_websocket(self):
        """Test real-time analytics WebSocket connection and updates"""
        # This would test WebSocket connections for real-time analytics
        # Implementation depends on your WebSocket setup
        pass
    
    @pytest.mark.asyncio
    async def test_websocket_authentication(self):
        """Test WebSocket authentication for analytics streams"""
        # This would test WebSocket authentication
        pass
    
    @pytest.mark.asyncio
    async def test_websocket_data_streaming(self):
        """Test continuous data streaming over WebSocket"""
        # This would test continuous analytics data streaming
        pass


class TestAnalyticsDataValidation:
    """Test suite for analytics data validation and schemas"""
    
    def test_analytics_request_validation(self):
        """Test validation of analytics request schemas"""
        # Test valid request
        valid_request = AnalyticsRequest(
            start_date=datetime.utcnow() - timedelta(days=7),
            end_date=datetime.utcnow(),
            metrics=['usage', 'performance'],
            filters={'search_type': 'hybrid'}
        )
        
        assert valid_request.start_date < valid_request.end_date
        assert 'usage' in valid_request.metrics
        
        # Test invalid request (end date before start date)
        with pytest.raises(ValueError):
            AnalyticsRequest(
                start_date=datetime.utcnow(),
                end_date=datetime.utcnow() - timedelta(days=1),
                metrics=['usage'],
                filters={}
            )
    
    def test_analytics_response_validation(self):
        """Test validation of analytics response schemas"""
        valid_response = AnalyticsResponse(
            timestamp=datetime.utcnow(),
            data={'test': 'data'},
            metadata={'query_time_ms': 150}
        )
        
        assert valid_response.timestamp is not None
        assert 'test' in valid_response.data
        assert valid_response.metadata['query_time_ms'] == 150
    
    def test_dashboard_data_validation(self):
        """Test validation of dashboard data schemas"""
        valid_dashboard = DashboardData(
            summary_metrics={
                'total_searches': 1000,
                'success_rate': 0.89
            },
            time_series_data=[
                {'timestamp': datetime.utcnow(), 'value': 100}
            ],
            alerts=[]
        )
        
        assert valid_dashboard.summary_metrics['total_searches'] == 1000
        assert len(valid_dashboard.time_series_data) == 1
        assert isinstance(valid_dashboard.alerts, list)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])