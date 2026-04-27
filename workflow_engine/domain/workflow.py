from typing import Any, Literal
from pydantic import BaseModel, Field


class RetryConfig(BaseModel):
    max_attempts: int = Field(ge=1, description="재시도 포함 총 시도 횟수")


class WorkflowNode(BaseModel):
    key: str
    type: Literal["tool", "llm", "human_approval"]
    depends_on: list[str] = Field(default_factory=list)
    inputs: dict[str, Any] = Field(default_factory=dict)
    tool: str | None = None
    task: str | None = None
    timeout_seconds: int | None = None
    retry: RetryConfig | None = None


class WorkflowDefinition(BaseModel):
    workflow_key: str
    version: str
    nodes: list[WorkflowNode]
