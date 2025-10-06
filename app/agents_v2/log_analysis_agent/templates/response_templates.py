"""
Response Templates

Emotion-specific and context-aware templates for log analysis responses.
Provides structured templates that adapt to user emotional states and situations.
"""

import random
from typing import Dict, List, Optional, Any
from dataclasses import dataclass
from enum import Enum

from app.agents_v2.primary_agent.prompts.emotion_templates import EmotionalState


@dataclass
class TemplateContext:
    """Context for template selection and customization"""
    emotional_state: EmotionalState
    has_critical_issues: bool
    resolution_available: bool
    user_name: Optional[str] = None
    urgency_level: str = "normal"
    technical_level: str = "intermediate"
    escalation_required: bool = False


class ResponseTemplates:
    """
    Provides emotion-specific templates for various response sections.

    Templates adapt based on:
    - User emotional state
    - Issue severity
    - Resolution availability
    - Technical proficiency
    """

    # Opening templates by emotional state and severity
    OPENING_TEMPLATES = {
        (EmotionalState.FRUSTRATED, True): [
            "I completely understand your frustration, {name}. I've found critical issues in your logs that explain these problems. Let me show you exactly how to fix them.",
            "I can see why you're frustrated, {name} - there are serious issues affecting your Mailbird. The good news is I have clear solutions for you.",
        ],
        (EmotionalState.FRUSTRATED, False): [
            "I understand this is frustrating, {name}. I've analyzed your logs and found the issues. Let's get this sorted out quickly.",
            "I know dealing with technical issues is annoying, {name}. I've identified what's wrong and have solutions ready.",
        ],
        (EmotionalState.ANXIOUS, True): [
            "I understand this is urgent, {name}. I've found critical issues that need immediate attention. Don't worry - I have step-by-step solutions.",
            "I can see this is causing concern, {name}. I've identified serious problems, but I have clear fixes that will resolve them quickly.",
        ],
        (EmotionalState.ANXIOUS, False): [
            "Don't worry, {name} - I've found the issues and know how to fix them. Let me guide you through the solution.",
            "I understand your concern, {name}. The issues I found are fixable, and I'll walk you through everything step by step.",
        ],
        (EmotionalState.CONFUSED, True): [
            "I'll explain everything clearly, {name}. I found some serious issues in your logs, but I'll guide you through fixing them simply.",
            "Let me clarify what's happening, {name}. There are critical problems, but I'll break down the solution into easy steps.",
        ],
        (EmotionalState.CONFUSED, False): [
            "Let me explain what I found, {name}. I'll keep it simple and clear so you know exactly what to do.",
            "I'll break this down for you, {name}. The issues are straightforward to fix once you understand them.",
        ],
        (EmotionalState.PROFESSIONAL, True): [
            "Analysis complete, {name}. Critical issues identified with recommended resolution paths below.",
            "I've completed the diagnostic analysis, {name}. Multiple critical issues detected requiring immediate remediation.",
        ],
        (EmotionalState.PROFESSIONAL, False): [
            "Log analysis complete, {name}. Issues identified with solutions provided below.",
            "I've analyzed your logs, {name}. Root causes determined with resolution steps outlined.",
        ],
        (EmotionalState.NEUTRAL, True): [
            "I've analyzed your logs, {name}. Several critical issues were found that need attention.",
            "Log analysis complete, {name}. I've identified important issues with solutions below.",
        ],
        (EmotionalState.NEUTRAL, False): [
            "I've reviewed your logs, {name}. Here's what I found and how to fix it.",
            "Analysis complete, {name}. I've identified the issues and their solutions.",
        ],
    }

    # Root cause introduction templates
    ROOT_CAUSE_TEMPLATES = {
        EmotionalState.FRUSTRATED: [
            "Here's what's actually causing your problems:",
            "I've found exactly what's wrong:",
            "The real issue behind all this frustration is:",
        ],
        EmotionalState.ANXIOUS: [
            "I've identified the root cause - here's what needs to be fixed:",
            "Don't worry, I know exactly what's wrong:",
            "The main issue I've discovered is:",
        ],
        EmotionalState.CONFUSED: [
            "Let me explain what's causing the problem:",
            "Here's what I discovered is wrong:",
            "The issue in simple terms is:",
        ],
        EmotionalState.PROFESSIONAL: [
            "Root cause analysis reveals:",
            "Primary issue identification:",
            "Diagnostic results indicate:",
        ],
        EmotionalState.NEUTRAL: [
            "I've identified the following issues:",
            "Here's what I found in your logs:",
            "The analysis shows these problems:",
        ],
    }

    # Solution introduction templates
    SOLUTION_INTRO_TEMPLATES = {
        EmotionalState.FRUSTRATED: [
            "Let's fix this right now. Here's exactly what to do:",
            "Here's the quickest way to resolve this:",
            "Follow these steps to get everything working again:",
        ],
        EmotionalState.ANXIOUS: [
            "Here's how to fix this quickly and safely:",
            "Don't worry, these steps will resolve the issue:",
            "Follow this proven solution:",
        ],
        EmotionalState.CONFUSED: [
            "I'll guide you through each step:",
            "Here's what to do (I'll keep it simple):",
            "Let me walk you through the solution:",
        ],
        EmotionalState.PROFESSIONAL: [
            "Recommended resolution procedure:",
            "Execute the following remediation steps:",
            "Resolution methodology:",
        ],
        EmotionalState.NEUTRAL: [
            "Here's how to resolve this:",
            "Please follow these steps:",
            "The solution involves:",
        ],
    }

    # Escalation templates
    ESCALATION_TEMPLATES = {
        EmotionalState.FRUSTRATED: [
            "I need to be honest - this is a bug in Mailbird itself that our engineering team needs to fix. "
            "I've provided a workaround above that should help until the fix is released.",
            "This is actually a known Mailbird bug. I know that's frustrating, but the workaround "
            "I've provided should get you back up and running.",
        ],
        EmotionalState.ANXIOUS: [
            "This issue requires a fix from our development team. Don't worry though - "
            "the workaround above will help you continue working while we resolve it.",
            "Our engineering team is aware of this bug. The temporary solution I've provided "
            "will keep you operational until the permanent fix is ready.",
        ],
        EmotionalState.CONFUSED: [
            "This is a problem with Mailbird itself that we need to fix in an update. "
            "For now, the solution I've given you will work around the issue.",
            "This isn't something you did wrong - it's a bug we need to fix. "
            "The steps above will help until we release the update.",
        ],
        EmotionalState.PROFESSIONAL: [
            "This issue has been escalated to engineering for permanent resolution. "
            "Interim workaround provided above.",
            "Bug identified requiring engineering intervention. "
            "Temporary mitigation steps documented above.",
        ],
        EmotionalState.NEUTRAL: [
            "This issue has been identified as a system bug that requires an engineering fix. "
            "A workaround has been provided above.",
            "Our development team will need to address this issue. "
            "Please use the workaround provided in the meantime.",
        ],
    }

    # Closing templates based on resolution status
    CLOSING_TEMPLATES = {
        ("success", EmotionalState.FRUSTRATED): [
            "This should fix everything. If you run into any other issues, just let me know - I'm here to help!",
            "Follow these steps and you'll be back to normal. Feel free to reach out if you need anything else!",
        ],
        ("success", EmotionalState.ANXIOUS): [
            "These steps will resolve your issue completely. Everything will be working normally again. I'm here if you need reassurance!",
            "Don't worry - after these steps, Mailbird will be running smoothly. Reach out anytime if you need help!",
        ],
        ("success", EmotionalState.CONFUSED): [
            "That's everything! Your Mailbird should work perfectly after these steps. Ask me if anything wasn't clear!",
            "You're all set! These steps will fix the problem. Let me know if you need me to explain anything differently!",
        ],
        ("success", EmotionalState.PROFESSIONAL): [
            "Resolution steps complete. System should return to normal operation. Additional support available as needed.",
            "Remediation procedure documented above. Contact support for any clarifications required.",
        ],
        ("partial", EmotionalState.FRUSTRATED): [
            "These steps should significantly improve things. If issues persist, we'll dig deeper - just let me know.",
            "This should help a lot. If you're still having problems after this, reach out and we'll investigate further.",
        ],
        ("partial", EmotionalState.ANXIOUS): [
            "These steps will help stabilize things. If you continue to see issues, don't hesitate to contact me for more help.",
            "This should resolve most of the problem. I'm here to help further if needed - you're not alone in this!",
        ],
        ("partial", EmotionalState.CONFUSED): [
            "Try these steps first - they usually fix the issue. If things aren't better, just let me know and I'll help more.",
            "Start with these solutions. If you're still confused or having problems, I'm happy to explain more!",
        ],
        ("partial", EmotionalState.PROFESSIONAL): [
            "Initial remediation steps provided. Further investigation may be required if issues persist.",
            "Preliminary resolution attempted. Additional diagnostic steps available if needed.",
        ],
        ("success", EmotionalState.NEUTRAL): [
            "These steps should resolve the issue. Please let me know if you need any additional assistance.",
            "The solution above will fix the problem. Feel free to reach out if you have questions.",
        ],
        ("partial", EmotionalState.NEUTRAL): [
            "These steps should help with the issue. Please contact us if problems persist.",
            "This should improve the situation. Additional support is available if needed.",
        ],
    }

    # Resource link templates
    RESOURCE_TEMPLATES = {
        EmotionalState.FRUSTRATED: "Here are some helpful resources if you want more information:",
        EmotionalState.ANXIOUS: "These resources might give you additional peace of mind:",
        EmotionalState.CONFUSED: "Here are some simple guides that explain things further:",
        EmotionalState.PROFESSIONAL: "Additional technical resources:",
        EmotionalState.NEUTRAL: "For more information, see these resources:",
    }

    def __init__(self):
        """Initialize the response templates"""
        self.default_name = "there"

    def get_opening_template(self, context: TemplateContext) -> str:
        """
        Get appropriate opening template based on context.

        Args:
            context: Template context with emotional state and severity

        Returns:
            Formatted opening template
        """
        # Look for specific combination
        key = (context.emotional_state, context.has_critical_issues)

        if key in self.OPENING_TEMPLATES:
            templates = self.OPENING_TEMPLATES[key]
        else:
            # Fall back to neutral
            templates = self.OPENING_TEMPLATES.get(
                (EmotionalState.NEUTRAL, context.has_critical_issues),
                ["I've analyzed your logs and found some issues to address."]
            )

        # Select template
        template = random.choice(templates)

        # Format with name
        name = context.user_name or self.default_name
        return template.format(name=name)

    def get_root_cause_intro(self, emotional_state: EmotionalState) -> str:
        """
        Get root cause introduction based on emotional state.

        Args:
            emotional_state: User's emotional state

        Returns:
            Root cause introduction text
        """
        templates = self.ROOT_CAUSE_TEMPLATES.get(
            emotional_state,
            self.ROOT_CAUSE_TEMPLATES[EmotionalState.NEUTRAL]
        )

        return random.choice(templates)

    def get_solution_intro(self, emotional_state: EmotionalState) -> str:
        """
        Get solution introduction based on emotional state.

        Args:
            emotional_state: User's emotional state

        Returns:
            Solution introduction text
        """
        templates = self.SOLUTION_INTRO_TEMPLATES.get(
            emotional_state,
            self.SOLUTION_INTRO_TEMPLATES[EmotionalState.NEUTRAL]
        )

        return random.choice(templates)

    def get_escalation_template(self, emotional_state: EmotionalState) -> str:
        """
        Get escalation message based on emotional state.

        Args:
            emotional_state: User's emotional state

        Returns:
            Escalation message
        """
        templates = self.ESCALATION_TEMPLATES.get(
            emotional_state,
            self.ESCALATION_TEMPLATES[EmotionalState.NEUTRAL]
        )

        return random.choice(templates)

    def get_closing_template(
        self,
        resolution_status: str,
        emotional_state: EmotionalState
    ) -> str:
        """
        Get closing message based on resolution and emotional state.

        Args:
            resolution_status: Status of resolution (success/partial)
            emotional_state: User's emotional state

        Returns:
            Closing message
        """
        key = (resolution_status, emotional_state)

        if key in self.CLOSING_TEMPLATES:
            templates = self.CLOSING_TEMPLATES[key]
        else:
            # Fall back
            templates = [
                "I've provided the best solution available. "
                "Let me know if you need any clarification!"
            ]

        return random.choice(templates)

    def get_resource_intro(self, emotional_state: EmotionalState) -> str:
        """
        Get resource section introduction.

        Args:
            emotional_state: User's emotional state

        Returns:
            Resource intro text
        """
        return self.RESOURCE_TEMPLATES.get(
            emotional_state,
            self.RESOURCE_TEMPLATES[EmotionalState.NEUTRAL]
        )

    def format_confidence_statement(
        self,
        confidence: float,
        emotional_state: EmotionalState
    ) -> str:
        """
        Format confidence level statement.

        Args:
            confidence: Confidence score (0-1)
            emotional_state: User's emotional state

        Returns:
            Confidence statement
        """
        if emotional_state == EmotionalState.PROFESSIONAL:
            return f"Diagnostic confidence: {confidence:.0%}"
        elif emotional_state == EmotionalState.ANXIOUS:
            if confidence > 0.8:
                return "I'm very confident this will fix your issue"
            else:
                return "This solution should help improve things"
        elif emotional_state == EmotionalState.CONFUSED:
            if confidence > 0.8:
                return "This is definitely the problem"
            else:
                return "This is likely the issue"
        else:
            if confidence > 0.8:
                return f"I'm {confidence:.0%} sure this is the issue"
            else:
                return "This appears to be the problem"

    def format_time_estimate(
        self,
        minutes: int,
        emotional_state: EmotionalState
    ) -> str:
        """
        Format time estimate based on emotional state.

        Args:
            minutes: Estimated time in minutes
            emotional_state: User's emotional state

        Returns:
            Formatted time estimate
        """
        if emotional_state == EmotionalState.ANXIOUS:
            if minutes < 10:
                return "This will only take a few minutes"
            elif minutes < 30:
                return f"This can be fixed in about {minutes} minutes"
            else:
                return "This will take some time, but we'll get through it"
        elif emotional_state == EmotionalState.PROFESSIONAL:
            return f"Estimated resolution time: {minutes} minutes"
        else:
            if minutes < 10:
                return "Quick fix - just a few minutes"
            elif minutes < 30:
                return f"About {minutes} minutes to fix"
            else:
                return f"This will take approximately {minutes} minutes"
