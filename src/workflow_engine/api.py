from pathlib import Path
from typing import Literal

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from workflow_engine.adapters.fake_ai import FakeAI
from workflow_engine.adapters.openai import OpenAIAdapter
from workflow_engine.adapters.mock_api import FakeMockAPIAdapter, MockAPIAdapter
from workflow_engine.adapters.run_store import RunNotFoundError, RunStoreAdapter
from workflow_engine.config import Settings
from workflow_engine.domain.run import WorkflowRun
from workflow_engine.engine.executor import WorkflowExecutor
from workflow_engine.engine.retry import RetryExecutor, RetryPolicy
from workflow_engine.engine.loader import load_workflow
from workflow_engine.domain.errors import WorkflowEngineError
from workflow_engine.engine.registries import AITaskRegistry, ToolRegistry
from workflow_engine.nodes.llm import classify_email, generate_reply
from workflow_engine.nodes.tools import CRMLookupTool, EmailSendTool, InquiryGetTool


class StartWorkflowRunRequest(BaseModel):
    workflow_key: str = Field(..., description="실행할 워크플로우 키")
    inquiry_id: str = Field(..., description="Mock Inquiry API에서 조회할 문의 ID")


class ApprovalDecisionRequest(BaseModel):
    decision: Literal["approve", "reject"] = Field(..., description="승인 결정값. approve 또는 reject")
    reason: str | None = Field(default=None, description="거부 사유")


def create_app(use_fake_dependencies: bool = False) -> FastAPI:
    app = FastAPI(
        title="AI 워크플로우 실행 엔진",
        description="고객 문의 자동 응답 워크플로우를 실행하고 승인 대기 상태를 관리하는 API입니다.",
        version="0.1.0",
    )
    settings = Settings()
    store = RunStoreAdapter()
    retry_executor = RetryExecutor(RetryPolicy())
    workflow_paths = {
        "customer_support_auto_reply": Path("workflows/customer_support_auto_reply.yaml")
    }

    if use_fake_dependencies:
        mock_server = FakeMockAPIAdapter()
    else:
        mock_server = MockAPIAdapter(settings.mock_api_base_url, settings.mock_api_key)

    if settings.llm_provider == "openai" and settings.openai_api_key:
        classify_ai = OpenAIAdapter(settings.openai_api_key, settings.openai_model)
        generate_ai = OpenAIAdapter(settings.openai_api_key, settings.openai_model)
    else:
        classify_ai = FakeAI({"category": "billing"})
        generate_ai = FakeAI({
            "subject": "Re: 카드 결제가 계속 실패합니다",
            "body": "예상 처리 기한 3영업일, 접수 확인 번호 ACK-001 안내드립니다.",
        })

    ai_registry = AITaskRegistry(
        tasks={"classify_email": classify_email, "generate_reply": generate_reply},
        profiles={"classify_email": classify_ai, "generate_reply": generate_ai},
    )

    executor = WorkflowExecutor(
        store=store,
        tool_registry=ToolRegistry({
            "inquiry_get": InquiryGetTool(mock_server, retry_executor),
            "crm_lookup": CRMLookupTool(mock_server, retry_executor),
            "email_send": EmailSendTool(mock_server, retry_executor),
        }),
        ai_registry=ai_registry,
    )

    @app.post(
        "/workflow-runs",
        response_model=WorkflowRun,
        summary="워크플로우 실행 시작",
        description="문의 ID를 입력받아 워크플로우를 승인 대기 단계까지 실행합니다.",
        tags=["워크플로우 실행"],
    )
    async def start_workflow_run(request: StartWorkflowRunRequest):
        workflow_path = workflow_paths.get(request.workflow_key)
        if workflow_path is None:
            raise HTTPException(status_code=404, detail="지원하지 않는 워크플로우입니다.")
        workflow = load_workflow(workflow_path)
        return await executor.start(workflow, {"inquiry_id": request.inquiry_id})

    @app.get(
        "/workflow-runs/{run_id}",
        response_model=WorkflowRun,
        summary="워크플로우 실행 상태 조회",
        description="실행 ID로 현재 상태, 컨텍스트, 노드 상태, 승인 정보를 조회합니다.",
        tags=["워크플로우 실행"],
    )
    async def get_workflow_run(run_id: str):
        try:
            return store.get(run_id)
        except RunNotFoundError as exc:
            raise HTTPException(status_code=404, detail="워크플로우 실행을 찾을 수 없습니다.") from exc

    @app.post(
        "/workflow-runs/{run_id}/approval",
        response_model=WorkflowRun,
        summary="승인 또는 거부 제출",
        description="승인 대기 중인 워크플로우에 approve 또는 reject 결정을 제출합니다.",
        tags=["승인"],
    )
    async def submit_approval(run_id: str, request: ApprovalDecisionRequest):
        workflow = load_workflow(workflow_paths["customer_support_auto_reply"])
        try:
            return await executor.submit_approval(workflow, run_id, request.decision, request.reason)
        except RunNotFoundError as exc:
            raise HTTPException(status_code=404, detail="워크플로우 실행을 찾을 수 없습니다.") from exc
        except WorkflowEngineError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    return app


app = create_app()
