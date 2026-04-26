# Mini Workflow Engine Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the assignment's runnable mini workflow engine: YAML-defined DAG execution, Mock API tools, LLM tasks, human approval pause/resume, retry, Korean Swagger docs, and tests.

**Architecture:** FastAPI exposes workflow-run APIs while the orchestration core remains framework-independent. YAML workflow definitions are validated before execution, node runners dispatch by `type`, registries map tool/task names to implementations, and an in-memory run store tracks pause/resume state.

**Tech Stack:** Python 3.13, FastAPI, Pydantic v2, httpx, PyYAML, OpenAI Python SDK, pytest, pytest-asyncio.

---

## File Structure

- Create: `pyproject.toml` - package metadata, dependencies, pytest config.
- Create: `.env.example` - documented environment variables.
- Create: `README.md` - run instructions, design summary, security notes.
- Create: `workflows/customer_support_auto_reply.yaml` - assignment workflow definition.
- Create: `src/workflow_engine/__init__.py` - package marker.
- Create: `src/workflow_engine/config.py` - environment-based settings.
- Create: `src/workflow_engine/domain.py` - shared enums and Pydantic models.
- Create: `src/workflow_engine/errors.py` - typed domain exceptions.
- Create: `src/workflow_engine/workflow_loader.py` - YAML loading.
- Create: `src/workflow_engine/workflow_validator.py` - schema relationship and DAG validation.
- Create: `src/workflow_engine/input_mapping.py` - `{{ input.x }}` / `{{ nodes.x.y }}` rendering.
- Create: `src/workflow_engine/retry.py` - retry policy and executor for transient failures.
- Create: `src/workflow_engine/store.py` - in-memory run store.
- Create: `src/workflow_engine/mock_api_client.py` - typed Mock API HTTP client.
- Create: `src/workflow_engine/tools.py` - Tool interface, registry, and `inquiry_get` / `crm_lookup` / `email_send`.
- Create: `src/workflow_engine/policies.py` - assignment response guidelines and plan rules.
- Create: `src/workflow_engine/llm.py` - LLM task interface, fake LLM, OpenAI-backed LLM.
- Create: `src/workflow_engine/executor.py` - workflow executor, node runners, approval resume.
- Create: `src/workflow_engine/api.py` - FastAPI app with Korean OpenAPI text.
- Create: `src/workflow_engine/main.py` - uvicorn entrypoint helper.
- Create: `tests/test_workflow_validator.py` - validation tests.
- Create: `tests/test_input_mapping.py` - context input rendering tests.
- Create: `tests/test_retry.py` - retry behavior tests.
- Create: `tests/test_tools.py` - tool contract tests with fake Mock API client.
- Create: `tests/test_llm.py` - fake LLM and output validation tests.
- Create: `tests/test_executor.py` - orchestration, approval, retry-failure tests.
- Create: `tests/test_api.py` - FastAPI endpoint and Korean OpenAPI tests.

## Task 1: Project Scaffold and Workflow Definition

**Files:**
- Create: `pyproject.toml`
- Create: `.env.example`
- Create: `workflows/customer_support_auto_reply.yaml`
- Create: `src/workflow_engine/__init__.py`
- Create: `src/workflow_engine/domain.py`
- Create: `src/workflow_engine/workflow_loader.py`
- Test: `tests/test_workflow_validator.py`

- [ ] **Step 1: Write the failing workflow loading test**

Create `tests/test_workflow_validator.py` with:

```python
from pathlib import Path

from workflow_engine.workflow_loader import load_workflow


def test_loads_customer_support_workflow_definition():
    workflow = load_workflow(Path("workflows/customer_support_auto_reply.yaml"))

    assert workflow.workflow_key == "customer_support_auto_reply"
    assert [node.key for node in workflow.nodes] == [
        "fetch_inquiry",
        "classify_inquiry",
        "lookup_customer",
        "generate_reply",
        "wait_for_approval",
        "send_reply_email",
    ]
    assert workflow.nodes[0].type == "tool"
    assert workflow.nodes[0].tool == "inquiry_get"
```

- [ ] **Step 2: Run the test and verify it fails**

Run:

```bash
python3.13 -m pytest tests/test_workflow_validator.py::test_loads_customer_support_workflow_definition -q
```

Expected: FAIL with `ModuleNotFoundError: No module named 'workflow_engine'`.

- [ ] **Step 3: Add package config and workflow model**

Create `pyproject.toml`:

```toml
[project]
name = "cox-wave-workflow-engine"
version = "0.1.0"
requires-python = ">=3.13,<3.14"
dependencies = [
  "fastapi==0.115.0",
  "uvicorn==0.30.0",
  "pydantic==2.9.0",
  "pydantic-settings==2.6.1",
  "httpx==0.27.2",
  "PyYAML==6.0.2",
  "openai==1.59.6",
]

[project.optional-dependencies]
dev = [
  "pytest==8.3.4",
  "pytest-asyncio==0.25.0",
  "respx==0.22.0",
]

[tool.pytest.ini_options]
pythonpath = ["src"]
asyncio_mode = "auto"
```

Create `.env.example`:

```bash
MOCK_API_BASE_URL=http://localhost:8080
MOCK_API_KEY=mock-api-key-12345
LLM_PROVIDER=fake
OPENAI_API_KEY=
OPENAI_MODEL=gpt-4.1-mini
```

Create `src/workflow_engine/__init__.py`:

```python
"""Mini workflow engine for the Coxwave assignment."""
```

Create `src/workflow_engine/domain.py`:

```python
from datetime import datetime
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, Field


class NodeType(StrEnum):
    TOOL = "tool"
    LLM = "llm"
    HUMAN_APPROVAL = "human_approval"


class RunStatus(StrEnum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    WAITING_APPROVAL = "WAITING_APPROVAL"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    REJECTED = "REJECTED"
    TIMED_OUT = "TIMED_OUT"


class NodeStatus(StrEnum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    WAITING = "WAITING"
    FAILED = "FAILED"
    SKIPPED = "SKIPPED"


class WorkflowNode(BaseModel):
    key: str
    type: Literal["tool", "llm", "human_approval"]
    depends_on: list[str] = Field(default_factory=list)
    inputs: dict[str, Any] = Field(default_factory=dict)
    tool: str | None = None
    task: str | None = None
    timeout_seconds: int | None = None


class WorkflowDefinition(BaseModel):
    workflow_key: str
    version: str
    nodes: list[WorkflowNode]


class WorkflowErrorData(BaseModel):
    code: str
    message: str
    node_key: str | None = None
    retryable: bool = False
    details: dict[str, Any] = Field(default_factory=dict)


class NodeState(BaseModel):
    status: NodeStatus = NodeStatus.PENDING
    attempts: int = 0
    error: WorkflowErrorData | None = None


class ApprovalState(BaseModel):
    node_key: str
    subject: str
    body: str
    deadline_at: datetime
    decision: Literal["approve", "reject"] | None = None
    reason: str | None = None
    decided_at: datetime | None = None


class WorkflowRun(BaseModel):
    run_id: str
    workflow_key: str
    status: RunStatus
    current_node_key: str | None = None
    context: dict[str, Any]
    node_states: dict[str, NodeState]
    approval: ApprovalState | None = None
    error: WorkflowErrorData | None = None
    created_at: datetime
    updated_at: datetime
```

Create `src/workflow_engine/workflow_loader.py`:

```python
from pathlib import Path

import yaml

from workflow_engine.domain import WorkflowDefinition


def load_workflow(path: Path) -> WorkflowDefinition:
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    return WorkflowDefinition.model_validate(raw)
```

- [ ] **Step 4: Add the assignment workflow YAML**

