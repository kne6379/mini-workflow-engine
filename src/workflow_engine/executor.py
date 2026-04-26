from datetime import datetime, timedelta, timezone
from uuid import uuid4

from workflow_engine.domain import (
    ApprovalState,
    NodeState,
    NodeStatus,
    RunStatus,
    WorkflowDefinition,
    WorkflowErrorData,
    WorkflowNode,
    WorkflowRun,
)
from workflow_engine.errors import InputMappingError, WorkflowEngineError
from workflow_engine.input_mapping import render_inputs
from workflow_engine.store import InMemoryRunStore
from workflow_engine.tools import ToolRegistry
from workflow_engine.workflow_validator import topological_sort, validate_workflow


class WorkflowExecutor:
    def __init__(self, store: InMemoryRunStore, tool_registry: ToolRegistry, llm_registry):
        self.store = store
        self.tool_registry = tool_registry
        self.llm_registry = llm_registry

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
            return await self.llm_registry.run(node.task or "", input_data)
        if node.type == "human_approval":
            return input_data
        raise WorkflowEngineError(f"Unsupported node type: {node.type}")

    def _fail_run(self, run: WorkflowRun, node_key: str, exc: Exception) -> WorkflowRun:
        message = str(exc)
        code = getattr(exc, "code", "NODE_EXECUTION_FAILED")
        error = WorkflowErrorData(code=code, message=message, node_key=node_key)
        run.status = RunStatus.FAILED
        run.error = error
        run.node_states[node_key].status = NodeStatus.FAILED
        run.node_states[node_key].error = error
        run.updated_at = datetime.now(timezone.utc)
        return self.store.save(run)
