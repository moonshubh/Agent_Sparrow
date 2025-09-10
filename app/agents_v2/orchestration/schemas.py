from typing import List, Literal, Optional
from langchain_core.messages import BaseMessage
from typing_extensions import TypedDict

from app.agents_v2.log_analysis_agent.simplified_schemas import SimplifiedLogAnalysisOutput as StructuredLogAnalysisOutput

# GraphState has been moved to app.agents_v2.orchestration.state