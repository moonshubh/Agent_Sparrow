"""
Quality Validator

Validates and scores the quality of log analysis responses to ensure
they meet standards for completeness, accuracy, empathy, and readability.
"""

from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, field
from enum import Enum
import re

from app.agents_v2.primary_agent.prompts.emotion_templates import EmotionalState
from ..schemas.log_schemas import LogAnalysisResult


class QualityDimension(Enum):
    """Dimensions of quality assessment"""
    METADATA_COMPLETENESS = ("metadata_completeness", 0.18)
    ERROR_IDENTIFICATION = ("error_identification", 0.22)
    ROOT_CAUSE_ACCURACY = ("root_cause_accuracy", 0.15)
    SOLUTION_QUALITY = ("solution_quality", 0.25)
    RESPONSE_FORMATTING = ("response_formatting", 0.10)
    EMOTIONAL_APPROPRIATENESS = ("emotional_appropriateness", 0.10)

    def __init__(self, key: str, weight: float):
        self.key = key
        self.weight = weight


@dataclass
class QualityIssue:
    """Represents a quality issue found during validation"""
    dimension: QualityDimension
    severity: str  # "critical", "major", "minor"
    description: str
    suggestion: str


@dataclass
class QualityScore:
    """Quality score with breakdown by dimension"""
    overall_score: float  # 0.0 to 1.0
    dimension_scores: Dict[QualityDimension, float] = field(default_factory=dict)
    issues: List[QualityIssue] = field(default_factory=list)
    passed: bool = False
    confidence_level: float = 0.0


@dataclass
class ValidationResult:
    """Result of quality validation"""
    score: QualityScore
    is_acceptable: bool
    needs_revision: bool
    revision_suggestions: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)


