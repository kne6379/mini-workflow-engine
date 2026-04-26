from datetime import datetime
from enum import StrEnum
from typing import Any, Literal
from pydantic import BaseModel, Field


class NodeType(StrEnum):
    TOOL = "tool"
    LLM = "llm"
    HUMAN_APPROVAL = "human_approval"


class RunStatus(StrEnum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    WAITING_APPROVAL = "WAITING_APPROVAL"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    REJECTED = "REJECTED"
    TIMED_OUT = "TIMED_OUT"


class NodeStatus(StrEnum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    WAITING = "WAITING"
    FAILED = "FAILED"
    SKIPPED = "SKIPPED"


class WorkflowErrorData(BaseModel):
    code: str
    message: str
    node_key: str | None = None
    retryable: bool = False
    details: dict[str, Any] = Field(default_factory=dict)


class NodeState(BaseModel):
    status: NodeStatus = NodeStatus.PENDING
    attempts: int = 0
    error: WorkflowErrorData | None = None


class ApprovalState(BaseModel):
    node_key: str
    subject: str
    body: str
    deadline_at: datetime
    decision: Literal["approve", "reject"] | None = None
    reason: str | None = None
    decided_at: datetime | None = None


class WorkflowRun(BaseModel):
    run_id: str
    workflow_key: str
    status: RunStatus
    current_node_key: str | None = None
    context: dict[str, Any]
    node_states: dict[str, NodeState]
    approval: ApprovalState | None = None
    error: WorkflowErrorData | None = None
    created_at: datetime
    updated_at: datetime
