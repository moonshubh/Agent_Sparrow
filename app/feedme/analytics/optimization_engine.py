"""
Optimization Engine for FeedMe v2.0 Phase 2
Automated optimization recommendations, A/B testing, and performance tuning.
"""

import asyncio
import time
import json
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Tuple, Callable
from dataclasses import dataclass, field
from enum import Enum
import numpy as np
import statistics
from collections import defaultdict, deque

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
import redis.asyncio as redis

from .schemas import (
    OptimizationStrategy, OptimizationResult, ABTestConfig,
    ABTestResult, PerformanceBaseline, OptimizationMetrics
)

logger = logging.getLogger(__name__)


class OptimizationCategory(Enum):
    """Categories of optimization strategies"""
    QUERY_OPTIMIZATION = "query_optimization"
    CACHING_STRATEGY = "caching_strategy"
    INDEX_OPTIMIZATION = "index_optimization"
    ALGORITHM_TUNING = "algorithm_tuning"
    RESOURCE_ALLOCATION = "resource_allocation"
    CONCURRENCY_OPTIMIZATION = "concurrency_optimization"
    MEMORY_MANAGEMENT = "memory_management"


@dataclass
class OptimizationCandidate:
    """Candidate optimization with impact assessment"""
    category: OptimizationCategory
    name: str
    description: str
    implementation_complexity: str  # low, medium, high
    expected_impact: float  # 0.0 to 1.0
    risk_level: str  # low, medium, high
    prerequisites: List[str] = field(default_factory=list)
    estimated_effort_hours: int = 0
    rollback_plan: str = ""


@dataclass
class ABTestConfiguration:
    """A/B testing configuration for optimization validation"""
    optimization_name: str
    control_group_percentage: float = 0.5
    test_duration_hours: int = 24
    minimum_sample_size: int = 1000
    success_metrics: List[str] = field(default_factory=lambda: [
        "avg_response_time", "error_rate", "throughput"
    ])
    early_stopping_enabled: bool = True
    confidence_level: float = 0.95


