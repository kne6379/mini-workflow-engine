from pathlib import Path

from workflow_engine.adapters.ai import FakeAIAdapter
from workflow_engine.adapters.run_store import RunStoreAdapter
from workflow_engine.domain.run import RunStatus
from workflow_engine.engine.executor import WorkflowExecutor
from workflow_engine.engine.registries import AITaskRegistry, ToolRegistry
from workflow_engine.tools import CRMLookupTool, EmailSendTool, InquiryGetTool
from workflow_engine.engine.workflow_loader import load_workflow


class FakeMockServerAdapter:
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
        store=RunStoreAdapter(),
        tool_registry=ToolRegistry({
            "inquiry_get": InquiryGetTool(client),
            "crm_lookup": CRMLookupTool(client),
            "email_send": EmailSendTool(client),
        }),
        ai_registry=AITaskRegistry(FakeAIAdapter()),
    )


async def test_executor_runs_until_approval_and_stores_context():
    client = FakeMockServerAdapter()
    executor = _executor(client)
    workflow = load_workflow(Path("workflows/customer_support_auto_reply.yaml"))

    run = await executor.start(workflow, {"inquiry_id": "INQ-002"})

    assert run.status == RunStatus.WAITING_APPROVAL
    assert run.current_node_key == "wait_for_approval"
    assert run.context["nodes"]["classify_inquiry"] == {"category": "billing"}
    assert run.context["nodes"]["lookup_customer"]["customer"]["plan"] == "Enterprise"
    assert run.approval is not None
    assert client.sent_payloads == []


from datetime import datetime, timedelta, timezone

from workflow_engine.domain.run import RunStatus
from workflow_engine.engine.retry import TransientExternalError


async def test_approval_resumes_and_sends_email():
    client = FakeMockServerAdapter()
    executor = _executor(client)
    workflow = load_workflow(Path("workflows/customer_support_auto_reply.yaml"))
    run = await executor.start(workflow, {"inquiry_id": "INQ-002"})

    resumed = await executor.submit_approval(workflow, run.run_id, "approve")

    assert resumed.status == RunStatus.COMPLETED
    assert resumed.context["nodes"]["send_reply_email"]["message_id"] == "msg-123"
    assert client.sent_payloads[0]["to"] == "minsu.kim@example.com"


async def test_reject_marks_run_rejected_and_does_not_send_email():
    client = FakeMockServerAdapter()
    executor = _executor(client)
    workflow = load_workflow(Path("workflows/customer_support_auto_reply.yaml"))
    run = await executor.start(workflow, {"inquiry_id": "INQ-002"})

    rejected = await executor.submit_approval(workflow, run.run_id, "reject", "답변 부정확")

    assert rejected.status == RunStatus.REJECTED
    assert client.sent_payloads == []


async def test_expired_approval_marks_run_timed_out():
    client = FakeMockServerAdapter()
    executor = _executor(client)
    workflow = load_workflow(Path("workflows/customer_support_auto_reply.yaml"))
    run = await executor.start(workflow, {"inquiry_id": "INQ-002"})
    run.approval.deadline_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    executor.store.save(run)

    timed_out = await executor.submit_approval(workflow, run.run_id, "approve")

    assert timed_out.status == RunStatus.TIMED_OUT
    assert client.sent_payloads == []


class FailingEmailClient(FakeMockServerAdapter):
    async def send_email(self, payload):
        raise TransientExternalError("Email service temporarily unavailable")


async def test_send_email_failure_marks_node_and_run_failed():
    client = FailingEmailClient()
    executor = _executor(client)
    workflow = load_workflow(Path("workflows/customer_support_auto_reply.yaml"))
    run = await executor.start(workflow, {"inquiry_id": "INQ-002"})

    failed = await executor.submit_approval(workflow, run.run_id, "approve")

    assert failed.status == RunStatus.FAILED
    assert failed.current_node_key == "send_reply_email"
    assert failed.node_states["send_reply_email"].status == "FAILED"
    assert failed.error.node_key == "send_reply_email"
