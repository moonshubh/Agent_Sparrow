"""
FeedMe v2.0 Repository Layer
High-performance repository implementations for Phase 2 optimization
"""

from typing import TYPE_CHECKING

# Lazy import to improve startup performance
if TYPE_CHECKING:
    from .optimized_repository import OptimizedFeedMeRepository

def get_optimized_repository():
    """
    Lazy loader for OptimizedFeedMeRepository to improve startup performance.
    Returns the repository class only when needed.
    """
    from .optimized_repository import OptimizedFeedMeRepository
    return OptimizedFeedMeRepository

__all__ = ['get_optimized_repository']