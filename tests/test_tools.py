from src.engine.registries import ToolRegistry
from src.nodes.tools import (
    CRMLookupTool,
    EmailSendTool,
    InquiryGetTool,
)
from src.nodes.tool_schemas import (
    CRMLookupInput,
    CRMLookupOutput,
    EmailSendInput,
    EmailSendOutput,
    InquiryGetInput,
    InquiryGetOutput,
)


class FakeMockAPIAdapter:
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
    tool = InquiryGetTool(FakeMockAPIAdapter())

    output = await tool.execute({"inquiry_id": "INQ-002"})

    assert output["inquiry"]["inquiry_id"] == "INQ-002"


def test_tool_schema_models_validate_expected_payloads():
    assert InquiryGetInput.model_validate({"inquiry_id": "INQ-002"}).inquiry_id == "INQ-002"
    assert CRMLookupInput.model_validate({"email": "minsu.kim@example.com"}).email == "minsu.kim@example.com"
    assert EmailSendInput.model_validate({
        "to": "minsu.kim@example.com",
        "subject": "Re: 카드 결제가 계속 실패합니다",
        "body": "안녕하세요",
    }).to == "minsu.kim@example.com"

    inquiry = InquiryGetOutput.model_validate({
        "inquiry": {
            "inquiry_id": "INQ-002",
            "from": "minsu.kim@example.com",
            "subject": "카드 결제가 계속 실패합니다",
            "body": "본문",
            "category": "billing",
            "status": "pending",
        }
    }).model_dump(by_alias=True)
    assert inquiry["inquiry"]["from"] == "minsu.kim@example.com"

    assert CRMLookupOutput.model_validate({
        "customer": {
            "customer_id": "C001",
            "email": "minsu.kim@example.com",
            "name": "김민수",
            "plan": "Enterprise",
            "status": "active",
        }
    }).customer.plan == "Enterprise"

    assert EmailSendOutput.model_validate({
        "message_id": "msg-123",
        "status": "sent",
        "to": "minsu.kim@example.com",
        "sent_at": "2026-04-26T00:00:00Z",
    }).message_id == "msg-123"


def test_tools_expose_input_and_output_schemas():
    assert InquiryGetTool.input_model is InquiryGetInput
    assert InquiryGetTool.output_model is InquiryGetOutput
    assert CRMLookupTool.input_model is CRMLookupInput
    assert CRMLookupTool.output_model is CRMLookupOutput
    assert EmailSendTool.input_model is EmailSendInput
    assert EmailSendTool.output_model is EmailSendOutput


async def test_crm_lookup_tool_returns_customer_output_shape():
    tool = CRMLookupTool(FakeMockAPIAdapter())

    output = await tool.execute({"email": "minsu.kim@example.com"})

    assert output["customer"]["plan"] == "Enterprise"


async def test_email_send_tool_returns_delivery_result_without_body_duplication():
    client = FakeMockAPIAdapter()
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


def test_tool_registry_returns_registered_tools():
    registry = ToolRegistry({"inquiry_get": InquiryGetTool(FakeMockAPIAdapter())})

    assert registry.get("inquiry_get").name == "inquiry_get"
