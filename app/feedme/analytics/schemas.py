"""
Analytics Data Models and Schemas for FeedMe v2.0 Phase 2
Comprehensive Pydantic models for analytics data structures, validation, and API contracts.
"""

from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Union, Literal
from pydantic import BaseModel, Field, field_validator, model_validator
from enum import Enum


class AlertSeverity(str, Enum):
    """Alert severity levels"""
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


class SearchType(str, Enum):
    """Types of search operations"""
    HYBRID = "hybrid"
    VECTOR = "vector"
    TEXT = "text"


class UserSegment(str, Enum):
    """User behavior segments"""
    EXPERT = "expert"
    INTERMEDIATE = "intermediate"
    BEGINNER = "beginner"
    POWER_USER = "power_user"
    CASUAL_USER = "casual_user"


class OptimizationType(str, Enum):
    """Types of optimization recommendations"""
    QUERY_OPTIMIZATION = "query_optimization"
    CACHING_IMPROVEMENT = "caching_improvement"
    DATABASE_OPTIMIZATION = "database_optimization"
    MEMORY_OPTIMIZATION = "memory_optimization"
    ALGORITHM_IMPROVEMENT = "algorithm_improvement"


# Core Analytics Models

class SearchEvent(BaseModel):
    """Individual search event for tracking"""
    user_id: str
    query: str
    timestamp: datetime
    results_count: int
    response_time_ms: float
    clicked_results: List[int] = Field(default_factory=list)
    conversation_id: Optional[int] = None
    search_type: SearchType
    context_data: Dict[str, Any] = Field(default_factory=dict)
    
    model_config = {"from_attributes": True}


class SearchSession(BaseModel):
    """Search session containing multiple related searches"""
    session_id: str
    user_id: str
    start_time: datetime
    end_time: datetime
    searches: List[Dict[str, Any]]
    success_rate: float = Field(ge=0.0, le=1.0)
    avg_response_time: float = Field(ge=0.0)
    
    @field_validator('end_time')
    @classmethod
    def end_time_after_start_time(cls, v, info):
        if 'start_time' in info.data and v <= info.data['start_time']:
            raise ValueError('end_time must be after start_time')
        return v
    
    model_config = {"from_attributes": True}


class UsageMetrics(BaseModel):
    """Core usage metrics"""
    total_searches: int = Field(ge=0)
    unique_users: int = Field(ge=0)
    avg_response_time: float = Field(ge=0.0)
    click_through_rate: float = Field(ge=0.0, le=1.0)
    success_rate: float = Field(ge=0.0, le=1.0)
    timestamp: datetime
    
    model_config = {"from_attributes": True}


class SearchBehaviorMetrics(BaseModel):
    """Search behavior analysis metrics"""
    total_sessions: int = Field(ge=0)
    avg_session_duration_minutes: float = Field(ge=0.0)
    avg_queries_per_session: float = Field(ge=0.0)
    overall_success_rate: float = Field(ge=0.0, le=1.0)
    query_refinement_rate: float = Field(ge=0.0, le=1.0)
    timestamp: datetime
    
    model_config = {"from_attributes": True}


# SearchAnalytics removed - search functionality eliminated


class SystemPerformanceMetrics(BaseModel):
    """System performance metrics"""
    avg_search_time_ms: float = Field(ge=0.0)
    p95_search_time_ms: float = Field(ge=0.0)
    p99_search_time_ms: float = Field(ge=0.0)
    error_rate: float = Field(ge=0.0, le=1.0)
    cache_hit_rate: float = Field(ge=0.0, le=1.0)
    concurrent_searches: int = Field(ge=0)
    peak_concurrent_searches: int = Field(ge=0)
    
    @field_validator('p95_search_time_ms')
    @classmethod
    def p95_greater_than_avg(cls, v, info):
        if 'avg_search_time_ms' in info.data and v < info.data['avg_search_time_ms']:
            raise ValueError('p95 must be >= average response time')
        return v
    
    @field_validator('p99_search_time_ms')
    @classmethod
    def p99_greater_than_p95(cls, v, info):
        if 'p95_search_time_ms' in info.data and v < info.data['p95_search_time_ms']:
            raise ValueError('p99 must be >= p95 response time')
        return v
    
    model_config = {"from_attributes": True}


class UserBehaviorAnalytics(BaseModel):
    """User behavior analytics"""
    user_segments: List[Dict[str, Any]]
    search_patterns_by_segment: Dict[str, Any]
    temporal_patterns: Dict[str, Any]
    retention_metrics: Dict[str, Any]
    
    model_config = {"from_attributes": True}


class QueryPattern(BaseModel):
    """Query pattern analysis"""
    query: str
    frequency: int = Field(ge=0)
    avg_response_time: float = Field(ge=0.0)
    success_rate: float = Field(ge=0.0, le=1.0)
    related_queries: List[str] = Field(default_factory=list)
    intent_category: Optional[str] = None
    complexity_level: int = Field(ge=1, le=5)
    
    model_config = {"from_attributes": True}


