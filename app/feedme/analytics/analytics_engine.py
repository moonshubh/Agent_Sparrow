"""
Analytics Engine for FeedMe v2.0 Phase 2
Main orchestration engine for analytics pipeline and insights generation.
"""

# mypy: ignore-errors

import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any

import redis.asyncio as redis
from sqlalchemy.ext.asyncio import AsyncSession

from .usage_tracker import UsageAnalytics

logger = logging.getLogger(__name__)


class AnalyticsEngine:
    """
    Main analytics orchestration engine that coordinates usage tracking,
    performance monitoring, and insights generation.
    """

    def __init__(
        self,
        usage_tracker: UsageAnalytics,
        db: AsyncSession,
        redis_client: redis.Redis,
        config: Optional[Dict[str, Any]] = None,
    ):
        self.usage_tracker = usage_tracker
        self.db = db
        self.redis = redis_client
        self.config = config or {}

    async def run_analytics_pipeline(self) -> Dict[str, Any]:
        """Run the main analytics pipeline"""
        try:
            # Generate insights using the usage tracker
            insights = await self.usage_tracker.generate_insights(
                start_date=datetime.utcnow() - timedelta(days=7),
                end_date=datetime.utcnow(),
            )

            return {
                "status": "completed",
                "insights": {
                    "total_searches": insights.total_searches,
                    "unique_users": insights.unique_users,
                    "avg_response_time": insights.avg_response_time,
                    "click_through_rate": insights.click_through_rate,
                    "success_rate": insights.success_rate,
                },
            }
        except Exception as e:
            logger.error(f"Analytics pipeline failed: {e}")
            return {"status": "failed", "error": str(e)}

    async def get_real_time_dashboard_data(self) -> Dict[str, Any]:
        """Get real-time dashboard data from Redis"""
        try:
            # Get real-time metrics from Redis
            current_searches = await self.redis.get("analytics:current_searches") or 0
            avg_response_time = await self.redis.get("analytics:avg_response_time") or 0
            click_through_rate = (
                await self.redis.get("analytics:click_through_rate") or 0
            )
            active_users = await self.redis.scard("analytics:active_users") or 0

            return {
                "current_searches": int(current_searches),
                "avg_response_time": float(avg_response_time),
                "click_through_rate": float(click_through_rate),
                "active_users": int(active_users),
            }
        except Exception as e:
            logger.error(f"Failed to get real-time dashboard data: {e}")
            # Return fallback data
            return {
                "current_searches": 0,
                "avg_response_time": 0.0,
                "click_through_rate": 0.0,
                "active_users": 0,
            }

    async def check_performance_alerts(self) -> List[Dict[str, Any]]:
        """Check for performance alerts from Redis"""
        try:
            alerts = []

            # Check for slow search alerts
            avg_response_time = await self.redis.get("analytics:avg_response_time")
            if avg_response_time and float(avg_response_time) > 2000:
                alerts.append(
                    {
                        "type": "slow_search",
                        "response_time": float(avg_response_time),
                        "threshold": 2000,
                        "severity": "high",
                    }
                )

            # Check for high error rate
            error_rate = await self.redis.get("analytics:error_rate")
            if error_rate and float(error_rate) > 0.05:  # 5% error rate threshold
                alerts.append(
                    {
                        "type": "high_error_rate",
                        "error_rate": float(error_rate),
                        "threshold": 0.05,
                        "severity": "high",
                    }
                )

            return alerts
        except Exception as e:
            logger.error(f"Failed to check performance alerts: {e}")
            return []

    async def generate_optimization_recommendations(self) -> List[Dict[str, Any]]:
        """Generate optimization recommendations based on real metrics"""
        try:
            recommendations = []

            # Check response time for query optimization
            avg_response_time = await self.redis.get("analytics:avg_response_time")
            if avg_response_time and float(avg_response_time) > 1000:
                recommendations.append(
                    {
                        "type": "query_optimization",
                        "priority": "high",
                        "description": f"Average response time ({avg_response_time}ms) exceeds threshold",
                        "action": "Consider adding database indexes or query caching",
                    }
                )

            # Check click-through rate for relevance optimization
            ctr = await self.redis.get("analytics:click_through_rate")
            if ctr and float(ctr) < 0.5:
                recommendations.append(
                    {
                        "type": "relevance_optimization",
                        "priority": "medium",
                        "description": f"Low click-through rate ({ctr}) indicates poor search relevance",
                        "action": "Review and improve search ranking algorithms",
                    }
                )

            # Check for memory usage optimization
            memory_usage = await self.redis.get("analytics:memory_usage")
            if memory_usage and float(memory_usage) > 0.8:
                recommendations.append(
                    {
                        "type": "memory_optimization",
                        "priority": "medium",
                        "description": f"High memory usage ({memory_usage}) detected",
                        "action": "Consider implementing result caching or pagination",
                    }
                )

            return recommendations
        except Exception as e:
            logger.error(f"Failed to generate optimization recommendations: {e}")
            return []
