"""Pydantic schema and rubric for reflection feedback from Gemini Flash.

The `ReflectionFeedback` model captures the evaluation of an agent
response. It is designed to be used with Gemini 2.5 Flash in JSON mode or
function-calling style.
"""

from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field, confloat


class Sufficiency(str, Enum):
    """Enumeration for sufficiency of the answer."""

    sufficient = "sufficient"
    insufficient = "insufficient"


class ReflectionFeedback(BaseModel):
    """Model returned by the reflection LLM."""

    confidence_score: confloat(ge=0.0, le=1.0) = Field(  # type: ignore[arg-type]
        description="A value from 0.0-1.0 indicating confidence in the answer."
    )
    is_sufficient: bool = Field(
        description=(
            "Whether the answer adequately addresses the user query with correct,"
            " relevant and complete information."
        )
    )
    correction_suggestions: Optional[str] = Field(
        default=None,
        description="If insufficient, guidelines to improve the answer.",
    )
    reasoning: Optional[str] = Field(
        default=None,
        description="Short explanation behind the evaluation.",
    )

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "confidence_score": 0.82,
                    "is_sufficient": True,
                    "correction_suggestions": None,
                    "reasoning": (
                        "Answer covered setup steps clearly and cited KB article;"
                        " minor style issues only."
                    ),
                }
            ]
        }
    }


# Text rubric used inside prompt – keep here for single-source-of-truth.
RUBRIC_MD = """
You are a senior quality assurance specialist. Evaluate the **Assistant**
answer given the **User Query**. Score confidence 0-1 considering:

1. Factual accuracy – are statements correct per provided context?
2. Relevance – does the answer stay on topic and address the query?
3. Completeness – are key details / steps missing?
4. Tone & style – is response polite, concise, and user-friendly?

Output MUST be valid JSON matching this schema:
{ReflectionFeedback.schema_json(indent=2)}
""".strip()
