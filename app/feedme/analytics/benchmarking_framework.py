"""
Performance Benchmarking Framework for FeedMe v2.0 Phase 2
Comprehensive load testing, performance profiling, and optimization benchmarks.
"""

import asyncio
import time
import statistics
import json
import psutil
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Union, Callable
from dataclasses import dataclass, field
from contextlib import asynccontextmanager
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
import numpy as np
from collections import defaultdict, deque

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
import redis.asyncio as redis

from .schemas import (
    BenchmarkResult, LoadTestResult, PerformanceProfile,
    OptimizationMetrics, BenchmarkConfig, SystemLoadMetrics
)

logger = logging.getLogger(__name__)


@dataclass
class BenchmarkScenario:
    """Configuration for a specific benchmark scenario"""
    name: str
    description: str
    concurrent_users: int
    duration_seconds: int
    query_patterns: List[str]
    search_types: List[str] = field(default_factory=lambda: ["hybrid", "vector", "text"])
    target_response_time_ms: int = 500
    target_error_rate: float = 0.01
    ramp_up_time_seconds: int = 30


@dataclass
class LoadTestConfiguration:
    """Load testing configuration"""
    scenarios: List[BenchmarkScenario]
    warmup_duration_seconds: int = 60
    cooldown_duration_seconds: int = 30
    data_collection_interval_seconds: int = 5
    enable_real_time_monitoring: bool = True
    auto_scaling_enabled: bool = False


