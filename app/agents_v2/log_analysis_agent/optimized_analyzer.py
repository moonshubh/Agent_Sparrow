"""
High-Performance Log Analysis Engine with Intelligent Optimization
Optimized for speed while maintaining analysis quality through parallel processing and smart chunking.
"""

import os
import json
import time
import asyncio
import hashlib
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor
from langchain_google_genai import ChatGoogleGenerativeAI
from app.core.logging_config import get_logger
from app.core.settings import settings

class OptimizedLogAnalyzer:
    """
    High-performance log analyzer using parallel processing, smart chunking,
    and progressive analysis for sub-60-second analysis times.
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
        
        # Performance configuration
        self.MAX_CHUNK_SIZE = 5000  # Max lines per chunk
        self.MAX_CONTEXT_CHARS = 15000  # Max chars to send to AI
        self.PARALLEL_CHUNKS = 3  # Max parallel processing
        
        # Cache for similar log patterns
        self.analysis_cache = {}
        
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
        
        # Phase 2: Parallel Deep Analysis (15-30 seconds)
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
        
        if progress_callback:
            await progress_callback(f"✅ Analysis complete in {analysis_duration:.1f}s")
        
        return {
            'basic_analysis': basic_analysis,
            'deep_analysis': deep_analysis,
            'optimized_solutions': solutions,
            'executive_summary': executive_summary,
            'performance_metrics': {
                'analysis_duration_seconds': analysis_duration,
                'analyzer_version': '4.0-optimized',
                'optimization_features': ['parallel_processing', 'smart_chunking', 'progressive_analysis'],
                'analysis_timestamp': datetime.utcnow().isoformat()
            }
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

# Main entry point
async def perform_optimized_log_analysis(raw_log_content: str, basic_parsed_data: Dict[str, Any], 
                                       progress_callback: Optional[callable] = None) -> Dict[str, Any]:
    """
    Main entry point for optimized high-performance log analysis.
    """
    analyzer = OptimizedLogAnalyzer()
    return await analyzer.perform_optimized_analysis(raw_log_content, basic_parsed_data, progress_callback)