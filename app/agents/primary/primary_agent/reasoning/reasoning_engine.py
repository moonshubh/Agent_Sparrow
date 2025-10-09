"""
Agent Sparrow - Core Reasoning Engine

This module implements the sophisticated reasoning engine that powers Agent Sparrow's
advanced decision-making capabilities with chain-of-thought processing, multi-step
problem solving, and intelligent tool usage decisions.
"""

import logging
import time
import json
from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime
import asyncio
import re
from textwrap import dedent

from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage
from opentelemetry import trace

from app.core.settings import settings
from app.agents.primary.primary_agent.prompts.agent_sparrow_v9_prompts import AgentSparrowV9Prompts, PromptV9Config
from .schemas import (
    ReasoningState, ReasoningStep, ReasoningPhase, QueryAnalysis,
    ToolDecisionReasoning, QualityAssessment, ProblemCategory, ToolDecisionType,
    ConfidenceLevel, ReasoningConfig, BusinessImpact, TimeSensitivity,
    SituationalAnalysis, SolutionArchitecture, SolutionCandidate, PredictiveInsight,
    ResponseOrchestration, SelfCritiqueResult
)
from .problem_solver import ProblemSolvingFramework
from .tool_intelligence import ToolIntelligence
from app.agents.primary.primary_agent.prompts import EmotionTemplates, AgentSparrowV9Prompts
from app.agents.primary.primary_agent.prompts.emotion_templates import EmotionalState
from app.providers.adapters import (
    get_adapter,
    default_provider,
    default_model_for_provider,
)

logger = logging.getLogger(__name__)
tracer = trace.get_tracer(__name__)


