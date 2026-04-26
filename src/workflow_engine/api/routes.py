from fastapi import FastAPI, HTTPException

from workflow_engine.adapters.run_store import RunNotFoundError
from workflow_engine.api.schemas import ApprovalDecisionRequest, StartWorkflowRunRequest
from workflow_engine.bootstrap import AppDependencies
from workflow_engine.domain.errors import WorkflowEngineError
from workflow_engine.domain.run import WorkflowRun
from workflow_engine.engine.loader import load_workflow


def register_routes(app: FastAPI, deps: AppDependencies) -> None:
    @app.post(
        "/workflow-runs",
        response_model=WorkflowRun,
        summary="워크플로우 실행 시작",
        description="문의 ID를 입력받아 워크플로우를 승인 대기 단계까지 실행합니다.",
        tags=["워크플로우 실행"],
    )
    async def start_workflow_run(request: StartWorkflowRunRequest):
        workflow_path = deps.workflow_paths.get(request.workflow_key)
        if workflow_path is None:
            raise HTTPException(status_code=404, detail="지원하지 않는 워크플로우입니다.")
        workflow = load_workflow(workflow_path)
        return await deps.executor.start(workflow, {"inquiry_id": request.inquiry_id})

    @app.get(
        "/workflow-runs/{run_id}",
        response_model=WorkflowRun,
        summary="워크플로우 실행 상태 조회",
        description="실행 ID로 현재 상태, 컨텍스트, 노드 상태, 승인 정보를 조회합니다. 승인 대기 중이면 deadline 경과 시 자동으로 TIMED_OUT 상태로 갱신됩니다.",
        tags=["워크플로우 실행"],
    )
    async def get_workflow_run(run_id: str):
        try:
            return await deps.executor.expire_if_overdue(run_id)
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
        workflow = load_workflow(deps.workflow_paths["customer_support_auto_reply"])
        try:
            return await deps.executor.submit_approval(
                workflow, run_id, request.decision, request.reason,
            )
        except RunNotFoundError as exc:
            raise HTTPException(status_code=404, detail="워크플로우 실행을 찾을 수 없습니다.") from exc
        except WorkflowEngineError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
