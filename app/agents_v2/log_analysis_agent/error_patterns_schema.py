"""Schema and loader for YAML-defined error patterns used by the Log Analysis Agent."""
from __future__ import annotations

import re
from pathlib import Path
from typing import List, Dict, Literal
from enum import Enum

import yaml
from pydantic import BaseModel, Field, field_validator


class ErrorPattern(BaseModel):
    """Represents a single error pattern entry from YAML."""

    pattern_id: str = Field(..., description="Unique identifier for the error pattern")
    regex: str = Field(..., description="Regex pattern to detect this error")
    severity_level_hint: Literal["High", "Medium", "Low"] = Field(
        ...,
        description="Suggested severity level (High, Medium, Low)",
    )
    component: str = Field(..., description="System component related to the error")
    description: str | None = Field(
        None, description="Human-friendly description of the error pattern"
    )

    @field_validator("pattern_id")
    def pattern_id_alphanumeric(cls, v: str):
        if not re.match(r"^[A-Za-z0-9_\-]+$", v):
            raise ValueError("pattern_id must be alphanumeric/underscore/hyphen")
        return v

    @field_validator("regex")
    def validate_regex(cls, v: str):
        try:
            re.compile(v, re.IGNORECASE)
        except re.error as exc:
            raise ValueError(f"Invalid regex '{v}': {exc}")
        return v

    @property
    def compiled_regex(self):
        return re.compile(self.regex, re.IGNORECASE)


class ErrorPatternConfig(BaseModel):
    """Root model holding a list of error patterns."""

    patterns: List[ErrorPattern]

    @classmethod
    def load_from_yaml(cls, path: str | Path) -> "ErrorPatternConfig":
        path = Path(path)
        if not path.exists():
            raise FileNotFoundError(f"Error pattern YAML not found: {path}")
        with path.open("r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
        # YAML can be list-only; wrap if needed
        if isinstance(data, list):
            data = {"patterns": data}
        return cls(**data)

    def build_regex_map(self) -> Dict[str, re.Pattern[str]]:
        """Return mapping pattern_id -> compiled regex."""
        return {p.pattern_id: p.compiled_regex for p in self.patterns}
