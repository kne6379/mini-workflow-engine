from pathlib import Path

from workflow_engine.engine.loader import load_workflow


def test_load_workflow_parses_yaml_into_definition(tmp_path: Path):
    yaml_text = """
workflow_key: test_wf
version: "1.0.0"
nodes:
  - key: a
    type: tool
    tool: foo
  - key: b
    type: human_approval
    timeout_seconds: 60
    depends_on: [a]
"""
    path = tmp_path / "wf.yaml"
    path.write_text(yaml_text, encoding="utf-8")
    workflow = load_workflow(path)
    assert workflow.workflow_key == "test_wf"
    assert len(workflow.nodes) == 2
    assert workflow.nodes[0].key == "a"
    assert workflow.nodes[1].timeout_seconds == 60


def test_load_workflow_loads_real_customer_support_yaml():
    workflow = load_workflow(Path("workflows/customer_support_auto_reply.yaml"))
    keys = [node.key for node in workflow.nodes]
    assert "fetch_inquiry" in keys
    assert "wait_for_approval" in keys
    assert "send_reply_email" in keys
