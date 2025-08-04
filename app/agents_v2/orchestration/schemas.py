from typing import List, Literal, Optional
from langchain_core.messages import BaseMessage
from typing_extensions import TypedDict

from app.agents_v2.log_analysis_agent.schemas import StructuredLogAnalysisOutput

# GraphState has been moved to app.agents_v2.orchestration.state