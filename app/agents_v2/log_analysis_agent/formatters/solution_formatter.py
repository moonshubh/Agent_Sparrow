"""
Solution Formatter

Formats solutions, workarounds, and resolution steps into clear,
actionable instructions with confidence scores and time estimates.
"""

from typing import List, Optional, Dict, Any, Tuple
from dataclasses import dataclass
from enum import Enum

from ..schemas.log_schemas import RootCause, IssueImpact


class SolutionType(Enum):
    """Types of solutions"""
    QUICK_FIX = "quick_fix"
    WORKAROUND = "workaround"
    PERMANENT_FIX = "permanent_fix"
    CONFIGURATION = "configuration"
    UPDATE_REQUIRED = "update_required"
    SUPPORT_REQUIRED = "support_required"


class Difficulty(Enum):
    """Solution difficulty levels"""
    EASY = ("Easy", "🟢", 5)  # name, icon, minutes
    MODERATE = ("Moderate", "🟡", 15)
    ADVANCED = ("Advanced", "🟠", 30)
    EXPERT = ("Expert", "🔴", 60)

    def __init__(self, display_name: str, icon: str, est_minutes: int):
        self.display_name = display_name
        self.icon = icon
        self.est_minutes = est_minutes


@dataclass
class Solution:
    """Represents a solution or workaround"""
    title: str
    steps: List[str]
    solution_type: SolutionType
    difficulty: Difficulty
    confidence_score: float
    estimated_time_minutes: int
    requires_restart: bool = False
    data_loss_risk: bool = False
    prerequisites: List[str] = None
    warnings: List[str] = None
    success_indicators: List[str] = None


