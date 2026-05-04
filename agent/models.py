from pydantic import BaseModel


class AgentResponse(BaseModel):
    answer: str
    data: list[dict] | None = None
    tool_calls: list[str] = []
    iterations: int
