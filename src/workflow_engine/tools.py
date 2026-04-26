from typing import Any, Protocol

from workflow_engine.retry import RetryExecutor


class Tool(Protocol):
    name: str

    async def execute(self, input_data: dict[str, Any]) -> dict[str, Any]:
        pass


class ToolRegistry:
    def __init__(self, tools: dict[str, Tool]):
        self._tools = tools

    def get(self, name: str) -> Tool:
        try:
            return self._tools[name]
        except KeyError as exc:
            raise KeyError(f"Unknown tool: {name}") from exc


class InquiryGetTool:
    name = "inquiry_get"

    def __init__(self, client, retry_executor: RetryExecutor | None = None):
        self.client = client
        self.retry_executor = retry_executor

    async def execute(self, input_data: dict[str, Any]) -> dict[str, Any]:
        async def operation():
            return await self.client.get_inquiry(input_data["inquiry_id"])

        inquiry = await self._run(operation)
        return {"inquiry": inquiry}

    async def _run(self, operation):
        if self.retry_executor is None:
            return await operation()
        return await self.retry_executor.run(self.name, operation)


class CRMLookupTool:
    name = "crm_lookup"

    def __init__(self, client, retry_executor: RetryExecutor | None = None):
        self.client = client
        self.retry_executor = retry_executor

    async def execute(self, input_data: dict[str, Any]) -> dict[str, Any]:
        async def operation():
            return await self.client.lookup_customer(input_data["email"])

        customer = await self._run(operation)
        return {"customer": customer}

    async def _run(self, operation):
        if self.retry_executor is None:
            return await operation()
        return await self.retry_executor.run(self.name, operation)


class EmailSendTool:
    name = "email_send"

    def __init__(self, client, retry_executor: RetryExecutor | None = None):
        self.client = client
        self.retry_executor = retry_executor

    async def execute(self, input_data: dict[str, Any]) -> dict[str, Any]:
        async def operation():
            return await self.client.send_email(input_data)

        if self.retry_executor is None:
            email = await operation()
        else:
            email = await self.retry_executor.run(self.name, operation)
        return {
            "message_id": email["message_id"],
            "status": email["status"],
            "to": email["to"],
            "sent_at": email["sent_at"],
        }
