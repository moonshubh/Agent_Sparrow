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

from app.core.settings import settings
from app.core.rate_limiting.agent_wrapper import wrap_gemini_agent
from uuid import uuid4
from datetime import datetime

from app.core.logging_config import get_logger
from .enhanced_schemas import (
    EnhancedLogAnalysisAgentState, 
    ComprehensiveLogAnalysisOutput,
    DetailedSystemMetadata,
    DetailedIssue,
    ComprehensiveSolution,
    EnhancedSolution,
    EnhancedSolutionStep,
    AutomatedTest,
    ResearchRecommendation,
    AnalysisMetrics,
    EnvironmentalContext,
    CorrelationAnalysis,
    DependencyAnalysis,
    PredictiveInsight,
    MLPatternDiscovery,
    ValidationSummary
)
from .edge_case_handler import EdgeCaseHandler
from .advanced_parser import AdvancedMailbirdAnalyzer
from .advanced_solution_engine import AdvancedSolutionEngine
from .intelligent_analyzer import IntelligentLogAnalyzer
from .optimized_analyzer import OptimizedLogAnalyzer

# Load environment variables
load_dotenv()

# GEMINI_API_KEY is now optional - will be retrieved from user context or database
# if not settings.gemini_api_key:
#     raise ValueError("GEMINI_API_KEY environment variable not set.")


