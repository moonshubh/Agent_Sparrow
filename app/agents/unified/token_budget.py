"""Token budget allocation for context management.

This module provides proactive token budget management across context components:
- System prompt
- Memory context
- Message history
- Tool results
- Generation output

By allocating token budgets, we can prevent context overflow before it happens.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional

from loguru import logger

# Shared model context metadata
from app.agents.unified.model_context import get_model_context_window
from app.core.config import get_models_config, iter_model_configs


@dataclass
class TokenBudget:
    """Allocate token budget across context components.

    This dataclass defines how tokens should be distributed across different
    parts of the context window. The allocations are percentages that should
    sum to 1.0 (100%).

    Default allocations:
    - system_prompt: 15% - Static instructions, tool descriptions, skill index
    - memory_context: 10% - Retrieved memories from long-term storage
    - message_history: 50% - Conversation history (auto-compacts via summarization)
    - tool_results: 15% - Tool outputs (auto-evicts large results)
    - generation: 10% - Reserved for model output

    Usage:
        budget = TokenBudget.for_model("gemini-2.5-flash")
        print(f"System prompt budget: {budget.get_budget('system_prompt')} tokens")
        print(f"Remaining for history: {budget.remaining_for_history(used={'system_prompt': 5000})}")
    """

    total: int  # Model's total context window
    model_name: str = "unknown"

    # Allocation percentages (should sum to 1.0)
    system_prompt: float = 0.15  # 15% for system prompt
    memory_context: float = 0.10  # 10% for retrieved memories
    message_history: float = 0.50  # 50% for conversation
    tool_results: float = 0.15  # 15% for tool outputs
    generation: float = 0.10  # 10% reserved for output

    def __post_init__(self):
        """Validate allocations sum to 1.0."""
        total_pct = (
            self.system_prompt
            + self.memory_context
            + self.message_history
            + self.tool_results
            + self.generation
        )
        if abs(total_pct - 1.0) > 0.01:
            logger.warning(
                "token_budget_allocation_mismatch",
                total_pct=total_pct,
                expected=1.0,
            )

    def get_budget(self, component: str) -> int:
        """Get token budget for a specific component.

        Args:
            component: One of 'system_prompt', 'memory_context', 'message_history',
                      'tool_results', 'generation'.

        Returns:
            Token budget for that component.
        """
        pct = getattr(self, component, 0.0)
        return int(self.total * pct)

    def remaining_for_history(self, used: Dict[str, int]) -> int:
        """Calculate remaining tokens for message history.

        After accounting for fixed components (system prompt, memory, tool results,
        and reserved generation space), this returns how many tokens are available
        for conversation history.

        Args:
            used: Dict mapping component name to tokens used.
                  e.g., {"system_prompt": 5000, "memory_context": 2000}

        Returns:
            Remaining tokens for message history.
        """
        fixed_used = (
            used.get("system_prompt", 0)
            + used.get("memory_context", 0)
            + used.get("tool_results", 0)
        )
        reserved_generation = self.get_budget("generation")

        return self.total - fixed_used - reserved_generation

    def is_within_budget(self, used: Dict[str, int]) -> bool:
        """Check if current usage is within budget.

        Args:
            used: Dict mapping component name to tokens used.

        Returns:
            True if all components are within their allocated budgets.
        """
        for component, tokens in used.items():
            budget = self.get_budget(component)
            if budget > 0 and tokens > budget:
                return False
        return True

    def get_utilization(self, used: Dict[str, int]) -> Dict[str, float]:
        """Calculate utilization percentage for each component.

        Args:
            used: Dict mapping component name to tokens used.

        Returns:
            Dict mapping component name to utilization percentage (0.0-1.0+).
        """
        utilization = {}
        for component, tokens in used.items():
            budget = self.get_budget(component)
            if budget > 0:
                utilization[component] = tokens / budget
            else:
                utilization[component] = 0.0 if tokens == 0 else float("inf")
        return utilization

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dict for serialization/observability."""
        return {
            "total": self.total,
            "model_name": self.model_name,
            "allocations": {
                "system_prompt": self.get_budget("system_prompt"),
                "memory_context": self.get_budget("memory_context"),
                "message_history": self.get_budget("message_history"),
                "tool_results": self.get_budget("tool_results"),
                "generation": self.get_budget("generation"),
            },
            "percentages": {
                "system_prompt": self.system_prompt,
                "memory_context": self.memory_context,
                "message_history": self.message_history,
                "tool_results": self.tool_results,
                "generation": self.generation,
            },
        }

    @classmethod
    def for_model(
        cls, model_name: str, provider: Optional[str] = None
    ) -> "TokenBudget":
        """Create a TokenBudget for a specific model.

        Args:
            model_name: Model identifier (e.g., "gemini-2.5-flash", "grok-4").
            provider: Optional provider hint (e.g., "google", "xai") for unknown models.

        Returns:
            TokenBudget configured for that model's context window.
        """
        context_window = get_model_context_window(model_name, provider)
        return cls(total=context_window, model_name=model_name)


