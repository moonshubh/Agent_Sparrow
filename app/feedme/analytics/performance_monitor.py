"""
Performance Monitor for FeedMe v2.0 Phase 2
Comprehensive performance monitoring, metrics collection, and optimization analysis.
"""

# mypy: ignore-errors

import json
import time
import psutil
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from contextlib import asynccontextmanager
import logging
from dataclasses import dataclass, field

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
import redis.asyncio as redis
import numpy as np
from collections import deque, defaultdict

from .schemas import (
    SearchPerformanceData,
    SystemHealthMetrics,
    OptimizationRecommendation,
    OptimizationType,
)

logger = logging.getLogger(__name__)


@dataclass
class PerformanceConfig:
    """Performance monitoring configuration"""

    collection_interval_seconds: int = 5
    retention_days: int = 30
    alert_thresholds: Dict[str, float] = field(
        default_factory=lambda: {
            "response_time_p95_ms": 1000,
            "error_rate_threshold": 0.05,
            "memory_usage_threshold": 0.8,
            "cpu_usage_threshold": 0.85,
            "cache_hit_rate_threshold": 0.7,
        }
    )
    optimization_thresholds: Dict[str, float] = field(
        default_factory=lambda: {
            "slow_query_ms": 1000,
            "high_memory_mb": 500,
            "low_cache_hit_rate": 0.6,
        }
    )


class TimingContext:
    """Context manager for measuring execution time"""

    def __init__(self):
        self.start_time = None
        self.end_time = None
        self.elapsed_ms = 0

    def __enter__(self):
        self.start_time = time.perf_counter()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.end_time = time.perf_counter()
        self.elapsed_ms = (self.end_time - self.start_time) * 1000


