"""
Natural Language Generator

Transforms technical log analysis into empathetic, conversational responses
that resonate with users' emotional states and technical proficiency levels.
"""

from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass
from datetime import datetime
import random
import re

from app.agents_v2.primary_agent.prompts.emotion_templates import (
    EmotionalState,
    EmotionTemplates,
)
try:
    from ..schemas.log_schemas import (
        LogAnalysisResult,
        RootCause,
        ErrorCategory,
        IssueImpact,
        UserContext,
    )
except ImportError:
    from app.agents_v2.log_analysis_agent.schemas.log_schemas import (
        LogAnalysisResult,
        RootCause,
        ErrorCategory,
        IssueImpact,
        UserContext,
    )


@dataclass
class ToneProfile:
    """Defines the tone characteristics for a response"""
    formality: float  # 0 (casual) to 1 (formal)
    technicality: float  # 0 (simple) to 1 (technical)
    empathy: float  # 0 (neutral) to 1 (highly empathetic)
    urgency: float  # 0 (relaxed) to 1 (urgent)


class NaturalLanguageGenerator:
    """
    Generates natural, empathetic language for log analysis responses.

    Features:
    - Emotional intelligence integration
    - Technical-to-plain language translation
    - Personalized greetings and closings
    - Context-aware messaging
    - Escalation language generation
    """

    # Greeting templates by emotional state
    GREETING_TEMPLATES = {
        EmotionalState.FRUSTRATED: [
            "I understand how frustrating these issues can be, {name}. Let me help you resolve this quickly.",
            "I can see you're dealing with some annoying problems, {name}. I'm here to help get this sorted out.",
            "I know technical issues are frustrating, {name}. Let's work through this together.",
        ],
        EmotionalState.ANXIOUS: [
            "I understand this is urgent for you, {name}. I've thoroughly analyzed your logs and have solutions ready.",
            "Don't worry, {name} - I've identified the issue and have clear steps to resolve it.",
            "I can see this is causing concern, {name}. Let me walk you through the solution step by step.",
        ],
        EmotionalState.CONFUSED: [
            "I'll help clarify what's happening with your Mailbird, {name}. Let me break this down simply.",
            "Let me explain what I found in your logs, {name}. I'll keep it straightforward.",
            "I understand this might seem complex, {name}. I'll guide you through everything clearly.",
        ],
        EmotionalState.PROFESSIONAL: [
            "Thank you for providing the logs, {name}. I've completed my analysis and identified the following issues.",
            "I've analyzed your Mailbird logs, {name}. Here's my detailed assessment.",
            "Based on my log analysis, {name}, I've identified the root cause and resolution steps.",
        ],
        EmotionalState.NEUTRAL: [
            "Hi {name}, I've analyzed your Mailbird logs and found some issues we can fix.",
            "Thanks for sharing your logs, {name}. I've identified what's causing the problem.",
            "Hello {name}, I've completed the log analysis. Here's what I discovered.",
        ],
    }

    # Closing templates by resolution status
    CLOSING_TEMPLATES = {
        "resolved": [
            "These steps should resolve your issue. If you need any clarification, just let me know!",
            "Follow these steps and your Mailbird should be working smoothly again. I'm here if you need help!",
            "This should get everything back to normal. Feel free to ask if anything isn't clear!",
        ],
        "escalated": [
            "I've identified this as a known issue that our engineering team needs to address. "
            "I've provided steps to help in the meantime.",
            "This appears to be a bug in Mailbird that requires a fix from our development team. "
            "The workaround above should help for now.",
            "I've flagged this for our engineering team. Meanwhile, the solution provided should help you continue working.",
        ],
        "partial": [
            "These steps should improve the situation. If issues persist, we may need to investigate further.",
            "This should help with the immediate problem. Let me know if you continue experiencing issues.",
            "Try these steps first - they address the most likely cause. We can explore further if needed.",
        ],
    }

    # Technical term translations
    TECHNICAL_TRANSLATIONS = {
        "null reference exception": "the program tried to use something that doesn't exist",
        "authentication failed": "your email password was rejected",
        "synchronization": "updating your emails",
        "database corruption": "your email storage has errors",
        "memory leak": "Mailbird is using too much memory",
        "network timeout": "the connection took too long",
        "SSL/TLS error": "secure connection problem",
        "IMAP connection": "email server connection",
        "OAuth token": "login permission",
        "cache invalidation": "clearing temporary files",
        "thread deadlock": "the program got stuck",
        "heap exhaustion": "ran out of memory",
    }

    def __init__(self):
        """Initialize the natural language generator"""
        self.emotion_templates = EmotionTemplates()
        self.default_name = "there"

    def generate_personalized_greeting(
        self,
        emotional_state: EmotionalState,
        user_name: Optional[str] = None,
        user_context: Optional[UserContext] = None,
    ) -> str:
        """
        Generate a personalized greeting based on emotional state.

        Args:
            emotional_state: Detected emotional state
            user_name: User's name if available
            user_context: Additional user context

        Returns:
            Personalized greeting message
        """
        name = user_name or self.default_name

        # Get appropriate template
        templates = self.GREETING_TEMPLATES.get(
            emotional_state, self.GREETING_TEMPLATES[EmotionalState.NEUTRAL]
        )

        # Select template with some variation
        template = random.choice(templates)

        # Personalize the greeting
        greeting = template.format(name=name)

        # Add context-specific elements
        if user_context:
            if user_context.urgency_level == "critical":
                greeting += " I'm prioritizing this as urgent."
            elif user_context.business_impact:
                greeting += " I understand this is affecting your work."

        return greeting

    def generate_root_cause_explanation(
        self,
        root_cause: RootCause,
        technical_level: str = "intermediate",
    ) -> str:
        """
        Generate plain-language explanation of root cause.

        Args:
            root_cause: The identified root cause
            technical_level: User's technical proficiency

        Returns:
            Natural language explanation
        """
        # Start with the basic issue
        if technical_level == "beginner":
            explanation = self._simplify_technical_description(root_cause.description)
        else:
            explanation = root_cause.description

        # Add confidence qualifier
        confidence_qualifier = self._get_confidence_qualifier(root_cause.confidence_score)

        # Build the explanation
        parts = []

        # Opening
        if root_cause.confidence_score > 0.8:
            parts.append(f"I've identified the issue: {explanation}")
        else:
            parts.append(f"It {confidence_qualifier} that {explanation}")

        # Impact statement
        impact_statement = self._generate_impact_statement(root_cause.impact)
        if impact_statement:
            parts.append(impact_statement)

        # Affected features
        if root_cause.affected_features:
            features = ", ".join(root_cause.affected_features[:3])
            parts.append(f"This is affecting: {features}")

        return " ".join(parts)

    def generate_closing_message(
        self,
        resolution_status: str,
        emotional_state: EmotionalState,
        user_name: Optional[str] = None,
    ) -> str:
        """
        Generate appropriate closing message.

        Args:
            resolution_status: Status of resolution (resolved/escalated/partial)
            emotional_state: User's emotional state
            user_name: User's name if available

        Returns:
            Closing message
        """
        # Get base template
        templates = self.CLOSING_TEMPLATES.get(
            resolution_status, self.CLOSING_TEMPLATES["partial"]
        )
        closing = random.choice(templates)

        # Add emotional touch if needed
        if emotional_state == EmotionalState.FRUSTRATED:
            closing = "I know this has been frustrating. " + closing
        elif emotional_state == EmotionalState.ANXIOUS:
            if closing:
                closing = "Don't worry - " + closing[0].upper() + closing[1:]
            else:
                closing = "Don't worry - " + closing

        # Add personal touch
        if user_name:
            if "!" in closing:
                closing = closing.replace("!", f", {user_name}!", 1)
            elif closing:
                terminal = closing[-1]
                if terminal in ".?!":
                    closing = f"{closing[:-1]}, {user_name}{terminal}"
                else:
                    closing = f"{closing}, {user_name}"
            else:
                closing = user_name

        return closing

    def generate_escalation_message(
        self,
        reason: str,
        ticket_id: Optional[str] = None,
        workaround_available: bool = False,
    ) -> str:
        """
        Generate escalation message for engineering issues.

        Args:
            reason: Reason for escalation
            ticket_id: Support ticket ID if available
            workaround_available: Whether a workaround exists

        Returns:
            Escalation message
        """
        lines = []

        lines.append("### 🔧 Engineering Team Notification")
        lines.append("")
        lines.append(
            "I've identified this as a known issue in Mailbird that requires "
            "a fix from our development team."
        )
        lines.append("")

        if reason:
            lines.append(f"**Technical Details**: {reason}")
            lines.append("")

        if ticket_id:
            lines.append(f"**Reference**: Issue #{ticket_id}")
            lines.append("")

        if workaround_available:
            lines.append(
                "I've provided a temporary workaround above that should help "
                "until the permanent fix is released."
            )
        else:
            lines.append(
                "Unfortunately, no workaround is currently available. Our team "
                "is actively working on a solution."
            )

        lines.append("")
        lines.append(
            "*We apologize for the inconvenience. You'll be notified when the fix is available.*"
        )

        return "\n".join(lines)

    def translate_technical_term(self, term: str) -> str:
        """
        Translate technical term to plain language.

        Args:
            term: Technical term to translate

        Returns:
            Plain language equivalent
        """
        term_lower = term.lower()

        # Check direct translations
        for technical, simple in self.TECHNICAL_TRANSLATIONS.items():
            if technical in term_lower:
                # Case-insensitive replacement
                return re.sub(re.escape(technical), simple, term, flags=re.IGNORECASE)

        # Category-based translations
        if "exception" in term_lower:
            return re.sub(r"exception", "error", term, flags=re.IGNORECASE)
        elif "thread" in term_lower:
            return re.sub(r"thread", "process", term, flags=re.IGNORECASE)
        elif "daemon" in term_lower:
            return re.sub(r"daemon", "background service", term, flags=re.IGNORECASE)

        return term

    def generate_summary_statement(
        self,
        analysis: LogAnalysisResult,
        tone_profile: Optional[ToneProfile] = None,
    ) -> str:
        """
        Generate executive summary statement.

        Args:
            analysis: Complete log analysis
            tone_profile: Desired tone characteristics

        Returns:
            Summary statement
        """
        if not tone_profile:
            tone_profile = ToneProfile(0.5, 0.3, 0.7, 0.5)

        parts = []

        # Opening assessment
        if analysis.has_critical_issues:
            parts.append("Your Mailbird is experiencing critical issues that need immediate attention.")
        elif analysis.root_causes:
            count = len(analysis.root_causes)
            parts.append(f"I found {count} issue{'s' if count > 1 else ''} in your Mailbird logs.")
        else:
            parts.append("Your Mailbird appears to be functioning normally.")

        # Add key metrics
        if analysis.metadata.error_rate > 10:
            parts.append(f"The error rate is unusually high ({analysis.metadata.error_rate:.1f}%).")

        # Add performance note
        if analysis.performance_metrics.has_performance_issues:
            parts.append("There are also some performance issues affecting responsiveness.")

        # Resolution availability
        if analysis.root_causes and analysis.estimated_resolution_time:
            time_str = self._format_resolution_time(analysis.estimated_resolution_time)
            parts.append(f"The issues can be resolved in approximately {time_str}.")

        return " ".join(parts)

    def generate_attachment_summary(
        self,
        attachment_data: Dict[str, Any],
        emotional_state: EmotionalState,
    ) -> str:
        """
        Generate summary for attachment analysis.

        Args:
            attachment_data: Attachment OCR/analysis data
            emotional_state: User's emotional state

        Returns:
            Natural language attachment summary
        """
        if not attachment_data:
            return ""

        lines = []

        if attachment_data.get("screenshot_count", 0) > 0:
            count = attachment_data["screenshot_count"]
            lines.append(f"I've also reviewed the {count} screenshot{'s' if count > 1 else ''} you provided.")

        if attachment_data.get("error_visible"):
            lines.append("I can see the error message in your screenshot, which confirms the issue.")

        if attachment_data.get("ocr_summary"):
            summary = attachment_data["ocr_summary"]
            if emotional_state == EmotionalState.CONFUSED:
                lines.append(f"The screenshot shows: {summary}")
            else:
                lines.append(f"Based on the screenshot: {summary}")

        return " ".join(lines) if lines else ""

    def _simplify_technical_description(self, description: str) -> str:
        """Simplify technical description for beginners"""
        # Replace technical terms with case-insensitive matching
        simplified = description
        for technical, simple in self.TECHNICAL_TRANSLATIONS.items():
            simplified = re.sub(re.escape(technical), simple, simplified, flags=re.IGNORECASE)

        # Remove technical jargon patterns
        simplified = re.sub(r'\b[A-Z]{3,}\b', '', simplified)  # Remove acronyms
        simplified = re.sub(r'0x[0-9A-Fa-f]+', 'error code', simplified)  # Replace hex codes

        return simplified

    def _get_confidence_qualifier(self, confidence: float) -> str:
        """Get confidence qualifier phrase"""
        if confidence > 0.9:
            return "definitely appears"
        elif confidence > 0.7:
            return "appears"
        elif confidence > 0.5:
            return "seems likely"
        else:
            return "might be"

    def _generate_impact_statement(self, impact: IssueImpact) -> Optional[str]:
        """Generate impact statement based on severity"""
        statements = {
            IssueImpact.CRITICAL: "This is severely impacting Mailbird's functionality.",
            IssueImpact.HIGH: "This is causing significant problems.",
            IssueImpact.MEDIUM: "This is causing moderate issues.",
            IssueImpact.LOW: "This is causing minor inconvenience.",
            IssueImpact.MINIMAL: "This has minimal impact on usage.",
        }
        return statements.get(impact)

    def _format_resolution_time(self, minutes: int) -> str:
        """Format resolution time in natural language"""
        if minutes < 5:
            return "a few minutes"
        elif minutes <= 15:
            return "10-15 minutes"
        elif minutes <= 30:
            return "half an hour"
        elif minutes <= 60:
            return "an hour"
        else:
            hours = minutes / 60
            return f"{hours:.0f} hours"

    def humanize_error_category(self, category: ErrorCategory) -> str:
        """
        Convert error category to human-readable form.

        Args:
            category: Error category enum

        Returns:
            Human-readable category name
        """
        translations = {
            ErrorCategory.AUTHENTICATION: "login and password issues",
            ErrorCategory.SYNCHRONIZATION: "email syncing problems",
            ErrorCategory.NETWORK: "internet connection issues",
            ErrorCategory.DATABASE: "email storage problems",
            ErrorCategory.CONFIGURATION: "settings issues",
            ErrorCategory.PERFORMANCE: "speed and responsiveness problems",
            ErrorCategory.UI_INTERACTION: "display and interface issues",
            ErrorCategory.FILE_SYSTEM: "file access problems",
            ErrorCategory.MEMORY: "memory usage issues",
            ErrorCategory.LICENSING: "license and activation problems",
            ErrorCategory.UNKNOWN: "unidentified issues",
        }
        return translations.get(category, category.name.lower().replace("_", " "))
