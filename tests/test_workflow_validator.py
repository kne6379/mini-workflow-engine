from pathlib import Path

from workflow_engine.workflow_loader import load_workflow


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
