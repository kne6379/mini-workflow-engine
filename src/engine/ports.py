from abc import ABC, abstractmethod
from typing import Any, ClassVar

from pydantic import BaseModel

from src.domain.run import WorkflowRun


class Tool(ABC):
    name: str  # 구현체가 클래스 변수로 정의
    input_model: ClassVar[type[BaseModel]]
    output_model: ClassVar[type[BaseModel]]

    @abstractmethod
    async def execute(self, input_data: dict[str, Any]) -> dict[str, Any]:
        ...


class AI(ABC):
    @abstractmethod
    async def chat_json(self, system: str, user: str) -> dict[str, Any]:
        ...


class InquiryReader(ABC):
    @abstractmethod
    async def get_inquiry(self, inquiry_id: str) -> dict[str, Any]:
        ...


class CustomerLookup(ABC):
    @abstractmethod
    async def lookup_customer(self, email: str) -> dict[str, Any]:
        ...


class EmailSender(ABC):
    @abstractmethod
    async def send_email(self, payload: dict[str, Any]) -> dict[str, Any]:
        ...


class RunStore(ABC):
    @abstractmethod
    def save(self, run: WorkflowRun) -> WorkflowRun:
        ...

    @abstractmethod
    def get(self, run_id: str) -> WorkflowRun:
        ...

    @abstractmethod
    def list_runs(self) -> list[WorkflowRun]:
        ...

    @abstractmethod
    def find_by_inquiry(self, inquiry_id: str) -> WorkflowRun | None:
        ...