Create `workflows/customer_support_auto_reply.yaml`:

```yaml
workflow_key: customer_support_auto_reply
version: "1.0.0"

nodes:
  - key: fetch_inquiry
    type: tool
    tool: inquiry_get
    inputs:
      inquiry_id: "{{ input.inquiry_id }}"

  - key: classify_inquiry
    type: llm
    task: classify_email
    depends_on:
      - fetch_inquiry
    inputs:
      subject: "{{ nodes.fetch_inquiry.inquiry.subject }}"
      body: "{{ nodes.fetch_inquiry.inquiry.body }}"

  - key: lookup_customer
    type: tool
    tool: crm_lookup
    depends_on:
      - fetch_inquiry
    inputs:
      email: "{{ nodes.fetch_inquiry.inquiry.from }}"

  - key: generate_reply
    type: llm
    task: generate_reply
    depends_on:
      - classify_inquiry
      - lookup_customer
    inputs:
      inquiry: "{{ nodes.fetch_inquiry.inquiry }}"
      category: "{{ nodes.classify_inquiry.category }}"
      customer: "{{ nodes.lookup_customer.customer }}"

  - key: wait_for_approval
    type: human_approval
    depends_on:
      - generate_reply
    timeout_seconds: 1800
    inputs:
      subject: "{{ nodes.generate_reply.subject }}"
      body: "{{ nodes.generate_reply.body }}"

  - key: send_reply_email
    type: tool
    tool: email_send
    depends_on:
      - wait_for_approval
    inputs:
      to: "{{ nodes.fetch_inquiry.inquiry.from }}"
      subject: "{{ nodes.generate_reply.subject }}"
      body: "{{ nodes.generate_reply.body }}"
```

- [ ] **Step 5: Run the test and commit**

Run:

```bash
python3.13 -m pytest tests/test_workflow_validator.py::test_loads_customer_support_workflow_definition -q
```

Expected: PASS.

Commit:

```bash
git add pyproject.toml .env.example workflows/customer_support_auto_reply.yaml src/workflow_engine/__init__.py src/workflow_engine/domain.py src/workflow_engine/workflow_loader.py tests/test_workflow_validator.py
git commit -m "feat: add workflow definition schema"
```

## Task 2: Workflow Validation and Input Mapping

**Files:**
- Create: `src/workflow_engine/errors.py`
- Create: `src/workflow_engine/workflow_validator.py`
- Create: `src/workflow_engine/input_mapping.py`
- Modify: `tests/test_workflow_validator.py`
- Test: `tests/test_input_mapping.py`

- [ ] **Step 1: Add failing validation tests**

Append to `tests/test_workflow_validator.py`:

```python
import pytest

from workflow_engine.domain import WorkflowDefinition
from workflow_engine.errors import WorkflowValidationError
from workflow_engine.workflow_validator import topological_sort, validate_workflow


def _workflow(nodes):
    return WorkflowDefinition(workflow_key="wf", version="1.0.0", nodes=nodes)


def test_validation_rejects_duplicate_node_keys():
    workflow = WorkflowDefinition.model_validate({
        "workflow_key": "wf",
        "version": "1.0.0",
        "nodes": [
            {"key": "same", "type": "tool", "tool": "inquiry_get"},
            {"key": "same", "type": "tool", "tool": "crm_lookup"},
        ],
    })

    with pytest.raises(WorkflowValidationError, match="Duplicate node key"):
        validate_workflow(workflow)


def test_validation_rejects_missing_dependency():
    workflow = WorkflowDefinition.model_validate({
        "workflow_key": "wf",
        "version": "1.0.0",
        "nodes": [
            {"key": "generate_reply", "type": "llm", "task": "generate_reply", "depends_on": ["missing"]},
        ],
    })

    with pytest.raises(WorkflowValidationError, match="unknown node"):
        validate_workflow(workflow)


def test_validation_rejects_cycle():
    workflow = WorkflowDefinition.model_validate({
        "workflow_key": "wf",
        "version": "1.0.0",
        "nodes": [
            {"key": "a", "type": "tool", "tool": "inquiry_get", "depends_on": ["b"]},
            {"key": "b", "type": "tool", "tool": "crm_lookup", "depends_on": ["a"]},
        ],
    })

    with pytest.raises(WorkflowValidationError, match="cycle"):
        validate_workflow(workflow)


def test_validation_rejects_missing_type_specific_fields():
    workflow = WorkflowDefinition.model_validate({
        "workflow_key": "wf",
        "version": "1.0.0",
        "nodes": [
            {"key": "lookup_customer", "type": "tool"},
            {"key": "classify_inquiry", "type": "llm"},
            {"key": "wait_for_approval", "type": "human_approval"},
        ],
    })

    with pytest.raises(WorkflowValidationError, match="requires"):
        validate_workflow(workflow)


def test_topological_sort_returns_dependency_order():
    workflow = load_workflow(Path("workflows/customer_support_auto_reply.yaml"))
    order = topological_sort(workflow)

    assert order.index("fetch_inquiry") < order.index("classify_inquiry")
    assert order.index("fetch_inquiry") < order.index("lookup_customer")
    assert order.index("classify_inquiry") < order.index("generate_reply")
    assert order.index("lookup_customer") < order.index("generate_reply")
    assert order.index("wait_for_approval") < order.index("send_reply_email")
```

- [ ] **Step 2: Add failing input mapping tests**

Create `tests/test_input_mapping.py`:

```python
import pytest

from workflow_engine.errors import InputMappingError
from workflow_engine.input_mapping import render_inputs


def test_render_inputs_resolves_full_value_templates():
    context = {
        "input": {"inquiry_id": "INQ-002"},
        "nodes": {
            "fetch_inquiry": {
                "inquiry": {
                    "from": "minsu.kim@example.com",
                    "subject": "카드 결제가 계속 실패합니다",
                }
            }
        },
    }

    rendered = render_inputs(
        {
            "inquiry_id": "{{ input.inquiry_id }}",
            "email": "{{ nodes.fetch_inquiry.inquiry.from }}",
        },
        context,
    )

    assert rendered == {
        "inquiry_id": "INQ-002",
        "email": "minsu.kim@example.com",
    }


def test_render_inputs_resolves_embedded_templates():
    context = {
        "input": {},
        "nodes": {
            "fetch_inquiry": {
                "inquiry": {
                    "subject": "카드 결제가 계속 실패합니다",
                }
            }
        },
    }

    rendered = render_inputs(
        {"subject": "Re: {{ nodes.fetch_inquiry.inquiry.subject }}"},
        context,
    )

    assert rendered == {"subject": "Re: 카드 결제가 계속 실패합니다"}


def test_render_inputs_fails_when_path_is_missing():
    with pytest.raises(InputMappingError, match="nodes.fetch_inquiry.inquiry.from"):
        render_inputs({"email": "{{ nodes.fetch_inquiry.inquiry.from }}"}, {"input": {}, "nodes": {}})
```

- [ ] **Step 3: Run tests and verify failures**

Run:

```bash
python3.13 -m pytest tests/test_workflow_validator.py tests/test_input_mapping.py -q
```

Expected: FAIL with imports missing for `workflow_engine.errors`, `workflow_engine.workflow_validator`, and `workflow_engine.input_mapping`.

- [ ] **Step 4: Implement validation and mapping**

Create `src/workflow_engine/errors.py`:

```python
class WorkflowEngineError(Exception):
    code = "WORKFLOW_ENGINE_ERROR"


class WorkflowValidationError(WorkflowEngineError):
    code = "WORKFLOW_VALIDATION_ERROR"


class InputMappingError(WorkflowEngineError):
    code = "INPUT_MAPPING_ERROR"
```

