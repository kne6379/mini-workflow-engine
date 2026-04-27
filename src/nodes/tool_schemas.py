from pydantic import BaseModel, ConfigDict, Field


class InquiryGetInput(BaseModel):
    inquiry_id: str


class InquiryData(BaseModel):
    model_config = ConfigDict(extra="allow", populate_by_name=True)

    inquiry_id: str
    from_: str = Field(alias="from")
    subject: str
    body: str
    category: str | None = None
    received_at: str | None = None
    status: str | None = None


class InquiryGetOutput(BaseModel):
    inquiry: InquiryData


class CRMLookupInput(BaseModel):
    email: str


class CustomerData(BaseModel):
    model_config = ConfigDict(extra="allow")

    customer_id: str | None = None
    email: str
    name: str | None = None
    plan: str | None = None
    status: str | None = None


class CRMLookupOutput(BaseModel):
    customer: CustomerData


class EmailSendInput(BaseModel):
    to: str
    subject: str
    body: str


class EmailSendOutput(BaseModel):
    message_id: str
    status: str
    to: str
    sent_at: str