class QualityValidator:
    """
    Validates response quality across multiple dimensions.

    Features:
    - Multi-dimensional quality scoring
    - Issue identification and suggestions
    - Readability assessment
    - Emotional tone validation
    - Completeness checking
    """

    # Minimum acceptable scores
    MIN_OVERALL_SCORE = 0.7
    MIN_DIMENSION_SCORE = 0.5

    # Readability targets
    TARGET_GRADE_LEVEL = 12  # High school level
    MAX_SENTENCE_LENGTH = 30  # words
    MAX_PARAGRAPH_LENGTH = 150  # words

    # Required response sections
    REQUIRED_SECTIONS = [
        "metadata",
        "root_cause",
        "solution",
        "closing"
    ]

    def __init__(self):
        """Initialize the quality validator"""
        self.strict_mode = False
        self.require_all_sections = True

    def validate_response(
        self,
        response: str,
        analysis: LogAnalysisResult,
        emotional_state: EmotionalState,
        user_context: Optional[Dict[str, Any]] = None
    ) -> ValidationResult:
        """
        Validate the quality of a generated response.

        Args:
            response: Generated response text
            analysis: Original log analysis
            emotional_state: Detected emotional state
            user_context: Additional user context

        Returns:
            Validation result with score and suggestions
        """
        score = QualityScore(overall_score=0.0)

        # Validate each dimension
        self._check_metadata_completeness(response, analysis, score)
        self._check_error_identification(response, analysis, score)
        self._check_root_cause_accuracy(response, analysis, score)
        self._check_solution_quality(response, analysis, score)
        self._check_response_formatting(response, score)
        self._check_emotional_appropriateness(response, emotional_state, score)

        # Calculate overall score
        score.overall_score = self._calculate_overall_score(score.dimension_scores)
        score.passed = score.overall_score >= self.MIN_OVERALL_SCORE

        # Determine confidence level
        score.confidence_level = self._calculate_confidence(score)

        # Create validation result
        result = ValidationResult(
            score=score,
            is_acceptable=score.passed,
            needs_revision=not score.passed or len(score.issues) > 0
        )

        # Add revision suggestions
        if result.needs_revision:
            result.revision_suggestions = self._generate_revision_suggestions(score)

        # Add warnings for minor issues
        result.warnings = self._generate_warnings(score, response)

        return result

    def _check_metadata_completeness(
        self,
        response: str,
        analysis: LogAnalysisResult,
        score: QualityScore
    ) -> None:
        """Check if metadata is complete and accurate"""
        dimension_score = 1.0
        issues = []

        # Check for version information
        if analysis.metadata and analysis.metadata.mailbird_version:
            if analysis.metadata.mailbird_version not in response:
                dimension_score -= 0.2
                issues.append(QualityIssue(
                    dimension=QualityDimension.METADATA_COMPLETENESS,
                    severity="minor",
                    description="Missing Mailbird version",
                    suggestion="Include Mailbird version in metadata section"
                ))

        # Check for OS information
        if analysis.metadata and analysis.metadata.os_version:
            if analysis.metadata.os_version != "Unknown" and analysis.metadata.os_version not in response:
                dimension_score -= 0.1
                issues.append(QualityIssue(
                    dimension=QualityDimension.METADATA_COMPLETENESS,
                    severity="minor",
                    description="Missing OS version",
                    suggestion="Include operating system information"
                ))

        # Check for error statistics
        if analysis.metadata and hasattr(analysis.metadata, 'error_count') and analysis.metadata.error_count:
            if analysis.metadata.error_count > 0:
                error_count_str = str(analysis.metadata.error_count)
                if error_count_str not in response:
                    dimension_score -= 0.2
                    issues.append(QualityIssue(
                        dimension=QualityDimension.METADATA_COMPLETENESS,
                        severity="major",
                        description="Missing error count",
                        suggestion="Include error statistics in metadata"
                    ))

        # Check for account information if relevant
        if analysis.metadata and hasattr(analysis.metadata, 'account_count') and analysis.metadata.account_count:
            if analysis.metadata.account_count > 0 and "account" not in response.lower():
                dimension_score -= 0.1

        score.dimension_scores[QualityDimension.METADATA_COMPLETENESS] = max(0, dimension_score)
        score.issues.extend(issues)

    def _check_error_identification(
        self,
        response: str,
        analysis: LogAnalysisResult,
        score: QualityScore
    ) -> None:
        """Check if errors are properly identified and highlighted"""
        dimension_score = 1.0

        # Check if error patterns are mentioned
        if analysis.error_patterns:
            patterns_mentioned = 0
            for pattern in analysis.error_patterns[:3]:  # Check top 3 patterns
                if pattern.description.lower() in response.lower():
                    patterns_mentioned += 1

            coverage = patterns_mentioned / min(3, len(analysis.error_patterns))
            dimension_score = coverage

            if coverage < 0.5:
                score.issues.append(QualityIssue(
                    dimension=QualityDimension.ERROR_IDENTIFICATION,
                    severity="major",
                    description="Insufficient error pattern coverage",
                    suggestion="Include more specific error patterns in the analysis"
                ))

        # Check for error highlighting (code blocks)
        if "```" not in response and analysis.error_patterns:
            dimension_score -= 0.3
            score.issues.append(QualityIssue(
                dimension=QualityDimension.ERROR_IDENTIFICATION,
                severity="major",
                description="No error code blocks",
                suggestion="Add code blocks to highlight specific errors"
            ))

        score.dimension_scores[QualityDimension.ERROR_IDENTIFICATION] = max(0, dimension_score)

    def _check_root_cause_accuracy(
        self,
        response: str,
        analysis: LogAnalysisResult,
        score: QualityScore
    ) -> None:
        """Check if root cause is accurately presented"""
        dimension_score = 1.0

        if analysis.root_causes:
            # Check if primary root cause is mentioned
            top_cause = analysis.top_priority_cause
            if top_cause:
                if top_cause.title.lower() not in response.lower():
                    dimension_score -= 0.4
                    score.issues.append(QualityIssue(
                        dimension=QualityDimension.ROOT_CAUSE_ACCURACY,
                        severity="critical",
                        description="Primary root cause not mentioned",
                        suggestion="Include the primary root cause clearly"
                    ))

                # Check confidence mention
                confidence_score = getattr(top_cause, "confidence_score", None)
                if isinstance(confidence_score, (int, float)):
                    confidence_token = f"{confidence_score:.0%}"
                    if confidence_token not in response:
                        dimension_score -= 0.1
                else:
                    dimension_score -= 0.1

            # Check for root cause section
            if "root cause" not in response.lower() and "main issue" not in response.lower():
                dimension_score -= 0.3
                score.issues.append(QualityIssue(
                    dimension=QualityDimension.ROOT_CAUSE_ACCURACY,
                    severity="major",
                    description="No clear root cause section",
                    suggestion="Add a clear root cause section"
                ))
        else:
            # No root causes - check if this is mentioned
            if "no critical issues" not in response.lower() and "running normally" not in response.lower():
                dimension_score -= 0.2

        score.dimension_scores[QualityDimension.ROOT_CAUSE_ACCURACY] = max(0, dimension_score)

    def _check_solution_quality(
        self,
        response: str,
        analysis: LogAnalysisResult,
        score: QualityScore
    ) -> None:
        """Check solution quality and completeness"""
        dimension_score = 1.0

        if analysis.root_causes:
            # Check for solution steps
            has_numbered_steps = bool(re.search(r'\d+\.\s+\w+', response))
            if not has_numbered_steps:
                dimension_score -= 0.3
                score.issues.append(QualityIssue(
                    dimension=QualityDimension.SOLUTION_QUALITY,
                    severity="major",
                    description="No numbered solution steps",
                    suggestion="Format solutions as numbered steps"
                ))

            # Check for time estimates
            if "minute" not in response.lower() and analysis.estimated_resolution_time > 0:
                dimension_score -= 0.1

            # Check for solution completeness
            top_cause = analysis.top_priority_cause
            if top_cause and top_cause.resolution_steps:
                steps_mentioned = sum(
                    1 for step in top_cause.resolution_steps
                    if any(word in response.lower() for word in step.lower().split()[:3])
                )
                coverage = steps_mentioned / len(top_cause.resolution_steps)
                if coverage < 0.5:
                    dimension_score -= 0.3
                    score.issues.append(QualityIssue(
                        dimension=QualityDimension.SOLUTION_QUALITY,
                        severity="major",
                        description="Incomplete solution steps",
                        suggestion="Include all resolution steps"
                    ))

        score.dimension_scores[QualityDimension.SOLUTION_QUALITY] = max(0, dimension_score)

    def _check_response_formatting(
        self,
        response: str,
        score: QualityScore
    ) -> None:
        """Check response formatting and structure"""
        dimension_score = 1.0

        # Check for headers
        header_count = len(re.findall(r'^#{1,3}\s+', response, re.MULTILINE))
        if header_count < 2:
            dimension_score -= 0.2
            score.issues.append(QualityIssue(
                dimension=QualityDimension.RESPONSE_FORMATTING,
                severity="minor",
                description="Insufficient section headers",
                suggestion="Add more section headers for better structure"
            ))

        # Check for proper markdown
        if not re.search(r'\*\*[^*]+\*\*', response):  # No bold text
            dimension_score -= 0.1

        # Check paragraph length
        paragraphs = response.split('\n\n')
        long_paragraphs = [p for p in paragraphs if len(p.split()) > self.MAX_PARAGRAPH_LENGTH]
        if long_paragraphs:
            dimension_score -= 0.1
            score.issues.append(QualityIssue(
                dimension=QualityDimension.RESPONSE_FORMATTING,
                severity="minor",
                description="Some paragraphs are too long",
                suggestion="Break up long paragraphs for better readability"
            ))

        # Check for required sections
        if self.require_all_sections:
            missing_sections = []
            for section in self.REQUIRED_SECTIONS:
                if section == "metadata" and "system information" not in response.lower():
                    missing_sections.append("metadata")
                elif section == "root_cause" and "root cause" not in response.lower() and "main issue" not in response.lower():
                    missing_sections.append("root cause")
                elif section == "solution" and not re.search(r'solution|fix|resolve', response.lower()):
                    missing_sections.append("solution")
                elif section == "closing" and not response.strip().endswith(("!", ".", "?")):
                    missing_sections.append("closing")

            if missing_sections:
                dimension_score -= 0.15 * len(missing_sections)
                score.issues.append(QualityIssue(
                    dimension=QualityDimension.RESPONSE_FORMATTING,
                    severity="major",
                    description=f"Missing sections: {', '.join(missing_sections)}",
                    suggestion="Include all required response sections"
                ))

        score.dimension_scores[QualityDimension.RESPONSE_FORMATTING] = max(0, dimension_score)

    def _check_emotional_appropriateness(
        self,
        response: str,
        emotional_state: EmotionalState,
        score: QualityScore
    ) -> None:
        """Check if emotional tone is appropriate"""
        dimension_score = 1.0

        # Check for appropriate language based on emotional state
        if emotional_state == EmotionalState.FRUSTRATED:
            # Should acknowledge frustration
            if not any(word in response.lower() for word in ["understand", "frustrat", "annoying", "apologize"]):
                dimension_score -= 0.3
                score.issues.append(QualityIssue(
                    dimension=QualityDimension.EMOTIONAL_APPROPRIATENESS,
                    severity="major",
                    description="Doesn't acknowledge user frustration",
                    suggestion="Add empathetic acknowledgment of frustration"
                ))

        elif emotional_state == EmotionalState.ANXIOUS:
            # Should be reassuring
            if not any(word in response.lower() for word in ["don't worry", "help", "resolve", "fix"]):
                dimension_score -= 0.3
                score.issues.append(QualityIssue(
                    dimension=QualityDimension.EMOTIONAL_APPROPRIATENESS,
                    severity="major",
                    description="Not reassuring enough for anxious user",
                    suggestion="Add reassuring language"
                ))

        elif emotional_state == EmotionalState.CONFUSED:
            # Should be clear and simple
            complex_sentences = [
                s for s in response.split('.')
                if len(s.split()) > self.MAX_SENTENCE_LENGTH
            ]
            if len(complex_sentences) > 3:
                dimension_score -= 0.2
                score.issues.append(QualityIssue(
                    dimension=QualityDimension.EMOTIONAL_APPROPRIATENESS,
                    severity="minor",
                    description="Language too complex for confused user",
                    suggestion="Simplify language and use shorter sentences"
                ))

        elif emotional_state == EmotionalState.PROFESSIONAL:
            # Should be formal
            informal_words = ["hey", "gonna", "wanna", "stuff", "things"]
            if any(word in response.lower() for word in informal_words):
                dimension_score -= 0.2
                score.issues.append(QualityIssue(
                    dimension=QualityDimension.EMOTIONAL_APPROPRIATENESS,
                    severity="minor",
                    description="Too informal for professional context",
                    suggestion="Use more formal language"
                ))

        score.dimension_scores[QualityDimension.EMOTIONAL_APPROPRIATENESS] = max(0, dimension_score)

    def _calculate_overall_score(self, dimension_scores: Dict[QualityDimension, float]) -> float:
        """Calculate weighted overall score"""
        total = 0.0
        for dimension, score in dimension_scores.items():
            total += score * dimension.weight
        return total

    def _calculate_confidence(self, score: QualityScore) -> float:
        """Calculate confidence level based on scores and issues"""
        base_confidence = score.overall_score

        # Reduce confidence for critical issues
        critical_issues = [i for i in score.issues if i.severity == "critical"]
        base_confidence -= 0.1 * len(critical_issues)

        # Reduce confidence for major issues
        major_issues = [i for i in score.issues if i.severity == "major"]
        base_confidence -= 0.05 * len(major_issues)

        return max(0.0, min(1.0, base_confidence))

    def _generate_revision_suggestions(self, score: QualityScore) -> List[str]:
        """Generate specific revision suggestions"""
        suggestions = []

        # Group issues by dimension
        issues_by_dimension = {}
        for issue in score.issues:
            if issue.dimension not in issues_by_dimension:
                issues_by_dimension[issue.dimension] = []
            issues_by_dimension[issue.dimension].append(issue)

        # Generate suggestions for each dimension
        for dimension, issues in issues_by_dimension.items():
            if issues:
                # Use the most severe issue's suggestion
                most_severe = max(issues, key=lambda x: {"critical": 3, "major": 2, "minor": 1}[x.severity])
                suggestions.append(most_severe.suggestion)

        return suggestions

    def _generate_warnings(self, score: QualityScore, response: str) -> List[str]:
        """Generate warnings for minor issues"""
        warnings = []

        # Check response length
        if len(response) < 500:
            warnings.append("Response may be too brief")
        elif len(response) > 5000:
            warnings.append("Response may be too long")

        # Check for technical jargon
        technical_terms = ["exception", "thread", "heap", "stack", "daemon", "mutex"]
        jargon_count = sum(1 for term in technical_terms if term in response.lower())
        if jargon_count > 5:
            warnings.append("Response contains significant technical jargon")

        return warnings

    def calculate_readability_score(self, text: str) -> float:
        """
        Calculate readability score using Flesch Reading Ease formula.

        Args:
            text: Text to analyze

        Returns:
            Readability score (0-100, higher is easier)
        """
        sentences = text.split('.')
        words = text.split()
        syllables = sum(self._count_syllables(word) for word in words)

        if len(sentences) == 0 or len(words) == 0:
            return 0.0

        # Flesch Reading Ease formula
        avg_sentence_length = len(words) / len(sentences)
        avg_syllables_per_word = syllables / len(words)

        score = 206.835 - 1.015 * avg_sentence_length - 84.6 * avg_syllables_per_word
        return max(0, min(100, score))

    def _count_syllables(self, word: str) -> int:
        """Count syllables in a word (approximation)"""
        word = word.lower()
        vowels = "aeiouyw"
        syllables = 0
        previous_was_vowel = False

        for char in word:
            is_vowel = char in vowels
            if is_vowel and not previous_was_vowel:
                syllables += 1
            previous_was_vowel = is_vowel

        # Adjust for silent e
        if word.endswith("e"):
            syllables -= 1

        return max(1, syllables)