class PerformanceMonitor:
    """
    Comprehensive performance monitoring system with real-time metrics,
    health checks, and optimization recommendations.
    """

    def __init__(
        self,
        db: AsyncSession,
        redis_client: redis.Redis,
        config: Optional[PerformanceConfig] = None,
    ):
        self.db = db
        self.redis = redis_client
        self.config = config or PerformanceConfig()

        # Metrics buffer for batch processing
        self._metrics_buffer: deque = deque(maxlen=1000)

        # Performance tracking
        self._performance_history = defaultdict(lambda: deque(maxlen=100))

        # Alert management
        self._alert_history = deque(maxlen=500)
        self._last_alert_times = {}

        # System resource monitoring
        self._system_metrics = {
            "cpu_samples": deque(maxlen=60),  # 1 minute of samples
            "memory_samples": deque(maxlen=60),
            "disk_samples": deque(maxlen=60),
        }

    async def collect_search_metrics(
        self, performance_data: SearchPerformanceData
    ) -> None:
        """Collect search performance metrics with real-time analysis"""
        try:
            # Add to buffer for batch processing
            self._metrics_buffer.append(performance_data)

            # Update real-time metrics
            await self._update_performance_metrics(performance_data)

            # Check for performance alerts
            await self._check_performance_thresholds(performance_data)

            # Update performance history for trend analysis
            self._update_performance_history(performance_data)

        except Exception as e:
            logger.error(f"Error collecting search metrics: {e}")

    async def _update_performance_metrics(self, data: SearchPerformanceData) -> None:
        """Update real-time performance metrics in Redis"""
        current_minute = datetime.utcnow().strftime("%Y-%m-%d-%H-%M")

        pipe = self.redis.pipeline()

        # Response time metrics
        pipe.lpush(
            f"feedme:perf:response_times:{current_minute}", data.response_time_ms
        )
        pipe.ltrim(f"feedme:perf:response_times:{current_minute}", 0, 199)
        pipe.expire(f"feedme:perf:response_times:{current_minute}", 3600)

        # Database performance
        pipe.lpush(
            f"feedme:perf:db_times:{current_minute}", data.database_query_time_ms
        )
        pipe.ltrim(f"feedme:perf:db_times:{current_minute}", 0, 199)
        pipe.expire(f"feedme:perf:db_times:{current_minute}", 3600)

        # Memory usage
        pipe.lpush(f"feedme:perf:memory:{current_minute}", data.memory_usage_mb)
        pipe.ltrim(f"feedme:perf:memory:{current_minute}", 0, 199)
        pipe.expire(f"feedme:perf:memory:{current_minute}", 3600)

        # Cache performance
        cache_status = 1 if data.cache_hit else 0
        pipe.lpush(f"feedme:perf:cache_hits:{current_minute}", cache_status)
        pipe.ltrim(f"feedme:perf:cache_hits:{current_minute}", 0, 199)
        pipe.expire(f"feedme:perf:cache_hits:{current_minute}", 3600)

        # Error tracking
        error_status = 1 if data.error_occurred else 0
        pipe.lpush(f"feedme:perf:errors:{current_minute}", error_status)
        pipe.ltrim(f"feedme:perf:errors:{current_minute}", 0, 199)
        pipe.expire(f"feedme:perf:errors:{current_minute}", 3600)

        await pipe.execute()

    async def _check_performance_thresholds(self, data: SearchPerformanceData) -> None:
        """Check performance data against alert thresholds"""
        alerts = []

        # Response time threshold
        if data.response_time_ms > self.config.alert_thresholds["response_time_p95_ms"]:
            alerts.append(
                {
                    "type": "slow_response",
                    "severity": "warning",
                    "metric": "response_time",
                    "value": data.response_time_ms,
                    "threshold": self.config.alert_thresholds["response_time_p95_ms"],
                    "search_id": data.search_id,
                }
            )

        # Memory usage threshold
        memory_usage_percent = (
            data.memory_usage_mb / 1024
        ) * 100  # Assuming 1GB baseline
        if (
            memory_usage_percent
            > self.config.alert_thresholds["memory_usage_threshold"] * 100
        ):
            alerts.append(
                {
                    "type": "high_memory_usage",
                    "severity": "warning",
                    "metric": "memory_usage",
                    "value": memory_usage_percent,
                    "threshold": self.config.alert_thresholds["memory_usage_threshold"]
                    * 100,
                    "search_id": data.search_id,
                }
            )

        # CPU usage threshold
        if (
            data.cpu_usage_percent
            > self.config.alert_thresholds["cpu_usage_threshold"] * 100
        ):
            alerts.append(
                {
                    "type": "high_cpu_usage",
                    "severity": "warning",
                    "metric": "cpu_usage",
                    "value": data.cpu_usage_percent,
                    "threshold": self.config.alert_thresholds["cpu_usage_threshold"]
                    * 100,
                    "search_id": data.search_id,
                }
            )

        # Error threshold
        if data.error_occurred:
            alerts.append(
                {
                    "type": "search_error",
                    "severity": (
                        "critical"
                        if data.error_type in ["timeout", "system_error"]
                        else "warning"
                    ),
                    "metric": "error_occurrence",
                    "error_type": data.error_type,
                    "search_id": data.search_id,
                }
            )

        # Send alerts
        for alert in alerts:
            await self._send_performance_alert(alert)

    async def _send_performance_alert(self, alert: Dict[str, Any]) -> None:
        """Send performance alert to monitoring system"""
        alert_data = {
            **alert,
            "timestamp": datetime.utcnow().isoformat(),
            "component": "feedme_search",
        }

        # Store in Redis for real-time access
        await self.redis.lpush("feedme:performance_alerts", json.dumps(alert_data))
        await self.redis.ltrim("feedme:performance_alerts", 0, 99)

        # Add to alert history
        self._alert_history.append(alert_data)

        logger.warning(
            f"Performance alert: {alert['type']} - {alert.get('metric', 'N/A')}"
        )

    def _update_performance_history(self, data: SearchPerformanceData) -> None:
        """Update performance history for trend analysis"""
        self._performance_history["response_times"].append(data.response_time_ms)
        self._performance_history["memory_usage"].append(data.memory_usage_mb)
        self._performance_history["cpu_usage"].append(data.cpu_usage_percent)
        self._performance_history["database_times"].append(data.database_query_time_ms)
        self._performance_history["embedding_times"].append(data.embedding_time_ms)

    async def collect_system_health(self) -> SystemHealthMetrics:
        """Collect comprehensive system health metrics"""
        try:
            # CPU usage
            cpu_percent = psutil.cpu_percent(interval=0.1)

            # Memory usage
            memory = psutil.virtual_memory()

            # Disk usage
            disk = psutil.disk_usage("/")

            # Network I/O
            network = psutil.net_io_counters()
            network_io_mbps = (network.bytes_sent + network.bytes_recv) / (1024 * 1024)

            # Active connections (approximate)
            connections = len(psutil.net_connections())

            health_metrics = SystemHealthMetrics(
                timestamp=datetime.utcnow(),
                cpu_usage_percent=cpu_percent,
                memory_usage_percent=memory.percent,
                disk_usage_percent=disk.percent,
                network_io_mbps=network_io_mbps,
                active_connections=connections,
            )

            # Update system metrics history
            self._system_metrics["cpu_samples"].append(cpu_percent)
            self._system_metrics["memory_samples"].append(memory.percent)
            self._system_metrics["disk_samples"].append(disk.percent)

            return health_metrics

        except Exception as e:
            logger.error(f"Error collecting system health: {e}")
            raise

    async def check_database_health(self) -> Dict[str, Any]:
        """Check database health and performance"""
        try:
            start_time = time.perf_counter()

            # Test database connectivity and responsiveness
            query = text("SELECT 1 as status, NOW() as timestamp")
            await self.db.fetch_one(query)

            end_time = time.perf_counter()
            response_time_ms = (end_time - start_time) * 1000

            # Get connection pool stats (if available)
            connection_count = getattr(self.db.bind.pool, "size", 0)

            health_status = {
                "status": "healthy" if response_time_ms < 1000 else "warning",
                "response_time_ms": response_time_ms,
                "connection_count": connection_count,
                "timestamp": datetime.utcnow().isoformat(),
            }

            # Check for slow response
            if response_time_ms > self.config.alert_thresholds.get(
                "database_response_time_ms", 1000
            ):
                health_status["alert_triggered"] = True
                await self._send_performance_alert(
                    {
                        "type": "slow_database",
                        "severity": "warning",
                        "metric": "database_response_time",
                        "value": response_time_ms,
                        "threshold": 1000,
                    }
                )

            return health_status

        except Exception as e:
            logger.error(f"Database health check failed: {e}")
            return {
                "status": "critical",
                "error": str(e),
                "timestamp": datetime.utcnow().isoformat(),
            }

    async def check_redis_health(self) -> Dict[str, Any]:
        """Check Redis health and performance"""
        try:
            start_time = time.perf_counter()

            # Test Redis connectivity
            await self.redis.ping()

            end_time = time.perf_counter()
            response_time_ms = (end_time - start_time) * 1000

            # Get Redis info
            info = await self.redis.info()

            memory_usage_mb = info.get("used_memory", 0) / (1024 * 1024)
            max_memory_mb = info.get("maxmemory", 0) / (1024 * 1024)
            memory_usage_percent = (
                (memory_usage_mb / max_memory_mb * 100) if max_memory_mb > 0 else 0
            )

            # Calculate cache hit rate
            keyspace_hits = info.get("keyspace_hits", 0)
            keyspace_misses = info.get("keyspace_misses", 0)
            total_requests = keyspace_hits + keyspace_misses
            cache_hit_rate = keyspace_hits / total_requests if total_requests > 0 else 0

            return {
                "status": "healthy" if response_time_ms < 100 else "warning",
                "response_time_ms": response_time_ms,
                "memory_usage_mb": memory_usage_mb,
                "memory_usage_percent": memory_usage_percent,
                "cache_hit_rate": cache_hit_rate,
                "connected_clients": info.get("connected_clients", 0),
                "timestamp": datetime.utcnow().isoformat(),
            }

        except Exception as e:
            logger.error(f"Redis health check failed: {e}")
            return {
                "status": "critical",
                "error": str(e),
                "timestamp": datetime.utcnow().isoformat(),
            }

    async def check_search_engine_health(self) -> Dict[str, Any]:
        """Check search engine health and performance"""
        try:
            # Get search metrics from the last hour
            search_metrics = await self._get_search_metrics()

            avg_response_time = search_metrics.get("avg_response_time_ms", 0)
            total_searches = search_metrics.get("total_searches_last_hour", 0)
            error_count = search_metrics.get("error_count_last_hour", 0)
            cache_hit_rate = search_metrics.get("cache_hit_rate", 0)

            error_rate = error_count / total_searches if total_searches > 0 else 0

            # Determine health status
            if error_rate > 0.1 or avg_response_time > 2000:
                status = "critical"
            elif error_rate > 0.05 or avg_response_time > 1000:
                status = "warning"
            else:
                status = "healthy"

            return {
                "status": status,
                "avg_response_time_ms": avg_response_time,
                "total_searches_last_hour": total_searches,
                "error_count_last_hour": error_count,
                "error_rate": error_rate,
                "cache_hit_rate": cache_hit_rate,
                "timestamp": datetime.utcnow().isoformat(),
            }

        except Exception as e:
            logger.error(f"Search engine health check failed: {e}")
            return {
                "status": "critical",
                "error": str(e),
                "timestamp": datetime.utcnow().isoformat(),
            }

    async def _get_search_metrics(self) -> Dict[str, Any]:
        """Get recent search performance metrics"""
        # This would typically query your search metrics
        # For now, return mock data
        return {
            "avg_response_time_ms": 350,
            "total_searches_last_hour": 250,
            "error_count_last_hour": 5,
            "cache_hit_rate": 0.68,
        }

    async def check_ai_models_health(self) -> Dict[str, Any]:
        """Check AI models health and availability"""
        try:
            # Check AI model availability and performance
            ai_metrics = await self._get_ai_model_metrics()

            return {
                "status": ai_metrics.get("model_status", "unknown"),
                "model_response_time_ms": ai_metrics.get("avg_response_time_ms", 0),
                "requests_last_hour": ai_metrics.get("requests_last_hour", 0),
                "errors_last_hour": ai_metrics.get("errors_last_hour", 0),
                "error_rate": ai_metrics.get("error_rate", 0),
                "quota_remaining": ai_metrics.get("quota_remaining", 0),
                "timestamp": datetime.utcnow().isoformat(),
            }

        except Exception as e:
            logger.error(f"AI models health check failed: {e}")
            return {
                "status": "critical",
                "error": str(e),
                "timestamp": datetime.utcnow().isoformat(),
            }

    async def _get_ai_model_metrics(self) -> Dict[str, Any]:
        """Get AI model performance metrics"""
        # This would typically query your AI model metrics
        # For now, return mock data
        return {
            "model_status": "healthy",
            "avg_response_time_ms": 1200,
            "requests_last_hour": 150,
            "errors_last_hour": 2,
            "error_rate": 2 / 150,
            "quota_remaining": 80,
        }

    async def calculate_response_time_percentiles(self) -> Dict[str, float]:
        """Calculate response time percentiles from recent data"""
        try:
            if not self._performance_history["response_times"]:
                return {"p50": 0, "p95": 0, "p99": 0}

            response_times = list(self._performance_history["response_times"])

            percentiles = {
                "p50": np.percentile(response_times, 50),
                "p95": np.percentile(response_times, 95),
                "p99": np.percentile(response_times, 99),
                "avg": np.mean(response_times),
                "min": np.min(response_times),
                "max": np.max(response_times),
            }

            return percentiles

        except Exception as e:
            logger.error(f"Error calculating percentiles: {e}")
            return {"p50": 0, "p95": 0, "p99": 0}

    async def calculate_error_rate(self, time_window_minutes: int = 60) -> float:
        """Calculate error rate for the specified time window"""
        try:
            # Get error data from Redis
            current_time = datetime.utcnow()
            error_counts = []
            total_counts = []

            for i in range(time_window_minutes):
                minute = (current_time - timedelta(minutes=i)).strftime(
                    "%Y-%m-%d-%H-%M"
                )

                # Get error count for this minute
                errors = await self.redis.lrange(f"feedme:perf:errors:{minute}", 0, -1)
                error_count = sum(int(e) for e in errors) if errors else 0

                # Total requests (errors + successes)
                total_count = len(errors) if errors else 0

                error_counts.append(error_count)
                total_counts.append(total_count)

            total_errors = sum(error_counts)
            total_requests = sum(total_counts)

            error_rate = total_errors / total_requests if total_requests > 0 else 0

            return error_rate

        except Exception as e:
            logger.error(f"Error calculating error rate: {e}")
            return 0.0

    async def analyze_cache_performance(self) -> Dict[str, Any]:
        """Analyze cache performance and hit rates"""
        try:
            current_time = datetime.utcnow()
            cache_hits = []
            total_requests = []

            # Analyze last hour
            for i in range(60):
                minute = (current_time - timedelta(minutes=i)).strftime(
                    "%Y-%m-%d-%H-%M"
                )

                hits = await self.redis.lrange(
                    f"feedme:perf:cache_hits:{minute}", 0, -1
                )
                hit_count = sum(int(h) for h in hits) if hits else 0
                total_count = len(hits) if hits else 0

                cache_hits.append(hit_count)
                total_requests.append(total_count)

            total_hits = sum(cache_hits)
            total_reqs = sum(total_requests)

            hit_rate = total_hits / total_reqs if total_reqs > 0 else 0

            # This would require correlating cache hits with response times
            # For now, use estimates
            avg_response_time_with_cache = 200  # Typical cached response
            avg_response_time_without_cache = 500  # Typical uncached response

            return {
                "hit_rate": hit_rate,
                "total_hits": total_hits,
                "total_requests": total_reqs,
                "avg_response_time_with_cache": avg_response_time_with_cache,
                "avg_response_time_without_cache": avg_response_time_without_cache,
                "optimization_potential": max(0, 0.8 - hit_rate),  # Target 80% hit rate
            }

        except Exception as e:
            logger.error(f"Error analyzing cache performance: {e}")
            return {"hit_rate": 0, "optimization_potential": 0}

    async def analyze_database_performance(self) -> List[Dict[str, Any]]:
        """Analyze database query performance"""
        try:
            query = text("""
                SELECT 
                    'vector_search' as query_type,
                    AVG(database_query_time_ms) as avg_execution_time_ms,
                    COUNT(*) as execution_count,
                    PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY database_query_time_ms) as p95_execution_time_ms,
                    COUNT(*) FILTER (WHERE database_query_time_ms > 1000) as slow_query_count
                FROM feedme_search_performance 
                WHERE timestamp >= NOW() - INTERVAL '1 hour'
                    AND search_type = 'vector'
                
                UNION ALL
                
                SELECT 
                    'text_search' as query_type,
                    AVG(database_query_time_ms) as avg_execution_time_ms,
                    COUNT(*) as execution_count,
                    PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY database_query_time_ms) as p95_execution_time_ms,
                    COUNT(*) FILTER (WHERE database_query_time_ms > 1000) as slow_query_count
                FROM feedme_search_performance 
                WHERE timestamp >= NOW() - INTERVAL '1 hour'
                    AND search_type = 'text'
            """)

            results = await self.db.fetch_all(query)
            return [dict(result) for result in results]

        except Exception as e:
            logger.error(f"Error analyzing database performance: {e}")
            return []

    async def analyze_memory_usage(self) -> Dict[str, Any]:
        """Analyze memory usage patterns and detect leaks"""
        try:
            memory_samples = list(self._performance_history["memory_usage"])

            if len(memory_samples) < 10:
                return {"trend": "insufficient_data", "leak_detected": False}

            # Calculate trend
            x = np.arange(len(memory_samples))
            y = np.array(memory_samples)

            # Linear regression to detect trend
            slope = np.polyfit(x, y, 1)[0]

            # Detect memory leak (consistent upward trend)
            trend = (
                "increasing" if slope > 1 else "decreasing" if slope < -1 else "stable"
            )
            leak_detected = slope > 2  # More than 2MB per sample

            # Calculate growth rate (MB per hour)
            if len(memory_samples) >= 12:  # At least 1 hour of 5-minute samples
                growth_rate_mb_per_hour = slope * 12  # 12 samples per hour
            else:
                growth_rate_mb_per_hour = 0

            return {
                "trend": trend,
                "leak_detected": leak_detected,
                "current_usage_mb": memory_samples[-1] if memory_samples else 0,
                "average_usage_mb": np.mean(memory_samples),
                "peak_usage_mb": np.max(memory_samples),
                "growth_rate_mb_per_hour": growth_rate_mb_per_hour,
                "alert_triggered": leak_detected,
            }

        except Exception as e:
            logger.error(f"Error analyzing memory usage: {e}")
            return {"trend": "error", "leak_detected": False}

    async def analyze_concurrency_impact(self) -> Dict[str, Any]:
        """Analyze the impact of concurrent searches on performance"""
        try:
            # This would analyze how response times degrade with concurrency
            # For now, return estimated analysis

            current_concurrent = len(self._performance_history["response_times"])
            avg_response_time = (
                np.mean(list(self._performance_history["response_times"]))
                if self._performance_history["response_times"]
                else 0
            )

            # Estimate degradation (this would be based on actual measurements)
            baseline_response_time = 200  # ms
            return {
                "current_concurrent_searches": current_concurrent,
                "peak_concurrent_searches": max(10, current_concurrent),
                "avg_response_time": avg_response_time,
                "baseline_response_time": baseline_response_time,
                "response_time_degradation": (
                    avg_response_time / baseline_response_time
                    if baseline_response_time > 0
                    else 1.0
                ),
                "cpu_usage_impact": (
                    np.mean(list(self._system_metrics["cpu_samples"]))
                    if self._system_metrics["cpu_samples"]
                    else 0
                ),
            }

        except Exception as e:
            logger.error(f"Error analyzing concurrency impact: {e}")
            return {"current_concurrent_searches": 0}

    async def generate_optimization_recommendations(
        self,
    ) -> List[OptimizationRecommendation]:
        """Generate automated optimization recommendations"""
        recommendations = []

        try:
            # Database optimization recommendations
            db_analysis = await self.analyze_database_performance()
            for analysis in db_analysis:
                if analysis.get("avg_execution_time_ms", 0) > 500:
                    recommendations.append(
                        OptimizationRecommendation(
                            type=OptimizationType.DATABASE_OPTIMIZATION,
                            priority="high",
                            description=f"Optimize {analysis['query_type']} queries - average execution time {analysis['avg_execution_time_ms']:.0f}ms",
                            impact_score=0.8,
                            implementation_effort="medium",
                            estimated_improvement="40-60% faster query execution",
                            technical_details={
                                "query_type": analysis["query_type"],
                                "current_avg_time": analysis["avg_execution_time_ms"],
                                "target_time": 200,
                            },
                        )
                    )

            # Cache optimization recommendations
            cache_analysis = await self.analyze_cache_performance()
            if cache_analysis.get("hit_rate", 0) < 0.7:
                recommendations.append(
                    OptimizationRecommendation(
                        type=OptimizationType.CACHING_IMPROVEMENT,
                        priority="medium",
                        description=f"Improve cache hit rate from {cache_analysis['hit_rate']:.1%} to 80%+",
                        impact_score=0.6,
                        implementation_effort="low",
                        estimated_improvement="20-30% faster response times",
                        technical_details={
                            "current_hit_rate": cache_analysis["hit_rate"],
                            "target_hit_rate": 0.8,
                            "optimization_potential": cache_analysis.get(
                                "optimization_potential", 0
                            ),
                        },
                    )
                )

            # Memory optimization recommendations
            memory_analysis = await self.analyze_memory_usage()
            if memory_analysis.get("leak_detected", False):
                recommendations.append(
                    OptimizationRecommendation(
                        type=OptimizationType.MEMORY_OPTIMIZATION,
                        priority="high",
                        description="Memory leak detected - investigate and fix memory allocation",
                        impact_score=0.9,
                        implementation_effort="high",
                        estimated_improvement="Prevent system instability and improve performance",
                        technical_details={
                            "growth_rate_mb_per_hour": memory_analysis.get(
                                "growth_rate_mb_per_hour", 0
                            ),
                            "current_usage_mb": memory_analysis.get(
                                "current_usage_mb", 0
                            ),
                            "trend": memory_analysis.get("trend", "unknown"),
                        },
                    )
                )

            # Query optimization recommendations
            percentiles = await self.calculate_response_time_percentiles()
            if percentiles.get("p95", 0) > 1000:
                recommendations.append(
                    OptimizationRecommendation(
                        type=OptimizationType.QUERY_OPTIMIZATION,
                        priority="high",
                        description=f"Optimize slow queries - P95 response time {percentiles['p95']:.0f}ms",
                        impact_score=0.7,
                        implementation_effort="medium",
                        estimated_improvement="50% reduction in P95 response time",
                        technical_details={
                            "current_p95": percentiles["p95"],
                            "target_p95": 500,
                            "current_avg": percentiles.get("avg", 0),
                        },
                    )
                )

            return recommendations

        except Exception as e:
            logger.error(f"Error generating optimization recommendations: {e}")
            return []

    async def check_and_send_alerts(self) -> List[Dict[str, Any]]:
        """Check system health and send alerts for any issues"""
        alerts = []

        try:
            # Check response time alerts
            percentiles = await self.calculate_response_time_percentiles()
            if (
                percentiles.get("p95", 0)
                > self.config.alert_thresholds["response_time_p95_ms"]
            ):
                alerts.append(
                    {
                        "type": "slow_response",
                        "severity": "warning",
                        "metric": "p95_response_time",
                        "value": percentiles["p95"],
                        "threshold": self.config.alert_thresholds[
                            "response_time_p95_ms"
                        ],
                        "timestamp": datetime.utcnow().isoformat(),
                    }
                )

            # Check error rate alerts
            error_rate = await self.calculate_error_rate()
            if error_rate > self.config.alert_thresholds["error_rate_threshold"]:
                alerts.append(
                    {
                        "type": "high_error_rate",
                        "severity": "critical",
                        "metric": "error_rate",
                        "value": error_rate,
                        "threshold": self.config.alert_thresholds[
                            "error_rate_threshold"
                        ],
                        "timestamp": datetime.utcnow().isoformat(),
                    }
                )

            # Check system health
            system_health = await self.collect_system_health()
            if (
                system_health.memory_usage_percent
                > self.config.alert_thresholds["memory_usage_threshold"] * 100
            ):
                alerts.append(
                    {
                        "type": "high_memory_usage",
                        "severity": "warning",
                        "metric": "memory_usage",
                        "value": system_health.memory_usage_percent,
                        "threshold": self.config.alert_thresholds[
                            "memory_usage_threshold"
                        ]
                        * 100,
                        "timestamp": datetime.utcnow().isoformat(),
                    }
                )

            # Send alerts to Redis
            for alert in alerts:
                await self.redis.lpush("feedme:performance_alerts", json.dumps(alert))

            return alerts

        except Exception as e:
            logger.error(f"Error checking and sending alerts: {e}")
            return []


