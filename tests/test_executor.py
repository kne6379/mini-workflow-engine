from pathlib import Path

from workflow_engine.domain import RunStatus
from workflow_engine.executor import WorkflowExecutor
from workflow_engine.llm import FakeLLMClient, LLMTaskRegistry
from workflow_engine.store import InMemoryRunStore
from workflow_engine.tools import CRMLookupTool, EmailSendTool, InquiryGetTool, ToolRegistry
from workflow_engine.workflow_loader import load_workflow


class FakeMockApiClient:
    def __init__(self):
        self.sent_payloads = []

    async def get_inquiry(self, inquiry_id):
        return {
            "inquiry_id": inquiry_id,
            "from": "minsu.kim@example.com",
            "subject": "카드 결제가 계속 실패합니다",
            "body": "결제 오류가 발생합니다",
            "category": "billing",
            "status": "pending",
        }

    async def lookup_customer(self, email):
        return {"customer_id": "C001", "email": email, "name": "김민수", "plan": "Enterprise"}

    async def send_email(self, payload):
        self.sent_payloads.append(payload)
        return {
            "message_id": "msg-123",
            "to": payload["to"],
            "status": "sent",
            "sent_at": "2026-04-26T00:00:00Z",
        }


def _executor(client):
    return WorkflowExecutor(
        store=InMemoryRunStore(),
        tool_registry=ToolRegistry({
            "inquiry_get": InquiryGetTool(client),
            "crm_lookup": CRMLookupTool(client),
            "email_send": EmailSendTool(client),
        }),
        llm_registry=LLMTaskRegistry(FakeLLMClient()),
    )


async def test_executor_runs_until_approval_and_stores_context():
    client = FakeMockApiClient()
    executor = _executor(client)
    workflow = load_workflow(Path("workflows/customer_support_auto_reply.yaml"))

    run = await executor.start(workflow, {"inquiry_id": "INQ-002"})

    assert run.status == RunStatus.WAITING_APPROVAL
    assert run.current_node_key == "wait_for_approval"
    assert run.context["nodes"]["classify_inquiry"] == {"category": "billing"}
    assert run.context["nodes"]["lookup_customer"]["customer"]["plan"] == "Enterprise"
    assert run.approval is not None
    assert client.sent_payloads == []
