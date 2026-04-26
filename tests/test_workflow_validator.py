from pathlib import Path

import pytest

from workflow_engine.domain import WorkflowDefinition
from workflow_engine.errors import WorkflowValidationError
from workflow_engine.workflow_validator import topological_sort, validate_workflow
from workflow_engine.workflow_loader import load_workflow


def _workflow(nodes):
    return WorkflowDefinition(workflow_key="wf", version="1.0.0", nodes=nodes)


def test_loads_customer_support_workflow_definition():
    workflow = load_workflow(Path("workflows/customer_support_auto_reply.yaml"))

    assert workflow.workflow_key == "customer_support_auto_reply"
    assert [node.key for node in workflow.nodes] == [
        "fetch_inquiry",
        "classify_inquiry",
        "lookup_customer",
        "generate_reply",
        "wait_for_approval",
        "send_reply_email",
    ]
    assert workflow.nodes[0].type == "tool"
    assert workflow.nodes[0].tool == "inquiry_get"


def test_validation_rejects_duplicate_node_keys():
    workflow = WorkflowDefinition.model_validate({
        "workflow_key": "wf",
        "version": "1.0.0",
        "nodes": [
            {"key": "same", "type": "tool", "tool": "inquiry_get"},
            {"key": "same", "type": "tool", "tool": "crm_lookup"},
        ],
    })

    with pytest.raises(WorkflowValidationError, match="Duplicate node key"):
        validate_workflow(workflow)


def test_validation_rejects_missing_dependency():
    workflow = WorkflowDefinition.model_validate({
        "workflow_key": "wf",
        "version": "1.0.0",
        "nodes": [
            {"key": "generate_reply", "type": "llm", "task": "generate_reply", "depends_on": ["missing"]},
        ],
    })

    with pytest.raises(WorkflowValidationError, match="unknown node"):
        validate_workflow(workflow)


def test_validation_rejects_cycle():
    workflow = WorkflowDefinition.model_validate({
        "workflow_key": "wf",
        "version": "1.0.0",
        "nodes": [
            {"key": "a", "type": "tool", "tool": "inquiry_get", "depends_on": ["b"]},
            {"key": "b", "type": "tool", "tool": "crm_lookup", "depends_on": ["a"]},
        ],
    })

    with pytest.raises(WorkflowValidationError, match="cycle"):
        validate_workflow(workflow)


def test_validation_rejects_missing_type_specific_fields():
    workflow = WorkflowDefinition.model_validate({
        "workflow_key": "wf",
        "version": "1.0.0",
        "nodes": [
            {"key": "lookup_customer", "type": "tool"},
            {"key": "classify_inquiry", "type": "llm"},
            {"key": "wait_for_approval", "type": "human_approval"},
        ],
    })

    with pytest.raises(WorkflowValidationError, match="requires"):
        validate_workflow(workflow)


def test_topological_sort_returns_dependency_order():
    workflow = load_workflow(Path("workflows/customer_support_auto_reply.yaml"))
    order = topological_sort(workflow)

    assert order.index("fetch_inquiry") < order.index("classify_inquiry")
    assert order.index("fetch_inquiry") < order.index("lookup_customer")
    assert order.index("classify_inquiry") < order.index("generate_reply")
    assert order.index("lookup_customer") < order.index("generate_reply")
    assert order.index("wait_for_approval") < order.index("send_reply_email")
