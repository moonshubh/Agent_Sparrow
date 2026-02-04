"""
Usage Analytics Tracker for FeedMe v2.0 Phase 2
Real-time usage metrics collection, analysis, and insights generation.
"""

# mypy: ignore-errors

import asyncio
import json
import time
from datetime import datetime, timedelta
from typing import Dict, List, Any
from collections import defaultdict, deque
import logging

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
import redis.asyncio as redis
import numpy as np
from scipy import stats

from .schemas import SearchEvent, AnalyticsInsights, UserBehaviorAnalytics

logger = logging.getLogger(__name__)


class UsageAnalytics:
    """
    Comprehensive usage analytics system with real-time tracking,
    pattern analysis, and predictive insights.
    """

    def __init__(
        self,
        db: AsyncSession,
        redis_client: redis.Redis,
        enable_real_time: bool = True,
        buffer_size: int = 1000,
        flush_interval_seconds: int = 60,
    ):
        self.db = db
        self.redis = redis_client
        self.enable_real_time = enable_real_time
        self.buffer_size = buffer_size
        self.flush_interval = flush_interval_seconds

        # Event buffer for batch processing
        self._event_buffer: deque = deque(maxlen=buffer_size)
        self._last_flush = time.time()

        # Real-time metrics cache
        self._metrics_cache = {}
        self._cache_ttl = 300  # 5 minutes

        # Anomaly detection thresholds
        self._anomaly_thresholds = {
            "response_time_multiplier": 3.0,
            "zero_results_threshold": 0.15,
            "error_rate_threshold": 0.1,
        }

        # Background task management
        self._background_task = None
        if enable_real_time:
            self._start_background_tasks()

    def _start_background_tasks(self):
        """Start background tasks if event loop is available"""
        try:
            self._background_task = asyncio.create_task(self._periodic_flush())
        except RuntimeError:
            # No event loop running, skip background tasks (useful for testing)
            pass

    async def track_search_event(self, event: SearchEvent) -> None:
        """
        Track a search event with real-time metrics updates
        and batch storage for detailed analysis.
        """
        try:
            # Add to buffer for batch processing
            self._event_buffer.append(event)

            if self.enable_real_time:
                await self._update_real_time_metrics(event)

            # Check for anomalies in real-time
            anomalies = await self._detect_event_anomalies(event)
            if anomalies:
                await self._handle_anomalies(anomalies)

            # Auto-flush if buffer is full
            if len(self._event_buffer) >= self.buffer_size:
                await self.flush_events_to_database()

        except Exception as e:
            logger.error(f"Error tracking search event: {e}")
            # Don't raise to avoid breaking the search flow

    async def _update_real_time_metrics(self, event: SearchEvent) -> None:
        """Update real-time metrics in Redis"""
        current_hour = datetime.utcnow().strftime("%Y-%m-%d-%H")

        # Update counters
        pipe = self.redis.pipeline()

        # Total searches
        pipe.incr(f"feedme:metrics:searches:{current_hour}")
        pipe.expire(f"feedme:metrics:searches:{current_hour}", 86400)

        # Response time metrics
        pipe.lpush(
            f"feedme:metrics:response_times:{current_hour}", event.response_time_ms
        )
        pipe.ltrim(
            f"feedme:metrics:response_times:{current_hour}", 0, 999
        )  # Keep last 1000
        pipe.expire(f"feedme:metrics:response_times:{current_hour}", 86400)

        # User activity
        pipe.sadd(f"feedme:metrics:active_users:{current_hour}", event.user_id)
        pipe.expire(f"feedme:metrics:active_users:{current_hour}", 86400)

        # Search type distribution
        pipe.incr(f"feedme:metrics:search_type:{event.search_type}:{current_hour}")
        pipe.expire(
            f"feedme:metrics:search_type:{event.search_type}:{current_hour}", 86400
        )

        # Success rate tracking
        success = 1 if event.results_count > 0 and event.clicked_results else 0
        pipe.lpush(f"feedme:metrics:success_rate:{current_hour}", success)
        pipe.ltrim(f"feedme:metrics:success_rate:{current_hour}", 0, 999)
        pipe.expire(f"feedme:metrics:success_rate:{current_hour}", 86400)

        # Performance alerts
        if event.response_time_ms > 2000:  # Slow search threshold
            alert_data = {
                "type": "slow_search",
                "response_time": event.response_time_ms,
                "threshold": 2000,
                "timestamp": event.timestamp.isoformat(),
                "user_id": event.user_id,
                "query": event.query[:100],  # Truncate for privacy
            }
            pipe.lpush("feedme:performance_alerts", json.dumps(alert_data))
            pipe.ltrim("feedme:performance_alerts", 0, 99)  # Keep last 100 alerts

        await pipe.execute()

    async def _detect_event_anomalies(self, event: SearchEvent) -> List[Dict[str, Any]]:
        """Detect anomalies in individual search events"""
        anomalies = []

        # High response time anomaly
        if event.response_time_ms > 10000:  # 10 seconds
            anomalies.append(
                {
                    "type": "performance_anomaly",
                    "severity": "high",
                    "metric": "response_time",
                    "value": event.response_time_ms,
                    "threshold": 10000,
                    "user_id": event.user_id,
                    "query": event.query[:100],
                }
            )

        # Zero results anomaly for common queries
        if event.results_count == 0 and len(event.query) > 5:
            anomalies.append(
                {
                    "type": "search_quality_anomaly",
                    "severity": "medium",
                    "metric": "zero_results",
                    "query": event.query,
                    "user_id": event.user_id,
                }
            )

        return anomalies

    async def _handle_anomalies(self, anomalies: List[Dict[str, Any]]) -> None:
        """Handle detected anomalies"""
        for anomaly in anomalies:
            # Store anomaly for analysis
            anomaly_data = {**anomaly, "timestamp": datetime.utcnow().isoformat()}
            await self.redis.lpush("feedme:anomalies", json.dumps(anomaly_data))
            await self.redis.ltrim("feedme:anomalies", 0, 499)  # Keep last 500

            # Log severe anomalies
            if anomaly["severity"] == "high":
                logger.warning(f"High severity anomaly detected: {anomaly}")

    async def flush_events_to_database(self) -> None:
        """Flush buffered events to database for persistent storage"""
        if not self._event_buffer:
            return

        events_to_process = list(self._event_buffer)
        self._event_buffer.clear()

        try:
            # Batch insert events
            insert_query = text("""
                INSERT INTO feedme_search_events 
                (user_id, query, timestamp, results_count, response_time_ms, 
                 clicked_results, conversation_id, search_type, context_data)
                VALUES 
                (:user_id, :query, :timestamp, :results_count, :response_time_ms,
                 :clicked_results, :conversation_id, :search_type, :context_data)
            """)

            event_data = []
            for event in events_to_process:
                event_data.append(
                    {
                        "user_id": event.user_id,
                        "query": event.query,
                        "timestamp": event.timestamp,
                        "results_count": event.results_count,
                        "response_time_ms": event.response_time_ms,
                        "clicked_results": json.dumps(event.clicked_results),
                        "conversation_id": event.conversation_id,
                        "search_type": event.search_type.value,
                        "context_data": json.dumps(event.context_data),
                    }
                )

            # Use proper async SQLAlchemy bulk insert
            async with self.db.begin() as transaction:
                await transaction.execute(insert_query, event_data)

            logger.info(f"Flushed {len(event_data)} search events to database")

        except Exception as e:
            logger.error(f"Error flushing events to database: {e}")
            # Re-add events to buffer for retry
            self._event_buffer.extendleft(reversed(events_to_process))

    async def _periodic_flush(self) -> None:
        """Periodic background task to flush events"""
        while True:
            try:
                await asyncio.sleep(self.flush_interval)
                await self.flush_events_to_database()
            except Exception as e:
                logger.error(f"Error in periodic flush: {e}")

    async def generate_insights(
        self, start_date: datetime, end_date: datetime, include_predictions: bool = True
    ) -> AnalyticsInsights:
        """
        Generate comprehensive analytics insights for the specified time period
        """
        try:
            # Get basic usage metrics
            usage_metrics = await self._get_usage_metrics(start_date, end_date)

            # Get top queries
            top_queries = await self._get_top_queries(start_date, end_date, limit=10)

            # Get performance trends
            performance_trends = await self._get_performance_trends(
                start_date, end_date
            )

            # Get optimization opportunities
            optimization_opportunities = await self._get_optimization_opportunities()

            return AnalyticsInsights(
                total_searches=usage_metrics["total_searches"],
                unique_users=usage_metrics["unique_users"],
                avg_response_time=usage_metrics["avg_response_time"],
                click_through_rate=usage_metrics["click_through_rate"],
                success_rate=usage_metrics["success_rate"],
                top_queries=top_queries,
                performance_trends=performance_trends,
                optimization_opportunities=optimization_opportunities,
            )

        except Exception as e:
            logger.error(f"Error generating insights: {e}")
            raise

    async def _get_usage_metrics(
        self, start_date: datetime, end_date: datetime
    ) -> Dict[str, Any]:
        """Get basic usage metrics for time period"""
        query = text("""
            SELECT 
                COUNT(*) as total_searches,
                COUNT(DISTINCT user_id) as unique_users,
                AVG(response_time_ms) as avg_response_time,
                AVG(CASE WHEN array_length(clicked_results, 1) > 0 THEN 1.0 ELSE 0.0 END) as click_through_rate,
                AVG(CASE WHEN results_count > 0 THEN 1.0 ELSE 0.0 END) as success_rate
            FROM feedme_search_events 
            WHERE timestamp BETWEEN :start_date AND :end_date
        """)

        result = await self.db.fetch_one(
            query, {"start_date": start_date, "end_date": end_date}
        )

        return (
            dict(result)
            if result
            else {
                "total_searches": 0,
                "unique_users": 0,
                "avg_response_time": 0.0,
                "click_through_rate": 0.0,
                "success_rate": 0.0,
            }
        )

    async def _get_top_queries(
        self, start_date: datetime, end_date: datetime, limit: int = 10
    ) -> List[Dict[str, Any]]:
        """Get most frequent queries"""
        query = text("""
            SELECT 
                query,
                COUNT(*) as frequency,
                AVG(response_time_ms) as avg_response_time,
                AVG(CASE WHEN results_count > 0 THEN 1.0 ELSE 0.0 END) as success_rate,
                AVG(CASE WHEN array_length(clicked_results, 1) > 0 THEN 1.0 ELSE 0.0 END) as click_through_rate
            FROM feedme_search_events 
            WHERE timestamp BETWEEN :start_date AND :end_date
            GROUP BY query
            HAVING COUNT(*) >= 5  -- Minimum frequency threshold
            ORDER BY frequency DESC
            LIMIT :limit
        """)

        # Use proper async SQLAlchemy execution
        async with self.db.begin() as transaction:
            result = await transaction.execute(
                query, {"start_date": start_date, "end_date": end_date, "limit": limit}
            )
            rows = result.fetchall()

        return [
            {
                "query": row[0],
                "frequency": row[1],
                "avg_response_time": row[2],
                "success_rate": row[3],
                "click_through_rate": row[4],
            }
            for row in rows
        ]

    async def _get_performance_trends(
        self, start_date: datetime, end_date: datetime
    ) -> Dict[str, Any]:
        """Get performance trends over time"""
        query = text("""
            SELECT 
                DATE_TRUNC('hour', timestamp) as hour,
                AVG(response_time_ms) as avg_response_time,
                COUNT(*) as search_count,
                AVG(CASE WHEN results_count > 0 THEN 1.0 ELSE 0.0 END) as success_rate
            FROM feedme_search_events 
            WHERE timestamp BETWEEN :start_date AND :end_date
            GROUP BY DATE_TRUNC('hour', timestamp)
            ORDER BY hour
        """)

        results = await self.db.fetch_all(
            query, {"start_date": start_date, "end_date": end_date}
        )

        # Calculate trends
        response_times = [r["avg_response_time"] for r in results]
        success_rates = [r["success_rate"] for r in results]

        response_time_trend = self._calculate_trend(response_times)
        success_rate_trend = self._calculate_trend(success_rates)

        return {
            "response_time_trend": response_time_trend,
            "success_rate_trend": success_rate_trend,
            "hourly_data": [dict(r) for r in results],
        }

    def _calculate_trend(self, values: List[float]) -> Dict[str, Any]:
        """Calculate trend direction and strength"""
        if len(values) < 2:
            return {"direction": "stable", "strength": 0.0}

        # Linear regression to determine trend
        x = np.arange(len(values))
        y = np.array(values)

        slope, intercept, r_value, p_value, std_err = stats.linregress(x, y)

        # Determine trend direction
        if abs(slope) < 0.01:
            direction = "stable"
        elif slope > 0:
            direction = "increasing"
        else:
            direction = "decreasing"

        return {
            "direction": direction,
            "strength": abs(r_value),
            "slope": slope,
            "p_value": p_value,
        }

    async def _get_optimization_opportunities(self) -> List[Dict[str, Any]]:
        """Identify optimization opportunities"""
        opportunities = []

        # Check for slow queries
        slow_queries = await self._identify_slow_queries()
        if slow_queries:
            opportunities.append(
                {
                    "type": "performance_optimization",
                    "priority": "high",
                    "description": f"Optimize {len(slow_queries)} slow query patterns",
                    "impact_score": 0.8,
                    "queries": slow_queries[:5],  # Top 5 slow queries
                }
            )

        # Check for low success rate queries
        low_success_queries = await self._identify_low_success_queries()
        if low_success_queries:
            opportunities.append(
                {
                    "type": "search_quality_improvement",
                    "priority": "medium",
                    "description": f"Improve {len(low_success_queries)} queries with low success rates",
                    "impact_score": 0.6,
                    "queries": low_success_queries[:5],
                }
            )

        return opportunities

    async def _identify_slow_queries(self) -> List[Dict[str, Any]]:
        """Identify consistently slow queries"""
        query = text("""
            SELECT 
                query,
                COUNT(*) as frequency,
                AVG(response_time_ms) as avg_response_time,
                PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY response_time_ms) as p95_response_time
            FROM feedme_search_events 
            WHERE timestamp >= NOW() - INTERVAL '7 days'
            GROUP BY query
            HAVING COUNT(*) >= 10 AND AVG(response_time_ms) > 1000
            ORDER BY avg_response_time DESC
            LIMIT 20
        """)

        results = await self.db.fetch_all(query)
        return [dict(result) for result in results]

    async def _identify_low_success_queries(self) -> List[Dict[str, Any]]:
        """Identify queries with consistently low success rates"""
        query = text("""
            SELECT 
                query,
                COUNT(*) as frequency,
                AVG(CASE WHEN results_count > 0 THEN 1.0 ELSE 0.0 END) as success_rate,
                AVG(response_time_ms) as avg_response_time
            FROM feedme_search_events 
            WHERE timestamp >= NOW() - INTERVAL '7 days'
            GROUP BY query
            HAVING COUNT(*) >= 10 AND AVG(CASE WHEN results_count > 0 THEN 1.0 ELSE 0.0 END) < 0.5
            ORDER BY frequency DESC
            LIMIT 20
        """)

        results = await self.db.fetch_all(query)
        return [dict(result) for result in results]

    async def analyze_search_patterns(
        self, time_window_hours: int = 24
    ) -> List[Dict[str, Any]]:
        """Analyze search patterns within a time window"""
        start_time = datetime.utcnow() - timedelta(hours=time_window_hours)

        query = text("""
            SELECT 
                query,
                COUNT(*) as frequency,
                AVG(results_count) as avg_results,
                AVG(CASE WHEN results_count > 0 THEN 1.0 ELSE 0.0 END) as success_rate,
                AVG(response_time_ms) as avg_response_time,
                string_agg(DISTINCT search_type, ', ') as search_types_used
            FROM feedme_search_events 
            WHERE timestamp >= :start_time
            GROUP BY query
            HAVING COUNT(*) >= 3
            ORDER BY frequency DESC
            LIMIT 50
        """)

        results = await self.db.fetch_all(query, {"start_time": start_time})
        return [dict(result) for result in results]

    async def analyze_user_behavior(
        self, time_period_days: int = 30
    ) -> UserBehaviorAnalytics:
        """Analyze user behavior patterns"""
        start_date = datetime.utcnow() - timedelta(days=time_period_days)

        # Get user segments
        user_segments = await self._get_user_segments(start_date)

        # Get search patterns by segment
        search_patterns = await self._get_search_patterns_by_segment(start_date)

        # Get temporal patterns
        temporal_patterns = await self._get_temporal_patterns(start_date)

        # Get retention metrics
        retention_metrics = await self._get_retention_metrics(start_date)

        return UserBehaviorAnalytics(
            user_segments=user_segments,
            search_patterns_by_segment=search_patterns,
            temporal_patterns=temporal_patterns,
            retention_metrics=retention_metrics,
        )

    async def _get_user_segments(self, start_date: datetime) -> List[Dict[str, Any]]:
        """Segment users based on behavior patterns"""
        query = text("""
            SELECT 
                user_id,
                COUNT(*) as search_count,
                AVG(response_time_ms) as avg_response_time,
                STRING_AGG(DISTINCT search_type, ', ') as preferred_search_types,
                AVG(CASE WHEN results_count > 0 THEN 1.0 ELSE 0.0 END) as success_rate,
                COUNT(DISTINCT DATE(timestamp)) as active_days
            FROM feedme_search_events 
            WHERE timestamp >= :start_date
            GROUP BY user_id
            HAVING COUNT(*) >= 5  -- Minimum activity threshold
        """)

        results = await self.db.fetch_all(query, {"start_date": start_date})

        # Segment users based on activity levels
        user_data = [dict(result) for result in results]
        segments = []

        for user in user_data:
            if user["search_count"] >= 50:
                segment = "expert"
            elif user["search_count"] >= 20:
                segment = "intermediate"
            else:
                segment = "beginner"

            segments.append({**user, "segment": segment})

        return segments

    async def _get_search_patterns_by_segment(
        self, start_date: datetime
    ) -> Dict[str, Any]:
        """Get search patterns for each user segment"""
        # This would involve more complex analysis
        # For now, return a placeholder structure
        return {
            "expert": {
                "avg_queries_per_session": 8.5,
                "preferred_search_type": "hybrid",
            },
            "intermediate": {
                "avg_queries_per_session": 4.2,
                "preferred_search_type": "vector",
            },
            "beginner": {
                "avg_queries_per_session": 2.1,
                "preferred_search_type": "text",
            },
        }

    async def _get_temporal_patterns(self, start_date: datetime) -> Dict[str, Any]:
        """Get temporal usage patterns"""
        query = text("""
            SELECT 
                EXTRACT(hour FROM timestamp) as hour,
                EXTRACT(dow FROM timestamp) as day_of_week,
                COUNT(*) as search_count
            FROM feedme_search_events 
            WHERE timestamp >= :start_date
            GROUP BY EXTRACT(hour FROM timestamp), EXTRACT(dow FROM timestamp)
            ORDER BY search_count DESC
        """)

        results = await self.db.fetch_all(query, {"start_date": start_date})

        # Find peak hours
        hourly_totals = defaultdict(int)
        for result in results:
            hourly_totals[int(result["hour"])] += result["search_count"]

        peak_hours = sorted(hourly_totals.items(), key=lambda x: x[1], reverse=True)[:3]

        return {
            "peak_hours": [hour for hour, count in peak_hours],
            "hourly_distribution": dict(hourly_totals),
            "detailed_patterns": [dict(result) for result in results],
        }

    async def _get_retention_metrics(self, start_date: datetime) -> Dict[str, Any]:
        """Calculate user retention metrics"""
        # Calculate daily, weekly, and monthly retention
        # This is a simplified version
        query = text("""
            SELECT 
                DATE(timestamp) as date,
                COUNT(DISTINCT user_id) as daily_active_users
            FROM feedme_search_events 
            WHERE timestamp >= :start_date
            GROUP BY DATE(timestamp)
            ORDER BY date
        """)

        results = await self.db.fetch_all(query, {"start_date": start_date})

        daily_users = [result["daily_active_users"] for result in results]

        return {
            "avg_daily_active_users": np.mean(daily_users) if daily_users else 0,
            "retention_trend": self._calculate_trend(daily_users),
            "daily_active_users": [dict(result) for result in results],
        }

    async def detect_anomalies(self, events: List[SearchEvent]) -> List[Dict[str, Any]]:
        """Detect anomalies in search events"""
        anomalies = []

        if not events:
            return anomalies

        # Response time anomalies
        response_times = [event.response_time_ms for event in events]
        mean_time = np.mean(response_times)
        std_time = np.std(response_times)

        for event in events:
            if event.response_time_ms > mean_time + (3 * std_time):
                anomalies.append(
                    {
                        "type": "performance_anomaly",
                        "severity": "high",
                        "user_id": event.user_id,
                        "response_time": event.response_time_ms,
                        "expected_range": f"{mean_time:.0f}±{3 * std_time:.0f}ms",
                    }
                )

        return anomalies
