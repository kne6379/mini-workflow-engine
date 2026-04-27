from typing import Any

import httpx

from workflow_engine.engine.ports import CustomerLookup, EmailSender, InquiryReader


class MockAPIAdapter(InquiryReader, CustomerLookup, EmailSender):
    def __init__(self, base_url: str, api_key: str):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key

    async def get_inquiry(self, inquiry_id: str) -> dict[str, Any]:
        return await self._request("GET", f"/api/inquiries/{inquiry_id}")

    async def lookup_customer(self, email: str) -> dict[str, Any]:
        return await self._request("POST", "/api/crm/lookup", json={"email": email})

    async def send_email(self, payload: dict[str, Any]) -> dict[str, Any]:
        return await self._request("POST", "/api/email/send", json=payload)

    async def _request(
        self, method: str, path: str, json: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        headers = {"Authorization": f"Bearer {self.api_key}"}
        async with httpx.AsyncClient(base_url=self.base_url, timeout=10.0) as client:
            response = await client.request(method, path, headers=headers, json=json)
        response.raise_for_status()
        body = response.json()
        if isinstance(body, dict) and "data" in body:
            return body["data"]
        return body


class FakeMockAPIAdapter(InquiryReader, CustomerLookup, EmailSender):
    async def get_inquiry(self, inquiry_id: str) -> dict[str, Any]:
        return {
            "inquiry_id": inquiry_id,
            "from": "minsu.kim@example.com",
            "subject": "카드 결제가 계속 실패합니다",
            "body": "결제 오류가 발생합니다",
            "category": "billing",
            "status": "pending",
        }

    async def lookup_customer(self, email: str) -> dict[str, Any]:
        return {
            "customer_id": "C001",
            "email": email,
            "name": "김민수",
            "plan": "Enterprise",
            "status": "active",
        }

    async def send_email(self, payload: dict[str, Any]) -> dict[str, Any]:
        return {
            "message_id": "msg-123",
            "to": payload["to"],
            "status": "sent",
            "sent_at": "2026-04-26T00:00:00Z",
        }
