from pathlib import Path

from workflow_engine.adapters.fake_ai import FakeAI
from workflow_engine.adapters.run_store import RunStoreAdapter
from workflow_engine.domain.run import RunStatus
from workflow_engine.engine.executor import WorkflowExecutor
from workflow_engine.engine.registries import AITaskRegistry, ToolRegistry
from workflow_engine.nodes.llm import classify_email, generate_reply
from workflow_engine.nodes.tools import CRMLookupTool, EmailSendTool, InquiryGetTool
from workflow_engine.engine.loader import load_workflow


class FakeMockAPIAdapter:
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
        return {"customer_id": "C001", "email": email, "name": "김민수", "plan": "Enterprise", "status": "active"}

    async def send_email(self, payload):
        self.sent_payloads.append(payload)
        return {
            "message_id": "msg-123",
            "to": payload["to"],
            "status": "sent",
            "sent_at": "2026-04-26T00:00:00Z",
        }


def _executor(client, approval_timer=None):
    from workflow_engine.adapters.fake_ai import FakeAI
    from workflow_engine.engine.registries import AITaskRegistry, ToolRegistry
    from workflow_engine.engine.retry import RetryPolicy
    from workflow_engine.nodes.llm import classify_email, generate_reply

    classify_ai = FakeAI({"category": "billing"})
    generate_ai = FakeAI({
        "subject": "Re: 카드 결제가 계속 실패합니다",
        "body": "예상 처리 기한 3영업일, 접수 확인 번호 ACK-001 안내드립니다.",
    })
    return WorkflowExecutor(
        store=RunStoreAdapter(),
        tool_registry=ToolRegistry({
            "inquiry_get": InquiryGetTool(client),
            "crm_lookup": CRMLookupTool(client),
            "email_send": EmailSendTool(client),
        }),
        ai_registry=AITaskRegistry(
            tasks={"classify_email": classify_email, "generate_reply": generate_reply},
            profiles={"classify_email": classify_ai, "generate_reply": generate_ai},
        ),
        approval_timer=approval_timer,
        default_retry_policy=RetryPolicy(
            initial_delay_seconds=0, multiplier=1.0, max_delay_seconds=0,
        ),
    )


async def test_executor_runs_until_approval_and_stores_context():
    client = FakeMockAPIAdapter()
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


async def test_approval_resumes_and_sends_email():
    client = FakeMockAPIAdapter()
    executor = _executor(client)
    workflow = load_workflow(Path("workflows/customer_support_auto_reply.yaml"))
    run = await executor.start(workflow, {"inquiry_id": "INQ-002"})

    resumed = await executor.submit_approval(workflow, run.run_id, "approve")

    assert resumed.status == RunStatus.COMPLETED
    assert resumed.context["nodes"]["send_reply_email"]["message_id"] == "msg-123"
    assert client.sent_payloads[0]["to"] == "minsu.kim@example.com"


async def test_reject_marks_run_rejected_and_does_not_send_email():
    client = FakeMockAPIAdapter()
    executor = _executor(client)
    workflow = load_workflow(Path("workflows/customer_support_auto_reply.yaml"))
    run = await executor.start(workflow, {"inquiry_id": "INQ-002"})

    rejected = await executor.submit_approval(workflow, run.run_id, "reject", "답변 부정확")

    assert rejected.status == RunStatus.REJECTED
    assert client.sent_payloads == []


async def test_expired_approval_marks_run_timed_out():
    client = FakeMockAPIAdapter()
    executor = _executor(client)
    workflow = load_workflow(Path("workflows/customer_support_auto_reply.yaml"))
    run = await executor.start(workflow, {"inquiry_id": "INQ-002"})
    run.approval.deadline_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    executor.store.save(run)

    timed_out = await executor.submit_approval(workflow, run.run_id, "approve")

    assert timed_out.status == RunStatus.TIMED_OUT
    assert client.sent_payloads == []


class FailingEmailClient(FakeMockAPIAdapter):
    async def send_email(self, payload):
        raise RuntimeError("Email service temporarily unavailable")


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


async def test_active_timer_expires_run_after_deadline():
    import asyncio
    from datetime import datetime, timezone
    from workflow_engine.engine.approval_timer import ApprovalTimer

    client = FakeMockAPIAdapter()
    timer = ApprovalTimer()
    executor = _executor(client, approval_timer=timer)
    timer.set_on_expire(executor.expire_run)
    workflow = load_workflow(Path("workflows/customer_support_auto_reply.yaml"))

    run = await executor.start(workflow, {"inquiry_id": "INQ-002"})
    # 강제로 deadline을 매우 짧게
    run.approval.deadline_at = datetime.now(timezone.utc)
    executor.store.save(run)
    timer.schedule(run.run_id, run.approval.deadline_at)

    await asyncio.sleep(0.1)
    refreshed = executor.store.get(run.run_id)
    assert refreshed.status == RunStatus.TIMED_OUT
    assert refreshed.error.code == "APPROVAL_TIMEOUT"