class SearchPerformanceData(BaseModel):
    """Detailed search performance data"""
    timestamp: datetime
    search_id: str
    query: str
    search_type: SearchType
    response_time_ms: float = Field(ge=0.0)
    results_count: int = Field(ge=0)
    cache_hit: bool
    database_query_time_ms: float = Field(ge=0.0)
    embedding_time_ms: float = Field(ge=0.0)
    ranking_time_ms: float = Field(ge=0.0)
    memory_usage_mb: float = Field(ge=0.0)
    cpu_usage_percent: float = Field(ge=0.0, le=100.0)
    error_occurred: bool
    error_type: Optional[str] = None
    
    model_config = {"from_attributes": True}


# Health Monitoring Models

class SystemHealthMetrics(BaseModel):
    """System health metrics"""
    timestamp: datetime
    cpu_usage_percent: float = Field(ge=0.0, le=100.0)
    memory_usage_percent: float = Field(ge=0.0, le=100.0)
    disk_usage_percent: float = Field(ge=0.0, le=100.0)
    network_io_mbps: float = Field(ge=0.0)
    active_connections: int = Field(ge=0)
    
    model_config = {"from_attributes": True}


class ComponentHealth(BaseModel):
    """Individual component health status"""
    component_name: str
    status: Literal["healthy", "warning", "critical"]
    response_time_ms: Optional[float] = Field(ge=0.0)
    last_error: Optional[str] = None
    metrics: Dict[str, Any] = Field(default_factory=dict)
    
    model_config = {"from_attributes": True}


class HealthStatus(BaseModel):
    """Overall system health status"""
    timestamp: datetime
    overall_status: Literal["healthy", "warning", "critical"]
    components: Dict[str, Dict[str, Any]]
    system_metrics: Dict[str, float]
    alerts_count: int = Field(ge=0, default=0)
    
    model_config = {"from_attributes": True}


class HealthAlert(BaseModel):
    """Health monitoring alert"""
    id: str
    timestamp: datetime
    severity: AlertSeverity
    component: str
    message: str
    details: Dict[str, Any] = Field(default_factory=dict)
    resolved: bool = False
    resolution_time: Optional[datetime] = None
    
    model_config = {"from_attributes": True}


class MonitoringConfig(BaseModel):
    """Monitoring configuration"""
    check_interval_seconds: int = Field(ge=1, default=30)
    alert_thresholds: Dict[str, float]
    critical_services: List[str]
    notification_channels: List[str] = Field(default_factory=list)
    
    model_config = {"from_attributes": True}


# Analytics Response Models

class AnalyticsInsights(BaseModel):
    """Comprehensive analytics insights"""
    total_searches: int = Field(ge=0)
    unique_users: int = Field(ge=0)
    avg_response_time: float = Field(ge=0.0)
    click_through_rate: float = Field(ge=0.0, le=1.0)
    success_rate: float = Field(ge=0.0, le=1.0)
    top_queries: List[Dict[str, Any]] = Field(default_factory=list)
    performance_trends: Dict[str, Any] = Field(default_factory=dict)
    optimization_opportunities: List[Dict[str, Any]] = Field(default_factory=list)
    
    model_config = {"from_attributes": True}


class OptimizationRecommendation(BaseModel):
    """Optimization recommendation"""
    type: OptimizationType
    priority: Literal["low", "medium", "high"]
    description: str
    impact_score: float = Field(ge=0.0, le=1.0)
    implementation_effort: Literal["low", "medium", "high"]
    estimated_improvement: str
    technical_details: Dict[str, Any] = Field(default_factory=dict)
    
    model_config = {"from_attributes": True}


class OptimizationInsight(BaseModel):
    """Performance optimization insight"""
    insight_type: str
    current_value: float
    target_value: float
    improvement_potential: float = Field(ge=0.0, le=1.0)
    recommendations: List[OptimizationRecommendation]
    
    model_config = {"from_attributes": True}


# API Request/Response Models

class AnalyticsRequest(BaseModel):
    """Analytics API request"""
    start_date: datetime
    end_date: datetime
    metrics: List[str]
    filters: Dict[str, Any] = Field(default_factory=dict)
    group_by: Optional[List[str]] = None
    
    @field_validator('end_date')
    @classmethod
    def end_date_after_start_date(cls, v, info):
        if 'start_date' in info.data and v <= info.data['start_date']:
            raise ValueError('end_date must be after start_date')
        return v
    
    @field_validator('start_date', 'end_date')
    @classmethod
    def reasonable_date_range(cls, v):
        now = datetime.utcnow()
        if v > now:
            raise ValueError('Date cannot be in the future')
        if v < now - timedelta(days=365):
            raise ValueError('Date cannot be more than 1 year ago')
        return v
    
    model_config = {"from_attributes": True}