Create `src/workflow_engine/workflow_validator.py`:

```python
from collections import deque

from workflow_engine.domain import WorkflowDefinition, WorkflowNode
from workflow_engine.errors import WorkflowValidationError


def validate_workflow(workflow: WorkflowDefinition) -> None:
    keys = [node.key for node in workflow.nodes]
    duplicate_keys = {key for key in keys if keys.count(key) > 1}
    if duplicate_keys:
        raise WorkflowValidationError(f"Duplicate node key: {sorted(duplicate_keys)[0]}")

    node_by_key = {node.key: node for node in workflow.nodes}
    for node in workflow.nodes:
        _validate_node_required_fields(node)
        for dependency in node.depends_on:
            if dependency not in node_by_key:
                raise WorkflowValidationError(
                    f"Node '{node.key}' depends on unknown node '{dependency}'"
                )

    topological_sort(workflow)


def topological_sort(workflow: WorkflowDefinition) -> list[str]:
    node_by_key = {node.key: node for node in workflow.nodes}
    incoming_counts = {node.key: len(node.depends_on) for node in workflow.nodes}
    outgoing: dict[str, list[str]] = {node.key: [] for node in workflow.nodes}

    for node in workflow.nodes:
        for dependency in node.depends_on:
            if dependency not in node_by_key:
                raise WorkflowValidationError(
                    f"Node '{node.key}' depends on unknown node '{dependency}'"
                )
            outgoing[dependency].append(node.key)

    ready = deque([node.key for node in workflow.nodes if incoming_counts[node.key] == 0])
    order: list[str] = []

    while ready:
        key = ready.popleft()
        order.append(key)
        for dependent in outgoing[key]:
            incoming_counts[dependent] -= 1
            if incoming_counts[dependent] == 0:
                ready.append(dependent)

    if len(order) != len(workflow.nodes):
        raise WorkflowValidationError("Workflow graph contains a cycle")

    return order


def _validate_node_required_fields(node: WorkflowNode) -> None:
    if node.type == "tool" and not node.tool:
        raise WorkflowValidationError(f"Node '{node.key}' with type 'tool' requires tool")
    if node.type == "llm" and not node.task:
        raise WorkflowValidationError(f"Node '{node.key}' with type 'llm' requires task")
    if node.type == "human_approval" and node.timeout_seconds is None:
        raise WorkflowValidationError(
            f"Node '{node.key}' with type 'human_approval' requires timeout_seconds"
        )
```

Create `src/workflow_engine/input_mapping.py`:

```python
import re
from typing import Any

from workflow_engine.errors import InputMappingError

TEMPLATE_PATTERN = re.compile(r"{{\s*([^}]+?)\s*}}")


def render_inputs(inputs: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    return {key: _render_value(value, context) for key, value in inputs.items()}


def _render_value(value: Any, context: dict[str, Any]) -> Any:
    if isinstance(value, str):
        matches = list(TEMPLATE_PATTERN.finditer(value))
        if not matches:
            return value
        if len(matches) == 1 and matches[0].span() == (0, len(value)):
            return _resolve_path(matches[0].group(1), context)
        rendered = value
        for match in matches:
            path = match.group(1)
            resolved = _resolve_path(path, context)
            rendered = rendered.replace(match.group(0), str(resolved))
        return rendered
    if isinstance(value, dict):
        return {key: _render_value(inner, context) for key, inner in value.items()}
    if isinstance(value, list):
        return [_render_value(item, context) for item in value]
    return value


def _resolve_path(path: str, context: dict[str, Any]) -> Any:
    current: Any = context
    clean_path = path.strip()
    for part in clean_path.split("."):
        if isinstance(current, dict) and part in current:
            current = current[part]
            continue
        raise InputMappingError(f"Missing input mapping path: {clean_path}")
    return current
```

- [ ] **Step 5: Run tests and commit**

Run:

```bash
python3.13 -m pytest tests/test_workflow_validator.py tests/test_input_mapping.py -q
```

Expected: PASS.

Commit:

```bash
git add src/workflow_engine/errors.py src/workflow_engine/workflow_validator.py src/workflow_engine/input_mapping.py tests/test_workflow_validator.py tests/test_input_mapping.py
git commit -m "feat: validate workflow definitions"
```

## Task 3: Retry Executor and Run Store

**Files:**
- Create: `src/workflow_engine/retry.py`
- Create: `src/workflow_engine/store.py`
- Test: `tests/test_retry.py`
- Test: `tests/test_store.py`

- [ ] **Step 1: Write failing retry tests**

Create `tests/test_retry.py`:

```python
import pytest

from workflow_engine.retry import RetryExecutor, RetryPolicy, TransientExternalError


async def test_retry_executor_retries_transient_errors():
    attempts = 0

    async def operation():
        nonlocal attempts
        attempts += 1
        if attempts < 3:
            raise TransientExternalError("service unavailable")
        return {"ok": True}

    executor = RetryExecutor(RetryPolicy(max_attempts=3, initial_delay_seconds=0))
    result = await executor.run("email_send", operation)

    assert result == {"ok": True}
    assert attempts == 3


async def test_retry_executor_raises_after_attempts_are_exhausted():
    attempts = 0

    async def operation():
        nonlocal attempts
        attempts += 1
        raise TransientExternalError("service unavailable")

    executor = RetryExecutor(RetryPolicy(max_attempts=3, initial_delay_seconds=0))

    with pytest.raises(TransientExternalError):
        await executor.run("email_send", operation)

    assert attempts == 3
```

- [ ] **Step 2: Write failing store tests**

Create `tests/test_store.py`:

```python
from datetime import datetime, timezone

import pytest

from workflow_engine.domain import NodeState, RunStatus, WorkflowRun
from workflow_engine.store import InMemoryRunStore, RunNotFoundError


def test_store_saves_and_returns_run():
    store = InMemoryRunStore()
    now = datetime.now(timezone.utc)
    run = WorkflowRun(
        run_id="run_123",
        workflow_key="customer_support_auto_reply",
        status=RunStatus.PENDING,
        current_node_key=None,
        context={"input": {"inquiry_id": "INQ-002"}, "nodes": {}},
        node_states={"fetch_inquiry": NodeState()},
        created_at=now,
        updated_at=now,
    )

    store.save(run)

    assert store.get("run_123").run_id == "run_123"
    assert store.list_runs() == [run]


def test_store_raises_for_missing_run():
    store = InMemoryRunStore()

    with pytest.raises(RunNotFoundError):
        store.get("missing")
```

- [ ] **Step 3: Run tests and verify failures**

Run:

```bash
python3.13 -m pytest tests/test_retry.py tests/test_store.py -q
```

Expected: FAIL with missing modules.

- [ ] **Step 4: Implement retry and store**

Create `src/workflow_engine/retry.py`:

```python
import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import TypeVar

T = TypeVar("T")


class TransientExternalError(Exception):
    pass


class PermanentExternalError(Exception):
    pass


@dataclass(frozen=True)
class RetryPolicy:
    max_attempts: int = 3
    initial_delay_seconds: float = 0.5
    multiplier: float = 2.0
    max_delay_seconds: float = 5.0


class RetryExecutor:
    def __init__(self, policy: RetryPolicy):
        self.policy = policy

    async def run(self, operation_name: str, operation: Callable[[], Awaitable[T]]) -> T:
        delay = self.policy.initial_delay_seconds
        last_error: TransientExternalError | None = None
        for attempt in range(1, self.policy.max_attempts + 1):
            try:
                return await operation()
            except TransientExternalError as exc:
                last_error = exc
                if attempt == self.policy.max_attempts:
                    break
                if delay > 0:
                    await asyncio.sleep(delay)
                delay = min(delay * self.policy.multiplier, self.policy.max_delay_seconds)
        raise last_error or TransientExternalError(f"{operation_name} failed")
```

