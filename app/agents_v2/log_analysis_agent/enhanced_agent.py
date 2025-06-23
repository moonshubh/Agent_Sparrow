"""
Enhanced Log Analysis Agent with Deep System Profiling and Intelligent Solution Generation
Production-ready agent leveraging Gemini 2.5 Pro for comprehensive log analysis.
"""

import os
import json
import time
from typing import Dict, Any, List
from dotenv import load_dotenv
from langchain_google_genai import ChatGoogleGenerativeAI
from uuid import uuid4
from datetime import datetime

from app.core.logging_config import get_logger
from .enhanced_schemas import (
    EnhancedLogAnalysisAgentState, 
    ComprehensiveLogAnalysisOutput,
    DetailedSystemMetadata,
    DetailedIssue,
    ComprehensiveSolution,
    ResearchRecommendation,
    AnalysisMetrics
)
from .advanced_parser import enhanced_parse_log_content
from .advanced_solution_engine import generate_comprehensive_solutions
from .intelligent_analyzer import perform_intelligent_log_analysis
from .optimized_analyzer import perform_optimized_log_analysis

# Load environment variables
load_dotenv()

# Ensure the GEMINI_API_KEY is set
if "GEMINI_API_KEY" not in os.environ:
    raise ValueError("GEMINI_API_KEY environment variable not set.")