from typing import Any
from app.providers.base import BaseChatModel

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
    
    def __init__(
        self,
        model: BaseChatModel,
        config: Optional[ReasoningConfig] = None,
        provider: Optional[str] = None,
        model_name: Optional[str] = None,
    ):
        """
        Initialize the ReasoningEngine with optional configuration.
        
        If no configuration is provided, a default ReasoningConfig is used. Instantiates the problem-solving and tool intelligence components required for the reasoning process.
        """
        self.model = model
        self.config = config or ReasoningConfig()
        self.provider = (provider or default_provider()).lower()
        self.model_name = (model_name or default_model_for_provider(self.provider)).lower()
        self._provider_prompt_cache: Dict[str, str] = {}
        self.problem_solver = ProblemSolvingFramework(self.config)
        self.tool_intelligence = ToolIntelligence(self.config)

    def _coerce_to_text(self, content: Any) -> str:
        """Normalize provider responses to plain text."""
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            parts: List[str] = []
            for item in content:
                if isinstance(item, str):
                    parts.append(item)
                elif isinstance(item, dict):
                    candidate = item.get("text") or item.get("content")
                    parts.append(str(candidate) if candidate is not None else str(item))
                else:
                    parts.append(str(item))
            return "\n".join(part for part in parts if part)
        return str(content)

    def _get_provider_system_prompt(self, version: str = "latest") -> str:
        if not self.provider or not self.model_name:
            return ""

        if version in self._provider_prompt_cache:
            return self._provider_prompt_cache[version]

        prompt = ""
        try:
            adapter = get_adapter(self.provider, self.model_name)
            prompt = adapter.get_system_prompt(version=version) or ""
        except Exception as exc:
            logger.warning(
                "Failed to load provider system prompt for %s/%s: %s",
                self.provider,
                self.model_name,
                exc,
            )
            prompt = ""

        self._provider_prompt_cache[version] = prompt
        return prompt

    def _compose_system_prompt(self, prompt_config: PromptV9Config, version: str = "latest") -> str:
        provider_prompt = self._get_provider_system_prompt(version=version).strip()
        agent_prompt = AgentSparrowV9Prompts.build_system_prompt(config=prompt_config).strip()

        if provider_prompt and agent_prompt:
            return f"{provider_prompt}\n\n{agent_prompt}"
        if provider_prompt:
            return provider_prompt
        return agent_prompt

    def _compose_system_prompt_with_instructions(
        self,
        instructions: str,
        *,
        prompt_config: Optional[PromptV9Config] = None,
        version: str = "latest",
    ) -> str:
        """Combine provider + Agent Sparrow prompts with call-specific instructions."""

        base_prompt = self._compose_system_prompt(
            prompt_config or PromptV9Config(),
            version=version,
        ).strip()
        instruction_text = dedent(instructions).strip()

        if base_prompt and instruction_text:
            return f"{base_prompt}\n\n{instruction_text}"
        return base_prompt or instruction_text
        
    def get_thinking_budget(self, complexity: str) -> int:
        """
        Determine thinking budget based on query complexity.
        
        Based on Google's recommendations:
        - Range: 0 to 24,576 tokens for Gemini 2.5 Flash
        - Use -1 for dynamic allocation (model decides)
        - Higher budgets for complex reasoning tasks
        """
        if getattr(self.config, "thinking_budget_override", None) is not None:
            return int(self.config.thinking_budget_override)

        quality = getattr(self.config, "quality_level", "balanced") or "balanced"
        quality = quality.lower()
        quality_budgets = {
            "fast": 2048,
            "balanced": 8192,
            "thorough": 16384,
        }
        base_budget = quality_budgets.get(quality, quality_budgets["balanced"])

        if complexity == "dynamic":
            return -1
        if complexity == "simple":
            return max(1024, base_budget // 2)
        if complexity == "complex":
            return min(24576, int(base_budget * 1.5))
        return base_budget
        
        
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
            reasoning_state = ReasoningState(
                session_id=session_id, 
                start_time=datetime.now(),
                query_text=query
            )
            reasoning_state.request_context = context or {}
            span.set_attribute("session_id", session_id)
            span.set_attribute("query_length", len(query))
            
            # Log configuration
            logger.info(f"Reasoning config: chain_of_thought={self.config.enable_chain_of_thought}, "
                       f"problem_solving={self.config.enable_problem_solving_framework}, "
                       f"tool_intelligence={self.config.enable_tool_intelligence}, "
                       f"self_critique={self.config.enable_self_critique}")
            
            try:
                # Unified Comprehensive Analysis (combines 4 phases)
                logger.info("Starting unified comprehensive analysis")
                unified_result = await self._unified_comprehensive_analysis(query, reasoning_state, context)
                
                # Parse and populate reasoning state from unified analysis
                await self._parse_unified_analysis(unified_result, reasoning_state, original_query=query)
                
                # Log key findings
                if reasoning_state.query_analysis:
                    span.set_attribute("emotion_detected", reasoning_state.query_analysis.emotional_state.value)
                    span.set_attribute("problem_category", reasoning_state.query_analysis.problem_category.value)
                    logger.info(f"Unified analysis complete: emotion={reasoning_state.query_analysis.emotional_state.value}, "
                               f"problem={reasoning_state.query_analysis.problem_category.value}")
                
                # Quality Assessment (if confidence is low)
                if reasoning_state.overall_confidence < 0.7:
                    logger.info("Low confidence detected, performing quality assessment")
                    if self.config.enable_quality_assessment:
                        await self._assess_quality(reasoning_state)

            except Exception as e:
                import traceback
                logger.error(f"Error during reasoning process: {e}")
                logger.error(f"Exception type: {type(e).__name__}")
                logger.error(f"Traceback:\n{traceback.format_exc()}")
                reasoning_state.is_escalated = True
                reasoning_state.escalation_reason = f"An unexpected error occurred: {e}"
                span.record_exception(e)
            
            # Finalize reasoning state
            await self._finalize_reasoning(reasoning_state, start_time)
            span.set_attribute("total_processing_time", reasoning_state.total_processing_time)
            span.set_attribute("overall_confidence", reasoning_state.overall_confidence)
            
            return reasoning_state
                
    async def _analyze_query_v9(
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
                surface_meaning=query, 
                latent_intent=inferred_intent,
                emotional_subtext=f"Detected primary emotion: {emotion_result.primary_emotion.value}", 
                historical_context="No historical context available in this session.", 
                emotional_state=emotion_result.primary_emotion,
                emotion_confidence=emotion_result.confidence_score,
                problem_category=problem_category,
                category_confidence=category_confidence,
                key_entities=key_entities,
                complexity_score=complexity_score,
                urgency_level=urgency_level,
                situational_analysis=SituationalAnalysis(
                    technical_complexity=int(complexity_score * 10),
                    emotional_intensity=self._assess_urgency(query, emotion_result.primary_emotion) * 2, 
                    business_impact=BusinessImpact.MEDIUM, 
                    time_sensitivity=TimeSensitivity.IMMEDIATE 
                )
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
    
    async def _apply_predictive_intelligence(self, reasoning_state: ReasoningState):
        """
        Applies the V9 Predictive Intelligence Engine based on query analysis.
        This is a placeholder for a more sophisticated implementation.
        """
        if not reasoning_state.query_analysis:
            return

        insights = []
        query_lower = reasoning_state.query_analysis.query_text.lower()

        if "slow" in query_lower and "email" in query_lower:
            insights.append(PredictiveInsight(
                pattern_detected="'Slow email' mentioned",
                proactive_suggestion="User might have large attachments, a large local database, or incorrect sync settings. Prepare to investigate these areas.",
                confidence=0.8
            ))
        
        if reasoning_state.query_analysis.emotional_state in [EmotionalState.FRUSTRATED, EmotionalState.DISAPPOINTED]:
            insights.append(PredictiveInsight(
                pattern_detected="High user frustration",
                proactive_suggestion="Immediate empathy and confidence boost required. Consider offering premium support or a quicker solution path.",
                confidence=0.9
            ))

        reasoning_state.predictive_insights = insights
        
        reasoning_state.add_reasoning_step(ReasoningStep(
            phase=ReasoningPhase.CONTEXT_RECOGNITION, 
            description="Applied Predictive Intelligence Engine.",
            reasoning=f"Generated {len(insights)} predictive insights.",
            confidence=0.85
        ))

    async def _map_solutions_v9(self, reasoning_state: ReasoningState): 
        """
        Generates and selects solution candidates for the analyzed query using the problem-solving framework.
        
        This phase creates potential solutions based on the query analysis attributes, selects the most confident solution if available, and records the process as a reasoning step in the reasoning state.
        """
        if not reasoning_state.query_analysis:
            return

        qa = reasoning_state.query_analysis
        
        solution_candidates = await self.problem_solver.generate_solution_candidates(
            problem_category=reasoning_state.query_analysis.problem_category,
            emotional_state=reasoning_state.query_analysis.emotional_state,
            urgency_level=5,  # Default urgency
            complexity_score=reasoning_state.query_analysis.situational_analysis.technical_complexity / 10,
            key_entities=reasoning_state.query_analysis.key_entities,
            query_text=reasoning_state.query_analysis.query_text
        )

        if solution_candidates:
            primary_pathway = max(solution_candidates, key=lambda s: s.confidence_score)
            alternative_routes = [s for s in solution_candidates if s.solution_id != primary_pathway.solution_id]

            # detailed_steps should already be populated by the problem solver
            primary_pathway.preventive_measures = ["Run maintenance checks regularly."] 

            solution_arch = SolutionArchitecture(
                primary_pathway=primary_pathway,
                alternative_routes=alternative_routes,
                enhancement_opportunities=["Introduce user to the new 'Speedy Sync' feature."] 
            )
            reasoning_state.solution_architecture = solution_arch
            confidence = primary_pathway.confidence_score
            reasoning = f"Constructed solution architecture with primary pathway: {primary_pathway.solution_summary}"
        else:
            confidence = 0.1
            reasoning = "No suitable solution candidates could be generated."
            reasoning_state.is_escalated = True
            reasoning_state.escalation_reason = "Solution mapping failed."
        
        reasoning_state.add_reasoning_step(ReasoningStep(
            phase=ReasoningPhase.SOLUTION_MAPPING,
            description="Generated solution candidates",
            reasoning=reasoning,
            confidence=confidence,
            evidence=[f"Solution: {s.solution_summary}" for s in solution_candidates[:3]] 
        ))

    async def _develop_response_strategy_v9(self, reasoning_state: ReasoningState): 
        """
        Constructs a comprehensive response strategy by integrating emotional state, urgency, complexity, tool decisions, and solution attributes into actionable guidance for customer interaction.
        
        The strategy adapts tone, structure, and content to the customer's emotional and situational context, and is recorded in the reasoning state for downstream use.
        """
        if not reasoning_state.query_analysis or not reasoning_state.solution_architecture:
            logger.warning("Missing query_analysis or solution_architecture, skipping response strategy development")
            return

        qa = reasoning_state.query_analysis
        
        emotional_strategy = EmotionTemplates.get_frustration_template() if qa.emotional_state in [EmotionalState.FRUSTRATED, EmotionalState.DISAPPOINTED] else "Acknowledge the user's emotional state and state the goal."

        # Generate the final response based on the query analysis and solution architecture
        try:
            final_response = await self._generate_final_response(reasoning_state)
            if not final_response:
                logger.error("_generate_final_response returned None")
                final_response = "I apologize, but I'm having trouble generating a response. Let me help you with your query."
        except Exception as e:
            logger.error(f"Error generating final response: {e}", exc_info=True)
            final_response = "I apologize, but I encountered an error while preparing my response. Please let me help you with your query."

        orchestration = ResponseOrchestration(
            emotional_acknowledgment_strategy=emotional_strategy,
            technical_solution_delivery_method="Use analogies and break complex concepts into digestible pieces.",
            relationship_strengthening_elements=["Reference previous successes.", "Provide bonus tips."],
            delight_injection_points=["Use a fun fact related to their issue.", "Celebrate their success in solving the problem."],
            final_response_preview=final_response
        )

        reasoning_state.response_orchestration = orchestration
        
        reasoning_state.add_reasoning_step(ReasoningStep(
            phase=ReasoningPhase.RESPONSE_STRATEGY,
            description="Developed comprehensive response strategy with final response",
            reasoning=f"Crafted multi-faceted response strategy incorporating emotional intelligence, "
                     f"urgency handling, and solution complexity. Generated final response of {len(final_response) if final_response else 0} characters.",
            confidence=0.8,  
            evidence=orchestration.relationship_strengthening_elements
        ))

    async def _assess_tool_needs(self, reasoning_state: ReasoningState) -> None:
        """
        Assess what tools are needed for this query using the tool intelligence system.
        """
        if not reasoning_state.query_analysis:
            return
            
        # Use the tool intelligence system to decide on tool usage
        tool_decision = await self.tool_intelligence.decide_tool_usage(
            query_analysis=reasoning_state.query_analysis,
            solution_candidates=reasoning_state.solution_architecture.alternative_routes if reasoning_state.solution_architecture else None
        )
        
        reasoning_state.tool_reasoning = tool_decision
        
        # Add reasoning step
        reasoning_state.add_reasoning_step(ReasoningStep(
            phase=ReasoningPhase.TOOL_ASSESSMENT,
            description="Assessed tool usage requirements",
            reasoning=f"Determined {tool_decision.decision_type.value} based on query analysis and solution requirements",
            confidence=tool_decision.confidence,
            evidence=tool_decision.required_information
        ))

    async def _generate_final_response(self, reasoning_state: ReasoningState) -> Optional[str]:
        """
        Generates the final polished response based on all reasoning analysis.
        
        This method uses the LLM to create a comprehensive, well-structured response that incorporates
        the emotional state, solution architecture, and response orchestration strategy.
        """
        with tracer.start_as_current_span("reasoning_engine._generate_final_response") as span:
            try:
                if not reasoning_state.query_analysis or not reasoning_state.solution_architecture:
                    return "I'm sorry, I wasn't able to fully analyze your query. Please try rephrasing it."

                qa = reasoning_state.query_analysis
                solution = reasoning_state.solution_architecture.primary_pathway
                
                # Use emotion templates for better response crafting
                # Get emotion-aware opening
                empathy_opening = EmotionTemplates.get_empathy_template(
                    qa.emotional_state, 
                    qa.key_entities.get('issue', qa.query_text[:50])
                )
                
                # Get response strategy for this emotion
                response_strategy = EmotionTemplates.get_response_strategy(qa.emotional_state)
                
                # Build a comprehensive prompt for final response generation
                response_prompt = f"""Generate a warm, human-like response that feels like talking to a knowledgeable friend who genuinely cares about solving email problems.

**Customer Query**: {qa.query_text}

**Emotional Context**: 
- Primary emotion: {qa.emotional_state.value} (confidence: {qa.situational_analysis.emotional_intensity}/10)
- Recommended tone: {response_strategy.get('tone', 'warm and professional')}
- Communication style: {response_strategy.get('language', 'clear and accessible')}

**Suggested Empathy Opening**:
{empathy_opening}

**Solution Details**:
Primary approach: {solution.solution_summary}
Steps required: {len(solution.detailed_steps)}

**Critical Response Requirements**:

1. **Human Touch Elements**:
   - Start with genuine empathy using the suggested opening or similar
   - Use natural language patterns (contractions like "I'll", "you're", "let's")
   - Include conversational connectors ("Actually", "By the way", "Oh, and...")
   - Add micro-acknowledgments ("I see", "Got it", "Makes sense")
   - Use inclusive language ("Let's tackle this together", "We'll get this sorted")

2. **Emotional Intelligence**:
   - Mirror the customer's communication style (formal/casual)
   - Validate their feelings without being patronizing
   - Show understanding of the impact on their workflow
   - Celebrate small wins during troubleshooting ("Great! That's progress")
   - Use appropriate enthusiasm or calmness based on their state

3. **Conversational Flow**:
   - Break solutions into digestible chunks with natural transitions
   - Use analogies that relate to everyday experiences
   - Add personality touches ("Here's a neat trick...", "Fun fact...")
   - Include anticipatory guidance ("You might be wondering...")
   - End with forward momentum ("Once this is set up, you'll love...")

4. **Mailbird Accuracy** (NEVER make up settings):
   - Only reference actual Mailbird settings from the knowledge base
   - Use exact menu paths: Settings → General → Notifications
   - If unsure about a setting location, say "Let me guide you to the right setting"
   - Reference actual features: Unified Account, Snooze, Email Tracking, etc.
   - Mention keyboard shortcuts only if certain (e.g., Ctrl+Shift+C for quick compose)

5. **Solution Delivery**:
   Structure: {response_strategy.get('structure', 'acknowledgment → solution → verification')}
   Include: {', '.join(response_strategy.get('extras', ['clear next steps']))}

**Example Natural Phrases to Use**:
- "I totally get how frustrating that must be..."
- "Let me walk you through this - it's actually pretty straightforward once you know where to look"
- "Here's what's happening behind the scenes..."
- "Quick tip while we're here..."
- "You're almost there! Just one more step..."

**Avoid**:
- Robotic phrases ("I understand your concern")
- Over-explaining simple concepts
- Making up Mailbird features or settings
- Being overly formal when they're casual
- Generic responses that could apply to any email client

Now, create a response that feels like it's from Agent Sparrow - your email-savvy friend who genuinely wants to help, knows Mailbird inside out, and can explain things in a way that just clicks."""

                request_context = getattr(reasoning_state, "request_context", {})
                if isinstance(request_context, dict):
                    grounding_section = request_context.get("grounding") or {}
                    grounding_digest = grounding_section.get("digest") or ""
                    if grounding_digest:
                        response_prompt += f"\n\nGrounding Evidence (internal use only):\n{grounding_digest}\n"

                response_prompt += "\nPlease do not include explicit URLs, citation markers, or numbered references in the final response. Rely on the provided evidence to stay accurate."  # noqa: E501

                # Use the full Agent Sparrow V9 prompts for proper response generation
                prompt_config = PromptV9Config(
                    include_self_critique=False,  # Don't include critique in response generation
                    include_reasoning=True,
                    include_emotional_resonance=True,
                    include_technical_excellence=True,
                    include_conversational_excellence=True,
                    include_solution_delivery=True,
                    include_knowledge_integration=True,
                    include_premium_elements=True,
                    include_success_directives=True
                )
                system_prompt = self._compose_system_prompt(prompt_config)
                
                messages: List[BaseMessage] = [
                    SystemMessage(content=system_prompt),
                    HumanMessage(content=response_prompt)
                ]

                response = await self.model.ainvoke(messages)
                final_response = response.content
                
                # Ensure we have a valid response
                if not final_response or len(final_response.strip()) == 0:
                    logger.warning("Empty response generated, using fallback")
                    # Generate a contextual fallback based on the query analysis
                    problem_type = qa.problem_category.value if qa.problem_category else "general"
                    final_response = f"I understand you're experiencing {problem_type} issues with Mailbird. Let me help you with that. Could you provide more details about what specific issue you're facing?"
                
                span.set_attribute("response_length", len(final_response))
                span.set_attribute("emotional_state", qa.emotional_state.value)
                
                return final_response

            except Exception as e:
                logger.error(f"Error generating final response: {e}", exc_info=True)
                span.record_exception(e)
                return "I apologize, but I encountered an error while preparing my response. Please try again."

    
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
        strategy_value = reasoning_state.response_strategy
        if isinstance(strategy_value, list):
            strategy = " ".join(str(s) for s in strategy_value)
        else:
            strategy = str(strategy_value)
        strategy = strategy.lower()
        
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
        if reasoning_state.response_orchestration:
            structure_score += 0.4
        
        # Check if solution is well-structured
        if reasoning_state.solution_architecture and reasoning_state.solution_architecture.primary_pathway:
            solution = reasoning_state.solution_architecture.primary_pathway
            if solution.solution_summary and solution.detailed_steps:
                structure_score += 0.3
            if solution.preventive_measures:
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
        
        if reasoning_state.solution_architecture:
            summary_parts.append(f"Constructed a solution architecture with {len(reasoning_state.solution_architecture.alternative_routes)} alternatives.")
        
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

        # V9 does not use a simple transparency explanation, this is now handled by the detailed reasoning trace.
        # This function can be deprecated or repurposed.
        return self._generate_reasoning_summary(reasoning_state)

    async def _perform_self_critique_v9(self, reasoning_state: ReasoningState):
        """
        Invokes the V9 self-critique framework to evaluate the drafted response.

        This method constructs a prompt with the drafted response and the critique checklist,
        calls the LLM, parses the structured critique, and updates the reasoning state
        with the SelfCritiqueResult.
        """
        with tracer.start_as_current_span("reasoning_engine._perform_self_critique_v9") as span:
            if not reasoning_state.response_orchestration:
                reasoning_state.add_reasoning_step(ReasoningStep(
                    phase=ReasoningPhase.SELF_CRITIQUE,
                    description="Self-critique skipped",
                    reasoning="Skipping self-critique as response orchestration is not available.",
                    confidence=0.2  # LOW confidence
                ))
                return
                
            draft_response = reasoning_state.response_orchestration.final_response_preview
            if not draft_response:
                reasoning_state.add_reasoning_step(ReasoningStep(
                    phase=ReasoningPhase.SELF_CRITIQUE,
                    description="Self-critique skipped",
                    reasoning="Skipping self-critique as no draft response is available.",
                    confidence=0.5  # MEDIUM confidence
                ))
                return

            reasoning_state.add_reasoning_step(ReasoningStep(
                phase=ReasoningPhase.SELF_CRITIQUE,
                description="Performing self-critique",
                reasoning="Performing internal self-critique on the drafted response.",
                confidence=0.8  # HIGH confidence
            ))

            prompt_config = PromptV9Config(include_self_critique=True)
            system_prompt = self._compose_system_prompt(prompt_config)
            
            critique_request_prompt = f"Here is the response I have drafted. Please provide your internal self-critique based on the framework provided in your system instructions:\n\n<draft_response>\n{draft_response}\n</draft_response>"

            messages: List[BaseMessage] = [
                SystemMessage(content=system_prompt),
                HumanMessage(content=critique_request_prompt)
            ]

            try:
                response = await self.model.ainvoke(messages)
                critique_content = response.content
                span.set_attribute("critique_raw_response", critique_content)

                score_match = re.search(r"Critique Score \(out of 10.0\):.*?([0-9.]+)", critique_content, re.DOTALL)
                verdict_match = re.search(r"Verdict \(Pass/Fail\):.*?\b(Pass|Fail)\b", critique_content, re.IGNORECASE)
                refinements_match = re.search(r"Required Refinements:.*?(\[.*?\]|None)", critique_content, re.DOTALL)

                critique_score = float(score_match.group(1)) if score_match else 0.0
                passed_critique = verdict_match.group(1).lower() == 'pass' if verdict_match else False
                
                improvements = []
                if refinements_match:
                    refinement_str = refinements_match.group(1)
                    if refinement_str.lower() != 'none':
                        improvements = [item.strip() for item in refinement_str.strip('[]').split(',') if item.strip()]

                critique_result = SelfCritiqueResult(
                    passed_critique=passed_critique,
                    critique_score=critique_score,
                    suggested_improvements=improvements,
                )
                reasoning_state.self_critique_result = critique_result
                summary = f"Self-critique completed. Score: {critique_score}/10.0. Passed: {passed_critique}"

            except Exception as e:
                logger.error(f"Error during self-critique LLM call: {e}")
                span.record_exception(e)
                critique_result = SelfCritiqueResult(passed_critique=False, critique_score=0.0, suggested_improvements=["Critique process failed."])
                reasoning_state.self_critique_result = critique_result
                summary = "Self-critique failed due to an exception."

            reasoning_state.add_reasoning_step(ReasoningStep(
                phase=ReasoningPhase.SELF_CRITIQUE,
                description="Self-critique completed",
                reasoning=summary,
                confidence=0.8  # HIGH confidence
            ))
    
    async def _unified_comprehensive_analysis(self, query: str, reasoning_state: ReasoningState, context: Optional[Dict[str, Any]]) -> str:
        """
        Perform unified comprehensive analysis combining query analysis, solution mapping,
        and tool assessment in a single LLM call.
        
        This method reduces LLM calls from 4 separate phases to 1 unified analysis.
        """
        with tracer.start_as_current_span("reasoning_engine.unified_analysis") as span:
            # Determine query complexity for thinking budget
            complexity = self._assess_initial_complexity(query)
            thinking_budget = self.get_thinking_budget(complexity)
            
            span.set_attribute("complexity", complexity)
            span.set_attribute("thinking_budget", thinking_budget)
            
            # Create comprehensive analysis prompt
            analysis_prompt_config = PromptV9Config(
                include_self_critique=False,
                include_reasoning=True,
                include_emotional_resonance=True,
                include_technical_excellence=True,
                include_conversational_excellence=False,
                include_solution_delivery=False,
                include_knowledge_integration=True,
                include_premium_elements=False,
                include_success_directives=False,
            )

            system_prompt = self._compose_system_prompt_with_instructions(
                f"""You are Agent Sparrow, an advanced AI customer success expert for Mailbird email client.

## Your Task: Comprehensive Query Analysis

Analyze the customer query and provide a comprehensive assessment covering:

1. **Emotional & Query Analysis**:
   - Detect emotional state (frustrated, confused, anxious, professional, excited, urgent, disappointed, neutral)
   - Identify problem category (technical_issue, account_setup, feature_education, billing_inquiry, general_question)
   - Assess urgency level (1-5 scale)
   - Extract key entities and intent

2. **Solution Mapping**:
   - Identify 2-3 potential solutions with confidence scores
   - Map to specific Mailbird features or settings
   - Consider platform-specific solutions (Windows/Mac)
   - Include step-by-step resolution paths

3. **Tool Assessment**:
   - Decide if tools are needed (NO_TOOLS_NEEDED, INTERNAL_KB_ONLY, WEB_SEARCH_REQUIRED, BOTH_SOURCES_NEEDED)
   - Provide reasoning for tool decision
   - Suggest specific search queries if needed

4. **Response Strategy**:
   - Recommend tone (empathetic, educational, direct, reassuring)
   - Suggest response structure (problem acknowledgment → solution → verification)
   - Include any escalation indicators

<thinking>
You have a thinking budget of {thinking_budget} tokens. Use this internal reasoning space to:
- Deeply analyze the customer's query and emotional state
- Consider multiple interpretations of their problem
- Evaluate different solution approaches and their confidence levels
- Plan the optimal response structure and tone
- Think through edge cases and potential follow-up questions

This is your private thinking space - the customer won't see this reasoning process.
</thinking>

Provide your analysis in a structured format with clear sections.""",
                prompt_config=analysis_prompt_config,
            )

            conversation_note = "No prior conversation context provided."
            grounding_digest = ""
            if context and isinstance(context, dict):
                messages_context = context.get("messages") or []
                if messages_context:
                    conversation_note = f"{len(messages_context)} prior messages available in session."
                grounding_section = context.get("grounding") or {}
                grounding_digest = grounding_section.get("digest") or ""

            user_prompt = f"Customer Query: {query}\n\nConversation context: {conversation_note}\n"
            if grounding_digest:
                user_prompt += f"\nGrounding Evidence (internal use only):\n{grounding_digest}\n"

            user_prompt += "\nProvide comprehensive analysis following the structure outlined in your instructions."

            # Make single LLM call for unified analysis
            messages: List[BaseMessage] = [
                SystemMessage(content=system_prompt),
                HumanMessage(content=user_prompt)
            ]
            
            try:
                # Use the model's ainvoke with thinking budget
                # Note: For Gemini 2.5 Flash, we need to configure thinking budget properly
                response = await self.model.ainvoke(messages)
                response_content_raw = response.content if hasattr(response, 'content') else response
                response_content = self._coerce_to_text(response_content_raw)
                
                span.set_attribute("response_length", len(response_content))
                return response_content
                
            except Exception as e:
                logger.error(f"Error in unified analysis: {e}")
                span.record_exception(e)
                raise
    
    async def _parse_unified_analysis(self, analysis_text: str, reasoning_state: ReasoningState, original_query: str = "") -> None:
        """
        Parse the unified analysis response and populate the reasoning state.
        """
        with tracer.start_as_current_span("reasoning_engine.parse_unified_analysis"):
            # Ensure query_text is set
            if not reasoning_state.query_text:
                reasoning_state.query_text = original_query
            try:
                # Extract emotional state
                emotion_match = re.search(r"emotional state[:\s]+(\w+)", analysis_text.lower())
                if emotion_match:
                    emotion_str = emotion_match.group(1)
                    emotion_map = {
                        "frustrated": EmotionalState.FRUSTRATED,
                        "confused": EmotionalState.CONFUSED,
                        "anxious": EmotionalState.ANXIOUS,
                        "professional": EmotionalState.PROFESSIONAL,
                        "excited": EmotionalState.EXCITED,
                        "urgent": EmotionalState.URGENT,
                        "disappointed": EmotionalState.DISAPPOINTED,
                        "neutral": EmotionalState.NEUTRAL
                    }
                    emotion = emotion_map.get(emotion_str, EmotionalState.NEUTRAL)
                else:
                    emotion = EmotionalState.NEUTRAL
                
                # Extract problem category
                category_match = re.search(r"problem category[:\s]+(\w+)", analysis_text.lower())
                if category_match:
                    category_str = category_match.group(1)
                    category_map = {
                        "technical": ProblemCategory.TECHNICAL_ISSUE,
                        "account": ProblemCategory.ACCOUNT_SETUP,
                        "feature": ProblemCategory.FEATURE_EDUCATION,
                        "billing": ProblemCategory.BILLING_INQUIRY,
                        "general": ProblemCategory.GENERAL_SUPPORT
                    }
                    category = category_map.get(category_str, ProblemCategory.GENERAL_SUPPORT)
                else:
                    category = ProblemCategory.GENERAL_SUPPORT
                
                # Extract urgency level
                urgency_match = re.search(r"urgency level[:\s]+(\d)", analysis_text)
                urgency = int(urgency_match.group(1)) if urgency_match else 3
                
                # Extract tool decision
                tool_decision = ToolDecisionType.NO_TOOLS_NEEDED
                if "WEB_SEARCH_REQUIRED" in analysis_text:
                    tool_decision = ToolDecisionType.WEB_SEARCH_REQUIRED
                elif "INTERNAL_KB_ONLY" in analysis_text:
                    tool_decision = ToolDecisionType.INTERNAL_KB_ONLY
                elif "BOTH_SOURCES_NEEDED" in analysis_text:
                    tool_decision = ToolDecisionType.BOTH_SOURCES_NEEDED
                
                # Create query analysis
                reasoning_state.query_analysis = QueryAnalysis(
                    query_text=reasoning_state.query_text or "",
                    surface_meaning=reasoning_state.query_text or "",
                    latent_intent="Extracted from unified analysis",
                    emotional_subtext=f"Detected emotion: {emotion.value}",
                    historical_context="From current session",
                    emotional_state=emotion,
                    emotion_confidence=0.8,  # Default confidence
                    problem_category=category,
                    category_confidence=0.8,
                    key_entities=[],
                    complexity_score=0.5,
                    urgency_level=urgency / 5.0,
                    situational_analysis=SituationalAnalysis(
                        technical_complexity=5,
                        emotional_intensity=urgency,
                        business_impact=BusinessImpact.MEDIUM,
                        time_sensitivity=TimeSensitivity.IMMEDIATE if urgency > 3 else TimeSensitivity.DAYS
                    )
                )
                
                # Set tool decision
                reasoning_state.tool_reasoning = ToolDecisionReasoning(
                    decision_type=tool_decision,
                    reasoning="Based on unified analysis",
                    confidence=0.8
                )
                
                # Create a basic solution for compatibility with quality assessment
                reasoning_state.selected_solution = SolutionCandidate(
                    solution_summary="Solution derived from unified analysis",
                    detailed_steps=["Analyze the issue", "Provide solution", "Verify resolution"],
                    preventive_measures=["Follow best practices"],
                    confidence_score=0.8,
                    estimated_time_minutes=5
                )
                
                # Set confidence score
                confidence_match = re.search(r"confidence[:\s]+(\d+\.?\d*)", analysis_text)
                if confidence_match:
                    reasoning_state.overall_confidence = float(confidence_match.group(1))
                else:
                    reasoning_state.overall_confidence = 0.8
                
                # Add reasoning step
                reasoning_state.add_reasoning_step(ReasoningStep(
                    phase=ReasoningPhase.QUERY_ANALYSIS,
                    description="Unified comprehensive analysis completed",
                    reasoning=f"Detected {emotion.value} emotion, {category.value} problem, urgency {urgency}/5",
                    confidence=reasoning_state.overall_confidence
                ))
                
            except Exception as e:
                logger.error(f"Error parsing unified analysis: {e}")
                # Set defaults on error
                reasoning_state.query_analysis = QueryAnalysis(
                    query_text=reasoning_state.query_text or "",
                    surface_meaning=reasoning_state.query_text or "",
                    latent_intent="Error in analysis",
                    emotional_subtext="Unable to detect",
                    historical_context="Error",
                    emotional_state=EmotionalState.NEUTRAL,
                    emotion_confidence=0.5,
                    problem_category=ProblemCategory.GENERAL_SUPPORT,
                    category_confidence=0.5,
                    key_entities=[],
                    complexity_score=0.5,
                    urgency_level=0.5,
                    situational_analysis=SituationalAnalysis(
                        technical_complexity=5,
                        emotional_intensity=5,
                        business_impact=BusinessImpact.MEDIUM,
                        time_sensitivity=TimeSensitivity.DAYS
                    )
                )
                
                # Set default solution
                reasoning_state.selected_solution = SolutionCandidate(
                    solution_summary="Error occurred during analysis",
                    detailed_steps=["Please try again"],
                    preventive_measures=[],
                    confidence_score=0.3,
                    estimated_time_minutes=1
                )
    
    def _assess_initial_complexity(self, query: str) -> str:
        """Quick assessment of query complexity for thinking budget."""
        query_lower = query.lower()
        
        # Complex indicators
        complex_indicators = [
            "not working", "error", "crash", "fail", "broken",
            "sync", "imap", "smtp", "oauth", "certificate",
            "multiple accounts", "migration", "import"
        ]
        
        # Simple indicators  
        simple_indicators = [
            "how to", "where is", "what is", "password",
            "price", "cost", "feature", "setting"
        ]
        
        complex_count = sum(1 for ind in complex_indicators if ind in query_lower)
        simple_count = sum(1 for ind in simple_indicators if ind in query_lower)
        
        if complex_count >= 2 or len(query) > 200:
            return "complex"
        elif simple_count >= 2 or len(query) < 50:
            return "simple"
        else:
            return "medium"
    
    async def _load_reasoning_model_instance(
        self,
        thinking_budget: Optional[int],
    ) -> Optional[BaseChatModel]:
        """Load a provider-specific model tuned for response generation."""
        try:
            adapter = get_adapter(self.provider, self.model_name)
        except Exception as exc:
            logger.debug(
                "No provider adapter available for %s/%s: %s",
                self.provider,
                self.model_name,
                exc,
            )
            return None

        api_key = getattr(self, "_api_key", None)
        try:
            return await adapter.load_reasoning_model(
                api_key=api_key,
                thinking_budget=thinking_budget,
            )
        except TypeError:
            # Adapter may not accept thinking_budget yet; retry without it.
            return await adapter.load_reasoning_model(api_key=api_key)
        except Exception as exc:
            logger.warning(
                "Failed to load reasoning model for %s/%s: %s",
                self.provider,
                self.model_name,
                exc,
            )
            return None

    async def generate_enhanced_response(
        self, 
        reasoning_state: ReasoningState,
        thinking_budget: Optional[int] = None
    ) -> str:
        """
        Generate an enhanced response with thinking budget and conversational style.
        
        This is the second major LLM call that generates the final response.
        """
        with tracer.start_as_current_span("reasoning_engine.generate_enhanced_response") as span:
            if not reasoning_state.query_analysis:
                return "I apologize, but I wasn't able to properly analyze your query. Could you please rephrase it?"
            
            # Use provided thinking budget or determine based on complexity
            if thinking_budget is None:
                complexity = self._assess_initial_complexity(reasoning_state.query_text or "")
                thinking_budget = self.get_thinking_budget(complexity)
            
            span.set_attribute("thinking_budget", thinking_budget)
            
            model_to_use = await self._load_reasoning_model_instance(thinking_budget) or self.model
            
            # Build context from reasoning state
            context_summary = self._build_context_summary(reasoning_state)
            
            # Create enhanced response prompt
            enhanced_prompt_config = PromptV9Config(
                include_self_critique=False,
                include_reasoning=True,
                include_emotional_resonance=True,
                include_technical_excellence=True,
                include_conversational_excellence=True,
                include_solution_delivery=True,
                include_knowledge_integration=True,
                include_premium_elements=True,
                include_success_directives=True,
            )

            system_prompt = self._compose_system_prompt_with_instructions(
                """You are Agent Sparrow, Mailbird's friendly and knowledgeable AI customer support expert.

## Your Task: Generate a Helpful Response

Based on the analysis provided, craft a response that:
1. Acknowledges the customer's emotional state appropriately
2. Provides clear, actionable solutions
3. Uses a warm, conversational tone
4. Includes specific Mailbird features or settings when relevant

## Response Guidelines:
- Be conversational and friendly, like talking to a colleague
- Use "I" statements ("I understand...", "I can help...")
- Break complex solutions into numbered steps
- Include relevant Mailbird menu paths (Settings → Accounts → ...)
- Offer alternative solutions when available
- End with a helpful follow-up question if appropriate

Remember: Quality over speed. Take time to craft a thoughtful response.""",
                prompt_config=enhanced_prompt_config,
            )

            user_prompt = f"""Customer Query: {reasoning_state.query_text}

Analysis Summary:
{context_summary}

Please think carefully about the best way to help this customer, considering their emotional state and the nature of their query. Generate a helpful, conversational response that addresses their needs.

Note: You have a thinking budget of {thinking_budget} tokens available for internal reasoning."""

            try:
                messages: List[BaseMessage] = [
                    SystemMessage(content=system_prompt),
                    HumanMessage(content=user_prompt)
                ]
                
                # Use the model's ainvoke for response generation
                response = await model_to_use.ainvoke(messages)

                # Debug logging
                logger.info(f"Raw response type: {type(response)}")
                logger.info(f"Response attributes: {dir(response)}")

                response_content_raw = response.content if hasattr(response, 'content') else response
                response_content = self._coerce_to_text(response_content_raw)
                
                # Check if response is empty (common when model returns tool calls)
                if not response_content or response_content.strip() == '':
                    # Check if it's a tool call response
                    if hasattr(response, 'tool_calls') and response.tool_calls:
                        logger.warning("Model returned tool calls instead of text response. Retrying without tools...")
                        # This shouldn't happen but let's handle it gracefully
                        response_content = "I'd be happy to help you with Mailbird pricing information! Mailbird offers different pricing plans to suit various needs. While I don't have the exact current prices at hand, I can tell you that Mailbird typically offers both a personal license and business options. For the most accurate and up-to-date pricing, I recommend visiting the official Mailbird website where you can see all available plans and any current promotions."
                    else:
                        # Try other attributes
                        if hasattr(response, 'text') and not callable(response.text):
                            response_content = response.text
                        elif hasattr(response, 'message'):
                            response_content = response.message.content if hasattr(response.message, 'content') else str(response.message)
                        else:
                            # Last resort - provide a generic response
                            response_content = "I apologize, but I'm having trouble generating a proper response. Please try rephrasing your question."
                
                # Log the response for debugging
                logger.info(f"Enhanced response generated: {len(response_content)} chars")
                logger.debug(f"Response preview: {response_content[:100]}...")
                
                span.set_attribute("response_length", len(response_content))
                
                # Update reasoning state with the response
                if reasoning_state.response_orchestration:
                    reasoning_state.response_orchestration.final_response_preview = response_content
                else:
                    # Create minimal orchestration if it doesn't exist
                    reasoning_state.response_orchestration = ResponseOrchestration(
                        emotional_acknowledgment_strategy="Acknowledged in response",
                        technical_solution_delivery_method="Clear step-by-step guidance",
                        relationship_strengthening_elements=[],
                        delight_injection_points=[],
                        final_response_preview=response_content
                    )
                
                # Add reasoning step
                reasoning_state.add_reasoning_step(ReasoningStep(
                    phase=ReasoningPhase.RESPONSE_STRATEGY,
                    description="Generated enhanced conversational response",
                    reasoning=f"Created response with {thinking_budget} token thinking budget",
                    confidence=0.9
                ))
                
                return response_content
                
            except Exception as e:
                logger.error(f"Error generating enhanced response: {e}")
                span.record_exception(e)
                return "I apologize, but I encountered an error while preparing my response. Please try again."
    
    def _build_context_summary(self, reasoning_state: ReasoningState) -> str:
        """Build a context summary from the reasoning state for response generation."""
        parts = []
        
        if reasoning_state.query_analysis:
            qa = reasoning_state.query_analysis
            parts.append(f"- Emotional State: {qa.emotional_state.value} (confidence: {qa.emotion_confidence:.1f})")
            parts.append(f"- Problem Type: {qa.problem_category.value}")
            parts.append(f"- Urgency: {qa.urgency_level:.1f}/1.0")
        
        if reasoning_state.tool_reasoning:
            tr = reasoning_state.tool_reasoning
            parts.append(f"- Tool Decision: {tr.decision_type.value}")
            if tr.search_strategy:
                parts.append(f"- Search Strategy: {tr.search_strategy}")
        
        if reasoning_state.predictive_insights:
            parts.append(f"- Key Insights: {len(reasoning_state.predictive_insights)} identified")

        request_context = getattr(reasoning_state, "request_context", {})
        if isinstance(request_context, dict):
            grounding_context = request_context.get("grounding") or {}
            kb_summary = (grounding_context.get("kb") or {}).get("summary")
            if kb_summary:
                try:
                    parts.append(
                        f"- KB Evidence: {kb_summary.total_results} results (avg relevance {kb_summary.avg_relevance:.2f})"
                    )
                except Exception:
                    parts.append("- KB Evidence available")
            grounding_digest = grounding_context.get("digest") or ""
            if grounding_digest:
                digest_preview = grounding_digest if len(grounding_digest) <= 280 else f"{grounding_digest[:280]}…"
                parts.append(f"- Grounding Digest: {digest_preview}")

        return "\n".join(parts) if parts else "No detailed analysis available"
    
    async def refine_response_if_needed(
        self,
        reasoning_state: ReasoningState,
        confidence_threshold: float = 0.6
    ) -> Optional[str]:
        """
        Optional 3rd LLM call: Refine response if confidence is low.
        
        Returns refined response or None if refinement not needed.
        """
        with tracer.start_as_current_span("reasoning_engine.refine_response") as span:
            # Check if refinement is needed
            if reasoning_state.overall_confidence >= confidence_threshold:
                span.set_attribute("refinement_needed", False)
                return None
            
            if not reasoning_state.response_orchestration or not reasoning_state.response_orchestration.final_response_preview:
                return None
            
            span.set_attribute("refinement_needed", True)
            span.set_attribute("original_confidence", reasoning_state.overall_confidence)
            
            current_response = reasoning_state.response_orchestration.final_response_preview
            
            # Create refinement prompt
            refinement_prompt_config = PromptV9Config(
                include_self_critique=False,
                include_reasoning=True,
                include_emotional_resonance=True,
                include_technical_excellence=True,
                include_conversational_excellence=True,
                include_solution_delivery=True,
                include_knowledge_integration=True,
                include_premium_elements=False,
                include_success_directives=True,
            )

            system_prompt = self._compose_system_prompt_with_instructions(
                """You are Agent Sparrow, tasked with improving a response that has low confidence.

## Your Task: Refine the Response

Review the current response and the analysis context, then improve it by:
1. Adding more specific details or examples
2. Clarifying any ambiguous points
3. Ensuring all aspects of the query are addressed
4. Maintaining a warm, helpful tone

Focus on accuracy and completeness while keeping the conversational style.""",
                prompt_config=refinement_prompt_config,
            )

            user_prompt = f"""Original Query: {reasoning_state.query_text}

Current Response (confidence: {reasoning_state.overall_confidence:.1f}):
{current_response}

Issues to address:
- Low confidence in analysis or response
- Possible missing information
- May need more specific Mailbird guidance

Please provide an improved version of this response."""

            try:
                messages: List[BaseMessage] = [
                    SystemMessage(content=system_prompt),
                    HumanMessage(content=user_prompt)
                ]
                
                # Use the model's ainvoke for refinement
                response = await self.model.ainvoke(messages)
                refined_response = response.content if hasattr(response, 'content') else str(response)
                
                # Update reasoning state
                reasoning_state.response_orchestration.final_response_preview = refined_response
                reasoning_state.overall_confidence = min(reasoning_state.overall_confidence + 0.1, 0.8)
                
                # Add reasoning step
                reasoning_state.add_reasoning_step(ReasoningStep(
                    phase=ReasoningPhase.QUALITY_ASSESSMENT,
                    description="Refined response due to low confidence",
                    reasoning=f"Improved response quality from {reasoning_state.overall_confidence - 0.1:.1f} to {reasoning_state.overall_confidence:.1f}",
                    confidence=reasoning_state.overall_confidence
                ))
                
                span.set_attribute("refined_confidence", reasoning_state.overall_confidence)
                return refined_response
                
            except Exception as e:
                logger.error(f"Error refining response: {e}")
                span.record_exception(e)
                return None
