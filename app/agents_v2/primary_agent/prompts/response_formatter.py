"""
Agent Sparrow - Response Formatting System

This module provides sophisticated response formatting and quality assurance
to ensure all Agent Sparrow responses meet the mandatory structure and
quality standards defined in the enhancement specification.
"""

from typing import Dict, List, Optional, Tuple, Union
from dataclasses import dataclass
from enum import Enum
import re
import logging
from functools import lru_cache

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
    
    @classmethod
    def generate_follow_up_questions(
        cls, 
        issue: str, 
        emotion: Union[EmotionalState, str], 
        solution_provided: str = ""
    ) -> List[str]:
        """Generate contextual follow-up questions based on the issue, emotion, and solution provided.
        
        Args:
            issue: The specific issue being addressed (non-empty string)
            emotion: Detected customer emotional state (EmotionalState enum or string)
            solution_provided: The solution content that was provided (optional)
            
        Returns:
            List of 3-5 follow-up questions
            
        Raises:
            ValueError: If issue is empty or None
            TypeError: If emotion is not EmotionalState or string
        """
        # Input validation
        if not issue or not isinstance(issue, str) or not issue.strip():
            raise ValueError("Issue must be a non-empty string")
        
        # Handle emotion parameter
        if isinstance(emotion, str):
            try:
                emotion = EmotionalState(emotion)
            except ValueError:
                # Default to NEUTRAL if invalid emotion string
                emotion = EmotionalState.NEUTRAL
        elif not isinstance(emotion, EmotionalState):
            raise TypeError(f"Emotion must be EmotionalState or string, got {type(emotion)}")
        
        # Normalize inputs
        issue_lower = issue.lower().strip()
        solution_provided = solution_provided or ""
        
        # Extract keywords using better tokenization
        issue_keywords = cls._extract_keywords(issue_lower)
        
        follow_up_questions = []
        
        # Structured mapping of keywords to question lists
        question_categories = {
            'sync_email': {
                'keywords': ['sync', 'email', 'connection', 'synchronize', 'refresh'],
                'questions': [
                    "Is the sync issue happening with all email accounts or just specific ones?",
                    "Have you tried removing and re-adding the email account?",
                    "Are you experiencing this issue on other devices as well?",
                    "Would you like help configuring sync settings for better performance?",
                    "Do you need assistance with backing up your emails before troubleshooting?"
                ]
            },
            'performance': {
                'keywords': ['slow', 'performance', 'crash', 'freeze', 'lag', 'memory'],
                'questions': [
                    "How long has Mailbird been running slowly on your system?",
                    "Are other applications also running slowly, or just Mailbird?",
                    "Would you like help optimizing Mailbird's performance settings?",
                    "Have you noticed if the slowdown happens at specific times?",
                    "Do you want to learn about reducing memory usage in Mailbird?"
                ]
            },
            'setup': {
                'keywords': ['setup', 'configure', 'install', 'set up', 'configuration'],
                'questions': [
                    "Do you need help importing your existing emails from another client?",
                    "Would you like assistance setting up additional email accounts?",
                    "Are there specific features you'd like help configuring?",
                    "Do you want to learn about Mailbird's advanced customization options?",
                    "Would you like tips on organizing your inbox effectively?"
                ]
            },
            'authentication': {
                'keywords': ['password', 'login', 'authentication', 'sign in', 'credentials', 'access'],
                'questions': [
                    "Are you using app-specific passwords for your email provider?",
                    "Would you like help setting up two-factor authentication?",
                    "Do you need assistance recovering your email account password?",
                    "Have you recently changed your email password?",
                    "Would you like to learn about Mailbird's security features?"
                ]
            }
        }
        
        # Find matching categories based on keywords
        matched_categories = []
        for category, data in question_categories.items():
            if any(keyword in issue_keywords for keyword in data['keywords']):
                matched_categories.append(category)
                follow_up_questions.extend(data['questions'])
        
        # Add generic questions if no specific match or as fallback
        if not matched_categories:
            follow_up_questions.extend([
                "Is there anything specific about this solution you'd like me to clarify?",
                "Would you like to know about related features in Mailbird?",
                "Do you have any other Mailbird questions I can help with?",
                "Would you like tips on preventing this issue in the future?",
                "Are there other email management tasks you need help with?"
            ])
        
        # Emotion-specific follow-ups with safe handling
        emotion_questions = {
            EmotionalState.FRUSTRATED: "Is there anything else causing frustration that I can help resolve?",
            EmotionalState.CONFUSED: "Would you like me to break down any of these steps in more detail?",
            EmotionalState.ANXIOUS: "Do you have any concerns about data safety I can address?",
            EmotionalState.URGENT: "Is there a specific deadline you're working against?"
        }
        
        if emotion in emotion_questions:
            follow_up_questions.append(emotion_questions[emotion])
        
        # Safety check for empty questions list
        if not follow_up_questions:
            return [
                "Is there anything specific about this issue you'd like me to clarify?",
                "Would you like to know about related features in Mailbird?",
                "Do you have any other questions I can help with?"
            ]
        
        # Remove duplicates while preserving order
        unique_questions = list(dict.fromkeys(follow_up_questions))
        
        # Enhanced scoring algorithm
        scored_questions = []
        for idx, question in enumerate(unique_questions):
            score = 0.0
            question_lower = question.lower()
            
            # Score based on keyword matches (use extracted keywords, not split)
            matching_keywords = sum(1 for keyword in issue_keywords if keyword in question_lower)
            score += matching_keywords * 2.0
            
            # Score for emotion relevance
            if emotion and hasattr(emotion, 'value'):
                emotion_str = emotion.value.lower()
                if emotion_str in question_lower:
                    score += 1.5
            
            # Slight penalty for generic questions to prioritize specific ones
            if any(generic in question_lower for generic in ['anything', 'other', 'else']):
                score -= 0.5
            
            # Add small index bonus to handle ties consistently (prefer earlier questions)
            score -= idx * 0.01
            
            scored_questions.append((score, question))
        
        # Sort by score (descending) and return top 5
        scored_questions.sort(key=lambda x: (-x[0], x[1]))  # Secondary sort by question text for consistency
        return [q[1] for q in scored_questions[:5]]
    
    @classmethod
    @lru_cache(maxsize=128)
    def _extract_keywords(cls, text: str) -> tuple:
        """Extract meaningful keywords from text using improved tokenization.
        
        Args:
            text: Input text to extract keywords from
            
        Returns:
            Tuple of extracted keywords (tuple for hashability with lru_cache)
        """
        # Remove common stop words
        stop_words = {
            'the', 'is', 'at', 'which', 'on', 'a', 'an', 'as', 'are', 'was',
            'were', 'been', 'be', 'have', 'has', 'had', 'do', 'does', 'did',
            'will', 'would', 'could', 'should', 'may', 'might', 'must', 'can',
            'this', 'that', 'these', 'those', 'i', 'me', 'my', 'we', 'you', 'your',
            'it', 'its', 'they', 'them', 'their', 'what', 'where', 'when', 'how',
            'why', 'all', 'any', 'each', 'few', 'more', 'most', 'other', 'some',
            'such', 'only', 'own', 'same', 'so', 'than', 'too', 'very', 'just',
            'and', 'or', 'but', 'if', 'while', 'with', 'for', 'to', 'from', 'of',
            'in', 'out', 'up', 'down', 'about', 'into', 'through', 'during', 'before',
            'after', 'above', 'below', 'between', 'under', 'again', 'further', 'then'
        }
        
        # Use regex to extract words (handles punctuation better than split)
        words = re.findall(r'\b[a-z]+\b', text.lower())
        
        # Filter out stop words and very short words
        keywords = [word for word in words if word not in stop_words and len(word) > 2]
        
        # Also extract multi-word terms (e.g., "app-specific", "two-factor")
        multi_word_patterns = re.findall(r'\b[a-z]+[-\s][a-z]+\b', text.lower())
        keywords.extend(multi_word_patterns)
        
        # Return as tuple for hashability (required for lru_cache)
        return tuple(set(keywords))