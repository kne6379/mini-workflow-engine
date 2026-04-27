from typing import Literal

from pydantic import BaseModel, Field


class StartWorkflowRunRequest(BaseModel):
    workflow_key: str = Field(..., description="실행할 워크플로우 키")
    inquiry_id: str = Field(..., description="Mock Inquiry API에서 조회할 문의 ID")


class ApprovalDecisionRequest(BaseModel):
    decision: Literal["approve", "reject"] = Field(..., description="승인 결정값. approve 또는 reject")
    reason: str | None = Field(default=None, description="거부 사유")