Create `src/workflow_engine/store.py`:

```python
from workflow_engine.domain import WorkflowRun


class RunNotFoundError(Exception):
    pass


class InMemoryRunStore:
    def __init__(self):
        self._runs: dict[str, WorkflowRun] = {}

    def save(self, run: WorkflowRun) -> WorkflowRun:
        self._runs[run.run_id] = run
        return run

    def get(self, run_id: str) -> WorkflowRun:
        try:
            return self._runs[run_id]
        except KeyError as exc:
            raise RunNotFoundError(run_id) from exc

    def list_runs(self) -> list[WorkflowRun]:
        return list(self._runs.values())
```

- [ ] **Step 5: Run tests and commit**

Run:

```bash
python3.13 -m pytest tests/test_retry.py tests/test_store.py -q
```

Expected: PASS.

Commit:

```bash
git add src/workflow_engine/retry.py src/workflow_engine/store.py tests/test_retry.py tests/test_store.py
git commit -m "feat: add retry executor and run store"
```

## Task 4: Mock API Tools

**Files:**
- Create: `src/workflow_engine/mock_api_client.py`
- Create: `src/workflow_engine/tools.py`
- Test: `tests/test_tools.py`

- [ ] **Step 1: Write failing tool contract tests**

Create `tests/test_tools.py`:

```python
from workflow_engine.tools import (
    CRMLookupTool,
    EmailSendTool,
    InquiryGetTool,
    ToolRegistry,
)
from workflow_engine.retry import RetryExecutor, RetryPolicy, TransientExternalError


class FakeMockApiClient:
    def __init__(self):
        self.sent_email = None

    async def get_inquiry(self, inquiry_id):
        return {
            "inquiry_id": inquiry_id,
            "from": "minsu.kim@example.com",
            "subject": "카드 결제가 계속 실패합니다",
            "body": "본문",
            "category": "billing",
            "status": "pending",
        }

    async def lookup_customer(self, email):
        return {"customer_id": "C001", "email": email, "name": "김민수", "plan": "Enterprise"}

    async def send_email(self, payload):
        self.sent_email = payload
        return {
            "message_id": "msg-123",
            "to": payload["to"],
            "status": "sent",
            "sent_at": "2026-04-26T00:00:00Z",
        }


async def test_inquiry_get_tool_returns_inquiry_output_shape():
    tool = InquiryGetTool(FakeMockApiClient())

    output = await tool.execute({"inquiry_id": "INQ-002"})

    assert output["inquiry"]["inquiry_id"] == "INQ-002"


async def test_crm_lookup_tool_returns_customer_output_shape():
    tool = CRMLookupTool(FakeMockApiClient())

    output = await tool.execute({"email": "minsu.kim@example.com"})

    assert output["customer"]["plan"] == "Enterprise"


async def test_email_send_tool_returns_delivery_result_without_body_duplication():
    client = FakeMockApiClient()
    tool = EmailSendTool(client)

    output = await tool.execute({
        "to": "minsu.kim@example.com",
        "subject": "Re: 카드 결제가 계속 실패합니다",
        "body": "안녕하세요",
    })

    assert output == {
        "message_id": "msg-123",
        "status": "sent",
        "to": "minsu.kim@example.com",
        "sent_at": "2026-04-26T00:00:00Z",
    }
    assert client.sent_email["body"] == "안녕하세요"


class FlakyEmailClient(FakeMockApiClient):
    def __init__(self):
        super().__init__()
        self.attempts = 0

    async def send_email(self, payload):
        self.attempts += 1
        if self.attempts < 3:
            raise TransientExternalError("temporary email outage")
        return await super().send_email(payload)


async def test_email_send_tool_retries_transient_failures():
    client = FlakyEmailClient()
    tool = EmailSendTool(
        client,
        retry_executor=RetryExecutor(RetryPolicy(max_attempts=3, initial_delay_seconds=0)),
    )

    output = await tool.execute({
        "to": "minsu.kim@example.com",
        "subject": "Re: 카드 결제가 계속 실패합니다",
        "body": "안녕하세요",
    })

    assert output["message_id"] == "msg-123"
    assert client.attempts == 3


def test_tool_registry_returns_registered_tools():
    registry = ToolRegistry({"inquiry_get": InquiryGetTool(FakeMockApiClient())})

    assert registry.get("inquiry_get").name == "inquiry_get"
```

- [ ] **Step 2: Run tests and verify failures**

Run:

```bash
python3.13 -m pytest tests/test_tools.py -q
```

Expected: FAIL with missing `workflow_engine.tools`.

- [ ] **Step 3: Implement Mock API client**

Create `src/workflow_engine/mock_api_client.py`:

```python
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

    async def _request(self, method: str, path: str, json: dict[str, Any] | None = None) -> dict[str, Any]:
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
```

- [ ] **Step 4: Implement tools and registry**

Create `src/workflow_engine/tools.py`:

```python
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
```

- [ ] **Step 5: Run tests and commit**

Run:

```bash
python3.13 -m pytest tests/test_tools.py -q
```

Expected: PASS.

Commit:

```bash
git add src/workflow_engine/mock_api_client.py src/workflow_engine/tools.py tests/test_tools.py
git commit -m "feat: add mock api tools"
```

## Task 5: LLM Tasks, Fake LLM, and OpenAI Adapter

**Files:**
- Create: `src/workflow_engine/policies.py`
- Create: `src/workflow_engine/llm.py`
- Test: `tests/test_llm.py`

- [ ] **Step 1: Write failing LLM tests**

Create `tests/test_llm.py`:

```python
import pytest

from workflow_engine.errors import WorkflowEngineError
from workflow_engine.llm import FakeLLMClient, LLMTaskRegistry, validate_category


def test_validate_category_accepts_assignment_categories():
    assert validate_category("billing") == "billing"


def test_validate_category_rejects_unknown_category():
    with pytest.raises(WorkflowEngineError):
        validate_category("sales")


async def test_fake_llm_classifies_from_subject_keywords():
    llm = FakeLLMClient()

    output = await llm.run_task("classify_email", {
        "subject": "카드 결제가 계속 실패합니다",
        "body": "결제 오류가 발생합니다",
    })

    assert output == {"category": "billing"}


async def test_fake_llm_generates_subject_and_body():
    llm = FakeLLMClient()

    output = await llm.run_task("generate_reply", {
        "inquiry": {"subject": "카드 결제가 계속 실패합니다"},
        "category": "billing",
        "customer": {"name": "김민수", "plan": "Enterprise"},
    })

    assert output["subject"] == "Re: 카드 결제가 계속 실패합니다"
    assert "김민수" in output["body"]
    assert "Enterprise" in output["body"]


def test_llm_task_registry_returns_client_task_runner():
    registry = LLMTaskRegistry(FakeLLMClient())

    assert registry.client.__class__.__name__ == "FakeLLMClient"
```

- [ ] **Step 2: Run tests and verify failures**

Run:

```bash
python3.13 -m pytest tests/test_llm.py -q
```

Expected: FAIL with missing `workflow_engine.llm`.

- [ ] **Step 3: Implement policy constants**

Create `src/workflow_engine/policies.py`:

