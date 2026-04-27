import asyncio
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from pydantic import ValidationError

from src.adapters.run_store import RunNotFoundError
from src.domain.errors import (
    ToolInputValidationError,
    ToolOutputValidationError,
    WorkflowEngineError,
)
from src.domain.run import (
    ApprovalState, NodeState, NodeStatus, RunStatus,
    WorkflowErrorData, WorkflowRun,
)
from src.domain.workflow import WorkflowDefinition, WorkflowNode
from src.engine.approval_timer import ApprovalTimer
from src.engine.input_mapping import render_inputs
from src.engine.ports import RunStore
from src.engine.registries import AITaskRegistry, ToolRegistry
from src.engine.retry import RetryExecutor, RetryPolicy
from src.engine.validator import topological_sort, validate_workflow


class WorkflowExecutor:
    """워크플로우 노드를 DAG 순서로 순차 실행하고 승인 노드에서 일시정지/재개한다.

    in-memory 한계: ``_run_locks``와 store는 프로세스 메모리에 축적되며 별도
    정리 로직이 없다. 단일 worker, 단명 프로세스, 적은 동시 run 수를 가정한다.
    영속화 또는 멀티 worker가 필요하면 외부 저장소 + 별도 락 매니저로 교체해야 한다.
    """

    def __init__(
        self,
        store: RunStore,
        tool_registry: ToolRegistry,
        ai_registry: AITaskRegistry,
        approval_timer: ApprovalTimer | None = None,
        default_retry_policy: RetryPolicy | None = None,
    ):
        self.store = store
        self.tool_registry = tool_registry
        self.ai_registry = ai_registry
        self.approval_timer = approval_timer
        self.default_retry_policy = default_retry_policy or RetryPolicy()
        self._run_locks: dict[str, asyncio.Lock] = {}

    def _lock_for(self, run_id: str) -> asyncio.Lock:
        if run_id not in self._run_locks:
            self._run_locks[run_id] = asyncio.Lock()
        return self._run_locks[run_id]

    async def start(self, workflow: WorkflowDefinition, input_data: dict) -> WorkflowRun:
        validate_workflow(workflow)
        # 멱등성: 같은 inquiry로 활성 또는 COMPLETED run이 있으면 기존 반환
        inquiry_id = input_data.get("inquiry_id")
        if inquiry_id is not None:
            existing = self.store.find_by_inquiry(inquiry_id)
            if existing is not None and existing.status in {
                RunStatus.PENDING, RunStatus.RUNNING,
                RunStatus.WAITING_APPROVAL, RunStatus.COMPLETED,
            }:
                return existing
        now = datetime.now(timezone.utc)
        run = WorkflowRun(
            run_id=f"run_{uuid4().hex[:12]}",
            workflow_key=workflow.workflow_key,
            status=RunStatus.PENDING,
            current_node_key=None,
            context={"input": input_data, "nodes": {}},
            node_states={node.key: NodeState() for node in workflow.nodes},
            created_at=now,
            updated_at=now,
        )
        self.store.save(run)
        return await self._execute_from_order(workflow, run, topological_sort(workflow))

    async def submit_approval(
        self, workflow: WorkflowDefinition, run_id: str,
        decision: str, reason: str | None = None,
    ) -> WorkflowRun:
        async with self._lock_for(run_id):
            run = self.store.get(run_id)
            if run.status != RunStatus.WAITING_APPROVAL or run.approval is None:
                raise WorkflowEngineError("승인 대기 상태가 아닙니다.")
            now = datetime.now(timezone.utc)
            if now > run.approval.deadline_at:
                run.status = RunStatus.TIMED_OUT
                run.error = WorkflowErrorData(
                    code="APPROVAL_TIMEOUT", message="승인 대기 시간이 초과되었습니다.",
                    node_key=run.approval.node_key,
                )
                run.updated_at = now
                if self.approval_timer is not None:
                    self.approval_timer.cancel(run_id)
                return self.store.save(run)

            if self.approval_timer is not None:
                self.approval_timer.cancel(run_id)
            run.approval.decision = decision
            run.approval.reason = reason
            run.approval.decided_at = now

            if decision == "reject":
                run.status = RunStatus.REJECTED
                run.updated_at = now
                return self.store.save(run)

            if decision != "approve":
                return self._fail_run(
                    run, run.current_node_key or "",
                    WorkflowEngineError(f"Unknown approval decision: {decision}"),
                )

            approval_node = run.approval.node_key
            run.node_states[approval_node].status = NodeStatus.COMPLETED
            run.context["nodes"][approval_node] = {
                "decision": "approve", "decided_at": now.isoformat(),
            }
            run.status = RunStatus.RUNNING
            run.updated_at = now
            self.store.save(run)
        return await self._execute_from_order(
            workflow, run, topological_sort(workflow), start_after=approval_node,
        )

    async def expire_run(self, run_id: str) -> None:
        """ApprovalTimer 콜백. WAITING_APPROVAL이면 TIMED_OUT으로 전환."""
        async with self._lock_for(run_id):
            try:
                run = self.store.get(run_id)
            except RunNotFoundError:
                return
            if run.status != RunStatus.WAITING_APPROVAL:
                return
            now = datetime.now(timezone.utc)
            run.status = RunStatus.TIMED_OUT
            run.error = WorkflowErrorData(
                code="APPROVAL_TIMEOUT", message="승인 대기 시간이 초과되었습니다.",
                node_key=run.approval.node_key if run.approval else None,
            )
            run.updated_at = now
            self.store.save(run)

    async def expire_if_overdue(self, run_id: str) -> WorkflowRun:
        """GET 안전망. deadline 경과 발견 시 만료 처리 후 최신 run 반환."""
        async with self._lock_for(run_id):
            run = self.store.get(run_id)
            if run.status == RunStatus.WAITING_APPROVAL and run.approval is not None:
                now = datetime.now(timezone.utc)
                if now > run.approval.deadline_at:
                    run.status = RunStatus.TIMED_OUT
                    run.error = WorkflowErrorData(
                        code="APPROVAL_TIMEOUT",
                        message="승인 대기 시간이 초과되었습니다.",
                        node_key=run.approval.node_key,
                    )
                    run.updated_at = now
                    self.store.save(run)
            return run

    async def _execute_from_order(
        self, workflow, run, order, start_after=None,
    ):
        node_by_key = {node.key: node for node in workflow.nodes}
        run.status = RunStatus.RUNNING
        skip = start_after is not None
        for node_key in order:
            if skip:
                if node_key == start_after:
                    skip = False
                continue
            node = node_by_key[node_key]
            if run.node_states[node.key].status == NodeStatus.COMPLETED:
                continue
            run.current_node_key = node.key
            run.node_states[node.key].status = NodeStatus.RUNNING
            run.node_states[node.key].attempts += 1
            run.updated_at = datetime.now(timezone.utc)
            self.store.save(run)
            try:
                result = await self._run_node(node, run)
            except Exception as exc:
                return self._fail_run(run, node.key, exc)

            if node.type == "human_approval":
                subject = result["subject"]
                body = result["body"]
                deadline = datetime.now(timezone.utc) + timedelta(seconds=node.timeout_seconds or 0)
                run.status = RunStatus.WAITING_APPROVAL
                run.node_states[node.key].status = NodeStatus.WAITING
                run.approval = ApprovalState(
                    node_key=node.key, subject=subject, body=body, deadline_at=deadline,
                )
                run.updated_at = datetime.now(timezone.utc)
                self.store.save(run)
                if self.approval_timer is not None:
                    self.approval_timer.schedule(run.run_id, deadline)
                return run

            run.context["nodes"][node.key] = result
            run.node_states[node.key].status = NodeStatus.COMPLETED
            run.updated_at = datetime.now(timezone.utc)
            self.store.save(run)

        run.status = RunStatus.COMPLETED
        run.current_node_key = None
        run.updated_at = datetime.now(timezone.utc)
        return self.store.save(run)

    async def _run_node(self, node: WorkflowNode, run: WorkflowRun) -> dict:
        input_data = render_inputs(node.inputs, run.context)

        async def call() -> dict:
            if node.type == "tool":
                return await self._run_tool_node(node, input_data)
            if node.type == "llm":
                return await self._run_llm_node(node, input_data)
            if node.type == "human_approval":
                return self._run_human_approval_node(input_data)
            raise WorkflowEngineError(f"지원하지 않는 node type: {node.type}")

        if node.retry is None:
            return await call()
        policy = replace(self.default_retry_policy, max_attempts=node.retry.max_attempts)
        return await RetryExecutor(policy).run(call)

    async def _run_tool_node(self, node: WorkflowNode, input_data: dict) -> dict:
        tool = self.tool_registry.get(node.tool or "")
        try:
            validated_input = tool.input_model.model_validate(input_data)
        except ValidationError as exc:
            raise ToolInputValidationError("Tool 입력 스키마 검증에 실패했습니다.") from exc

        raw_output = await tool.execute(validated_input.model_dump(by_alias=True))

        try:
            return tool.output_model.model_validate(raw_output).model_dump(by_alias=True)
        except ValidationError as exc:
            raise ToolOutputValidationError("Tool 출력 스키마 검증에 실패했습니다.") from exc

    async def _run_llm_node(self, node: WorkflowNode, input_data: dict) -> dict:
        return await self.ai_registry.run(node.task or "", input_data)

    def _run_human_approval_node(self, input_data: dict) -> dict:
        return input_data

    def _fail_run(self, run, node_key, exc):
        message = str(exc)
        code = getattr(exc, "code", "NODE_EXECUTION_FAILED")
        error = WorkflowErrorData(code=code, message=message, node_key=node_key)
        run.status = RunStatus.FAILED
        run.error = error
        if node_key in run.node_states:
            run.node_states[node_key].status = NodeStatus.FAILED
            run.node_states[node_key].error = error
        run.updated_at = datetime.now(timezone.utc)
        return self.store.save(run)
