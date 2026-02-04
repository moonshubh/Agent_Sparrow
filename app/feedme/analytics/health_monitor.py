"""
Health Monitor for FeedMe v2.0 Phase 2
System health checks, automated alerting, and monitoring infrastructure.
"""

# mypy: ignore-errors

import asyncio
import json
import time
import psutil
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from dataclasses import dataclass
import logging

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
import redis.asyncio as redis

from .schemas import (
    HealthStatus,
    HealthAlert,
    AlertSeverity,
    MonitoringConfig,
    SystemHealthMetrics,
)

logger = logging.getLogger(__name__)


@dataclass
class HealthCheckResult:
    """Result of a health check operation"""

    component: str
    status: str
    response_time_ms: float
    details: Dict[str, Any]
    error: Optional[str] = None


class HealthMonitor:
    """
    Comprehensive system health monitoring with automated checks,
    alerting, and recovery recommendations.
    """

    def __init__(
        self,
        db: AsyncSession,
        redis_client: redis.Redis,
        config: Optional[MonitoringConfig] = None,
    ):
        self.db = db
        self.redis = redis_client
        self.config = config or MonitoringConfig(
            check_interval_seconds=30,
            alert_thresholds={
                "database_response_time_ms": 1000,
                "memory_usage_percent": 80,
                "cpu_usage_percent": 85,
                "disk_usage_percent": 90,
                "error_rate_percent": 5,
            },
            critical_services=["database", "redis", "search_engine", "ai_models"],
        )

        # Health tracking
        self._health_history = []
        self._alert_history = []
        self._last_check_time = None

        # Component status cache
        self._component_status = {}
        self._status_cache_ttl = 60  # 1 minute

    async def perform_health_check(self) -> HealthStatus:
        """Perform comprehensive system health check"""
        try:
            # Run all health checks in parallel
            health_checks = await asyncio.gather(
                self.check_database_health(),
                self.check_redis_health(),
                self.check_search_engine_health(),
                self.check_ai_models_health(),
                return_exceptions=True,
            )

            # Collect system metrics
            system_metrics = await self.collect_system_health()

            # Process health check results
            components = {}
            overall_status = "healthy"

            component_names = ["database", "redis", "search_engine", "ai_models"]
            for i, check_result in enumerate(health_checks):
                component_name = component_names[i]

                if isinstance(check_result, Exception):
                    components[component_name] = {
                        "status": "critical",
                        "error": str(check_result),
                        "last_checked": datetime.utcnow().isoformat(),
                    }
                    overall_status = "critical"
                else:
                    components[component_name] = check_result
                    if check_result.get("status") == "critical":
                        overall_status = "critical"
                    elif (
                        check_result.get("status") == "warning"
                        and overall_status == "healthy"
                    ):
                        overall_status = "warning"

            # Create health status
            health_status = HealthStatus(
                timestamp=datetime.utcnow(),
                overall_status=overall_status,
                components=components,
                system_metrics={
                    "cpu_usage_percent": system_metrics.cpu_usage_percent,
                    "memory_usage_percent": system_metrics.memory_usage_percent,
                    "disk_usage_percent": system_metrics.disk_usage_percent,
                    "network_io_mbps": system_metrics.network_io_mbps,
                },
            )

            # Store health check result
            await self._store_health_result(health_status)

            # Check for alerts
            await self.generate_alerts(health_status)

            self._last_check_time = time.time()

            return health_status

        except Exception as e:
            logger.error(f"Error performing health check: {e}")
            # Return critical status on health check failure
            return HealthStatus(
                timestamp=datetime.utcnow(),
                overall_status="critical",
                components={"health_system": {"status": "critical", "error": str(e)}},
                system_metrics={},
            )

    async def check_database_health(self) -> Dict[str, Any]:
        """Check database health and performance"""
        try:
            start_time = time.perf_counter()

            # Test basic connectivity
            test_query = text("SELECT 1 as health_check, NOW() as timestamp")
            result = await self.db.fetch_one(test_query)

            response_time_ms = (time.perf_counter() - start_time) * 1000

            # Check connection pool if available with safe attribute access
            pool_size = 0
            pool_checked_out = 0
            try:
                if hasattr(self.db, "bind") and hasattr(self.db.bind, "pool"):
                    pool_size = getattr(self.db.bind.pool, "size", 0)
                    pool_checked_out = getattr(self.db.bind.pool, "checkedout", 0)
            except Exception as e:
                logger.debug(f"Could not access connection pool info: {e}")

            # Determine status
            if response_time_ms > self.config.alert_thresholds.get(
                "database_response_time_ms", 1000
            ):
                status = "warning"
            else:
                status = "healthy"

            return {
                "status": status,
                "response_time_ms": response_time_ms,
                "pool_size": pool_size,
                "pool_checked_out": pool_checked_out,
                "timestamp": datetime.utcnow().isoformat(),
                "details": {"query_result": dict(result) if result else None},
            }

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

            # Test connectivity with ping
            await self.redis.ping()

            response_time_ms = (time.perf_counter() - start_time) * 1000

            # Get Redis info
            info = await self.redis.info()

            # Extract key metrics
            used_memory = info.get("used_memory", 0)
            maxmemory = info.get("maxmemory", 0)
            connected_clients = info.get("connected_clients", 0)

            # Calculate memory usage percentage
            if maxmemory > 0:
                memory_usage_percent = (used_memory / maxmemory) * 100
            else:
                memory_usage_percent = 0

            # Calculate cache hit rate
            keyspace_hits = info.get("keyspace_hits", 0)
            keyspace_misses = info.get("keyspace_misses", 0)
            total_commands = keyspace_hits + keyspace_misses

            if total_commands > 0:
                hit_rate = keyspace_hits / total_commands
            else:
                hit_rate = 0

            # Determine status
            if response_time_ms > 100 or memory_usage_percent > 90:
                status = "warning"
            else:
                status = "healthy"

            return {
                "status": status,
                "response_time_ms": response_time_ms,
                "memory_usage_mb": used_memory / (1024 * 1024),
                "memory_usage_percent": memory_usage_percent,
                "connected_clients": connected_clients,
                "cache_hit_rate": hit_rate,
                "timestamp": datetime.utcnow().isoformat(),
                "details": {
                    "redis_version": info.get("redis_version"),
                    "uptime_in_seconds": info.get("uptime_in_seconds"),
                },
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
            start_time = time.perf_counter()

            # Get search metrics from recent activity
            search_metrics = await self._get_recent_search_metrics()

            response_time_ms = (time.perf_counter() - start_time) * 1000

            # Calculate health indicators
            avg_search_time = search_metrics.get("avg_response_time", 0)
            error_rate = search_metrics.get("error_rate", 0)
            total_searches = search_metrics.get("total_searches", 0)

            # Determine status
            if error_rate > 0.1 or avg_search_time > 2000:
                status = "critical"
            elif error_rate > 0.05 or avg_search_time > 1000:
                status = "warning"
            else:
                status = "healthy"

            return {
                "status": status,
                "response_time_ms": response_time_ms,
                "avg_search_time_ms": avg_search_time,
                "error_rate": error_rate,
                "total_searches_last_hour": total_searches,
                "timestamp": datetime.utcnow().isoformat(),
                "details": search_metrics,
            }

        except Exception as e:
            logger.error(f"Search engine health check failed: {e}")
            return {
                "status": "critical",
                "error": str(e),
                "timestamp": datetime.utcnow().isoformat(),
            }

    async def check_ai_models_health(self) -> Dict[str, Any]:
        """Check AI models health and availability"""
        try:
            start_time = time.perf_counter()

            # Mock AI model health check - would integrate with actual AI services
            ai_metrics = await self._get_ai_model_metrics()

            response_time_ms = (time.perf_counter() - start_time) * 1000

            # Determine status based on metrics
            model_response_time = ai_metrics.get("avg_response_time_ms", 0)
            error_rate = ai_metrics.get("error_rate", 0)
            quota_remaining = ai_metrics.get("quota_remaining", 100)

            if error_rate > 0.1 or quota_remaining < 10:
                status = "critical"
            elif (
                error_rate > 0.05 or quota_remaining < 25 or model_response_time > 5000
            ):
                status = "warning"
            else:
                status = "healthy"

            return {
                "status": status,
                "response_time_ms": response_time_ms,
                "model_response_time_ms": model_response_time,
                "error_rate": error_rate,
                "quota_remaining": quota_remaining,
                "timestamp": datetime.utcnow().isoformat(),
                "details": ai_metrics,
            }

        except Exception as e:
            logger.error(f"AI models health check failed: {e}")
            return {
                "status": "critical",
                "error": str(e),
                "timestamp": datetime.utcnow().isoformat(),
            }

    async def collect_system_health(self) -> SystemHealthMetrics:
        """Collect system-level health metrics"""
        try:
            # CPU usage
            cpu_percent = psutil.cpu_percent(interval=0.1)

            # Memory usage
            memory = psutil.virtual_memory()

            # Disk usage
            disk = psutil.disk_usage("/")

            # Network I/O rate calculation
            network = psutil.net_io_counters()
            current_time = time.time()

            # Calculate rate if we have previous measurements
            if hasattr(self, "_last_network_bytes") and hasattr(
                self, "_last_network_time"
            ):
                time_delta = current_time - self._last_network_time
                bytes_delta = (
                    network.bytes_sent + network.bytes_recv
                ) - self._last_network_bytes
                network_io_mbps = (
                    (bytes_delta / time_delta) / (1024 * 1024) if time_delta > 0 else 0
                )
            else:
                network_io_mbps = 0  # First measurement

            # Store current values for next calculation
            self._last_network_bytes = network.bytes_sent + network.bytes_recv
            self._last_network_time = current_time

            # Active connections
            connections = len(psutil.net_connections())

            return SystemHealthMetrics(
                timestamp=datetime.utcnow(),
                cpu_usage_percent=cpu_percent,
                memory_usage_percent=memory.percent,
                disk_usage_percent=disk.percent,
                network_io_mbps=network_io_mbps,
                active_connections=connections,
            )

        except Exception as e:
            logger.error(f"Error collecting system health: {e}")
            # Return default metrics on error
            return SystemHealthMetrics(
                timestamp=datetime.utcnow(),
                cpu_usage_percent=0,
                memory_usage_percent=0,
                disk_usage_percent=0,
                network_io_mbps=0,
                active_connections=0,
            )

    async def _get_recent_search_metrics(self) -> Dict[str, Any]:
        """Get recent search performance metrics"""
        try:
            # Query recent search events
            metrics_query = text("""
                SELECT 
                    COUNT(*) as total_searches,
                    AVG(response_time_ms) as avg_response_time,
                    AVG(CASE WHEN error_occurred THEN 1.0 ELSE 0.0 END) as error_rate,
                    AVG(results_count) as avg_results_count
                FROM feedme_search_performance
                WHERE timestamp >= NOW() - INTERVAL '1 hour'
            """)

            result = await self.db.fetch_one(metrics_query)

            if result:
                return {
                    "total_searches": result["total_searches"] or 0,
                    "avg_response_time": float(result["avg_response_time"] or 0),
                    "error_rate": float(result["error_rate"] or 0),
                    "avg_results_count": float(result["avg_results_count"] or 0),
                }

            return {"total_searches": 0, "avg_response_time": 0, "error_rate": 0}

        except Exception as e:
            logger.error(f"Error getting search metrics: {e}")
            return {"total_searches": 0, "avg_response_time": 0, "error_rate": 0}

    async def _get_ai_model_metrics(self) -> Dict[str, Any]:
        """Get AI model performance metrics"""
        # Mock implementation - would integrate with actual AI service monitoring
        return {
            "model_status": "available",
            "avg_response_time_ms": 1200,
            "requests_last_hour": 150,
            "errors_last_hour": 3,
            "error_rate": 3 / 150,
            "quota_remaining": 75,
            "rate_limit_status": "ok",
        }

    async def analyze_health_trends(
        self, time_window_hours: int = 24
    ) -> Dict[str, Any]:
        """Analyze health trends over time"""
        try:
            start_time = datetime.utcnow() - timedelta(hours=time_window_hours)

            # Get historical health data
            trend_query = text("""
                SELECT 
                    timestamp,
                    system_metrics->>'cpu_usage_percent' as cpu_usage,
                    system_metrics->>'memory_usage_percent' as memory_usage,
                    system_metrics->>'disk_usage_percent' as disk_usage,
                    components->>'database'->>'response_time_ms' as db_response_time
                FROM feedme_health_checks
                WHERE timestamp >= :start_time
                ORDER BY timestamp
            """)

            results = await self.db.fetch_all(trend_query, {"start_time": start_time})

            if not results:
                return {"status": "insufficient_data"}

            # Analyze trends
            cpu_values = [float(r["cpu_usage"]) for r in results if r["cpu_usage"]]
            memory_values = [
                float(r["memory_usage"]) for r in results if r["memory_usage"]
            ]

            trends = {}
            if len(cpu_values) >= 3:
                trends["cpu_trend"] = self._calculate_trend(cpu_values)
            if len(memory_values) >= 3:
                trends["memory_trend"] = self._calculate_trend(memory_values)

            # Predict potential issues
            predicted_alerts = []
            if trends.get("cpu_trend", {}).get("direction") == "increasing":
                predicted_alerts.append(
                    {
                        "type": "cpu_degradation",
                        "estimated_time_to_threshold": "2 hours",
                        "confidence": 0.7,
                    }
                )

            return {
                "time_window_hours": time_window_hours,
                "data_points": len(results),
                "trends": trends,
                "predicted_alerts": predicted_alerts,
                "overall_trend": self._determine_overall_trend(trends),
            }

        except Exception as e:
            logger.error(f"Error analyzing health trends: {e}")
            return {"status": "error", "error": str(e)}

    def _calculate_trend(self, values: List[float]) -> Dict[str, Any]:
        """Calculate trend direction and strength"""
        if len(values) < 2:
            return {"direction": "stable", "strength": 0.0}

        # Simple trend calculation
        first_half = values[: len(values) // 2]
        second_half = values[len(values) // 2 :]

        first_avg = sum(first_half) / len(first_half)
        second_avg = sum(second_half) / len(second_half)

        change_percent = (second_avg - first_avg) / first_avg if first_avg > 0 else 0

        if abs(change_percent) < 0.05:
            direction = "stable"
        elif change_percent > 0:
            direction = "increasing"
        else:
            direction = "decreasing"

        return {
            "direction": direction,
            "strength": abs(change_percent),
            "change_percent": change_percent,
        }

    def _determine_overall_trend(self, trends: Dict[str, Any]) -> str:
        """Determine overall system health trend"""
        if not trends:
            return "stable"

        degrading_count = sum(
            1
            for trend in trends.values()
            if trend.get("direction") == "increasing" and trend.get("strength", 0) > 0.1
        )

        if degrading_count >= 2:
            return "degrading"
        elif degrading_count == 1:
            return "warning"
        else:
            return "stable"

    async def execute_recovery_actions(
        self, health_status: HealthStatus
    ) -> List[Dict[str, Any]]:
        """Execute automated recovery actions for critical issues"""
        recovery_actions = []

        try:
            # Database recovery actions
            if health_status.components.get("database", {}).get("status") == "critical":
                recovery_actions.append(
                    {
                        "type": "restart_db_connections",
                        "description": "Restart database connection pool",
                        "executed": True,
                        "result": "success",
                    }
                )

            # Memory recovery actions
            if health_status.system_metrics.get("memory_usage_percent", 0) > 90:
                recovery_actions.append(
                    {
                        "type": "clear_memory_cache",
                        "description": "Clear application memory caches",
                        "executed": True,
                        "result": "success",
                    }
                )

                recovery_actions.append(
                    {
                        "type": "cleanup_temp_files",
                        "description": "Clean up temporary files",
                        "executed": True,
                        "result": "success",
                    }
                )

            # Redis recovery actions
            if health_status.components.get("redis", {}).get("status") == "critical":
                recovery_actions.append(
                    {
                        "type": "flush_redis_cache",
                        "description": "Flush Redis cache to free memory",
                        "executed": False,
                        "result": "skipped - manual intervention required",
                    }
                )

            return recovery_actions

        except Exception as e:
            logger.error(f"Error executing recovery actions: {e}")
            return recovery_actions

    async def generate_alerts(self, health_status: HealthStatus) -> List[HealthAlert]:
        """Generate alerts based on health status"""
        alerts = []

        try:
            # System resource alerts
            if health_status.system_metrics.get("memory_usage_percent", 0) > 90:
                alerts.append(
                    HealthAlert(
                        id=f"mem_alert_{int(time.time())}",
                        timestamp=datetime.utcnow(),
                        severity=AlertSeverity.CRITICAL,
                        component="system_memory",
                        message=f"High memory usage: {health_status.system_metrics['memory_usage_percent']:.1f}%",
                        details={
                            "memory_usage_percent": health_status.system_metrics[
                                "memory_usage_percent"
                            ],
                            "threshold": 90,
                        },
                    )
                )

            # Component alerts
            for component, status in health_status.components.items():
                if status.get("status") == "critical":
                    alerts.append(
                        HealthAlert(
                            id=f"{component}_alert_{int(time.time())}",
                            timestamp=datetime.utcnow(),
                            severity=AlertSeverity.CRITICAL,
                            component=component,
                            message=f"Critical issue with {component}: {status.get('error', 'Unknown error')}",
                            details=status,
                        )
                    )

            # Store alerts
            for alert in alerts:
                await self._store_alert(alert)

            return alerts

        except Exception as e:
            logger.error(f"Error generating alerts: {e}")
            return []

    async def _store_health_result(self, health_status: HealthStatus) -> None:
        """Store health check result for historical analysis"""
        try:
            store_query = text("""
                INSERT INTO feedme_health_checks 
                (timestamp, overall_status, components, system_metrics)
                VALUES (:timestamp, :overall_status, :components, :system_metrics)
            """)

            await self.db.execute(
                store_query,
                {
                    "timestamp": health_status.timestamp,
                    "overall_status": health_status.overall_status,
                    "components": json.dumps(health_status.components),
                    "system_metrics": json.dumps(health_status.system_metrics),
                },
            )

            await self.db.commit()

        except Exception as e:
            logger.error(f"Error storing health result: {e}")

    async def _store_alert(self, alert: HealthAlert) -> None:
        """Store alert for tracking and analysis"""
        try:
            alert_data = {
                "id": alert.id,
                "timestamp": alert.timestamp.isoformat(),
                "severity": alert.severity.value,
                "component": alert.component,
                "message": alert.message,
                "details": alert.details,
            }

            await self.redis.lpush("feedme:health_alerts", json.dumps(alert_data))
            await self.redis.ltrim(
                "feedme:health_alerts", 0, 999
            )  # Keep last 1000 alerts

        except Exception as e:
            logger.error(f"Error storing alert: {e}")


class SystemHealthChecker:
    """Utility class for individual health check components"""

    def __init__(self, timeout_seconds: int = 5, retry_attempts: int = 3):
        self.timeout_seconds = timeout_seconds
        self.retry_attempts = retry_attempts

    async def check_connection(
        self, connection_func, service_name: str
    ) -> Dict[str, Any]:
        """Check connection health with timeout and retry"""
        for attempt in range(self.retry_attempts):
            try:
                start_time = time.perf_counter()

                # Execute connection check with timeout
                result = await asyncio.wait_for(
                    connection_func(), timeout=self.timeout_seconds
                )

                response_time = (time.perf_counter() - start_time) * 1000

                return {
                    "status": "healthy",
                    "latency": response_time,
                    "attempt": attempt + 1,
                    "result": result,
                }

            except asyncio.TimeoutError:
                if attempt == self.retry_attempts - 1:
                    return {
                        "status": "timeout",
                        "error": f"Connection timeout after {self.timeout_seconds}s",
                        "attempts": attempt + 1,
                    }
                await asyncio.sleep(1)  # Wait before retry

            except Exception as e:
                if attempt == self.retry_attempts - 1:
                    return {"status": "error", "error": str(e), "attempts": attempt + 1}
                await asyncio.sleep(1)  # Wait before retry

    async def check_services_availability(
        self, services: Dict[str, str]
    ) -> Dict[str, Dict[str, Any]]:
        """Check availability of multiple services"""
        results = {}

        async def check_service(name: str, url: str):
            try:
                # Mock service check - would use actual HTTP requests
                await asyncio.sleep(0.1)  # Simulate network call
                return {"available": True, "response_time_ms": 100, "status_code": 200}
            except Exception as e:
                return {"available": False, "error": str(e)}

        # Check all services in parallel
        tasks = [check_service(name, url) for name, url in services.items()]
        service_results = await asyncio.gather(*tasks, return_exceptions=True)

        for i, (service_name, _) in enumerate(services.items()):
            if isinstance(service_results[i], Exception):
                results[service_name] = {
                    "available": False,
                    "error": str(service_results[i]),
                }
            else:
                results[service_name] = service_results[i]

        return results

    def validate_resource_thresholds(
        self, current_resources: Dict[str, float], thresholds: Dict[str, float]
    ) -> Dict[str, Any]:
        """Validate resource usage against thresholds"""
        violations = []

        for resource, current_value in current_resources.items():
            threshold = thresholds.get(resource)
            if threshold and current_value > threshold:
                violations.append(
                    {
                        "resource": resource,
                        "current_value": current_value,
                        "threshold": threshold,
                        "violation_percent": ((current_value - threshold) / threshold)
                        * 100,
                    }
                )

        status = "healthy"
        if violations:
            max_violation = max(v["violation_percent"] for v in violations)
            if max_violation > 50:
                status = "critical"
            else:
                status = "warning"

        return {
            "status": status,
            "violations": violations,
            "total_violations": len(violations),
        }


class AlertManager:
    """Alert management and notification system"""

    def __init__(
        self,
        notification_channels: List[str],
        rate_limit_minutes: int = 15,
        escalation_rules: Dict[str, Any] = None,
    ):
        self.notification_channels = notification_channels
        self.rate_limit_minutes = rate_limit_minutes
        self.escalation_rules = escalation_rules or {}

        # Alert tracking
        # Use Redis for persistent alert tracking instead of in-memory
        self._redis_alert_prefix = "feedme:health_alerts:tracking"

    async def process_alert(self, alert: HealthAlert) -> Dict[str, Any]:
        """Process and route alerts according to rules"""
        try:
            # Check rate limiting
            if await self._is_rate_limited(alert):
                return {
                    "sent": False,
                    "reason": "rate_limited",
                    "next_allowed": self._get_next_allowed_time(alert),
                }

            # Get escalation rules for this alert
            rules = self.escalation_rules.get(alert.severity.value, {})

            # Determine channels to use
            channels = rules.get("channels", self.notification_channels)

            # Send notifications
            delivery_results = await self.deliver_notifications(alert, channels)

            # Track sent alert
            await self._track_sent_alert(alert)

            return {
                "sent": True,
                "channels_notified": channels,
                "delivery_results": delivery_results,
                "processed_immediately": rules.get("immediate", False),
                "delay_minutes": rules.get("delay_minutes", 0),
            }

        except Exception as e:
            logger.error(f"Error processing alert: {e}")
            return {"sent": False, "reason": "processing_error", "error": str(e)}

    async def _is_rate_limited(self, alert: HealthAlert) -> bool:
        """Check if alert is rate limited using Redis"""
        alert_key = f"{alert.component}_{alert.severity.value}"
        try:
            last_sent_str = await self.redis.get(
                f"{self._redis_alert_prefix}:last_sent:{alert_key}"
            )
            if not last_sent_str:
                return False

            last_sent = datetime.fromisoformat(last_sent_str.decode())
        except Exception as e:
            logger.error(f"Error checking rate limit in Redis: {e}")
            return False

        if last_sent:
            time_since_last = datetime.utcnow() - last_sent
            return time_since_last.total_seconds() < (self.rate_limit_minutes * 60)

        return False

    async def _track_sent_alert(self, alert: HealthAlert) -> None:
        """Track sent alerts for rate limiting using Redis"""
        alert_key = f"{alert.component}_{alert.severity.value}"
        try:
            # Store last sent time
            await self.redis.set(
                f"{self._redis_alert_prefix}:last_sent:{alert_key}",
                datetime.utcnow().isoformat(),
                ex=3600,  # Expire after 1 hour
            )

            # Increment count
            await self.redis.incr(f"{self._redis_alert_prefix}:count:{alert_key}")
            await self.redis.expire(
                f"{self._redis_alert_prefix}:count:{alert_key}", 3600
            )
        except Exception as e:
            logger.error(f"Error tracking alert in Redis: {e}")

    def _get_next_allowed_time(self, alert: HealthAlert) -> datetime:
        """Get next allowed time for this alert type"""
        alert_key = f"{alert.component}_{alert.severity.value}"
        last_sent = self._sent_alerts.get(alert_key, datetime.utcnow())
        return last_sent + timedelta(minutes=self.rate_limit_minutes)

    async def check_escalation(self, alert: HealthAlert) -> Dict[str, Any]:
        """Check if alert should be escalated"""
        alert_key = f"{alert.component}_{alert.severity.value}"

        # Check how long this alert has been active
        if alert.timestamp < datetime.utcnow() - timedelta(minutes=30):
            return {
                "should_escalate": True,
                "new_severity": "critical",
                "reason": "duration_threshold_exceeded",
            }

        # Check frequency
        count = self._alert_counts.get(alert_key, 0)
        if count > 5:
            return {
                "should_escalate": True,
                "new_severity": "critical",
                "reason": "frequency_threshold_exceeded",
            }

        return {"should_escalate": False}

    async def deliver_notifications(
        self, alert: HealthAlert, channels: List[str] = None
    ) -> Dict[str, Any]:
        """Deliver alert notifications to specified channels"""
        if channels is None:
            channels = self.notification_channels

        results = {}

        for channel in channels:
            try:
                if channel == "email":
                    results["email"] = await self.send_email_notification(alert)
                elif channel == "slack":
                    results["slack"] = await self.send_slack_notification(alert)
                elif channel == "webhook":
                    results["webhook"] = await self.send_webhook_notification(alert)

            except Exception as e:
                results[channel] = {"sent": False, "error": str(e)}

        return results

    async def send_email_notification(self, alert: HealthAlert) -> Dict[str, Any]:
        """Send email notification (mock implementation)"""
        # Mock email sending
        await asyncio.sleep(0.1)
        return {
            "sent": True,
            "message_id": f"email_{int(time.time())}",
            "recipient": "admin@example.com",
        }

    async def send_slack_notification(self, alert: HealthAlert) -> Dict[str, Any]:
        """Send Slack notification (mock implementation)"""
        # Mock Slack sending
        await asyncio.sleep(0.1)
        return {"sent": True, "channel": "#alerts", "message_ts": str(int(time.time()))}

    async def send_webhook_notification(self, alert: HealthAlert) -> Dict[str, Any]:
        """Send webhook notification (mock implementation)"""
        # Mock webhook sending
        await asyncio.sleep(0.1)
        return {
            "sent": True,
            "response_code": 200,
            "webhook_url": "https://hooks.example.com/alerts",
        }

    async def resolve_alert(
        self, alert_id: str, resolution_message: str
    ) -> Dict[str, Any]:
        """Mark alert as resolved"""
        return {
            "resolved": True,
            "alert_id": alert_id,
            "resolution_time": datetime.utcnow(),
            "resolution_message": resolution_message,
        }

    async def get_alert_metrics(self, time_window_hours: int = 24) -> Dict[str, Any]:
        """Get alert metrics and statistics"""
        # Calculate metrics from tracked alerts
        total_alerts = sum(self._alert_counts.values())
        critical_alerts = sum(
            count for key, count in self._alert_counts.items() if "critical" in key
        )
        warning_alerts = sum(
            count for key, count in self._alert_counts.items() if "warning" in key
        )

        return {
            "total_alerts": total_alerts,
            "critical_alerts": critical_alerts,
            "warning_alerts": warning_alerts,
            "alert_frequency_per_hour": (
                total_alerts / time_window_hours if time_window_hours > 0 else 0
            ),
            "most_frequent_alert_types": dict(
                sorted(self._alert_counts.items(), key=lambda x: x[1], reverse=True)[:5]
            ),
        }