# Helper to build budgets using shared model context metadata
def _budget(model_name: str, provider: Optional[str] = None) -> TokenBudget:
    return TokenBudget.for_model(model_name, provider)


def _build_budget_index() -> dict[str, TokenBudget]:
    config = get_models_config()
    budgets: dict[str, TokenBudget] = {}
    for _, _, model_cfg in iter_model_configs(config):
        budgets[model_cfg.model_id] = _budget(model_cfg.model_id)
    return budgets


BUDGETS = _build_budget_index()


def get_budget_for_model(
    model_name: str, provider: Optional[str] = None
) -> TokenBudget:
    """Return a TokenBudget for the given model, falling back to defaults."""
    budget = BUDGETS.get(model_name)
    if budget is not None:
        return budget
    return _budget(model_name, provider)


class TokenBudgetTracker:
    """Track token usage against budget during a conversation.

    This class maintains running totals of token usage across components
    and provides warnings when approaching or exceeding budget limits.

    Usage:
        tracker = TokenBudgetTracker.for_model("gemini-2.5-flash")
        tracker.add_usage("system_prompt", 5000)
        tracker.add_usage("message_history", 50000)

        if tracker.should_compact_history():
            # Trigger summarization
            pass

        print(tracker.get_summary())
    """

    def __init__(self, budget: TokenBudget):
        """Initialize tracker with a budget.

        Args:
            budget: TokenBudget to track against.
        """
        self.budget = budget
        self._usage: Dict[str, int] = {
            "system_prompt": 0,
            "memory_context": 0,
            "message_history": 0,
            "tool_results": 0,
        }

    def add_usage(self, component: str, tokens: int) -> None:
        """Add token usage for a component.

        Args:
            component: Component name.
            tokens: Tokens to add.
        """
        if component in self._usage:
            self._usage[component] += tokens
        else:
            self._usage[component] = tokens

    def set_usage(self, component: str, tokens: int) -> None:
        """Set token usage for a component (replaces existing).

        Args:
            component: Component name.
            tokens: Total tokens for this component.
        """
        self._usage[component] = tokens

    def get_usage(self, component: str) -> int:
        """Get current token usage for a component.

        Args:
            component: Component name.

        Returns:
            Current token usage.
        """
        return self._usage.get(component, 0)

    def get_total_usage(self) -> int:
        """Get total token usage across all components.

        Returns:
            Total tokens used.
        """
        return sum(self._usage.values())

    def get_utilization_ratio(self) -> float:
        """Get overall context utilization ratio.

        Returns:
            Ratio of used tokens to total context window (0.0-1.0+).
            Returns 0.0 if budget total is zero.
        """
        if not self.budget.total:
            return 0.0
        return self.get_total_usage() / self.budget.total

    def should_compact_history(self, threshold: float = 0.7) -> bool:
        """Check if message history should be compacted.

        Args:
            threshold: Utilization threshold (0.0-1.0) to trigger compaction.

        Returns:
            True if history should be compacted.
        """
        history_budget = self.budget.get_budget("message_history")
        history_usage = self._usage.get("message_history", 0)

        if history_budget > 0:
            return (history_usage / history_budget) > threshold

        # Fallback to overall utilization
        return self.get_utilization_ratio() > threshold

    def should_evict_tool_results(self, threshold: float = 0.8) -> bool:
        """Check if tool results should be evicted.

        Args:
            threshold: Utilization threshold (0.0-1.0) to trigger eviction.

        Returns:
            True if tool results should be evicted.
        """
        tool_budget = self.budget.get_budget("tool_results")
        tool_usage = self._usage.get("tool_results", 0)

        if tool_budget > 0:
            return (tool_usage / tool_budget) > threshold

        return False

    def get_remaining_for_history(self) -> int:
        """Get remaining tokens available for history.

        Returns:
            Available tokens for message history.
        """
        return self.budget.remaining_for_history(self._usage)

    def get_summary(self) -> Dict[str, Any]:
        """Get summary of current usage and budget.

        Returns:
            Dict with usage, budget, and utilization info.
        """
        return {
            "budget": self.budget.to_dict(),
            "usage": dict(self._usage),
            "total_usage": self.get_total_usage(),
            "utilization_ratio": self.get_utilization_ratio(),
            "remaining_for_history": self.get_remaining_for_history(),
            "should_compact_history": self.should_compact_history(),
            "should_evict_tool_results": self.should_evict_tool_results(),
        }

    @classmethod
    def for_model(
        cls, model_name: str, provider: Optional[str] = None
    ) -> "TokenBudgetTracker":
        """Create a tracker for a specific model.

        Args:
            model_name: Model identifier (e.g., "gemini-2.5-flash", "grok-4").
            provider: Optional provider hint (e.g., "google", "xai", "openai", "anthropic").

        Returns:
            TokenBudgetTracker for that model.
        """
        budget = get_budget_for_model(model_name, provider)
        return cls(budget)


# Export classes
__all__ = [
    "TokenBudget",
    "TokenBudgetTracker",
    "BUDGETS",
    "get_budget_for_model",
    "get_model_context_window",
]
