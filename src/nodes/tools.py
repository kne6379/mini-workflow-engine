from typing import Any

from src.engine.ports import CustomerLookup, EmailSender, InquiryReader, Tool
from src.nodes.tool_schemas import (
    CRMLookupInput,
    CRMLookupOutput,
    EmailSendInput,
    EmailSendOutput,
    InquiryGetInput,
    InquiryGetOutput,
)


class InquiryGetTool(Tool):
    name = "inquiry_get"
    input_model = InquiryGetInput
    output_model = InquiryGetOutput

    def __init__(self, inquiry_reader: InquiryReader):
        self.inquiry_reader = inquiry_reader

    async def execute(self, input_data: dict[str, Any]) -> dict[str, Any]:
        inquiry = await self.inquiry_reader.get_inquiry(input_data["inquiry_id"])
        return {"inquiry": inquiry}


class CRMLookupTool(Tool):
    name = "crm_lookup"
    input_model = CRMLookupInput
    output_model = CRMLookupOutput

    def __init__(self, customer_lookup: CustomerLookup):
        self.customer_lookup = customer_lookup

    async def execute(self, input_data: dict[str, Any]) -> dict[str, Any]:
        customer = await self.customer_lookup.lookup_customer(input_data["email"])
        return {"customer": customer}


class EmailSendTool(Tool):
    name = "email_send"
    input_model = EmailSendInput
    output_model = EmailSendOutput

    def __init__(self, email_sender: EmailSender):
        self.email_sender = email_sender

    async def execute(self, input_data: dict[str, Any]) -> dict[str, Any]:
        return await self.email_sender.send_email(input_data)