class MetricCollector:
    """Utility class for collecting detailed metrics"""

    def __init__(self, collection_interval: float = 1.0, buffer_size: int = 1000):
        self.collection_interval = collection_interval
        self.buffer_size = buffer_size
        self._metrics_buffer = deque(maxlen=buffer_size)

    @asynccontextmanager
    async def measure_time(self):
        """Async context manager for measuring execution time"""
        timer = TimingContext()
        timer.start_time = time.perf_counter()
        try:
            yield timer
        finally:
            timer.end_time = time.perf_counter()
            timer.elapsed_ms = (timer.end_time - timer.start_time) * 1000

    def get_current_memory_usage(self) -> float:
        """Get current memory usage in MB"""
        process = psutil.Process()
        return process.memory_info().rss / (1024 * 1024)

    def get_current_cpu_usage(self) -> float:
        """Get current CPU usage percentage"""
        return psutil.cpu_percent(interval=0.1)

    def calculate_average_cpu(self, samples: List[float]) -> float:
        """Calculate average CPU usage from samples"""
        return np.mean(samples) if samples else 0.0

    async def process_metrics_batch(
        self, metrics: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Process a batch of metrics"""
        batch_id = datetime.utcnow().isoformat()

        processed_metrics = []
        for metric in metrics:
            processed_metric = {
                **metric,
                "batch_id": batch_id,
                "processed_at": datetime.utcnow(),
                "aggregated": True,
            }
            processed_metrics.append(processed_metric)

        return processed_metrics

    def validate_metric(self, metric: Dict[str, Any]) -> bool:
        """Validate metric data"""
        required_fields = ["timestamp", "metric_type", "value"]

        # Check required fields
        if not all(field in metric for field in required_fields):
            return False

        # Check data types
        if not isinstance(metric["timestamp"], datetime):
            return False

        if not isinstance(metric["value"], (int, float)):
            return False

        return True