class EnhancedLogAnalysisAgent:
    """Production-grade log analysis agent with comprehensive profiling and solution generation."""
    
    def __init__(self):
        self.primary_llm = ChatGoogleGenerativeAI(
            model="gemini-2.5-pro",  # Use most advanced model
            temperature=0.1,
            google_api_key=os.getenv("GEMINI_API_KEY"),
        )
        
        self.fallback_llm = ChatGoogleGenerativeAI(
            model="gemini-1.5-pro-latest",
            temperature=0.2,
            google_api_key=os.getenv("GEMINI_API_KEY"),
        )
        
        # Performance configuration
        self.use_optimized_analysis = os.getenv("USE_OPTIMIZED_ANALYSIS", "true").lower() == "true"
        self.optimization_threshold = int(os.getenv("OPTIMIZATION_THRESHOLD_LINES", "500"))
    
    async def analyze_logs(self, state: EnhancedLogAnalysisAgentState) -> Dict[str, Any]:
        """
        Comprehensive log analysis with deep system profiling and intelligent solution generation.
        """
        trace_id = state.get("trace_id") or str(uuid4())
        logger = get_logger("enhanced_log_analysis_agent", trace_id=trace_id)
        start_time = time.time()
        
        print("=== Enhanced Log Analysis Agent v3.0 ===")
        logger.info("enhanced_analysis_start", version="3.0")
        
        try:
            raw_log_content = state.get("raw_log_content")
            if not raw_log_content:
                logger.error("validation_error", reason="'raw_log_content' is missing.")
                raise ValueError("'raw_log_content' is missing from the agent state.")
            
            # Phase 1: Enhanced Log Parsing and System Profiling
            print("Phase 1: Advanced log parsing and system profiling...")
            logger.info("parsing_phase_start")
            
            parsed_data = enhanced_parse_log_content(raw_log_content)
            
            state['parsed_log_data'] = parsed_data["entries"]
            state['system_profile'] = parsed_data["system_profile"]
            state['detected_issues'] = parsed_data["detected_issues"]
            
            logger.info("parsing_complete", 
                       entries=len(parsed_data["entries"]),
                       issues_detected=len(parsed_data["detected_issues"]),
                       system_version=parsed_data["system_profile"].get("mailbird_version", "Unknown"))
            
            # Phase 2: Intelligent Analysis with Performance Optimization
            log_line_count = len(raw_log_content.split('\n'))
            
            # Choose analysis approach based on log size and configuration
            if self.use_optimized_analysis and log_line_count > self.optimization_threshold:
                print(f"Phase 2: High-performance optimized analysis ({log_line_count} lines)...")
                logger.info("optimized_analysis_start", log_lines=log_line_count)
                
                try:
                    # Use optimized analyzer for large logs
                    optimized_analysis = await perform_optimized_log_analysis(
                        raw_log_content, parsed_data
                    )
                    
                    state['optimized_analysis'] = optimized_analysis
                    logger.info("optimized_analysis_complete", 
                               analyzer_version="4.0-optimized",
                               performance_features=optimized_analysis.get('performance_metrics', {}).get('optimization_features', []))
                    
                    # Extract enhanced issues from optimized analysis
                    enhanced_issues = self._convert_optimized_issues_to_legacy_format(
                        optimized_analysis, parsed_data["detected_issues"]
                    )
                    
                except Exception as e:
                    logger.warning("optimized_analysis_failed", error=str(e))
                    print(f"Optimized analysis failed, falling back to standard analysis: {e}")
                    enhanced_issues = await self._fallback_to_basic_analysis(parsed_data, e)
                    
            else:
                print("Phase 2: AI-powered intelligent analysis with Gemini 2.5 Pro...")
                logger.info("intelligent_analysis_start")
                
                try:
                    # Use the intelligent analyzer for smaller logs or when optimization is disabled
                    intelligent_analysis = await perform_intelligent_log_analysis(
                        raw_log_content, parsed_data
                    )
                    
                    state['intelligent_analysis'] = intelligent_analysis
                    logger.info("intelligent_analysis_complete", 
                               ai_model="gemini-2.5-pro",
                               reasoning_approach="step-by-step-thinking")
                    
                    # Extract enhanced issues from intelligent analysis
                    enhanced_issues = self._convert_intelligent_issues_to_legacy_format(
                        intelligent_analysis.get('issues_analysis', {}),
                        parsed_data["detected_issues"]
                    )
                    
                except Exception as e:
                    logger.warning("intelligent_analysis_failed", error=str(e))
                    print(f"Intelligent analysis failed, falling back to basic analysis: {e}")
                    enhanced_issues = await self._fallback_to_basic_analysis(parsed_data, e)
            
            state['detected_issues'] = enhanced_issues
            logger.info("issue_analysis_complete", enhanced_issues_count=len(enhanced_issues))
            
            # Phase 3: Intelligent Solution Generation
            print("Phase 3: Generating AI-powered solutions...")
            logger.info("solution_generation_start")
            
            # Use solutions from appropriate analysis method
            if 'optimized_analysis' in state and 'optimized_solutions' in state['optimized_analysis']:
                # Use optimized solutions
                optimized_solutions = state['optimized_analysis']['optimized_solutions']
                solutions = self._convert_optimized_solutions_to_legacy_format(optimized_solutions)
                logger.info("using_optimized_solutions", count=len(solutions))
            elif 'intelligent_analysis' in state and 'intelligent_solutions' in state['intelligent_analysis']:
                # Use intelligent solutions
                intelligent_solutions = state['intelligent_analysis']['intelligent_solutions']
                solutions = self._convert_intelligent_solutions_to_legacy_format(intelligent_solutions)
                logger.info("using_intelligent_solutions", count=len(solutions))
            else:
                # Fallback to template-based solution generation
                account_analysis = parsed_data.get("account_analysis", [])
                solutions = await generate_comprehensive_solutions(
                    enhanced_issues, 
                    parsed_data["system_profile"], 
                    account_analysis
                )
                solutions = [solution.model_dump() if hasattr(solution, 'model_dump') else solution for solution in solutions]
                logger.info("using_fallback_solutions", count=len(solutions))
            
            state['generated_solutions'] = solutions
            logger.info("solution_generation_complete", solutions_count=len(solutions))
            
            # Phase 4: Comprehensive Report Generation
            print("Phase 4: Compiling comprehensive analysis report...")
            logger.info("report_generation_start")
            
            # Store state for report generation
            self._current_state = state
            
            final_report = await self._generate_comprehensive_report(
                parsed_data, enhanced_issues, solutions, start_time
            )
            
            state['final_report'] = final_report
            
            analysis_duration = time.time() - start_time
            logger.info("enhanced_analysis_complete", 
                       duration_seconds=round(analysis_duration, 2),
                       total_issues=len(enhanced_issues),
                       total_solutions=len(solutions))
            
            print(f"=== Analysis Complete ({analysis_duration:.2f}s) ===")
            
        except Exception as e:
            logger.error("enhanced_analysis_failed", error=str(e), exc_info=True)
            print(f"Enhanced analysis failed: {e}")
            
            # Generate comprehensive error report
            try:
                error_report = await self._generate_error_report(state, str(e), start_time)
                state['final_report'] = error_report
            except Exception as report_error:
                logger.error("error_report_generation_failed", error=str(report_error))
                # Create minimal fallback report
                state['final_report'] = {
                    'overall_summary': f'Analysis failed: {str(e)}',
                    'health_status': 'Unknown',
                    'system_metadata': {
                        'mailbird_version': 'Unknown',
                        'database_size_mb': 0.0,
                        'account_count': 0,
                        'folder_count': 0
                    },
                    'identified_issues': [],
                    'proposed_solutions': [],
                    'immediate_actions': ['Contact technical support with log file']
                }
        
        return {
            'parsed_log_data': state.get('parsed_log_data'),
            'system_profile': state.get('system_profile'),
            'detected_issues': state.get('detected_issues'),
            'generated_solutions': state.get('generated_solutions'),
            'final_report': state.get('final_report'),
            'trace_id': trace_id,
        }
    
    async def _enhance_issue_analysis(self, detected_issues: List[Dict], system_profile: Dict, log_entries: List[Dict]) -> List[Dict]:
        """Enhance issue analysis using Gemini 2.5 Pro reasoning."""
        enhanced_issues = []
        
        for issue in detected_issues:
            try:
                # Create detailed issue analysis prompt
                analysis_prompt = f"""
Analyze this Mailbird issue with expert-level reasoning:

ISSUE DETAILS:
- Category: {issue.get('category', 'Unknown')}
- Signature: {issue.get('signature', 'Unknown')}
- Occurrences: {issue.get('occurrences', 0)}
- Frequency Pattern: {issue.get('frequency_pattern', 'Unknown')}

SYSTEM CONTEXT:
- Mailbird Version: {system_profile.get('mailbird_version', 'Unknown')}
- Database Size: {system_profile.get('database_size_mb', 'Unknown')} MB
- Account Count: {system_profile.get('account_count', 'Unknown')}
- Memory Usage: {system_profile.get('memory_usage_mb', 'Unknown')} MB

ANALYSIS REQUIREMENTS:
1. Provide a confidence score (0.0-1.0) for issue detection accuracy
2. Refine the root cause analysis with deeper technical reasoning
3. Assess the true severity based on system context and frequency
4. Provide enhanced user impact assessment

Return a JSON object with:
{{
    "confidence_score": 0.85,
    "refined_root_cause": "Detailed technical analysis",
    "contextual_severity": "High|Medium|Low",
    "enhanced_user_impact": "Detailed impact analysis",
    "technical_recommendations": ["specific technical notes"]
}}
"""
                
                # Use Gemini 2.5 Pro for analysis
                response = await self.primary_llm.ainvoke(analysis_prompt)
                enhancement_data = json.loads(response.content)
                
                # Update issue with enhanced analysis
                issue.update({
                    'confidence_score': enhancement_data.get('confidence_score', 0.7),
                    'root_cause': enhancement_data.get('refined_root_cause', issue.get('root_cause', '')),
                    'severity': enhancement_data.get('contextual_severity', issue.get('severity', 'Medium')),
                    'user_impact': enhancement_data.get('enhanced_user_impact', issue.get('user_impact', '')),
                    'technical_recommendations': enhancement_data.get('technical_recommendations', [])
                })
                
                enhanced_issues.append(issue)
                
            except Exception as e:
                print(f"Failed to enhance issue {issue.get('issue_id', 'unknown')}: {e}")
                # Keep original issue if enhancement fails
                enhanced_issues.append(issue)
        
        return enhanced_issues
    
    def _convert_intelligent_issues_to_legacy_format(self, intelligent_issues: Dict, fallback_issues: List[Dict]) -> List[Dict]:
        """Convert intelligent analysis issues to legacy format for compatibility."""
        try:
            converted_issues = []
            
            # Extract patterns and convert to legacy issue format
            for pattern in intelligent_issues.get('identified_patterns', []):
                issue = {
                    'issue_id': f"ai_{pattern.get('pattern_type', 'unknown')}",
                    'category': pattern.get('pattern_type', 'Unknown').replace('_', ' ').title(),
                    'signature': pattern.get('technical_details', ''),
                    'severity': pattern.get('impact_level', 'Medium').title(),
                    'root_cause': pattern.get('technical_details', ''),
                    'user_impact': f"Affects {len(pattern.get('accounts_affected', []))} accounts",
                    'affected_accounts': pattern.get('accounts_affected', []),
                    'confidence_score': 0.9,  # High confidence for AI analysis
                    'frequency_pattern': pattern.get('frequency', 'Unknown'),
                    'ai_generated': True
                }
                converted_issues.append(issue)
            
            # Convert issue categories
            for category, details in intelligent_issues.get('issue_categories', {}).items():
                issue = {
                    'issue_id': f"ai_category_{category}",
                    'category': category.replace('_', ' ').title(),
                    'signature': details.get('description', ''),
                    'severity': details.get('severity', 'Medium').title(),
                    'root_cause': details.get('description', ''),
                    'user_impact': f"Affects {len(details.get('accounts', []))} accounts",
                    'affected_accounts': details.get('accounts', []),
                    'occurrences': details.get('count', 1),
                    'confidence_score': 0.9,
                    'ai_generated': True
                }
                converted_issues.append(issue)
            
            return converted_issues if converted_issues else fallback_issues
            
        except Exception as e:
            print(f"Failed to convert intelligent issues: {e}")
            return fallback_issues
    
    def _convert_intelligent_solutions_to_legacy_format(self, intelligent_solutions: List[Dict]) -> List[Dict]:
        """Convert intelligent solutions to legacy format for compatibility."""
        try:
            converted_solutions = []
            
            for solution in intelligent_solutions:
                # Convert to expected format
                converted_solution = {
                    'issue_id': solution.get('solution_id', 'unknown'),
                    'solution_summary': solution.get('title', ''),
                    'priority': solution.get('priority', 'Medium'),
                    'implementation_timeline': solution.get('estimated_resolution_time', 'Unknown'),
                    'success_probability': solution.get('success_probability', 'Medium'),
                    'solution_steps': solution.get('implementation_steps', []),
                    'prerequisites': solution.get('prerequisites', []),
                    'estimated_total_time_minutes': self._extract_time_minutes(
                        solution.get('estimated_resolution_time', '15 minutes')
                    ),
                    'alternative_approaches': solution.get('alternative_approaches', []),
                    'expected_outcome': f"Resolves {solution.get('title', 'issue')}",
                    'ai_generated': True,
                    'technical_notes': solution.get('technical_notes', ''),
                    'success_metrics': solution.get('success_metrics', []),
                    'risks': solution.get('risks', [])
                }
                converted_solutions.append(converted_solution)
            
            return converted_solutions
            
        except Exception as e:
            print(f"Failed to convert intelligent solutions: {e}")
            return []
    
    def _extract_time_minutes(self, time_str: str) -> int:
        """Extract minutes from time string like '15-30 minutes'."""
        try:
            import re
            numbers = re.findall(r'\d+', time_str)
            if numbers:
                return int(numbers[0])  # Take first number
            return 15  # Default
        except:
            return 15
    
    async def _fallback_to_basic_analysis(self, parsed_data: Dict, error: Exception) -> List[Dict]:
        """Fallback to basic issue enhancement when advanced analysis fails."""
        try:
            enhanced_issues = await self._enhance_issue_analysis(
                parsed_data["detected_issues"], 
                parsed_data["system_profile"],
                parsed_data["entries"]
            )
            return enhanced_issues
        except Exception as fallback_error:
            # Return basic detected issues if all else fails
            return parsed_data.get("detected_issues", [])
    
    def _convert_optimized_issues_to_legacy_format(self, optimized_analysis: Dict, fallback_issues: List[Dict]) -> List[Dict]:
        """Convert optimized analysis results to legacy format for compatibility."""
        try:
            converted_issues = []
            
            # Extract from basic analysis
            basic_analysis = optimized_analysis.get('basic_analysis', {})
            immediate_issues = basic_analysis.get('immediate_issues', [])
            
            for issue in immediate_issues:
                converted_issue = {
                    'issue_id': f"opt_{issue.get('type', 'unknown')}",
                    'category': issue.get('type', 'Unknown').replace('_', ' ').title(),
                    'signature': issue.get('sample_message', ''),
                    'severity': issue.get('severity', 'Medium').title(),
                    'root_cause': f"Detected {issue.get('count', 1)} occurrences of {issue.get('type', 'issue')}",
                    'user_impact': f"Affects {len(issue.get('accounts_affected', []))} accounts",
                    'affected_accounts': issue.get('accounts_affected', []),
                    'occurrences': issue.get('count', 1),
                    'confidence_score': 0.85,  # High confidence for optimized analysis
                    'ai_generated': True,
                    'analysis_method': 'optimized'
                }
                converted_issues.append(converted_issue)
            
            # Extract from deep analysis patterns
            deep_analysis = optimized_analysis.get('deep_analysis', {})
            critical_patterns = deep_analysis.get('critical_patterns', [])
            
            for pattern in critical_patterns:
                converted_issue = {
                    'issue_id': f"opt_pattern_{pattern.get('pattern', 'unknown').replace(' ', '_')}",
                    'category': 'Pattern Analysis',
                    'signature': pattern.get('pattern', ''),
                    'severity': pattern.get('severity', 'Medium').title(),
                    'root_cause': pattern.get('context', 'Pattern-based detection'),
                    'user_impact': f"Pattern occurs {pattern.get('occurrences', 1)} times",
                    'occurrences': pattern.get('occurrences', 1),
                    'confidence_score': 0.9,
                    'ai_generated': True,
                    'analysis_method': 'optimized_pattern'
                }
                converted_issues.append(converted_issue)
            
            return converted_issues if converted_issues else fallback_issues
            
        except Exception as e:
            print(f"Failed to convert optimized issues: {e}")
            return fallback_issues
    
    def _convert_optimized_solutions_to_legacy_format(self, optimized_solutions: List[Dict]) -> List[Dict]:
        """Convert optimized solutions to legacy format for compatibility."""
        try:
            converted_solutions = []
            
            for solution in optimized_solutions:
                converted_solution = {
                    'issue_id': solution.get('solution_id', 'unknown'),
                    'solution_summary': solution.get('title', ''),
                    'priority': solution.get('priority', 'Medium'),
                    'implementation_timeline': solution.get('estimated_time', 'Unknown'),
                    'success_probability': solution.get('success_rate', 'Medium'),
                    'solution_steps': solution.get('implementation_steps', []),
                    'estimated_total_time_minutes': self._extract_time_minutes(
                        solution.get('estimated_time', '15 minutes')
                    ),
                    'expected_outcome': f"Resolves {solution.get('title', 'issue')}",
                    'ai_generated': True,
                    'analysis_method': 'optimized',
                    'target_issues': solution.get('target_issues', []),
                    'risk_level': solution.get('risk_level', 'Low')
                }
                converted_solutions.append(converted_solution)
            
            return converted_solutions
            
        except Exception as e:
            print(f"Failed to convert optimized solutions: {e}")
            return []
    
    async def _generate_comprehensive_report(self, parsed_data: Dict, issues: List[Dict], solutions: List, start_time: float) -> ComprehensiveLogAnalysisOutput:
        """Generate the final comprehensive analysis report."""
        
        def safe_float(value, default=0.0):
            """Safely convert value to float, handling 'Unknown' and other strings."""
            try:
                if isinstance(value, str) and value.lower() in ['unknown', 'n/a', '']:
                    return default
                return float(value)
            except (ValueError, TypeError):
                return default
        
        def safe_int(value, default=0):
            """Safely convert value to int, handling 'Unknown' and other strings."""
            try:
                if isinstance(value, str) and value.lower() in ['unknown', 'n/a', '']:
                    return default
                return int(value)
            except (ValueError, TypeError):
                return default
        
        # Create detailed system metadata
        system_metadata = DetailedSystemMetadata(
            mailbird_version=parsed_data["system_profile"].get("mailbird_version", "Unknown"),
            database_size_mb=safe_float(parsed_data["system_profile"].get("database_size_mb", 0)),
            account_count=safe_int(parsed_data["system_profile"].get("account_count", 0)),
            folder_count=safe_int(parsed_data["system_profile"].get("folder_count", 0)),
            memory_usage_mb=safe_float(parsed_data["system_profile"].get("memory_usage_mb")),
            startup_time_ms=safe_float(parsed_data["system_profile"].get("startup_time_ms")),
            email_providers=parsed_data["system_profile"].get("email_providers", []),
            sync_status=parsed_data["system_profile"].get("sync_status"),
            os_version=parsed_data["system_profile"].get("os_version", "Unknown"),
            system_architecture=parsed_data["system_profile"].get("system_architecture", "Unknown"),
            log_timeframe=parsed_data["metadata"].get("log_timeframe", "Unknown"),
            analysis_timestamp=datetime.utcnow().isoformat(),
            total_entries_parsed=len(parsed_data["entries"]),
            error_rate_percentage=safe_float(parsed_data["metadata"].get("error_rate_percentage", 0.0)),
            log_level_distribution=parsed_data["metadata"].get("log_level_distribution", {})
        )
        
        # Convert issues to detailed issue objects
        detailed_issues = [
            DetailedIssue(
                issue_id=issue.get("issue_id", "unknown"),
                category=issue.get("category", "unknown"),
                signature=issue.get("signature", ""),
                occurrences=issue.get("occurrences", 0),
                severity=issue.get("severity", "Medium"),
                root_cause=issue.get("root_cause", ""),
                user_impact=issue.get("user_impact", ""),
                first_occurrence=issue.get("first_occurrence"),
                last_occurrence=issue.get("last_occurrence"),
                frequency_pattern=issue.get("frequency_pattern", "Unknown"),
                related_log_levels=issue.get("related_log_levels", []),
                confidence_score=issue.get("confidence_score", 0.7)
            )
            for issue in issues
        ]
        
        # Convert solutions to comprehensive solution objects
        comprehensive_solutions = []
        for solution in solutions:
            try:
                # Debug: log solution type and structure
                print(f"Processing solution type: {type(solution)}, keys: {getattr(solution, 'keys', lambda: 'no keys')() if hasattr(solution, 'keys') else 'no keys method'}")
                
                # Convert all solutions to dictionary format first for consistency
                if hasattr(solution, 'model_dump'):
                    # Convert Pydantic models to dict
                    solution_dict = solution.model_dump()
                elif hasattr(solution, 'dict'):
                    # Convert Pydantic models (older version) to dict
                    solution_dict = solution.dict()
                elif isinstance(solution, dict):
                    # Already a dictionary - normalize field names for compatibility
                    solution_dict = {
                        'issue_id': solution.get('issue_id', solution.get('solution_id', 'unknown')),
                        'solution_summary': solution.get('solution_summary', solution.get('title', 'No summary')),
                        'confidence_level': solution.get('confidence_level', solution.get('priority', 'Medium')),
                        'solution_steps': solution.get('solution_steps', solution.get('implementation_steps', [])),
                        'prerequisites': solution.get('prerequisites', []),
                        'estimated_total_time_minutes': solution.get('estimated_total_time_minutes', solution.get('eta_min', solution.get('estimated_time_minutes', 30))),
                        'success_probability': solution.get('success_probability', solution.get('success_prob', 'Medium')),
                        'alternative_approaches': solution.get('alternative_approaches', []),
                        'references': solution.get('references', [])
                    }
                else:
                    # Convert object to dictionary using getattr
                    solution_dict = {
                        'issue_id': getattr(solution, 'issue_id', 'unknown'),
                        'solution_summary': getattr(solution, 'solution_summary', 'No summary'),
                        'confidence_level': getattr(solution, 'confidence_level', 'Medium'),
                        'solution_steps': getattr(solution, 'solution_steps', []),
                        'prerequisites': getattr(solution, 'prerequisites', []),
                        'estimated_total_time_minutes': getattr(solution, 'estimated_total_time_minutes', 30),
                        'success_probability': getattr(solution, 'success_probability', 'Medium'),
                        'alternative_approaches': getattr(solution, 'alternative_approaches', []),
                        'references': getattr(solution, 'references', [])
                    }
                
                # Now handle the dictionary format consistently
                solution_steps_dicts = []
                raw_steps = solution_dict.get('solution_steps', [])
                
                for i, step in enumerate(raw_steps):
                    if isinstance(step, dict):
                        step_dict = {
                            "step_number": step.get('step_number', i + 1),
                            "description": step.get('action', step.get('description', 'No description')),
                            "expected_outcome": step.get('expected_outcome', step.get('expected_result', 'Unknown outcome')),
                            "troubleshooting_note": step.get('troubleshooting_note', '')
                        }
                    else:
                        # Handle string steps or object steps
                        if hasattr(step, 'description'):
                            # Object step
                            step_dict = {
                                "step_number": getattr(step, 'step_number', i + 1),
                                "description": getattr(step, 'description', str(step)),
                                "expected_outcome": getattr(step, 'expected_outcome', 'Complete step successfully'),
                                "troubleshooting_note": getattr(step, 'troubleshooting_note', '')
                            }
                        else:
                            # String step
                            step_dict = {
                                "step_number": i + 1,
                                "description": str(step),
                                "expected_outcome": "Complete step successfully",
                                "troubleshooting_note": ""
                            }
                    solution_steps_dicts.append(step_dict)
                
                comprehensive_solution = ComprehensiveSolution(
                    issue_id=solution_dict.get('issue_id', 'unknown'),
                    solution_summary=solution_dict.get('solution_summary', solution_dict.get('title', 'No summary')),
                    confidence_level=solution_dict.get('confidence_level', 'Medium'),
                    solution_steps=solution_steps_dicts,
                    prerequisites=solution_dict.get('prerequisites', []),
                    estimated_total_time_minutes=solution_dict.get('estimated_total_time_minutes', 30),
                    success_probability=solution_dict.get('success_probability', 'Medium'),
                    alternative_approaches=solution_dict.get('alternative_approaches', []),
                    references=solution_dict.get('references', []),
                    requires_restart=any("restart" in str(step).lower() for step in raw_steps),
                    data_backup_required=any("backup" in str(step).lower() for step in raw_steps)
                )
                    
                comprehensive_solutions.append(comprehensive_solution)
            except Exception as e:
                # If validation fails, create a minimal fallback solution
                print(f"Failed to create ComprehensiveSolution: {e}, creating fallback solution")
                
                # Extract basic info safely using the same conversion pattern
                if hasattr(solution, 'model_dump'):
                    solution_dict = solution.model_dump()
                elif hasattr(solution, 'dict'):
                    solution_dict = solution.dict()
                elif isinstance(solution, dict):
                    solution_dict = solution
                else:
                    solution_dict = {
                        'issue_id': getattr(solution, 'issue_id', 'unknown'),
                        'solution_summary': getattr(solution, 'solution_summary', 'Unknown issue'),
                        'title': getattr(solution, 'title', 'Unknown issue')
                    }
                
                issue_id = solution_dict.get('issue_id', 'unknown')
                summary = solution_dict.get('solution_summary', solution_dict.get('title', 'Unknown issue'))
                
                fallback_solution = ComprehensiveSolution(
                    issue_id=issue_id,
                    solution_summary=summary,
                    confidence_level="Low",
                    solution_steps=[{
                        "step_number": 1,
                        "description": "Contact technical support with log file details",
                        "expected_outcome": "Professional assistance for issue resolution",
                        "troubleshooting_note": ""
                    }],
                    prerequisites=[],
                    estimated_total_time_minutes=15,
                    success_probability="Medium",
                    alternative_approaches=[],
                    references=[],
                    requires_restart=False,
                    data_backup_required=False
                )
                comprehensive_solutions.append(fallback_solution)
        
        # Generate executive summary
        high_severity_count = sum(1 for issue in issues if issue.get("severity") == "High")
        medium_severity_count = sum(1 for issue in issues if issue.get("severity") == "Medium")
        low_severity_count = sum(1 for issue in issues if issue.get("severity") == "Low")
        
        if high_severity_count > 0:
            health_status = "Critical"
        elif medium_severity_count > 2:
            health_status = "Degraded"
        else:
            health_status = "Healthy"
        
        # Create analysis metrics
        # Helper function to safely check requires_web_search
        def check_requires_web_search(solution):
            if isinstance(solution, dict):
                return solution.get('requires_web_search', False)
            else:
                return getattr(solution, 'requires_web_search', False)
        
        analysis_metrics = AnalysisMetrics(
            analysis_duration_seconds=round(time.time() - start_time, 2),
            parser_version="3.0.0-enhanced",
            llm_model_used="gemini-2.5-pro",
            web_search_performed=any(check_requires_web_search(solution) for solution in solutions),
            confidence_threshold_met=all(issue.get("confidence_score", 0) > 0.7 for issue in issues),
            completeness_score=min(1.0, len(issues) * 0.1 + len(solutions) * 0.1)
        )
        
        # Generate immediate actions and recommendations
        immediate_actions = []
        preventive_measures = []
        monitoring_recommendations = []
        
        for issue in issues:
            if issue.get("severity") == "High":
                immediate_actions.append(f"Address {issue.get('category', 'unknown')} issue immediately")
            
        preventive_measures.extend([
            "Regular database maintenance and optimization",
            "Monitor system resources and performance",
            "Keep Mailbird updated to latest version",
            "Regular backup of email data and settings"
        ])
        
        monitoring_recommendations.extend([
            "Monitor error rates in future log files",
            "Track application performance metrics",
            "Watch for recurring authentication issues",
            "Monitor database size growth"
        ])
        
        # Include AI-generated executive summary if available
        ai_executive_summary = None
        ai_analysis_metadata = None
        analysis_method = "standard"
        
        # Check which analysis method was used and get appropriate summary
        if hasattr(self, '_current_state'):
            if 'optimized_analysis' in self._current_state:
                optimized_analysis = self._current_state['optimized_analysis']
                ai_executive_summary = optimized_analysis.get('executive_summary')
                ai_analysis_metadata = optimized_analysis.get('performance_metrics')
                analysis_method = "optimized"
            elif 'intelligent_analysis' in self._current_state:
                intelligent_analysis = self._current_state['intelligent_analysis']
                ai_executive_summary = intelligent_analysis.get('executive_summary')
                ai_analysis_metadata = intelligent_analysis.get('analysis_metadata')
                analysis_method = "intelligent"
        
        # Create enhanced overall summary based on analysis method
        if ai_executive_summary and analysis_method == "optimized":
            performance_info = ai_analysis_metadata.get('analysis_duration_seconds', 0) if ai_analysis_metadata else 0
            overall_summary = f"## High-Performance Analysis Results\n\n{ai_executive_summary}\n\n---\n\n**Technical Summary:** Optimized analysis of Mailbird {system_metadata.mailbird_version} identified {len(issues)} issues across {len(parsed_data['entries'])} log entries in {performance_info:.1f}s using parallel processing. System health: {health_status}."
        elif ai_executive_summary and analysis_method == "intelligent":
            overall_summary = f"## AI-Powered Analysis Results\n\n{ai_executive_summary}\n\n---\n\n**Technical Summary:** Analysis of Mailbird {system_metadata.mailbird_version} identified {len(issues)} issues across {len(parsed_data['entries'])} log entries using Gemini 2.5 Pro reasoning. System health: {health_status}."
        else:
            overall_summary = f"Analysis of Mailbird {system_metadata.mailbird_version} identified {len(issues)} issues across {len(parsed_data['entries'])} log entries. System health: {health_status}."
        
        return ComprehensiveLogAnalysisOutput(
            overall_summary=overall_summary,
            health_status=health_status,
            priority_concerns=[issue.get("category", "unknown") for issue in issues[:3] if issue.get("severity") == "High"],
            system_metadata=system_metadata,
            identified_issues=detailed_issues,
            issue_summary_by_severity={
                "High": high_severity_count,
                "Medium": medium_severity_count,
                "Low": low_severity_count
            },
            proposed_solutions=comprehensive_solutions,
            supplemental_research=ResearchRecommendation(
                rationale="Additional research recommended for complex issues",
                recommended_queries=[f"Mailbird {system_metadata.mailbird_version} troubleshooting"],
                research_priority="Medium",
                expected_information="Version-specific fixes and updates"
            ) if any(check_requires_web_search(solution) for solution in solutions) else None,
            analysis_metrics=analysis_metrics,
            immediate_actions=immediate_actions,
            preventive_measures=preventive_measures,
            monitoring_recommendations=monitoring_recommendations
        )
    
    async def _generate_error_report(self, state: Dict, error: str, start_time: float) -> ComprehensiveLogAnalysisOutput:
        """Generate a comprehensive error report when analysis fails."""
        
        # Basic system metadata from partial parsing
        parsed_log_data = state.get('parsed_log_data', {})
        if parsed_log_data and isinstance(parsed_log_data, dict):
            metadata = parsed_log_data.get('metadata', {})
        else:
            metadata = {}
        
        system_metadata = DetailedSystemMetadata(
            mailbird_version=metadata.get("mailbird_version", "Unknown"),
            database_size_mb=0.0,
            account_count=0,
            folder_count=0,
            log_timeframe=metadata.get("log_timeframe", "Unknown"),
            analysis_timestamp=datetime.utcnow().isoformat(),
            total_entries_parsed=metadata.get("total_entries_parsed", 0),
            error_rate_percentage=0.0,
            log_level_distribution={}
        )
        
        analysis_metrics = AnalysisMetrics(
            analysis_duration_seconds=round(time.time() - start_time, 2),
            parser_version="3.0.0-enhanced",
            llm_model_used="gemini-2.5-pro",
            web_search_performed=False,
            confidence_threshold_met=False,
            completeness_score=0.0
        )
        
        return ComprehensiveLogAnalysisOutput(
            overall_summary=f"Log analysis failed due to system error: {error}",
            health_status="Unknown",
            priority_concerns=["Analysis system error"],
            system_metadata=system_metadata,
            identified_issues=[],
            issue_summary_by_severity={"High": 0, "Medium": 0, "Low": 0},
            proposed_solutions=[],
            supplemental_research=ResearchRecommendation(
                rationale="Manual analysis required due to system error",
                recommended_queries=["Mailbird manual log analysis", "Mailbird support contact"],
                research_priority="High",
                expected_information="Professional technical support"
            ),
            analysis_metrics=analysis_metrics,
            immediate_actions=["Contact technical support with log file"],
            preventive_measures=["Ensure proper log file format"],
            monitoring_recommendations=["Monitor system resources during log analysis"]
        )


# Main entry point function
async def run_enhanced_log_analysis_agent(state: EnhancedLogAnalysisAgentState) -> Dict[str, Any]:
    """
    Main entry point for the enhanced log analysis agent.
    """
    agent = EnhancedLogAnalysisAgent()
    return await agent.analyze_logs(state)