class AnalyticsResponse(BaseModel):
    """Analytics API response"""
    timestamp: datetime
    data: Dict[str, Any]
    metadata: Dict[str, Any] = Field(default_factory=dict)
    execution_time_ms: Optional[float] = None
    
    model_config = {"from_attributes": True}


class DashboardData(BaseModel):
    """Dashboard data structure"""
    summary_metrics: Dict[str, Union[int, float, str]]
    time_series_data: List[Dict[str, Any]]
    alerts: List[HealthAlert]
    last_updated: datetime = Field(default_factory=datetime.utcnow)
    
    model_config = {"from_attributes": True}


class ReportConfig(BaseModel):
    """Report generation configuration"""
    report_type: str
    date_range: Dict[str, datetime]
    include_sections: List[str]
    format: Literal["json", "pdf", "csv"] = "json"
    delivery_method: Literal["api_response", "email", "file"] = "api_response"
    
    @model_validator(mode='after')
    def validate_date_range(self):
        date_range = self.date_range or {}
        if 'start' in date_range and 'end' in date_range:
            if date_range['end'] <= date_range['start']:
                raise ValueError('End date must be after start date')
        return self
    
    model_config = {"from_attributes": True}


# Advanced Analytics Models

class TrendAnalysis(BaseModel):
    """Trend analysis data"""
    metric_name: str
    trend_direction: Literal["increasing", "decreasing", "stable"]
    trend_strength: float = Field(ge=0.0, le=1.0)
    data_points: List[Dict[str, Any]]
    prediction: Optional[Dict[str, Any]] = None
    
    model_config = {"from_attributes": True}


class AnomalyDetection(BaseModel):
    """Anomaly detection result"""
    timestamp: datetime
    metric_name: str
    value: float
    expected_value: float
    anomaly_score: float = Field(ge=0.0, le=1.0)
    anomaly_type: Literal["spike", "drop", "pattern_change"]
    context: Dict[str, Any] = Field(default_factory=dict)
    
    model_config = {"from_attributes": True}


class PerformanceBenchmark(BaseModel):
    """Performance benchmark data"""
    benchmark_name: str
    target_value: float
    current_value: float
    measurement_unit: str
    performance_ratio: float = Field(ge=0.0)
    meets_target: bool
    improvement_needed: Optional[float] = None
    
    @field_validator('performance_ratio', mode='before')
    @classmethod
    def calculate_performance_ratio(cls, v, info):
        if 'current_value' in info.data and 'target_value' in info.data:
            target = info.data['target_value']
            current = info.data['current_value']
            if target > 0:
                return current / target
        return v or 0.0
    
    @field_validator('meets_target', mode='before')
    @classmethod
    def calculate_meets_target(cls, v, info):
        if 'performance_ratio' in info.data:
            return info.data['performance_ratio'] >= 1.0
        return v or False
    
    model_config = {"from_attributes": True}


class SystemComponents:
    """System components enumeration"""
    DATABASE = "database"
    REDIS = "redis"
    SEARCH_ENGINE = "search_engine"
    AI_MODELS = "ai_models"
    WEB_SERVER = "web_server"
    TASK_QUEUE = "task_queue"


# Validation Utilities

def validate_percentage(value: float) -> float:
    """Validate percentage values (0.0 to 1.0)"""
    if not 0.0 <= value <= 1.0:
        raise ValueError(f"Percentage must be between 0.0 and 1.0, got {value}")
    return value


def validate_positive_number(value: float) -> float:
    """Validate positive numbers"""
    if value < 0:
        raise ValueError(f"Value must be positive, got {value}")
    return value


def validate_response_time(value: float) -> float:
    """Validate response time values (must be positive and reasonable)"""
    if value < 0:
        raise ValueError(f"Response time must be positive, got {value}")
    if value > 60000:  # More than 1 minute is suspicious
        raise ValueError(f"Response time seems unreasonably high: {value}ms")
    return value


# Export all models for easy importing
__all__ = [
    # Enums
    "AlertSeverity", "SearchType", "UserSegment", "OptimizationType",
    
    # Core Analytics  
    "SearchEvent", "SearchSession", "UsageMetrics", "SearchBehaviorMetrics",
    "SystemPerformanceMetrics", "UserBehaviorAnalytics",
    "QueryPattern", "SearchPerformanceData",
    
    # Health Monitoring
    "SystemHealthMetrics", "ComponentHealth", "HealthStatus", "HealthAlert",
    "MonitoringConfig",
    
    # Analytics Insights
    "AnalyticsInsights", "OptimizationRecommendation", "OptimizationInsight",
    
    # API Models
    "AnalyticsRequest", "AnalyticsResponse", "DashboardData", "ReportConfig",
    
    # Advanced Analytics
    "TrendAnalysis", "AnomalyDetection", "PerformanceBenchmark", "SystemComponents",
    
    # Validation Functions
    "validate_percentage", "validate_positive_number", "validate_response_time"
]