class SolutionFormatter:
    """
    Formats solutions and resolution steps into user-friendly instructions.

    Features:
    - Step-by-step instructions with numbering
    - Time estimates and difficulty indicators
    - Confidence scores and warnings
    - Success verification steps
    - Alternative solutions
    """

    # Solution type icons
    SOLUTION_ICONS = {
        SolutionType.QUICK_FIX: "⚡",
        SolutionType.WORKAROUND: "🔄",
        SolutionType.PERMANENT_FIX: "✅",
        SolutionType.CONFIGURATION: "⚙️",
        SolutionType.UPDATE_REQUIRED: "⬆️",
        SolutionType.SUPPORT_REQUIRED: "🆘"
    }

    # Confidence level descriptions
    CONFIDENCE_LEVELS = {
        (0.9, 1.0): ("Very High", "💚"),
        (0.7, 0.9): ("High", "🟢"),
        (0.5, 0.7): ("Moderate", "🟡"),
        (0.3, 0.5): ("Low", "🟠"),
        (0.0, 0.3): ("Uncertain", "🔴")
    }

    def __init__(self):
        """Initialize the solution formatter"""
        self.show_time_estimates = True
        self.show_confidence = True
        self.show_difficulty = True

    def format_root_cause_solutions(self, root_cause: RootCause) -> str:
        """
        Format solutions for a root cause.

        Args:
            root_cause: Root cause with resolution steps

        Returns:
            Formatted solution section
        """
        lines = []

        # Header with confidence
        confidence_desc, confidence_icon = self._get_confidence_description(root_cause.confidence_score)
        lines.append(f"## 🔧 Solution for: {root_cause.title}")
        lines.append("")
        lines.append(f"**Confidence**: {confidence_icon} {confidence_desc} ({root_cause.confidence_score:.0%})")

        # Time estimate
        if root_cause.estimated_resolution_time:
            time_desc = self._format_time_estimate(root_cause.estimated_resolution_time)
            lines.append(f"**Estimated Time**: ⏱️ {time_desc}")

        # Impact level
        impact_icon = self._get_impact_icon(root_cause.impact)
        lines.append(f"**Impact**: {impact_icon} {root_cause.impact.value.title()}")
        lines.append("")

        # Resolution steps
        if root_cause.resolution_steps:
            lines.append("### Resolution Steps:")
            lines.append("")

            for i, step in enumerate(root_cause.resolution_steps, 1):
                formatted_step = self._format_step(i, step)
                lines.append(formatted_step)

            lines.append("")

        # Preventive measures
        if root_cause.preventive_measures:
            lines.append("### 🛡️ Prevention Tips:")
            lines.append("")

            for measure in root_cause.preventive_measures:
                lines.append(f"- {measure}")

            lines.append("")

        # Support escalation note
        if root_cause.requires_support:
            lines.append(self._format_escalation_note(root_cause))

        return "\n".join(lines)

    def format_solution(self, solution: Solution) -> str:
        """
        Format a complete solution with all details.

        Args:
            solution: Solution to format

        Returns:
            Formatted solution markdown
        """
        lines = []

        # Title with solution type icon
        icon = self.SOLUTION_ICONS.get(solution.solution_type, "🔧")
        lines.append(f"### {icon} {solution.title}")
        lines.append("")

        # Metadata badges
        badges = []

        if self.show_difficulty:
            badges.append(f"{solution.difficulty.icon} {solution.difficulty.display_name}")

        if self.show_time_estimates:
            time_est = self._format_time_estimate(solution.estimated_time_minutes)
            badges.append(f"⏱️ {time_est}")

        if self.show_confidence:
            conf_desc, conf_icon = self._get_confidence_description(solution.confidence_score)
            badges.append(f"{conf_icon} {conf_desc}")

        if badges:
            lines.append(" • ".join(badges))
            lines.append("")

        # Warnings
        if solution.warnings:
            for warning in solution.warnings:
                lines.append(f"> ⚠️ **Warning**: {warning}")
            lines.append("")

        # Data loss risk
        if solution.data_loss_risk:
            lines.append("> 🚨 **Important**: This solution may result in data loss. Please backup your data first.")
            lines.append("")

        # Prerequisites
        if solution.prerequisites:
            lines.append("**Prerequisites:**")
            for prereq in solution.prerequisites:
                lines.append(f"- {prereq}")
            lines.append("")

        # Main steps
        lines.append("**Steps:**")
        lines.append("")

        for i, step in enumerate(solution.steps, 1):
            formatted_step = self._format_detailed_step(i, step)
            lines.append(formatted_step)

        lines.append("")

        # Restart required
        if solution.requires_restart:
            lines.append("📝 **Note**: Mailbird restart required after completing these steps.")
            lines.append("")

        # Success indicators
        if solution.success_indicators:
            lines.append("**How to verify success:**")
            for indicator in solution.success_indicators:
                lines.append(f"- ✓ {indicator}")
            lines.append("")

        return "\n".join(lines)

    def format_multiple_solutions(self, solutions: List[Solution]) -> str:
        """
        Format multiple alternative solutions.

        Args:
            solutions: List of solutions to format

        Returns:
            Formatted solutions with tabs or sections
        """
        if not solutions:
            return self._format_no_solutions_available()

        lines = []
        lines.append("## 🔧 Available Solutions")
        lines.append("")

        # Sort by confidence and estimated time (prefer quicker solutions when confidence is equal)
        sorted_solutions = sorted(
            solutions,
            key=lambda s: (s.confidence_score, -s.estimated_time_minutes),
            reverse=True
        )

        # Mark recommended solution
        lines.append("> 💡 **Recommended**: Start with the first solution (highest confidence)")
        lines.append("")

        # Format each solution
        for i, solution in enumerate(sorted_solutions, 1):
            if i > 1:
                lines.append("---")
                lines.append("")

            lines.append(f"### Option {i}: {solution.title}")

            # Quick metadata line
            metadata = []
            metadata.append(f"{solution.difficulty.icon} {solution.difficulty.display_name}")
            metadata.append(f"⏱️ ~{solution.estimated_time_minutes} min")
            metadata.append(f"Confidence: {solution.confidence_score:.0%}")

            lines.append(f"*{' • '.join(metadata)}*")
            lines.append("")

            # Steps summary (collapsed for alternatives)
            if i == 1:
                # Full steps for recommended solution
                for j, step in enumerate(solution.steps, 1):
                    lines.append(f"{j}. {step}")
            else:
                # Collapsed for alternatives
                lines.append("<details>")
                lines.append(f"<summary>Show steps</summary>")
                lines.append("")
                for j, step in enumerate(solution.steps, 1):
                    lines.append(f"{j}. {step}")
                lines.append("")
                lines.append("</details>")

            lines.append("")

        return "\n".join(lines)

    def format_workaround(self, title: str, steps: List[str],
                         permanent_fix_available: bool = False) -> str:
        """
        Format a temporary workaround.

        Args:
            title: Workaround title
            steps: Workaround steps
            permanent_fix_available: Whether a permanent fix exists

        Returns:
            Formatted workaround section
        """
        lines = []
        lines.append(f"### 🔄 Temporary Workaround: {title}")
        lines.append("")

        if permanent_fix_available:
            lines.append("> ℹ️ This is a temporary solution. A permanent fix is available below.")
        else:
            lines.append("> ℹ️ This workaround will help until a permanent fix is available.")

        lines.append("")

        for i, step in enumerate(steps, 1):
            lines.append(f"{i}. {step}")

        lines.append("")
        return "\n".join(lines)

    def _format_step(self, number: int, step: str) -> str:
        """Format a single resolution step"""
        # Check for special step types
        if step.lower().startswith("open"):
            icon = "📂"
        elif step.lower().startswith("click"):
            icon = "👆"
        elif step.lower().startswith("restart"):
            icon = "🔄"
        elif step.lower().startswith("delete") or step.lower().startswith("remove"):
            icon = "🗑️"
        elif step.lower().startswith("download"):
            icon = "⬇️"
        elif step.lower().startswith("backup"):
            icon = "💾"
        else:
            icon = ""

        return f"{number}. {icon} {step}"

    def _format_detailed_step(self, number: int, step: str) -> str:
        """Format a detailed step with potential sub-items"""
        # Check if step contains sub-steps (indicated by semicolons or bullets)
        if ";" in step or "•" in step:
            main_step, *sub_steps = step.replace("•", ";").split(";")
            lines = [f"{number}. {main_step.strip()}"]

            for sub_step in sub_steps:
                if sub_step.strip():
                    lines.append(f"   - {sub_step.strip()}")

            return "\n".join(lines)
        else:
            return self._format_step(number, step)

    def _format_time_estimate(self, minutes: int) -> str:
        """Format time estimate in human-readable format"""
        if minutes < 5:
            return "< 5 minutes"
        elif minutes <= 15:
            return f"~{minutes} minutes"
        elif minutes <= 60:
            return f"~{minutes} minutes"
        else:
            hours = minutes / 60
            return f"~{hours:.1f} hours"

    def _get_confidence_description(self, score: float) -> Tuple[str, str]:
        """Get confidence level description and icon"""
        for range_tuple, (desc, icon) in self.CONFIDENCE_LEVELS.items():
            if range_tuple[0] <= score <= range_tuple[1]:
                return desc, icon
        return "Unknown", "❓"

    def _get_impact_icon(self, impact: IssueImpact) -> str:
        """Get icon for impact level"""
        icons = {
            IssueImpact.MINIMAL: "🟢",
            IssueImpact.LOW: "🟡",
            IssueImpact.MEDIUM: "🟠",
            IssueImpact.HIGH: "🔴",
            IssueImpact.CRITICAL: "🚨"
        }
        return icons.get(impact, "⚫")

    def _format_escalation_note(self, root_cause: RootCause) -> str:
        """Format escalation note for support-required issues"""
        lines = []
        lines.append("---")
        lines.append("")
        lines.append("### 🆘 Support Required")
        lines.append("")
        lines.append("This issue requires assistance from Mailbird support team.")
        lines.append("")
        lines.append("**When contacting support, please provide:**")
        lines.append("1. This analysis report")
        lines.append("2. Your log files")
        lines.append(f"3. Issue ID: `{root_cause.cause_id}`")

        if root_cause.escalation_reason:
            lines.append("")
            lines.append(f"**Reason**: {root_cause.escalation_reason}")

        return "\n".join(lines)

    def _format_no_solutions_available(self) -> str:
        """Format message when no solutions are available"""
        return (
            "### ℹ️ Manual Review Required\n\n"
            "No automated solutions are available for this issue. "
            "Please contact Mailbird support with your log files for assistance.\n"
        )

    def format_command_line_solution(self, commands: List[str],
                                   description: str,
                                   requires_admin: bool = False) -> str:
        """
        Format command-line based solutions.

        Args:
            commands: List of commands to execute
            description: Description of what commands do
            requires_admin: Whether admin rights are required

        Returns:
            Formatted command-line solution
        """
        lines = []
        lines.append(f"### 💻 Command Line Solution: {description}")
        lines.append("")

        if requires_admin:
            lines.append("> ⚠️ **Note**: Run Command Prompt as Administrator")
            lines.append("")

        lines.append("```batch")
        for cmd in commands:
            lines.append(cmd)
        lines.append("```")
        lines.append("")
        lines.append("*Copy and paste these commands one by one*")

        return "\n".join(lines)