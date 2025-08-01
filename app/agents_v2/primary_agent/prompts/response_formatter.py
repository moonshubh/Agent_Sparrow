"""
Agent Sparrow - Response Formatting System

This module provides sophisticated response formatting and quality assurance
to ensure all Agent Sparrow responses meet the mandatory structure and
quality standards defined in the enhancement specification.
"""

from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from enum import Enum
import re
import logging

from .emotion_templates import EmotionalState, EmotionDetectionResult

logger = logging.getLogger(__name__)


class ResponseSection(Enum):
    """Sections that should be present in Agent Sparrow responses"""
    EMPATHETIC_OPENING = "empathetic_opening"
    PRIMARY_SOLUTION = "primary_solution"
    QUICK_FIX = "quick_fix"
    DETAILED_SOLUTION = "detailed_solution"
    SECONDARY_INFO = "secondary_info"
    PRO_TIPS = "pro_tips"
    SUPPORTIVE_CLOSING = "supportive_closing"


@dataclass
class QualityScore:
    """Quality assessment result for response validation"""
    overall_score: float  # 0.0 to 1.0
    section_scores: Dict[ResponseSection, float]
    missing_sections: List[ResponseSection]
    improvement_suggestions: List[str]
    passes_quality_check: bool


@dataclass
class ResponseStructure:
    """Parsed structure of an Agent Sparrow response"""
    empathetic_opening: str
    primary_heading: str
    main_content: str
    sections: Dict[str, str]
    has_proper_markdown: bool
    has_numbered_steps: bool
    has_closing: str


