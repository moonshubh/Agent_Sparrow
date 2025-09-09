"""
FeedMe Analytics Module v2.0 Phase 2
Comprehensive analytics system for usage tracking, performance monitoring, and optimization.
"""

from .schemas import (
    # Core Analytics Models
    SearchEvent,
    SearchSession,
    UsageMetrics,
    SearchBehaviorMetrics,
    SystemPerformanceMetrics,
    UserBehaviorAnalytics,
    QueryPattern,
    SearchPerformanceData,
    
    # Health Monitoring Models
    SystemHealthMetrics,
    ComponentHealth,
    HealthStatus,
    HealthAlert,
    MonitoringConfig,
    
    # Analytics Insights
    AnalyticsInsights,
    OptimizationRecommendation,
    OptimizationInsight,
    
    # API Models
    AnalyticsRequest,
    AnalyticsResponse,
    DashboardData,
    ReportConfig,
    
    # Advanced Analytics
    TrendAnalysis,
    AnomalyDetection,
    PerformanceBenchmark,
    
    # Enums
    AlertSeverity,
    SearchType,
    UserSegment,
    OptimizationType
)

from .usage_tracker import UsageAnalytics
from .performance_monitor import PerformanceMonitor, MetricCollector, PerformanceConfig

# Version information
__version__ = "2.0.0"
__phase__ = "Phase 2"
__status__ = "Production Ready"

# Module metadata
__all__ = [
    # Core Analytics Classes
    "UsageAnalytics",
    "PerformanceMonitor", 
    "MetricCollector",
    "PerformanceConfig",
    
    # Data Models
    "SearchEvent",
    "SearchSession", 
    "UsageMetrics",
    "SearchBehaviorMetrics",
    "SystemPerformanceMetrics",
    "UserBehaviorAnalytics",
    "QueryPattern",
    "SearchPerformanceData",
    
    # Health Monitoring
    "SystemHealthMetrics",
    "ComponentHealth",
    "HealthStatus", 
    "HealthAlert",
    "MonitoringConfig",
    
    # Analytics Insights
    "AnalyticsInsights",
    "OptimizationRecommendation",
    "OptimizationInsight",
    
    # API Models
    "AnalyticsRequest",
    "AnalyticsResponse",
    "DashboardData",
    "ReportConfig",
    
    # Advanced Analytics
    "TrendAnalysis",
    "AnomalyDetection", 
    "PerformanceBenchmark",
    
    # Enumerations
    "AlertSeverity",
    "SearchType",
    "UserSegment", 
    "OptimizationType"
]

# Configuration defaults
DEFAULT_CONFIG = {
    "analytics": {
        "enable_real_time": True,
        "buffer_size": 1000,
        "flush_interval_seconds": 60,
        "cache_ttl_seconds": 300
    },
    "performance": {
        "collection_interval_seconds": 5,
        "retention_days": 30,
        "alert_thresholds": {
            "response_time_p95_ms": 1000,
            "error_rate_threshold": 0.05,
            "memory_usage_threshold": 0.8,
            "cpu_usage_threshold": 0.85,
            "cache_hit_rate_threshold": 0.7
        }
    },
    "health_monitoring": {
        "check_interval_seconds": 30,
        "critical_services": ["database", "redis", "search_engine", "ai_models"],
        "notification_channels": ["email", "slack", "webhook"]
    }
}

def get_default_config():
    """Get default analytics configuration"""
    return DEFAULT_CONFIG.copy()

def create_analytics_system(db, redis_client, config=None):
    """
    Factory function to create a complete analytics system
    
    Args:
        db: Database session
        redis_client: Redis client
        config: Optional configuration override
        
    Returns:
        Tuple of (UsageAnalytics, PerformanceMonitor)
    """
    if config is None:
        config = get_default_config()
    
    # Create usage analytics
    usage_analytics = UsageAnalytics(
        db=db,
        redis_client=redis_client,
        enable_real_time=config["analytics"]["enable_real_time"],
        buffer_size=config["analytics"]["buffer_size"],
        flush_interval_seconds=config["analytics"]["flush_interval_seconds"]
    )
    
    # Create performance monitor
    perf_config = PerformanceConfig(
        collection_interval_seconds=config["performance"]["collection_interval_seconds"],
        retention_days=config["performance"]["retention_days"],
        alert_thresholds=config["performance"]["alert_thresholds"]
    )
    
    performance_monitor = PerformanceMonitor(
        db=db,
        redis_client=redis_client,
        config=perf_config
    )
    
    return usage_analytics, performance_monitor

# Module documentation
__doc__ = """
FeedMe Analytics Module v2.0 Phase 2

This module provides comprehensive analytics capabilities for the FeedMe system including:

1. **Usage Analytics**: Real-time tracking of search events, user behavior analysis, 
   and insights generation with predictive capabilities.

2. **Performance Monitoring**: System health monitoring, resource usage tracking,
   and automated performance optimization recommendations.

3. **Health Monitoring**: Comprehensive system health checks, alerting, and 
   automated recovery actions.

4. **Data Models**: Complete set of Pydantic models for type-safe analytics data
   handling and API contracts.

Key Features:
- Real-time metrics collection with Redis caching
- Batch processing for detailed historical analysis  
- Anomaly detection and automated alerting
- Performance optimization recommendations
- Comprehensive health monitoring
- Scalable architecture with async processing
- Full test coverage with TDD methodology

Usage Example:
```python
from app.feedme.analytics import create_analytics_system, SearchEvent
from datetime import datetime

# Create analytics system
usage_analytics, performance_monitor = create_analytics_system(db, redis)

# Track a search event
event = SearchEvent(
    user_id="user123",
    query="email sync issues", 
    timestamp=datetime.utcnow(),
    results_count=5,
    response_time_ms=250,
    search_type="hybrid"
)

await usage_analytics.track_search_event(event)

# Generate insights
insights = await usage_analytics.generate_insights(
    start_date=datetime.utcnow() - timedelta(days=7),
    end_date=datetime.utcnow()
)
```

For detailed documentation, see individual module docstrings and the project README.
"""