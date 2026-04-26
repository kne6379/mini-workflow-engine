from workflow_engine.retry import RetryExecutor, RetryPolicy, TransientExternalError
from workflow_engine.tools import (
    CRMLookupTool,
    EmailSendTool,
    InquiryGetTool,
    ToolRegistry,
)


class FakeMockApiClient:
    def __init__(self):
        self.sent_email = None

    async def get_inquiry(self, inquiry_id):
        return {
            "inquiry_id": inquiry_id,
            "from": "minsu.kim@example.com",
            "subject": "카드 결제가 계속 실패합니다",
            "body": "본문",
            "category": "billing",
            "status": "pending",
        }

    async def lookup_customer(self, email):
        return {
            "customer_id": "C001",
            "email": email,
            "name": "김민수",
            "plan": "Enterprise",
        }

    async def send_email(self, payload):
        self.sent_email = payload
        return {
            "message_id": "msg-123",
            "to": payload["to"],
            "status": "sent",
            "sent_at": "2026-04-26T00:00:00Z",
        }


async def test_inquiry_get_tool_returns_inquiry_output_shape():
    tool = InquiryGetTool(FakeMockApiClient())

    output = await tool.execute({"inquiry_id": "INQ-002"})

    assert output["inquiry"]["inquiry_id"] == "INQ-002"


async def test_crm_lookup_tool_returns_customer_output_shape():
    tool = CRMLookupTool(FakeMockApiClient())

    output = await tool.execute({"email": "minsu.kim@example.com"})

    assert output["customer"]["plan"] == "Enterprise"


async def test_email_send_tool_returns_delivery_result_without_body_duplication():
    client = FakeMockApiClient()
    tool = EmailSendTool(client)

    output = await tool.execute(
        {
            "to": "minsu.kim@example.com",
            "subject": "Re: 카드 결제가 계속 실패합니다",
            "body": "안녕하세요",
        }
    )

    assert output == {
        "message_id": "msg-123",
        "status": "sent",
        "to": "minsu.kim@example.com",
        "sent_at": "2026-04-26T00:00:00Z",
    }
    assert client.sent_email["body"] == "안녕하세요"


class FlakyEmailClient(FakeMockApiClient):
    def __init__(self):
        super().__init__()
        self.attempts = 0

    async def send_email(self, payload):
        self.attempts += 1
        if self.attempts < 3:
            raise TransientExternalError("temporary email outage")
        return await super().send_email(payload)


async def test_email_send_tool_retries_transient_failures():
    client = FlakyEmailClient()
    tool = EmailSendTool(
        client,
        retry_executor=RetryExecutor(
            RetryPolicy(max_attempts=3, initial_delay_seconds=0)
        ),
    )

    output = await tool.execute(
        {
            "to": "minsu.kim@example.com",
            "subject": "Re: 카드 결제가 계속 실패합니다",
            "body": "안녕하세요",
        }
    )

    assert output["message_id"] == "msg-123"
    assert client.attempts == 3


def test_tool_registry_returns_registered_tools():
    registry = ToolRegistry({"inquiry_get": InquiryGetTool(FakeMockApiClient())})

    assert registry.get("inquiry_get").name == "inquiry_get"