```python
CATEGORIES = ["billing", "technical", "account", "feature_request", "general"]

CATEGORY_GUIDELINES = {
    "billing": "정중하고 신속하게 응답하며 예상 처리 기한과 접수 확인 번호를 포함한다.",
    "technical": "전문적이고 체계적으로 응답하며 문제 인지 여부와 예상 해결 일정을 포함한다.",
    "account": "보안 절차를 강조하고 예상 처리 시간을 포함한다.",
    "feature_request": "피드백에 감사하고 검토 예정과 가능한 대안을 안내한다.",
    "general": "친근하고 명확하게 답변하거나 적절한 안내 방향을 제시한다.",
}

PLAN_RULES = {
    "Enterprise": "전담 매니저 또는 엔지니어 연결과 우선 처리를 안내한다.",
    "Business": "일반 지원 채널과 순차 처리, 셀프서비스 가이드를 안내한다.",
    "Free": "공식 문서와 커뮤니티를 우선 안내하고 유료 플랜 혜택을 함께 안내한다.",
}

PROHIBITED_RULES = [
    "확인되지 않은 정보를 단정하지 않는다.",
    "구체적 금액을 직접 언급하지 않는다.",
    "타 고객 사례를 언급하지 않는다.",
    "내부 시스템 구조를 노출하지 않는다.",
    "보안 정책 우회 방법을 안내하지 않는다.",
    "확정되지 않은 출시 일정을 약속하지 않는다.",
    "경쟁사 제품과 비교하지 않는다.",
]
```

- [ ] **Step 4: Implement LLM clients**

Create `src/workflow_engine/llm.py`:

```python
import json
from typing import Any, Protocol

from openai import AsyncOpenAI

from workflow_engine.errors import WorkflowEngineError
from workflow_engine.policies import CATEGORIES, CATEGORY_GUIDELINES, PLAN_RULES, PROHIBITED_RULES


def validate_category(category: str) -> str:
    if category not in CATEGORIES:
        raise WorkflowEngineError(f"Invalid category from LLM: {category}")
    return category


class LLMClient(Protocol):
    async def run_task(self, task_name: str, input_data: dict[str, Any]) -> dict[str, Any]:
        pass


class LLMTaskRegistry:
    def __init__(self, client: LLMClient):
        self.client = client

    async def run(self, task_name: str, input_data: dict[str, Any]) -> dict[str, Any]:
        if task_name not in {"classify_email", "generate_reply"}:
            raise WorkflowEngineError(f"Unknown LLM task: {task_name}")
        return await self.client.run_task(task_name, input_data)


class FakeLLMClient:
    async def run_task(self, task_name: str, input_data: dict[str, Any]) -> dict[str, Any]:
        if task_name == "classify_email":
            return {"category": self._classify(input_data)}
        if task_name == "generate_reply":
            inquiry = input_data["inquiry"]
            customer = input_data["customer"]
            category = input_data["category"]
            subject = f"Re: {inquiry['subject']}"
            body = (
                f"안녕하세요 {customer.get('name', '고객')}님. "
                f"{customer.get('plan', '고객')} 플랜 문의를 확인했습니다. "
                f"{CATEGORY_GUIDELINES[category]}"
            )
            return {"subject": subject, "body": body}
        raise WorkflowEngineError(f"Unknown LLM task: {task_name}")

    def _classify(self, input_data: dict[str, Any]) -> str:
        text = f"{input_data.get('subject', '')} {input_data.get('body', '')}"
        if any(keyword in text for keyword in ["결제", "청구", "환불", "요금", "카드"]):
            return "billing"
        if any(keyword in text for keyword in ["API", "오류", "버그", "웹훅", "장애"]):
            return "technical"
        if any(keyword in text for keyword in ["계정", "비밀번호", "SSO", "권한", "로그인"]):
            return "account"
        if any(keyword in text for keyword in ["기능", "추가", "개선", "요청"]):
            return "feature_request"
        return "general"


class OpenAILLMClient:
    def __init__(self, api_key: str, model: str):
        self.client = AsyncOpenAI(api_key=api_key)
        self.model = model

    async def run_task(self, task_name: str, input_data: dict[str, Any]) -> dict[str, Any]:
        if task_name == "classify_email":
            return await self._classify_email(input_data)
        if task_name == "generate_reply":
            return await self._generate_reply(input_data)
        raise WorkflowEngineError(f"Unknown LLM task: {task_name}")

    async def _classify_email(self, input_data: dict[str, Any]) -> dict[str, Any]:
        prompt = (
            "다음 고객 문의를 billing, technical, account, feature_request, general 중 하나로 분류하고 "
            "JSON 형식으로만 응답하세요. 필요한 키는 category 하나입니다.\n"
            f"제목: {input_data['subject']}\n본문: {input_data['body']}"
        )
        parsed = await self._json_response(prompt)
        return {"category": validate_category(parsed["category"])}

    async def _generate_reply(self, input_data: dict[str, Any]) -> dict[str, Any]:
        category = input_data["category"]
        customer = input_data["customer"]
        inquiry = input_data["inquiry"]
        prompt = (
            "고객 문의 답변 초안을 JSON 형식으로만 작성하세요. 필요한 키는 subject, body입니다.\n"
            f"문의: {json.dumps(inquiry, ensure_ascii=False)}\n"
            f"고객: {json.dumps(customer, ensure_ascii=False)}\n"
            f"카테고리: {category}\n"
            f"응답 가이드라인: {CATEGORY_GUIDELINES[category]}\n"
            f"플랜 규칙: {PLAN_RULES.get(customer.get('plan', ''), '')}\n"
            f"금지 사항: {json.dumps(PROHIBITED_RULES, ensure_ascii=False)}"
        )
        parsed = await self._json_response(prompt)
        return {"subject": parsed["subject"], "body": parsed["body"]}

    async def _json_response(self, prompt: str) -> dict[str, Any]:
        response = await self.client.chat.completions.create(
            model=self.model,
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"},
        )
        content = response.choices[0].message.content or "{}"
        return json.loads(content)
```

- [ ] **Step 5: Run tests and commit**

Run:

```bash
python3.13 -m pytest tests/test_llm.py -q
```

Expected: PASS.

Commit:

```bash
git add src/workflow_engine/policies.py src/workflow_engine/llm.py tests/test_llm.py
git commit -m "feat: add llm task clients"
```

## Task 6: Workflow Executor Happy Path and Approval Pause

**Files:**
- Create: `src/workflow_engine/executor.py`
- Test: `tests/test_executor.py`

- [ ] **Step 1: Write failing executor happy-path test**

Create `tests/test_executor.py`:

```python
from pathlib import Path

from workflow_engine.domain import RunStatus
from workflow_engine.executor import WorkflowExecutor
from workflow_engine.llm import FakeLLMClient, LLMTaskRegistry
from workflow_engine.store import InMemoryRunStore
from workflow_engine.tools import CRMLookupTool, EmailSendTool, InquiryGetTool, ToolRegistry
from workflow_engine.workflow_loader import load_workflow


class FakeMockApiClient:
    def __init__(self):
        self.sent_payloads = []

    async def get_inquiry(self, inquiry_id):
        return {
            "inquiry_id": inquiry_id,
            "from": "minsu.kim@example.com",
            "subject": "카드 결제가 계속 실패합니다",
            "body": "결제 오류가 발생합니다",
            "category": "billing",
            "status": "pending",
        }

    async def lookup_customer(self, email):
        return {"customer_id": "C001", "email": email, "name": "김민수", "plan": "Enterprise"}

    async def send_email(self, payload):
        self.sent_payloads.append(payload)
        return {
            "message_id": "msg-123",
            "to": payload["to"],
            "status": "sent",
            "sent_at": "2026-04-26T00:00:00Z",
        }


def _executor(client):
    return WorkflowExecutor(
        store=InMemoryRunStore(),
        tool_registry=ToolRegistry({
            "inquiry_get": InquiryGetTool(client),
            "crm_lookup": CRMLookupTool(client),
            "email_send": EmailSendTool(client),
        }),
        llm_registry=LLMTaskRegistry(FakeLLMClient()),
    )


async def test_executor_runs_until_approval_and_stores_context():
    client = FakeMockApiClient()
    executor = _executor(client)
    workflow = load_workflow(Path("workflows/customer_support_auto_reply.yaml"))

    run = await executor.start(workflow, {"inquiry_id": "INQ-002"})

    assert run.status == RunStatus.WAITING_APPROVAL
    assert run.current_node_key == "wait_for_approval"
    assert run.context["nodes"]["classify_inquiry"] == {"category": "billing"}
    assert run.context["nodes"]["lookup_customer"]["customer"]["plan"] == "Enterprise"
    assert run.approval is not None
    assert client.sent_payloads == []
```

