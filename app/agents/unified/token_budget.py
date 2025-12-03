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

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from loguru import logger


# Model context window sizes (in tokens)
# Kept in sync with context_middleware.py - Updated Nov 2025
MODEL_CONTEXT_WINDOWS = {
    # Google Gemini models (Nov 2025) - All have 1M input tokens
    "gemini-3-pro-preview": 1_048_576,        # Gemini 3 Pro - most intelligent
    "gemini-3-pro-image-preview": 65_536,     # Gemini 3 Pro Image
    "gemini-2.5-flash": 1_048_576,            # Stable workhorse
    "gemini-2.5-flash-lite": 1_048_576,       # Ultra fast, cost-efficient
    "gemini-2.5-pro": 1_048_576,              # Advanced thinking model
    "gemini-2.5-flash-preview-09-2025": 1_048_576,
    "gemini-2.5-flash-lite-preview-09-2025": 1_048_576,
    "gemini-2.0-flash": 1_048_576,            # Second gen workhorse
    "gemini-2.0-flash-lite": 1_048_576,       # Second gen fast
    "gemini-embedding-001": 3_584,
    "models/gemini-embedding-001": 3_584,

    # XAI Grok models (Nov 2025) - Major updates!
    "grok-4": 256_000,                        # 256K context
    "grok-4-fast": 2_000_000,                 # 2M context! (Sept 2025 release)
    "grok-4-1-fast-reasoning": 2_000_000,     # 2M context with reasoning
    "grok-3": 131_072,                        # 128K context
    "grok-3-mini": 131_072,                   # 128K context
    "grok-3-fast": 131_072,

    # OpenRouter model aliases
    "x-ai/grok-4.1-fast:free": 2_000_000,
    "x-ai/grok-4": 256_000,
    "x-ai/grok-4-fast": 2_000_000,
    "google/gemini-2.5-flash": 1_048_576,
    "google/gemini-2.5-pro": 1_048_576,
    "google/gemini-3-pro-preview": 1_048_576,

    # OpenAI models (Nov 2025) - GPT-4.1 series has 1M context!
    # GPT-5 series (released Dec 2025) - 400K input window per OpenAI docs
    "gpt-5.1": 400_000,                       # Latest flagship (400K)
    "gpt-5": 400_000,                         # Previous flagship (400K)
    "gpt-5-mini": 400_000,                    # Lightweight GPT-5 (400K)
    "gpt-5-nano": 400_000,                    # Ultra-lightweight GPT-5 (400K)
    "gpt-5-pro": 400_000,                     # Pro tier GPT-5 (400K)
    "gpt-4.1": 1_000_000,                     # 1M context
    "gpt-4.1-mini": 1_000_000,                # 1M context
    "gpt-4.1-nano": 1_000_000,                # 1M context
    "gpt-4o": 128_000,                        # 128K context
    "gpt-4o-mini": 128_000,
    "gpt-4-turbo": 128_000,
    "gpt-4": 8_192,
    "gpt-3.5-turbo": 16_385,

    # Anthropic Claude models (Nov 2025) - Claude 4 has 1M context!
    "claude-sonnet-4": 1_000_000,             # 1M context (Aug 2025)
    "claude-4-sonnet": 1_000_000,             # Alias
    "claude-sonnet-4.5": 1_000_000,           # Most advanced
    "claude-4.5-sonnet": 1_000_000,           # Alias
    "claude-3-opus": 200_000,
    "claude-3-sonnet": 200_000,
    "claude-3-haiku": 200_000,
    "claude-3.5-sonnet": 200_000,
}

# Provider-specific default context windows (Nov 2025)
PROVIDER_DEFAULT_CONTEXT = {
    "google": 1_048_576,   # Gemini 2.5/3 all have 1M
    "xai": 256_000,        # Grok 4 default (256K)
    "openai": 1_000_000,   # GPT-4.1+ all have 1M
    "anthropic": 1_000_000,  # Claude 4 has 1M
}

DEFAULT_CONTEXT_WINDOW = 128_000  # Conservative default


