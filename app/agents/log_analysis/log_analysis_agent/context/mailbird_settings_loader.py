"""
Mailbird Settings Loader (Windows)

Safely load MailbirdSettings.yml content to a Python dict for downstream metadata
extraction. This loader enforces size limits and uses yaml.safe_load.
"""

from __future__ import annotations

import os
from typing import Any, Dict, Optional

try:
    import yaml
except Exception:  # pragma: no cover
    yaml = None  # type: ignore


MAX_SETTINGS_BYTES = 1 * 1024 * 1024  # 1 MB safety limit


def load_mailbird_settings(path: Optional[str] = None, content: Optional[str] = None) -> Dict[str, Any]:
    """Load Mailbird settings YAML either from a file path or direct content.

    Raises when yaml is unavailable or content exceeds size limits.

    Note:
        Both the size check and file read use ``errors="ignore"`` so undecodable
        bytes are skipped rather than raising ``UnicodeDecodeError``. This keeps
        ingestion resilient but may omit corrupt characters from the resulting
        configuration.
    """
    if yaml is None:
        raise RuntimeError("PyYAML not available. Install pyyaml to load settings.")

    if content is not None:
        # ``errors="ignore"`` ensures invalid bytes do not abort ingestion but may drop data.
        if len(content.encode("utf-8", errors="ignore")) > MAX_SETTINGS_BYTES:
            raise ValueError("Settings content too large")
        return _safe_yaml_load(content)

    if path:
        st = os.stat(path)
        if st.st_size > MAX_SETTINGS_BYTES:
            raise ValueError("Settings file too large")
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            data = f.read()
        return _safe_yaml_load(data)

    return {}


def _safe_yaml_load(data: str) -> Dict[str, Any]:
    obj = yaml.safe_load(data) if data else None
    if obj is None:
        return {}
    if not isinstance(obj, dict):
        # Normalize to dict when YAML root is a list or primitive
        return {"settings": obj}
    return obj