- [ ] **Step 2: Run test and verify failure**

Run:

```bash
python3.13 -m pytest tests/test_executor.py::test_executor_runs_until_approval_and_stores_context -q
```

Expected: FAIL with missing `workflow_engine.executor`.

- [ ] **Step 3: Implement executor start and node runners**

Create `src/workflow_engine/executor.py`:

```python
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from workflow_engine.domain import (
    ApprovalState,
    NodeState,
    NodeStatus,
    RunStatus,
    WorkflowDefinition,
    WorkflowErrorData,
    WorkflowNode,
    WorkflowRun,
)
from workflow_engine.errors import InputMappingError, WorkflowEngineError
from workflow_engine.input_mapping import render_inputs
from workflow_engine.store import InMemoryRunStore
from workflow_engine.tools import ToolRegistry
from workflow_engine.workflow_validator import topological_sort, validate_workflow


class WorkflowExecutor:
    def __init__(self, store: InMemoryRunStore, tool_registry: ToolRegistry, llm_registry):
        self.store = store
        self.tool_registry = tool_registry
        self.llm_registry = llm_registry

    async def start(self, workflow: WorkflowDefinition, input_data: dict) -> WorkflowRun:
        validate_workflow(workflow)
        now = datetime.now(timezone.utc)
        run = WorkflowRun(
            run_id=f"run_{uuid4().hex[:12]}",
            workflow_key=workflow.workflow_key,
            status=RunStatus.PENDING,
            current_node_key=None,
            context={"input": input_data, "nodes": {}},
            node_states={node.key: NodeState() for node in workflow.nodes},
            created_at=now,
            updated_at=now,
        )
        self.store.save(run)
        return await self._execute_from_order(workflow, run, topological_sort(workflow))

    async def _execute_from_order(
        self,
        workflow: WorkflowDefinition,
        run: WorkflowRun,
        order: list[str],
        start_after: str | None = None,
    ) -> WorkflowRun:
        node_by_key = {node.key: node for node in workflow.nodes}
        run.status = RunStatus.RUNNING
        skip = start_after is not None
        for node_key in order:
            if skip:
                if node_key == start_after:
                    skip = False
                continue
            node = node_by_key[node_key]
            if run.node_states[node.key].status == NodeStatus.COMPLETED:
                continue
            run.current_node_key = node.key
            run.node_states[node.key].status = NodeStatus.RUNNING
            run.node_states[node.key].attempts += 1
            run.updated_at = datetime.now(timezone.utc)
            self.store.save(run)

            try:
                result = await self._run_node(node, run)
            except Exception as exc:
                return self._fail_run(run, node.key, exc)

            if node.type == "human_approval":
                subject = result["subject"]
                body = result["body"]
                run.status = RunStatus.WAITING_APPROVAL
                run.node_states[node.key].status = NodeStatus.WAITING
                run.approval = ApprovalState(
                    node_key=node.key,
                    subject=subject,
                    body=body,
                    deadline_at=datetime.now(timezone.utc) + timedelta(seconds=node.timeout_seconds or 0),
                )
                run.updated_at = datetime.now(timezone.utc)
                return self.store.save(run)

            run.context["nodes"][node.key] = result
            run.node_states[node.key].status = NodeStatus.COMPLETED
            run.updated_at = datetime.now(timezone.utc)
            self.store.save(run)

        run.status = RunStatus.COMPLETED
        run.current_node_key = None
        run.updated_at = datetime.now(timezone.utc)
        return self.store.save(run)

    async def _run_node(self, node: WorkflowNode, run: WorkflowRun) -> dict:
        input_data = render_inputs(node.inputs, run.context)
        if node.type == "tool":
            return await self.tool_registry.get(node.tool or "").execute(input_data)
        if node.type == "llm":
            return await self.llm_registry.run(node.task or "", input_data)
        if node.type == "human_approval":
            return input_data
        raise WorkflowEngineError(f"Unsupported node type: {node.type}")

    def _fail_run(self, run: WorkflowRun, node_key: str, exc: Exception) -> WorkflowRun:
        message = str(exc)
        code = getattr(exc, "code", "NODE_EXECUTION_FAILED")
        error = WorkflowErrorData(code=code, message=message, node_key=node_key)
        run.status = RunStatus.FAILED
        run.error = error
        run.node_states[node_key].status = NodeStatus.FAILED
        run.node_states[node_key].error = error
        run.updated_at = datetime.now(timezone.utc)
        return self.store.save(run)
```

- [ ] **Step 4: Run test and commit**

Run:

```bash
python3.13 -m pytest tests/test_executor.py::test_executor_runs_until_approval_and_stores_context -q
```

Expected: PASS.

Commit:

```bash
git add src/workflow_engine/executor.py tests/test_executor.py
git commit -m "feat: execute workflow until approval"
```

## Task 7: Approval Resume, Reject, Timeout, and Send Failure

**Files:**
- Modify: `src/workflow_engine/executor.py`
- Modify: `tests/test_executor.py`

- [ ] **Step 1: Add failing approval and failure tests**

Append to `tests/test_executor.py`:

```python
from datetime import datetime, timedelta, timezone

from workflow_engine.domain import RunStatus
from workflow_engine.retry import TransientExternalError


async def test_approval_resumes_and_sends_email():
    client = FakeMockApiClient()
    executor = _executor(client)
    workflow = load_workflow(Path("workflows/customer_support_auto_reply.yaml"))
    run = await executor.start(workflow, {"inquiry_id": "INQ-002"})

    resumed = await executor.submit_approval(workflow, run.run_id, "approve")

    assert resumed.status == RunStatus.COMPLETED
    assert resumed.context["nodes"]["send_reply_email"]["message_id"] == "msg-123"
    assert client.sent_payloads[0]["to"] == "minsu.kim@example.com"


async def test_reject_marks_run_rejected_and_does_not_send_email():
    client = FakeMockApiClient()
    executor = _executor(client)
    workflow = load_workflow(Path("workflows/customer_support_auto_reply.yaml"))
    run = await executor.start(workflow, {"inquiry_id": "INQ-002"})

    rejected = await executor.submit_approval(workflow, run.run_id, "reject", "답변 부정확")

    assert rejected.status == RunStatus.REJECTED
    assert client.sent_payloads == []


async def test_expired_approval_marks_run_timed_out():
    client = FakeMockApiClient()
    executor = _executor(client)
    workflow = load_workflow(Path("workflows/customer_support_auto_reply.yaml"))
    run = await executor.start(workflow, {"inquiry_id": "INQ-002"})
    run.approval.deadline_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    executor.store.save(run)

    timed_out = await executor.submit_approval(workflow, run.run_id, "approve")

    assert timed_out.status == RunStatus.TIMED_OUT
    assert client.sent_payloads == []


class FailingEmailClient(FakeMockApiClient):
    async def send_email(self, payload):
        raise TransientExternalError("Email service temporarily unavailable")


async def test_send_email_failure_marks_node_and_run_failed():
    client = FailingEmailClient()
    executor = _executor(client)
    workflow = load_workflow(Path("workflows/customer_support_auto_reply.yaml"))
    run = await executor.start(workflow, {"inquiry_id": "INQ-002"})

    failed = await executor.submit_approval(workflow, run.run_id, "approve")

    assert failed.status == RunStatus.FAILED
    assert failed.current_node_key == "send_reply_email"
    assert failed.node_states["send_reply_email"].status == "FAILED"
    assert failed.error.node_key == "send_reply_email"
```