def get_model_context_window(model: str, provider: Optional[str] = None) -> int:
    """Get the context window size for a model.

    Supports multiple lookup strategies:
    1. Exact model name match
    2. Partial model name match (for versioned models)
    3. Provider default fallback
    4. Global default fallback

    Args:
        model: Model identifier (e.g., "gemini-2.5-flash", "grok-4-1-fast-reasoning")
        provider: Optional provider hint (e.g., "google", "xai")

    Returns:
        Context window size in tokens.
    """
    if not model:
        # Use provider default if available
        if provider and provider.lower() in PROVIDER_DEFAULT_CONTEXT:
            return PROVIDER_DEFAULT_CONTEXT[provider.lower()]
        return DEFAULT_CONTEXT_WINDOW

    model_lower = model.lower()

    # 1. Exact match
    if model in MODEL_CONTEXT_WINDOWS:
        return MODEL_CONTEXT_WINDOWS[model]

    # 2. Case-insensitive exact match
    for known_model, context in MODEL_CONTEXT_WINDOWS.items():
        if known_model.lower() == model_lower:
            return context

    # 3. Partial match (for versioned models like "gemini-2.5-flash-001")
    for known_model, context in MODEL_CONTEXT_WINDOWS.items():
        if model_lower.startswith(known_model.lower()):
            return context
        if known_model.lower().startswith(model_lower):
            return context

    # 4. Provider-based inference from model name
    if "gemini" in model_lower:
        return PROVIDER_DEFAULT_CONTEXT.get("google", DEFAULT_CONTEXT_WINDOW)
    if "grok" in model_lower:
        return PROVIDER_DEFAULT_CONTEXT.get("xai", DEFAULT_CONTEXT_WINDOW)
    if "gpt" in model_lower:
        return PROVIDER_DEFAULT_CONTEXT.get("openai", DEFAULT_CONTEXT_WINDOW)
    if "claude" in model_lower:
        return PROVIDER_DEFAULT_CONTEXT.get("anthropic", DEFAULT_CONTEXT_WINDOW)

    # 5. Use provider default if available
    if provider and provider.lower() in PROVIDER_DEFAULT_CONTEXT:
        return PROVIDER_DEFAULT_CONTEXT[provider.lower()]

    return DEFAULT_CONTEXT_WINDOW


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
    system_prompt: float = 0.15    # 15% for system prompt
    memory_context: float = 0.10   # 10% for retrieved memories
    message_history: float = 0.50  # 50% for conversation
    tool_results: float = 0.15     # 15% for tool outputs
    generation: float = 0.10       # 10% reserved for output

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
    def for_model(cls, model_name: str, provider: Optional[str] = None) -> "TokenBudget":
        """Create a TokenBudget for a specific model.

        Args:
            model_name: Model identifier (e.g., "gemini-2.5-flash", "grok-4").
            provider: Optional provider hint (e.g., "google", "xai") for unknown models.

        Returns:
            TokenBudget configured for that model's context window.
        """
        context_window = get_model_context_window(model_name, provider)
        return cls(total=context_window, model_name=model_name)


# Pre-configured budgets for common models across all providers (Nov 2025)
BUDGETS = {
    # Google Gemini models (all 1M context)
    "gemini-3-pro-preview": TokenBudget(total=1_048_576, model_name="gemini-3-pro-preview"),
    "gemini-2.5-flash": TokenBudget(total=1_048_576, model_name="gemini-2.5-flash"),
    "gemini-2.5-flash-lite": TokenBudget(total=1_048_576, model_name="gemini-2.5-flash-lite"),
    "gemini-2.5-pro": TokenBudget(total=1_048_576, model_name="gemini-2.5-pro"),
    "gemini-2.0-flash": TokenBudget(total=1_048_576, model_name="gemini-2.0-flash"),
    "gemini-2.0-flash-lite": TokenBudget(total=1_048_576, model_name="gemini-2.0-flash-lite"),
    # XAI Grok models (Nov 2025 - major context updates!)
    "grok-4-1-fast-reasoning": TokenBudget(total=2_000_000, model_name="grok-4-1-fast-reasoning"),
    "grok-4-fast": TokenBudget(total=2_000_000, model_name="grok-4-fast"),
    "grok-4": TokenBudget(total=256_000, model_name="grok-4"),
    "grok-3": TokenBudget(total=131_072, model_name="grok-3"),
    "grok-3-fast": TokenBudget(total=131_072, model_name="grok-3-fast"),
    # OpenAI models (GPT-4.1+ has 1M, GPT-5 series has 400K per OpenAI docs)
    "gpt-5.1": TokenBudget(total=400_000, model_name="gpt-5.1"),
    "gpt-5": TokenBudget(total=400_000, model_name="gpt-5"),
    "gpt-5-mini": TokenBudget(total=400_000, model_name="gpt-5-mini"),
    "gpt-4.1": TokenBudget(total=1_000_000, model_name="gpt-4.1"),
    "gpt-4.1-mini": TokenBudget(total=1_000_000, model_name="gpt-4.1-mini"),
    "gpt-4o": TokenBudget(total=128_000, model_name="gpt-4o"),
    "gpt-4o-mini": TokenBudget(total=128_000, model_name="gpt-4o-mini"),
    "gpt-4-turbo": TokenBudget(total=128_000, model_name="gpt-4-turbo"),
    "gpt-4": TokenBudget(total=8_192, model_name="gpt-4"),
    # Anthropic Claude models (Nov 2025 - Claude 4 has 1M!)
    "claude-sonnet-4": TokenBudget(total=1_000_000, model_name="claude-sonnet-4"),
    "claude-sonnet-4.5": TokenBudget(total=1_000_000, model_name="claude-sonnet-4.5"),
    "claude-3-opus": TokenBudget(total=200_000, model_name="claude-3-opus"),
    "claude-3-sonnet": TokenBudget(total=200_000, model_name="claude-3-sonnet"),
    "claude-3.5-sonnet": TokenBudget(total=200_000, model_name="claude-3.5-sonnet"),
    "claude-3-haiku": TokenBudget(total=200_000, model_name="claude-3-haiku"),
}


def get_budget_for_model(model_name: str, provider: Optional[str] = None) -> TokenBudget:
    """Get pre-configured budget for a model, or create one.

    Supports multi-provider model lookup:
    1. Check pre-configured BUDGETS dict
    2. Use provider-aware context window lookup for unknown models

    Args:
        model_name: Model identifier.
        provider: Optional provider hint (e.g., "google", "xai", "openai", "anthropic").

    Returns:
        TokenBudget for that model.
    """
    if model_name in BUDGETS:
        return BUDGETS[model_name]
    return TokenBudget.for_model(model_name, provider)


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
    def for_model(cls, model_name: str, provider: Optional[str] = None) -> "TokenBudgetTracker":
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
    "MODEL_CONTEXT_WINDOWS",
    "PROVIDER_DEFAULT_CONTEXT",
]
