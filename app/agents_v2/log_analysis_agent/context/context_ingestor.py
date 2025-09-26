"""
Context Ingestor for User Input Integration

This module processes user-provided context to enhance log analysis
with reported symptoms, attempted solutions, and business impact.
"""

import re
import logging
from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime, timedelta
from dataclasses import dataclass

from app.agents_v2.primary_agent.prompts.emotion_templates import EmotionTemplates

from ..schemas.log_schemas import UserContext

logger = logging.getLogger(__name__)


class ContextIngestor:
    """
    Processes and extracts structured information from user input.

    This class parses natural language descriptions of issues to extract:
    - Reported problems and symptoms
    - Timeline information
    - Affected accounts or features
    - Previous troubleshooting attempts
    - Business impact and urgency
    """

    # Time-related patterns
    TIME_PATTERNS = {
        "recent": timedelta(hours=1),
        "today": timedelta(hours=24),
        "yesterday": timedelta(hours=48),
        "this week": timedelta(days=7),
        "last week": timedelta(days=14),
        "this month": timedelta(days=30),
    }

    # Urgency indicators
    URGENCY_KEYWORDS = {
        "critical": ["critical", "emergency", "urgent", "asap", "immediately"],
        "high": ["important", "quickly", "soon", "deadline", "priority"],
        "normal": ["when possible", "normal", "standard", "regular"],
        "low": ["no rush", "eventually", "low priority", "whenever"],
    }

    # Technical proficiency indicators
    PROFICIENCY_INDICATORS = {
        "expert": ["developer", "IT professional", "sysadmin", "engineer"],
        "advanced": ["power user", "experienced", "technical"],
        "intermediate": ["familiar", "some experience", "moderate"],
        "beginner": ["new user", "novice", "beginner", "not technical"],
    }

    def __init__(self):
        """Initialize the context ingestor."""
        self._compiled_patterns = self._compile_patterns()

    def _compile_patterns(self) -> Dict[str, re.Pattern]:
        """Pre-compile regex patterns for efficiency."""
        return {
            "email": re.compile(
                r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b"
            ),
            "time": re.compile(
                r"\b(\d{1,2}:\d{2}(?::\d{2})?(?:\s*[AP]M)?)\b", re.IGNORECASE
            ),
            "date": re.compile(
                r"\b(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})\b"
            ),
            "version": re.compile(
                r"\b(?:version|v\.?)\s*([\d.]+)\b", re.IGNORECASE
            ),
        }

    def ingest_user_input(
        self,
        user_input: str,
        additional_metadata: Optional[Dict[str, Any]] = None,
    ) -> UserContext:
        """
        Process user input to extract structured context.

        Args:
            user_input: Natural language description from user
            additional_metadata: Optional additional context

        Returns:
            Structured UserContext object
        """
        context = UserContext(reported_issue=user_input)

        # Extract temporal information
        context.occurrence_time = self._extract_occurrence_time(user_input)

        # Extract affected accounts
        context.affected_accounts = self._extract_affected_accounts(user_input)

        # Extract recent changes
        context.recent_changes = self._extract_recent_changes(user_input)

        # Extract attempted solutions
        context.attempted_solutions = self._extract_attempted_solutions(user_input)

        # Assess business impact
        context.business_impact = self._assess_business_impact(user_input)

        # Determine urgency
        context.urgency_level = self._determine_urgency(user_input)

        # Assess technical proficiency
        context.technical_proficiency = self._assess_proficiency(user_input)

        # Detect emotional state
        emotion_result = EmotionTemplates.detect_emotion(user_input)
        context.emotional_state = emotion_result.primary_emotion.value

        # Merge additional metadata if provided
        if additional_metadata:
            self._merge_metadata(context, additional_metadata)

        return context

    def _extract_occurrence_time(self, text: str) -> Optional[datetime]:
        """Extract when the issue occurred from text."""
        now = datetime.now()
        text_lower = text.lower()

        # Check for relative time expressions
        for time_phrase, delta in self.TIME_PATTERNS.items():
            if time_phrase in text_lower:
                return now - delta

        # Check for specific time mentions
        time_match = self._compiled_patterns["time"].search(text)
        if time_match:
            # For specific times, assume today
            time_str = time_match.group(1)
            try:
                # Simple parsing - would need enhancement for production
                return now.replace(
                    hour=int(time_str.split(":")[0]) % 24,
                    minute=int(time_str.split(":")[1][:2]),
                    second=0,
                    microsecond=0,
                )
            except (ValueError, IndexError):
                pass

        # Check for specific date mentions
        date_match = self._compiled_patterns["date"].search(text)
        if date_match:
            # Simple date parsing - would need enhancement for production
            return now  # Placeholder

        return None

    def _extract_affected_accounts(self, text: str) -> List[str]:
        """Extract email accounts mentioned in the text."""
        accounts = []

        # Find email addresses
        email_matches = self._compiled_patterns["email"].findall(text)
        accounts.extend(email_matches)

        # Look for provider mentions
        providers = ["gmail", "outlook", "yahoo", "icloud", "hotmail", "exchange"]
        text_lower = text.lower()
        for provider in providers:
            if provider in text_lower:
                # Add as a provider reference if not already captured as email
                if not any(provider in acc.lower() for acc in accounts):
                    accounts.append(f"{provider} account")

        return accounts

    def _extract_recent_changes(self, text: str) -> List[str]:
        """Extract mentions of recent system or application changes."""
        changes = []
        text_lower = text.lower()

        change_indicators = [
            (r"updated?\s+(\w+)", "Updated {}"),
            (r"installed?\s+(\w+)", "Installed {}"),
            (r"upgraded?\s+(\w+)", "Upgraded {}"),
            (r"changed?\s+(\w+)", "Changed {}"),
            (r"new\s+(\w+)", "New {}"),
            (r"recently\s+(\w+)", "Recently {}"),
        ]

        for pattern, template in change_indicators:
            matches = re.findall(pattern, text_lower)
            for match in matches:
                if len(match) > 2:  # Filter out very short matches
                    changes.append(template.format(match))

        # Check for specific change mentions
        if "windows update" in text_lower:
            changes.append("Windows Update")
        if "antivirus" in text_lower or "firewall" in text_lower:
            changes.append("Security software changes")
        if "password" in text_lower and "change" in text_lower:
            changes.append("Password change")

        return changes[:5]  # Limit to 5 most relevant changes

    def _extract_attempted_solutions(self, text: str) -> List[str]:
        """Extract what the user has already tried."""
        solutions = []
        text_lower = text.lower()

        # Common troubleshooting phrases
        attempt_patterns = [
            r"i(?:'ve)?\s+tried\s+(.+?)(?:\.|,|but|and|\n|$)",
            r"already\s+(.+?)(?:\.|,|but|and|\n|$)",
            r"attempted\s+to\s+(.+?)(?:\.|,|but|and|\n|$)",
            r"i\s+(\w+ed)\s+(?:the\s+)?(.+?)(?:\.|,|but|and|\n|$)",
        ]

        for pattern in attempt_patterns:
            matches = re.findall(pattern, text_lower, re.IGNORECASE)
            for match in matches:
                if isinstance(match, tuple):
                    solution = " ".join(match).strip()
                else:
                    solution = match.strip()

                if len(solution) > 5 and len(solution) < 100:
                    solutions.append(self._clean_solution_text(solution))

        # Look for specific common attempts
        if "restart" in text_lower:
            solutions.append("Restarted application/computer")
        if "reinstall" in text_lower:
            solutions.append("Reinstalled Mailbird")
        if "clear" in text_lower and "cache" in text_lower:
            solutions.append("Cleared cache")

        return list(set(solutions))[:5]  # Unique solutions, max 5

    def _clean_solution_text(self, text: str) -> str:
        """Clean and normalize solution text."""
        # Remove common filler words
        text = re.sub(r"\b(to|the|a|an)\b", "", text)
        # Collapse whitespace
        text = " ".join(text.split())
        # Capitalize first letter
        return text.strip().capitalize() if text else ""

    def _assess_business_impact(self, text: str) -> str:
        """Assess the business impact from user description."""
        text_lower = text.lower()

        # Critical impact indicators
        if any(
            phrase in text_lower
            for phrase in [
                "can't work",
                "business critical",
                "losing money",
                "clients waiting",
                "deadline",
                "completely blocked",
            ]
        ):
            return "Critical - Unable to conduct business"

        # High impact indicators
        if any(
            phrase in text_lower
            for phrase in [
                "affecting work",
                "productivity",
                "multiple users",
                "team blocked",
                "important emails",
            ]
        ):
            return "High - Significant productivity impact"

        # Medium impact indicators
        if any(
            phrase in text_lower
            for phrase in [
                "annoying",
                "slowing down",
                "intermittent",
                "sometimes",
                "occasionally",
            ]
        ):
            return "Medium - Workflow disruption"

        # Low impact
        return "Low - Minor inconvenience"

    def _determine_urgency(self, text: str) -> str:
        """Determine urgency level from user input."""
        text_lower = text.lower()

        for urgency_level, keywords in self.URGENCY_KEYWORDS.items():
            if any(keyword in text_lower for keyword in keywords):
                return urgency_level

        # Default based on emotional content
        emotion_result = EmotionTemplates.detect_emotion(text)
        if emotion_result.primary_emotion.value in ["urgent", "anxious", "frustrated"]:
            return "high"

        return "normal"

    def _assess_proficiency(self, text: str) -> str:
        """Assess user's technical proficiency from their description."""
        text_lower = text.lower()

        # Check for proficiency indicators
        for level, indicators in self.PROFICIENCY_INDICATORS.items():
            if any(indicator in text_lower for indicator in indicators):
                return level

        # Analyze technical terminology usage
        technical_terms = [
            "imap", "smtp", "ssl", "port", "certificate",
            "database", "cache", "registry", "protocol",
            "authentication", "oauth", "api", "server",
        ]

        technical_count = sum(1 for term in technical_terms if term in text_lower)

        if technical_count >= 4:
            return "advanced"
        elif technical_count >= 2:
            return "intermediate"
        else:
            return "beginner"

    def _merge_metadata(
        self,
        context: UserContext,
        metadata: Dict[str, Any]
    ):
        """Merge additional metadata into context."""
        # Override with explicit metadata if provided
        if "urgency" in metadata:
            context.urgency_level = metadata["urgency"]
        if "technical_level" in metadata:
            context.technical_proficiency = metadata["technical_level"]
        if "accounts" in metadata:
            context.affected_accounts.extend(metadata["accounts"])
        if "business_impact" in metadata:
            context.business_impact = metadata["business_impact"]

    def enhance_with_log_correlation(
        self,
        context: UserContext,
        log_timestamp_range: Tuple[datetime, datetime],
    ) -> UserContext:
        """
        Enhance user context by correlating with log timestamps.

        Args:
            context: User context to enhance
            log_timestamp_range: Tuple of (start, end) timestamps from logs

        Returns:
            Enhanced UserContext
        """
        log_start, log_end = log_timestamp_range

        # If no occurrence time specified, use log evidence
        if not context.occurrence_time:
            # Assume issue started near the beginning of error logs
            context.occurrence_time = log_start
        else:
            # Validate occurrence time against log range
            if context.occurrence_time < log_start:
                logger.info(
                    "User reported time precedes log errors, adjusting to log start"
                )
                context.occurrence_time = log_start

        # Add timing information to business impact if significant delay
        if context.occurrence_time:
            duration = datetime.now() - context.occurrence_time
            if duration > timedelta(days=1):
                context.business_impact += f" (Issue ongoing for {duration.days} days)"
            elif duration > timedelta(hours=4):
                hours = duration.total_seconds() / 3600
                context.business_impact += f" (Issue ongoing for {hours:.0f} hours)"

        return context

    def generate_contextual_summary(self, context: UserContext) -> str:
        """
        Generate a human-readable summary of the user context.

        Args:
            context: UserContext to summarize

        Returns:
            Formatted summary string
        """
        summary_parts = []

        # Issue summary
        if len(context.reported_issue) > 100:
            summary_parts.append(f"Issue: {context.reported_issue[:100]}...")
        else:
            summary_parts.append(f"Issue: {context.reported_issue}")

        # Timing
        if context.occurrence_time:
            time_ago = datetime.now() - context.occurrence_time
            if time_ago < timedelta(hours=1):
                summary_parts.append("Started: Less than an hour ago")
            elif time_ago < timedelta(days=1):
                hours = time_ago.total_seconds() / 3600
                summary_parts.append(f"Started: {hours:.0f} hours ago")
            else:
                summary_parts.append(f"Started: {time_ago.days} days ago")

        # Affected accounts
        if context.affected_accounts:
            summary_parts.append(
                f"Affected: {', '.join(context.affected_accounts[:3])}"
            )

        # Urgency and impact
        summary_parts.append(f"Urgency: {context.urgency_level}")
        summary_parts.append(f"Impact: {context.business_impact}")

        # Previous attempts
        if context.attempted_solutions:
            summary_parts.append(
                f"Already tried: {', '.join(context.attempted_solutions[:2])}"
            )

        # User profile
        summary_parts.append(f"User level: {context.technical_proficiency}")
        summary_parts.append(f"Emotional state: {context.emotional_state}")

        return " | ".join(summary_parts)