"""
Adaptive Quality Management System for MB-Sparrow.

This module provides dynamic timeout adjustment based on quality levels,
ensuring high-quality responses while managing processing time.
"""

from enum import Enum
from typing import Any, Dict, Optional, Tuple
import logging
from dataclasses import dataclass

logger = logging.getLogger(__name__)


class QualityLevel(str, Enum):
    """Quality levels for adaptive processing."""

    FAST = "fast"  # 0.5x base timeout - Quick responses
    BALANCED = "balanced"  # 1.0x base timeout - Default
    THOROUGH = "thorough"  # 1.5x base timeout - Complete analysis


@dataclass
class TimeoutConfig:
    """Configuration for timeout values."""

    reasoning_base: int = 30  # Base timeout for reasoning in seconds
    troubleshooting_base: int = 20  # Base timeout for troubleshooting
    diagnostic_base: int = 10  # Base timeout for diagnostic steps
    log_analysis_base: int = 45  # Base timeout for log analysis
    research_base: int = 25  # Base timeout for research


class AdaptiveQualityManager:
    """
    Manages quality-based timeout adjustments for different agent operations.

    This manager allows the system to prioritize quality over speed based on
    user preferences and context requirements.
    """

    def __init__(self, config: Optional[TimeoutConfig] = None):
        """
        Initialize the quality manager with configuration.

        Args:
            config: Optional timeout configuration
        """
        self.config = config or TimeoutConfig()

        # Quality multipliers
        self.multipliers = {
            QualityLevel.FAST: 0.5,
            QualityLevel.BALANCED: 1.0,
            QualityLevel.THOROUGH: 1.5,
        }

        # Track quality metrics
        self.metrics = {
            "fast_requests": 0,
            "balanced_requests": 0,
            "thorough_requests": 0,
            "timeouts_exceeded": 0,
            "quality_adjustments": 0,
        }

    def get_timeout(self, operation: str, quality: QualityLevel) -> int:
        """
        Get the adjusted timeout for an operation based on quality level.

        Args:
            operation: The operation type (reasoning, troubleshooting, etc.)
            quality: The requested quality level

        Returns:
            Adjusted timeout in seconds
        """
        # Get base timeout for operation
        base_timeout = self._get_base_timeout(operation)

        # Apply quality multiplier
        multiplier = self.multipliers[quality]
        adjusted_timeout = int(base_timeout * multiplier)

        # Track metrics
        self.metrics[f"{quality.value}_requests"] += 1

        logger.info(
            f"Timeout for {operation} at {quality.value} quality: {adjusted_timeout}s"
        )

        return adjusted_timeout

    def _get_base_timeout(self, operation: str) -> int:
        """
        Get the base timeout for an operation.

        Args:
            operation: The operation type

        Returns:
            Base timeout in seconds
        """
        operation_timeouts = {
            "reasoning": self.config.reasoning_base,
            "troubleshooting": self.config.troubleshooting_base,
            "diagnostic": self.config.diagnostic_base,
            "log_analysis": self.config.log_analysis_base,
            "research": self.config.research_base,
        }

        return operation_timeouts.get(operation, 30)  # Default to 30s

    def adjust_quality_for_complexity(
        self, quality: QualityLevel, complexity_score: float
    ) -> Tuple[QualityLevel, str]:
        """
        Automatically adjust quality level based on detected complexity.

        Args:
            quality: Requested quality level
            complexity_score: Complexity score (0.0 to 1.0)

        Returns:
            Tuple of (adjusted_quality, reason)
        """
        # High complexity (>0.7) suggests upgrading quality
        if complexity_score > 0.7 and quality == QualityLevel.FAST:
            self.metrics["quality_adjustments"] += 1
            return QualityLevel.BALANCED, "Complexity requires more thorough analysis"

        # Very high complexity (>0.9) suggests maximum quality
        if complexity_score > 0.9 and quality != QualityLevel.THOROUGH:
            self.metrics["quality_adjustments"] += 1
            return (
                QualityLevel.THOROUGH,
                "High complexity detected - using thorough analysis",
            )

        # Low complexity (<0.3) allows downgrading if requested
        if complexity_score < 0.3 and quality == QualityLevel.THOROUGH:
            self.metrics["quality_adjustments"] += 1
            return QualityLevel.BALANCED, "Simple query - balanced quality sufficient"

        return quality, "Quality level appropriate for complexity"

    def get_quality_recommendation(
        self,
        query_type: str,
        user_emotion: Optional[str] = None,
        technical_level: Optional[str] = None,
    ) -> QualityLevel:
        """
        Recommend a quality level based on context.

        Args:
            query_type: Type of query (troubleshooting, information, etc.)
            user_emotion: Detected user emotional state
            technical_level: User's technical expertise level

        Returns:
            Recommended quality level
        """
        # Urgent/frustrated users might prefer faster responses
        if user_emotion in ["frustrated", "urgent", "anxious"]:
            return QualityLevel.FAST

        # Complex troubleshooting needs thorough analysis
        if query_type in [
            "complex_troubleshooting",
            "system_analysis",
            "performance_optimization",
        ]:
            return QualityLevel.THOROUGH

        # Technical users can handle more detailed responses
        if technical_level in ["advanced", "expert"]:
            return QualityLevel.THOROUGH

        # Default to balanced
        return QualityLevel.BALANCED

    def get_processing_profile(self, quality: QualityLevel) -> Dict[str, Any]:
        """
        Get a complete processing profile for a quality level.

        Args:
            quality: The quality level

        Returns:
            Processing profile with various parameters
        """
        profiles = {
            QualityLevel.FAST: {
                "timeout_multiplier": 0.5,
                "max_iterations": 2,
                "enable_deep_analysis": False,
                "enable_ml_patterns": False,
                "enable_correlation_analysis": False,
                "chunk_size": 1000,
                "parallel_processing": True,
                "cache_aggressive": True,
                "description": "Optimized for speed - basic analysis only",
            },
            QualityLevel.BALANCED: {
                "timeout_multiplier": 1.0,
                "max_iterations": 5,
                "enable_deep_analysis": True,
                "enable_ml_patterns": True,
                "enable_correlation_analysis": False,
                "chunk_size": 5000,
                "parallel_processing": True,
                "cache_aggressive": False,
                "description": "Balanced speed and quality",
            },
            QualityLevel.THOROUGH: {
                "timeout_multiplier": 1.5,
                "max_iterations": 10,
                "enable_deep_analysis": True,
                "enable_ml_patterns": True,
                "enable_correlation_analysis": True,
                "chunk_size": 10000,
                "parallel_processing": False,  # Sequential for thoroughness
                "cache_aggressive": False,
                "description": "Maximum quality - comprehensive analysis",
            },
        }

        return profiles[quality]

    def estimate_processing_time(
        self, operation: str, quality: QualityLevel, data_size: Optional[int] = None
    ) -> Dict[str, int]:
        """
        Estimate processing time for an operation.

        Args:
            operation: The operation type
            quality: The quality level
            data_size: Optional data size in bytes/lines

        Returns:
            Dictionary with min, expected, and max times in seconds
        """
        base_timeout = self.get_timeout(operation, quality)

        # Adjust for data size if provided
        size_factor = 1.0
        if data_size:
            if data_size > 10000:
                size_factor = 1.5
            elif data_size > 50000:
                size_factor = 2.0

        expected = int(base_timeout * size_factor * 0.7)  # Usually 70% of timeout

        return {
            "min": int(expected * 0.5),
            "expected": expected,
            "max": int(base_timeout * size_factor),
        }

    def get_metrics(self) -> Dict[str, Any]:
        """
        Get quality manager metrics.

        Returns:
            Dictionary of metrics
        """
        total_requests = sum(
            [
                self.metrics["fast_requests"],
                self.metrics["balanced_requests"],
                self.metrics["thorough_requests"],
            ]
        )

        if total_requests > 0:
            quality_distribution = {
                "fast": (self.metrics["fast_requests"] / total_requests) * 100,
                "balanced": (self.metrics["balanced_requests"] / total_requests) * 100,
                "thorough": (self.metrics["thorough_requests"] / total_requests) * 100,
            }
        else:
            quality_distribution = {"fast": 0, "balanced": 0, "thorough": 0}

        return {
            "total_requests": total_requests,
            "quality_distribution": quality_distribution,
            "quality_adjustments": self.metrics["quality_adjustments"],
            "timeouts_exceeded": self.metrics["timeouts_exceeded"],
        }


# Global singleton instance
_quality_manager: Optional[AdaptiveQualityManager] = None


def get_quality_manager() -> AdaptiveQualityManager:
    """Get or create the global quality manager instance."""
    global _quality_manager
    if _quality_manager is None:
        _quality_manager = AdaptiveQualityManager()
    return _quality_manager
