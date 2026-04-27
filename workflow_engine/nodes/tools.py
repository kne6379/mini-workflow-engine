from typing import Any

from workflow_engine.engine.ports import CustomerLookup, EmailSender, InquiryReader, Tool


class InquiryGetTool(Tool):
    name = "inquiry_get"

    def __init__(self, inquiry_reader: InquiryReader):
        self.inquiry_reader = inquiry_reader

    async def execute(self, input_data: dict[str, Any]) -> dict[str, Any]:
        inquiry = await self.inquiry_reader.get_inquiry(input_data["inquiry_id"])
        return {"inquiry": inquiry}


class CRMLookupTool(Tool):
    name = "crm_lookup"

    def __init__(self, customer_lookup: CustomerLookup):
        self.customer_lookup = customer_lookup

    async def execute(self, input_data: dict[str, Any]) -> dict[str, Any]:
        customer = await self.customer_lookup.lookup_customer(input_data["email"])
        return {"customer": customer}


class EmailSendTool(Tool):
    name = "email_send"

    def __init__(self, email_sender: EmailSender):
        self.email_sender = email_sender

    async def execute(self, input_data: dict[str, Any]) -> dict[str, Any]:
        email = await self.email_sender.send_email(input_data)
        return {
            "message_id": email["message_id"],
            "status": email["status"],
            "to": email["to"],
            "sent_at": email["sent_at"],
        }
