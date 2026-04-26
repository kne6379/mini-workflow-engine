from datetime import datetime, timedelta, timezone
from uuid import uuid4

from workflow_engine.domain.run import (
    ApprovalState,
    NodeState,
    NodeStatus,
    RunStatus,
    WorkflowErrorData,
    WorkflowRun,
)
from workflow_engine.domain.workflow import WorkflowDefinition, WorkflowNode
from workflow_engine.engine.input_mapping import render_inputs
from workflow_engine.engine.workflow_validator import topological_sort, validate_workflow
from workflow_engine.domain.errors import WorkflowEngineError
from workflow_engine.engine.ports import RunStore
from workflow_engine.engine.registries import AITaskRegistry, ToolRegistry


class WorkflowExecutor:
    def __init__(self, store: RunStore, tool_registry: ToolRegistry, ai_registry: AITaskRegistry):
        self.store = store
        self.tool_registry = tool_registry
        self.ai_registry = ai_registry

    async def start(self, workflow: WorkflowDefinition, input_data: dict) -> WorkflowRun:
        validate_workflow(workflow)
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
        self,
        workflow: WorkflowDefinition,
        run_id: str,
        decision: str,
        reason: str | None = None,
    ) -> WorkflowRun:
        run = self.store.get(run_id)
        if run.status != RunStatus.WAITING_APPROVAL or run.approval is None:
            raise WorkflowEngineError("승인 대기 상태가 아닙니다.")

        now = datetime.now(timezone.utc)
        if now > run.approval.deadline_at:
            run.status = RunStatus.TIMED_OUT
            run.updated_at = now
            return self.store.save(run)

        run.approval.decision = decision
        run.approval.reason = reason
        run.approval.decided_at = now

        if decision == "reject":
            run.status = RunStatus.REJECTED
            run.updated_at = now
            return self.store.save(run)

        if decision != "approve":
            return self._fail_run(run, run.current_node_key or "", WorkflowEngineError(f"Unknown approval decision: {decision}"))

        approval_node = run.approval.node_key
        run.node_states[approval_node].status = NodeStatus.COMPLETED
        run.context["nodes"][approval_node] = {"decision": "approve", "decided_at": now.isoformat()}
        run.status = RunStatus.RUNNING
        run.updated_at = now
        self.store.save(run)
        return await self._execute_from_order(workflow, run, topological_sort(workflow), start_after=approval_node)

    async def _execute_from_order(
        self,
        workflow: WorkflowDefinition,
        run: WorkflowRun,
        order: list[str],
        start_after: str | None = None,
    ) -> WorkflowRun:
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
                run.status = RunStatus.WAITING_APPROVAL
                run.node_states[node.key].status = NodeStatus.WAITING
                run.approval = ApprovalState(
                    node_key=node.key,
                    subject=subject,
                    body=body,
                    deadline_at=datetime.now(timezone.utc) + timedelta(seconds=node.timeout_seconds or 0),
                )
                run.updated_at = datetime.now(timezone.utc)
                return self.store.save(run)

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
        if node.type == "tool":
            return await self.tool_registry.get(node.tool or "").execute(input_data)
        if node.type == "llm":
            return await self.ai_registry.run(node.task or "", input_data)
        if node.type == "human_approval":
            return input_data
        raise WorkflowEngineError(f"Unsupported node type: {node.type}")

    def _fail_run(self, run: WorkflowRun, node_key: str, exc: Exception) -> WorkflowRun:
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
