"""Unit tests for ErrorPattern YAML loader."""
from pathlib import Path

import pytest

from app.agents_v2.log_analysis_agent.error_patterns_schema import (
    ErrorPatternConfig,
)


def test_load_valid_yaml(tmp_path: Path):
    yaml_content = """
- pattern_id: TestError
  regex: "Error occurred"
  severity_level_hint: High
  component: Core
"""
    file = tmp_path / "patterns.yaml"
    file.write_text(yaml_content)

    config = ErrorPatternConfig.load_from_yaml(file)
    assert len(config.patterns) == 1
    assert config.patterns[0].pattern_id == "TestError"
    assert config.patterns[0].compiled_regex.search("some Error occurred text")


def test_invalid_regex(tmp_path: Path):
    yaml_content = """
- pattern_id: BadRegex
  regex: "(unclosed"
  severity_level_hint: Low
  component: Misc
"""
    file = tmp_path / "bad.yaml"
    file.write_text(yaml_content)

    with pytest.raises(ValueError):
        ErrorPatternConfig.load_from_yaml(file)
