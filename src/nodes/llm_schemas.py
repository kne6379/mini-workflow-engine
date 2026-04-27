from typing import Literal

from pydantic import BaseModel, ConfigDict, field_validator


Category = Literal["billing", "technical", "account", "feature_request", "general"]


class ClassifyEmailInput(BaseModel):
    subject: str
    body: str


class ClassifyEmailOutput(BaseModel):
    category: Category


class GenerateReplyInquiry(BaseModel):
    model_config = ConfigDict(extra="allow")

    subject: str
    body: str


class GenerateReplyCustomer(BaseModel):
    model_config = ConfigDict(extra="allow")

    name: str | None = None
    plan: str | None = None
    status: str | None = None


class GenerateReplyInput(BaseModel):
    inquiry: GenerateReplyInquiry
    category: Category
    customer: GenerateReplyCustomer


class GenerateReplyOutput(BaseModel):
    subject: str
    body: str

    @field_validator("subject", "body")
    @classmethod
    def must_not_be_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("비어있지 않은 문자열이어야 합니다.")
        return value
