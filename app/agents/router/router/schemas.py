from pydantic import BaseModel

class RouteQuery(BaseModel):
    """Route a user query to the most relevant agent."""

    destination: str

class RouteQueryWithConf(BaseModel):
    """Router output that includes a confidence score."""

    destination: str
    confidence: float