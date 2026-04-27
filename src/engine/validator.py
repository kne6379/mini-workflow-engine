from collections import deque

from src.domain.workflow import WorkflowDefinition, WorkflowNode
from src.domain.errors import WorkflowValidationError


def validate_workflow(workflow: WorkflowDefinition) -> None:
    _validate_unique_node_keys(workflow)

    node_by_key = {node.key: node for node in workflow.nodes}
    for node in workflow.nodes:
        _validate_node_required_fields(node)
        for dependency in node.depends_on:
            if dependency not in node_by_key:
                raise WorkflowValidationError(
                    f"Node '{node.key}' depends on unknown node '{dependency}'"
                )

    topological_sort(workflow)


def topological_sort(workflow: WorkflowDefinition) -> list[str]:
    _validate_unique_node_keys(workflow)

    node_by_key = {node.key: node for node in workflow.nodes}
    incoming_counts = {node.key: len(node.depends_on) for node in workflow.nodes}
    outgoing: dict[str, list[str]] = {node.key: [] for node in workflow.nodes}

    for node in workflow.nodes:
        for dependency in node.depends_on:
            if dependency not in node_by_key:
                raise WorkflowValidationError(
                    f"Node '{node.key}' depends on unknown node '{dependency}'"
                )
            outgoing[dependency].append(node.key)

    ready = deque([node.key for node in workflow.nodes if incoming_counts[node.key] == 0])
    order: list[str] = []

    while ready:
        key = ready.popleft()
        order.append(key)
        for dependent in outgoing[key]:
            incoming_counts[dependent] -= 1
            if incoming_counts[dependent] == 0:
                ready.append(dependent)

    if len(order) != len(workflow.nodes):
        raise WorkflowValidationError("Workflow graph contains a cycle")

    return order


def _validate_unique_node_keys(workflow: WorkflowDefinition) -> None:
    keys = [node.key for node in workflow.nodes]
    duplicate_keys = {key for key in keys if keys.count(key) > 1}
    if duplicate_keys:
        raise WorkflowValidationError(f"Duplicate node key: {sorted(duplicate_keys)[0]}")


def _validate_node_required_fields(node: WorkflowNode) -> None:
    if node.type == "tool" and not node.tool:
        raise WorkflowValidationError(f"Node '{node.key}' with type 'tool' requires tool")
    if node.type == "llm" and not node.task:
        raise WorkflowValidationError(f"Node '{node.key}' with type 'llm' requires task")
    if node.type == "human_approval" and node.timeout_seconds is None:
        raise WorkflowValidationError(
            f"Node '{node.key}' with type 'human_approval' requires timeout_seconds"
        )
