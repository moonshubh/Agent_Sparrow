"""
Agent Sparrow - Core Reasoning Engine

This module implements the sophisticated reasoning engine that powers Agent Sparrow's
advanced decision-making capabilities with chain-of-thought processing, multi-step
problem solving, and intelligent tool usage decisions.
"""

import logging
import time
from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime
import asyncio
import re

from langchain_core.messages import BaseMessage, HumanMessage
from opentelemetry import trace

from .schemas import (
    ReasoningState,
    ReasoningStep,
    ReasoningPhase,
    QueryAnalysis,
    SolutionCandidate,
    ToolDecisionReasoning,
    QualityAssessment,
    ProblemCategory,
    ToolDecisionType,
    ConfidenceLevel,
    ReasoningConfig
)
from .problem_solver import ProblemSolvingFramework
from .tool_intelligence import ToolIntelligence
from app.agents_v2.primary_agent.prompts import EmotionTemplates
from app.agents_v2.primary_agent.prompts.emotion_templates import EmotionalState

logger = logging.getLogger(__name__)
tracer = trace.get_tracer(__name__)


class ReasoningEngine:
    """
    Sophisticated reasoning engine for Agent Sparrow
    
    Implements advanced cognitive processes:
    - Chain-of-thought reasoning with transparency
    - Multi-step problem solving framework
    - Intelligent tool usage decisions
    - Quality assessment and validation
    - Emotional intelligence integration
    """
    
    def __init__(self, config: Optional[ReasoningConfig] = None):
        """
        Initialize the ReasoningEngine with optional configuration.
        
        If no configuration is provided, a default ReasoningConfig is used. Instantiates the problem-solving and tool intelligence components required for the reasoning process.
        """
        self.config = config or ReasoningConfig()
        self.problem_solver = ProblemSolvingFramework(self.config)
        self.tool_intelligence = ToolIntelligence(self.config)
        
    async def reason_about_query(
        self, 
        query: str, 
        context: Optional[Dict[str, Any]] = None,
        session_id: str = "default"
    ) -> ReasoningState:
        """
        Executes the full multi-phase reasoning pipeline to analyze a customer query and generate a comprehensive reasoning state.
        
        This method orchestrates advanced cognitive processes including query analysis, context recognition, solution mapping, tool usage assessment, response strategy development, and quality evaluation. It integrates emotional and contextual understanding, problem categorization, and quality control, returning a detailed reasoning state with confidence scores, recommendations, and escalation flags if needed.
        
        Parameters:
            query (str): The customer query text to be analyzed.
            context (Optional[Dict[str, Any]]): Optional contextual information relevant to the query.
            session_id (str): Identifier for the reasoning session.
        
        Returns:
            ReasoningState: The complete reasoning state containing analysis results, recommendations, confidence metrics, and escalation indicators.
        """
        with tracer.start_as_current_span("reasoning_engine.reason_about_query") as span:
            start_time = time.time()
            
            # Initialize reasoning state
            reasoning_state = ReasoningState(session_id=session_id, start_time=datetime.now())
            span.set_attribute("session_id", session_id)
            span.set_attribute("query_length", len(query))
            
            try:
                # Phase 1: Query Analysis
                if self.config.enable_chain_of_thought:
                    await self._analyze_query(query, reasoning_state, context)
                    span.set_attribute("emotion_detected", reasoning_state.query_analysis.emotional_state.value)
                    span.set_attribute("problem_category", reasoning_state.query_analysis.problem_category.value)
                
                # Phase 2: Context Recognition
                await self._recognize_context(reasoning_state, context)
                
                # Phase 3: Solution Mapping
                if self.config.enable_problem_solving_framework:
                    await self._map_solutions(reasoning_state)
                    span.set_attribute("solution_candidates", len(reasoning_state.solution_candidates))
                
                # Phase 4: Tool Assessment
                if self.config.enable_tool_intelligence:
                    await self._assess_tool_needs(reasoning_state)
                    span.set_attribute("tool_decision", reasoning_state.tool_reasoning.decision_type.value)
                
                # Phase 5: Response Strategy
                await self._develop_response_strategy(reasoning_state)
                
                # Phase 6: Quality Assessment
                if self.config.enable_quality_assessment:
                    await self._assess_quality(reasoning_state)
                    span.set_attribute("quality_score", reasoning_state.quality_assessment.overall_quality_score)
                
                # Finalize reasoning
                await self._finalize_reasoning(reasoning_state, start_time)
                span.set_attribute("reasoning_confidence", reasoning_state.overall_confidence)
                span.set_attribute("processing_time", reasoning_state.total_processing_time)
                
                logger.info(f"Reasoning completed for session {session_id}: "
                          f"confidence={reasoning_state.overall_confidence:.2f}, "
                          f"time={reasoning_state.total_processing_time:.2f}s")
                
                return reasoning_state
                
            except Exception as e:
                logger.error(f"Reasoning engine error for session {session_id}: {e}")
                span.record_exception(e)
                
                # Create fallback reasoning state
                reasoning_state.escalation_reasons.append(f"Reasoning engine error: {str(e)}")
                reasoning_state.requires_human_review = True
                reasoning_state.overall_confidence = 0.2
                
                return reasoning_state
    
    async def _analyze_query(
        self, 
        query: str, 
        reasoning_state: ReasoningState, 
        context: Optional[Dict[str, Any]]
    ) -> None:
        """
        Performs comprehensive analysis of the customer query, extracting emotional state, problem category, urgency, complexity, key entities, inferred intent, and contextual clues.
        
        Updates the reasoning state with a detailed query analysis and records a reasoning step summarizing the findings.
        """
        with tracer.start_as_current_span("reasoning_engine.analyze_query"):
            
            # Detect emotional state
            emotion_result = EmotionTemplates.detect_emotion(query)
            
            # Analyze problem category
            problem_category, category_confidence = self._categorize_problem(query)
            
            # Assess urgency and complexity
            urgency_level = self._assess_urgency(query, emotion_result.primary_emotion)
            complexity_score = self._assess_complexity(query)
            
            # Extract key entities and intent
            key_entities = self._extract_entities(query)
            inferred_intent = self._infer_intent(query, problem_category)
            context_clues = self._extract_context_clues(query, context)
            
            # Create query analysis
            reasoning_state.query_analysis = QueryAnalysis(
                query_text=query,
                emotional_state=emotion_result.primary_emotion,
                emotion_confidence=emotion_result.confidence_score,
                problem_category=problem_category,
                category_confidence=category_confidence,
                urgency_level=urgency_level,
                complexity_score=complexity_score,
                key_entities=key_entities,
                inferred_intent=inferred_intent,
                context_clues=context_clues
            )
            
            # Add reasoning step
            step = ReasoningStep(
                phase=ReasoningPhase.QUERY_ANALYSIS,
                description="Analyzed customer query for emotional state, problem category, and complexity",
                reasoning=f"Detected {emotion_result.primary_emotion.value} emotion (conf: {emotion_result.confidence_score:.2f}), "
                         f"categorized as {problem_category.value} (conf: {category_confidence:.2f}), "
                         f"urgency level {urgency_level}/5, complexity {complexity_score:.2f}",
                confidence=min(emotion_result.confidence_score, category_confidence),
                evidence=[
                    f"Emotional indicators: {', '.join(emotion_result.detected_indicators)}",
                    f"Key entities: {', '.join(key_entities)}",
                    f"Intent signals: {inferred_intent}"
                ]
            )
            reasoning_state.add_reasoning_step(step)
    
    async def _recognize_context(
        self, 
        reasoning_state: ReasoningState, 
        context: Optional[Dict[str, Any]]
    ) -> None:
        """
        Analyzes and enriches the reasoning state with contextual insights and confidence factors based on provided context and query analysis.
        
        This phase identifies relevant situational factors such as previous conversation history, user profile, system state, emotional urgency, problem category, and entity complexity. It computes an overall context confidence score and records a reasoning step summarizing the context recognition process.
        """
        with tracer.start_as_current_span("reasoning_engine.recognize_context"):
            
            context_insights = []
            confidence_factors = []
            
            # Analyze provided context
            if context:
                if 'previous_messages' in context:
                    context_insights.append("Previous conversation context available")
                    confidence_factors.append(0.8)
                
                if 'user_profile' in context:
                    context_insights.append("User profile information available")
                    confidence_factors.append(0.7)
                
                if 'system_state' in context:
                    context_insights.append("System state information available")
                    confidence_factors.append(0.6)
            
            # Infer additional context from query analysis
            if reasoning_state.query_analysis:
                qa = reasoning_state.query_analysis
                
                if qa.emotional_state in [EmotionalState.URGENT, EmotionalState.ANXIOUS]:
                    context_insights.append("Time-sensitive situation requiring immediate attention")
                    confidence_factors.append(0.9)
                
                if qa.problem_category == ProblemCategory.TECHNICAL_ISSUE:
                    context_insights.append("Technical troubleshooting context required")
                    confidence_factors.append(0.8)
                
                if len(qa.key_entities) > 3:
                    context_insights.append("Complex multi-entity problem")
                    confidence_factors.append(0.7)
            
            # Calculate context confidence
            context_confidence = sum(confidence_factors) / len(confidence_factors) if confidence_factors else 0.5
            
            # Add reasoning step
            step = ReasoningStep(
                phase=ReasoningPhase.CONTEXT_RECOGNITION,
                description="Analyzed available context and situational factors",
                reasoning=f"Identified {len(context_insights)} relevant context factors. "
                         f"Context richness supports confidence level of {context_confidence:.2f}",
                confidence=context_confidence,
                evidence=context_insights
            )
            reasoning_state.add_reasoning_step(step)
    
    async def _map_solutions(self, reasoning_state: ReasoningState) -> None:
        """
        Generates and selects solution candidates for the analyzed query using the problem-solving framework.
        
        This phase creates potential solutions based on the query analysis attributes, selects the most confident solution if available, and records the process as a reasoning step in the reasoning state.
        """
        with tracer.start_as_current_span("reasoning_engine.map_solutions"):
            
            if not reasoning_state.query_analysis:
                return
                
            qa = reasoning_state.query_analysis
            
            # Use problem solving framework to generate solutions
            solutions = await self.problem_solver.generate_solution_candidates(
                problem_category=qa.problem_category,
                emotional_state=qa.emotional_state,
                urgency_level=qa.urgency_level,
                complexity_score=qa.complexity_score,
                key_entities=qa.key_entities,
                query_text=qa.query_text
            )
            
            reasoning_state.solution_candidates = solutions
            
            # Select best solution
            if solutions:
                # Sort by confidence and select highest
                best_solution = max(solutions, key=lambda s: s.confidence_score)
                reasoning_state.selected_solution = best_solution
            
            # Add reasoning step
            step = ReasoningStep(
                phase=ReasoningPhase.SOLUTION_MAPPING,
                description=f"Generated {len(solutions)} solution candidates",
                reasoning=f"Mapped problem to {len(solutions)} potential solutions. "
                         f"Selected solution with confidence {reasoning_state.selected_solution.confidence_score:.2f}" 
                         if reasoning_state.selected_solution else "No viable solutions identified",
                confidence=reasoning_state.selected_solution.confidence_score if reasoning_state.selected_solution else 0.2,
                evidence=[f"Solution: {s.solution_summary}" for s in solutions[:3]]  # Top 3
            )
            reasoning_state.add_reasoning_step(step)
    
    async def _assess_tool_needs(self, reasoning_state: ReasoningState) -> None:
        """
        Evaluates whether external tools are needed to address the query and records the tool usage decision in the reasoning state.
        
        This phase uses tool intelligence to analyze the query and solution candidates, determines the necessity and type of tool usage, and documents the decision along with confidence, evidence, and considered alternatives in the reasoning process.
        """
        with tracer.start_as_current_span("reasoning_engine.assess_tool_needs"):
            
            if not reasoning_state.query_analysis:
                return
                
            # Use tool intelligence to make decisions
            tool_reasoning = await self.tool_intelligence.decide_tool_usage(
                query_analysis=reasoning_state.query_analysis,
                solution_candidates=reasoning_state.solution_candidates
            )
            
            reasoning_state.tool_reasoning = tool_reasoning
            
            # Add reasoning step
            step = ReasoningStep(
                phase=ReasoningPhase.TOOL_ASSESSMENT,
                description="Analyzed tool requirements for optimal response",
                reasoning=tool_reasoning.reasoning,
                confidence=tool_reasoning.confidence,
                evidence=tool_reasoning.required_information,
                alternatives_considered=[dt.value for dt in ToolDecisionType if dt != tool_reasoning.decision_type]
            )
            reasoning_state.add_reasoning_step(step)
    
    async def _develop_response_strategy(self, reasoning_state: ReasoningState) -> None:
        """
        Constructs a comprehensive response strategy by integrating emotional state, urgency, complexity, tool decisions, and solution attributes into actionable guidance for customer interaction.
        
        The strategy adapts tone, structure, and content to the customer's emotional and situational context, and is recorded in the reasoning state for downstream use.
        """
        with tracer.start_as_current_span("reasoning_engine.develop_response_strategy"):
            
            strategy_elements = []
            
            if reasoning_state.query_analysis:
                qa = reasoning_state.query_analysis
                
                # Emotional adaptation
                if qa.emotional_state == EmotionalState.FRUSTRATED:
                    strategy_elements.append("Lead with sincere apology and immediate action plan")
                elif qa.emotional_state == EmotionalState.CONFUSED:
                    strategy_elements.append("Use step-by-step educational approach with simple language")
                elif qa.emotional_state == EmotionalState.ANXIOUS:
                    strategy_elements.append("Provide immediate reassurance followed by quick resolution")
                elif qa.emotional_state == EmotionalState.PROFESSIONAL:
                    strategy_elements.append("Match professional tone with comprehensive technical details")
                
                # Urgency adaptation
                if qa.urgency_level >= 4:
                    strategy_elements.append("Prioritize quick fix before detailed solution")
                
                # Complexity adaptation
                if qa.complexity_score > 0.7:
                    strategy_elements.append("Break down solution into manageable phases")
            
            # Tool-based strategy
            if reasoning_state.tool_reasoning:
                tr = reasoning_state.tool_reasoning
                if tr.decision_type == ToolDecisionType.WEB_SEARCH_REQUIRED:
                    strategy_elements.append("Enhance response with current information from web search")
                elif tr.decision_type == ToolDecisionType.INTERNAL_KB_ONLY:
                    strategy_elements.append("Leverage internal knowledge base for comprehensive response")
            
            # Solution-based strategy
            if reasoning_state.selected_solution:
                sol = reasoning_state.selected_solution
                if sol.estimated_time_minutes <= 5:
                    strategy_elements.append("Focus on immediate resolution")
                else:
                    strategy_elements.append("Provide timeline expectations and progress checkpoints")
            
            reasoning_state.response_strategy = " | ".join(strategy_elements)
            
            # Add reasoning step
            step = ReasoningStep(
                phase=ReasoningPhase.RESPONSE_STRATEGY,
                description="Developed comprehensive response strategy",
                reasoning=f"Crafted multi-faceted response strategy incorporating emotional intelligence, "
                         f"urgency handling, and solution complexity. Strategy includes {len(strategy_elements)} key elements.",
                confidence=0.8,  # High confidence in strategy development
                evidence=strategy_elements
            )
            reasoning_state.add_reasoning_step(step)
    
    async def _assess_quality(self, reasoning_state: ReasoningState) -> None:
        """
        Evaluates the quality of the reasoning process across multiple dimensions and updates the reasoning state with assessment results.
        
        Assesses reasoning clarity, solution completeness, emotional appropriateness, technical accuracy, and response structure, computes an overall quality score, and generates improvement suggestions and quality issues if thresholds are not met. Flags the reasoning state for human review if the overall quality score falls below the configured threshold.
        """
        with tracer.start_as_current_span("reasoning_engine.assess_quality"):
            
            # Assess different quality dimensions
            reasoning_clarity = self._assess_reasoning_clarity(reasoning_state)
            solution_completeness = self._assess_solution_completeness(reasoning_state)
            emotional_appropriateness = self._assess_emotional_appropriateness(reasoning_state)
            technical_accuracy = self._assess_technical_accuracy(reasoning_state)
            response_structure = self._assess_response_structure(reasoning_state)
            
            # Calculate overall quality
            quality_weights = [0.2, 0.25, 0.2, 0.25, 0.1]  # Weighted importance
            quality_scores = [
                reasoning_clarity, solution_completeness, emotional_appropriateness,
                technical_accuracy, response_structure
            ]
            overall_quality = sum(score * weight for score, weight in zip(quality_scores, quality_weights))
            
            # Generate improvement suggestions
            improvement_suggestions = []
            quality_issues = []
            
            if reasoning_clarity < 0.7:
                improvement_suggestions.append("Enhance reasoning transparency and explanation")
                quality_issues.append("Reasoning clarity below threshold")
            
            if solution_completeness < 0.7:
                improvement_suggestions.append("Provide more comprehensive solution details")
                quality_issues.append("Solution completeness insufficient")
            
            if emotional_appropriateness < 0.7:
                improvement_suggestions.append("Better align response tone with customer emotion")
                quality_issues.append("Emotional alignment could be improved")
            
            # Create quality assessment
            reasoning_state.quality_assessment = QualityAssessment(
                overall_quality_score=overall_quality,
                reasoning_clarity=reasoning_clarity,
                solution_completeness=solution_completeness,
                emotional_appropriateness=emotional_appropriateness,
                technical_accuracy=technical_accuracy,
                response_structure=response_structure,
                improvement_suggestions=improvement_suggestions,
                quality_issues=quality_issues,
                confidence_in_assessment=0.8
            )
            
            # Check if quality meets standards
            if overall_quality < self.config.quality_score_threshold:
                reasoning_state.requires_human_review = True
                reasoning_state.escalation_reasons.append(f"Quality score {overall_quality:.2f} below threshold {self.config.quality_score_threshold}")
    
    async def _finalize_reasoning(self, reasoning_state: ReasoningState, start_time: float) -> None:
        """
        Finalizes the reasoning process by updating the reasoning state with processing time, overall confidence, summary, transparency explanation, and escalation flags if necessary.
        """
        
        # Calculate processing time
        reasoning_state.total_processing_time = time.time() - start_time
        
        # Calculate overall confidence
        if reasoning_state.reasoning_steps:
            step_confidences = [step.confidence for step in reasoning_state.reasoning_steps]
            reasoning_state.overall_confidence = sum(step_confidences) / len(step_confidences)
        
        # Generate reasoning summary
        reasoning_state.reasoning_summary = self._generate_reasoning_summary(reasoning_state)
        
        # Generate transparency explanation if enabled
        if self.config.enable_reasoning_transparency:
            reasoning_state.transparency_explanation = self._generate_transparency_explanation(reasoning_state)
        
        # Check for escalation needs
        if reasoning_state.overall_confidence < self.config.escalation_threshold:
            reasoning_state.requires_human_review = True
            reasoning_state.escalation_reasons.append(f"Overall confidence {reasoning_state.overall_confidence:.2f} below escalation threshold")
    
    # Helper methods for analysis
    
    def _categorize_problem(self, query: str) -> Tuple[ProblemCategory, float]:
        """
        Categorize the type of customer problem described in the query and assign a confidence score.
        
        Returns:
            A tuple containing the identified problem category and a confidence score between 0 and 1.
        """
        query_lower = query.lower()
        
        # Technical issue indicators
        technical_keywords = ['error', 'crash', 'bug', 'not working', 'broken', 'sync', 'connection', 'slow']
        if any(keyword in query_lower for keyword in technical_keywords):
            return ProblemCategory.TECHNICAL_ISSUE, 0.8
        
        # Account setup indicators
        setup_keywords = ['setup', 'configure', 'add account', 'new account', 'install', 'download']
        if any(keyword in query_lower for keyword in setup_keywords):
            return ProblemCategory.ACCOUNT_SETUP, 0.8
        
        # Feature education indicators
        feature_keywords = ['how to', 'how do i', 'tutorial', 'guide', 'learn', 'feature']
        if any(keyword in query_lower for keyword in feature_keywords):
            return ProblemCategory.FEATURE_EDUCATION, 0.7
        
        # Billing indicators
        billing_keywords = ['price', 'cost', 'billing', 'payment', 'subscription', 'upgrade']
        if any(keyword in query_lower for keyword in billing_keywords):
            return ProblemCategory.BILLING_INQUIRY, 0.9
        
        # Default to general support
        return ProblemCategory.GENERAL_SUPPORT, 0.5
    
    def _assess_urgency(self, query: str, emotion: EmotionalState) -> int:
        """
        Determines the urgency level of a query on a scale from 1 to 5 based on emotional state and presence of urgency-related keywords.
        
        Parameters:
        	query (str): The customer query text to analyze.
        	emotion (EmotionalState): The detected emotional state associated with the query.
        
        Returns:
        	int: An integer urgency score from 1 (lowest) to 5 (highest).
        """
        urgency_score = 1
        
        # Emotional urgency indicators
        if emotion in [EmotionalState.URGENT, EmotionalState.ANXIOUS]:
            urgency_score += 2
        elif emotion == EmotionalState.FRUSTRATED:
            urgency_score += 1
        
        # Textual urgency indicators
        urgent_keywords = ['urgent', 'emergency', 'asap', 'immediately', 'deadline', 'critical']
        urgent_count = sum(1 for keyword in urgent_keywords if keyword in query.lower())
        urgency_score += min(urgent_count, 2)
        
        return min(urgency_score, 5)
    
    def _assess_complexity(self, query: str) -> float:
        """
        Calculates a complexity score for a query on a scale from 0 to 1.
        
        The score is based on query length, presence of technical terms, and indicators of multiple problems. Higher scores indicate greater complexity.
         
        Returns:
            float: A value between 0 and 1 representing the assessed complexity of the query.
        """
        complexity_factors = []
        
        # Length complexity
        if len(query) > 200:
            complexity_factors.append(0.3)
        elif len(query) > 100:
            complexity_factors.append(0.2)
        else:
            complexity_factors.append(0.1)
        
        # Technical term density
        technical_terms = ['imap', 'smtp', 'oauth', 'ssl', 'port', 'server', 'protocol', 'authentication']
        query_terms = query.split()
        if not query_terms:  # Handle empty query case
            tech_density = 0.0
        else:
            tech_term_count = sum(1 for term in technical_terms if term in query.lower())
            tech_density = tech_term_count / len(query_terms)
        complexity_factors.append(min(tech_density * 2, 0.4))
        
        # Multiple problems indicator
        problem_indicators = ['and', 'also', 'plus', 'additionally', 'furthermore']
        if any(indicator in query.lower() for indicator in problem_indicators):
            complexity_factors.append(0.3)
        
        return min(sum(complexity_factors), 1.0)
    
    def _extract_entities(self, query: str) -> List[str]:
        """
        Extracts key entities such as email providers, Mailbird features, and error codes from the query string.
        
        Returns:
            entities (List[str]): A list of extracted entities in the format 'email_provider:<name>', 'feature:<name>', or 'error:<pattern>'.
        """
        entities = []
        
        # Email providers
        email_providers = ['gmail', 'outlook', 'yahoo', 'icloud', 'hotmail', 'office365']
        for provider in email_providers:
            if provider in query.lower():
                entities.append(f"email_provider:{provider}")
        
        # Mailbird features
        features = ['unified inbox', 'calendar', 'contacts', 'settings', 'accounts', 'sync']
        for feature in features:
            if feature in query.lower():
                entities.append(f"feature:{feature}")
        
        # Error patterns
        error_pattern = re.findall(r'error[\s\w]*\d+', query.lower())
        for error in error_pattern:
            entities.append(f"error:{error}")
        
        return entities
    
    def _infer_intent(self, query: str, category: ProblemCategory) -> str:
        """
        Infers the customer's intent based on the query and identified problem category.
        
        Parameters:
            query (str): The customer's query text.
            category (ProblemCategory): The categorized type of problem detected in the query.
        
        Returns:
            str: A concise description of the inferred customer intent.
        """
        if category == ProblemCategory.TECHNICAL_ISSUE:
            return "Customer wants to resolve a technical problem"
        elif category == ProblemCategory.ACCOUNT_SETUP:
            return "Customer needs help setting up or configuring their account"
        elif category == ProblemCategory.FEATURE_EDUCATION:
            return "Customer wants to learn how to use a feature"
        elif category == ProblemCategory.BILLING_INQUIRY:
            return "Customer has questions about pricing or billing"
        else:
            return "Customer seeks general support and assistance"
    
    def _extract_context_clues(self, query: str, context: Optional[Dict[str, Any]]) -> List[str]:
        """
        Extracts contextual clues from the query text and optional context metadata.
        
        Identifies temporal and frequency references within the query, and adds context clues based on user type and account age if provided in the context dictionary.
        
        Returns:
            List of extracted context clue strings.
        """
        clues = []
        
        # Temporal clues
        temporal_words = ['recently', 'today', 'yesterday', 'suddenly', 'after', 'since']
        for word in temporal_words:
            if word in query.lower():
                clues.append(f"temporal_reference:{word}")
        
        # Frequency clues
        frequency_words = ['always', 'never', 'sometimes', 'often', 'rarely']
        for word in frequency_words:
            if word in query.lower():
                clues.append(f"frequency:{word}")
        
        # Context from additional information
        if context:
            if context.get('user_type') == 'business':
                clues.append("business_user_context")
            if context.get('account_age_days', 0) < 7:
                clues.append("new_user_context")
        
        return clues
    
    def _assess_reasoning_clarity(self, reasoning_state: ReasoningState) -> float:
        """
        Calculates a clarity score for the reasoning process based on phase coverage, reasoning depth, and supporting evidence.
        
        Parameters:
        	reasoning_state (ReasoningState): The current reasoning state containing reasoning steps and evidence.
        
        Returns:
        	float: A normalized clarity score between 0.0 and 1.0 reflecting the thoroughness and transparency of the reasoning process.
        """
        if not reasoning_state.reasoning_steps:
            return 0.3
        
        clarity_score = 0.0
        
        # Check if all major phases are covered
        phases_covered = set(step.phase for step in reasoning_state.reasoning_steps)
        expected_phases = [ReasoningPhase.QUERY_ANALYSIS, ReasoningPhase.SOLUTION_MAPPING, ReasoningPhase.TOOL_ASSESSMENT]
        coverage_score = len(phases_covered.intersection(expected_phases)) / len(expected_phases)
        clarity_score += coverage_score * 0.4
        
        # Check reasoning depth
        avg_reasoning_length = sum(len(step.reasoning) for step in reasoning_state.reasoning_steps) / len(reasoning_state.reasoning_steps)
        depth_score = min(avg_reasoning_length / 100, 1.0)  # Normalize to 100 chars
        clarity_score += depth_score * 0.3
        
        # Check evidence provided
        evidence_count = sum(len(step.evidence) for step in reasoning_state.reasoning_steps)
        evidence_score = min(evidence_count / 10, 1.0)  # Normalize to 10 pieces of evidence
        clarity_score += evidence_score * 0.3
        
        return min(clarity_score, 1.0)
    
    def _assess_solution_completeness(self, reasoning_state: ReasoningState) -> float:
        """
        Calculates a completeness score for the selected solution based on detail, fallback options, success indicators, time estimate, and risk factors.
        
        Returns:
            float: A score between 0.0 and 1.0 indicating the thoroughness of the proposed solution.
        """
        if not reasoning_state.selected_solution:
            return 0.2
        
        solution = reasoning_state.selected_solution
        completeness_score = 0.0
        
        # Check solution detail
        if len(solution.detailed_approach) > 50:
            completeness_score += 0.3
        
        # Check if fallback options provided
        if solution.fallback_options:
            completeness_score += 0.2
        
        # Check if success indicators provided
        if solution.success_indicators:
            completeness_score += 0.2
        
        # Check if time estimate provided
        if solution.estimated_time_minutes > 0:
            completeness_score += 0.1
        
        # Check if risk factors considered
        if solution.risk_factors:
            completeness_score += 0.2
        
        return min(completeness_score, 1.0)
    
    def _assess_emotional_appropriateness(self, reasoning_state: ReasoningState) -> float:
        """
        Evaluates how well the response strategy aligns with the detected emotional state of the query.
        
        Returns:
            float: A score between 0 and 1 indicating the degree of emotional appropriateness, with higher values reflecting better alignment between the response strategy and the user's emotional state.
        """
        if not reasoning_state.query_analysis or not reasoning_state.response_strategy:
            return 0.5
        
        emotion = reasoning_state.query_analysis.emotional_state
        strategy = reasoning_state.response_strategy.lower()
        
        # Check for appropriate emotional responses
        if emotion == EmotionalState.FRUSTRATED and 'apology' in strategy:
            return 0.9
        elif emotion == EmotionalState.CONFUSED and 'step-by-step' in strategy:
            return 0.9
        elif emotion == EmotionalState.ANXIOUS and 'reassurance' in strategy:
            return 0.9
        elif emotion == EmotionalState.PROFESSIONAL and 'professional' in strategy:
            return 0.9
        else:
            return 0.6  # Neutral emotional alignment
    
    def _assess_technical_accuracy(self, reasoning_state: ReasoningState) -> float:
        """
        Estimates the technical accuracy of the reasoning process based on the presence and detail of technical reasoning.
        
        Returns:
            float: A confidence score representing the assessed technical accuracy, with higher values for detailed technical solutions to technical issues.
        """
        # This would typically involve checking against known technical facts
        # For now, return high confidence if technical reasoning is present
        
        if reasoning_state.query_analysis and reasoning_state.query_analysis.problem_category == ProblemCategory.TECHNICAL_ISSUE:
            if reasoning_state.selected_solution and len(reasoning_state.selected_solution.detailed_approach) > 100:
                return 0.8
            else:
                return 0.6
        
        return 0.7  # Default for non-technical queries
    
    def _assess_response_structure(self, reasoning_state: ReasoningState) -> float:
        """
        Evaluates the structural quality of the response by scoring the presence and completeness of key components in the reasoning state.
        
        Returns:
            float: A score between 0.0 and 1.0 reflecting the overall response structure quality.
        """
        structure_score = 0.0
        
        # Check if response strategy exists
        if reasoning_state.response_strategy:
            structure_score += 0.4
        
        # Check if solution is well-structured
        if reasoning_state.selected_solution:
            solution = reasoning_state.selected_solution
            if solution.solution_summary and solution.detailed_approach:
                structure_score += 0.3
            if solution.expected_outcome:
                structure_score += 0.2
        
        # Check if quality assessment was performed
        if reasoning_state.quality_assessment:
            structure_score += 0.1
        
        return min(structure_score, 1.0)
    
    def _generate_reasoning_summary(self, reasoning_state: ReasoningState) -> str:
        """
        Produces a concise summary string highlighting key reasoning phases, including query analysis, solution generation, tool decision, and quality assessment, based on the provided reasoning state.
        
        Returns:
            str: A summary of the main reasoning steps and outcomes.
        """
        summary_parts = []
        
        if reasoning_state.query_analysis:
            qa = reasoning_state.query_analysis
            summary_parts.append(f"Analyzed query showing {qa.emotional_state.value} emotion and {qa.problem_category.value} category")
        
        if reasoning_state.solution_candidates:
            summary_parts.append(f"Generated {len(reasoning_state.solution_candidates)} solution candidates")
        
        if reasoning_state.tool_reasoning:
            summary_parts.append(f"Determined {reasoning_state.tool_reasoning.decision_type.value} for optimal response")
        
        if reasoning_state.quality_assessment:
            qa = reasoning_state.quality_assessment
            summary_parts.append(f"Quality assessment: {qa.overall_quality_score:.2f}/1.0")
        
        return " | ".join(summary_parts)
    
    def _generate_transparency_explanation(self, reasoning_state: ReasoningState) -> str:
        """
        Generate a user-friendly explanation of the reasoning process based on the current reasoning state.
        
        Returns:
            str: A concise, natural language summary describing detected emotion, problem category, urgency, tool usage decisions, and solution confidence, or an empty string if transparency is disabled.
        """
        if not self.config.enable_reasoning_transparency:
            return ""
        
        explanation_parts = []
        
        if reasoning_state.query_analysis:
            qa = reasoning_state.query_analysis
            explanation_parts.append(
                f"I detected that you're feeling {qa.emotional_state.value} about this {qa.problem_category.value.replace('_', ' ')} "
                f"with an urgency level of {qa.urgency_level}/5."
            )
        
        if reasoning_state.tool_reasoning:
            tr = reasoning_state.tool_reasoning
            if tr.decision_type == ToolDecisionType.WEB_SEARCH_REQUIRED:
                explanation_parts.append("I'll search for the most current information to give you the best answer.")
            elif tr.decision_type == ToolDecisionType.INTERNAL_KB_ONLY:
                explanation_parts.append("I have comprehensive information in my knowledge base to help you.")
        
        if reasoning_state.selected_solution:
            sol = reasoning_state.selected_solution
            explanation_parts.append(
                f"I've identified a solution that should take about {sol.estimated_time_minutes} minutes to implement "
                f"with a {sol.confidence_score:.0%} confidence rate."
            )
        
        return " ".join(explanation_parts)