class EnhancedLogAnalysisAgent:
    """Production-grade log analysis agent with comprehensive profiling and solution generation v3.0."""
    
    def __init__(self):
        # Create rate-limited LLM instances
        primary_llm_base = ChatGoogleGenerativeAI(
            model="gemini-2.5-pro",  # Use most advanced model
            temperature=0.1,
            google_api_key=settings.gemini_api_key,
        )
        self.primary_llm = wrap_gemini_agent(primary_llm_base, "gemini-2.5-pro")
        
        fallback_llm_base = ChatGoogleGenerativeAI(
            model="gemini-2.5-flash",  # Use supported model for rate limiting
            temperature=0.2,
            google_api_key=settings.gemini_api_key,
        )
        self.fallback_llm = wrap_gemini_agent(fallback_llm_base, "gemini-2.5-flash")
        
        # Initialize enhanced components
        self.edge_case_handler = EdgeCaseHandler()
        self.advanced_parser = AdvancedMailbirdAnalyzer()
        self.intelligent_analyzer = IntelligentLogAnalyzer()
        self.optimized_analyzer = OptimizedLogAnalyzer()
        self.solution_engine = AdvancedSolutionEngine()
        
        # Initialize state tracking for consistent access patterns
        self._current_state = {}
        
        # Performance configuration
        self.use_optimized_analysis = os.getenv("USE_OPTIMIZED_ANALYSIS", "true").lower() == "true"
        self.use_enhanced_log_analysis = os.getenv("USE_ENHANCED_LOG_ANALYSIS", "true").lower() == "true"
        self.optimization_threshold = int(os.getenv("OPTIMIZATION_THRESHOLD_LINES", "500"))
        
        # Enhanced analysis features
        self.enable_ml_pattern_discovery = os.getenv("ENABLE_ML_PATTERN_DISCOVERY", "true").lower() == "true"
        self.enable_predictive_analysis = os.getenv("ENABLE_PREDICTIVE_ANALYSIS", "true").lower() == "true"
        self.enable_correlation_analysis = os.getenv("ENABLE_CORRELATION_ANALYSIS", "true").lower() == "true"
        self.enable_automated_remediation = os.getenv("ENABLE_AUTOMATED_REMEDIATION", "false").lower() == "true"
    
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
            
            # Phase 1: Enhanced Log Preprocessing and Validation
            print("Phase 1: Enhanced log preprocessing with edge case handling...")
            logger.info("preprocessing_phase_start")
            
            # Use enhanced edge case handler for preprocessing
            try:
                preprocessed_content = await self.edge_case_handler.preprocess_log_content(raw_log_content)
                validation_summary = self.edge_case_handler.validate_analysis_input(preprocessed_content)
                
                # Detect platform and language
                detected_platform = await self.edge_case_handler.detect_platform(preprocessed_content)
                detected_language = await self.edge_case_handler.detect_log_language(preprocessed_content)
                
                logger.info("preprocessing_complete", 
                           content_length=len(preprocessed_content),
                           detected_platform=detected_platform,
                           detected_language=detected_language,
                           validation_issues=len(validation_summary.get('issues', [])))
                
            except Exception as e:
                logger.warning("preprocessing_failed", error=str(e))
                preprocessed_content = raw_log_content
                detected_platform = 'unknown'
                detected_language = 'en'
                validation_summary = {'is_valid': True, 'warnings': []}
            
            # Phase 2: Advanced Log Parsing with Enhanced Features
            print("Phase 2: Advanced log parsing with cross-platform and multi-language support...")
            logger.info("parsing_phase_start")
            
            try:
                # Use enhanced parser with platform and language detection
                parsed_data = await self.advanced_parser.analyze_logs(
                    preprocessed_content, 
                    platform=detected_platform,
                    language=detected_language
                )
                
                state['parsed_log_data'] = parsed_data["entries"]
                state['system_profile'] = parsed_data["system_profile"]
                state['detected_issues'] = parsed_data["detected_issues"]
                state['validation_summary'] = validation_summary
                state['environmental_context'] = {
                    'platform': detected_platform,
                    'language': detected_language,
                    'preprocessing_applied': preprocessed_content != raw_log_content
                }
                
                logger.info("parsing_complete", 
                           entries=len(parsed_data["entries"]),
                           issues_detected=len(parsed_data["detected_issues"]),
                           system_version=parsed_data["system_profile"].get("mailbird_version", "Unknown"),
                           platform=detected_platform,
                           language=detected_language,
                           ml_patterns_discovered=len(parsed_data.get("ml_discovered_patterns", [])))
                
            except Exception as e:
                logger.error("parsing_failed", error=str(e))
                # Fallback to basic parsing
                parsed_data = {
                    "entries": [],
                    "system_profile": {"mailbird_version": "Unknown"},
                    "detected_issues": [],
                    "metadata": {"total_entries_parsed": 0}
                }
                state['parsed_log_data'] = parsed_data["entries"]
                state['system_profile'] = parsed_data["system_profile"]
                state['detected_issues'] = parsed_data["detected_issues"]
            
            # Phase 3: Enhanced Intelligent Analysis with v3.0 Features
            log_line_count = len(preprocessed_content.split('\n'))
            
            # Choose analysis approach based on log size and configuration
            if self.use_optimized_analysis and log_line_count > self.optimization_threshold:
                print(f"Phase 3: High-performance optimized analysis ({log_line_count} lines)...")
                logger.info("optimized_analysis_start", log_lines=log_line_count)
                
                try:
                    # Use enhanced optimized analyzer
                    optimized_analysis = await self.optimized_analyzer.perform_optimized_analysis(
                        preprocessed_content, parsed_data
                    )
                    
                    state['optimized_analysis'] = optimized_analysis
                    logger.info("optimized_analysis_complete", 
                               analyzer_version="4.0-enhanced-optimized",
                               performance_features=optimized_analysis.get('performance_metrics', {}).get('optimization_features', []))
                    
                    # Extract enhanced issues from optimized analysis
                    enhanced_issues = self._convert_optimized_issues_to_legacy_format(
                        optimized_analysis, parsed_data["detected_issues"]
                    )
                    
                except Exception as e:
                    logger.warning("optimized_analysis_failed", error=str(e))
                    print(f"Optimized analysis failed, falling back to intelligent analysis: {e}")
                    enhanced_issues = await self._fallback_to_intelligent_analysis(parsed_data, preprocessed_content, e)
                    
            else:
                print("Phase 3: AI-powered intelligent analysis with enhanced v3.0 features...")
                logger.info("intelligent_analysis_start")
                
                try:
                    # Use enhanced intelligent analyzer with full v3.0 features
                    historical_data = state.get('historical_data', [])  # For predictive analysis
                    
                    intelligent_analysis = await self.intelligent_analyzer.perform_intelligent_analysis(
                        preprocessed_content, 
                        parsed_data,
                        historical_data=historical_data if self.enable_predictive_analysis else None
                    )
                    
                    state['intelligent_analysis'] = intelligent_analysis
                    
                    # Log enhanced features used
                    features_used = []
                    if intelligent_analysis.get('correlation_analysis'):
                        features_used.append('correlation_analysis')
                    if intelligent_analysis.get('dependency_analysis'):
                        features_used.append('dependency_analysis')
                    if intelligent_analysis.get('predictive_analysis'):
                        features_used.append('predictive_analysis')
                    
                    logger.info("intelligent_analysis_complete", 
                               ai_model="gemini-2.5-pro",
                               reasoning_approach="multi-phase-comprehensive",
                               enhanced_features=features_used)
                    
                    # Extract enhanced issues from intelligent analysis
                    enhanced_issues = self._convert_enhanced_intelligent_issues_to_legacy_format(
                        intelligent_analysis,
                        parsed_data["detected_issues"]
                    )
                    
                except Exception as e:
                    logger.warning("intelligent_analysis_failed", error=str(e))
                    print(f"Intelligent analysis failed, falling back to basic analysis: {e}")
                    enhanced_issues = await self._fallback_to_basic_analysis(parsed_data, e)
            
            state['detected_issues'] = enhanced_issues
            logger.info("issue_analysis_complete", enhanced_issues_count=len(enhanced_issues))
            
            # Phase 4: Enhanced Solution Generation with Automation Support
            print("Phase 4: Generating enhanced AI-powered solutions with automation...")
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
                solutions = self._convert_enhanced_intelligent_solutions_to_legacy_format(intelligent_solutions)
                logger.info("using_enhanced_intelligent_solutions", count=len(solutions))
            else:
                # Use enhanced solution engine for comprehensive solution generation
                try:
                    print("Generating comprehensive solutions with enhanced engine...")
                    account_analysis = parsed_data.get("account_analysis", [])
                    
                    # Use enhanced solution engine
                    enhanced_solutions = await self.solution_engine.generate_comprehensive_solutions(
                        enhanced_issues, 
                        parsed_data["system_profile"], 
                        account_analysis
                    )
                    
                    # Convert to consistent format
                    solutions = []
                    for solution in enhanced_solutions:
                        if hasattr(solution, 'model_dump'):
                            solutions.append(solution.model_dump())
                        elif hasattr(solution, 'dict'):
                            solutions.append(solution.dict())
                        elif isinstance(solution, dict):
                            solutions.append(solution)
                        else:
                            # Convert object to dict
                            solutions.append({
                                'issue_id': getattr(solution, 'issue_id', 'unknown'),
                                'solution_summary': getattr(solution, 'solution_summary', 'Unknown'),
                                'priority': getattr(solution, 'priority', 'Medium'),
                                'solution_steps': getattr(solution, 'solution_steps', []),
                                'estimated_total_time_minutes': getattr(solution, 'estimated_total_time_minutes', 30)
                            })
                    
                    logger.info("using_enhanced_solution_engine", count=len(solutions))
                    
                    # Add automation capabilities if enabled
                    if self.enable_automated_remediation:
                        solutions = await self._add_automation_capabilities(solutions)
                        logger.info("automation_capabilities_added")
                    
                except Exception as e:
                    logger.warning("enhanced_solution_generation_failed", error=str(e))
                    print(f"Enhanced solution generation failed, using basic solutions: {e}")
                    solutions = []
            
            state['generated_solutions'] = solutions
            logger.info("solution_generation_complete", solutions_count=len(solutions))
            
            # Phase 5: Comprehensive Report Generation with Enhanced Features
            print("Phase 5: Compiling comprehensive analysis report with v3.0 enhancements...")
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
                # Get Mailbird settings context - import here to avoid circular dependency
                from .mailbird_settings_knowledge import get_mailbird_settings_context
                mailbird_settings_context = get_mailbird_settings_context()
                
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

