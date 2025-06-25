"""
High-Performance Log Analysis Engine with Intelligent Optimization v4.0
Enhanced with adaptive performance profiles, incremental analysis, and smart caching.
Optimized for speed while maintaining analysis quality through parallel processing and smart chunking.
"""

import os
import json
import time
import asyncio
import hashlib
import pickle
import logging
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor
from langchain_google_genai import ChatGoogleGenerativeAI
from app.core.logging_config import get_logger
from app.core.settings import settings
from collections import defaultdict

logger = logging.getLogger(__name__)

class OptimizedLogAnalyzer:
    """
    High-performance log analyzer using parallel processing, smart chunking,
    adaptive performance profiles, and incremental analysis for sub-60-second analysis times.
    """
    
    def __init__(self):
        # Use both Pro and Flash models strategically
        self.reasoning_llm = ChatGoogleGenerativeAI(
            model="gemini-2.5-pro",
            temperature=0.1,
            google_api_key=settings.gemini_api_key,
        )
        
        self.fast_llm = ChatGoogleGenerativeAI(
            model="gemini-2.5-flash",
            temperature=0.1,
            google_api_key=settings.gemini_api_key,
        )
        
        # Adaptive performance profiles
        self.performance_profiles = {
            'ultra_fast': {  # <30 seconds for any log size
                'MAX_CHUNK_SIZE': 10000,
                'MAX_CONTEXT_CHARS': 10000,
                'PARALLEL_CHUNKS': 5,
                'sampling_rate': 0.1,  # Sample 10% of log
                'use_cache_aggressively': True,
                'skip_deep_analysis': False,
                'model_preference': 'flash'
            },
            'balanced': {  # <60 seconds, better accuracy
                'MAX_CHUNK_SIZE': 5000,
                'MAX_CONTEXT_CHARS': 15000,
                'PARALLEL_CHUNKS': 3,
                'sampling_rate': 0.3,
                'use_cache_aggressively': True,
                'skip_deep_analysis': False,
                'model_preference': 'mixed'
            },
            'thorough': {  # <120 seconds, maximum accuracy
                'MAX_CHUNK_SIZE': 2000,
                'MAX_CONTEXT_CHARS': 20000,
                'PARALLEL_CHUNKS': 2,
                'sampling_rate': 0.7,
                'use_cache_aggressively': False,
                'skip_deep_analysis': False,
                'model_preference': 'pro'
            }
        }
        
        # Current profile (can be dynamically adjusted)
        self.current_profile = 'balanced'
        self._update_config()
        
        # Enhanced caching system
        self.analysis_cache = {}
        self.pattern_cache = {}
        self.cache_ttl = 3600  # 1 hour
        
        # Incremental analysis state
        self.incremental_state = {}
        self.processed_content_hashes = {}
        
        # Performance monitoring
        self.performance_metrics = {
            'analysis_times': [],
            'log_sizes': [],
            'cache_hits': 0,
            'cache_misses': 0
        }
        
        # Optimized system instructions
        self.system_instructions = """
You are an expert Mailbird log analyst. Analyze QUICKLY but THOROUGHLY:
- Focus on CRITICAL issues first
- Provide SPECIFIC root causes
- Generate ACTIONABLE solutions
- Be CONCISE but COMPLETE
Response format: JSON only, no extra text.
"""

    async def perform_optimized_analysis(self, raw_log_content: str, basic_parsed_data: Dict[str, Any], 
                                       progress_callback: Optional[callable] = None) -> Dict[str, Any]:
        """
        Perform high-speed optimized analysis with progress tracking.
        """
        logger = get_logger("optimized_analyzer")
        start_time = time.time()
        
        if progress_callback:
            await progress_callback("🚀 Starting optimized analysis...")
        
        # Phase 1: Quick Basic Analysis (5-10 seconds)
        logger.info("Starting fast basic analysis...")
        if progress_callback:
            await progress_callback("📊 Performing quick pattern detection...")
        
        basic_analysis = await self._fast_basic_analysis(raw_log_content, basic_parsed_data)
        
        # Phase 2: Parallel Deep Analysis (15-30 seconds) - skip if configured
        if self.skip_deep_analysis:
            logger.info("Skipping deep analysis as per performance profile configuration")
            if progress_callback:
                await progress_callback("⏭️ Skipping deep analysis (performance mode)")
            deep_analysis = {
                "critical_patterns": [],
                "root_causes": [],
                "temporal_insights": {},
                "chunks_analyzed": 0,
                "chunks_failed": 0,
                "analysis_skipped": True,
                "reason": "Skipped as per performance profile configuration"
            }
        else:
            if progress_callback:
                await progress_callback("🔍 Running parallel deep analysis...")
            
            deep_analysis = await self._parallel_deep_analysis(raw_log_content, basic_analysis)
        
        # Phase 3: Smart Solution Generation (10-20 seconds)
        if progress_callback:
            await progress_callback("💡 Generating intelligent solutions...")
        
        solutions = await self._smart_solution_generation(basic_analysis, deep_analysis)
        
        # Phase 4: Executive Summary (5-10 seconds)
        if progress_callback:
            await progress_callback("📋 Creating executive summary...")
        
        executive_summary = await self._fast_executive_summary(basic_analysis, deep_analysis, solutions)
        
        analysis_duration = time.time() - start_time
        logger.info(f"Optimized analysis completed in {analysis_duration:.2f}s")
        
        # Update performance metrics
        self.performance_metrics['analysis_times'].append(analysis_duration)
        self.performance_metrics['log_sizes'].append(len(raw_log_content))
        
        # Keep only the last 1000 entries to prevent memory issues
        if len(self.performance_metrics['analysis_times']) > 1000:
            self.performance_metrics['analysis_times'] = self.performance_metrics['analysis_times'][-1000:]
            self.performance_metrics['log_sizes'] = self.performance_metrics['log_sizes'][-1000:]
        
        if progress_callback:
            await progress_callback(f"✅ Analysis complete in {analysis_duration:.1f}s")
        
        # Include performance metrics in the response
        performance_metrics = {
            'analysis_duration_seconds': analysis_duration,
            'analyzer_version': '4.0-optimized',
            'optimization_features': ['parallel_processing', 'smart_chunking', 'progressive_analysis'],
            'analysis_timestamp': datetime.utcnow().isoformat(),
            'total_analyses': len(self.performance_metrics['analysis_times']),
            'average_analysis_time': sum(self.performance_metrics['analysis_times']) / max(1, len(self.performance_metrics['analysis_times']))
        }
        
        return {
            'basic_analysis': basic_analysis,
            'deep_analysis': deep_analysis,
            'optimized_solutions': solutions,
            'executive_summary': executive_summary,
            'performance_metrics': performance_metrics
        }

    async def _fast_basic_analysis(self, raw_log_content: str, basic_parsed_data: Dict) -> Dict[str, Any]:
        """Perform fast basic analysis using pattern recognition."""
        
        # Use pre-computed basic data and enhance with quick AI insights
        log_lines = raw_log_content.split('\n')
        
        # Smart sampling for large logs
        if len(log_lines) > 1000:
            # Sample: first 200 + last 200 + random 100 from middle
            sampled_lines = (
                log_lines[:200] + 
                log_lines[-200:] + 
                [log_lines[i] for i in range(200, len(log_lines)-200, max(1, (len(log_lines)-400)//100))][:100]
            )
            sample_content = '\n'.join(sampled_lines)
        else:
            sample_content = raw_log_content
        
        # Use fast Flash model for basic analysis
        prompt = f"""
{self.system_instructions}

TASK: RAPID LOG ANALYSIS
Analyze this Mailbird log sample for immediate issues:

LOG SAMPLE ({len(sample_content)} chars):
```
{sample_content[:self.MAX_CONTEXT_CHARS]}
```

BASIC DATA:
{json.dumps(basic_parsed_data, indent=1)[:2000]}

REQUIRED OUTPUT (JSON only):
{{
  "immediate_issues": [
    {{
      "type": "connection_failure|auth_error|database_issue|performance",
      "severity": "critical|high|medium|low",
      "count": 5,
      "sample_message": "specific error message",
      "accounts_affected": ["email@domain.com"]
    }}
  ],
  "system_health": {{
    "status": "critical|degraded|stable|healthy",
    "confidence": 0.85,
    "key_concerns": ["concern1", "concern2"]
  }},
  "quick_recommendations": ["action1", "action2", "action3"]
}}
"""
        
        try:
            response = await self.fast_llm.ainvoke(prompt)
            result = self._extract_json_from_response(response.content)
            result['analysis_method'] = 'fast_sampling'
            result['sample_size'] = len(sample_content.split('\n'))
            return result
        except Exception as e:
            return {
                "error": f"Fast analysis failed: {str(e)}",
                "immediate_issues": [],
                "system_health": {"status": "unknown", "confidence": 0.0},
                "quick_recommendations": ["Manual review required"]
            }

    async def _parallel_deep_analysis(self, raw_log_content: str, basic_analysis: Dict) -> Dict[str, Any]:
        """Perform deep analysis using parallel processing of log chunks."""
        
        log_lines = raw_log_content.split('\n')
        
        # Smart chunking based on log size
        if len(log_lines) <= 1000:
            # Small logs: single chunk with Pro model
            chunks = [log_lines]
        else:
            # Large logs: intelligent chunking
            chunk_size = min(self.MAX_CHUNK_SIZE, len(log_lines) // self.PARALLEL_CHUNKS)
            chunks = [log_lines[i:i + chunk_size] for i in range(0, len(log_lines), chunk_size)]
        
        # Process chunks in parallel
        tasks = []
        for i, chunk in enumerate(chunks[:self.PARALLEL_CHUNKS]):  # Limit parallel tasks
            chunk_content = '\n'.join(chunk)
            task = self._analyze_chunk(chunk_content, i, basic_analysis)
            tasks.append(task)
        
        # Wait for all chunks to complete
        chunk_results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Merge results
        merged_analysis = self._merge_chunk_results(chunk_results)
        return merged_analysis

    async def _analyze_chunk(self, chunk_content: str, chunk_id: int, basic_analysis: Dict) -> Dict[str, Any]:
        """Analyze a single chunk of log data."""
        
        # Focus analysis based on basic findings
        focus_areas = basic_analysis.get('system_health', {}).get('key_concerns', [])
        
        prompt = f"""
{self.system_instructions}

TASK: CHUNK DEEP ANALYSIS (Chunk {chunk_id})
Focus on: {', '.join(focus_areas) if focus_areas else 'all issues'}

LOG CHUNK:
```
{chunk_content[:self.MAX_CONTEXT_CHARS]}
```

OUTPUT (JSON only):
{{
  "chunk_id": {chunk_id},
  "critical_patterns": [
    {{
      "pattern": "specific pattern found",
      "occurrences": 3,
      "severity": "critical|high|medium",
      "context": "when this happens"
    }}
  ],
  "root_causes": [
    {{
      "cause": "technical root cause",
      "evidence": "supporting evidence",
      "impact": "user impact description"
    }}
  ],
  "temporal_insights": {{
    "time_range": "timeframe of chunk",
    "peak_issues": "when most issues occur",
    "correlation": "relationship to other events"
  }}
}}
"""
        
        try:
            # Use Pro model for deep analysis
            response = await self.reasoning_llm.ainvoke(prompt)
            return self._extract_json_from_response(response.content)
        except Exception as e:
            return {
                "chunk_id": chunk_id,
                "error": str(e),
                "critical_patterns": [],
                "root_causes": [],
                "temporal_insights": {}
            }

    def _merge_chunk_results(self, chunk_results: List) -> Dict[str, Any]:
        """Merge analysis results from multiple chunks."""
        
        merged = {
            "critical_patterns": [],
            "root_causes": [],
            "temporal_insights": {},
            "chunks_analyzed": 0,
            "chunks_failed": 0
        }
        
        for result in chunk_results:
            if isinstance(result, Exception):
                merged["chunks_failed"] += 1
                continue
                
            if isinstance(result, dict) and "error" not in result:
                merged["chunks_analyzed"] += 1
                merged["critical_patterns"].extend(result.get("critical_patterns", []))
                merged["root_causes"].extend(result.get("root_causes", []))
                
                # Merge temporal insights
                chunk_temporal = result.get("temporal_insights", {})
                if chunk_temporal:
                    merged["temporal_insights"][f"chunk_{result.get('chunk_id', 0)}"] = chunk_temporal
            else:
                merged["chunks_failed"] += 1
        
        # Deduplicate and prioritize patterns
        merged["critical_patterns"] = self._deduplicate_patterns(merged["critical_patterns"])
        merged["root_causes"] = self._deduplicate_causes(merged["root_causes"])
        
        return merged

    def _deduplicate_patterns(self, patterns: List[Dict]) -> List[Dict]:
        """Remove duplicate patterns and sort by severity."""
        unique_patterns = {}
        
        for pattern in patterns:
            key = pattern.get("pattern", "unknown")
            if key not in unique_patterns or pattern.get("occurrences", 0) > unique_patterns[key].get("occurrences", 0):
                unique_patterns[key] = pattern
        
        # Sort by severity and occurrences
        severity_order = {"critical": 3, "high": 2, "medium": 1, "low": 0}
        return sorted(
            unique_patterns.values(),
            key=lambda x: (severity_order.get(x.get("severity", "low"), 0), x.get("occurrences", 0)),
            reverse=True
        )

    def _deduplicate_causes(self, causes: List[Dict]) -> List[Dict]:
        """Remove duplicate root causes."""
        unique_causes = {}
        
        for cause in causes:
            key = cause.get("cause", "unknown")
            if key not in unique_causes:
                unique_causes[key] = cause
        
        return list(unique_causes.values())

    async def _smart_solution_generation(self, basic_analysis: Dict, deep_analysis: Dict) -> List[Dict[str, Any]]:
        """Generate solutions using smart prioritization."""
        
        # Extract top issues
        immediate_issues = basic_analysis.get("immediate_issues", [])
        critical_patterns = deep_analysis.get("critical_patterns", [])
        
        # Focus on top 3-5 most critical issues
        top_issues = []
        for issue in immediate_issues[:3]:
            if issue.get("severity") in ["critical", "high"]:
                top_issues.append(issue)
        
        for pattern in critical_patterns[:2]:
            if pattern.get("severity") in ["critical", "high"]:
                top_issues.append(pattern)
        
        if not top_issues:
            return [{
                "solution_id": "no_critical_issues",
                "title": "System Appears Stable",
                "priority": "Low",
                "implementation_steps": [{"step_number": 1, "action": "Monitor for future issues"}]
            }]
        
        # Generate solutions for top issues
        prompt = f"""
{self.system_instructions}

TASK: RAPID SOLUTION GENERATION
Generate solutions for top critical issues:

ISSUES:
{json.dumps(top_issues, indent=1)[:3000]}

OUTPUT (JSON only):
[
  {{
    "solution_id": "dns_fix",
    "title": "Fix DNS Resolution Issues",
    "priority": "Critical|High|Medium",
    "estimated_time": "5-15 minutes",
    "success_rate": "High|Medium|Low",
    "implementation_steps": [
      {{
        "step_number": 1,
        "action": "Specific action to take",
        "command": "actual command if needed",
        "expected_result": "what should happen"
      }}
    ],
    "target_issues": ["issue1", "issue2"],
    "risk_level": "Low|Medium|High"
  }}
]
"""
        
        try:
            response = await self.fast_llm.ainvoke(prompt)
            solutions = self._extract_json_from_response(response.content)
            if isinstance(solutions, list):
                return solutions
            return [solutions] if isinstance(solutions, dict) else []
        except Exception as e:
            return [{
                "solution_id": "error_fallback",
                "title": "Contact Support",
                "priority": "High",
                "error": str(e),
                "implementation_steps": [
                    {"step_number": 1, "action": "Contact Mailbird support with log file"}
                ]
            }]

    async def _fast_executive_summary(self, basic_analysis: Dict, deep_analysis: Dict, 
                                    solutions: List[Dict]) -> str:
        """Generate concise executive summary."""
        
        # Create summary data
        summary_data = {
            "system_status": basic_analysis.get("system_health", {}).get("status", "unknown"),
            "critical_issues": len([i for i in basic_analysis.get("immediate_issues", []) 
                                  if i.get("severity") == "critical"]),
            "solutions_provided": len(solutions),
            "top_recommendations": basic_analysis.get("quick_recommendations", [])[:3]
        }
        
        prompt = f"""
Create a concise executive summary (markdown format):

ANALYSIS RESULTS:
{json.dumps(summary_data, indent=1)}

TOP ISSUES:
{json.dumps(basic_analysis.get("immediate_issues", [])[:3], indent=1)[:1000]}

FORMAT:
## Executive Summary
[2-3 sentence overview]

## System Status: {summary_data["system_status"].title()}
[Brief status explanation]

## Critical Actions Required:
1. [Action 1]
2. [Action 2]
3. [Action 3]

## Next Steps:
- [Step 1]
- [Step 2]

*Analysis completed in [X] seconds using optimized processing*
"""
        
        try:
            response = await self.fast_llm.ainvoke(prompt)
            return response.content
        except Exception as e:
            return f"""# Executive Summary

Analysis encountered an error: {str(e)}

## Immediate Actions:
1. Save the log file for manual review
2. Contact Mailbird support
3. Monitor system performance

*Automated analysis partially completed*"""

    def _extract_json_from_response(self, response_text: str) -> Dict:
        """Extract JSON from AI response, handling various formats."""
        try:
            # Try direct JSON parsing
            return json.loads(response_text)
        except:
            try:
                # Try extracting from code blocks
                if '```json' in response_text:
                    start = response_text.find('```json') + 7
                    end = response_text.find('```', start)
                    return json.loads(response_text[start:end].strip())
                elif '```' in response_text:
                    start = response_text.find('```') + 3
                    end = response_text.find('```', start)
                    return json.loads(response_text[start:end].strip())
                else:
                    # Try to find JSON-like content
                    start = response_text.find('{')
                    end = response_text.rfind('}') + 1
                    if start != -1 and end > start:
                        return json.loads(response_text[start:end])
            except:
                pass
        
        # Fallback
        return {"error": "Failed to parse AI response", "raw_response": response_text[:500]}

    def _update_config(self):
        """Update configuration based on current performance profile."""
        profile = self.performance_profiles[self.current_profile]
        self.MAX_CHUNK_SIZE = profile['MAX_CHUNK_SIZE']
        self.MAX_CONTEXT_CHARS = profile['MAX_CONTEXT_CHARS']
        self.PARALLEL_CHUNKS = profile['PARALLEL_CHUNKS']

    def set_performance_profile(self, profile_name: str):
        """Set performance profile dynamically."""
        if profile_name in self.performance_profiles:
            self.current_profile = profile_name
            self._update_config()
            logger.info(f"Performance profile set to: {profile_name}")
        else:
            logger.warning(f"Unknown profile: {profile_name}")

    def auto_adjust_profile(self, log_size: int, time_constraint: Optional[int] = None):
        """Automatically adjust performance profile based on log size and time constraints."""
        if time_constraint and time_constraint < 45:
            self.set_performance_profile('ultra_fast')
        elif log_size > 50000:  # Large logs
            if time_constraint and time_constraint < 90:
                self.set_performance_profile('balanced')
            else:
                self.set_performance_profile('thorough')
        elif log_size > 10000:  # Medium logs
            self.set_performance_profile('balanced')
        else:  # Small logs
            self.set_performance_profile('thorough')

    async def analyze_incremental(self, new_log_lines: List[str], session_id: str) -> Dict[str, Any]:
        """
        Perform incremental analysis on new log entries.
        Maintains state between calls for real-time monitoring.
        """
        try:
            logger.info(f"Starting incremental analysis for session {session_id}")
            
            # Initialize session state if needed
            if session_id not in self.incremental_state:
                self.incremental_state[session_id] = {
                    'processed_lines': 0,
                    'known_issues': [],
                    'last_analysis': None,
                    'baseline_patterns': {}
                }
            
            session_state = self.incremental_state[session_id]
            
            # Filter only new lines
            start_index = session_state['processed_lines']
            truly_new_lines = new_log_lines[start_index:]
            
            if not truly_new_lines:
                return {
                    'new_issues': [],
                    'status': 'no_new_data',
                    'session_summary': session_state
                }
            
            # Analyze new content
            new_content = '\n'.join(truly_new_lines)
            
            # Use ultra_fast profile for incremental analysis
            original_profile = self.current_profile
            self.set_performance_profile('ultra_fast')
            
            try:
                # Quick analysis of new content
                basic_data = {'entries': []}  # Minimal basic data for speed
                analysis_result = await self.perform_optimized_analysis(new_content, basic_data)
                
                # Compare with known issues to find new ones
                new_issues = self._identify_new_issues(
                    analysis_result.get('basic_analysis', {}).get('immediate_issues', []),
                    session_state['known_issues']
                )
                
                # Update session state
                session_state['processed_lines'] += len(truly_new_lines)
                session_state['last_analysis'] = datetime.now().isoformat()
                session_state['known_issues'].extend(new_issues)
                
                # Keep only recent issues (last 100)
                session_state['known_issues'] = session_state['known_issues'][-100:]
                
                return {
                    'new_issues': new_issues,
                    'lines_processed': len(truly_new_lines),
                    'total_lines': session_state['processed_lines'],
                    'status': 'completed',
                    'session_summary': session_state,
                    'analysis_duration': analysis_result.get('performance_metrics', {}).get('analysis_duration_seconds', 0)
                }
                
            finally:
                # Restore original profile
                self.set_performance_profile(original_profile)
                
        except Exception as e:
            logger.error(f"Incremental analysis failed: {str(e)}")
            return {
                'new_issues': [],
                'status': 'error',
                'error': str(e),
                'session_summary': self.incremental_state.get(session_id, {})
            }

    def _identify_new_issues(self, current_issues: List[Dict], known_issues: List[Dict]) -> List[Dict]:
        """Identify issues that haven't been seen before."""
        new_issues = []
        known_signatures = {issue.get('type', '') + issue.get('sample_message', '')[:50] for issue in known_issues}
        
        for issue in current_issues:
            issue_signature = issue.get('type', '') + issue.get('sample_message', '')[:50]
            if issue_signature not in known_signatures:
                new_issues.append(issue)
        
        return new_issues

    def _intelligent_log_sampling(self, log_lines: List[str], target_size: int) -> List[str]:
        """
        Intelligently sample log lines to maintain representative coverage:
        - Prioritize error/warning lines
        - Maintain temporal distribution
        - Preserve context around errors
        - Include system state changes
        """
        if len(log_lines) <= target_size:
            return log_lines
        
        # Categorize lines
        error_lines = []
        warning_lines = []
        info_lines = []
        other_lines = []
        
        for i, line in enumerate(log_lines):
            line_lower = line.lower()
            if 'error' in line_lower or 'failed' in line_lower or 'exception' in line_lower:
                error_lines.append((i, line))
            elif 'warning' in line_lower or 'warn' in line_lower:
                warning_lines.append((i, line))
            elif 'info' in line_lower:
                info_lines.append((i, line))
            else:
                other_lines.append((i, line))
        
        # Sampling strategy
        sample_allocation = {
            'errors': min(len(error_lines), target_size // 2),  # 50% for errors
            'warnings': min(len(warning_lines), target_size // 4),  # 25% for warnings
            'info': min(len(info_lines), target_size // 6),  # ~17% for info
            'other': target_size // 12  # ~8% for other
        }
        
        sampled_lines = []
        
        # Sample errors (all if few, evenly distributed if many)
        if error_lines:
            if len(error_lines) <= sample_allocation['errors']:
                sampled_lines.extend(error_lines)
            else:
                step = len(error_lines) // sample_allocation['errors']
                sampled_lines.extend([error_lines[i] for i in range(0, len(error_lines), step)][:sample_allocation['errors']])
        
        # Sample warnings
        if warning_lines and len(sampled_lines) < target_size:
            remaining = target_size - len(sampled_lines)
            to_sample = min(sample_allocation['warnings'], remaining, len(warning_lines))
            if to_sample > 0:
                step = max(1, len(warning_lines) // to_sample)
                sampled_lines.extend([warning_lines[i] for i in range(0, len(warning_lines), step)][:to_sample])
        
        # Sample info lines
        if info_lines and len(sampled_lines) < target_size:
            remaining = target_size - len(sampled_lines)
            to_sample = min(sample_allocation['info'], remaining, len(info_lines))
            if to_sample > 0:
                step = max(1, len(info_lines) // to_sample)
                sampled_lines.extend([info_lines[i] for i in range(0, len(info_lines), step)][:to_sample])
        
        # Fill remaining with other lines
        if other_lines and len(sampled_lines) < target_size:
            remaining = target_size - len(sampled_lines)
            to_sample = min(remaining, len(other_lines))
            if to_sample > 0:
                step = max(1, len(other_lines) // to_sample)
                sampled_lines.extend([other_lines[i] for i in range(0, len(other_lines), step)][:to_sample])
        
        # Sort by original line index to maintain temporal order
        sampled_lines.sort(key=lambda x: x[0])
        
        return [line for _, line in sampled_lines]

    def _get_cache_key(self, content: str) -> str:
        """Generate cache key for content."""
        return hashlib.md5(content.encode('utf-8')).hexdigest()

    def _check_cache(self, cache_key: str) -> Optional[Dict]:
        """Check if analysis result is cached and still valid."""
        if cache_key in self.analysis_cache:
            cached_result, timestamp = self.analysis_cache[cache_key]
            if datetime.now() - timestamp < timedelta(seconds=self.cache_ttl):
                self.performance_metrics['cache_hits'] += 1
                return cached_result
            else:
                # Remove expired cache entry
                del self.analysis_cache[cache_key]
        
        self.performance_metrics['cache_misses'] += 1
        return None

    def _cache_result(self, cache_key: str, result: Dict):
        """Cache analysis result."""
        self.analysis_cache[cache_key] = (result, datetime.now())
        
        # Limit cache size (keep last 100 entries)
        if len(self.analysis_cache) > 100:
            oldest_key = min(self.analysis_cache.keys(), 
                           key=lambda k: self.analysis_cache[k][1])
            del self.analysis_cache[oldest_key]

    def get_performance_stats(self) -> Dict[str, Any]:
        """Get performance statistics."""
        cache_total = self.performance_metrics['cache_hits'] + self.performance_metrics['cache_misses']
        cache_hit_rate = (self.performance_metrics['cache_hits'] / max(cache_total, 1)) * 100
        
        avg_analysis_time = 0
        if self.performance_metrics['analysis_times']:
            avg_analysis_time = sum(self.performance_metrics['analysis_times']) / len(self.performance_metrics['analysis_times'])
        
        return {
            'current_profile': self.current_profile,
            'cache_hit_rate': round(cache_hit_rate, 2),
            'total_analyses': len(self.performance_metrics['analysis_times']),
            'average_analysis_time': round(avg_analysis_time, 2),
            'active_sessions': len(self.incremental_state),
            'cache_size': len(self.analysis_cache)
        }

    def clear_session(self, session_id: str):
        """Clear incremental analysis state for a session."""
        if session_id in self.incremental_state:
            del self.incremental_state[session_id]
            logger.info(f"Cleared session state for {session_id}")

    def cleanup_expired_sessions(self, max_age_hours: int = 24):
        """Clean up expired incremental analysis sessions."""
        current_time = datetime.now()
        expired_sessions = []
        
        for session_id, state in self.incremental_state.items():
            last_analysis = state.get('last_analysis')
            if last_analysis:
                try:
                    last_time = datetime.fromisoformat(last_analysis)
                    if current_time - last_time > timedelta(hours=max_age_hours):
                        expired_sessions.append(session_id)
                except:
                    expired_sessions.append(session_id)  # Invalid timestamp
        
        for session_id in expired_sessions:
            self.clear_session(session_id)
        
        logger.info(f"Cleaned up {len(expired_sessions)} expired sessions")

# Main entry point with enhanced capabilities
async def perform_optimized_log_analysis(raw_log_content: str, basic_parsed_data: Dict[str, Any], 
                                       progress_callback: Optional[callable] = None,
                                       performance_profile: Optional[str] = None,
                                       time_constraint: Optional[int] = None) -> Dict[str, Any]:
    """
    Main entry point for optimized high-performance log analysis.
    Enhanced with adaptive profiles and performance optimization.
    """
    analyzer = OptimizedLogAnalyzer()
    
    # Auto-adjust performance profile if needed
    if performance_profile:
        analyzer.set_performance_profile(performance_profile)
    elif time_constraint or len(raw_log_content) > 10000:
        analyzer.auto_adjust_profile(len(raw_log_content.split('\n')), time_constraint)
    
    result = await analyzer.perform_optimized_analysis(raw_log_content, basic_parsed_data, progress_callback)
    
    # Add performance stats to result
    result['performance_stats'] = analyzer.get_performance_stats()
    
    return result

# Incremental analysis entry point
async def perform_incremental_analysis(new_log_lines: List[str], session_id: str) -> Dict[str, Any]:
    """
    Entry point for incremental log analysis for real-time monitoring.
    """
    analyzer = OptimizedLogAnalyzer()
    return await analyzer.analyze_incremental(new_log_lines, session_id)