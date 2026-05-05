from typing import Any

from pydantic import BaseModel


class ToolCall(BaseModel):
    name: str
    input: dict
    output: Any = None


class AgentResponse(BaseModel):
    answer: str
    tool_calls: list[ToolCall] = []
    error: str | None = None