class ResponseFormatter:
    """
    Sophisticated response formatting and quality assurance system
    
    Ensures all Agent Sparrow responses follow the mandatory structure:
    - Empathetic opening acknowledging emotion and situation
    - Primary solution heading that's action-oriented
    - Clear numbered steps when applicable
    - Secondary headings for additional information
    - Pro tips section with advanced features
    - Supportive closing with continuation offer
    """
    
    # Emotion-based closing templates (shared across methods)
    CLOSING_TEMPLATES = {
        EmotionalState.FRUSTRATED: "You've got this! These steps will have your email working perfectly again. Remember, you're just a few clicks away from inbox bliss.",
        EmotionalState.CONFUSED: "See? Not so complicated after all! You're becoming a Mailbird pro already. Your email setup is in great hands - yours!",
        EmotionalState.ANXIOUS: "Breathe easy - your emails are safe and you're back in control. You handled that beautifully!",
        EmotionalState.PROFESSIONAL: "Excellent. Your email system is now optimized for peak performance. You're all set for productive communication.",
        EmotionalState.URGENT: "Crisis averted! Your urgent emails are flowing again. You can focus on what matters most.",
        EmotionalState.EXCITED: "This is just the beginning! Wait until you discover all the other amazing things Mailbird can do. Enjoy exploring!",
        EmotionalState.DISAPPOINTED: "I know this wasn't the experience you expected, but look - we've turned it around together. Your Mailbird is now working exactly as it should.",
        EmotionalState.NEUTRAL: "Perfect! Everything's running smoothly now. Enjoy your streamlined email experience!"
    }
    
    # Mandatory response structure template
    MANDATORY_STRUCTURE_TEMPLATE = """[Empathetic Opening - Acknowledge emotion and situation]

## [Primary Solution Heading - Action-oriented]

[Clear explanation of the solution with numbered steps if applicable]

### Quick Fix (if available)
[Immediate workaround for urgent situations]

### Detailed Solution
1. [First step with specific details]
2. [Second step with expected outcome]
3. [Continue as needed]

## [Secondary Heading if Multiple Issues]

[Additional information, alternatives, or preventive measures]

### Pro Tips 💡
- [Advanced feature or optimization]
- [Time-saving shortcut]

[Closing with support continuation offer and confidence building]"""
    
    # Quality assurance criteria
    QUALITY_CRITERIA = {
        "emotional_tone_matches": {
            "weight": 0.20,
            "description": "Emotional tone matches customer state"
        },
        "addresses_specific_issue": {
            "weight": 0.25,
            "description": "Solution directly addresses the specific issue"
        },
        "clear_numbered_steps": {
            "weight": 0.15,
            "description": "Steps are clear and numbered when appropriate"
        },
        "technical_accuracy": {
            "weight": 0.15,
            "description": "Technical accuracy is verified"
        },
        "proper_markdown": {
            "weight": 0.10,
            "description": "Markdown formatting is properly applied"
        },
        "fallback_options": {
            "weight": 0.10,
            "description": "Fallback options are provided"
        },
        "builds_confidence": {
            "weight": 0.05,
            "description": "Response builds customer confidence"
        }
    }
    
    # Response patterns for validation
    VALIDATION_PATTERNS = {
        "empathetic_opening": [
            r"(?i)^(I (understand|can see|realize|appreciate)|I'm (sorry|genuinely sorry)|Thank you for)",
            r"(?i)^(I completely understand|I can really hear|Your (frustration|concern) is)",
            r"(?i)^(No worries|Don't worry|I want to reassure you)"
        ],
        "primary_heading": [
            r"^## [A-Z][^#\n]+$"  # Starts with ##, capital letter, no other # in line
        ],
        "numbered_steps": [
            r"^\d+\.\s+.+$"  # Lines starting with number, period, space
        ],
        "markdown_formatting": [
            r"^#{1,3}\s+.+$",  # Headers
            r"^\*\s+.+$",      # Bullet points
            r"^\d+\.\s+.+$",   # Numbered lists
            r"\*\*[^*]+\*\*",  # Bold text
            r"`[^`]+`"         # Code blocks
        ],
        "pro_tips_section": [
            r"### Pro Tips 💡",
            r"### (Advanced|Pro) Tips?",
            r"### Tips? (and|&) Tricks?"
        ],
        "supportive_closing": [
            r"(?i)(let me know if|feel free to|don't hesitate|I'm here to help)",
            r"(?i)(any other questions|anything else|further assistance)",
            r"(?i)(happy to help|glad to assist|here for you)"
        ]
    }
    
    @classmethod
    def parse_response_structure(cls, response: str) -> ResponseStructure:
        """
        Parses an Agent Sparrow response and extracts its structural components.
        
        Splits the response into sections such as empathetic opening, primary heading, subsections, and closing, while detecting the presence of proper markdown formatting and numbered steps. Returns a ResponseStructure object containing all parsed elements.
        """
        lines = response.split('\n')
        
        # Extract empathetic opening (first paragraph before first heading)
        empathetic_opening = ""
        primary_heading = ""
        main_content = ""
        sections = {}
        
        current_section = None
        current_content = []
        
        for line in lines:
            line = line.strip()
            
            if line.startswith('##') and not line.startswith('###'):
                # Primary or secondary heading
                if not primary_heading:
                    primary_heading = line
                    # Only set empathetic_opening if it's not already set and we have content
                    if current_content and not empathetic_opening:
                        empathetic_opening = '\n'.join(current_content).strip()
                    current_content = []
                else:
                    # Save previous section
                    if current_section:
                        sections[current_section] = '\n'.join(current_content).strip()
                    current_section = line
                    current_content = []
            elif line.startswith('###'):
                # Subsection heading - ensure we have a primary heading first
                if not primary_heading:
                    logger.warning("Found subsection header before any primary heading")
                    # Treat as content until we find a primary heading
                    current_content.append(line)
                    continue
                    
                # Save current section if exists
                if current_section:
                    sections[current_section] = '\n'.join(current_content).strip()
                current_section = line
                current_content = []
            else:
                current_content.append(line)
        
        # Handle last section
        if current_section:
            sections[current_section] = '\n'.join(current_content).strip()
        elif current_content and not empathetic_opening:  # Only set empathetic_opening if not already set
            empathetic_opening = '\n'.join(current_content).strip()
        
        # Check for proper markdown formatting
        has_proper_markdown = any(
            re.search(pattern, response, re.MULTILINE)
            for pattern in cls.VALIDATION_PATTERNS["markdown_formatting"]
        )
        
        # Check for numbered steps
        has_numbered_steps = bool(
            re.search(r"^\d+\.\s+.+$", response, re.MULTILINE)
        )
        
        # Extract closing (last paragraph)
        closing_lines = []
        for line in reversed(lines):
            line = line.strip()
            if line and not line.startswith('#'):
                closing_lines.append(line)
            elif line.startswith('#'):
                break
        
        has_closing = '\n'.join(reversed(closing_lines)).strip()
        
        return ResponseStructure(
            empathetic_opening=empathetic_opening,
            primary_heading=primary_heading,
            main_content=main_content,
            sections=sections,
            has_proper_markdown=has_proper_markdown,
            has_numbered_steps=has_numbered_steps,
            has_closing=has_closing
        )
    
    @classmethod
    def validate_response_quality(cls, response: str, emotion_result: Optional[EmotionDetectionResult] = None) -> QualityScore:
        """
        Evaluates a response against quality assurance criteria and returns a detailed quality assessment.
        
        The method analyzes the response for the presence and quality of key sections such as empathetic opening, primary solution heading, detailed solution steps, pro tips, and supportive closing. It checks for proper markdown formatting and emotional tone alignment (if emotion detection results are provided). The assessment includes section scores, missing sections, improvement suggestions, and an overall pass/fail flag based on weighted criteria.
        
        Parameters:
            response (str): The response text to be evaluated.
            emotion_result (Optional[EmotionDetectionResult]): Optional emotion detection result for tone matching.
        
        Returns:
            QualityScore: An object containing overall and per-section scores, missing sections, suggestions for improvement, and a quality check pass indicator.
        """
        structure = cls.parse_response_structure(response)
        section_scores = {}
        improvement_suggestions = []
        
        # Check empathetic opening
        opening_score = 0.0
        if structure.empathetic_opening:
            opening_patterns = cls.VALIDATION_PATTERNS["empathetic_opening"]
            if any(re.search(pattern, structure.empathetic_opening) for pattern in opening_patterns):
                opening_score = 1.0
            else:
                opening_score = 0.5
                improvement_suggestions.append("Empathetic opening could be more emotionally aware")
        else:
            improvement_suggestions.append("Missing empathetic opening")
        
        section_scores[ResponseSection.EMPATHETIC_OPENING] = opening_score
        
        # Check primary solution heading
        heading_score = 0.0
        if structure.primary_heading:
            if re.match(r"^## [A-Z][^#\n]+$", structure.primary_heading):
                heading_score = 1.0
            else:
                heading_score = 0.7
                improvement_suggestions.append("Primary heading should be action-oriented and properly formatted")
        else:
            improvement_suggestions.append("Missing primary solution heading")
        
        section_scores[ResponseSection.PRIMARY_SOLUTION] = heading_score
        
        # Check detailed solution steps
        steps_score = 0.0
        if structure.has_numbered_steps:
            steps_score = 1.0
        elif "step" in response.lower() or "solution" in response.lower():
            steps_score = 0.7
            improvement_suggestions.append("Consider using numbered steps for clarity")
        else:
            steps_score = 0.5
            improvement_suggestions.append("Add clear step-by-step instructions")
        
        section_scores[ResponseSection.DETAILED_SOLUTION] = steps_score
        
        # Check pro tips section
        pro_tips_score = 0.0
        pro_tips_patterns = cls.VALIDATION_PATTERNS["pro_tips_section"]
        if any(re.search(pattern, response) for pattern in pro_tips_patterns):
            pro_tips_score = 1.0
        elif "tip" in response.lower() or "💡" in response:
            pro_tips_score = 0.7
        else:
            improvement_suggestions.append("Consider adding Pro Tips section for enhanced value")
        
        section_scores[ResponseSection.PRO_TIPS] = pro_tips_score
        
        # Check supportive closing
        closing_score = 0.0
        if structure.has_closing:
            closing_patterns = cls.VALIDATION_PATTERNS["supportive_closing"]
            if any(re.search(pattern, structure.has_closing) for pattern in closing_patterns):
                closing_score = 1.0
            else:
                closing_score = 0.6
                improvement_suggestions.append("Closing could be more supportive and inviting")
        else:
            improvement_suggestions.append("Missing supportive closing")
        
        section_scores[ResponseSection.SUPPORTIVE_CLOSING] = closing_score
        
        # Check markdown formatting
        markdown_score = 1.0 if structure.has_proper_markdown else 0.3
        if not structure.has_proper_markdown:
            improvement_suggestions.append("Use proper Markdown formatting (headers, lists, bold text)")
        
        # Calculate overall score
        weights = [0.25, 0.25, 0.20, 0.15, 0.15]  # Corresponding to sections above
        scores = [opening_score, heading_score, steps_score, pro_tips_score, closing_score]
        overall_score = sum(score * weight for score, weight in zip(scores, weights))
        
        # Determine missing sections
        missing_sections = []
        if opening_score < 0.5:
            missing_sections.append(ResponseSection.EMPATHETIC_OPENING)
        if heading_score < 0.5:
            missing_sections.append(ResponseSection.PRIMARY_SOLUTION)
        if steps_score < 0.5:
            missing_sections.append(ResponseSection.DETAILED_SOLUTION)
        if pro_tips_score < 0.3:
            missing_sections.append(ResponseSection.PRO_TIPS)
        if closing_score < 0.5:
            missing_sections.append(ResponseSection.SUPPORTIVE_CLOSING)
        
        # Quality check passes if overall score >= 0.8 and no critical missing sections
        critical_missing = any(
            section in missing_sections 
            for section in [ResponseSection.EMPATHETIC_OPENING, ResponseSection.PRIMARY_SOLUTION]
        )
        passes_quality_check = overall_score >= 0.8 and not critical_missing
        
        return QualityScore(
            overall_score=overall_score,
            section_scores=section_scores,
            missing_sections=missing_sections,
            improvement_suggestions=improvement_suggestions,
            passes_quality_check=passes_quality_check
        )
    
    @classmethod
    def generate_response_template(cls, emotion: EmotionalState, issue: str, solution_type: str = "technical") -> str:
        """
        Generate a formatted response template tailored to the customer's emotional state, issue, and solution type.
        
        The template includes an empathy-driven opening, an action-oriented primary heading, placeholders for main content, quick fix, detailed solution steps, additional information, pro tips, and a supportive closing customized by emotion and issue context.
        
        Parameters:
            emotion (EmotionalState): The detected emotional state of the customer.
            issue (str): The specific issue being addressed.
            solution_type (str, optional): The type of solution (e.g., "technical", "billing", "feature", "setup", "troubleshooting"). Defaults to "technical".
        
        Returns:
            str: A response template string ready for content insertion, structured according to Agent Sparrow's standards.
        """
        # Get emotion-specific empathy template
        empathy_opening = EmotionTemplates.get_empathy_template(emotion, issue)
        
        # Generate action-oriented heading based on solution type
        heading_templates = {
            "technical": f"## Resolving Your {issue} Issue",
            "billing": f"## Clarifying Your {issue} Questions", 
            "feature": f"## Mastering {issue} in Mailbird",
            "setup": f"## Setting Up {issue} Successfully",
            "troubleshooting": f"## Troubleshooting {issue}"
        }
        
        primary_heading = heading_templates.get(solution_type, f"## Solving Your {issue} Challenge")
        
        # Select appropriate closing based on emotion - warm, confidence-building, never questioning
        supportive_closing = cls.CLOSING_TEMPLATES.get(emotion, 
            "You're all set! Your email is working beautifully now. Happy emailing!")
        
        template = f"""{empathy_opening}

{primary_heading}

[Insert main solution content here]

### Quick Fix
[Insert immediate workaround if applicable]

### Detailed Solution
1. [First step with specific details]
2. [Second step with expected outcome]
3. [Continue as needed]

## Additional Information

[Insert secondary information, alternatives, or preventive measures]

### Pro Tips 💡
- [Advanced feature or optimization tip]
- [Time-saving shortcut or hidden feature]

{supportive_closing}"""

        return template
    
    @classmethod
    def apply_mandatory_formatting(cls, response: str) -> str:
        """
        Format a response string to enforce mandatory spacing and markdown conventions.
        
        Ensures proper blank lines before and after markdown headers and limits consecutive blank lines to a maximum of two.
        
        Returns:
            str: The formatted response string with required structure applied.
        """
        lines = response.split('\n')
        formatted_lines = []
        
        for i, line in enumerate(lines):
            stripped = line.strip()
            
            # Handle header spacing
            if stripped.startswith('#'):
                if formatted_lines and formatted_lines[-1].strip() != '':
                    formatted_lines.append('')

                formatted_lines.append(line)

                if i < len(lines) - 1 and lines[i+1].strip() != '':
                    formatted_lines.append('')
            else:
                formatted_lines.append(line)
        
        # Remove excessive blank lines (more than 2 consecutive)
        final_lines = []
        blank_count = 0
        
        for line in formatted_lines:
            if line.strip() == '':
                blank_count += 1
                if blank_count <= 2:
                    final_lines.append(line)
            else:
                blank_count = 0
                final_lines.append(line)
        
        return '\n'.join(final_lines).strip()
    
    @classmethod
    def enhance_response_with_structure(cls, raw_response: str, emotion_result: EmotionDetectionResult, issue: str) -> str:
        """
        Enhances a raw LLM-generated response by ensuring it follows the Agent Sparrow structural and quality standards.
        
        The method parses the input response, generates or replaces the empathetic opening and supportive closing based on detected customer emotion and issue if they are missing or insufficient, ensures the presence of a primary heading, and adds a Pro Tips section if absent. The final response is assembled with proper formatting and section order.
        
        Returns:
            str: The enhanced and formatted response string with all mandatory sections.
        """
        # Parse existing structure
        structure = cls.parse_response_structure(raw_response)
        
        # Generate proper empathetic opening if missing
        if not structure.empathetic_opening or len(structure.empathetic_opening) < 20:
            empathy_opening = EmotionTemplates.format_emotion_aware_opening(emotion_result, issue)
        else:
            empathy_opening = structure.empathetic_opening
        
        # Ensure proper primary heading
        if not structure.primary_heading or not structure.primary_heading.startswith('##'):
            primary_heading = f"## Resolving Your {issue} Issue"
        else:
            primary_heading = structure.primary_heading
        
        # Extract main content (everything except opening and closing)
        main_content = raw_response
        if structure.empathetic_opening:
            main_content = main_content.replace(structure.empathetic_opening, '').strip()
        if structure.has_closing:
            main_content = main_content.replace(structure.has_closing, '').strip()
        
        # Add Pro Tips section if missing
        if "### Pro Tips" not in main_content and "💡" not in main_content:
            pro_tips = cls._generate_contextual_pro_tips(issue, emotion_result.primary_emotion)
            if pro_tips:
                main_content += f"\n\n### Pro Tips 💡\n{pro_tips}"
        
        # Generate supportive closing if missing or inadequate
        if not structure.has_closing or len(structure.has_closing) < 30:
            # Use warm, confidence-building closings based on emotion
            supportive_closing = cls.CLOSING_TEMPLATES.get(
                emotion_result.primary_emotion,
                "You're all set! Your email is working beautifully now. Happy emailing!"
            )
        else:
            supportive_closing = structure.has_closing
        
        # Assemble enhanced response
        enhanced_response = f"""{empathy_opening}

{primary_heading}

{main_content}

{supportive_closing}"""
        
    @classmethod
    def _generate_contextual_pro_tips(cls, issue: str, emotion: EmotionalState) -> str:
        """Generate context-aware pro tips based on the issue and customer emotion.
        
        Args:
            issue: The specific issue being addressed
            emotion: Detected customer emotional state
            
        Returns:
            Formatted pro tips as a string with markdown bullet points
        """
        # Default tips that are generally useful
        default_tips = [
            "Use keyboard shortcuts (Ctrl+N for new message) to boost productivity",
            "Enable notifications to stay on top of important emails",
            "Use the unified inbox to manage multiple email accounts in one place"
        ]
        
        # Context-specific tips based on common issues
        issue_tips = []
        issue_lower = issue.lower()
        
        if any(term in issue_lower for term in ['sync', 'update', 'refresh']):
            issue_tips.extend([
                "Enable 'Sync in background' for real-time email updates",
                "Check your internet connection if sync seems delayed"
            ])
        elif any(term in issue_lower for term in ['slow', 'performance', 'lag']):
            issue_tips.extend([
                "Clear cache from Settings > Storage to improve performance",
                "Limit the number of emails loaded in each folder"
            ])
        elif any(term in issue_lower for term in ['attachment', 'file']):
            issue_tips.extend([
                "Use the paperclip icon to quickly attach files to emails",
                "Drag and drop files directly into your email to attach them"
            ])
        
        # Emotion-appropriate tips
        if emotion == EmotionalState.FRUSTRATED:
            issue_tips.append("Try restarting the application if you're experiencing unexpected behavior")
        elif emotion == EmotionalState.CONFUSED:
            issue_tips.append("Hover over any icon to see a tooltip explaining its function")
        
        # Combine tips, prioritizing issue-specific ones
        all_tips = list(dict.fromkeys(issue_tips + default_tips))  # Remove duplicates while preserving order
        
        # Format as markdown bullet points
        return '\n'.join(f"- {tip}" for tip in all_tips[:3])  # Return up to 3 tips

        # Apply formatting rules
        return cls.apply_mandatory_formatting(enhanced_response)