{mailbird_settings_context}

ANALYSIS REQUIREMENTS:
1. Provide a confidence score (0.0-1.0) for issue detection accuracy
2. Refine the root cause analysis with deeper technical reasoning
3. Assess the true severity based on system context and frequency
4. Provide enhanced user impact assessment
5. When recommending settings changes, ONLY suggest settings that exist in the Valid Mailbird Settings Reference above

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
            email_providers=parsed_data["system_profile"].get("email_providers", []),
            sync_status=parsed_data["system_profile"].get("sync_status"),
            os_version=parsed_data["system_profile"].get("os_version", "Unknown"),
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
                if isinstance(solution, dict):
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
                elif hasattr(solution, 'model_dump'):
                    # Convert Pydantic models to dict
                    solution_dict = solution.model_dump()
                elif hasattr(solution, 'dict'):
                    # Convert Pydantic models (older version) to dict
                    solution_dict = solution.dict()
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
                
                # Now handle the dictionary format consistently and create EnhancedSolutionStep objects
                enhanced_solution_steps = []
                raw_steps = solution_dict.get('solution_steps', [])
                
                for i, step in enumerate(raw_steps):
                    if isinstance(step, dict):
                        enhanced_step = EnhancedSolutionStep(
                            step_number=step.get('step_number', i + 1),
                            description=step.get('action', step.get('description', 'No description')),
                            expected_outcome=step.get('expected_outcome', step.get('expected_result', 'Unknown outcome')),
                            troubleshooting_note=step.get('troubleshooting_note', ''),
                            estimated_time_minutes=step.get('estimated_time_minutes', 5),
                            risk_level=step.get('risk_level', 'Low'),
                            platform_specific=step.get('platform_specific'),
                            automated_script=step.get('automated_script'),
                            validation_command=step.get('validation_command'),
                            rollback_procedure=step.get('rollback_procedure')
                        )
                    else:
                        # Handle string steps or object steps
                        if hasattr(step, 'description'):
                            # Object step
                            enhanced_step = EnhancedSolutionStep(
                                step_number=getattr(step, 'step_number', i + 1),
                                description=getattr(step, 'description', str(step)),
                                expected_outcome=getattr(step, 'expected_outcome', 'Complete step successfully'),
                                troubleshooting_note=getattr(step, 'troubleshooting_note', ''),
                                estimated_time_minutes=getattr(step, 'estimated_time_minutes', 5),
                                risk_level=getattr(step, 'risk_level', 'Low')
                            )
                        else:
                            # String step
                            enhanced_step = EnhancedSolutionStep(
                                step_number=i + 1,
                                description=str(step),
                                expected_outcome="Complete step successfully",
                                troubleshooting_note="",
                                estimated_time_minutes=5,
                                risk_level="Low"
                            )
                    enhanced_solution_steps.append(enhanced_step)
                
                comprehensive_solution = EnhancedSolution(
                    issue_id=solution_dict.get('issue_id', 'unknown'),
                    solution_summary=solution_dict.get('solution_summary', solution_dict.get('title', 'No summary')),
                    confidence_level=solution_dict.get('confidence_level', 'Medium'),
                    solution_steps=enhanced_solution_steps,
                    prerequisites=solution_dict.get('prerequisites', []),
                    estimated_total_time_minutes=solution_dict.get('estimated_total_time_minutes', 30),
                    success_probability=solution_dict.get('success_probability', 'Medium'),
                    alternative_approaches=solution_dict.get('alternative_approaches', []),
                    references=solution_dict.get('references', []),
                    requires_restart=any("restart" in str(step).lower() for step in raw_steps),
                    data_backup_required=any("backup" in str(step).lower() for step in raw_steps),
                    platform_compatibility=["windows", "macos", "linux"],  # Default to all platforms
                    automated_tests=[],  # No automated tests by default
                    success_criteria=[f"Issue '{solution_dict.get('issue_id', 'unknown')}' is resolved"]
                )
                    
                comprehensive_solutions.append(comprehensive_solution)
            except Exception as e:
                # If validation fails, create a minimal fallback solution
                print(f"Failed to create ComprehensiveSolution: {e}, creating fallback solution")
                
                # Extract basic info safely - avoid calling model_dump on dict
                if isinstance(solution, dict):
                    solution_dict = solution
                elif hasattr(solution, 'model_dump'):
                    solution_dict = solution.model_dump()
                elif hasattr(solution, 'dict'):
                    solution_dict = solution.dict()
                else:
                    solution_dict = {
                        'issue_id': getattr(solution, 'issue_id', 'unknown'),
                        'solution_summary': getattr(solution, 'solution_summary', 'Unknown issue'),
                        'title': getattr(solution, 'title', 'Unknown issue')
                    }
                
                issue_id = solution_dict.get('issue_id', 'unknown')
                summary = solution_dict.get('solution_summary', solution_dict.get('title', 'Unknown issue'))
                
                # Create fallback solution step as EnhancedSolutionStep
                fallback_step = EnhancedSolutionStep(
                    step_number=1,
                    description="Contact technical support with log file details",
                    expected_outcome="Professional assistance for issue resolution",
                    troubleshooting_note="",
                    estimated_time_minutes=15,
                    risk_level="Low"
                )
                
                fallback_solution = EnhancedSolution(
                    issue_id=issue_id,
                    solution_summary=summary,
                    confidence_level="Low",
                    solution_steps=[fallback_step],
                    prerequisites=[],
                    estimated_total_time_minutes=15,
                    success_probability="Medium",
                    alternative_approaches=[],
                    references=[],
                    requires_restart=False,
                    data_backup_required=False,
                    platform_compatibility=["windows", "macos", "linux"],
                    automated_tests=[],
                    success_criteria=["Contact support successfully"]
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
        
        # Create required environmental context
        environmental_context = EnvironmentalContext(
            os_version=getattr(self, '_current_state', {}).get('environmental_context', {}).get('platform', 'unknown'),
            platform=getattr(self, '_current_state', {}).get('environmental_context', {}).get('platform', 'unknown'),
            antivirus_software=[],
            firewall_status="unknown",
            network_type="unknown", 
            proxy_configured=False,
            system_locale="en-US",
            timezone="UTC"
        )
        
        # Create required correlation analysis
        correlation_analysis = CorrelationAnalysis(
            temporal_correlations=[],
            account_correlations=[],
            issue_type_correlations=[],
            correlation_matrix={},
            analysis_summary={"status": "basic_analysis", "correlations_found": 0}
        )
        
        # Create required dependency analysis
        dependency_analysis = DependencyAnalysis(
            graph_summary={"total_nodes": len(issues), "total_edges": 0},
            root_causes=[issue.get("issue_id", "unknown") for issue in issues[:3] if issue.get("severity") == "High"],
            primary_symptoms=[issue.get("issue_id", "unknown") for issue in issues if issue.get("severity") in ["Medium", "Low"]],
            cyclical_dependencies=[],
            centrality_measures={},
            issue_relationships=[]
        )
        
        # Create required predictive insights
        predictive_insights = []
        
        # Create required ML pattern discovery  
        ml_pattern_discovery = MLPatternDiscovery(
            patterns_discovered=[],
            pattern_confidence={},
            clustering_summary={"clusters_found": 0, "method": "basic"},
            recommendations=["Enable ML analysis for enhanced pattern discovery"]
        )
        
        # Create required validation summary
        validation_summary = ValidationSummary(
            is_valid=True,
            issues_found=[],
            warnings=[],
            suggestions=[],
            preprocessing_applied=getattr(self, '_current_state', {}).get('environmental_context', {}).get('preprocessing_applied', False),
            detected_language=getattr(self, '_current_state', {}).get('environmental_context', {}).get('language', 'en'),
            detected_platform=getattr(self, '_current_state', {}).get('environmental_context', {}).get('platform', 'unknown')
        )
        
        return ComprehensiveLogAnalysisOutput(
            overall_summary=overall_summary,
            health_status=health_status,
            priority_concerns=[issue.get("category", "unknown") for issue in issues[:3] if issue.get("severity") == "High"],
            system_metadata=system_metadata,
            environmental_context=environmental_context,
            identified_issues=detailed_issues,
            issue_summary_by_severity={
                "High": high_severity_count,
                "Medium": medium_severity_count,
                "Low": low_severity_count
            },
            correlation_analysis=correlation_analysis,
            dependency_analysis=dependency_analysis,
            predictive_insights=predictive_insights,
            ml_pattern_discovery=ml_pattern_discovery,
            proposed_solutions=comprehensive_solutions,
            supplemental_research=ResearchRecommendation(
                rationale="Additional research recommended for complex issues",
                recommended_queries=[f"Mailbird {system_metadata.mailbird_version} troubleshooting"],
                research_priority="Medium",
                expected_information="Version-specific fixes and updates"
            ) if any(check_requires_web_search(solution) for solution in solutions) else None,
            analysis_metrics=analysis_metrics,
            validation_summary=validation_summary,
            immediate_actions=immediate_actions,
            preventive_measures=preventive_measures,
            monitoring_recommendations=monitoring_recommendations,
            automated_remediation_available=self.enable_automated_remediation
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
        
        # Create required fields for error report
        environmental_context = EnvironmentalContext(
            os_version="unknown",
            platform="unknown",
            antivirus_software=[],
            firewall_status="unknown",
            network_type="unknown",
            proxy_configured=False,
            system_locale="en-US", 
            timezone="UTC"
        )
        
        correlation_analysis = CorrelationAnalysis(
            temporal_correlations=[],
            account_correlations=[],
            issue_type_correlations=[],
            correlation_matrix={},
            analysis_summary={"status": "error", "correlations_found": 0}
        )
        
        dependency_analysis = DependencyAnalysis(
            graph_summary={"total_nodes": 0, "total_edges": 0},
            root_causes=[],
            primary_symptoms=[],
            cyclical_dependencies=[],
            centrality_measures={},
            issue_relationships=[]
        )
        
        ml_pattern_discovery = MLPatternDiscovery(
            patterns_discovered=[],
            pattern_confidence={},
            clustering_summary={"clusters_found": 0, "method": "error"},
            recommendations=["Analysis failed - manual review required"]
        )
        
        validation_summary = ValidationSummary(
            is_valid=False,
            issues_found=["Analysis system error"],
            warnings=[str(error)],
            suggestions=["Contact technical support"],
            preprocessing_applied=False,
            detected_language="unknown",
            detected_platform="unknown"
        )
        
        return ComprehensiveLogAnalysisOutput(
            overall_summary=f"Log analysis failed due to system error: {error}",
            health_status="Unknown",
            priority_concerns=["Analysis system error"],
            system_metadata=system_metadata,
            environmental_context=environmental_context,
            identified_issues=[],
            issue_summary_by_severity={"High": 0, "Medium": 0, "Low": 0},
            correlation_analysis=correlation_analysis,
            dependency_analysis=dependency_analysis,
            predictive_insights=[],
            ml_pattern_discovery=ml_pattern_discovery,
            proposed_solutions=[],
            supplemental_research=ResearchRecommendation(
                rationale="Manual analysis required due to system error",
                recommended_queries=["Mailbird manual log analysis", "Mailbird support contact"],
                research_priority="High",
                expected_information="Professional technical support"
            ),
            analysis_metrics=analysis_metrics,
            validation_summary=validation_summary,
            immediate_actions=["Contact technical support with log file"],
            preventive_measures=["Ensure proper log file format"],
            monitoring_recommendations=["Monitor system resources during log analysis"],
            automated_remediation_available=False
        )

    async def _fallback_to_intelligent_analysis(self, parsed_data: Dict, preprocessed_content: str, error: Exception) -> List[Dict]:
        """Fallback to intelligent analysis when optimized analysis fails."""
        try:
            logger.info("fallback_to_intelligent_analysis", reason=str(error))
            print("Falling back to intelligent analysis...")
            
            # Use intelligent analyzer as fallback
            historical_data = []  # No historical data for fallback
            intelligent_analysis = await self.intelligent_analyzer.perform_intelligent_analysis(
                preprocessed_content,
                parsed_data,
                historical_data=historical_data
            )
            
            # Store the fallback analysis
            if hasattr(self, '_current_state'):
                self._current_state['intelligent_analysis'] = intelligent_analysis
            
            # Convert issues
            enhanced_issues = self._convert_enhanced_intelligent_issues_to_legacy_format(
                intelligent_analysis,
                parsed_data["detected_issues"]
            )
            
            return enhanced_issues
            
        except Exception as fallback_error:
            logger.error("intelligent_fallback_failed", error=str(fallback_error))
            return await self._fallback_to_basic_analysis(parsed_data, fallback_error)

    def _convert_enhanced_intelligent_issues_to_legacy_format(self, intelligent_analysis: Dict, fallback_issues: List[Dict]) -> List[Dict]:
        """Convert enhanced intelligent analysis issues to legacy format for compatibility."""
        try:
            converted_issues = []
            
            # Extract from account analysis
            account_analysis = intelligent_analysis.get('issues_analysis', {}).get('account_analysis', [])
            for account in account_analysis:
                for error_pattern in account.get('error_patterns', []):
                    issue = {
                        'issue_id': f"ai_{error_pattern.get('error_type', 'unknown').replace(' ', '_')}",
                        'category': error_pattern.get('error_type', 'Unknown').replace('_', ' ').title(),
                        'signature': error_pattern.get('error_type', ''),
                        'severity': account.get('issue_severity', 'Medium').title(),
                        'root_cause': f"Account-specific issue affecting {account.get('email_address', 'unknown account')}",
                        'user_impact': f"Affects {account.get('email_address', 'account')} with {error_pattern.get('frequency', 0)} occurrences",
                        'affected_accounts': [account.get('email_address', 'unknown')],
                        'occurrences': error_pattern.get('frequency', 1),
                        'confidence_score': 0.95,  # High confidence for intelligent analysis
                        'first_occurrence': error_pattern.get('first_occurrence'),
                        'last_occurrence': error_pattern.get('last_occurrence'),
                        'ai_generated': True,
                        'analysis_method': 'intelligent_enhanced'
                    }
                    converted_issues.append(issue)
            
            # Extract from technical patterns
            technical_patterns = intelligent_analysis.get('issues_analysis', {}).get('technical_patterns', [])
            for pattern in technical_patterns:
                issue = {
                    'issue_id': f"ai_pattern_{pattern.get('pattern_name', 'unknown').replace(' ', '_')}",
                    'category': pattern.get('pattern_name', 'Technical Pattern'),
                    'signature': pattern.get('technical_signature', ''),
                    'severity': 'High' if 'critical' in pattern.get('pattern_name', '').lower() else 'Medium',
                    'root_cause': pattern.get('root_cause', 'Pattern-based detection'),
                    'user_impact': pattern.get('impact_assessment', 'Technical impact detected'),
                    'affected_accounts': pattern.get('affected_accounts', []),
                    'occurrences': 1,  # Pattern-level occurrence
                    'frequency_pattern': pattern.get('frequency_analysis', 'Unknown'),
                    'confidence_score': 0.9,
                    'ai_generated': True,
                    'analysis_method': 'intelligent_pattern'
                }
                converted_issues.append(issue)
            
            # Extract from critical findings
            critical_findings = intelligent_analysis.get('issues_analysis', {}).get('critical_findings', [])
            for finding in critical_findings:
                issue = {
                    'issue_id': f"ai_critical_{finding.get('finding', 'unknown').replace(' ', '_')}",
                    'category': 'Critical Finding',
                    'signature': finding.get('finding', ''),
                    'severity': 'Critical',
                    'root_cause': finding.get('technical_details', 'Critical issue detected'),
                    'user_impact': finding.get('business_impact', 'Critical business impact'),
                    'affected_accounts': finding.get('affected_accounts', []),
                    'occurrences': len(finding.get('evidence', [])),
                    'confidence_score': 0.98,  # Very high confidence for critical findings
                    'ai_generated': True,
                    'analysis_method': 'intelligent_critical'
                }
                converted_issues.append(issue)
            
            return converted_issues if converted_issues else fallback_issues
            
        except Exception as e:
            logger.error("enhanced_intelligent_issues_conversion_failed", error=str(e))
            return fallback_issues

    def _convert_enhanced_intelligent_solutions_to_legacy_format(self, intelligent_solutions: List[Dict]) -> List[Dict]:
        """Convert enhanced intelligent solutions to legacy format for compatibility."""
        try:
            converted_solutions = []
            
            for solution in intelligent_solutions:
                # Handle both direct solutions and nested solution structures
                if isinstance(solution, dict):
                    # Convert enhanced solution format
                    converted_solution = {
                        'issue_id': solution.get('solution_id', solution.get('issue_id', 'unknown')),
                        'solution_summary': solution.get('title', solution.get('solution_summary', '')),
                        'priority': solution.get('priority', 'Medium'),
                        'implementation_timeline': solution.get('estimated_resolution_time', solution.get('implementation_timeline', 'Unknown')),
                        'success_probability': solution.get('success_probability', 'Medium'),
                        'solution_steps': self._convert_solution_steps(solution.get('implementation_steps', solution.get('solution_steps', []))),
                        'prerequisites': solution.get('prerequisites', []),
                        'estimated_total_time_minutes': self._extract_time_minutes(
                            solution.get('estimated_resolution_time', '15 minutes')
                        ),
                        'alternative_approaches': solution.get('alternative_approaches', []),
                        'expected_outcome': solution.get('expected_outcome', f"Resolves {solution.get('title', 'issue')}"),
                        'ai_generated': True,
                        'technical_notes': solution.get('technical_notes', ''),
                        'success_metrics': solution.get('success_metrics', []),
                        'risks': solution.get('risks', []),
                        'correlation_insights': solution.get('correlation_insights', []),
                        'predictive_actions': solution.get('predictive_actions', [])
                    }
                    converted_solutions.append(converted_solution)
            
            return converted_solutions
            
        except Exception as e:
            logger.error("enhanced_intelligent_solutions_conversion_failed", error=str(e))
            return []

    def _convert_solution_steps(self, steps: List) -> List[Dict]:
        """Convert solution steps to consistent format."""
        converted_steps = []
        
        for i, step in enumerate(steps):
            if isinstance(step, dict):
                converted_step = {
                    'step_number': step.get('step_number', i + 1),
                    'description': step.get('action', step.get('description', 'No description')),
                    'expected_outcome': step.get('expected_outcome', step.get('expected_result', 'Complete step')),
                    'troubleshooting_note': step.get('troubleshooting_note', ''),
                    'estimated_time_minutes': step.get('estimated_time', step.get('estimated_time_minutes', 5))
                }
            else:
                # Handle string or other formats
                converted_step = {
                    'step_number': i + 1,
                    'description': str(step),
                    'expected_outcome': 'Complete step successfully',
                    'troubleshooting_note': '',
                    'estimated_time_minutes': 5
                }
            
            converted_steps.append(converted_step)
        
        return converted_steps

    async def _add_automation_capabilities(self, solutions: List[Dict]) -> List[Dict]:
        """Add automation capabilities to solutions when enabled."""
        try:
            enhanced_solutions = []
            
            for solution in solutions:
                # Add automation fields
                enhanced_solution = solution.copy()
                enhanced_solution.update({
                    'automation_available': True,
                    'can_auto_execute': False,  # Conservative default
                    'validation_commands': [],
                    'rollback_procedures': [],
                    'safety_checks': ['Manual review required before execution']
                })
                
                # Analyze solution steps for automation potential
                steps = solution.get('solution_steps', [])
                automated_steps = []
                
                for step in steps:
                    step_dict = step if isinstance(step, dict) else {'description': str(step)}
                    
                    # Check if step can be automated safely
                    description = step_dict.get('description', '').lower()
                    if any(safe_keyword in description for safe_keyword in ['check', 'verify', 'view', 'review']):
                        step_dict['can_automate'] = True
                        step_dict['automation_risk'] = 'Low'
                    else:
                        step_dict['can_automate'] = False
                        step_dict['automation_risk'] = 'High'
                    
                    automated_steps.append(step_dict)
                
                enhanced_solution['solution_steps'] = automated_steps
                enhanced_solutions.append(enhanced_solution)
            
            return enhanced_solutions
            
        except Exception as e:
            logger.error("automation_enhancement_failed", error=str(e))
            return solutions


# Main entry point function
async def run_enhanced_log_analysis_agent(state: EnhancedLogAnalysisAgentState) -> Dict[str, Any]:
    """
    Main entry point for the enhanced log analysis agent.
    """
    agent = EnhancedLogAnalysisAgent()
    return await agent.analyze_logs(state)