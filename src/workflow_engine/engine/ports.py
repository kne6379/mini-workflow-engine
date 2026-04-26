from typing import Any, Protocol

from workflow_engine.domain.run import WorkflowRun


class Tool(Protocol):
    name: str

    async def execute(self, input_data: dict[str, Any]) -> dict[str, Any]:
        ...


class AI(Protocol):
    async def run_task(self, task_name: str, input_data: dict[str, Any]) -> dict[str, Any]:
        ...


class InquiryReader(Protocol):
    async def get_inquiry(self, inquiry_id: str) -> dict[str, Any]:
        ...


class CustomerLookup(Protocol):
    async def lookup_customer(self, email: str) -> dict[str, Any]:
        ...


class EmailSender(Protocol):
    async def send_email(self, payload: dict[str, Any]) -> dict[str, Any]:
        ...


class RunStore(Protocol):
    def save(self, run: WorkflowRun) -> WorkflowRun:
        ...

    def get(self, run_id: str) -> WorkflowRun:
        ...

    def list_runs(self) -> list[WorkflowRun]:
        ...