- [ ] **Step 2: Run tests and verify failures**

Run:

```bash
python3.13 -m pytest tests/test_executor.py -q
```

Expected: FAIL with missing `submit_approval`.

- [ ] **Step 3: Implement approval resume/reject/timeout**

Modify `src/workflow_engine/executor.py` by adding `submit_approval` to `WorkflowExecutor`:

```python
    async def submit_approval(
        self,
        workflow: WorkflowDefinition,
        run_id: str,
        decision: str,
        reason: str | None = None,
    ) -> WorkflowRun:
        run = self.store.get(run_id)
        if run.status != RunStatus.WAITING_APPROVAL or run.approval is None:
            return self._fail_run(run, run.current_node_key or "", WorkflowEngineError("Run is not waiting for approval"))

        now = datetime.now(timezone.utc)
        if now > run.approval.deadline_at:
            run.status = RunStatus.TIMED_OUT
            run.updated_at = now
            return self.store.save(run)

        run.approval.decision = decision
        run.approval.reason = reason
        run.approval.decided_at = now

        if decision == "reject":
            run.status = RunStatus.REJECTED
            run.updated_at = now
            return self.store.save(run)

        if decision != "approve":
            return self._fail_run(run, run.current_node_key or "", WorkflowEngineError(f"Unknown approval decision: {decision}"))

        approval_node = run.approval.node_key
        run.node_states[approval_node].status = NodeStatus.COMPLETED
        run.context["nodes"][approval_node] = {"decision": "approve", "decided_at": now.isoformat()}
        run.status = RunStatus.RUNNING
        run.updated_at = now
        self.store.save(run)
        return await self._execute_from_order(workflow, run, topological_sort(workflow), start_after=approval_node)
```

- [ ] **Step 4: Run tests and commit**

Run:

```bash
python3.13 -m pytest tests/test_executor.py -q
```

Expected: PASS.

Commit:

```bash
git add src/workflow_engine/executor.py tests/test_executor.py
git commit -m "feat: resume workflow after approval"
```

## Task 8: FastAPI API with Korean Swagger Documentation

**Files:**
- Create: `src/workflow_engine/config.py`
- Create: `src/workflow_engine/api.py`
- Create: `src/workflow_engine/main.py`
- Test: `tests/test_api.py`

- [ ] **Step 1: Write failing API tests**

Create `tests/test_api.py`:

```python
from fastapi.testclient import TestClient

from workflow_engine.api import create_app


def test_openapi_documentation_is_korean():
    app = create_app()
    client = TestClient(app)

    schema = client.get("/openapi.json").json()

    assert schema["info"]["title"] == "AI 워크플로우 실행 엔진"
    assert "워크플로우 실행" in schema["paths"]["/workflow-runs"]["post"]["summary"]


def test_start_workflow_endpoint_returns_run_waiting_for_approval():
    app = create_app(use_fake_dependencies=True)
    client = TestClient(app)

    response = client.post("/workflow-runs", json={
        "workflow_key": "customer_support_auto_reply",
        "inquiry_id": "INQ-002",
    })

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "WAITING_APPROVAL"
    assert body["current_node_key"] == "wait_for_approval"


def test_approval_endpoint_completes_run():
    app = create_app(use_fake_dependencies=True)
    client = TestClient(app)
    started = client.post("/workflow-runs", json={
        "workflow_key": "customer_support_auto_reply",
        "inquiry_id": "INQ-002",
    }).json()

    response = client.post(f"/workflow-runs/{started['run_id']}/approval", json={"decision": "approve"})

    assert response.status_code == 200
    assert response.json()["status"] == "COMPLETED"
```

- [ ] **Step 2: Run tests and verify failures**

Run:

```bash
python3.13 -m pytest tests/test_api.py -q
```

Expected: FAIL with missing `workflow_engine.api`.

- [ ] **Step 3: Implement config and API**

Create `src/workflow_engine/config.py`:

```python
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    mock_api_base_url: str = "http://localhost:8080"
    mock_api_key: str = "mock-api-key-12345"
    llm_provider: str = "fake"
    openai_api_key: str = ""
    openai_model: str = "gpt-4.1-mini"

    class Config:
        env_file = ".env"
```

Create `src/workflow_engine/api.py`:

```python
from pathlib import Path

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from workflow_engine.config import Settings
from workflow_engine.domain import WorkflowRun
from workflow_engine.executor import WorkflowExecutor
from workflow_engine.llm import FakeLLMClient, LLMTaskRegistry, OpenAILLMClient
from workflow_engine.mock_api_client import MockApiClient
from workflow_engine.retry import RetryExecutor, RetryPolicy
from workflow_engine.store import InMemoryRunStore, RunNotFoundError
from workflow_engine.tools import CRMLookupTool, EmailSendTool, InquiryGetTool, ToolRegistry
from workflow_engine.workflow_loader import load_workflow


class StartWorkflowRunRequest(BaseModel):
    workflow_key: str = Field(..., description="실행할 워크플로우 키")
    inquiry_id: str = Field(..., description="Mock Inquiry API에서 조회할 문의 ID")


class ApprovalDecisionRequest(BaseModel):
    decision: str = Field(..., description="승인 결정값. approve 또는 reject")
    reason: str | None = Field(default=None, description="거부 사유")


class LocalFakeMockApiClient:
    async def get_inquiry(self, inquiry_id):
        return {
            "inquiry_id": inquiry_id,
            "from": "minsu.kim@example.com",
            "subject": "카드 결제가 계속 실패합니다",
            "body": "결제 오류가 발생합니다",
            "category": "billing",
            "status": "pending",
        }

    async def lookup_customer(self, email):
        return {"customer_id": "C001", "email": email, "name": "김민수", "plan": "Enterprise"}

    async def send_email(self, payload):
        return {
            "message_id": "msg-123",
            "to": payload["to"],
            "status": "sent",
            "sent_at": "2026-04-26T00:00:00Z",
        }


def create_app(use_fake_dependencies: bool = False) -> FastAPI:
    app = FastAPI(
        title="AI 워크플로우 실행 엔진",
        description="고객 문의 자동 응답 워크플로우를 실행하고 승인 대기 상태를 관리하는 API입니다.",
        version="0.1.0",
    )
    settings = Settings()
    store = InMemoryRunStore()
    retry_executor = RetryExecutor(RetryPolicy())
    workflow_path = Path("workflows/customer_support_auto_reply.yaml")

    if use_fake_dependencies:
        mock_client = LocalFakeMockApiClient()
    else:
        mock_client = MockApiClient(settings.mock_api_base_url, settings.mock_api_key)

    if settings.llm_provider == "openai" and settings.openai_api_key:
        llm_client = OpenAILLMClient(settings.openai_api_key, settings.openai_model)
    else:
        llm_client = FakeLLMClient()

    executor = WorkflowExecutor(
        store=store,
        tool_registry=ToolRegistry({
            "inquiry_get": InquiryGetTool(mock_client, retry_executor),
            "crm_lookup": CRMLookupTool(mock_client, retry_executor),
            "email_send": EmailSendTool(mock_client, retry_executor),
        }),
        llm_registry=LLMTaskRegistry(llm_client),
    )

    @app.post(
        "/workflow-runs",
        response_model=WorkflowRun,
        summary="워크플로우 실행 시작",
        description="문의 ID를 입력받아 워크플로우를 승인 대기 단계까지 실행합니다.",
        tags=["워크플로우 실행"],
    )
    async def start_workflow_run(request: StartWorkflowRunRequest):
        workflow = load_workflow(workflow_path)
        return await executor.start(workflow, request.model_dump())

    @app.get(
        "/workflow-runs/{run_id}",
        response_model=WorkflowRun,
        summary="워크플로우 실행 상태 조회",
        description="실행 ID로 현재 상태, 컨텍스트, 노드 상태, 승인 정보를 조회합니다.",
        tags=["워크플로우 실행"],
    )
    async def get_workflow_run(run_id: str):
        try:
            return store.get(run_id)
        except RunNotFoundError as exc:
            raise HTTPException(status_code=404, detail="워크플로우 실행을 찾을 수 없습니다.") from exc

    @app.post(
        "/workflow-runs/{run_id}/approval",
        response_model=WorkflowRun,
        summary="승인 또는 거부 제출",
        description="승인 대기 중인 워크플로우에 approve 또는 reject 결정을 제출합니다.",
        tags=["승인"],
    )
    async def submit_approval(run_id: str, request: ApprovalDecisionRequest):
        workflow = load_workflow(workflow_path)
        return await executor.submit_approval(workflow, run_id, request.decision, request.reason)

    return app


app = create_app()
```

