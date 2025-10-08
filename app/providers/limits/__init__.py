"""Provider rate limit wrappers/config.

Stable import path for rate-limit utilities bound to providers.
"""

from .wrappers import wrap_gemini_agent  # noqa: F401

__all__ = [
    "wrap_gemini_agent",
]
