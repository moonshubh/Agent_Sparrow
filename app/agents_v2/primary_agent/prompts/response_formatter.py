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

from .emotion_templates import EmotionalState, EmotionDetectionResult


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
        Parse and analyze the structure of an Agent Sparrow response
        
        Args:
            response: The response text to analyze
            
        Returns:
            ResponseStructure object with parsed components
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
                # Subsection heading
                if current_section:
                    sections[current_section] = '\n'.join(current_content).strip()
                current_section = line
                current_content = []
            else:
                current_content.append(line)
        
        # Handle last section
        if current_section:
            sections[current_section] = '\n'.join(current_content).strip()
        elif not empathetic_opening and current_content:
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
        Validate response against quality assurance checklist
        
        Args:
            response: The response text to validate
            emotion_result: Optional emotion detection result for tone matching
            
        Returns:
            QualityScore with detailed assessment
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
        Generate a response template based on emotion and issue type
        
        Args:
            emotion: Detected customer emotional state
            issue: Specific issue being addressed
            solution_type: Type of solution (technical, billing, feature, etc.)
            
        Returns:
            Formatted response template ready for content insertion
        """
        # Get emotion-specific empathy template
        from .emotion_templates import EmotionTemplates
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
        
        # Select appropriate closing based on emotion
        closing_templates = {
            EmotionalState.FRUSTRATED: "I'm confident this solution will resolve the issue for you. If you encounter any difficulties with these steps, please don't hesitate to reach out - I'm here to ensure you have a smooth Mailbird experience.",
            EmotionalState.CONFUSED: "I hope this step-by-step approach makes everything clear! If any part needs further explanation, feel free to ask - I'm happy to walk through it again or clarify any details.",
            EmotionalState.ANXIOUS: "This solution should have you back up and running quickly. Your emails and data remain safe throughout this process. If you need any reassurance or run into questions, I'm here to help immediately.",
            EmotionalState.PROFESSIONAL: "This comprehensive solution should address your requirements effectively. If you need any additional technical details or have follow-up questions, please feel free to reach out.",
            EmotionalState.URGENT: "This should resolve your issue promptly so you can get back to your important work. If you need any immediate assistance during implementation, don't hesitate to contact support."
        }
        
        supportive_closing = closing_templates.get(emotion, 
            "I'm here to help if you need any clarification on these steps. Don't hesitate to reach out if you have any other Mailbird questions!")
        
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
        Apply mandatory formatting rules to ensure response meets standards
        
        Args:
            response: Raw response text
            
        Returns:
            Formatted response with mandatory structure applied
        """
        lines = response.split('\n')
        formatted_lines = []
        
        for i, line in enumerate(lines):
            stripped = line.strip()
            
            # Ensure proper spacing around headers
            if stripped.startswith('#'):
                if i > 0 and formatted_lines and formatted_lines[-1].strip():
                    formatted_lines.append('')  # Add blank line before header
                formatted_lines.append(line)
                if i < len(lines) - 1:
                    formatted_lines.append('')  # Add blank line after header
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
        Enhance a raw LLM response with proper Agent Sparrow structure
        
        Args:
            raw_response: Raw response from LLM
            emotion_result: Detected customer emotion
            issue: Specific issue being addressed
            
        Returns:
            Enhanced response with proper structure and formatting
        """
        # Parse existing structure
        structure = cls.parse_response_structure(raw_response)
        
        # Generate proper empathetic opening if missing
        if not structure.empathetic_opening or len(structure.empathetic_opening) < 20:
            from .emotion_templates import EmotionTemplates
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
            main_content += "\n\n### Pro Tips 💡\n- Consider enabling automatic sync for real-time email updates\n- Use keyboard shortcuts (Ctrl+N for new message) to boost productivity"
        
        # Generate supportive closing if missing or inadequate
        if not structure.has_closing or len(structure.has_closing) < 30:
            from .emotion_templates import EmotionTemplates
            strategy = EmotionTemplates.get_response_strategy(emotion_result.primary_emotion)
            
            if emotion_result.primary_emotion == EmotionalState.FRUSTRATED:
                supportive_closing = "I'm confident this solution will resolve the issue for you. If you encounter any difficulties with these steps, please don't hesitate to reach out - I'm here to ensure you have a smooth Mailbird experience."
            elif emotion_result.primary_emotion == EmotionalState.CONFUSED:
                supportive_closing = "I hope this step-by-step approach makes everything clear! If any part needs further explanation, feel free to ask - I'm happy to walk through it again."
            else:
                supportive_closing = "I'm here to help if you need any clarification on these steps. Feel free to reach out with any other Mailbird questions!"
        else:
            supportive_closing = structure.has_closing
        
        # Assemble enhanced response
        enhanced_response = f"""{empathy_opening}

{primary_heading}

{main_content}

{supportive_closing}"""
        
        # Apply formatting rules
        return cls.apply_mandatory_formatting(enhanced_response)