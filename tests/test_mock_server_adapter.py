import pytest
import respx
from httpx import Response

from workflow_engine.adapters.mock_server import MockServerAdapter
from workflow_engine.engine.retry import PermanentExternalError, TransientExternalError


@respx.mock
async def test_mock_server_adapter_sends_bearer_token_and_unwraps_data_response():
    route = respx.get("http://mock.local/api/inquiries/INQ-002").mock(
        return_value=Response(
            200,
            json={
                "success": True,
                "data": {"inquiry_id": "INQ-002"},
            },
        )
    )
    client = MockServerAdapter("http://mock.local/", "mock-api-key-12345")

    output = await client.get_inquiry("INQ-002")

    assert output == {"inquiry_id": "INQ-002"}
    assert route.calls[0].request.headers["Authorization"] == "Bearer mock-api-key-12345"


@respx.mock
async def test_mock_server_adapter_maps_transient_http_status_to_retryable_error():
    respx.post("http://mock.local/api/email/send").mock(
        return_value=Response(503, text="temporarily unavailable")
    )
    client = MockServerAdapter("http://mock.local", "mock-api-key-12345")

    with pytest.raises(TransientExternalError):
        await client.send_email({"to": "minsu.kim@example.com", "subject": "답변", "body": "본문"})


@respx.mock
async def test_mock_server_adapter_maps_non_retryable_http_status_to_permanent_error():
    respx.post("http://mock.local/api/crm/lookup").mock(
        return_value=Response(404, text="customer not found")
    )
    client = MockServerAdapter("http://mock.local", "mock-api-key-12345")

    with pytest.raises(PermanentExternalError):
        await client.lookup_customer("missing@example.com")