async def test_approve_cancels_active_timer():
    import asyncio
    from workflow_engine.engine.approval_timer import ApprovalTimer

    client = FakeMockAPIAdapter()
    timer = ApprovalTimer()
    executor = _executor(client, approval_timer=timer)
    timer.set_on_expire(executor.expire_run)
    workflow = load_workflow(Path("workflows/customer_support_auto_reply.yaml"))

    run = await executor.start(workflow, {"inquiry_id": "INQ-002"})
    completed = await executor.submit_approval(workflow, run.run_id, "approve")
    assert completed.status == RunStatus.COMPLETED
    # 타이머가 취소되었는지: 추가 sleep 후에도 status 변하지 않음
    await asyncio.sleep(0.05)
    refreshed = executor.store.get(run.run_id)
    assert refreshed.status == RunStatus.COMPLETED


async def test_expire_if_overdue_lazy_expires_when_timer_lost():
    from datetime import datetime, timedelta, timezone

    client = FakeMockAPIAdapter()
    executor = _executor(client)  # timer 없음 (시뮬레이트: 프로세스 재시작 후 타이머 손실)
    workflow = load_workflow(Path("workflows/customer_support_auto_reply.yaml"))

    run = await executor.start(workflow, {"inquiry_id": "INQ-002"})
    run.approval.deadline_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    executor.store.save(run)

    refreshed = await executor.expire_if_overdue(run.run_id)
    assert refreshed.status == RunStatus.TIMED_OUT
    assert refreshed.error.code == "APPROVAL_TIMEOUT"


class FlakyThenSuccessEmailClient(FakeMockAPIAdapter):
    def __init__(self, fail_count: int):
        super().__init__()
        self.fail_count = fail_count
        self.attempts = 0

    async def send_email(self, payload):
        self.attempts += 1
        if self.attempts <= self.fail_count:
            raise RuntimeError("temporary email outage")
        return await super().send_email(payload)


async def test_node_with_retry_succeeds_after_transient_failures():
    client = FlakyThenSuccessEmailClient(fail_count=4)  # 5회째 성공
    executor = _executor(client)
    workflow = load_workflow(Path("workflows/customer_support_auto_reply.yaml"))
    run = await executor.start(workflow, {"inquiry_id": "INQ-002"})

    completed = await executor.submit_approval(workflow, run.run_id, "approve")

    assert completed.status == RunStatus.COMPLETED
    assert client.attempts == 5  # send_reply_email retry: max_attempts=5
    assert client.sent_payloads[0]["to"] == "minsu.kim@example.com"


async def test_node_with_retry_fails_after_attempts_exhausted():
    client = FailingEmailClient()
    executor = _executor(client)
    workflow = load_workflow(Path("workflows/customer_support_auto_reply.yaml"))
    run = await executor.start(workflow, {"inquiry_id": "INQ-002"})

    failed = await executor.submit_approval(workflow, run.run_id, "approve")

    assert failed.status == RunStatus.FAILED
    assert failed.current_node_key == "send_reply_email"
    assert "Email service temporarily unavailable" in failed.error.message


async def test_node_without_retry_fails_immediately():
    class FailingCRMClient(FakeMockAPIAdapter):
        def __init__(self):
            super().__init__()
            self.attempts = 0

        async def lookup_customer(self, email):
            self.attempts += 1
            raise RuntimeError("crm down")

    client = FailingCRMClient()
    executor = _executor(client)
    workflow = load_workflow(Path("workflows/customer_support_auto_reply.yaml"))

    failed = await executor.start(workflow, {"inquiry_id": "INQ-002"})

    assert failed.status == RunStatus.FAILED
    assert failed.current_node_key == "lookup_customer"
    assert client.attempts == 1   # retry 블록 없음 → 1회만 시도


async def test_input_mapping_error_is_not_retried(tmp_path: Path):
    from workflow_engine.engine.loader import load_workflow

    yaml_text = """
workflow_key: bad_mapping
version: "1.0.0"
nodes:
  - key: fetch_inquiry
    type: tool
    tool: inquiry_get
    inputs:
      inquiry_id: "{{ input.inquiry_id }}"
  - key: classify_inquiry
    type: llm
    task: classify_email
    depends_on: [fetch_inquiry]
    retry: { max_attempts: 5 }
    inputs:
      subject: "{{ nodes.fetch_inquiry.inquiry.MISSING_FIELD }}"
      body: "{{ nodes.fetch_inquiry.inquiry.body }}"
"""
    path = tmp_path / "wf.yaml"
    path.write_text(yaml_text, encoding="utf-8")
    workflow = load_workflow(path)

    classify_calls = 0

    class CountingFakeAI:
        async def chat_json(self, system, user):
            nonlocal classify_calls
            classify_calls += 1
            return {"category": "billing"}

    from workflow_engine.engine.registries import AITaskRegistry, ToolRegistry
    from workflow_engine.engine.retry import RetryPolicy

    executor = WorkflowExecutor(
        store=RunStoreAdapter(),
        tool_registry=ToolRegistry({"inquiry_get": InquiryGetTool(FakeMockAPIAdapter())}),
        ai_registry=AITaskRegistry(
            tasks={"classify_email": classify_email},
            profiles={"classify_email": CountingFakeAI()},
        ),
        default_retry_policy=RetryPolicy(
            initial_delay_seconds=0, multiplier=1.0, max_delay_seconds=0,
        ),
    )

    failed = await executor.start(workflow, {"inquiry_id": "INQ-002"})

    assert failed.status == RunStatus.FAILED
    assert failed.current_node_key == "classify_inquiry"
    assert classify_calls == 0   # input mapping 단계에서 실패 → AI 호출 0회
