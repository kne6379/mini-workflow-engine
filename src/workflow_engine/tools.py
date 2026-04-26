from typing import Any

from workflow_engine.engine.retry import RetryExecutor
from workflow_engine.ports import CustomerLookup, EmailSender, InquiryReader


class InquiryGetTool:
    name = "inquiry_get"

    def __init__(self, inquiry_reader: InquiryReader, retry_executor: RetryExecutor | None = None):
        self.inquiry_reader = inquiry_reader
        self.retry_executor = retry_executor

    async def execute(self, input_data: dict[str, Any]) -> dict[str, Any]:
        async def operation():
            return await self.inquiry_reader.get_inquiry(input_data["inquiry_id"])

        inquiry = await self._run(operation)
        return {"inquiry": inquiry}

    async def _run(self, operation):
        if self.retry_executor is None:
            return await operation()
        return await self.retry_executor.run(self.name, operation)


class CRMLookupTool:
    name = "crm_lookup"

    def __init__(self, customer_lookup: CustomerLookup, retry_executor: RetryExecutor | None = None):
        self.customer_lookup = customer_lookup
        self.retry_executor = retry_executor

    async def execute(self, input_data: dict[str, Any]) -> dict[str, Any]:
        async def operation():
            return await self.customer_lookup.lookup_customer(input_data["email"])

        customer = await self._run(operation)
        return {"customer": customer}

    async def _run(self, operation):
        if self.retry_executor is None:
            return await operation()
        return await self.retry_executor.run(self.name, operation)


class EmailSendTool:
    name = "email_send"

    def __init__(self, email_sender: EmailSender, retry_executor: RetryExecutor | None = None):
        self.email_sender = email_sender
        self.retry_executor = retry_executor

    async def execute(self, input_data: dict[str, Any]) -> dict[str, Any]:
        async def operation():
            return await self.email_sender.send_email(input_data)

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