Create `src/workflow_engine/main.py`:

```python
import uvicorn


def main() -> None:
    uvicorn.run("workflow_engine.api:app", host="0.0.0.0", port=8000, reload=True)


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run tests and commit**

Run:

```bash
python3.13 -m pytest tests/test_api.py -q
```

Expected: PASS.

Commit:

```bash
git add src/workflow_engine/config.py src/workflow_engine/api.py src/workflow_engine/main.py tests/test_api.py
git commit -m "feat: expose workflow run api"
```

## Task 9: README, Full Test Run, and Manual Demo Path

**Files:**
- Create: `README.md`
- Modify: `src/workflow_engine/api.py` if final API wording needs Korean polishing.

- [ ] **Step 1: Write README**

Create `README.md`:

```markdown
# AI Workflow Builder Mini Engine

고객 문의 자동 응답 시나리오를 실행하는 미니 워크플로우 엔진입니다.

## 실행 환경

- Python 3.13
- Docker 및 Docker Compose
- Mock API 서버

## Mock API 서버 실행

```bash
cd mock-server
docker compose up --build
```

Mock 서버는 `http://localhost:8080`에서 실행됩니다.

## 워크플로우 엔진 설치

```bash
python3.13 -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev]"
```

## 환경 변수

```bash
cp .env.example .env
```

기본값은 Fake LLM을 사용합니다.

```bash
LLM_PROVIDER=fake
MOCK_API_BASE_URL=http://localhost:8080
MOCK_API_KEY=mock-api-key-12345
```

OpenAI를 사용하려면:

```bash
LLM_PROVIDER=openai
OPENAI_API_KEY=your-api-key
OPENAI_MODEL=gpt-4.1-mini
```

## API 서버 실행

```bash
python -m workflow_engine.main
```

Swagger 문서는 `http://localhost:8000/docs`에서 확인할 수 있습니다.

## 실행 예시

```bash
curl -X POST http://localhost:8000/workflow-runs \
  -H "Content-Type: application/json" \
  -d '{"workflow_key":"customer_support_auto_reply","inquiry_id":"INQ-002"}'
```

승인:

```bash
curl -X POST http://localhost:8000/workflow-runs/{run_id}/approval \
  -H "Content-Type: application/json" \
  -d '{"decision":"approve"}'
```

거부:

```bash
curl -X POST http://localhost:8000/workflow-runs/{run_id}/approval \
  -H "Content-Type: application/json" \
  -d '{"decision":"reject","reason":"답변 내용이 부정확함"}'
```

## 설계 요약

워크플로우는 YAML로 정의됩니다. `key`는 워크플로우 내부 참조명이고, `type`은 실행할 runner를 선택합니다. 재사용 단위는 `type + tool/task` 조합입니다. `depends_on`은 DAG 간선이며 실행 순서와 업무 의존성을 표현합니다.

노드 결과는 `context.nodes`에 저장되고 다음 노드는 input mapping으로 필요한 값을 참조합니다. Human approval 노드는 실행을 `WAITING_APPROVAL` 상태로 멈추고 승인 API 호출 후 남은 노드를 이어 실행합니다.

## 테스트

```bash
python -m pytest -q
```

자동 테스트는 네트워크와 비용 문제를 피하기 위해 Fake LLM을 사용합니다. OpenAI 연동은 환경 변수를 설정한 뒤 수동으로 확인합니다.

## 보안 고려사항

- 실제 OpenAI API Key는 커밋하지 않습니다.
- Mock API Key와 OpenAI API Key는 환경 변수로 주입합니다.
- 과제 MVP의 승인 API는 인증을 생략합니다.
- 운영 환경에서는 승인 API에 인증과 권한 검사가 필요합니다.

## 한계

- Run store는 in-memory입니다.
- 순차 실행만 지원합니다.
- 병렬 실행, 조건 분기, 시각적 빌더는 범위에서 제외했습니다.
```

- [ ] **Step 2: Run full tests**

Run:

```bash
python3.13 -m pytest -q
```

Expected: PASS for all tests.

- [ ] **Step 3: Run API smoke test with fake dependencies**

Run:

```bash
python3.13 -m uvicorn workflow_engine.api:app --app-dir src --port 8000
```

Expected: server starts at `http://127.0.0.1:8000`.

In another terminal:

```bash
curl -s http://localhost:8000/openapi.json
```

Expected: JSON contains `"title":"AI 워크플로우 실행 엔진"`.

- [ ] **Step 4: Commit docs and final polish**

Commit:

```bash
git add README.md src/workflow_engine/api.py
git commit -m "docs: add workflow engine usage guide"
```

## Self-Review Checklist

- Spec coverage:
  - YAML workflow definition: Task 1.
  - DAG validation and cycle detection: Task 2.
  - Sequential execution and context passing: Task 6.
  - Retry for transient failures: Task 3 and Task 7.
  - Tool interface and Mock API tools: Task 4.
  - LLM task abstraction and fake/OpenAI clients: Task 5.
  - Human approval pause/resume/reject/timeout: Task 6 and Task 7.
  - Korean Swagger docs: Task 8.
  - Unit tests: Tasks 1-8.
  - README: Task 9.
- Placeholder scan: no unspecified implementation slots remain.
- Type consistency:
  - Node key field is `key`.
  - Current run field is `current_node_key`.
  - Workflow field is `workflow_key`.
  - Approval decision values are `approve` and `reject`.
  - Tool names are `inquiry_get`, `crm_lookup`, `email_send`.
  - LLM task names are `classify_email`, `generate_reply`.

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-04-26-mini-workflow-engine.md`. Two execution options:

1. **Subagent-Driven (recommended)** - dispatch a fresh subagent per task, review between tasks, fast iteration.
2. **Inline Execution** - execute tasks in this session using executing-plans, batch execution with checkpoints.

Which approach?
