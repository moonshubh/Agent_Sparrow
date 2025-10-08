from typing import List, Literal, Optional
from langchain_core.messages import BaseMessage
from typing_extensions import TypedDict

from app.agents.log_analysis.log_analysis_agent.simplified_schemas import SimplifiedLogAnalysisOutput as StructuredLogAnalysisOutput

# GraphState has been moved to app.agents.orchestration.orchestration.state