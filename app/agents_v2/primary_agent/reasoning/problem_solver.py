"""
Agent Sparrow - Problem Solving Framework

This module implements the sophisticated 5-step problem-solving framework
for systematic analysis and solution generation with multi-step reasoning
and comprehensive solution candidate development.
"""

import logging
import asyncio
from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime
import uuid

from .schemas import (
    SolutionCandidate,
    ProblemSolvingPhase,
    ProblemCategory,
    ReasoningConfig
)
from app.agents_v2.primary_agent.prompts.emotion_templates import EmotionalState

logger = logging.getLogger(__name__)


class ProblemSolvingFramework:
    """
    Sophisticated 5-step problem solving framework for Agent Sparrow
    
    Implements systematic approach to complex problem resolution:
    Step 1: Problem Definition
    Step 2: Information Gathering
    Step 3: Hypothesis Generation
    Step 4: Solution Implementation
    Step 5: Verification & Prevention
    """
    
    def __init__(self, config: ReasoningConfig):
        """
        Initialize the ProblemSolvingFramework with the provided reasoning configuration.
        
        Associates each problem category with its corresponding solution template method for structured solution generation.
        """
        self.config = config
        
        # Solution templates by problem category
        self.solution_templates = {
            ProblemCategory.TECHNICAL_ISSUE: self._technical_solution_templates,
            ProblemCategory.ACCOUNT_SETUP: self._account_setup_templates,
            ProblemCategory.FEATURE_EDUCATION: self._feature_education_templates,
            ProblemCategory.BILLING_INQUIRY: self._billing_inquiry_templates,
            ProblemCategory.PERFORMANCE_OPTIMIZATION: self._performance_templates,
            ProblemCategory.TROUBLESHOOTING: self._troubleshooting_templates,
            ProblemCategory.GENERAL_SUPPORT: self._general_support_templates
        }
    
    async def generate_solution_candidates(
        self,
        problem_category: ProblemCategory,
        emotional_state: EmotionalState,
        urgency_level: int,
        complexity_score: float,
        key_entities: List[str],
        query_text: str
    ) -> List[SolutionCandidate]:
        """
        Asynchronously generates and ranks solution candidates for a given problem using a structured 5-step problem-solving framework.
        
        This method analyzes the problem context, gathers relevant information, generates hypotheses, plans solution implementations using category-specific templates, and enhances each solution with verification, prevention, and risk assessment. The resulting solution candidates are ranked by confidence and appropriateness, and the top candidates are returned.
        
        Parameters:
            problem_category (ProblemCategory): The categorized type of the problem.
            emotional_state (EmotionalState): The customer's emotional state.
            urgency_level (int): The urgency of the problem on a scale from 1 to 5.
            complexity_score (float): The complexity of the problem on a scale from 0 to 1.
            key_entities (List[str]): Key entities extracted from the query.
            query_text (str): The original query text.
        
        Returns:
            List[SolutionCandidate]: A list of ranked solution candidates tailored to the problem context.
        """
        
        logger.info(f"Generating solutions for {problem_category.value} with urgency {urgency_level}")
        
        # Step 1: Problem Definition
        problem_definition = await self._define_problem(
            problem_category, emotional_state, urgency_level, complexity_score, key_entities, query_text
        )
        
        # Step 2: Information Gathering
        information_analysis = await self._gather_information(
            problem_definition, key_entities, query_text
        )
        
        # Step 3: Hypothesis Generation
        hypotheses = await self._generate_hypotheses(
            problem_definition, information_analysis, problem_category
        )
        
        # Step 4: Solution Implementation Planning
        solution_candidates = await self._plan_solution_implementations(
            hypotheses, problem_category, emotional_state, urgency_level, complexity_score
        )
        
        # Step 5: Verification & Prevention Integration
        enhanced_solutions = await self._enhance_with_verification(
            solution_candidates, problem_category
        )
        
        # Rank solutions by confidence and appropriateness
        ranked_solutions = self._rank_solutions(
            enhanced_solutions, emotional_state, urgency_level, complexity_score
        )
        
        # Limit to max candidates
        return ranked_solutions[:self.config.max_solution_candidates]
    
    async def _define_problem(
        self,
        problem_category: ProblemCategory,
        emotional_state: EmotionalState,
        urgency_level: int,
        complexity_score: float,
        key_entities: List[str],
        query_text: str
    ) -> Dict[str, Any]:
        """
        Constructs a comprehensive problem definition dictionary based on the provided context.
        
        The returned dictionary includes the problem category, extracted symptoms from the query, identified affected systems, user impact assessment, problem scope, and relevant constraints.
         
        Returns:
            dict: A dictionary containing detailed problem definition fields for downstream reasoning steps.
        """
        
        problem_definition = {
            'category': problem_category,
            'primary_symptoms': self._extract_symptoms(query_text),
            'affected_systems': self._identify_affected_systems(key_entities),
            'user_impact': self._assess_user_impact(emotional_state, urgency_level),
            'scope': self._determine_problem_scope(complexity_score, key_entities),
            'constraints': self._identify_constraints(emotional_state, urgency_level)
        }
        
        logger.debug(f"Problem definition: {problem_definition}")
        return problem_definition
    
    async def _gather_information(
        self,
        problem_definition: Dict[str, Any],
        key_entities: List[str],
        query_text: str
    ) -> Dict[str, Any]:
        """
        Collects and organizes relevant information needed to analyze the defined problem.
        
        Returns a dictionary containing known factors, missing information, context clues, similar cases, and relevant documentation references based on the problem definition, key entities, and query text.
        """
        
        information_analysis = {
            'known_factors': self._identify_known_factors(problem_definition, key_entities),
            'missing_information': self._identify_missing_information(problem_definition),
            'context_clues': self._extract_context_clues(query_text),
            'similar_cases': self._find_similar_cases(problem_definition),
            'relevant_documentation': self._identify_relevant_docs(problem_definition)
        }
        
        return information_analysis
    
    async def _generate_hypotheses(
        self,
        problem_definition: Dict[str, Any],
        information_analysis: Dict[str, Any],
        problem_category: ProblemCategory
    ) -> List[Dict[str, Any]]:
        """
        Generates a ranked list of hypotheses for the given problem, assigning probabilities and confidence levels to primary, alternative, and edge case scenarios.
        
        Parameters:
            problem_definition (Dict[str, Any]): Structured details of the defined problem.
            information_analysis (Dict[str, Any]): Collected and analyzed information relevant to the problem.
            problem_category (ProblemCategory): The category of the problem being addressed.
        
        Returns:
            List[Dict[str, Any]]: A list of hypothesis dictionaries, each containing the hypothesis, its probability, confidence score, and type (primary, alternative, or edge case).
        """
        
        hypotheses = []
        
        # Primary hypothesis (80% probability)
        primary_hypothesis = self._generate_primary_hypothesis(
            problem_definition, information_analysis, problem_category
        )
        hypotheses.append({
            'hypothesis': primary_hypothesis,
            'probability': 0.8,
            'confidence': 0.8,
            'type': 'primary'
        })
        
        # Alternative hypothesis (15% probability)
        alternative_hypothesis = self._generate_alternative_hypothesis(
            problem_definition, information_analysis, problem_category
        )
        if alternative_hypothesis:
            hypotheses.append({
                'hypothesis': alternative_hypothesis,
                'probability': 0.15,
                'confidence': 0.6,
                'type': 'alternative'
            })
        
        # Edge case hypothesis (5% probability)
        edge_case_hypothesis = self._generate_edge_case_hypothesis(
            problem_definition, information_analysis, problem_category
        )
        if edge_case_hypothesis:
            hypotheses.append({
                'hypothesis': edge_case_hypothesis,
                'probability': 0.05,
                'confidence': 0.4,
                'type': 'edge_case'
            })
        
        return hypotheses
    
    async def _plan_solution_implementations(
        self,
        hypotheses: List[Dict[str, Any]],
        problem_category: ProblemCategory,
        emotional_state: EmotionalState,
        urgency_level: int,
        complexity_score: float
    ) -> List[SolutionCandidate]:
        """
        Generates solution candidates for each hypothesis using category-specific templates.
        
        For each hypothesis, selects the appropriate solution template based on the problem category and asynchronously generates a `SolutionCandidate` tailored to the hypothesis and contextual factors.
        
        Returns:
            List[SolutionCandidate]: A list of generated solution candidates for the provided hypotheses.
        """
        
        solution_candidates = []
        
        for hypothesis in hypotheses:
            # Get solution template for this category
            template_func = self.solution_templates.get(problem_category, self._general_support_templates)
            
            # Generate solution based on hypothesis
            solution = await template_func(
                hypothesis, emotional_state, urgency_level, complexity_score
            )
            
            if solution:
                solution_candidates.append(solution)
        
        return solution_candidates
    
    async def _enhance_with_verification(
        self,
        solution_candidates: List[SolutionCandidate],
        problem_category: ProblemCategory
    ) -> List[SolutionCandidate]:
        """
        Enhance solution candidates by adding verification steps, prevention measures, risk assessments, and fallback options.
        
        Each solution is updated with success indicators, appended prevention guidance, identified risk factors, and generated fallback options if not already present.
        
        Returns:
            List[SolutionCandidate]: The list of enhanced solution candidates.
        """
        
        enhanced_solutions = []
        
        for solution in solution_candidates:
            # Add verification steps
            solution.success_indicators = self._generate_success_indicators(solution, problem_category)
            
            # Add prevention measures
            prevention_measures = self._generate_prevention_measures(solution, problem_category)
            if prevention_measures:
                # Prevention measures are now handled in SolutionCandidate.preventive_measures
                pass
            
            # Add risk assessment
            solution.risk_factors = self._assess_solution_risks(solution, problem_category)
            
            # Add fallback options
            if not solution.fallback_options:
                solution.fallback_options = self._generate_fallback_options(solution, problem_category)
            
            enhanced_solutions.append(solution)
        
        return enhanced_solutions
    
    # Solution template methods for different problem categories
    
    async def _technical_solution_templates(
        self,
        hypothesis: Dict[str, Any],
        emotional_state: EmotionalState,
        urgency_level: int,
        complexity_score: float
    ) -> SolutionCandidate:
        """
        Generate a solution candidate for technical issues such as connection, synchronization, or performance problems based on the provided hypothesis and user context.
        
        Selects and customizes a stepwise solution approach according to the hypothesis content, urgency level, and emotional state, returning a detailed solution candidate with summary, approach, expected outcome, confidence score, estimated resolution time, and required tools.
        
        Returns:
            SolutionCandidate: A structured solution candidate tailored to the technical issue described in the hypothesis.
        """
        
        base_solutions = {
            'connection_issue': {
                'summary': 'Resolve Email Connection Problem',
                'approach': """1. **Verify Account Settings**
   - Check server settings (IMAP/SMTP)
   - Verify port numbers and security settings
   - Test connection in account settings

2. **Authentication Troubleshooting**
   - Update app-specific password if using 2FA
   - Check OAuth 2.0 authorization status
   - Re-authenticate account if necessary

3. **Network and Firewall Check**
   - Verify internet connection stability
   - Check firewall/antivirus email blocking
   - Test with different network if possible""",
                'time': 15,
                'confidence': 0.85
            },
            'sync_issue': {
                'summary': 'Fix Email Synchronization Issues',
                'approach': """1. **Force Manual Sync**
   - Right-click account → "Sync Now"
   - Check sync status indicators
   - Monitor for error messages

2. **Sync Settings Optimization**
   - Adjust sync frequency settings
   - Enable/disable IMAP IDLE
   - Configure folder sync preferences

3. **Account Refresh**
   - Remove and re-add account if needed
   - Clear local cache and restart
   - Verify server-side email accessibility""",
                'time': 20,
                'confidence': 0.8
            },
            'performance_issue': {
                'summary': 'Optimize Mailbird Performance',
                'approach': """1. **Resource Optimization**
   - Close unnecessary applications
   - Restart Mailbird application
   - Check available system memory

2. **Configuration Tuning**
   - Reduce sync frequency for large accounts
   - Disable unnecessary app integrations
   - Optimize attachment handling settings

3. **System Maintenance**
   - Clear application cache
   - Update to latest Mailbird version
   - Check for Windows/macOS updates""",
                'time': 25,
                'confidence': 0.75
            }
        }
        
        # Define issue type mappings with their associated keywords
        issue_type_mappings = {
            'connection_issue': ['connection', 'connect', 'server', 'authentication'],
            'sync_issue': ['sync', 'synchronization', 'folder', 'emails missing'],
            'performance_issue': ['slow', 'performance', 'crash', 'freeze']
        }
        
        # Select most appropriate solution based on hypothesis
        hypothesis_text = hypothesis['hypothesis'].lower()
        solution_key = 'connection_issue'  # Default fallback
        
        # Find the first matching issue type
        for issue_type, keywords in issue_type_mappings.items():
            if any(term in hypothesis_text for term in keywords):
                solution_key = issue_type
                break
                
        solution_data = base_solutions[solution_key]
        
        # Adjust for urgency and emotion
        if urgency_level >= 4:
            solution_data['time'] = max(solution_data['time'] - 5, 5)  # Faster approach
        
        if emotional_state == EmotionalState.FRUSTRATED:
            solution_data['confidence'] += 0.05  # Be more confident
        
        # Create detailed steps as a proper list
        if isinstance(solution_data['approach'], str):
            # Split by numbered steps and clean up
            steps = [step.strip() for step in solution_data['approach'].split('\n') if step.strip() and not step.strip().startswith('**')]
            detailed_steps = steps[:5] if len(steps) > 5 else steps  # Limit to reasonable number
        else:
            detailed_steps = solution_data['approach']
        
        return SolutionCandidate(
            solution_summary=solution_data['summary'],
            detailed_steps=detailed_steps or ["Analyze the issue", "Apply appropriate solution", "Verify resolution"],
            preventive_measures=["Regularly check email server settings", "Monitor connection stability"],
            confidence_score=min(solution_data['confidence'] * hypothesis['confidence'], 1.0),
            estimated_time_minutes=solution_data['time'],
            required_tools=['internal_knowledge', 'configuration_access']
        )
    
    async def _account_setup_templates(
        self,
        hypothesis: Dict[str, Any],
        emotional_state: EmotionalState,
        urgency_level: int,
        complexity_score: float
    ) -> SolutionCandidate:
        """
        Generates a detailed solution candidate for completing an email account setup process.
        
        Parameters:
            hypothesis (Dict[str, Any]): The hypothesis guiding the solution approach, typically describing the likely account setup issue.
        
        Returns:
            SolutionCandidate: A structured solution outlining step-by-step account setup, including both automatic and manual configuration, expected outcomes, estimated time, and required tools.
        """
        
        return SolutionCandidate(
            solution_summary="Complete Email Account Setup",
            detailed_steps=[
                "Collect email address and password",
                "Use Mailbird's auto-setup feature", 
                "Input IMAP/SMTP settings manually if needed",
                "Configure sync preferences",
                "Test send/receive functionality"
            ],
            preventive_measures=["Keep credentials secure", "Regular account maintenance"],
            confidence_score=0.9,
            estimated_time_minutes=10,
            required_tools=['account_credentials', 'server_settings']
        )
    
    async def _feature_education_templates(
        self,
        hypothesis: Dict[str, Any],
        emotional_state: EmotionalState,
        urgency_level: int,
        complexity_score: float
    ) -> SolutionCandidate:
        """
        Generates a solution candidate focused on educating the user about a specific Mailbird feature.
        
        Returns:
            SolutionCandidate: A detailed, step-by-step educational plan including tutorials, practical examples, advanced tips, and troubleshooting guidance to help the user master and integrate the feature into their workflow.
        """
        
        return SolutionCandidate(
            solution_summary="Master Mailbird Feature Usage",
            detailed_steps="""1. **Feature Discovery**
   - Identify the specific feature of interest
   - Locate feature in Mailbird interface
   - Understand feature capabilities and benefits

2. **Step-by-Step Tutorial**
   - Provide detailed usage instructions
   - Include visual cues and navigation tips
   - Explain customization options

3. **Practical Application**
   - Demonstrate with real-world examples
   - Show integration with workflow
   - Highlight productivity benefits

4. **Advanced Tips and Optimization**
   - Share power-user techniques
   - Explain related features
   - Provide troubleshooting tips""",
            confidence_score=0.95,
            estimated_time_minutes=15,
            required_tools=['feature_documentation', 'tutorials']
        )
    
    async def _billing_inquiry_templates(
        self,
        hypothesis: Dict[str, Any],
        emotional_state: EmotionalState,
        urgency_level: int,
        complexity_score: float
    ) -> SolutionCandidate:
        """
        Generate a solution candidate for billing inquiries, addressing account review, pricing clarification, issue resolution, and future billing prevention.
        
        Returns:
            SolutionCandidate: A structured solution for resolving billing-related questions and issues, including steps for review, clarification, resolution, and prevention.
        """
        
        return SolutionCandidate(
            solution_summary="Resolve Billing Questions and Issues",
            detailed_steps="""1. **Account and Billing Review**
   - Verify current subscription status
   - Review billing history and charges
   - Identify specific billing concern

2. **Pricing and Plan Clarification**
   - Explain current pricing structure
   - Compare available plans and features
   - Clarify billing cycles and payments

3. **Issue Resolution**
   - Address specific billing problems
   - Process refunds or adjustments if applicable
   - Update payment methods or billing info

4. **Future Billing Prevention**
   - Set up billing notifications
   - Explain renewal and cancellation policies
   - Provide account management resources""",
            confidence_score=0.8,
            estimated_time_minutes=12,
            required_tools=['billing_system', 'account_access', 'current_pricing']
        )
    
    async def _performance_templates(
        self,
        hypothesis: Dict[str, Any],
        emotional_state: EmotionalState,
        urgency_level: int,
        complexity_score: float
    ) -> SolutionCandidate:
        """
        Generate a solution candidate focused on optimizing Mailbird's performance based on the provided hypothesis and contextual factors.
        
        Returns:
            SolutionCandidate: A structured plan detailing assessment, configuration, system improvements, and maintenance steps to enhance Mailbird's speed and efficiency.
        """
        
        return SolutionCandidate(
            solution_summary="Optimize Mailbird Performance",
            detailed_steps="""1. **Performance Assessment**
   - Analyze current system resource usage
   - Identify performance bottlenecks
   - Measure baseline performance metrics

2. **Configuration Optimization**
   - Adjust sync settings for large accounts
   - Optimize attachment handling
   - Configure efficient folder management

3. **System-Level Improvements**
   - Free up system resources
   - Update Mailbird to latest version
   - Configure optimal memory settings

4. **Monitoring and Maintenance**
   - Set up performance monitoring
   - Establish regular maintenance routine
   - Plan for future scalability""",
            confidence_score=0.8,
            estimated_time_minutes=20,
            required_tools=['system_diagnostics', 'performance_tools']
        )
    
    async def _troubleshooting_templates(
        self,
        hypothesis: Dict[str, Any],
        emotional_state: EmotionalState,
        urgency_level: int,
        complexity_score: float
    ) -> SolutionCandidate:
        """
        Generates a structured troubleshooting solution candidate for general problem scenarios.
        
        The returned solution outlines a stepwise approach for isolating, testing, and resolving issues, including verification and documentation steps. The plan is tailored for systematic diagnosis and resolution, with an estimated time and required tools specified.
        
        Returns:
            SolutionCandidate: A detailed troubleshooting plan with summary, approach, expected outcome, confidence score, estimated time, and required tools.
        """
        
        return SolutionCandidate(
            solution_summary="Systematic Problem Troubleshooting",
            detailed_steps="""1. **Problem Isolation**
   - Reproduce the issue consistently
   - Identify specific error messages
   - Determine affected functionality

2. **Systematic Testing**
   - Test with different accounts
   - Try alternative workflows
   - Check system and network factors

3. **Progressive Solution Application**
   - Apply least invasive fixes first
   - Escalate to more comprehensive solutions
   - Document what works and what doesn't

4. **Verification and Documentation**
   - Confirm issue resolution
   - Document solution for future reference
   - Implement preventive measures""",
            confidence_score=0.75,
            estimated_time_minutes=25,
            required_tools=['diagnostic_tools', 'system_access']
        )
    
    async def _general_support_templates(
        self,
        hypothesis: Dict[str, Any],
        emotional_state: EmotionalState,
        urgency_level: int,
        complexity_score: float
    ) -> SolutionCandidate:
        """
        Generates a comprehensive general support solution candidate based on the provided hypothesis and user context.
        
        Returns:
            SolutionCandidate: A structured support plan including needs assessment, tailored guidance, implementation support, and follow-up, with estimated time and required resources.
        """
        
        return SolutionCandidate(
            solution_summary="Comprehensive Support Assistance",
            detailed_steps=[
                "Clarify specific requirements and understand user goals",
                "Provide relevant information and step-by-step assistance", 
                "Walk through solutions with troubleshooting support",
                "Confirm satisfaction and provide additional resources"
            ],
            preventive_measures=[
                "Establish clear communication channels",
                "Document solutions for future reference",
                "Set up proper follow-up procedures"
            ],
            confidence_score=0.7,
            estimated_time_minutes=18,
            required_tools=['knowledge_base', 'support_resources']
        )
    
    # Helper methods
    
    def _extract_symptoms(self, query_text: str) -> List[str]:
        """
        Extracts symptom indicators from the query text based on predefined keywords.
        
        Parameters:
            query_text (str): The user's query describing the problem.
        
        Returns:
            List[str]: A list of detected symptom keywords present in the query.
        """
        symptoms = []
        
        symptom_indicators = [
            'not working', 'broken', 'error', 'crash', 'slow', 'freeze',
            'missing', 'disappeared', 'wrong', 'incorrect', 'failed'
        ]
        
        query_lower = query_text.lower()
        for indicator in symptom_indicators:
            if indicator in query_lower:
                symptoms.append(indicator)
        
        return symptoms
    
    def _identify_affected_systems(self, key_entities: List[str]) -> List[str]:
        """
        Identifies affected systems based on labeled entities in the provided list.
        
        Parameters:
            key_entities (List[str]): A list of entity strings labeled with prefixes such as 'email_provider:', 'feature:', or 'error:'.
        
        Returns:
            List[str]: A list of human-readable descriptions of affected systems derived from the input entities.
        """
        systems = []
        
        for entity in key_entities:
            if 'email_provider:' in entity:
                systems.append(f"Email service: {entity.split(':')[1]}")
            elif 'feature:' in entity:
                systems.append(f"Mailbird feature: {entity.split(':')[1]}")
            elif 'error:' in entity:
                systems.append(f"System error: {entity.split(':')[1]}")
        
        return systems
    
    def _assess_user_impact(self, emotional_state: EmotionalState, urgency_level: int) -> str:
        """
        Evaluates and categorizes the impact of the problem on the user based on emotional state and urgency level.
        
        Returns:
            str: A description of user impact as 'High', 'Medium', or 'Low', reflecting the severity of disruption to the user's workflow.
        """
        if urgency_level >= 4 or emotional_state == EmotionalState.URGENT:
            return "High impact - blocking critical workflow"
        elif urgency_level >= 2 or emotional_state == EmotionalState.FRUSTRATED:
            return "Medium impact - causing significant inconvenience"
        else:
            return "Low impact - minor disruption to workflow"
    
    def _determine_problem_scope(self, complexity_score: float, key_entities: List[str]) -> str:
        """
        Determines the scope of a problem based on its complexity score and involved entities.
        
        Parameters:
            complexity_score (float): Numeric value representing the assessed complexity of the problem.
            key_entities (List[str]): Entities involved in or affected by the problem.
        
        Returns:
            str: A description of the problem's scope, categorized as complex, moderate, or focused.
        """
        if complexity_score > 0.8:
            return "Complex multi-system issue"
        elif complexity_score > 0.5:
            return "Moderate scope affecting multiple components"
        else:
            return "Focused issue with limited scope"
    
    def _identify_constraints(self, emotional_state: EmotionalState, urgency_level: int) -> List[str]:
        """
        Identifies constraints that should be considered when generating solutions based on the user's emotional state and urgency level.
        
        Parameters:
        	emotional_state (EmotionalState): The user's current emotional state, influencing the type of guidance needed.
        	urgency_level (int): The urgency of the problem, affecting time sensitivity.
        
        Returns:
        	List[str]: A list of constraint descriptions relevant to the solution approach.
        """
        constraints = []
        
        if urgency_level >= 4:
            constraints.append("Time-sensitive - requires immediate resolution")
        
        if emotional_state == EmotionalState.CONFUSED:
            constraints.append("Requires simple, clear instructions")
        elif emotional_state == EmotionalState.FRUSTRATED:
            constraints.append("Must provide immediate relief and clear progress")
        
        return constraints
    
    def _identify_known_factors(self, problem_definition: Dict[str, Any], key_entities: List[str]) -> List[str]:
        """
        Identifies and summarizes known factors related to the problem based on its definition and key entities.
        
        Returns:
            List of descriptive strings outlining the problem category, user impact, and affected systems if available.
        """
        known_factors = []
        
        known_factors.append(f"Problem category: {problem_definition['category'].value}")
        known_factors.append(f"User impact: {problem_definition['user_impact']}")
        
        if problem_definition['affected_systems']:
            known_factors.append(f"Affected systems: {', '.join(problem_definition['affected_systems'])}")
        
        return known_factors
    
    def _identify_missing_information(self, problem_definition: Dict[str, Any]) -> List[str]:
        """
        Identify information gaps in the problem definition that are required for a complete solution.
        
        Parameters:
            problem_definition (Dict[str, Any]): The structured problem definition to analyze.
        
        Returns:
            List[str]: A list of missing information items needed to fully address the problem.
        """
        missing_info = []
        
        if not problem_definition.get('affected_systems'):
            missing_info.append("Specific affected systems or components")
        
        if problem_definition['category'] == ProblemCategory.TECHNICAL_ISSUE:
            missing_info.extend([
                "Exact error messages or codes",
                "System configuration details",
                "Recent changes or updates"
            ])
        
        return missing_info
    
    def _extract_context_clues(self, query_text: str) -> List[str]:
        """
        Extracts context clues from the query text indicating timing or frequency patterns.
        
        Returns:
            List of context clues such as recent changes, intermittent issues, or consistent behavior patterns based on keywords found in the query text.
        """
        clues = []
        
        if 'recently' in query_text.lower() or 'after' in query_text.lower():
            clues.append("Recent change or update related")
        
        if 'sometimes' in query_text.lower() or 'occasionally' in query_text.lower():
            clues.append("Intermittent issue")
        
        if 'always' in query_text.lower() or 'never' in query_text.lower():
            clues.append("Consistent behavior pattern")
        
        return clues
    
    def _find_similar_cases(self, problem_definition: Dict[str, Any]) -> List[str]:
        """
        Return example descriptions of similar cases relevant to the problem definition.
        
        This is a placeholder implementation intended for future integration with a knowledge base.
        """
        return [
            "Similar cases found in knowledge base",
            "Common resolution patterns identified"
        ]
    
    def _identify_relevant_docs(self, problem_definition: Dict[str, Any]) -> List[str]:
        """
        Returns a list of relevant documentation titles based on the problem category in the provided problem definition.
        
        Parameters:
            problem_definition (Dict[str, Any]): Dictionary containing details about the problem, including its category.
        
        Returns:
            List[str]: Titles of documentation relevant to the specified problem category.
        """
        docs = []
        
        category = problem_definition['category']
        if category == ProblemCategory.TECHNICAL_ISSUE:
            docs.extend(["Technical troubleshooting guide", "Error resolution documentation"])
        elif category == ProblemCategory.ACCOUNT_SETUP:
            docs.extend(["Account setup guide", "Provider-specific instructions"])
        
        return docs
    
    def _generate_primary_hypothesis(
        self, problem_definition: Dict[str, Any], information_analysis: Dict[str, Any], category: ProblemCategory
    ) -> str:
        """
        Returns the most probable hypothesis for the given problem category based on the problem definition and analyzed information.
        
        Parameters:
            problem_definition (Dict[str, Any]): Structured details about the problem.
            information_analysis (Dict[str, Any]): Collected and analyzed information relevant to the problem.
            category (ProblemCategory): The category of the problem.
        
        Returns:
            str: The primary hypothesis describing the likely cause or nature of the problem.
        """
        
        category_hypotheses = {
            ProblemCategory.TECHNICAL_ISSUE: "Configuration or connectivity issue with email account settings",
            ProblemCategory.ACCOUNT_SETUP: "Missing or incorrect account configuration parameters",
            ProblemCategory.FEATURE_EDUCATION: "User needs guidance on feature usage and best practices",
            ProblemCategory.BILLING_INQUIRY: "Question about current subscription or billing status",
            ProblemCategory.PERFORMANCE_OPTIMIZATION: "System resource constraints affecting application performance",
            ProblemCategory.TROUBLESHOOTING: "Systematic diagnosis needed to identify root cause",
            ProblemCategory.GENERAL_SUPPORT: "General assistance needed with Mailbird functionality"
        }
        
        return category_hypotheses.get(category, "User needs comprehensive support assistance")
    
    def _generate_alternative_hypothesis(
        self, problem_definition: Dict[str, Any], information_analysis: Dict[str, Any], category: ProblemCategory
    ) -> Optional[str]:
        """
        Returns an alternative hypothesis for the given problem category based on the problem definition and analyzed information.
        
        Parameters:
            problem_definition (Dict[str, Any]): Structured details about the identified problem.
            information_analysis (Dict[str, Any]): Collected and analyzed information relevant to the problem.
            category (ProblemCategory): The category of the problem being addressed.
        
        Returns:
            Optional[str]: An alternative hypothesis statement if available for the specified category; otherwise, None.
        """
        
        alternative_hypotheses = {
            ProblemCategory.TECHNICAL_ISSUE: "Email provider policy change affecting authentication",
            ProblemCategory.ACCOUNT_SETUP: "Two-factor authentication or app password required",
            ProblemCategory.FEATURE_EDUCATION: "Related feature conflicts or integration issues",
            ProblemCategory.BILLING_INQUIRY: "Payment method or billing cycle confusion",
            ProblemCategory.PERFORMANCE_OPTIMIZATION: "Large mailbox size or inefficient sync settings",
            ProblemCategory.TROUBLESHOOTING: "Multiple related issues requiring compound solution",
            ProblemCategory.GENERAL_SUPPORT: "Complex workflow optimization opportunity"
        }
        
        return alternative_hypotheses.get(category)
    
    def _generate_edge_case_hypothesis(
        self, problem_definition: Dict[str, Any], information_analysis: Dict[str, Any], category: ProblemCategory
    ) -> Optional[str]:
        """
        Returns an edge case hypothesis string for the given problem category, if applicable.
        
        Parameters:
            problem_definition (Dict[str, Any]): The structured definition of the problem.
            information_analysis (Dict[str, Any]): Analysis of gathered information relevant to the problem.
            category (ProblemCategory): The category of the problem.
        
        Returns:
            Optional[str]: An edge case hypothesis description for the specified category, or None if not defined.
        """
        
        edge_cases = {
            ProblemCategory.TECHNICAL_ISSUE: "Rare system compatibility or security software conflict",
            ProblemCategory.ACCOUNT_SETUP: "Corporate email policies blocking standard setup",
            ProblemCategory.FEATURE_EDUCATION: "Advanced customization or integration requirements",
            ProblemCategory.BILLING_INQUIRY: "Complex billing scenario or account transfer issue",
            ProblemCategory.PERFORMANCE_OPTIMIZATION: "Hardware limitations or system-specific constraints",
            ProblemCategory.TROUBLESHOOTING: "Previously unknown bug or system-specific issue"
        }
        
        return edge_cases.get(category)
    
    def _generate_success_indicators(self, solution: SolutionCandidate, category: ProblemCategory) -> List[str]:
        """
        Generates a list of success indicators to verify whether a solution has effectively resolved the problem for a given category.
        
        Parameters:
        	solution (SolutionCandidate): The proposed solution candidate.
        	category (ProblemCategory): The category of the problem being addressed.
        
        Returns:
        	List[str]: Success criteria that can be used to confirm the solution's effectiveness, including both general and category-specific indicators.
        """
        
        base_indicators = [
            "Email functionality restored",
            "No error messages displayed",
            "User can complete intended task"
        ]
        
        category_specific = {
            ProblemCategory.TECHNICAL_ISSUE: [
                "Stable connection maintained",
                "Sync working properly",
                "No recurring errors"
            ],
            ProblemCategory.ACCOUNT_SETUP: [
                "Account appears in account list",
                "Send/receive test successful",
                "Folders syncing correctly"
            ],
            ProblemCategory.FEATURE_EDUCATION: [
                "User demonstrates feature usage",
                "Feature integrated into workflow",
                "User comfortable with customization"
            ]
        }
        
        return base_indicators + category_specific.get(category, [])
    
    def _generate_prevention_measures(self, solution: SolutionCandidate, category: ProblemCategory) -> str:
        """
        Returns recommended prevention measures for the given solution and problem category.
        
        Parameters:
        	category (ProblemCategory): The category of the problem for which prevention measures are suggested.
        
        Returns:
        	str: A string describing prevention strategies tailored to the problem category.
        """
        
        prevention_measures = {
            ProblemCategory.TECHNICAL_ISSUE: "Keep Mailbird updated, monitor account settings changes, maintain stable network connection",
            ProblemCategory.ACCOUNT_SETUP: "Save account settings documentation, monitor email provider policy changes",
            ProblemCategory.FEATURE_EDUCATION: "Bookmark relevant documentation, explore related features for enhanced productivity",
            ProblemCategory.BILLING_INQUIRY: "Set up billing notifications, review account status monthly",
            ProblemCategory.PERFORMANCE_OPTIMIZATION: "Monitor system resources, maintain regular optimization schedule"
        }
        
        return prevention_measures.get(category, "Regular maintenance and monitoring recommended")
    
    def _assess_solution_risks(self, solution: SolutionCandidate, category: ProblemCategory) -> List[str]:
        """
        Identifies potential risks associated with a solution candidate based on its detailed approach and problem category.
        
        Parameters:
        	solution (SolutionCandidate): The solution candidate to assess.
        	category (ProblemCategory): The category of the problem being addressed.
        
        Returns:
        	List[str]: A list of risk descriptions relevant to the solution.
        """
        
        risks = []
        
        if "restart" in ' '.join(solution.detailed_steps).lower():
            risks.append("Temporary interruption of email access during restart")
        
        if "remove" in ' '.join(solution.detailed_steps).lower() or "delete" in ' '.join(solution.detailed_steps).lower():
            risks.append("Potential data loss if not backed up properly")
        
        if category == ProblemCategory.TECHNICAL_ISSUE:
            risks.append("Configuration changes may require readjustment")
        
        return risks
    
    def _generate_fallback_options(self, solution: SolutionCandidate, category: ProblemCategory) -> List[str]:
        """
        Generate a list of fallback options to suggest if the primary solution for a given problem category fails.
        
        Parameters:
            solution (SolutionCandidate): The primary solution candidate for which fallbacks are being generated.
            category (ProblemCategory): The category of the problem to tailor fallback options.
        
        Returns:
            List[str]: A list of fallback strategies, including both general and category-specific options.
        """
        
        fallback_options = [
            "Contact Mailbird support for personalized assistance",
            "Try alternative configuration approach",
            "Temporary workaround while investigating further"
        ]
        
        category_specific = {
            ProblemCategory.TECHNICAL_ISSUE: [
                "Use webmail as temporary alternative",
                "Try different network or device",
                "Check with email provider support"
            ],
            ProblemCategory.ACCOUNT_SETUP: [
                "Manual IMAP/SMTP configuration",
                "Contact email provider for settings",
                "Use OAuth authentication if available"
            ]
        }
        
        return fallback_options + category_specific.get(category, [])
    
    def _rank_solutions(
        self,
        solutions: List[SolutionCandidate],
        emotional_state: EmotionalState,
        urgency_level: int,
        complexity_score: float
    ) -> List[SolutionCandidate]:
        """
        Rank solution candidates by adjusting their confidence scores based on urgency, emotional state, and complexity, then return them sorted from highest to lowest score.
        
        Parameters:
            solutions (List[SolutionCandidate]): The list of solution candidates to rank.
            emotional_state (EmotionalState): The user's current emotional state, influencing ranking adjustments.
            urgency_level (int): The urgency of the problem, affecting preference for faster solutions.
            complexity_score (float): The assessed complexity of the problem.
        
        Returns:
            List[SolutionCandidate]: The ranked list of solution candidates, sorted by adjusted confidence score.
        """
        
        for solution in solutions:
            # Calculate ranking score
            score = solution.confidence_score
            
            # Adjust for urgency (prefer faster solutions)
            if urgency_level >= 4:
                time_factor = max(0.5, 1.0 - (solution.estimated_time_minutes / 60))
                score *= (0.7 + 0.3 * time_factor)
            
            # Adjust for emotional state
            if emotional_state == EmotionalState.FRUSTRATED:
                # Prefer solutions with higher confidence
                score *= (0.8 + 0.2 * solution.confidence_score)
            elif emotional_state == EmotionalState.CONFUSED:
                # Prefer solutions with clearer steps
                step_clarity = len(solution.detailed_steps) / 20  # Normalize
                score *= (0.9 + 0.1 * min(step_clarity, 1.0))
            
            # Store ranking score
            solution.confidence_score = min(score, 1.0)
        
        # Sort by ranking score
        return sorted(solutions, key=lambda s: s.confidence_score, reverse=True)