"""
Intelligent Solution Generation Engine with Web Search Fallback
Production-grade solution reasoning and validation system for Mailbird issues.
"""

import asyncio
import json
from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime
import os
from langchain_google_genai import ChatGoogleGenerativeAI

from app.core.settings import settings
from langchain_core.prompts import PromptTemplate
from pydantic import BaseModel, Field

# Import search tools
from app.agents_v2.primary_agent.tools import tavily_web_search


class SolutionStep(BaseModel):
    """Individual solution step with validation."""
    step_number: int
    description: str
    expected_outcome: str
    troubleshooting_note: Optional[str] = None


class GeneratedSolution(BaseModel):
    """Complete solution with metadata."""
    issue_id: str
    solution_summary: str
    confidence_level: str  # High, Medium, Low
    solution_steps: List[SolutionStep]
    prerequisites: List[str]
    estimated_time_minutes: int
    success_probability: str
    alternative_approaches: List[str]
    references: List[str]
    requires_web_search: bool = False


class WebSearchContext(BaseModel):
    """Context for web search enhancement."""
    search_queries: List[str]
    search_results: List[Dict[str, Any]]
    enhanced_solution: Optional[GeneratedSolution] = None


class AdvancedSolutionEngine:
    """Advanced solution generation with Gemini 2.5 Pro reasoning and web search fallback."""
    
    def __init__(self):
        self.primary_llm = ChatGoogleGenerativeAI(
            model="gemini-2.5-pro",  # Use the most powerful model
            temperature=0.1,  # Low temperature for consistent reasoning
            google_api_key=settings.gemini_api_key,
        )
        
        self.fallback_llm = ChatGoogleGenerativeAI(
            model="gemini-1.5-pro-latest",
            temperature=0.2,
            google_api_key=settings.gemini_api_key,
        )
        
        # Solution generation prompt template
        self.solution_prompt = PromptTemplate(
            template="""
You are a SENIOR MAILBIRD TECHNICAL SPECIALIST with 10+ years of experience diagnosing and solving complex email client issues. You have deep expertise in:

- Email protocols (IMAP, SMTP, OAuth 2.0, Exchange)
- Windows application troubleshooting
- Database optimization (SQLite)
- Network connectivity and security
- Mailbird architecture and common failure patterns

ANALYSIS CONTEXT:
Issue Type: {issue_type}
Issue Description: {issue_description}
Severity: {severity}
Frequency: {occurrences} occurrences
System Context: {system_context}
User Impact: {user_impact}

SOLUTION GENERATION REQUIREMENTS:

1. **DEEP TECHNICAL REASONING**: 
   - Analyze the root cause using your expert knowledge
   - Consider system interactions and dependencies
   - Account for Mailbird-specific implementation details

2. **SOLUTION QUALITY CRITERIA**:
   - Solutions must be ACTIONABLE and SPECIFIC
   - Include exact menu paths and configuration values
   - Provide verification steps to confirm success
   - Consider user technical skill level (assume intermediate)

3. **STEP-BY-STEP APPROACH**:
   - Break down complex solutions into clear steps
   - Include expected outcomes for each step
   - Provide troubleshooting notes for potential issues
   - Estimate time requirements realistically

4. **RISK ASSESSMENT**:
   - Identify potential risks or side effects
   - Suggest backup/recovery procedures when applicable
   - Provide alternative approaches for different scenarios

5. **CONFIDENCE EVALUATION**:
   - High: Solution is well-established and proven effective
   - Medium: Solution is logical but may require iteration
   - Low: Solution is experimental or requires further investigation

RESPONSE FORMAT (JSON only):
{{
    "solution_summary": "One-sentence summary of the primary solution approach",
    "confidence_level": "High|Medium|Low",
    "solution_steps": [
        {{
            "step_number": 1,
            "description": "Specific action with exact details",
            "expected_outcome": "What the user should see/experience",
            "troubleshooting_note": "Optional: What to do if this step fails"
        }}
    ],
    "prerequisites": ["Required conditions or preparations"],
    "estimated_time_minutes": 15,
    "success_probability": "High|Medium|Low",
    "alternative_approaches": ["Alternative solution if primary fails"],
    "references": ["Canonical URLs or documentation sources"],
    "requires_web_search": false
}}

CRITICAL DECISION POINT:
Set "requires_web_search": true ONLY if:
- The issue involves undocumented error codes
- Recent Mailbird updates may have changed behavior
- The problem suggests new/emerging compatibility issues
- Your confidence is Low AND additional research would significantly improve the solution

Generate the most comprehensive, actionable solution based on your expert knowledge.
""",
            input_variables=["issue_type", "issue_description", "severity", "occurrences", "system_context", "user_impact"]
        )
        
        # Enhanced solution prompt with web search context
        self.enhanced_solution_prompt = PromptTemplate(
            template="""
You are enhancing a technical solution using additional web research context.

ORIGINAL SOLUTION:
{original_solution}

WEB SEARCH RESULTS:
{search_results}

ENHANCEMENT INSTRUCTIONS:
1. Integrate relevant information from search results
2. Update solution steps with newer/better approaches
3. Add specific version-related fixes if found
4. Include any newly discovered troubleshooting tips
5. Update confidence level based on additional validation

Provide the enhanced solution in the same JSON format, incorporating improvements from the web research.
""",
            input_variables=["original_solution", "search_results"]
        )
    
    async def generate_solution(self, issue: Dict[str, Any], system_metadata: Dict[str, Any]) -> GeneratedSolution:
        """Generate a comprehensive solution for the given issue."""
        
        # Prepare context for solution generation
        context = {
            "issue_type": issue.get("category", "unknown"),
            "issue_description": f"{issue.get('signature', '')} - {issue.get('root_cause', '')}",
            "severity": issue.get("severity", "Unknown"),
            "occurrences": issue.get("occurrences", 0),
            "system_context": self._format_system_context(system_metadata),
            "user_impact": issue.get("user_impact", "Unknown impact")
        }
        
        try:
            # Generate initial solution using Gemini 2.5 Pro
            solution_chain = self.solution_prompt | self.primary_llm
            response = await solution_chain.ainvoke(context)
            
            # Parse the JSON response
            solution_data = json.loads(response.content)
            
            # Convert to structured solution object
            solution = GeneratedSolution(
                issue_id=issue.get("issue_id", "unknown"),
                solution_summary=solution_data.get("solution_summary", ""),
                confidence_level=solution_data.get("confidence_level", "Medium"),
                solution_steps=[
                    SolutionStep(**step) for step in solution_data.get("solution_steps", [])
                ],
                prerequisites=solution_data.get("prerequisites", []),
                estimated_time_minutes=solution_data.get("estimated_time_minutes", 30),
                success_probability=solution_data.get("success_probability", "Medium"),
                alternative_approaches=solution_data.get("alternative_approaches", []),
                references=solution_data.get("references", []),
                requires_web_search=solution_data.get("requires_web_search", False)
            )
            
            # If web search is required, enhance the solution
            if solution.requires_web_search:
                enhanced_solution = await self._enhance_with_web_search(solution, issue, system_metadata)
                return enhanced_solution if enhanced_solution else solution
            
            return solution
            
        except Exception as e:
            # Fallback to simpler model if primary fails
            return await self._generate_fallback_solution(issue, system_metadata, str(e))
    
    async def _enhance_with_web_search(self, original_solution: GeneratedSolution, issue: Dict[str, Any], system_metadata: Dict[str, Any]) -> Optional[GeneratedSolution]:
        """Enhance solution using web search results."""
        try:
            # Generate search queries
            search_queries = self._generate_search_queries(issue, system_metadata)
            
            # Perform web searches
            search_results = []
            for query in search_queries[:3]:  # Limit to 3 searches to control costs
                try:
                    results = await tavily_web_search.ainvoke({"query": query})
                    if results:
                        search_results.extend(results[:2])  # Top 2 results per query
                except Exception as search_error:
                    print(f"Web search failed for query '{query}': {search_error}")
                    continue
            
            if not search_results:
                return original_solution
            
            # Format search results for enhancement
            formatted_results = self._format_search_results(search_results)
            
            # Generate enhanced solution
            enhancement_context = {
                "original_solution": original_solution.model_dump_json(indent=2),
                "search_results": formatted_results
            }
            
            enhancement_chain = self.enhanced_solution_prompt | self.primary_llm
            response = await enhancement_chain.ainvoke(enhancement_context)
            
            # Parse enhanced solution
            enhanced_data = json.loads(response.content)
            
            # Create enhanced solution object
            enhanced_solution = GeneratedSolution(
                issue_id=original_solution.issue_id,
                solution_summary=enhanced_data.get("solution_summary", original_solution.solution_summary),
                confidence_level=enhanced_data.get("confidence_level", original_solution.confidence_level),
                solution_steps=[
                    SolutionStep(**step) for step in enhanced_data.get("solution_steps", [])
                ],
                prerequisites=enhanced_data.get("prerequisites", original_solution.prerequisites),
                estimated_time_minutes=enhanced_data.get("estimated_time_minutes", original_solution.estimated_time_minutes),
                success_probability=enhanced_data.get("success_probability", original_solution.success_probability),
                alternative_approaches=enhanced_data.get("alternative_approaches", original_solution.alternative_approaches),
                references=enhanced_data.get("references", original_solution.references),
                requires_web_search=False  # Mark as enhanced
            )
            
            return enhanced_solution
            
        except Exception as e:
            print(f"Solution enhancement failed: {e}")
            return original_solution
    
    def _generate_search_queries(self, issue: Dict[str, Any], system_metadata: Dict[str, Any]) -> List[str]:
        """Generate targeted search queries for the issue."""
        mailbird_version = system_metadata.get("mailbird_version", "")
        issue_type = issue.get("category", "")
        issue_signature = issue.get("signature", "")
        
        queries = [
            f"Mailbird {mailbird_version} {issue_type} fix solution",
            f"Mailbird {issue_signature} troubleshooting",
            f"Mailbird {issue_type} error resolution 2024"
        ]
        
        # Add specific queries based on issue type
        if "authentication" in issue_type:
            queries.append(f"Mailbird OAuth authentication fix {mailbird_version}")
        elif "database" in issue_type:
            queries.append(f"Mailbird database corruption repair SQLite")
        elif "network" in issue_type:
            queries.append(f"Mailbird network connectivity issues Windows firewall")
        
        return queries
    
    def _format_search_results(self, search_results: List[Dict]) -> str:
        """Format search results for LLM consumption."""
        formatted_results = []
        
        for i, result in enumerate(search_results[:5], 1):  # Limit to top 5 results
            formatted_result = f"""
SEARCH RESULT {i}:
Title: {result.get('title', 'No title')}
URL: {result.get('url', 'No URL')}
Content: {result.get('content', 'No content')[:500]}...
Relevance Score: {result.get('score', 'N/A')}
"""
            formatted_results.append(formatted_result)
        
        return "\n".join(formatted_results)
    
    def _format_system_context(self, metadata: Dict[str, Any]) -> str:
        """Format system metadata for context."""
        return f"""
Mailbird Version: {metadata.get('mailbird_version', 'Unknown')}
Database Size: {metadata.get('database_size_mb', 'Unknown')} MB
Account Count: {metadata.get('account_count', 'Unknown')}
Folder Count: {metadata.get('folder_count', 'Unknown')}
OS Version: {metadata.get('os_version', 'Unknown')}
Memory Usage: {metadata.get('memory_usage_mb', 'Unknown')} MB
Email Providers: {', '.join(metadata.get('email_providers', []))}
"""
    
    async def _generate_fallback_solution(self, issue: Dict[str, Any], system_metadata: Dict[str, Any], error: str) -> GeneratedSolution:
        """Generate a basic solution using fallback model."""
        try:
            # Simple fallback solution template
            basic_solution = GeneratedSolution(
                issue_id=issue.get("issue_id", "unknown"),
                solution_summary=f"Basic troubleshooting steps for {issue.get('category', 'unknown')} issue",
                confidence_level="Low",
                solution_steps=[
                    SolutionStep(
                        step_number=1,
                        description="Restart Mailbird application completely",
                        expected_outcome="Application should start fresh without cached issues"
                    ),
                    SolutionStep(
                        step_number=2,
                        description="Check Windows Event Viewer for additional error details",
                        expected_outcome="May reveal additional system-level error information"
                    ),
                    SolutionStep(
                        step_number=3,
                        description="Contact Mailbird support with log file details",
                        expected_outcome="Professional assistance for complex issues"
                    )
                ],
                prerequisites=["Administrative access to Windows system"],
                estimated_time_minutes=15,
                success_probability="Low",
                alternative_approaches=["Reinstall Mailbird application", "Check for Windows updates"],
                references=["https://support.mailbird.com"],
                requires_web_search=True
            )
            
            return basic_solution
            
        except Exception as fallback_error:
            # Ultimate fallback - minimal solution
            return GeneratedSolution(
                issue_id=issue.get("issue_id", "error"),
                solution_summary="Unable to generate specific solution due to system error",
                confidence_level="Low",
                solution_steps=[
                    SolutionStep(
                        step_number=1,
                        description="Contact technical support with log file",
                        expected_outcome="Professional diagnosis and resolution"
                    )
                ],
                prerequisites=[],
                estimated_time_minutes=5,
                success_probability="Medium",
                alternative_approaches=[],
                references=[],
                requires_web_search=False
            )


async def generate_comprehensive_solutions(detected_issues: List[Dict[str, Any]], system_metadata: Dict[str, Any]) -> List[GeneratedSolution]:
    """Generate comprehensive solutions for all detected issues."""
    solution_engine = AdvancedSolutionEngine()
    solutions = []
    
    # Process issues in order of severity
    prioritized_issues = sorted(detected_issues, key=lambda x: {
        'High': 3, 'Medium': 2, 'Low': 1
    }.get(x.get('severity', 'Low'), 1), reverse=True)
    
    for issue in prioritized_issues:
        try:
            solution = await solution_engine.generate_solution(issue, system_metadata)
            solutions.append(solution)
        except Exception as e:
            print(f"Failed to generate solution for issue {issue.get('issue_id', 'unknown')}: {e}")
            # Continue with other issues even if one fails
            continue
    
    return solutions