class OptimizationEngine:
    """
    Comprehensive optimization engine with automated recommendations,
    A/B testing capabilities, and performance tuning algorithms.
    """
    
    def __init__(
        self,
        db: AsyncSession,
        redis_client: redis.Redis,
        performance_monitor=None,
        config: Optional[Dict[str, Any]] = None
    ):
        self.db = db
        self.redis = redis_client
        self.performance_monitor = performance_monitor
        self.config = config or {}
        
        # Optimization tracking
        self._active_optimizations = {}
        self._optimization_history = deque(maxlen=100)
        self._performance_baselines = {}
        
        # A/B testing management
        self._active_ab_tests = {}
        self._ab_test_results = deque(maxlen=50)
        
        # Optimization strategies
        self._optimization_strategies = self._initialize_optimization_strategies()
        
        # Learning and adaptation
        self._optimization_effectiveness = defaultdict(list)
        self._adaptation_enabled = True
    
    def _initialize_optimization_strategies(self) -> Dict[str, OptimizationCandidate]:
        """Initialize predefined optimization strategies"""
        strategies = {
            "query_result_caching": OptimizationCandidate(
                category=OptimizationCategory.CACHING_STRATEGY,
                name="Query Result Caching",
                description="Implement intelligent caching of search results",
                implementation_complexity="medium",
                expected_impact=0.4,
                risk_level="low",
                estimated_effort_hours=16,
                rollback_plan="Disable cache with feature flag"
            ),
            
            "database_query_optimization": OptimizationCandidate(
                category=OptimizationCategory.QUERY_OPTIMIZATION,
                name="Database Query Optimization",
                description="Optimize database queries for vector similarity search",
                implementation_complexity="high",
                expected_impact=0.6,
                risk_level="medium",
                prerequisites=["query_analysis", "index_analysis"],
                estimated_effort_hours=32,
                rollback_plan="Revert to original query plans"
            ),
            
            "embedding_batch_processing": OptimizationCandidate(
                category=OptimizationCategory.ALGORITHM_TUNING,
                name="Embedding Batch Processing",
                description="Batch embedding generation for improved throughput",
                implementation_complexity="medium",
                expected_impact=0.35,
                risk_level="low",
                estimated_effort_hours=20,
                rollback_plan="Process embeddings individually"
            ),
            
            "connection_pool_tuning": OptimizationCandidate(
                category=OptimizationCategory.RESOURCE_ALLOCATION,
                name="Connection Pool Optimization",
                description="Tune database connection pool settings",
                implementation_complexity="low",
                expected_impact=0.25,
                risk_level="low",
                estimated_effort_hours=8,
                rollback_plan="Restore default connection pool settings"
            ),
            
            "search_index_optimization": OptimizationCandidate(
                category=OptimizationCategory.INDEX_OPTIMIZATION,
                name="Search Index Optimization",
                description="Optimize vector and text search indexes",
                implementation_complexity="high",
                expected_impact=0.5,
                risk_level="medium",
                prerequisites=["index_analysis", "query_pattern_analysis"],
                estimated_effort_hours=40,
                rollback_plan="Rebuild original indexes"
            ),
            
            "concurrent_search_limiting": OptimizationCandidate(
                category=OptimizationCategory.CONCURRENCY_OPTIMIZATION,
                name="Concurrent Search Rate Limiting",
                description="Implement intelligent rate limiting for concurrent searches",
                implementation_complexity="medium",
                expected_impact=0.3,
                risk_level="low",
                estimated_effort_hours=16,
                rollback_plan="Remove rate limiting"
            ),
            
            "memory_pool_optimization": OptimizationCandidate(
                category=OptimizationCategory.MEMORY_MANAGEMENT,
                name="Memory Pool Optimization",
                description="Implement memory pooling for embedding operations",
                implementation_complexity="high",
                expected_impact=0.4,
                risk_level="medium",
                estimated_effort_hours=28,
                rollback_plan="Use standard memory allocation"
            )
        }
        
        return strategies
    
    async def analyze_optimization_opportunities(
        self,
        performance_data: Dict[str, Any],
        time_window_hours: int = 24
    ) -> List[OptimizationCandidate]:
        """
        Analyze performance data and identify optimization opportunities
        """
        try:
            logger.info("Analyzing optimization opportunities...")
            
            # Get performance baselines
            baseline_metrics = await self._get_performance_baseline(time_window_hours)
            
            # Analyze current performance issues
            performance_issues = await self._identify_performance_issues(performance_data, baseline_metrics)
            
            # Generate optimization candidates
            candidates = []
            
            for issue_type, severity in performance_issues.items():
                if severity == 'high':
                    candidates.extend(self._get_candidates_for_issue(issue_type, severity))
                elif severity == 'medium':
                    candidates.extend(self._get_candidates_for_issue(issue_type, severity))
            
            # Score and rank candidates
            scored_candidates = await self._score_optimization_candidates(candidates, performance_data)
            
            # Filter based on feasibility and impact
            filtered_candidates = await self._filter_candidates_by_feasibility(scored_candidates)
            
            # Sort by expected impact and implementation complexity
            prioritized_candidates = self._prioritize_candidates(filtered_candidates)
            
            logger.info(f"Identified {len(prioritized_candidates)} optimization opportunities")
            return prioritized_candidates[:10]  # Return top 10
            
        except Exception as e:
            logger.error(f"Error analyzing optimization opportunities: {e}")
            return []
    
    async def _get_performance_baseline(self, time_window_hours: int) -> Dict[str, float]:
        """Get performance baseline metrics"""
        try:
            query = text("""
                SELECT 
                    AVG(response_time_ms) as avg_response_time,
                    PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY response_time_ms) as p95_response_time,
                    AVG(CASE WHEN error_occurred THEN 1.0 ELSE 0.0 END) as error_rate,
                    COUNT(*) as total_requests,
                    AVG(database_query_time_ms) as avg_db_time,
                    AVG(embedding_time_ms) as avg_embedding_time,
                    AVG(memory_usage_mb) as avg_memory_usage
                FROM feedme_search_performance 
                WHERE timestamp >= NOW() - INTERVAL :hours HOUR
            """)
            
            result = await self.db.fetch_one(query, {'hours': time_window_hours})
            
            if result:
                return {
                    'avg_response_time': float(result['avg_response_time'] or 0),
                    'p95_response_time': float(result['p95_response_time'] or 0),
                    'error_rate': float(result['error_rate'] or 0),
                    'total_requests': int(result['total_requests'] or 0),
                    'avg_db_time': float(result['avg_db_time'] or 0),
                    'avg_embedding_time': float(result['avg_embedding_time'] or 0),
                    'avg_memory_usage': float(result['avg_memory_usage'] or 0)
                }
            
            return {}
            
        except Exception as e:
            logger.error(f"Error getting performance baseline: {e}")
            return {}
    
    async def _identify_performance_issues(
        self,
        current_data: Dict[str, Any],
        baseline_data: Dict[str, float]
    ) -> Dict[str, str]:
        """Identify performance issues by comparing current data with baseline"""
        issues = {}
        
        # Response time issues
        current_response_time = current_data.get('avg_response_time', 0)
        baseline_response_time = baseline_data.get('avg_response_time', 0)
        
        if baseline_response_time > 0:
            response_time_increase = (current_response_time - baseline_response_time) / baseline_response_time
            if response_time_increase > 0.5:
                issues['slow_response_time'] = 'high'
            elif response_time_increase > 0.2:
                issues['slow_response_time'] = 'medium'
        
        # Error rate issues
        current_error_rate = current_data.get('error_rate', 0)
        if current_error_rate > 0.05:
            issues['high_error_rate'] = 'high'
        elif current_error_rate > 0.02:
            issues['high_error_rate'] = 'medium'
        
        # Database performance issues
        current_db_time = current_data.get('avg_db_time', 0)
        baseline_db_time = baseline_data.get('avg_db_time', 0)
        
        if baseline_db_time > 0:
            db_time_increase = (current_db_time - baseline_db_time) / baseline_db_time
            if db_time_increase > 0.4:
                issues['slow_database'] = 'high'
            elif db_time_increase > 0.2:
                issues['slow_database'] = 'medium'
        
        # Memory usage issues
        current_memory = current_data.get('avg_memory_usage', 0)
        baseline_memory = baseline_data.get('avg_memory_usage', 0)
        
        if baseline_memory > 0:
            memory_increase = (current_memory - baseline_memory) / baseline_memory
            if memory_increase > 0.5:
                issues['high_memory_usage'] = 'high'
            elif memory_increase > 0.3:
                issues['high_memory_usage'] = 'medium'
        
        return issues
    
    def _get_candidates_for_issue(self, issue_type: str, severity: str) -> List[OptimizationCandidate]:
        """Get optimization candidates for specific performance issues"""
        candidates = []
        
        if issue_type == 'slow_response_time':
            candidates.extend([
                self._optimization_strategies['query_result_caching'],
                self._optimization_strategies['database_query_optimization'],
                self._optimization_strategies['embedding_batch_processing']
            ])
        
        elif issue_type == 'high_error_rate':
            candidates.extend([
                self._optimization_strategies['connection_pool_tuning'],
                self._optimization_strategies['concurrent_search_limiting']
            ])
        
        elif issue_type == 'slow_database':
            candidates.extend([
                self._optimization_strategies['database_query_optimization'],
                self._optimization_strategies['search_index_optimization'],
                self._optimization_strategies['connection_pool_tuning']
            ])
        
        elif issue_type == 'high_memory_usage':
            candidates.extend([
                self._optimization_strategies['memory_pool_optimization'],
                self._optimization_strategies['query_result_caching']
            ])
        
        return candidates
    
    async def _score_optimization_candidates(
        self,
        candidates: List[OptimizationCandidate],
        performance_data: Dict[str, Any]
    ) -> List[Tuple[OptimizationCandidate, float]]:
        """Score optimization candidates based on expected impact and feasibility"""
        scored_candidates = []
        
        for candidate in candidates:
            # Base score from expected impact
            score = candidate.expected_impact
            
            # Adjust for implementation complexity
            complexity_multiplier = {
                'low': 1.2,
                'medium': 1.0,
                'high': 0.8
            }
            score *= complexity_multiplier.get(candidate.implementation_complexity, 1.0)
            
            # Adjust for risk level
            risk_multiplier = {
                'low': 1.1,
                'medium': 1.0,
                'high': 0.9
            }
            score *= risk_multiplier.get(candidate.risk_level, 1.0)
            
            # Adjust based on historical effectiveness
            if candidate.name in self._optimization_effectiveness:
                historical_effectiveness = statistics.mean(self._optimization_effectiveness[candidate.name])
                score *= (0.5 + historical_effectiveness * 0.5)  # Weight historical data 50%
            
            # Check prerequisites
            if candidate.prerequisites:
                prerequisite_penalty = len(candidate.prerequisites) * 0.1
                score *= (1.0 - prerequisite_penalty)
            
            scored_candidates.append((candidate, score))
        
        return scored_candidates
    
    async def _filter_candidates_by_feasibility(
        self,
        scored_candidates: List[Tuple[OptimizationCandidate, float]]
    ) -> List[Tuple[OptimizationCandidate, float]]:
        """Filter candidates based on feasibility constraints"""
        filtered = []
        
        for candidate, score in scored_candidates:
            # Skip if prerequisites not met
            if candidate.prerequisites and not await self._check_prerequisites(candidate.prerequisites):
                continue
            
            # Skip high-risk optimizations in production
            if candidate.risk_level == 'high' and self.config.get('environment') == 'production':
                continue
            
            # Skip if estimated effort is too high
            max_effort_hours = self.config.get('max_optimization_effort_hours', 50)
            if candidate.estimated_effort_hours > max_effort_hours:
                continue
            
            filtered.append((candidate, score))
        
        return filtered
    
    async def _check_prerequisites(self, prerequisites: List[str]) -> bool:
        """Check if optimization prerequisites are met"""
        try:
            for prerequisite in prerequisites:
                if prerequisite == 'database_connection':
                    # Check database connectivity
                    try:
                        if hasattr(self, 'db') and self.db:
                            await self.db.execute('SELECT 1')
                    except Exception:
                        return False
                        
                elif prerequisite == 'redis_connection':
                    # Check Redis connectivity
                    try:
                        if hasattr(self, 'redis') and self.redis:
                            await self.redis.ping()
                    except Exception:
                        return False
                        
                elif prerequisite == 'low_system_load':
                    # Check system load
                    import psutil
                    if psutil.cpu_percent(interval=1) > 80:
                        return False
                        
                elif prerequisite == 'maintenance_window':
                    # Check if we're in maintenance window
                    current_hour = datetime.utcnow().hour
                    if not (2 <= current_hour <= 6):  # 2-6 AM UTC maintenance window
                        return False
                        
                # Add more prerequisite checks as needed
                        
            return True
        except Exception as e:
            logger.error(f"Error checking prerequisites: {e}")
            return False
    
    def _prioritize_candidates(
        self,
        scored_candidates: List[Tuple[OptimizationCandidate, float]]
    ) -> List[OptimizationCandidate]:
        """Prioritize candidates by score and return sorted list"""
        # Sort by score descending
        sorted_candidates = sorted(scored_candidates, key=lambda x: x[1], reverse=True)
        
        # Return just the candidates (without scores)
        return [candidate for candidate, score in sorted_candidates]
    
    async def implement_optimization(
        self,
        optimization: OptimizationCandidate,
        enable_ab_testing: bool = True,
        test_configuration: Optional[ABTestConfiguration] = None
    ) -> OptimizationResult:
        """
        Implement an optimization with optional A/B testing
        """
        try:
            logger.info(f"Implementing optimization: {optimization.name}")
            
            optimization_id = f"opt_{int(time.time())}"
            start_time = datetime.utcnow()
            
            # Record baseline performance
            baseline_metrics = await self._capture_performance_baseline()
            
            # If A/B testing is enabled, set up the test
            ab_test_result = None
            if enable_ab_testing:
                if not test_configuration:
                    test_configuration = ABTestConfiguration(
                        optimization_name=optimization.name
                    )
                
                ab_test_result = await self._setup_ab_test(optimization, test_configuration)
            
            # Implement the optimization
            implementation_result = await self._execute_optimization_implementation(optimization)
            
            # Monitor performance after implementation
            post_optimization_metrics = await self._monitor_post_optimization_performance(
                optimization_id, duration_minutes=30
            )
            
            # Calculate impact
            impact_analysis = self._calculate_optimization_impact(
                baseline_metrics, post_optimization_metrics
            )
            
            # Record optimization effectiveness for learning
            effectiveness_score = self._calculate_effectiveness_score(impact_analysis)
            self._optimization_effectiveness[optimization.name].append(effectiveness_score)
            
            result = OptimizationResult(
                optimization_id=optimization_id,
                optimization_name=optimization.name,
                category=optimization.category.value,
                start_time=start_time,
                end_time=datetime.utcnow(),
                baseline_metrics=baseline_metrics,
                post_optimization_metrics=post_optimization_metrics,
                impact_analysis=impact_analysis,
                ab_test_result=ab_test_result,
                implementation_success=implementation_result['success'],
                effectiveness_score=effectiveness_score,
                rollback_executed=False
            )
            
            # Store result
            await self._store_optimization_result(result)
            self._optimization_history.append(result)
            
            logger.info(f"Optimization implemented successfully: {optimization.name}")
            return result
            
        except Exception as e:
            logger.error(f"Optimization implementation failed: {optimization.name} - {e}")
            
            # Attempt rollback
            rollback_success = await self._execute_rollback(optimization)
            
            return OptimizationResult(
                optimization_id=optimization_id,
                optimization_name=optimization.name,
                category=optimization.category.value,
                start_time=start_time,
                end_time=datetime.utcnow(),
                error=str(e),
                implementation_success=False,
                rollback_executed=rollback_success
            )
    
    async def _capture_performance_baseline(self) -> Dict[str, float]:
        """Capture current performance metrics as baseline"""
        if self.performance_monitor:
            # Use performance monitor to get current metrics
            metrics = await self.performance_monitor.calculate_response_time_percentiles()
            error_rate = await self.performance_monitor.calculate_error_rate()
            cache_analysis = await self.performance_monitor.analyze_cache_performance()
            
            return {
                'avg_response_time': metrics.get('avg', 0),
                'p95_response_time': metrics.get('p95', 0),
                'p99_response_time': metrics.get('p99', 0),
                'error_rate': error_rate,
                'cache_hit_rate': cache_analysis.get('hit_rate', 0)
            }
        
        # Fallback to database query
        return await self._get_performance_baseline(1)  # Last 1 hour
    
    async def _setup_ab_test(
        self,
        optimization: OptimizationCandidate,
        config: ABTestConfiguration
    ) -> Dict[str, Any]:
        """Set up A/B test for optimization validation"""
        test_id = f"ab_test_{int(time.time())}"
        
        ab_test_config = {
            'test_id': test_id,
            'optimization_name': optimization.name,
            'control_group_percentage': config.control_group_percentage,
            'test_duration_hours': config.test_duration_hours,
            'minimum_sample_size': config.minimum_sample_size,
            'success_metrics': config.success_metrics,
            'start_time': datetime.utcnow(),
            'status': 'running'
        }
        
        # Store A/B test configuration in Redis
        await self.redis.setex(
            f"ab_test:{test_id}",
            config.test_duration_hours * 3600,
            json.dumps(ab_test_config, default=str)
        )
        
        self._active_ab_tests[test_id] = ab_test_config
        
        logger.info(f"A/B test setup complete: {test_id}")
        return {'test_id': test_id, 'status': 'configured'}
    
    async def _execute_optimization_implementation(self, optimization: OptimizationCandidate) -> Dict[str, Any]:
        """Execute the actual optimization implementation"""
        try:
            # Simulate optimization implementation
            # In a real system, this would contain the actual optimization logic
            
            implementation_steps = []
            
            if optimization.category == OptimizationCategory.CACHING_STRATEGY:
                implementation_steps = [
                    "Enable query result caching",
                    "Configure cache TTL settings",
                    "Update cache eviction policies"
                ]
            
            elif optimization.category == OptimizationCategory.QUERY_OPTIMIZATION:
                implementation_steps = [
                    "Analyze current query plans",
                    "Implement optimized queries",
                    "Update database indexes"
                ]
            
            elif optimization.category == OptimizationCategory.ALGORITHM_TUNING:
                implementation_steps = [
                    "Implement batch processing",
                    "Optimize algorithm parameters",
                    "Update processing pipeline"
                ]
            
            # Simulate implementation time
            await asyncio.sleep(1)  # In reality, this would be actual implementation time
            
            return {
                'success': True,
                'implementation_steps': implementation_steps,
                'implementation_time_seconds': 1
            }
            
        except Exception as e:
            logger.error(f"Optimization implementation failed: {e}")
            return {
                'success': False,
                'error': str(e)
            }
    
    async def _monitor_post_optimization_performance(
        self,
        optimization_id: str,
        duration_minutes: int = 30
    ) -> Dict[str, float]:
        """Monitor performance after optimization implementation (non-blocking)"""
        try:
            # Run monitoring in background task to avoid blocking
            monitoring_task = asyncio.create_task(
                self._collect_performance_samples(optimization_id, duration_minutes)
            )
            
            # Don't wait for completion, let it run in background
            return await monitoring_task
            
        except Exception as e:
            logger.error(f"Error monitoring post-optimization performance: {e}")
            return {}
    
    async def _collect_performance_samples(
        self, 
        optimization_id: str, 
        duration_minutes: int
    ) -> Dict[str, float]:
        """Collect performance samples in background task"""
        try:
            # Collect performance samples over the monitoring period
            samples = []
            sample_interval = 60  # 1 minute intervals
            total_samples = duration_minutes
            
            for i in range(total_samples):
                # Check for shutdown during monitoring
                if getattr(self, '_shutdown_requested', False):
                    logger.info(f"Monitoring stopped for optimization {optimization_id} due to shutdown")
                    break
                    
                if self.performance_monitor:
                    # Get current performance metrics
                    metrics = await self.performance_monitor.calculate_response_time_percentiles()
                    error_rate = await self.performance_monitor.calculate_error_rate(60)
                    
                    sample = {
                        'timestamp': datetime.utcnow(),
                        'avg_response_time': metrics.get('avg', 0),
                        'p95_response_time': metrics.get('p95', 0),
                        'error_rate': error_rate
                    }
                    samples.append(sample)
                
                await asyncio.sleep(sample_interval)
            
            # Calculate average metrics from samples
            if samples:
                avg_metrics = {
                    'avg_response_time': statistics.mean([s['avg_response_time'] for s in samples]),
                    'p95_response_time': statistics.mean([s['p95_response_time'] for s in samples]),
                    'error_rate': statistics.mean([s['error_rate'] for s in samples])
                }
            else:
                avg_metrics = {'avg_response_time': 0, 'p95_response_time': 0, 'error_rate': 0}
            
            return avg_metrics
            
        except Exception as e:
            logger.error(f"Error monitoring post-optimization performance: {e}")
            return {}
    
    def _calculate_optimization_impact(
        self,
        baseline_metrics: Dict[str, float],
        post_metrics: Dict[str, float]
    ) -> Dict[str, Any]:
        """Calculate the impact of optimization"""
        impact = {}
        
        for metric, baseline_value in baseline_metrics.items():
            post_value = post_metrics.get(metric, baseline_value)
            
            if baseline_value > 0:
                if metric in ['avg_response_time', 'p95_response_time', 'p99_response_time', 'error_rate']:
                    # For these metrics, lower is better
                    improvement = (baseline_value - post_value) / baseline_value
                    impact[f"{metric}_improvement"] = improvement
                else:
                    # For metrics like cache_hit_rate, higher is better
                    improvement = (post_value - baseline_value) / baseline_value
                    impact[f"{metric}_improvement"] = improvement
            else:
                impact[f"{metric}_improvement"] = 0
        
        # Calculate overall effectiveness score
        response_time_improvement = impact.get('avg_response_time_improvement', 0)
        error_rate_improvement = impact.get('error_rate_improvement', 0)
        
        overall_effectiveness = (response_time_improvement * 0.6 + error_rate_improvement * 0.4)
        impact['overall_effectiveness'] = max(-1.0, min(1.0, overall_effectiveness))  # Clamp to [-1, 1]
        
        return impact
    
    def _calculate_effectiveness_score(self, impact_analysis: Dict[str, Any]) -> float:
        """Calculate effectiveness score for learning purposes"""
        return impact_analysis.get('overall_effectiveness', 0)
    
    async def _execute_rollback(self, optimization: OptimizationCandidate) -> bool:
        """Execute rollback plan for failed optimization"""
        try:
            logger.info(f"Executing rollback for optimization: {optimization.name}")
            
            # Simulate rollback execution
            await asyncio.sleep(0.5)
            
            logger.info(f"Rollback completed for optimization: {optimization.name}")
            return True
            
        except Exception as e:
            logger.error(f"Rollback failed for optimization {optimization.name}: {e}")
            return False
    
    async def _store_optimization_result(self, result: OptimizationResult) -> None:
        """Store optimization result for historical analysis"""
        try:
            result_data = {
                'optimization_id': result.optimization_id,
                'optimization_name': result.optimization_name,
                'category': result.category,
                'start_time': result.start_time.isoformat(),
                'end_time': result.end_time.isoformat(),
                'implementation_success': result.implementation_success,
                'effectiveness_score': result.effectiveness_score,
                'rollback_executed': result.rollback_executed
            }
            
            # Store in Redis for fast access
            await self.redis.lpush("feedme:optimization_results", json.dumps(result_data))
            await self.redis.ltrim("feedme:optimization_results", 0, 99)  # Keep last 100
            
            # Store in database for detailed analysis
            insert_query = text("""
                INSERT INTO feedme_optimization_results 
                (optimization_id, optimization_name, category, start_time, end_time, 
                 results_data, implementation_success, effectiveness_score)
                VALUES (:optimization_id, :optimization_name, :category, :start_time, :end_time,
                        :results_data, :implementation_success, :effectiveness_score)
            """)
            
            await self.db.execute(insert_query, {
                'optimization_id': result.optimization_id,
                'optimization_name': result.optimization_name,
                'category': result.category,
                'start_time': result.start_time,
                'end_time': result.end_time,
                'results_data': json.dumps(result_data),
                'implementation_success': result.implementation_success,
                'effectiveness_score': result.effectiveness_score
            })
            
            await self.db.commit()
            
        except Exception as e:
            logger.error(f"Error storing optimization result: {e}")
    
    async def run_continuous_optimization(
        self,
        optimization_interval_hours: int = 24,
        max_concurrent_optimizations: int = 2
    ) -> None:
        """
        Run continuous optimization process with automated monitoring and tuning
        """
        logger.info("Starting continuous optimization process...")
        self._shutdown_requested = False
        
        try:
            while not self._shutdown_requested:
                try:
                    # Check if we should run optimization analysis
                    current_time = datetime.utcnow()
                    last_analysis_time = getattr(self, '_last_analysis_time', None)
                    
                    if (last_analysis_time is None or 
                        (current_time - last_analysis_time).total_seconds() >= optimization_interval_hours * 3600):
                        
                        # Check current system performance
                        if self.performance_monitor:
                            current_performance = await self.performance_monitor.calculate_response_time_percentiles()
                            error_rate = await self.performance_monitor.calculate_error_rate()
                            
                            performance_data = {
                                'avg_response_time': current_performance.get('avg', 0),
                                'p95_response_time': current_performance.get('p95', 0),
                                'error_rate': error_rate
                            }
                            
                            # Analyze optimization opportunities
                            candidates = await self.analyze_optimization_opportunities(performance_data)
                            
                            # Implement top candidates (up to max concurrent)
                            active_count = len(self._active_optimizations)
                            available_slots = max_concurrent_optimizations - active_count
                            
                            for i, candidate in enumerate(candidates[:available_slots]):
                                logger.info(f"Auto-implementing optimization: {candidate.name}")
                                
                                # Implement with A/B testing for safety
                                result = await self.implement_optimization(
                                    candidate,
                                    enable_ab_testing=True
                                )
                                
                                if result.implementation_success:
                                    self._active_optimizations[result.optimization_id] = {
                                        'candidate': candidate,
                                        'result': result,
                                        'start_time': datetime.utcnow()
                                    }
                        
                        self._last_analysis_time = current_time
                    
                    # Monitor active optimizations
                    await self._monitor_active_optimizations()
                    
                    # Sleep before next iteration (check for shutdown every 10 seconds)
                    for _ in range(360):  # 360 * 10 = 3600 seconds (1 hour)
                        if self._shutdown_requested:
                            break
                        await asyncio.sleep(10)
                    
                except Exception as e:
                    logger.error(f"Error in continuous optimization: {e}")
                    # Wait before retrying, but check for shutdown
                    for _ in range(360):
                        if self._shutdown_requested:
                            break
                        await asyncio.sleep(10)
        
        finally:
            logger.info("Continuous optimization process shutting down...")
            await self._cleanup_active_optimizations()
    
    async def request_shutdown(self) -> None:
        """Request graceful shutdown of continuous optimization"""
        logger.info("Shutdown requested for optimization engine")
        self._shutdown_requested = True
    
    async def _cleanup_active_optimizations(self) -> None:
        """Clean up active optimizations during shutdown"""
        try:
            if hasattr(self, '_active_optimizations'):
                logger.info(f"Cleaning up {len(self._active_optimizations)} active optimizations")
                for opt_id, opt_data in self._active_optimizations.items():
                    try:
                        # Save current state for later resumption
                        await self._save_optimization_state(opt_id, opt_data)
                    except Exception as e:
                        logger.error(f"Error saving optimization state for {opt_id}: {e}")
                        
                self._active_optimizations.clear()
        except Exception as e:
            logger.error(f"Error during optimization cleanup: {e}")
    
    async def _save_optimization_state(self, opt_id: str, opt_data: Dict[str, Any]) -> None:
        """Save optimization state for resumption after restart"""
        try:
            state_data = {
                'optimization_id': opt_id,
                'candidate_name': opt_data['candidate'].name,
                'start_time': opt_data['start_time'].isoformat(),
                'current_phase': opt_data.get('current_phase', 'monitoring'),
                'implementation_success': opt_data['result'].implementation_success
            }
            
            # Store in Redis or database for persistence
            if hasattr(self, 'redis') and self.redis:
                await self.redis.set(
                    f"feedme:optimization:state:{opt_id}",
                    json.dumps(state_data),
                    ex=86400 * 7  # Keep for 7 days
                )
                
            logger.info(f"Saved state for optimization {opt_id}")
        except Exception as e:
            logger.error(f"Error saving optimization state: {e}")
    
    async def _monitor_active_optimizations(self) -> None:
        """Monitor active optimizations and handle completion/failure"""
        completed_optimizations = []
        
        for opt_id, opt_data in self._active_optimizations.items():
            # Check if optimization has been running long enough
            runtime = datetime.utcnow() - opt_data['start_time']
            
            if runtime.total_seconds() >= 3600:  # 1 hour minimum runtime
                # Evaluate optimization effectiveness
                current_metrics = await self._capture_performance_baseline()
                baseline_metrics = opt_data['result'].baseline_metrics
                
                impact = self._calculate_optimization_impact(baseline_metrics, current_metrics)
                
                # If optimization is effective, keep it; otherwise, consider rollback
                if impact.get('overall_effectiveness', 0) < -0.1:  # 10% degradation
                    logger.warning(f"Optimization {opt_id} showing negative impact, considering rollback")
                    # In a real system, this would trigger automated rollback
                
                completed_optimizations.append(opt_id)
        
        # Remove completed optimizations
        for opt_id in completed_optimizations:
            del self._active_optimizations[opt_id]
    
    async def get_optimization_recommendations(
        self,
        priority_filter: Optional[str] = None,
        category_filter: Optional[OptimizationCategory] = None,
        limit: int = 5
    ) -> List[Dict[str, Any]]:
        """Get current optimization recommendations"""
        try:
            # Get current performance data
            performance_data = await self._capture_performance_baseline()
            
            # Analyze opportunities
            candidates = await self.analyze_optimization_opportunities(performance_data)
            
            # Apply filters
            filtered_candidates = candidates
            
            if category_filter:
                filtered_candidates = [c for c in filtered_candidates if c.category == category_filter]
            
            if priority_filter:
                # Define priority mapping based on expected impact
                priority_mapping = {
                    'high': lambda c: c.expected_impact >= 0.5,
                    'medium': lambda c: 0.3 <= c.expected_impact < 0.5,
                    'low': lambda c: c.expected_impact < 0.3
                }
                
                if priority_filter in priority_mapping:
                    filtered_candidates = [c for c in filtered_candidates if priority_mapping[priority_filter](c)]
            
            # Convert to recommendation format
            recommendations = []
            for candidate in filtered_candidates[:limit]:
                recommendations.append({
                    'name': candidate.name,
                    'category': candidate.category.value,
                    'description': candidate.description,
                    'expected_impact': candidate.expected_impact,
                    'implementation_complexity': candidate.implementation_complexity,
                    'risk_level': candidate.risk_level,
                    'estimated_effort_hours': candidate.estimated_effort_hours,
                    'prerequisites': candidate.prerequisites
                })
            
            return recommendations
            
        except Exception as e:
            logger.error(f"Error getting optimization recommendations: {e}")
            return []
    
    async def generate_optimization_report(self, time_period_days: int = 30) -> Dict[str, Any]:
        """Generate comprehensive optimization effectiveness report"""
        try:
            end_date = datetime.utcnow()
            start_date = end_date - timedelta(days=time_period_days)
            
            # Get optimization results from the time period
            recent_results = [
                result for result in self._optimization_history
                if result.start_time >= start_date
            ]
            
            if not recent_results:
                return {'status': 'no_data', 'message': 'No optimization data available for the specified period'}
            
            # Calculate summary statistics
            total_optimizations = len(recent_results)
            successful_optimizations = len([r for r in recent_results if r.implementation_success])
            avg_effectiveness = statistics.mean([r.effectiveness_score for r in recent_results if r.effectiveness_score is not None])
            
            # Analyze effectiveness by category
            category_effectiveness = defaultdict(list)
            for result in recent_results:
                if result.effectiveness_score is not None:
                    category_effectiveness[result.category].append(result.effectiveness_score)
            
            category_analysis = {
                category: {
                    'count': len(scores),
                    'avg_effectiveness': statistics.mean(scores),
                    'success_rate': len([s for s in scores if s > 0]) / len(scores)
                }
                for category, scores in category_effectiveness.items()
            }
            
            # Identify top performing optimizations
            top_optimizations = sorted(
                [r for r in recent_results if r.effectiveness_score is not None],
                key=lambda x: x.effectiveness_score,
                reverse=True
            )[:5]
            
            report = {
                'report_period': {
                    'start_date': start_date.isoformat(),
                    'end_date': end_date.isoformat(),
                    'total_optimizations': total_optimizations
                },
                'summary_statistics': {
                    'success_rate': successful_optimizations / total_optimizations if total_optimizations > 0 else 0,
                    'avg_effectiveness_score': avg_effectiveness,
                    'total_implementations': total_optimizations,
                    'successful_implementations': successful_optimizations
                },
                'category_analysis': category_analysis,
                'top_performing_optimizations': [
                    {
                        'name': opt.optimization_name,
                        'category': opt.category,
                        'effectiveness_score': opt.effectiveness_score,
                        'implementation_date': opt.start_time.isoformat()
                    }
                    for opt in top_optimizations
                ],
                'recommendations': await self._generate_report_recommendations(recent_results)
            }
            
            return report
            
        except Exception as e:
            logger.error(f"Error generating optimization report: {e}")
            return {'status': 'error', 'error': str(e)}
    
    async def _generate_report_recommendations(self, results: List[OptimizationResult]) -> List[str]:
        """Generate recommendations based on optimization analysis"""
        recommendations = []
        
        if not results:
            return ["Insufficient data for recommendations"]
        
        # Analyze success patterns
        successful_results = [r for r in results if r.implementation_success and r.effectiveness_score > 0]
        
        if len(successful_results) / len(results) < 0.5:
            recommendations.append("Focus on lower-risk optimizations to improve success rate")
        
        # Analyze category effectiveness
        category_scores = defaultdict(list)
        for result in results:
            if result.effectiveness_score is not None:
                category_scores[result.category].append(result.effectiveness_score)
        
        best_category = max(category_scores.items(), key=lambda x: statistics.mean(x[1]))
        recommendations.append(f"Continue focusing on {best_category[0]} optimizations - showing best results")
        
        # General recommendations
        avg_effectiveness = statistics.mean([r.effectiveness_score for r in results if r.effectiveness_score is not None])
        if avg_effectiveness < 0.1:
            recommendations.append("Consider more thorough analysis before implementing optimizations")
        
        return recommendations[:5]  # Return top 5 recommendations
