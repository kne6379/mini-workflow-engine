from typing import Any

import httpx

from workflow_engine.retry import PermanentExternalError, TransientExternalError


class MockApiClient:
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
        try:
            async with httpx.AsyncClient(base_url=self.base_url, timeout=10.0) as client:
                response = await client.request(method, path, headers=headers, json=json)
        except httpx.TimeoutException as exc:
            raise TransientExternalError(str(exc)) from exc
        except httpx.TransportError as exc:
            raise TransientExternalError(str(exc)) from exc

        if response.status_code in {408, 429, 500, 502, 503, 504}:
            raise TransientExternalError(response.text)
        if response.status_code >= 400:
            raise PermanentExternalError(response.text)

        body = response.json()
        if isinstance(body, dict) and "data" in body:
            return body["data"]
        return body
