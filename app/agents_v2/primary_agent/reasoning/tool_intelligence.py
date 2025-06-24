"""
Agent Sparrow - Tool Intelligence System

This module implements sophisticated tool usage decisions with reasoning transparency,
providing intelligent recommendations for when and how to use different tools based
on query analysis and context assessment.
"""

import logging
import re
from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime, timedelta

from .schemas import (
    QueryAnalysis,
    SolutionCandidate,
    ToolDecisionReasoning,
    ToolDecisionType,
    ProblemCategory,
    ReasoningConfig
)
from app.agents_v2.primary_agent.prompts.emotion_templates import EmotionalState

logger = logging.getLogger(__name__)


class ToolIntelligence:
    """
    Sophisticated tool decision engine for Agent Sparrow
    
    Implements enhanced decision logic for determining optimal tool usage:
    - Temporal awareness for current information needs
    - Confidence-based fallback strategies
    - Context-aware tool selection
    - Reasoning transparency and explanation
    """
    
    def __init__(self, config: ReasoningConfig):
        """
        Initialize tool intelligence system
        
        Args:
            config: Reasoning configuration
        """
        self.config = config
        
        # Tool decision patterns and heuristics
        self.temporal_indicators = [
            'current', 'latest', 'recent', 'today', 'now', 'updated',
            'new', 'current status', 'right now', 'at the moment'
        ]
        
        self.error_code_patterns = [
            r'error\s*\d+',
            r'code\s*\d+', 
            r'exception\s*\d+',
            r'0x[0-9a-fA-F]+',
            r'HTTP\s*\d{3}'
        ]
        
        self.external_service_indicators = [
            'gmail', 'google', 'outlook', 'microsoft', 'yahoo', 'icloud',
            'office365', 'exchange', 'server status', 'downtime', 'maintenance'
        ]
        
        # Knowledge confidence thresholds
        self.high_confidence_threshold = 0.8
        self.medium_confidence_threshold = 0.6
        self.low_confidence_threshold = 0.4
    
    async def decide_tool_usage(
        self,
        query_analysis: QueryAnalysis,
        solution_candidates: Optional[List[SolutionCandidate]] = None
    ) -> ToolDecisionReasoning:
        """
        Make intelligent tool usage decision with detailed reasoning
        
        Args:
            query_analysis: Analysis of the customer query
            solution_candidates: Optional list of solution candidates
            
        Returns:
            Detailed tool decision with reasoning
        """
        
        # Initialize decision reasoning
        reasoning_factors = []
        confidence_factors = []
        required_information = []
        temporal_factors = []
        knowledge_gaps = []
        
        # 1. Temporal Analysis
        temporal_decision = self._analyze_temporal_needs(query_analysis)
        if temporal_decision['needs_current_info']:
            reasoning_factors.append("Query requires current/real-time information")
            temporal_factors.extend(temporal_decision['indicators'])
            required_information.extend(temporal_decision['info_needed'])
            confidence_factors.append(0.9)
        
        # 2. Error Code Analysis
        error_decision = self._analyze_error_codes(query_analysis)
        if error_decision['has_specific_errors']:
            if error_decision['known_errors']:
                reasoning_factors.append("Contains known error codes that can be resolved internally")
                confidence_factors.append(0.8)
            else:
                reasoning_factors.append("Contains unknown error codes requiring external research")
                knowledge_gaps.extend(error_decision['unknown_errors'])
                required_information.append("Error code documentation and resolution guides")
                confidence_factors.append(0.7)
        
        # 3. External Service Analysis
        external_decision = self._analyze_external_services(query_analysis)
        if external_decision['involves_external_services']:
            reasoning_factors.append("Query involves external email providers requiring current policy information")
            required_information.extend(external_decision['services'])
            confidence_factors.append(0.8)
        
        # 4. Problem Category Analysis
        category_decision = self._analyze_problem_category(query_analysis)
        reasoning_factors.extend(category_decision['reasoning'])
        confidence_factors.extend(category_decision['confidence_factors'])
        required_information.extend(category_decision['info_needed'])
        
        # 5. Emotional State Analysis
        emotion_decision = self._analyze_emotional_urgency(query_analysis)
        if emotion_decision['requires_immediate_response']:
            reasoning_factors.append("Emotional state requires immediate response with available information")
            confidence_factors.append(0.6)
        
        # 6. Solution Candidate Analysis
        solution_decision = self._analyze_solution_confidence(solution_candidates)
        reasoning_factors.extend(solution_decision['reasoning'])
        confidence_factors.extend(solution_decision['confidence_factors'])
        knowledge_gaps.extend(solution_decision['gaps'])
        
        # Make final decision based on analysis
        decision_type, final_reasoning = self._make_final_decision(
            reasoning_factors, confidence_factors, required_information, 
            temporal_factors, knowledge_gaps, query_analysis
        )
        
        # Calculate overall confidence
        overall_confidence = sum(confidence_factors) / len(confidence_factors) if confidence_factors else 0.5
        
        # Generate search strategy if web search is needed
        search_strategy = None
        expected_sources = []
        if decision_type in [ToolDecisionType.WEB_SEARCH_REQUIRED, ToolDecisionType.BOTH_SOURCES_NEEDED]:
            search_strategy = self._generate_search_strategy(query_analysis, required_information)
            expected_sources = self._identify_expected_sources(query_analysis, required_information)
        
        return ToolDecisionReasoning(
            decision_type=decision_type,
            reasoning=final_reasoning,
            confidence=overall_confidence,
            required_information=required_information,
            temporal_factors=temporal_factors,
            knowledge_gaps=knowledge_gaps,
            search_strategy=search_strategy,
            expected_sources=expected_sources
        )
    
    def _analyze_temporal_needs(self, query_analysis: QueryAnalysis) -> Dict[str, Any]:
        """Analyze if query requires current/temporal information"""
        query_text = query_analysis.query_text.lower()
        
        temporal_indicators_found = []
        for indicator in self.temporal_indicators:
            if indicator in query_text:
                temporal_indicators_found.append(indicator)
        
        needs_current_info = len(temporal_indicators_found) > 0
        
        info_needed = []
        if needs_current_info:
            if any(word in query_text for word in ['status', 'down', 'working']):
                info_needed.append("Current service status")
            if any(word in query_text for word in ['version', 'update', 'latest']):
                info_needed.append("Latest version information")
            if any(word in query_text for word in ['price', 'cost', 'plan']):
                info_needed.append("Current pricing information")
        
        return {
            'needs_current_info': needs_current_info,
            'indicators': temporal_indicators_found,
            'info_needed': info_needed
        }
    
    def _analyze_error_codes(self, query_analysis: QueryAnalysis) -> Dict[str, Any]:
        """Analyze error codes in the query"""
        query_text = query_analysis.query_text
        
        error_codes = []
        for pattern in self.error_code_patterns:
            matches = re.findall(pattern, query_text, re.IGNORECASE)
            error_codes.extend(matches)
        
        # Simulate known vs unknown errors (in real implementation, this would check against KB)
        known_errors = []
        unknown_errors = []
        
        for error in error_codes:
            # This is a simplified heuristic - real implementation would check against knowledge base
            if any(common in error.lower() for common in ['404', '500', '401', '403', 'timeout', 'connection']):
                known_errors.append(error)
            else:
                unknown_errors.append(error)
        
        return {
            'has_specific_errors': len(error_codes) > 0,
            'known_errors': known_errors,
            'unknown_errors': unknown_errors,
            'all_errors': error_codes
        }
    
    def _analyze_external_services(self, query_analysis: QueryAnalysis) -> Dict[str, Any]:
        """Analyze external service involvement"""
        query_text = query_analysis.query_text.lower()
        
        involved_services = []
        for service in self.external_service_indicators:
            if service in query_text:
                involved_services.append(service)
        
        # Check for policy/authentication related queries
        policy_related = any(word in query_text for word in [
            'authentication', 'oauth', 'permission', 'blocked', 'security',
            'two-factor', '2fa', 'app password', 'less secure'
        ])
        
        return {
            'involves_external_services': len(involved_services) > 0 or policy_related,
            'services': involved_services,
            'policy_related': policy_related
        }
    
    def _analyze_problem_category(self, query_analysis: QueryAnalysis) -> Dict[str, Any]:
        """Analyze problem category implications for tool usage"""
        category = query_analysis.problem_category
        reasoning = []
        confidence_factors = []
        info_needed = []
        
        if category == ProblemCategory.TECHNICAL_ISSUE:
            if query_analysis.complexity_score > 0.7:
                reasoning.append("Complex technical issue may require external troubleshooting resources")
                info_needed.append("Advanced troubleshooting guides")
                confidence_factors.append(0.7)
            else:
                reasoning.append("Standard technical issue likely covered in internal knowledge base")
                confidence_factors.append(0.8)
        
        elif category == ProblemCategory.ACCOUNT_SETUP:
            reasoning.append("Account setup queries may need current provider authentication requirements")
            info_needed.append("Current OAuth and authentication procedures")
            confidence_factors.append(0.6)
        
        elif category == ProblemCategory.BILLING_INQUIRY:
            reasoning.append("Billing questions require most current pricing and policy information")
            info_needed.append("Current pricing plans and billing policies")
            confidence_factors.append(0.9)  # High need for current info
        
        elif category == ProblemCategory.FEATURE_EDUCATION:
            reasoning.append("Feature education typically well-covered in internal documentation")
            confidence_factors.append(0.9)  # High confidence in internal knowledge
        
        else:
            reasoning.append("General support query with moderate external information needs")
            confidence_factors.append(0.6)
        
        return {
            'reasoning': reasoning,
            'confidence_factors': confidence_factors,
            'info_needed': info_needed
        }
    
    def _analyze_emotional_urgency(self, query_analysis: QueryAnalysis) -> Dict[str, Any]:
        """Analyze emotional urgency factors"""
        emotion = query_analysis.emotional_state
        urgency = query_analysis.urgency_level
        
        immediate_response_emotions = [
            EmotionalState.URGENT, EmotionalState.ANXIOUS, EmotionalState.FRUSTRATED
        ]
        
        requires_immediate = (
            emotion in immediate_response_emotions or 
            urgency >= 4
        )
        
        return {
            'requires_immediate_response': requires_immediate,
            'emotion': emotion,
            'urgency_level': urgency
        }
    
    def _analyze_solution_confidence(self, solution_candidates: Optional[List[SolutionCandidate]]) -> Dict[str, Any]:
        """Analyze confidence in available solutions"""
        reasoning = []
        confidence_factors = []
        gaps = []
        
        if not solution_candidates:
            reasoning.append("No solution candidates available - external research needed")
            confidence_factors.append(0.3)
            gaps.append("Complete solution approach")
            return {
                'reasoning': reasoning,
                'confidence_factors': confidence_factors,
                'gaps': gaps
            }
        
        # Analyze solution quality
        avg_confidence = sum(sol.confidence_score for sol in solution_candidates) / len(solution_candidates)
        
        if avg_confidence >= self.high_confidence_threshold:
            reasoning.append("High confidence solutions available internally")
            confidence_factors.append(0.9)
        elif avg_confidence >= self.medium_confidence_threshold:
            reasoning.append("Moderate confidence solutions available, may benefit from external validation")
            confidence_factors.append(0.6)
            gaps.append("Solution validation and additional approaches")
        else:
            reasoning.append("Low confidence solutions - external research strongly recommended")
            confidence_factors.append(0.3)
            gaps.append("Alternative solution approaches")
        
        # Check for incomplete solutions
        incomplete_solutions = [sol for sol in solution_candidates if len(sol.detailed_approach) < 50]
        if incomplete_solutions:
            reasoning.append(f"{len(incomplete_solutions)} solutions lack sufficient detail")
            gaps.append("Detailed implementation steps")
        
        return {
            'reasoning': reasoning,
            'confidence_factors': confidence_factors,
            'gaps': gaps
        }
    
    def _make_final_decision(
        self,
        reasoning_factors: List[str],
        confidence_factors: List[float],
        required_information: List[str],
        temporal_factors: List[str],
        knowledge_gaps: List[str],
        query_analysis: QueryAnalysis
    ) -> Tuple[ToolDecisionType, str]:
        """Make final tool usage decision"""
        
        # Calculate decision weights
        needs_external_info = len(temporal_factors) > 0 or len(knowledge_gaps) > 0
        has_confidence_gaps = any(cf < self.medium_confidence_threshold for cf in confidence_factors)
        is_urgent = query_analysis.urgency_level >= 4
        
        # Decision logic
        if needs_external_info and has_confidence_gaps:
            decision = ToolDecisionType.BOTH_SOURCES_NEEDED
            reasoning = (
                f"Both internal knowledge base and web search required. "
                f"Identified {len(temporal_factors)} temporal factors and {len(knowledge_gaps)} knowledge gaps. "
                f"Will combine internal expertise with current external information."
            )
        
        elif needs_external_info:
            if is_urgent:
                decision = ToolDecisionType.BOTH_SOURCES_NEEDED
                reasoning = (
                    f"Urgent query requiring external information. "
                    f"Will prioritize speed by combining internal knowledge with targeted web search."
                )
            else:
                decision = ToolDecisionType.WEB_SEARCH_REQUIRED
                reasoning = (
                    f"External information required for optimal response. "
                    f"Web search needed for: {', '.join(required_information[:3])}."
                )
        
        elif has_confidence_gaps:
            avg_confidence = sum(confidence_factors) / len(confidence_factors)
            if avg_confidence < self.low_confidence_threshold:
                decision = ToolDecisionType.WEB_SEARCH_REQUIRED
                reasoning = (
                    f"Low confidence in internal knowledge (avg: {avg_confidence:.2f}). "
                    f"Web search recommended to provide accurate information."
                )
            else:
                decision = ToolDecisionType.INTERNAL_KB_ONLY
                reasoning = (
                    f"Sufficient internal knowledge available (confidence: {avg_confidence:.2f}). "
                    f"Internal knowledge base can provide comprehensive response."
                )
        
        else:
            # High confidence, no external needs
            decision = ToolDecisionType.INTERNAL_KB_ONLY
            reasoning = (
                f"Internal knowledge base sufficient for comprehensive response. "
                f"High confidence in available information and solution approaches."
            )
        
        # Special case: escalation needed
        if query_analysis.complexity_score > 0.9 and any(cf < 0.3 for cf in confidence_factors):
            decision = ToolDecisionType.ESCALATION_REQUIRED
            reasoning = (
                f"Highly complex query with very low confidence levels. "
                f"Human expert consultation recommended for optimal resolution."
            )
        
        return decision, reasoning
    
    def _generate_search_strategy(self, query_analysis: QueryAnalysis, required_information: List[str]) -> str:
        """Generate targeted search strategy"""
        search_terms = []
        
        # Add core entities
        search_terms.extend(query_analysis.key_entities)
        
        # Add problem-specific terms
        if query_analysis.problem_category == ProblemCategory.TECHNICAL_ISSUE:
            search_terms.extend(["troubleshooting", "fix", "resolve"])
        elif query_analysis.problem_category == ProblemCategory.BILLING_INQUIRY:
            search_terms.extend(["pricing", "cost", "billing"])
        
        # Add temporal modifiers if needed
        if any("current" in info for info in required_information):
            search_terms.append("2024")
        
        strategy = f"Target search terms: {', '.join(search_terms[:5])}. "
        
        if query_analysis.urgency_level >= 4:
            strategy += "Prioritize recent, authoritative sources. "
        
        if query_analysis.complexity_score > 0.7:
            strategy += "Include technical documentation and detailed guides."
        
        return strategy
    
    def _identify_expected_sources(self, query_analysis: QueryAnalysis, required_information: List[str]) -> List[str]:
        """Identify expected source types for information"""
        expected_sources = []
        
        # Official documentation
        if query_analysis.problem_category in [ProblemCategory.FEATURE_EDUCATION, ProblemCategory.ACCOUNT_SETUP]:
            expected_sources.append("Official Mailbird documentation")
        
        # Provider documentation
        if any("gmail" in entity for entity in query_analysis.key_entities):
            expected_sources.append("Google Support documentation")
        if any("outlook" in entity for entity in query_analysis.key_entities):
            expected_sources.append("Microsoft Support documentation")
        
        # Technical resources
        if query_analysis.problem_category == ProblemCategory.TECHNICAL_ISSUE:
            expected_sources.extend(["Technical forums", "Troubleshooting guides"])
        
        # Pricing/billing
        if query_analysis.problem_category == ProblemCategory.BILLING_INQUIRY:
            expected_sources.append("Official pricing pages")
        
        # Current status information
        if any("status" in info for info in required_information):
            expected_sources.append("Service status pages")
        
        return expected_sources