class PerformanceBenchmarkFramework:
    """
    Comprehensive performance benchmarking framework with load testing,
    profiling, and optimization analysis capabilities.
    """
    
    def __init__(
        self,
        db: AsyncSession,
        redis_client: redis.Redis,
        config: Optional[BenchmarkConfig] = None
    ):
        self.db = db
        self.redis = redis_client
        self.config = config or BenchmarkConfig()
        
        # Benchmark state management
        self._active_benchmarks = {}
        self._benchmark_results = deque(maxlen=100)
        
        # Load testing components
        self._load_generators = {}
        self._performance_collectors = {}
        
        # Profiling and analysis
        self._profiler_enabled = False
        self._performance_snapshots = deque(maxlen=1000)
        
        # Optimization tracking
        self._optimization_baselines = {}
        self._improvement_tracking = defaultdict(list)
    
    async def execute_performance_benchmark(
        self,
        scenario: BenchmarkScenario,
        baseline_comparison: bool = True
    ) -> BenchmarkResult:
        """
        Execute a comprehensive performance benchmark with the specified scenario
        """
        # Initialize benchmark_id before try block to ensure it's available in except
        benchmark_id = f"benchmark_{int(time.time())}"
        start_time = datetime.utcnow()
        
        try:
            logger.info(f"Starting benchmark: {scenario.name}")
            
            # Initialize benchmark
            await self._initialize_benchmark(benchmark_id, scenario)
            
            # System warmup
            if scenario.name not in self._optimization_baselines:
                await self._system_warmup(scenario)
            
            # Execute load test
            load_results = await self._execute_load_test(scenario)
            
            # Collect system metrics
            system_metrics = await self._collect_system_metrics_during_test(scenario)
            
            # Analyze performance characteristics
            performance_analysis = await self._analyze_performance_characteristics(
                load_results, system_metrics
            )
            
            # Generate optimization recommendations
            optimization_recommendations = await self._generate_benchmark_optimizations(
                performance_analysis, scenario
            )
            
            # Compare with baseline if requested
            baseline_comparison_result = None
            if baseline_comparison and scenario.name in self._optimization_baselines:
                baseline_comparison_result = await self._compare_with_baseline(
                    performance_analysis, scenario.name
                )
            
            # Create benchmark result
            benchmark_result = BenchmarkResult(
                benchmark_id=benchmark_id,
                scenario_name=scenario.name,
                start_time=start_time,
                end_time=datetime.utcnow(),
                load_test_results=load_results,
                system_metrics=system_metrics,
                performance_analysis=performance_analysis,
                optimization_recommendations=optimization_recommendations,
                baseline_comparison=baseline_comparison_result,
                success=True
            )
            
            # Store results
            await self._store_benchmark_results(benchmark_result)
            self._benchmark_results.append(benchmark_result)
            
            # Update baseline if this is a new best performance
            if self._should_update_baseline(benchmark_result, scenario.name):
                self._optimization_baselines[scenario.name] = performance_analysis
            
            logger.info(f"Benchmark completed: {scenario.name}")
            return benchmark_result
            
        except Exception as e:
            logger.error(f"Benchmark failed: {scenario.name} - {e}")
            # benchmark_id and start_time are now guaranteed to be initialized
            return BenchmarkResult(
                benchmark_id=benchmark_id,
                scenario_name=scenario.name,
                start_time=start_time,
                end_time=datetime.utcnow(),
                error=str(e),
                success=False
            )
    
    async def _initialize_benchmark(self, benchmark_id: str, scenario: BenchmarkScenario) -> None:
        """Initialize benchmark environment and monitoring"""
        self._active_benchmarks[benchmark_id] = {
            'scenario': scenario,
            'status': 'initializing',
            'start_time': datetime.utcnow(),
            'metrics_buffer': deque(maxlen=10000)
        }
        
        # Initialize Redis monitoring keys
        await self.redis.delete(f"benchmark:{benchmark_id}:*")
        await self.redis.setex(f"benchmark:{benchmark_id}:status", 3600, "running")
    
    async def _system_warmup(self, scenario: BenchmarkScenario) -> None:
        """Warm up the system before benchmarking"""
        logger.info("Starting system warmup...")
        
        warmup_queries = scenario.query_patterns[:5]  # Use subset for warmup
        
        # Execute warmup searches
        for i in range(20):
            for query in warmup_queries:
                for search_type in scenario.search_types:
                    try:
                        # Simulate search without recording metrics
                        await self._simulate_search(query, search_type, record_metrics=False)
                        await asyncio.sleep(0.1)
                    except Exception as e:
                        logger.warning(f"Warmup search failed: {e}")
        
        # Allow system to stabilize
        await asyncio.sleep(10)
        logger.info("System warmup completed")
    
    async def _execute_load_test(self, scenario: BenchmarkScenario) -> LoadTestResult:
        """Execute load test with the specified scenario"""
        logger.info(f"Executing load test: {scenario.concurrent_users} users, {scenario.duration_seconds}s")
        
        # Initialize load test tracking
        load_metrics = {
            'total_requests': 0,
            'successful_requests': 0,
            'failed_requests': 0,
            'response_times': [],
            'error_details': [],
            'throughput_samples': [],
            'concurrent_users_actual': []
        }
        
        # Create semaphore for concurrency control
        semaphore = asyncio.Semaphore(scenario.concurrent_users)
        
        # Start load generation
        start_time = time.time()
        end_time = start_time + scenario.duration_seconds
        
        # Launch concurrent load generators
        tasks = []
        for user_id in range(scenario.concurrent_users):
            task = asyncio.create_task(
                self._load_generator_worker(
                    user_id, scenario, semaphore, start_time, end_time, load_metrics
                )
            )
            tasks.append(task)
        
        # Monitor load test progress
        monitoring_task = asyncio.create_task(
            self._monitor_load_test_progress(scenario, load_metrics, start_time, end_time)
        )
        
        # Wait for completion
        await asyncio.gather(*tasks, monitoring_task, return_exceptions=True)
        
        # Calculate final metrics
        total_duration = time.time() - start_time
        avg_throughput = load_metrics['total_requests'] / total_duration
        
        return LoadTestResult(
            scenario_name=scenario.name,
            duration_seconds=total_duration,
            concurrent_users=scenario.concurrent_users,
            total_requests=load_metrics['total_requests'],
            successful_requests=load_metrics['successful_requests'],
            failed_requests=load_metrics['failed_requests'],
            error_rate=load_metrics['failed_requests'] / max(load_metrics['total_requests'], 1),
            avg_response_time_ms=statistics.mean(load_metrics['response_times']) if load_metrics['response_times'] else 0,
            p95_response_time_ms=np.percentile(load_metrics['response_times'], 95) if load_metrics['response_times'] else 0,
            p99_response_time_ms=np.percentile(load_metrics['response_times'], 99) if load_metrics['response_times'] else 0,
            throughput_rps=avg_throughput,
            peak_throughput_rps=max(load_metrics['throughput_samples']) if load_metrics['throughput_samples'] else 0,
            error_details=load_metrics['error_details'][:100]  # Keep top 100 errors
        )
    
    async def _load_generator_worker(
        self,
        user_id: int,
        scenario: BenchmarkScenario,
        semaphore: asyncio.Semaphore,
        start_time: float,
        end_time: float,
        load_metrics: Dict[str, Any]
    ) -> None:
        """Individual load generator worker"""
        try:
            # Stagger start times for ramp-up
            ramp_delay = (user_id / scenario.concurrent_users) * scenario.ramp_up_time_seconds
            await asyncio.sleep(ramp_delay)
            
            while time.time() < end_time:
                async with semaphore:
                    # Select random query and search type
                    query = np.random.choice(scenario.query_patterns)
                    search_type = np.random.choice(scenario.search_types)
                    
                    # Execute search
                    request_start = time.time()
                    try:
                        await self._simulate_search(query, search_type, record_metrics=True)
                        response_time_ms = (time.time() - request_start) * 1000
                        
                        # Record success
                        load_metrics['total_requests'] += 1
                        load_metrics['successful_requests'] += 1
                        load_metrics['response_times'].append(response_time_ms)
                        
                    except Exception as e:
                        # Record failure
                        load_metrics['total_requests'] += 1
                        load_metrics['failed_requests'] += 1
                        load_metrics['error_details'].append({
                            'error': str(e),
                            'query': query[:50],  # Truncate for storage
                            'search_type': search_type,
                            'timestamp': datetime.utcnow().isoformat()
                        })
                
                # Brief pause between requests
                await asyncio.sleep(np.random.uniform(0.1, 0.5))
                
        except Exception as e:
            logger.error(f"Load generator worker {user_id} failed: {e}")
    
    async def _monitor_load_test_progress(
        self,
        scenario: BenchmarkScenario,
        load_metrics: Dict[str, Any],
        start_time: float,
        end_time: float
    ) -> None:
        """Monitor load test progress and collect throughput samples"""
        last_sample_time = start_time
        last_request_count = 0
        
        while time.time() < end_time:
            await asyncio.sleep(5)  # Sample every 5 seconds
            
            current_time = time.time()
            current_requests = load_metrics['total_requests']
            
            # Calculate current throughput
            time_delta = current_time - last_sample_time
            request_delta = current_requests - last_request_count
            
            if time_delta > 0:
                current_throughput = request_delta / time_delta
                load_metrics['throughput_samples'].append(current_throughput)
            
            # Update for next sample
            last_sample_time = current_time
            last_request_count = current_requests
            
            # Log progress
            elapsed = current_time - start_time
            remaining = end_time - current_time
            logger.info(
                f"Load test progress: {elapsed:.0f}s elapsed, {remaining:.0f}s remaining, "
                f"{current_requests} requests, {load_metrics['failed_requests']} errors"
            )
    
    async def _simulate_search(self, query: str, search_type: str, record_metrics: bool = True) -> Dict[str, Any]:
        """Simulate a search operation for benchmarking"""
        search_start = time.perf_counter()
        
        try:
            # Simulate database query time
            db_start = time.perf_counter()
            await asyncio.sleep(np.random.uniform(0.05, 0.2))  # 50-200ms
            db_time = (time.perf_counter() - db_start) * 1000
            
            # Simulate embedding time for vector search
            embed_time = 0
            if search_type in ['vector', 'hybrid']:
                embed_start = time.perf_counter()
                await asyncio.sleep(np.random.uniform(0.03, 0.1))  # 30-100ms
                embed_time = (time.perf_counter() - embed_start) * 1000
            
            # Simulate ranking time
            rank_start = time.perf_counter()
            await asyncio.sleep(np.random.uniform(0.01, 0.05))  # 10-50ms
            rank_time = (time.perf_counter() - rank_start) * 1000
            
            # Calculate total response time
            total_time = (time.perf_counter() - search_start) * 1000
            
            # Simulate occasional errors (2% error rate)
            if np.random.random() < 0.02:
                raise Exception("Simulated search timeout")
            
            result = {
                'query': query,
                'search_type': search_type,
                'response_time_ms': total_time,
                'database_time_ms': db_time,
                'embedding_time_ms': embed_time,
                'ranking_time_ms': rank_time,
                'results_count': np.random.randint(0, 20),
                'cache_hit': np.random.random() < 0.7,  # 70% cache hit rate
                'memory_usage_mb': psutil.Process().memory_info().rss / (1024 * 1024),
                'success': True
            }
            
            return result
            
        except Exception as e:
            return {
                'query': query,
                'search_type': search_type,
                'error': str(e),
                'success': False
            }
    
    async def _collect_system_metrics_during_test(self, scenario: BenchmarkScenario) -> SystemLoadMetrics:
        """Collect system metrics during load test"""
        try:
            # Collect multiple samples during the test
            cpu_samples = []
            memory_samples = []
            disk_samples = []
            network_samples = []
            
            # Collect samples every 10 seconds during test duration
            sample_count = max(1, scenario.duration_seconds // 10)
            
            for _ in range(sample_count):
                # CPU usage
                cpu_percent = psutil.cpu_percent(interval=1.0)
                cpu_samples.append(cpu_percent)
                
                # Memory usage
                memory = psutil.virtual_memory()
                memory_samples.append(memory.percent)
                
                # Disk usage
                disk = psutil.disk_usage('/')
                disk_samples.append(disk.percent)
                
                # Network I/O (simplified)
                network = psutil.net_io_counters()
                network_samples.append(network.bytes_sent + network.bytes_recv)
                
                await asyncio.sleep(10)
            
            return SystemLoadMetrics(
                avg_cpu_usage_percent=statistics.mean(cpu_samples),
                peak_cpu_usage_percent=max(cpu_samples),
                avg_memory_usage_percent=statistics.mean(memory_samples),
                peak_memory_usage_percent=max(memory_samples),
                avg_disk_usage_percent=statistics.mean(disk_samples),
                network_io_bytes_total=max(network_samples) - min(network_samples),
                system_load_average=psutil.getloadavg()[0] if hasattr(psutil, 'getloadavg') else 0
            )
            
        except Exception as e:
            logger.error(f"Error collecting system metrics: {e}")
            return SystemLoadMetrics()  # Return empty metrics
    
    async def _analyze_performance_characteristics(
        self,
        load_results: LoadTestResult,
        system_metrics: SystemLoadMetrics
    ) -> Dict[str, Any]:
        """Analyze performance characteristics from benchmark results"""
        analysis = {
            'performance_grade': self._calculate_performance_grade(load_results),
            'bottleneck_analysis': self._identify_bottlenecks(load_results, system_metrics),
            'scalability_assessment': self._assess_scalability(load_results, system_metrics),
            'optimization_opportunities': self._identify_optimization_opportunities(load_results),
            'resource_utilization': self._analyze_resource_utilization(system_metrics),
            'performance_trends': self._analyze_performance_trends(load_results)
        }
        
        return analysis
    
    def _calculate_performance_grade(self, load_results: LoadTestResult) -> str:
        """Calculate overall performance grade (A-F)"""
        score = 100
        
        # Response time scoring (40% weight)
        if load_results.avg_response_time_ms > 1000:
            score -= 30
        elif load_results.avg_response_time_ms > 500:
            score -= 15
        elif load_results.avg_response_time_ms > 200:
            score -= 5
        
        # Error rate scoring (30% weight)
        if load_results.error_rate > 0.05:
            score -= 25
        elif load_results.error_rate > 0.02:
            score -= 15
        elif load_results.error_rate > 0.01:
            score -= 5
        
        # Throughput scoring (30% weight)
        if load_results.throughput_rps < 10:
            score -= 20
        elif load_results.throughput_rps < 50:
            score -= 10
        elif load_results.throughput_rps < 100:
            score -= 5
        
        # Convert to letter grade
        if score >= 90:
            return 'A'
        elif score >= 80:
            return 'B'
        elif score >= 70:
            return 'C'
        elif score >= 60:
            return 'D'
        else:
            return 'F'
    
    def _identify_bottlenecks(self, load_results: LoadTestResult, system_metrics: SystemLoadMetrics) -> List[str]:
        """Identify performance bottlenecks"""
        bottlenecks = []
        
        # Response time bottlenecks
        if load_results.p95_response_time_ms > 2 * load_results.avg_response_time_ms:
            bottlenecks.append("High response time variance - some requests are much slower")
        
        # Error rate bottlenecks
        if load_results.error_rate > 0.02:
            bottlenecks.append("High error rate indicating system instability")
        
        # System resource bottlenecks
        if system_metrics.peak_cpu_usage_percent > 80:
            bottlenecks.append("CPU utilization bottleneck")
        
        if system_metrics.peak_memory_usage_percent > 85:
            bottlenecks.append("Memory utilization bottleneck")
        
        # Throughput bottlenecks
        if load_results.peak_throughput_rps < load_results.throughput_rps * 1.5:
            bottlenecks.append("Limited throughput scaling capability")
        
        return bottlenecks
    
    def _assess_scalability(self, load_results: LoadTestResult, system_metrics: SystemLoadMetrics) -> Dict[str, Any]:
        """Assess system scalability characteristics"""
        return {
            'linear_scaling': load_results.throughput_rps / load_results.concurrent_users > 0.8,
            'resource_efficiency': system_metrics.avg_cpu_usage_percent < 60,
            'error_stability': load_results.error_rate < 0.01,
            'response_consistency': load_results.p95_response_time_ms / load_results.avg_response_time_ms < 2.0,
            'recommended_max_users': self._estimate_max_users(load_results, system_metrics)
        }
    
    def _estimate_max_users(self, load_results: LoadTestResult, system_metrics: SystemLoadMetrics) -> int:
        """Estimate maximum supported concurrent users"""
        # Simple estimation based on resource utilization
        cpu_headroom = (100 - system_metrics.peak_cpu_usage_percent) / 100
        memory_headroom = (100 - system_metrics.peak_memory_usage_percent) / 100
        
        # Conservative estimate using minimum headroom
        headroom_factor = min(cpu_headroom, memory_headroom)
        
        if headroom_factor > 0:
            estimated_max = int(load_results.concurrent_users * (1 + headroom_factor))
        else:
            estimated_max = load_results.concurrent_users
        
        return min(estimated_max, load_results.concurrent_users * 3)  # Cap at 3x current
    
    def _identify_optimization_opportunities(self, load_results: LoadTestResult) -> List[Dict[str, Any]]:
        """Identify specific optimization opportunities"""
        opportunities = []
        
        # Response time optimization
        if load_results.avg_response_time_ms > 300:
            opportunities.append({
                'type': 'response_time_optimization',
                'priority': 'high',
                'description': 'Optimize response times through caching and query optimization',
                'potential_improvement': '30-50% faster responses'
            })
        
        # Error rate optimization
        if load_results.error_rate > 0.01:
            opportunities.append({
                'type': 'error_rate_optimization',
                'priority': 'critical',
                'description': 'Reduce error rate through stability improvements',
                'potential_improvement': f'Reduce errors from {load_results.error_rate:.1%} to <1%'
            })
        
        # Throughput optimization
        if load_results.throughput_rps < 100:
            opportunities.append({
                'type': 'throughput_optimization',
                'priority': 'medium',
                'description': 'Increase throughput through parallel processing',
                'potential_improvement': '2-3x throughput increase'
            })
        
        return opportunities
    
    def _analyze_resource_utilization(self, system_metrics: SystemLoadMetrics) -> Dict[str, Any]:
        """Analyze system resource utilization patterns"""
        return {
            'cpu_utilization_efficiency': 'optimal' if system_metrics.avg_cpu_usage_percent < 60 else 'high',
            'memory_utilization_efficiency': 'optimal' if system_metrics.avg_memory_usage_percent < 70 else 'high',
            'resource_balance': abs(system_metrics.avg_cpu_usage_percent - system_metrics.avg_memory_usage_percent) < 20,
            'headroom_available': {
                'cpu': max(0, 80 - system_metrics.peak_cpu_usage_percent),
                'memory': max(0, 85 - system_metrics.peak_memory_usage_percent)
            }
        }
    
    def _analyze_performance_trends(self, load_results: LoadTestResult) -> Dict[str, Any]:
        """Analyze performance trends and patterns"""
        return {
            'response_time_stability': 'stable' if load_results.p95_response_time_ms / load_results.avg_response_time_ms < 2 else 'variable',
            'throughput_consistency': 'consistent' if load_results.peak_throughput_rps / load_results.throughput_rps < 1.5 else 'variable',
            'error_distribution': 'low' if load_results.error_rate < 0.01 else 'medium' if load_results.error_rate < 0.05 else 'high'
        }
    
    async def _generate_benchmark_optimizations(
        self,
        performance_analysis: Dict[str, Any],
        scenario: BenchmarkScenario
    ) -> List[Dict[str, Any]]:
        """Generate specific optimization recommendations based on benchmark results"""
        optimizations = []
        
        # Add optimizations based on bottlenecks
        for bottleneck in performance_analysis['bottleneck_analysis']:
            if 'CPU' in bottleneck:
                optimizations.append({
                    'type': 'cpu_optimization',
                    'priority': 'high',
                    'description': 'Optimize CPU-intensive operations and implement parallel processing',
                    'implementation': 'Add async processing and optimize algorithms'
                })
            
            if 'Memory' in bottleneck:
                optimizations.append({
                    'type': 'memory_optimization',
                    'priority': 'high',
                    'description': 'Optimize memory usage and implement memory pooling',
                    'implementation': 'Add memory caching and cleanup procedures'
                })
        
        # Add optimizations based on performance opportunities
        for opportunity in performance_analysis['optimization_opportunities']:
            optimizations.append({
                'type': opportunity['type'],
                'priority': opportunity['priority'],
                'description': opportunity['description'],
                'expected_improvement': opportunity['potential_improvement']
            })
        
        return optimizations
    
    async def _compare_with_baseline(
        self,
        current_analysis: Dict[str, Any],
        scenario_name: str
    ) -> Dict[str, Any]:
        """Compare current performance with baseline"""
        baseline = self._optimization_baselines.get(scenario_name)
        if not baseline:
            return {'status': 'no_baseline_available'}
        
        comparison = {
            'performance_change': self._compare_performance_grades(
                current_analysis['performance_grade'],
                baseline['performance_grade']
            ),
            'bottleneck_changes': self._compare_bottlenecks(
                current_analysis['bottleneck_analysis'],
                baseline['bottleneck_analysis']
            ),
            'improvement_areas': self._identify_improvements(current_analysis, baseline)
        }
        
        return comparison
    
    def _compare_performance_grades(self, current_grade: str, baseline_grade: str) -> str:
        """Compare performance grades"""
        grade_values = {'A': 5, 'B': 4, 'C': 3, 'D': 2, 'F': 1}
        current_value = grade_values.get(current_grade, 0)
        baseline_value = grade_values.get(baseline_grade, 0)
        
        if current_value > baseline_value:
            return 'improved'
        elif current_value < baseline_value:
            return 'degraded'
        else:
            return 'unchanged'
    
    def _compare_bottlenecks(self, current_bottlenecks: List[str], baseline_bottlenecks: List[str]) -> Dict[str, Any]:
        """Compare bottleneck analysis"""
        return {
            'new_bottlenecks': [b for b in current_bottlenecks if b not in baseline_bottlenecks],
            'resolved_bottlenecks': [b for b in baseline_bottlenecks if b not in current_bottlenecks],
            'persistent_bottlenecks': [b for b in current_bottlenecks if b in baseline_bottlenecks]
        }
    
    def _identify_improvements(self, current: Dict[str, Any], baseline: Dict[str, Any]) -> List[str]:
        """Identify specific improvement areas"""
        improvements = []
        
        # Compare scalability
        if current['scalability_assessment']['linear_scaling'] and not baseline['scalability_assessment']['linear_scaling']:
            improvements.append("Improved linear scaling capability")
        
        if current['scalability_assessment']['resource_efficiency'] and not baseline['scalability_assessment']['resource_efficiency']:
            improvements.append("Better resource efficiency")
        
        return improvements
    
    def _should_update_baseline(self, result: BenchmarkResult, scenario_name: str) -> bool:
        """Determine if baseline should be updated with new results"""
        if scenario_name not in self._optimization_baselines:
            return True
        
        baseline = self._optimization_baselines[scenario_name]
        current_grade = result.performance_analysis['performance_grade']
        baseline_grade = baseline['performance_grade']
        
        # Update if performance improved
        grade_values = {'A': 5, 'B': 4, 'C': 3, 'D': 2, 'F': 1}
        return grade_values.get(current_grade, 0) > grade_values.get(baseline_grade, 0)
    
    async def _store_benchmark_results(self, result: BenchmarkResult) -> None:
        """Store benchmark results for historical analysis"""
        try:
            result_data = {
                'benchmark_id': result.benchmark_id,
                'scenario_name': result.scenario_name,
                'start_time': result.start_time.isoformat(),
                'end_time': result.end_time.isoformat(),
                'performance_grade': result.performance_analysis.get('performance_grade', 'F'),
                'avg_response_time_ms': result.load_test_results.avg_response_time_ms,
                'error_rate': result.load_test_results.error_rate,
                'throughput_rps': result.load_test_results.throughput_rps,
                'success': result.success
            }
            
            # Store in Redis for fast access
            await self.redis.lpush("feedme:benchmark_results", json.dumps(result_data))
            await self.redis.ltrim("feedme:benchmark_results", 0, 999)  # Keep last 1000
            
            # Store detailed results in database
            insert_query = text("""
                INSERT INTO feedme_benchmark_results 
                (benchmark_id, scenario_name, start_time, end_time, results_data, success)
                VALUES (:benchmark_id, :scenario_name, :start_time, :end_time, :results_data, :success)
            """)
            
            await self.db.execute(insert_query, {
                'benchmark_id': result.benchmark_id,
                'scenario_name': result.scenario_name,
                'start_time': result.start_time,
                'end_time': result.end_time,
                'results_data': json.dumps(result_data),
                'success': result.success
            })
            
            await self.db.commit()
            
        except Exception as e:
            logger.error(f"Error storing benchmark results: {e}")
    
    async def run_optimization_validation_suite(
        self,
        optimization_name: str,
        before_after_comparison: bool = True
    ) -> Dict[str, Any]:
        """
        Run a comprehensive validation suite to verify optimization effectiveness
        """
        try:
            validation_results = {
                'optimization_name': optimization_name,
                'validation_start': datetime.utcnow(),
                'test_scenarios': []
            }
            
            # Define validation scenarios
            validation_scenarios = [
                BenchmarkScenario(
                    name=f"{optimization_name}_light_load",
                    description="Light load validation test",
                    concurrent_users=10,
                    duration_seconds=60,
                    query_patterns=["email sync", "account setup", "troubleshooting"],
                    target_response_time_ms=300
                ),
                BenchmarkScenario(
                    name=f"{optimization_name}_moderate_load",
                    description="Moderate load validation test",
                    concurrent_users=25,
                    duration_seconds=120,
                    query_patterns=["email sync", "account setup", "troubleshooting", "feature questions"],
                    target_response_time_ms=500
                ),
                BenchmarkScenario(
                    name=f"{optimization_name}_stress_test",
                    description="Stress test validation",
                    concurrent_users=50,
                    duration_seconds=180,
                    query_patterns=["complex query", "multiple filters", "large result set"],
                    target_response_time_ms=1000
                )
            ]
            
            # Execute validation scenarios
            for scenario in validation_scenarios:
                scenario_result = await self.execute_performance_benchmark(scenario, before_after_comparison)
                validation_results['test_scenarios'].append({
                    'scenario_name': scenario.name,
                    'performance_grade': scenario_result.performance_analysis.get('performance_grade', 'F'),
                    'meets_targets': self._validate_performance_targets(scenario_result, scenario),
                    'optimization_impact': self._calculate_optimization_impact(scenario_result)
                })
            
            # Calculate overall validation result
            validation_results['overall_success'] = all(
                scenario['meets_targets'] for scenario in validation_results['test_scenarios']
            )
            
            validation_results['validation_end'] = datetime.utcnow()
            
            return validation_results
            
        except Exception as e:
            logger.error(f"Optimization validation failed: {e}")
            return {'optimization_name': optimization_name, 'success': False, 'error': str(e)}
    
    def _validate_performance_targets(self, result: BenchmarkResult, scenario: BenchmarkScenario) -> bool:
        """Validate that performance meets target criteria"""
        meets_response_time = result.load_test_results.avg_response_time_ms <= scenario.target_response_time_ms
        meets_error_rate = result.load_test_results.error_rate <= scenario.target_error_rate
        
        return meets_response_time and meets_error_rate
    
    def _calculate_optimization_impact(self, result: BenchmarkResult) -> Dict[str, Any]:
        """Calculate the impact of optimization"""
        if result.baseline_comparison:
            return {
                'performance_change': result.baseline_comparison.get('performance_change', 'unknown'),
                'bottleneck_improvements': len(result.baseline_comparison.get('bottleneck_changes', {}).get('resolved_bottlenecks', [])),
                'optimization_effective': result.baseline_comparison.get('performance_change') == 'improved'
            }
        
        return {'optimization_effective': result.performance_analysis.get('performance_grade', 'F') in ['A', 'B']}
    
    async def generate_performance_report(self, time_period_days: int = 30) -> Dict[str, Any]:
        """Generate comprehensive performance report"""
        try:
            end_date = datetime.utcnow()
            start_date = end_date - timedelta(days=time_period_days)
            
            # Get benchmark results from the time period
            recent_results = [
                result for result in self._benchmark_results
                if result.start_time >= start_date
            ]
            
            if not recent_results:
                return {'status': 'no_data', 'message': 'No benchmark data available for the specified period'}
            
            # Analyze trends
            performance_trends = self._analyze_benchmark_trends(recent_results)
            
            # Identify top performing scenarios
            top_performers = self._identify_top_performing_scenarios(recent_results)
            
            # Identify areas needing attention
            attention_areas = self._identify_attention_areas(recent_results)
            
            # Calculate optimization effectiveness
            optimization_effectiveness = self._calculate_optimization_effectiveness(recent_results)
            
            report = {
                'report_period': {
                    'start_date': start_date.isoformat(),
                    'end_date': end_date.isoformat(),
                    'total_benchmarks': len(recent_results)
                },
                'performance_trends': performance_trends,
                'top_performers': top_performers,
                'attention_areas': attention_areas,
                'optimization_effectiveness': optimization_effectiveness,
                'recommendations': self._generate_report_recommendations(recent_results)
            }
            
            return report
            
        except Exception as e:
            logger.error(f"Error generating performance report: {e}")
            return {'status': 'error', 'error': str(e)}
    
    def _analyze_benchmark_trends(self, results: List[BenchmarkResult]) -> Dict[str, Any]:
        """Analyze performance trends over time"""
        if len(results) < 2:
            return {'status': 'insufficient_data'}
        
        # Sort by time
        sorted_results = sorted(results, key=lambda x: x.start_time)
        
        # Track metrics over time
        grades = [r.performance_analysis.get('performance_grade', 'F') for r in sorted_results]
        response_times = [r.load_test_results.avg_response_time_ms for r in sorted_results]
        error_rates = [r.load_test_results.error_rate for r in sorted_results]
        
        # Calculate trends with error handling for insufficient data
        grade_values = {'A': 5, 'B': 4, 'C': 3, 'D': 2, 'F': 1}
        
        try:
            if len(grades) >= 2:
                grade_trend = np.polyfit(range(len(grades)), [grade_values.get(g, 1) for g in grades], 1)[0]
            else:
                grade_trend = 0
        except (np.linalg.LinAlgError, ValueError) as e:
            logger.warning(f"Error calculating grade trend: {e}")
            grade_trend = 0
            
        try:
            if len(response_times) >= 2:
                response_time_trend = np.polyfit(range(len(response_times)), response_times, 1)[0]
            else:
                response_time_trend = 0
        except (np.linalg.LinAlgError, ValueError) as e:
            logger.warning(f"Error calculating response time trend: {e}")
            response_time_trend = 0
            
        try:
            if len(error_rates) >= 2:
                error_rate_trend = np.polyfit(range(len(error_rates)), error_rates, 1)[0]
            else:
                error_rate_trend = 0
        except (np.linalg.LinAlgError, ValueError) as e:
            logger.warning(f"Error calculating error rate trend: {e}")
            error_rate_trend = 0
        
        return {
            'performance_grade_trend': 'improving' if grade_trend > 0.1 else 'declining' if grade_trend < -0.1 else 'stable',
            'response_time_trend': 'improving' if response_time_trend < -10 else 'declining' if response_time_trend > 10 else 'stable',
            'error_rate_trend': 'improving' if error_rate_trend < -0.01 else 'declining' if error_rate_trend > 0.01 else 'stable',
            'latest_grade': grades[-1],
            'avg_response_time': statistics.mean(response_times),
            'avg_error_rate': statistics.mean(error_rates)
        }
    
    def _identify_top_performing_scenarios(self, results: List[BenchmarkResult]) -> List[Dict[str, Any]]:
        """Identify top performing benchmark scenarios"""
        scenario_performance = defaultdict(list)
        
        for result in results:
            grade_value = {'A': 5, 'B': 4, 'C': 3, 'D': 2, 'F': 1}[result.performance_analysis.get('performance_grade', 'F')]
            scenario_performance[result.scenario_name].append(grade_value)
        
        # Calculate average performance per scenario
        scenario_averages = {
            scenario: statistics.mean(grades)
            for scenario, grades in scenario_performance.items()
        }
        
        # Return top 5 scenarios
        top_scenarios = sorted(scenario_averages.items(), key=lambda x: x[1], reverse=True)[:5]
        
        return [
            {
                'scenario_name': scenario,
                'avg_performance_score': score,
                'performance_grade': {5: 'A', 4: 'B', 3: 'C', 2: 'D', 1: 'F'}[round(score)]
            }
            for scenario, score in top_scenarios
        ]
    
    def _identify_attention_areas(self, results: List[BenchmarkResult]) -> List[Dict[str, Any]]:
        """Identify areas that need attention"""
        attention_areas = []
        
        # Check for consistently poor performance
        poor_performers = [r for r in results if r.performance_analysis.get('performance_grade', 'F') in ['D', 'F']]
        if len(poor_performers) > len(results) * 0.3:
            attention_areas.append({
                'area': 'overall_performance',
                'severity': 'high',
                'description': f'{len(poor_performers)} of {len(results)} benchmarks showed poor performance'
            })
        
        # Check for high error rates
        high_error_results = [r for r in results if r.load_test_results.error_rate > 0.05]
        if high_error_results:
            attention_areas.append({
                'area': 'error_rates',
                'severity': 'critical',
                'description': f'{len(high_error_results)} benchmarks had error rates above 5%'
            })
        
        # Check for slow response times
        slow_results = [r for r in results if r.load_test_results.avg_response_time_ms > 1000]
        if slow_results:
            attention_areas.append({
                'area': 'response_times',
                'severity': 'medium',
                'description': f'{len(slow_results)} benchmarks had response times above 1 second'
            })
        
        return attention_areas
    
    def _calculate_optimization_effectiveness(self, results: List[BenchmarkResult]) -> Dict[str, Any]:
        """Calculate effectiveness of optimizations"""
        results_with_baseline = [r for r in results if r.baseline_comparison]
        
        if not results_with_baseline:
            return {'status': 'no_baseline_comparisons'}
        
        improvements = [r for r in results_with_baseline if r.baseline_comparison.get('performance_change') == 'improved']
        degradations = [r for r in results_with_baseline if r.baseline_comparison.get('performance_change') == 'degraded']
        
        return {
            'total_comparisons': len(results_with_baseline),
            'improvements': len(improvements),
            'degradations': len(degradations),
            'stable': len(results_with_baseline) - len(improvements) - len(degradations),
            'improvement_rate': len(improvements) / len(results_with_baseline),
            'optimization_effectiveness': 'high' if len(improvements) / len(results_with_baseline) > 0.7 else 'medium' if len(improvements) / len(results_with_baseline) > 0.4 else 'low'
        }
    
    def _generate_report_recommendations(self, results: List[BenchmarkResult]) -> List[str]:
        """Generate recommendations based on benchmark analysis"""
        recommendations = []
        
        # Analyze common issues
        common_bottlenecks = defaultdict(int)
        for result in results:
            for bottleneck in result.performance_analysis.get('bottleneck_analysis', []):
                common_bottlenecks[bottleneck] += 1
        
        # Generate recommendations based on common bottlenecks
        for bottleneck, frequency in common_bottlenecks.items():
            if frequency > len(results) * 0.5:  # Appears in >50% of results
                if 'CPU' in bottleneck:
                    recommendations.append("Consider CPU optimization - implement parallel processing and algorithm improvements")
                elif 'Memory' in bottleneck:
                    recommendations.append("Address memory bottlenecks - implement caching and memory management improvements")
                elif 'response time' in bottleneck:
                    recommendations.append("Focus on response time optimization - optimize database queries and caching strategies")
        
        # Add general recommendations if no specific patterns found
        if not recommendations:
            avg_grade = statistics.mode([r.performance_analysis.get('performance_grade', 'F') for r in results])
            if avg_grade in ['D', 'F']:
                recommendations.append("Overall performance needs improvement - conduct detailed profiling and optimization")
            elif avg_grade == 'C':
                recommendations.append("Performance is adequate but has room for improvement - focus on specific bottlenecks")
        
        return recommendations[:5]  # Return top 5 recommendations