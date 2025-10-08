"""Compatibility layer for primary troubleshooting components.

Canonical import path: app.agents.primary.troubleshooting
Temporarily re-exports from app.agents.primary.primary_agent.troubleshooting.*
"""

try:
    from app.agents.primary.primary_agent.troubleshooting.troubleshooting_engine import (
        TroubleshootingEngine,  # noqa: F401
        TroubleshootingConfig,  # noqa: F401
    )
    from app.agents.primary.primary_agent.troubleshooting.troubleshooting_schemas import (
        TroubleshootingState,  # noqa: F401
        DiagnosticStep,  # noqa: F401
        TroubleshootingPhase,  # noqa: F401
    )
except Exception:  # pragma: no cover
    pass

__all__ = [
    "TroubleshootingEngine",
    "TroubleshootingConfig",
    "TroubleshootingState",
    "DiagnosticStep",
    "TroubleshootingPhase",
]
