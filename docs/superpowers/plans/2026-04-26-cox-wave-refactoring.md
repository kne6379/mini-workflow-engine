# Cox-Wave Workflow Engine Refactoring Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 기존 MVP 워크플로우 엔진을 디렉토리 재구조화 + 능동 타임아웃 + run-level 락 + 시작 멱등성 + LLM 출력 검증 + 프롬프트 분리 + 액션 기반 LLM 레지스트리 + bootstrap 분리로 정돈한다.

**Architecture:** 5개 폴더(api/domain/engine/nodes/adapters) + 최상위 `app.py`/`bootstrap.py`/`main.py`/`config.py`. 의존 방향 단방향(api→bootstrap→engine+nodes+adapters→domain). 능동 타임아웃은 per-run `asyncio.Task`. 멱등성은 `inquiry_id` 자연 키.

**Tech Stack:** Python 3.13, FastAPI 0.115, Pydantic 2.9, httpx 0.27, openai 1.59, pytest 8.3 (asyncio_mode=auto), uvicorn 0.30.

**Spec:** `docs/superpowers/specs/2026-04-26-cox-wave-refactoring-design.md`

---

## File Structure (최종 모습)

```
src/workflow_engine/
├── main.py
├── app.py
├── bootstrap.py
├── config.py
├── api/
│   ├── __init__.py
│   ├── routes.py
│   └── schemas.py
├── domain/
│   ├── __init__.py
│   ├── workflow.py
│   ├── run.py
│   ├── reply_policy.py
│   └── errors.py
├── engine/
│   ├── __init__.py
│   ├── executor.py
│   ├── validator.py
│   ├── loader.py
│   ├── input_mapping.py
│   ├── retry.py
│   ├── ports.py
│   ├── registries.py
│   └── approval_timer.py
├── nodes/
│   ├── __init__.py
│   ├── tools.py
│   ├── llm.py
│   └── prompts.py
└── adapters/
    ├── __init__.py
    ├── openai.py
    ├── fake_ai.py
    ├── mock_api.py
    └── run_store.py

tests/
├── conftest.py
├── test_input_mapping.py
├── test_validator.py
├── test_retry.py
├── test_loader.py
├── test_run_store.py
├── test_tools.py
├── test_mock_api_adapter.py
├── test_openai_adapter.py
├── test_fake_ai.py
├── test_prompts.py
├── test_llm_tasks.py
├── test_ai_registry.py
├── test_approval_timer.py
├── test_executor.py
├── test_idempotency.py
└── test_api.py
```

각 task는 독립 commit. import 갱신은 매 task 내부에서 처리한다.

---

## Phase 1 — 디렉토리 재구조화 + 명명 정정

각 task는 "파일 이동 + import 갱신 + 테스트 통과 확인". 한 번에 한 파일만 옮긴다 (대량 이동 시 import 깨짐 추적 어려움).

---

### Task 1: domain/ 폴더 생성 + domain.py 분할

**Files:**
- Create: `src/workflow_engine/domain/__init__.py` (empty)
- Create: `src/workflow_engine/domain/workflow.py`
- Create: `src/workflow_engine/domain/run.py`
- Delete: `src/workflow_engine/domain.py`

- [ ] **Step 1: 새 파일 `domain/__init__.py` 생성 (빈 파일)**

```bash
mkdir -p src/workflow_engine/domain
touch src/workflow_engine/domain/__init__.py
```

- [ ] **Step 2: `domain/workflow.py` 작성**

```python
from typing import Any, Literal
from pydantic import BaseModel, Field


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
```

- [ ] **Step 3: `domain/run.py` 작성**

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

- [ ] **Step 4: 기존 `src/workflow_engine/domain.py` 삭제**

```bash
rm src/workflow_engine/domain.py
```

- [ ] **Step 5: 모든 import 갱신**

치환 (모든 src + tests 파일에서):
- `from workflow_engine.domain import` → 분할 후 적절한 모듈로 분기:
  - `WorkflowNode`, `WorkflowDefinition` → `from workflow_engine.domain.workflow import ...`
  - `RunStatus`, `NodeStatus`, `NodeType`, `NodeState`, `ApprovalState`, `WorkflowRun`, `WorkflowErrorData` → `from workflow_engine.domain.run import ...`

영향 파일:
- `src/workflow_engine/engine/executor.py`
- `src/workflow_engine/engine/workflow_validator.py`
- `src/workflow_engine/engine/workflow_loader.py`
- `src/workflow_engine/api.py`
- `src/workflow_engine/adapters/run_store.py`
- `src/workflow_engine/ports.py`
- `tests/test_executor.py`

- [ ] **Step 6: 전체 테스트 통과 확인**

```bash
python -m pytest -q
```

Expected: 모든 테스트 PASS (로직 변경 없으므로 기존 테스트 그대로 통과해야 함).

- [ ] **Step 7: Commit**

```bash
git add src/workflow_engine/domain src/workflow_engine/engine tests
git rm src/workflow_engine/domain.py
git commit -m "refactor: split domain.py into domain/{workflow,run}.py"
```

---

### Task 2: errors.py → domain/errors.py

**Files:**
- Create: `src/workflow_engine/domain/errors.py`
- Delete: `src/workflow_engine/errors.py`

- [ ] **Step 1: `domain/errors.py` 작성**

```python
class WorkflowEngineError(Exception):
    code = "WORKFLOW_ENGINE_ERROR"


class WorkflowValidationError(WorkflowEngineError):
    code = "WORKFLOW_VALIDATION_ERROR"


class InputMappingError(WorkflowEngineError):
    code = "INPUT_MAPPING_ERROR"
```

- [ ] **Step 2: 기존 `src/workflow_engine/errors.py` 삭제**

```bash
rm src/workflow_engine/errors.py
```

- [ ] **Step 3: 모든 import 갱신**

치환: `from workflow_engine.errors import` → `from workflow_engine.domain.errors import`

영향 파일:
- `src/workflow_engine/engine/executor.py`
- `src/workflow_engine/engine/workflow_validator.py`
- `src/workflow_engine/engine/input_mapping.py`
- `src/workflow_engine/registries.py`
- `src/workflow_engine/adapters/ai.py`
- `src/workflow_engine/api.py`
- 모든 test 파일에서 `errors` 사용처

- [ ] **Step 4: 전체 테스트 통과**

```bash
python -m pytest -q
```

- [ ] **Step 5: Commit**

```bash
git add src/workflow_engine/domain/errors.py
git rm src/workflow_engine/errors.py
git commit -m "refactor: move errors.py to domain/errors.py"
```

---

### Task 3: policies.py → domain/reply_policy.py

**Files:**
- Create: `src/workflow_engine/domain/reply_policy.py`
- Delete: `src/workflow_engine/policies.py`

- [ ] **Step 1: `domain/reply_policy.py` 작성** (현 policies.py 내용 그대로)

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

(REQUIRED_INCLUDES, CATEGORY_TONE은 Phase 2의 Task 9에서 추가한다.)

- [ ] **Step 2: 기존 `src/workflow_engine/policies.py` 삭제**

```bash
rm src/workflow_engine/policies.py
```

- [ ] **Step 3: import 갱신**

치환: `from workflow_engine.policies import` → `from workflow_engine.domain.reply_policy import`

영향 파일:
- `src/workflow_engine/adapters/ai.py`

- [ ] **Step 4: 테스트 통과**

```bash
python -m pytest -q
```

- [ ] **Step 5: Commit**

```bash
git add src/workflow_engine/domain/reply_policy.py
git rm src/workflow_engine/policies.py
git commit -m "refactor: move policies.py to domain/reply_policy.py"
```

---

### Task 4: ports.py → engine/ports.py

**Files:**
- Move: `src/workflow_engine/ports.py` → `src/workflow_engine/engine/ports.py`

- [ ] **Step 1: 파일 이동 (내용 그대로 유지)**

```bash
git mv src/workflow_engine/ports.py src/workflow_engine/engine/ports.py
```

- [ ] **Step 2: `engine/ports.py` 안의 import 경로 보정**

```python
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
```

(`AI` 프로토콜의 `run_task` 시그니처는 Phase 2의 Task 12에서 `chat_json`으로 바꾼다.)

- [ ] **Step 3: 모든 import 갱신**

치환: `from workflow_engine.ports import` → `from workflow_engine.engine.ports import`

영향 파일:
- `src/workflow_engine/adapters/run_store.py`
- `src/workflow_engine/registries.py`
- `src/workflow_engine/tools.py`

- [ ] **Step 4: 테스트 통과**

```bash
python -m pytest -q
```

- [ ] **Step 5: Commit**

```bash
git add src/workflow_engine/engine/ports.py
git rm src/workflow_engine/ports.py
git commit -m "refactor: move ports.py to engine/ports.py"
```

---

### Task 5: registries.py → engine/registries.py

**Files:**
- Move: `src/workflow_engine/registries.py` → `src/workflow_engine/engine/registries.py`

- [ ] **Step 1: 파일 이동 + import 보정**

```bash
git mv src/workflow_engine/registries.py src/workflow_engine/engine/registries.py
```

내부 import:
```python
from typing import Any

from workflow_engine.domain.errors import WorkflowEngineError
from workflow_engine.engine.ports import AI, Tool


class ToolRegistry:
    def __init__(self, tools: dict[str, Tool]):
        self._tools = tools

    def get(self, name: str) -> Tool:
        try:
            return self._tools[name]
        except KeyError as exc:
            raise KeyError(f"Unknown tool: {name}") from exc


class AITaskRegistry:
    def __init__(self, ai: AI):
        self.ai = ai

    async def run(self, task_name: str, input_data: dict[str, Any]) -> dict[str, Any]:
        if task_name not in {"classify_email", "generate_reply"}:
            raise WorkflowEngineError(f"Unknown AI task: {task_name}")
        return await self.ai.run_task(task_name, input_data)
```

(이 클래스는 Phase 2의 Task 16에서 `tasks` + `profiles` 두 dict 형태로 바뀐다.)

- [ ] **Step 2: import 갱신**

치환: `from workflow_engine.registries import` → `from workflow_engine.engine.registries import`

영향 파일:
- `src/workflow_engine/engine/executor.py`
- `src/workflow_engine/api.py`
- `tests/test_tools.py`, `tests/test_ai.py`

- [ ] **Step 3: 테스트 통과**

```bash
python -m pytest -q
```

- [ ] **Step 4: Commit**

```bash
git add src/workflow_engine/engine/registries.py
git rm src/workflow_engine/registries.py
git commit -m "refactor: move registries.py to engine/registries.py"
```

---

### Task 6: tools.py → nodes/tools.py

**Files:**
- Create: `src/workflow_engine/nodes/__init__.py`
- Move: `src/workflow_engine/tools.py` → `src/workflow_engine/nodes/tools.py`

- [ ] **Step 1: nodes 디렉토리 생성**

```bash
mkdir -p src/workflow_engine/nodes
touch src/workflow_engine/nodes/__init__.py
```

- [ ] **Step 2: 파일 이동 + import 보정**

```bash
git mv src/workflow_engine/tools.py src/workflow_engine/nodes/tools.py
```

내부 import 갱신:
```python
from typing import Any

from workflow_engine.engine.ports import CustomerLookup, EmailSender, InquiryReader
from workflow_engine.engine.retry import RetryExecutor


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
```

- [ ] **Step 3: import 갱신**

치환: `from workflow_engine.tools import` → `from workflow_engine.nodes.tools import`

영향 파일:
- `src/workflow_engine/api.py`
- `tests/test_tools.py`

- [ ] **Step 4: 테스트 통과**

```bash
python -m pytest -q
```

- [ ] **Step 5: Commit**

```bash
git add src/workflow_engine/nodes
git rm src/workflow_engine/tools.py
git commit -m "refactor: move tools.py to nodes/tools.py"
```

---

### Task 7: engine/workflow_validator.py → engine/validator.py + engine/workflow_loader.py → engine/loader.py

**Files:**
- Move: `src/workflow_engine/engine/workflow_validator.py` → `src/workflow_engine/engine/validator.py`
- Move: `src/workflow_engine/engine/workflow_loader.py` → `src/workflow_engine/engine/loader.py`

- [ ] **Step 1: 두 파일 이동**

```bash
git mv src/workflow_engine/engine/workflow_validator.py src/workflow_engine/engine/validator.py
git mv src/workflow_engine/engine/workflow_loader.py src/workflow_engine/engine/loader.py
```

- [ ] **Step 2: 두 파일 내부 import 보정**

`engine/validator.py`:
```python
from collections import deque

from workflow_engine.domain.errors import WorkflowValidationError
from workflow_engine.domain.workflow import WorkflowDefinition, WorkflowNode

# (기존 함수 본문 그대로 — validate_workflow, topological_sort,
#  _validate_unique_node_keys, _validate_node_required_fields)
```

`engine/loader.py`:
```python
from pathlib import Path

import yaml

from workflow_engine.domain.workflow import WorkflowDefinition


def load_workflow(path: Path) -> WorkflowDefinition:
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    return WorkflowDefinition.model_validate(raw)
```

- [ ] **Step 3: 모든 import 갱신**

치환:
- `from workflow_engine.engine.workflow_validator import` → `from workflow_engine.engine.validator import`
- `from workflow_engine.engine.workflow_loader import` → `from workflow_engine.engine.loader import`

영향 파일:
- `src/workflow_engine/engine/executor.py`
- `src/workflow_engine/api.py`
- `tests/test_workflow_validator.py` (파일명도 추후 정리)
- `tests/test_executor.py`

- [ ] **Step 4: 테스트 파일도 개명**

```bash
git mv tests/test_workflow_validator.py tests/test_validator.py
```

- [ ] **Step 5: 테스트 통과**

```bash
python -m pytest -q
```

- [ ] **Step 6: Commit**

```bash
git add src/workflow_engine/engine tests/test_validator.py
git commit -m "refactor: rename workflow_validator to validator, workflow_loader to loader"
```

---

### Task 8: adapters/mock_server.py → adapters/mock_api.py + adapters/ai.py 분할

**Files:**
- Move: `src/workflow_engine/adapters/mock_server.py` → `src/workflow_engine/adapters/mock_api.py`
- Split: `src/workflow_engine/adapters/ai.py` → `src/workflow_engine/adapters/openai.py` + `src/workflow_engine/adapters/fake_ai.py`
- Rename test file: `tests/test_mock_server_adapter.py` → `tests/test_mock_api_adapter.py`

- [ ] **Step 1: mock_server.py 이동 + 클래스 개명**

```bash
git mv src/workflow_engine/adapters/mock_server.py src/workflow_engine/adapters/mock_api.py
```

`adapters/mock_api.py` 안에서 클래스명 `MockServerAdapter` → `MockAPIAdapter`, `FakeMockServerAdapter` → `FakeMockAPIAdapter`.

```python
from typing import Any

import httpx

from workflow_engine.engine.retry import PermanentExternalError, TransientExternalError


class MockAPIAdapter:
    def __init__(self, base_url: str, api_key: str):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key

    async def get_inquiry(self, inquiry_id: str) -> dict[str, Any]:
        return await self._request("GET", f"/api/inquiries/{inquiry_id}")

    async def lookup_customer(self, email: str) -> dict[str, Any]:
        return await self._request("POST", "/api/crm/lookup", json={"email": email})

    async def send_email(self, payload: dict[str, Any]) -> dict[str, Any]:
        return await self._request("POST", "/api/email/send", json=payload)

    async def _request(self, method, path, json=None):
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


class FakeMockAPIAdapter:
    async def get_inquiry(self, inquiry_id: str) -> dict[str, Any]:
        return {
            "inquiry_id": inquiry_id,
            "from": "minsu.kim@example.com",
            "subject": "카드 결제가 계속 실패합니다",
            "body": "결제 오류가 발생합니다",
            "category": "billing",
            "status": "pending",
        }

    async def lookup_customer(self, email: str) -> dict[str, Any]:
        return {"customer_id": "C001", "email": email, "name": "김민수", "plan": "Enterprise"}

    async def send_email(self, payload: dict[str, Any]) -> dict[str, Any]:
        return {
            "message_id": "msg-123",
            "to": payload["to"],
            "status": "sent",
            "sent_at": "2026-04-26T00:00:00Z",
        }
```

- [ ] **Step 2: `adapters/ai.py`를 `openai.py` + `fake_ai.py`로 분할**

`adapters/openai.py` (현 ai.py의 OpenAIAdapter + validate_category):
```python
import json
from typing import Any

from openai import AsyncOpenAI

from workflow_engine.domain.errors import WorkflowEngineError
from workflow_engine.domain.reply_policy import (
    CATEGORIES, CATEGORY_GUIDELINES, PLAN_RULES, PROHIBITED_RULES,
)


def validate_category(category: str) -> str:
    if category not in CATEGORIES:
        raise WorkflowEngineError(f"Invalid category from AI: {category}")
    return category


class OpenAIAdapter:
    def __init__(self, api_key: str, model: str):
        self.client = AsyncOpenAI(api_key=api_key)
        self.model = model

    async def run_task(self, task_name: str, input_data: dict[str, Any]) -> dict[str, Any]:
        if task_name == "classify_email":
            return await self._classify_email(input_data)
        if task_name == "generate_reply":
            return await self._generate_reply(input_data)
        raise WorkflowEngineError(f"Unknown AI task: {task_name}")

    async def _classify_email(self, input_data):
        prompt = (
            "다음 고객 문의를 billing, technical, account, feature_request, general 중 하나로 분류하고 "
            "JSON 형식으로만 응답하세요. 필요한 키는 category 하나입니다.\n"
            f"제목: {input_data['subject']}\n본문: {input_data['body']}"
        )
        parsed = await self._json_response(prompt)
        return {"category": validate_category(parsed["category"])}

    async def _generate_reply(self, input_data):
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

    async def _json_response(self, prompt):
        response = await self.client.chat.completions.create(
            model=self.model,
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"},
        )
        return json.loads(response.choices[0].message.content or "{}")
```

(시그니처는 Phase 2의 Task 13/14에서 chat_json으로 바뀐다.)

`adapters/fake_ai.py`:
```python
from typing import Any

from workflow_engine.domain.errors import WorkflowEngineError
from workflow_engine.domain.reply_policy import CATEGORY_GUIDELINES


class FakeAIAdapter:
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
        raise WorkflowEngineError(f"Unknown AI task: {task_name}")

    def _classify(self, input_data):
        text = f"{input_data.get('subject', '')} {input_data.get('body', '')}"
        if any(k in text for k in ["결제", "청구", "환불", "요금", "카드"]):
            return "billing"
        if any(k in text for k in ["API", "오류", "버그", "웹훅", "장애"]):
            return "technical"
        if any(k in text for k in ["계정", "비밀번호", "SSO", "권한", "로그인"]):
            return "account"
        if any(k in text for k in ["기능", "추가", "개선", "요청"]):
            return "feature_request"
        return "general"
```

(이 어댑터는 Phase 2의 Task 13에서 `FakeAI(response)` 구조로 완전히 교체된다. Task 8에서는 위치만 옮기고 동작은 유지.)

- [ ] **Step 3: 기존 `adapters/ai.py` 삭제**

```bash
rm src/workflow_engine/adapters/ai.py
```

- [ ] **Step 4: import 갱신**

치환:
- `from workflow_engine.adapters.mock_server import MockServerAdapter` → `from workflow_engine.adapters.mock_api import MockAPIAdapter`
- `FakeMockServerAdapter` → `FakeMockAPIAdapter`
- `from workflow_engine.adapters.ai import OpenAIAdapter` → `from workflow_engine.adapters.openai import OpenAIAdapter`
- `from workflow_engine.adapters.ai import FakeAIAdapter` → `from workflow_engine.adapters.fake_ai import FakeAIAdapter`
- `from workflow_engine.adapters.ai import validate_category` → `from workflow_engine.adapters.openai import validate_category`

영향 파일:
- `src/workflow_engine/api.py`
- `tests/test_ai.py`
- `tests/test_mock_server_adapter.py`
- `tests/test_executor.py`

- [ ] **Step 5: 테스트 파일 개명**

```bash
git mv tests/test_mock_server_adapter.py tests/test_mock_api_adapter.py
```

- [ ] **Step 6: 테스트 통과**

```bash
python -m pytest -q
```

- [ ] **Step 7: Commit**

```bash
git add src/workflow_engine/adapters tests
git rm src/workflow_engine/adapters/ai.py
git commit -m "refactor: split adapters/ai.py into openai.py and fake_ai.py; rename mock_server to mock_api"
```

---

### Task 9: Phase 1 마무리 검증

- [ ] **Step 1: 전체 테스트 통과**

```bash
python -m pytest -q
```

Expected: 모든 기존 테스트 PASS.

- [ ] **Step 2: 서버 기동 + 정상 동작 확인**

```bash
python -m workflow_engine.main &
SERVER_PID=$!
sleep 2

curl -s -X POST http://localhost:8000/workflow-runs \
  -H "Content-Type: application/json" \
  -d '{"workflow_key":"customer_support_auto_reply","inquiry_id":"INQ-002"}' | python -m json.tool

kill $SERVER_PID
```

Expected: status `WAITING_APPROVAL`, current_node_key `wait_for_approval`.

- [ ] **Step 3: tag 또는 별도 commit 없음 — Phase 1 작업이 모두 commit된 상태로 끝나면 OK**

---

## Phase 2 — 액션 기반 LLM 레지스트리 + 프롬프트 분리 + 출력 검증

---

### Task 10: domain/reply_policy.py에 REQUIRED_INCLUDES, CATEGORY_TONE 추가

**Files:**
- Modify: `src/workflow_engine/domain/reply_policy.py`

- [ ] **Step 1: reply_policy.py 끝에 추가**

```python
REQUIRED_INCLUDES = {
    "billing": ["예상 처리 기한", "접수 확인 번호"],
    "technical": ["문제 인지 여부", "예상 해결 일정"],
    "account": ["보안 절차 안내", "예상 처리 시간"],
    "feature_request": ["피드백 감사", "검토 예정 안내"],
    "general": [],
}

CATEGORY_TONE = {
    "billing": "정중하고 신속",
    "technical": "전문적이고 체계적",
    "account": "보안을 강조하며 친절",
    "feature_request": "감사와 공감",
    "general": "친근하고 도움이 되는",
}
```

- [ ] **Step 2: 테스트 통과 (영향 없음 확인)**

```bash
python -m pytest -q
```

- [ ] **Step 3: Commit**

```bash
git add src/workflow_engine/domain/reply_policy.py
git commit -m "feat: add REQUIRED_INCLUDES and CATEGORY_TONE to reply policy"
```

---

### Task 11: domain/errors.py에 LLMOutputValidationError 추가

**Files:**
- Modify: `src/workflow_engine/domain/errors.py`

- [ ] **Step 1: errors.py 끝에 추가**

```python
class LLMOutputValidationError(WorkflowEngineError):
    code = "LLM_OUTPUT_VALIDATION_ERROR"


class ApprovalTimeoutError(WorkflowEngineError):
    code = "APPROVAL_TIMEOUT"
```

- [ ] **Step 2: 테스트 통과**

```bash
python -m pytest -q
```

- [ ] **Step 3: Commit**

```bash
git add src/workflow_engine/domain/errors.py
git commit -m "feat: add LLMOutputValidationError and ApprovalTimeoutError"
```

---

### Task 12: nodes/prompts.py 신설 + render_template 함수

**Files:**
- Create: `src/workflow_engine/nodes/prompts.py`
- Create: `tests/test_prompts.py`

- [ ] **Step 1: 실패하는 테스트 작성 (`tests/test_prompts.py`)**

```python
import pytest

from workflow_engine.domain.errors import InputMappingError
from workflow_engine.nodes.prompts import render_template


def test_render_template_replaces_single_placeholder():
    result = render_template("Hello {{ name }}!", {"name": "Alice"})
    assert result == "Hello Alice!"


def test_render_template_handles_nested_path():
    result = render_template(
        "Plan: {{ customer.plan }}",
        {"customer": {"plan": "Enterprise"}},
    )
    assert result == "Plan: Enterprise"


def test_render_template_replaces_multiple_occurrences():
    result = render_template("{{ x }} and {{ x }}", {"x": "yes"})
    assert result == "yes and yes"


def test_render_template_raises_on_missing_path():
    with pytest.raises(InputMappingError):
        render_template("Hello {{ unknown }}!", {})
```

- [ ] **Step 2: 테스트 실패 확인**

```bash
python -m pytest tests/test_prompts.py -v
```

Expected: FAIL with import error or `render_template not defined`.

- [ ] **Step 3: nodes/prompts.py 작성**

```python
from typing import Any

from workflow_engine.engine.input_mapping import render_inputs


def render_template(template: str, context: dict[str, Any]) -> str:
    """input_mapping의 {{ ... }} 렌더링을 prompt 템플릿에 재사용."""
    return render_inputs({"_": template}, context)["_"]


CLASSIFY_SYSTEM = (
    "당신은 고객 문의 메일을 5개 카테고리 중 하나로 분류하는 도우미입니다. "
    "billing, technical, account, feature_request, general 중에서만 고르고, "
    "JSON 형식으로 {\"category\": \"<카테고리>\"} 만 반환하세요."
)
CLASSIFY_USER_TEMPLATE = "제목: {{ subject }}\n본문: {{ body }}"

GENERATE_SYSTEM_TEMPLATE = (
    "당신은 고객 지원 이메일 답변 초안을 작성하는 도우미입니다.\n"
    "응답 톤: {{ tone }}\n"
    "응답 가이드라인: {{ guideline }}\n"
    "고객 플랜 규칙: {{ plan_rule }}\n"
    "필수 포함 항목: {{ required_includes }}\n"
    "금지 사항:\n{{ prohibited }}\n"
    "출력 형식: JSON 객체로만 응답하세요. 키는 subject, body 두 개입니다."
)
GENERATE_USER_TEMPLATE = (
    "문의 제목: {{ inquiry.subject }}\n"
    "문의 본문: {{ inquiry.body }}\n"
    "분류 카테고리: {{ category }}\n"
    "고객 정보: 이름 {{ customer.name }}, 플랜 {{ customer.plan }}, 상태 {{ customer.status }}"
)
```

- [ ] **Step 4: 테스트 통과 확인**

```bash
python -m pytest tests/test_prompts.py -v
```

Expected: 4개 테스트 PASS.

- [ ] **Step 5: Commit**

```bash
git add src/workflow_engine/nodes/prompts.py tests/test_prompts.py
git commit -m "feat: add nodes/prompts.py with render_template and message templates"
```

---

### Task 13: engine/ports.AI 시그니처 변경 + adapters/fake_ai.py FakeAI 클래스

**Files:**
- Modify: `src/workflow_engine/engine/ports.py`
- Replace: `src/workflow_engine/adapters/fake_ai.py`
- Create: `tests/test_fake_ai.py`

- [ ] **Step 1: ports.AI 시그니처 변경**

`engine/ports.py`의 `AI` 클래스를 다음으로 교체:

```python
class AI(Protocol):
    async def chat_json(self, system: str, user: str) -> dict[str, Any]: ...
```

- [ ] **Step 2: `adapters/fake_ai.py`를 새 구조로 교체**

```python
from typing import Any


class FakeAI:
    """Test용 결정적 응답 어댑터.
    
    각 호출마다 미리 등록된 단일 응답을 반환한다. system/user prompt도 보관해
    테스트가 prompt 내용을 단언할 수 있다.
    """

    def __init__(self, response: dict[str, Any]):
        self._response = response
        self.last_system: str | None = None
        self.last_user: str | None = None

    async def chat_json(self, system: str, user: str) -> dict[str, Any]:
        self.last_system = system
        self.last_user = user
        return self._response
```

- [ ] **Step 3: `tests/test_fake_ai.py` 작성**

```python
from workflow_engine.adapters.fake_ai import FakeAI


async def test_fake_ai_returns_registered_response():
    ai = FakeAI({"category": "billing"})
    result = await ai.chat_json(system="sys", user="user")
    assert result == {"category": "billing"}


async def test_fake_ai_records_last_system_and_user():
    ai = FakeAI({"x": 1})
    await ai.chat_json(system="hello", user="world")
    assert ai.last_system == "hello"
    assert ai.last_user == "world"
```

- [ ] **Step 4: 기존 `tests/test_ai.py` 삭제**

```bash
git rm tests/test_ai.py
```

(이 파일은 옛 `FakeAIAdapter.run_task` 동작을 검증함. 새 구조에서는 의미 없음.)

- [ ] **Step 5: 테스트 통과**

```bash
python -m pytest tests/test_fake_ai.py tests/test_prompts.py -v
```

Expected: PASS.

(주의: 이 시점에서 `OpenAIAdapter`와 기존 `FakeAIAdapter`를 사용하는 다른 테스트들은 일시적으로 깨진다. Task 14, 15에서 복구한다. Task 13만 단독으로 `pytest -q` 돌리면 다수 FAIL — 이건 의도된 중간 상태.)

- [ ] **Step 6: Commit**

```bash
git add src/workflow_engine/engine/ports.py src/workflow_engine/adapters/fake_ai.py tests/test_fake_ai.py
git rm tests/test_ai.py
git commit -m "feat: change AI Protocol to chat_json; replace FakeAIAdapter with FakeAI"
```

---

### Task 14: adapters/openai.py를 chat_json 시그니처로 교체

**Files:**
- Replace: `src/workflow_engine/adapters/openai.py`
- Create: `tests/test_openai_adapter.py`

- [ ] **Step 1: 새 구현으로 교체**

```python
import json
from typing import Any

from openai import AsyncOpenAI


class OpenAIAdapter:
    def __init__(self, api_key: str, model: str, temperature: float = 0):
        self.client = AsyncOpenAI(api_key=api_key)
        self.model = model
        self.temperature = temperature

    async def chat_json(self, system: str, user: str) -> dict[str, Any]:
        response = await self.client.chat.completions.create(
            model=self.model,
            temperature=self.temperature,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            response_format={"type": "json_object"},
        )
        return json.loads(response.choices[0].message.content or "{}")
```

- [ ] **Step 2: `tests/test_openai_adapter.py` 작성**

```python
import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from workflow_engine.adapters.openai import OpenAIAdapter


async def test_openai_adapter_passes_system_and_user_messages():
    adapter = OpenAIAdapter(api_key="test", model="gpt-4.1-mini")
    fake_completion = MagicMock()
    fake_completion.choices = [MagicMock(message=MagicMock(content='{"ok": true}'))]
    adapter.client.chat.completions.create = AsyncMock(return_value=fake_completion)

    result = await adapter.chat_json(system="be helpful", user="hi")

    assert result == {"ok": True}
    call = adapter.client.chat.completions.create.call_args
    assert call.kwargs["messages"] == [
        {"role": "system", "content": "be helpful"},
        {"role": "user", "content": "hi"},
    ]
    assert call.kwargs["response_format"] == {"type": "json_object"}


async def test_openai_adapter_uses_temperature_zero_by_default():
    adapter = OpenAIAdapter(api_key="test", model="gpt-4.1-mini")
    fake_completion = MagicMock()
    fake_completion.choices = [MagicMock(message=MagicMock(content="{}"))]
    adapter.client.chat.completions.create = AsyncMock(return_value=fake_completion)

    await adapter.chat_json(system="s", user="u")

    assert adapter.client.chat.completions.create.call_args.kwargs["temperature"] == 0
```

- [ ] **Step 3: 테스트 통과**

```bash
python -m pytest tests/test_openai_adapter.py -v
```

Expected: 2개 PASS.

- [ ] **Step 4: Commit**

```bash
git add src/workflow_engine/adapters/openai.py tests/test_openai_adapter.py
git commit -m "feat: rewrite OpenAIAdapter with chat_json signature"
```

---

### Task 15: nodes/llm.py 신설 — classify_email + generate_reply + 검증

**Files:**
- Create: `src/workflow_engine/nodes/llm.py`
- Create: `tests/test_llm_tasks.py`

- [ ] **Step 1: 실패하는 테스트 작성**

```python
import pytest

from workflow_engine.adapters.fake_ai import FakeAI
from workflow_engine.domain.errors import LLMOutputValidationError
from workflow_engine.nodes.llm import classify_email, generate_reply


async def test_classify_email_returns_category():
    ai = FakeAI({"category": "billing"})
    result = await classify_email(ai, {"subject": "결제 오류", "body": "..."})
    assert result == {"category": "billing"}


async def test_classify_email_passes_subject_and_body_in_user_prompt():
    ai = FakeAI({"category": "general"})
    await classify_email(ai, {"subject": "Hello", "body": "World"})
    assert "Hello" in ai.last_user
    assert "World" in ai.last_user


async def test_classify_email_rejects_unknown_category():
    ai = FakeAI({"category": "sales"})
    with pytest.raises(LLMOutputValidationError):
        await classify_email(ai, {"subject": "x", "body": "y"})


async def test_generate_reply_returns_subject_and_body():
    body_text = "안녕하세요. 예상 처리 기한 3영업일 이내로 처리하며 접수 확인 번호 ACK-001을 안내드립니다."
    ai = FakeAI({"subject": "Re: 결제 오류", "body": body_text})
    result = await generate_reply(ai, {
        "inquiry": {"subject": "결제 오류", "body": "..."},
        "category": "billing",
        "customer": {"name": "김민수", "plan": "Enterprise", "status": "active"},
    })
    assert result["subject"] == "Re: 결제 오류"
    assert result["body"] == body_text


async def test_generate_reply_rejects_empty_body():
    ai = FakeAI({"subject": "Re: x", "body": "   "})
    with pytest.raises(LLMOutputValidationError):
        await generate_reply(ai, {
            "inquiry": {"subject": "x", "body": "y"},
            "category": "general",
            "customer": {"name": "n", "plan": "Free", "status": "active"},
        })


async def test_generate_reply_rejects_billing_without_required_keywords():
    # billing은 "예상 처리 기한", "접수 확인 번호" 둘 다 포함되어야 함
    ai = FakeAI({"subject": "Re: x", "body": "처리해 드리겠습니다"})
    with pytest.raises(LLMOutputValidationError):
        await generate_reply(ai, {
            "inquiry": {"subject": "x", "body": "y"},
            "category": "billing",
            "customer": {"name": "n", "plan": "Enterprise", "status": "active"},
        })


async def test_generate_reply_passes_general_with_no_required_keywords():
    ai = FakeAI({"subject": "Re: x", "body": "안내해 드리겠습니다"})
    result = await generate_reply(ai, {
        "inquiry": {"subject": "x", "body": "y"},
        "category": "general",
        "customer": {"name": "n", "plan": "Free", "status": "active"},
    })
    assert result["body"] == "안내해 드리겠습니다"


async def test_generate_reply_includes_tone_and_guideline_in_system_prompt():
    body_text = "예상 처리 기한 3영업일, 접수 확인 번호 ACK-001"
    ai = FakeAI({"subject": "Re: x", "body": body_text})
    await generate_reply(ai, {
        "inquiry": {"subject": "x", "body": "y"},
        "category": "billing",
        "customer": {"name": "n", "plan": "Enterprise", "status": "active"},
    })
    assert "정중하고 신속" in ai.last_system  # CATEGORY_TONE
    assert "예상 처리 기한" in ai.last_system  # REQUIRED_INCLUDES
    assert "전담 매니저" in ai.last_system     # PLAN_RULES Enterprise
    assert "확인되지 않은 정보" in ai.last_system  # PROHIBITED
```

- [ ] **Step 2: 테스트 실패 확인**

```bash
python -m pytest tests/test_llm_tasks.py -v
```

Expected: FAIL with import error.

- [ ] **Step 3: nodes/llm.py 작성**

```python
from typing import Any

from workflow_engine.domain.errors import LLMOutputValidationError
from workflow_engine.domain.reply_policy import (
    CATEGORIES, CATEGORY_GUIDELINES, CATEGORY_TONE,
    PLAN_RULES, PROHIBITED_RULES, REQUIRED_INCLUDES,
)
from workflow_engine.engine.ports import AI
from workflow_engine.nodes.prompts import (
    CLASSIFY_SYSTEM, CLASSIFY_USER_TEMPLATE,
    GENERATE_SYSTEM_TEMPLATE, GENERATE_USER_TEMPLATE,
    render_template,
)


async def classify_email(ai: AI, input_data: dict[str, Any]) -> dict[str, Any]:
    user = render_template(CLASSIFY_USER_TEMPLATE, input_data)
    response = await ai.chat_json(system=CLASSIFY_SYSTEM, user=user)
    category = response.get("category")
    if category not in CATEGORIES:
        raise LLMOutputValidationError(f"Unknown category: {category!r}")
    return {"category": category}


async def generate_reply(ai: AI, input_data: dict[str, Any]) -> dict[str, Any]:
    category = input_data["category"]
    plan = input_data["customer"].get("plan", "")
    system = render_template(GENERATE_SYSTEM_TEMPLATE, {
        "tone": CATEGORY_TONE[category],
        "guideline": CATEGORY_GUIDELINES[category],
        "plan_rule": PLAN_RULES.get(plan, ""),
        "required_includes": ", ".join(REQUIRED_INCLUDES[category]) or "(없음)",
        "prohibited": "\n".join(f"- {rule}" for rule in PROHIBITED_RULES),
    })
    user = render_template(GENERATE_USER_TEMPLATE, input_data)
    response = await ai.chat_json(system=system, user=user)
    _validate_reply(response, category)
    return {"subject": response["subject"], "body": response["body"]}


def _validate_reply(response: dict[str, Any], category: str) -> None:
    subject = response.get("subject")
    body = response.get("body")
    if not isinstance(subject, str) or not subject.strip():
        raise LLMOutputValidationError("subject가 비어있습니다.")
    if not isinstance(body, str) or not body.strip():
        raise LLMOutputValidationError("body가 비어있습니다.")
    missing = [keyword for keyword in REQUIRED_INCLUDES[category]
               if keyword not in body]
    if missing:
        raise LLMOutputValidationError(
            f"카테고리 '{category}'의 필수 포함 항목 누락: {missing}"
        )
```

- [ ] **Step 4: 테스트 통과 확인**

```bash
python -m pytest tests/test_llm_tasks.py -v
```

Expected: 8개 PASS.

- [ ] **Step 5: Commit**

```bash
git add src/workflow_engine/nodes/llm.py tests/test_llm_tasks.py
git commit -m "feat: add nodes/llm.py with classify_email, generate_reply, _validate_reply"
```

---

### Task 16: engine/registries.AITaskRegistry를 tasks + profiles 두 dict 형태로 변경

**Files:**
- Modify: `src/workflow_engine/engine/registries.py`
- Create: `tests/test_ai_registry.py`

- [ ] **Step 1: 실패하는 테스트 작성**

```python
import pytest

from workflow_engine.adapters.fake_ai import FakeAI
from workflow_engine.domain.errors import WorkflowEngineError
from workflow_engine.engine.registries import AITaskRegistry


async def _passthrough(ai, input_data):
    return await ai.chat_json(system="s", user="u")


async def test_registry_dispatches_to_registered_task_and_profile():
    classify_ai = FakeAI({"category": "billing"})
    generate_ai = FakeAI({"subject": "x", "body": "y"})
    registry = AITaskRegistry(
        tasks={"classify_email": _passthrough, "generate_reply": _passthrough},
        profiles={"classify_email": classify_ai, "generate_reply": generate_ai},
    )
    classify_result = await registry.run("classify_email", {})
    generate_result = await registry.run("generate_reply", {})
    assert classify_result == {"category": "billing"}
    assert generate_result == {"subject": "x", "body": "y"}


async def test_registry_uses_separate_adapter_per_action():
    classify_ai = FakeAI({"category": "billing"})
    generate_ai = FakeAI({"subject": "x", "body": "y"})
    registry = AITaskRegistry(
        tasks={"classify_email": _passthrough, "generate_reply": _passthrough},
        profiles={"classify_email": classify_ai, "generate_reply": generate_ai},
    )
    await registry.run("classify_email", {})
    await registry.run("generate_reply", {})
    assert classify_ai.last_user == "u"
    assert generate_ai.last_user == "u"


async def test_registry_raises_for_unknown_task():
    registry = AITaskRegistry(tasks={}, profiles={})
    with pytest.raises(WorkflowEngineError, match="Unknown AI task"):
        await registry.run("missing", {})


async def test_registry_raises_when_profile_missing():
    registry = AITaskRegistry(
        tasks={"classify_email": _passthrough},
        profiles={},  # 프로필 미등록
    )
    with pytest.raises(WorkflowEngineError, match="No AI profile"):
        await registry.run("classify_email", {})
```

- [ ] **Step 2: 테스트 실패 확인**

```bash
python -m pytest tests/test_ai_registry.py -v
```

Expected: FAIL — 새 시그니처 미구현.

- [ ] **Step 3: AITaskRegistry 재작성**

`engine/registries.py` 전체:

```python
from typing import Any, Awaitable, Callable

from workflow_engine.domain.errors import WorkflowEngineError
from workflow_engine.engine.ports import AI, Tool

TaskFn = Callable[[AI, dict[str, Any]], Awaitable[dict[str, Any]]]


class ToolRegistry:
    def __init__(self, tools: dict[str, Tool]):
        self._tools = tools

    def get(self, name: str) -> Tool:
        try:
            return self._tools[name]
        except KeyError as exc:
            raise KeyError(f"Unknown tool: {name}") from exc


class AITaskRegistry:
    def __init__(self, tasks: dict[str, TaskFn], profiles: dict[str, AI]):
        self._tasks = tasks
        self._profiles = profiles

    async def run(self, task_name: str, input_data: dict[str, Any]) -> dict[str, Any]:
        task_fn = self._tasks.get(task_name)
        if task_fn is None:
            raise WorkflowEngineError(f"Unknown AI task: {task_name}")
        adapter = self._profiles.get(task_name)
        if adapter is None:
            raise WorkflowEngineError(f"No AI profile registered for task: {task_name}")
        return await task_fn(adapter, input_data)
```

- [ ] **Step 4: 테스트 통과 확인**

```bash
python -m pytest tests/test_ai_registry.py -v
```

Expected: 4개 PASS.

- [ ] **Step 5: Commit**

```bash
git add src/workflow_engine/engine/registries.py tests/test_ai_registry.py
git commit -m "feat: change AITaskRegistry to tasks + profiles dual-dict structure"
```

---

### Task 17: api.py와 test_executor.py 갱신 — 새 레지스트리 시그니처 반영

**Files:**
- Modify: `src/workflow_engine/api.py`
- Modify: `tests/test_executor.py`

- [ ] **Step 1: api.py 조립부 갱신**

`src/workflow_engine/api.py`에서 `AITaskRegistry(...)` 호출 부분을 찾아 다음으로 교체:

```python
from workflow_engine.adapters.fake_ai import FakeAI
from workflow_engine.adapters.openai import OpenAIAdapter
from workflow_engine.nodes.llm import classify_email, generate_reply

# create_app 함수 안:
if settings.llm_provider == "openai" and settings.openai_api_key:
    classify_ai = OpenAIAdapter(settings.openai_api_key, settings.openai_model)
    generate_ai = OpenAIAdapter(settings.openai_api_key, settings.openai_model)
else:
    classify_ai = FakeAI({"category": "billing"})
    generate_ai = FakeAI({
        "subject": "Re: 카드 결제가 계속 실패합니다",
        "body": "예상 처리 기한 3영업일, 접수 확인 번호 ACK-001 안내드립니다.",
    })

executor = WorkflowExecutor(
    store=store,
    tool_registry=ToolRegistry({...}),  # 기존 그대로
    ai_registry=AITaskRegistry(
        tasks={"classify_email": classify_email, "generate_reply": generate_reply},
        profiles={"classify_email": classify_ai, "generate_reply": generate_ai},
    ),
)
```

(Phase 3 Task 19에서 `bootstrap.py`로 이 조립이 옮겨진다. 이 task에선 임시로 `api.py`를 동작 가능 상태로 유지하는 것이 목적.)

- [ ] **Step 2: tests/test_executor.py 갱신**

`tests/test_executor.py` 의 `_executor` 헬퍼를 갱신:

```python
from workflow_engine.adapters.fake_ai import FakeAI
from workflow_engine.engine.registries import AITaskRegistry, ToolRegistry
from workflow_engine.nodes.llm import classify_email, generate_reply


def _executor(client):
    classify_ai = FakeAI({"category": "billing"})
    generate_ai = FakeAI({
        "subject": "Re: 카드 결제가 계속 실패합니다",
        "body": "예상 처리 기한 3영업일, 접수 확인 번호 ACK-001 안내드립니다.",
    })
    return WorkflowExecutor(
        store=RunStoreAdapter(),
        tool_registry=ToolRegistry({
            "inquiry_get": InquiryGetTool(client),
            "crm_lookup": CRMLookupTool(client),
            "email_send": EmailSendTool(client),
        }),
        ai_registry=AITaskRegistry(
            tasks={"classify_email": classify_email, "generate_reply": generate_reply},
            profiles={"classify_email": classify_ai, "generate_reply": generate_ai},
        ),
    )
```

- [ ] **Step 3: tests/test_api.py도 갱신 (use_fake_dependencies 분기)**

`tests/test_api.py`에서 `use_fake_dependencies=True` 호출이 동작하도록 `api.create_app`도 새 fake AI 패턴에 맞게 수정. 또는 잠시 use_fake_dependencies 분기에서 `FakeAI` 두 개를 만들어 사용.

`src/workflow_engine/api.py` `create_app`의 use_fake_dependencies 분기 갱신:

```python
def create_app(use_fake_dependencies: bool = False) -> FastAPI:
    settings = Settings()
    if use_fake_dependencies:
        from workflow_engine.adapters.mock_api import FakeMockAPIAdapter
        mock_server = FakeMockAPIAdapter()
    else:
        from workflow_engine.adapters.mock_api import MockAPIAdapter
        mock_server = MockAPIAdapter(settings.mock_api_base_url, settings.mock_api_key)
    
    if settings.llm_provider == "openai" and settings.openai_api_key:
        classify_ai = OpenAIAdapter(settings.openai_api_key, settings.openai_model)
        generate_ai = OpenAIAdapter(settings.openai_api_key, settings.openai_model)
    else:
        classify_ai = FakeAI({"category": "billing"})
        generate_ai = FakeAI({
            "subject": "Re: 카드 결제가 계속 실패합니다",
            "body": "예상 처리 기한 3영업일, 접수 확인 번호 ACK-001 안내드립니다.",
        })
    
    # ... 나머지 동일
```

(Phase 3 Task 19에서 `bootstrap.py` + `app.py(deps)` 분리되며 use_fake_dependencies 플래그가 사라진다.)

- [ ] **Step 4: 전체 테스트 통과 확인**

```bash
python -m pytest -q
```

Expected: 모든 테스트 PASS.

- [ ] **Step 5: 서버 기동 확인**

```bash
python -m workflow_engine.main &
SERVER_PID=$!
sleep 2

curl -s -X POST http://localhost:8000/workflow-runs \
  -H "Content-Type: application/json" \
  -d '{"workflow_key":"customer_support_auto_reply","inquiry_id":"INQ-002"}' | python -m json.tool

kill $SERVER_PID
```

Expected: status `WAITING_APPROVAL`, generate된 body에 "예상 처리 기한"이 포함됨.

- [ ] **Step 6: Commit**

```bash
git add src/workflow_engine/api.py tests/test_executor.py tests/test_api.py
git commit -m "refactor: wire api.py and test_executor.py to new AITaskRegistry signature"
```

---

## Phase 3 — Bootstrap 분리 + app.py + routes.py + schemas.py

---

### Task 18: config.py에 액션별 모델 환경변수 추가

**Files:**
- Modify: `src/workflow_engine/config.py`
- Modify: `.env.example`

- [ ] **Step 1: config.py 갱신**

```python
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env")

    mock_api_base_url: str = "http://localhost:8080"
    mock_api_key: str = "mock-api-key-12345"
    llm_provider: str = "fake"
    openai_api_key: str = ""
    openai_model: str = "gpt-4.1-mini"           # fallback
    openai_classify_model: str = ""              # 비면 openai_model 사용
    openai_generate_model: str = ""              # 비면 openai_model 사용
    openai_temperature: float = 0.0

    @property
    def classify_model(self) -> str:
        return self.openai_classify_model or self.openai_model

    @property
    def generate_model(self) -> str:
        return self.openai_generate_model or self.openai_model
```

- [ ] **Step 2: .env.example 갱신**

```
MOCK_API_BASE_URL=http://localhost:8080
MOCK_API_KEY=mock-api-key-12345

LLM_PROVIDER=fake
OPENAI_API_KEY=
OPENAI_MODEL=gpt-4.1-mini
OPENAI_CLASSIFY_MODEL=gpt-4.1-mini
OPENAI_GENERATE_MODEL=gpt-4.1-mini
OPENAI_TEMPERATURE=0
```

- [ ] **Step 3: 테스트 통과 (영향 없음 확인)**

```bash
python -m pytest -q
```

- [ ] **Step 4: Commit**

```bash
git add src/workflow_engine/config.py .env.example
git commit -m "feat: add openai_classify_model and openai_generate_model settings with fallback"
```

---

### Task 19: bootstrap.py 신설

**Files:**
- Create: `src/workflow_engine/bootstrap.py`

- [ ] **Step 1: bootstrap.py 작성**

```python
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from workflow_engine.adapters.fake_ai import FakeAI
from workflow_engine.adapters.mock_api import FakeMockAPIAdapter, MockAPIAdapter
from workflow_engine.adapters.openai import OpenAIAdapter
from workflow_engine.adapters.run_store import RunStoreAdapter
from workflow_engine.config import Settings
from workflow_engine.engine.executor import WorkflowExecutor
from workflow_engine.engine.registries import AITaskRegistry, ToolRegistry
from workflow_engine.engine.retry import RetryExecutor, RetryPolicy
from workflow_engine.nodes.llm import classify_email, generate_reply
from workflow_engine.nodes.tools import CRMLookupTool, EmailSendTool, InquiryGetTool


@dataclass
class AppDependencies:
    executor: WorkflowExecutor
    store: RunStoreAdapter
    workflow_paths: dict[str, Path]


def build_dependencies(settings: Settings) -> AppDependencies:
    """운영 의존성 조립."""
    store = RunStoreAdapter()
    retry = RetryExecutor(RetryPolicy())
    mock_api = MockAPIAdapter(settings.mock_api_base_url, settings.mock_api_key)

    if settings.llm_provider == "openai" and settings.openai_api_key:
        classify_ai = OpenAIAdapter(
            settings.openai_api_key, settings.classify_model, settings.openai_temperature,
        )
        generate_ai = OpenAIAdapter(
            settings.openai_api_key, settings.generate_model, settings.openai_temperature,
        )
    else:
        classify_ai, generate_ai = _default_fakes()

    return _assemble(
        store=store,
        retry=retry,
        mock_api=mock_api,
        classify_ai=classify_ai,
        generate_ai=generate_ai,
    )


def build_test_dependencies(
    *,
    classify_response: dict[str, Any] | None = None,
    generate_response: dict[str, Any] | None = None,
    fake_mock_api: Any = None,
    retry_policy: RetryPolicy | None = None,
) -> AppDependencies:
    """테스트용 fake 의존성 조립."""
    store = RunStoreAdapter()
    retry = RetryExecutor(retry_policy or RetryPolicy(max_attempts=1, initial_delay_seconds=0))
    mock_api = fake_mock_api or FakeMockAPIAdapter()
    classify_default, generate_default = _default_fakes()
    classify_ai = FakeAI(classify_response) if classify_response is not None else classify_default
    generate_ai = FakeAI(generate_response) if generate_response is not None else generate_default
    return _assemble(
        store=store,
        retry=retry,
        mock_api=mock_api,
        classify_ai=classify_ai,
        generate_ai=generate_ai,
    )


def _default_fakes() -> tuple[FakeAI, FakeAI]:
    classify_ai = FakeAI({"category": "billing"})
    generate_ai = FakeAI({
        "subject": "Re: 카드 결제가 계속 실패합니다",
        "body": (
            "안녕하세요. 결제 오류 문의 확인했습니다. "
            "예상 처리 기한 3영업일 이내, 접수 확인 번호 ACK-001입니다."
        ),
    })
    return classify_ai, generate_ai


def _assemble(*, store, retry, mock_api, classify_ai, generate_ai) -> AppDependencies:
    tool_registry = ToolRegistry({
        "inquiry_get": InquiryGetTool(mock_api, retry),
        "crm_lookup": CRMLookupTool(mock_api, retry),
        "email_send": EmailSendTool(mock_api, retry),
    })
    ai_registry = AITaskRegistry(
        tasks={"classify_email": classify_email, "generate_reply": generate_reply},
        profiles={"classify_email": classify_ai, "generate_reply": generate_ai},
    )
    executor = WorkflowExecutor(
        store=store,
        tool_registry=tool_registry,
        ai_registry=ai_registry,
    )
    return AppDependencies(
        executor=executor,
        store=store,
        workflow_paths={
            "customer_support_auto_reply": Path("workflows/customer_support_auto_reply.yaml"),
        },
    )
```

(Phase 4 Task 24에서 `ApprovalTimer` 조립이 추가된다.)

- [ ] **Step 2: 테스트 통과 (bootstrap 자체는 아직 사용 안 됨)**

```bash
python -m pytest -q
```

- [ ] **Step 3: Commit**

```bash
git add src/workflow_engine/bootstrap.py
git commit -m "feat: add bootstrap.py with build_dependencies and build_test_dependencies"
```

---

### Task 20: api/ 디렉토리 생성 + schemas.py 분리

**Files:**
- Delete (move-aside): 잠시 `src/workflow_engine/api.py`
- Create: `src/workflow_engine/api/__init__.py`
- Create: `src/workflow_engine/api/schemas.py`

- [ ] **Step 1: 기존 api.py를 임시 백업 후 삭제**

```bash
cp src/workflow_engine/api.py /tmp/api_old.py.bak
git rm src/workflow_engine/api.py
```

- [ ] **Step 2: api/ 디렉토리 + __init__.py 생성**

```bash
mkdir -p src/workflow_engine/api
touch src/workflow_engine/api/__init__.py
```

- [ ] **Step 3: api/schemas.py 작성**

```python
from typing import Literal

from pydantic import BaseModel, Field


class StartWorkflowRunRequest(BaseModel):
    workflow_key: str = Field(..., description="실행할 워크플로우 키")
    inquiry_id: str = Field(..., description="Mock Inquiry API에서 조회할 문의 ID")


class ApprovalDecisionRequest(BaseModel):
    decision: Literal["approve", "reject"] = Field(..., description="승인 결정값. approve 또는 reject")
    reason: str | None = Field(default=None, description="거부 사유")
```

- [ ] **Step 4: 테스트는 일시적으로 깨질 것 — 다음 task에서 복구**

이 시점에선 `api.py` 삭제로 인해 `python -m workflow_engine.main` 및 `tests/test_api.py`가 깨진다. Task 21, 22에서 복구.

- [ ] **Step 5: Commit**

```bash
git add src/workflow_engine/api
git commit -m "refactor: convert api.py to api/ package, add schemas.py"
```

---

### Task 21: api/routes.py 작성

**Files:**
- Create: `src/workflow_engine/api/routes.py`

- [ ] **Step 1: api/routes.py 작성**

```python
from fastapi import FastAPI, HTTPException

from workflow_engine.api.schemas import ApprovalDecisionRequest, StartWorkflowRunRequest
from workflow_engine.bootstrap import AppDependencies
from workflow_engine.domain.errors import WorkflowEngineError
from workflow_engine.domain.run import WorkflowRun
from workflow_engine.engine.loader import load_workflow
from workflow_engine.adapters.run_store import RunNotFoundError


def register_routes(app: FastAPI, deps: AppDependencies) -> None:
    @app.post(
        "/workflow-runs",
        response_model=WorkflowRun,
        summary="워크플로우 실행 시작",
        description="문의 ID를 입력받아 워크플로우를 승인 대기 단계까지 실행합니다.",
        tags=["워크플로우 실행"],
    )
    async def start_workflow_run(request: StartWorkflowRunRequest):
        workflow_path = deps.workflow_paths.get(request.workflow_key)
        if workflow_path is None:
            raise HTTPException(status_code=404, detail="지원하지 않는 워크플로우입니다.")
        workflow = load_workflow(workflow_path)
        return await deps.executor.start(workflow, {"inquiry_id": request.inquiry_id})

    @app.get(
        "/workflow-runs/{run_id}",
        response_model=WorkflowRun,
        summary="워크플로우 실행 상태 조회",
        description="실행 ID로 현재 상태, 컨텍스트, 노드 상태, 승인 정보를 조회합니다.",
        tags=["워크플로우 실행"],
    )
    async def get_workflow_run(run_id: str):
        try:
            return deps.store.get(run_id)
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
        workflow = load_workflow(deps.workflow_paths["customer_support_auto_reply"])
        try:
            return await deps.executor.submit_approval(
                workflow, run_id, request.decision, request.reason,
            )
        except RunNotFoundError as exc:
            raise HTTPException(status_code=404, detail="워크플로우 실행을 찾을 수 없습니다.") from exc
        except WorkflowEngineError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
```

- [ ] **Step 2: Commit (테스트 아직 못 돌림)**

```bash
git add src/workflow_engine/api/routes.py
git commit -m "feat: add api/routes.py with register_routes"
```

---

### Task 22: 최상위 app.py 작성 + main.py 갱신

**Files:**
- Create: `src/workflow_engine/app.py`
- Modify: `src/workflow_engine/main.py`

- [ ] **Step 1: app.py 작성**

```python
from fastapi import FastAPI

from workflow_engine.api.routes import register_routes
from workflow_engine.bootstrap import AppDependencies


def create_app(deps: AppDependencies) -> FastAPI:
    app = FastAPI(
        title="AI 워크플로우 실행 엔진",
        description="고객 문의 자동 응답 워크플로우를 실행하고 승인 대기 상태를 관리하는 API입니다.",
        version="0.1.0",
    )
    register_routes(app, deps)
    return app
```

- [ ] **Step 2: main.py 갱신**

```python
import uvicorn

from workflow_engine.app import create_app
from workflow_engine.bootstrap import build_dependencies
from workflow_engine.config import Settings


def main() -> None:
    settings = Settings()
    deps = build_dependencies(settings)
    app = create_app(deps)
    uvicorn.run(app, host="0.0.0.0", port=8000)


if __name__ == "__main__":
    main()
```

(`reload=True`는 일시 제거. uvicorn reload는 import string을 받기 때문에 `app=create_app(deps)`처럼 인스턴스를 직접 넘기면 reload 비활성. 운영 환경에선 `uvicorn workflow_engine.main:app` 같은 형태가 필요하지만 평가 MVP에선 reload 없이 충분.)

- [ ] **Step 3: Commit (테스트 아직 못 돌림)**

```bash
git add src/workflow_engine/app.py src/workflow_engine/main.py
git commit -m "feat: add top-level app.py and update main.py to use bootstrap"
```

---

### Task 23: tests/conftest.py 추가 + test_api.py 갱신

**Files:**
- Create: `tests/conftest.py`
- Modify: `tests/test_api.py`

- [ ] **Step 1: tests/conftest.py 작성**

```python
import pytest
from fastapi.testclient import TestClient

from workflow_engine.app import create_app
from workflow_engine.bootstrap import build_test_dependencies


@pytest.fixture
def deps():
    return build_test_dependencies()


@pytest.fixture
def client(deps):
    return TestClient(create_app(deps))
```

- [ ] **Step 2: tests/test_api.py 갱신**

```python
from fastapi.testclient import TestClient

from workflow_engine.app import create_app
from workflow_engine.bootstrap import build_test_dependencies


def test_openapi_documentation_is_korean(client):
    schema = client.get("/openapi.json").json()
    assert schema["info"]["title"] == "AI 워크플로우 실행 엔진"
    assert "워크플로우 실행" in schema["paths"]["/workflow-runs"]["post"]["summary"]


def test_start_workflow_endpoint_returns_run_waiting_for_approval(client):
    response = client.post("/workflow-runs", json={
        "workflow_key": "customer_support_auto_reply",
        "inquiry_id": "INQ-002",
    })
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "WAITING_APPROVAL"
    assert body["current_node_key"] == "wait_for_approval"


def test_start_workflow_endpoint_rejects_unknown_workflow_key(client):
    response = client.post("/workflow-runs", json={
        "workflow_key": "unknown_workflow",
        "inquiry_id": "INQ-002",
    })
    assert response.status_code == 404
    assert response.json()["detail"] == "지원하지 않는 워크플로우입니다."


def test_approval_endpoint_completes_run(client):
    started = client.post("/workflow-runs", json={
        "workflow_key": "customer_support_auto_reply",
        "inquiry_id": "INQ-002",
    }).json()
    response = client.post(f"/workflow-runs/{started['run_id']}/approval", json={"decision": "approve"})
    assert response.status_code == 200
    assert response.json()["status"] == "COMPLETED"


def test_approval_endpoint_returns_404_for_missing_run(client):
    response = client.post("/workflow-runs/run_missing/approval", json={"decision": "approve"})
    assert response.status_code == 404
    assert response.json()["detail"] == "워크플로우 실행을 찾을 수 없습니다."


def test_approval_endpoint_rejects_run_that_is_not_waiting(client):
    started = client.post("/workflow-runs", json={
        "workflow_key": "customer_support_auto_reply",
        "inquiry_id": "INQ-002",
    }).json()
    client.post(f"/workflow-runs/{started['run_id']}/approval", json={"decision": "approve"})
    response = client.post(f"/workflow-runs/{started['run_id']}/approval", json={"decision": "approve"})
    assert response.status_code == 409
    assert response.json()["detail"] == "승인 대기 상태가 아닙니다."
```

- [ ] **Step 3: 전체 테스트 통과**

```bash
python -m pytest -q
```

Expected: 모든 테스트 PASS.

- [ ] **Step 4: 서버 기동 확인**

```bash
python -m workflow_engine.main &
SERVER_PID=$!
sleep 2

curl -s http://localhost:8000/openapi.json | python -c "import sys, json; print(json.load(sys.stdin)['info']['title'])"

kill $SERVER_PID
```

Expected: `AI 워크플로우 실행 엔진`.

- [ ] **Step 5: Commit**

```bash
git add tests/conftest.py tests/test_api.py
git commit -m "feat: add tests/conftest.py and rewrite test_api.py with build_test_dependencies"
```

---

## Phase 4 — 능동 타임아웃 + run_id 락 + 멱등성

---

### Task 24: engine/approval_timer.py 신설

**Files:**
- Create: `src/workflow_engine/engine/approval_timer.py`
- Create: `tests/test_approval_timer.py`

- [ ] **Step 1: 실패하는 테스트 작성**

```python
import asyncio
from datetime import datetime, timedelta, timezone

import pytest

from workflow_engine.engine.approval_timer import ApprovalTimer


async def test_schedule_fires_callback_after_deadline():
    fired: list[str] = []

    async def on_expire(run_id: str) -> None:
        fired.append(run_id)

    timer = ApprovalTimer()
    timer.set_on_expire(on_expire)
    deadline = datetime.now(timezone.utc) + timedelta(milliseconds=50)
    timer.schedule("run_1", deadline)
    await asyncio.sleep(0.15)
    assert fired == ["run_1"]


async def test_cancel_prevents_callback():
    fired: list[str] = []

    async def on_expire(run_id: str) -> None:
        fired.append(run_id)

    timer = ApprovalTimer()
    timer.set_on_expire(on_expire)
    deadline = datetime.now(timezone.utc) + timedelta(milliseconds=100)
    timer.schedule("run_1", deadline)
    timer.cancel("run_1")
    await asyncio.sleep(0.2)
    assert fired == []


async def test_schedule_replaces_previous_task_for_same_run_id():
    fired: list[tuple[str, float]] = []

    async def on_expire(run_id: str) -> None:
        fired.append((run_id, asyncio.get_event_loop().time()))

    timer = ApprovalTimer()
    timer.set_on_expire(on_expire)
    deadline_a = datetime.now(timezone.utc) + timedelta(milliseconds=200)
    timer.schedule("run_1", deadline_a)
    deadline_b = datetime.now(timezone.utc) + timedelta(milliseconds=50)
    timer.schedule("run_1", deadline_b)  # 새 태스크가 직전 태스크를 cancel해야 함
    await asyncio.sleep(0.3)
    assert len(fired) == 1


async def test_schedule_with_past_deadline_fires_immediately():
    fired: list[str] = []

    async def on_expire(run_id: str) -> None:
        fired.append(run_id)

    timer = ApprovalTimer()
    timer.set_on_expire(on_expire)
    deadline = datetime.now(timezone.utc) - timedelta(seconds=5)
    timer.schedule("run_1", deadline)
    await asyncio.sleep(0.05)
    assert fired == ["run_1"]


def test_schedule_without_callback_raises_assertion():
    timer = ApprovalTimer()
    with pytest.raises(AssertionError):
        timer.schedule("run_1", datetime.now(timezone.utc))
```

- [ ] **Step 2: 테스트 실패 확인**

```bash
python -m pytest tests/test_approval_timer.py -v
```

Expected: FAIL — 클래스 미구현.

- [ ] **Step 3: engine/approval_timer.py 작성**

```python
import asyncio
from collections.abc import Awaitable, Callable
from datetime import datetime, timezone


class ApprovalTimer:
    """per-run asyncio Task로 승인 deadline을 능동적으로 감시한다."""

    def __init__(self) -> None:
        self._tasks: dict[str, asyncio.Task] = {}
        self._on_expire: Callable[[str], Awaitable[None]] | None = None

    def set_on_expire(self, callback: Callable[[str], Awaitable[None]]) -> None:
        self._on_expire = callback

    def schedule(self, run_id: str, deadline_at: datetime) -> None:
        assert self._on_expire is not None, "set_on_expire must be called before schedule"
        existing = self._tasks.get(run_id)
        if existing is not None and not existing.done():
            existing.cancel()
        seconds = max(0.0, (deadline_at - datetime.now(timezone.utc)).total_seconds())
        self._tasks[run_id] = asyncio.create_task(self._wait_and_expire(run_id, seconds))

    async def _wait_and_expire(self, run_id: str, seconds: float) -> None:
        try:
            await asyncio.sleep(seconds)
        except asyncio.CancelledError:
            return
        assert self._on_expire is not None
        await self._on_expire(run_id)
        self._tasks.pop(run_id, None)

    def cancel(self, run_id: str) -> None:
        task = self._tasks.pop(run_id, None)
        if task is not None and not task.done():
            task.cancel()
```

- [ ] **Step 4: 테스트 통과 확인**

```bash
python -m pytest tests/test_approval_timer.py -v
```

Expected: 5개 PASS.

- [ ] **Step 5: Commit**

```bash
git add src/workflow_engine/engine/approval_timer.py tests/test_approval_timer.py
git commit -m "feat: add ApprovalTimer for active approval deadline expiration"
```

---

### Task 25: WorkflowExecutor에 ApprovalTimer + run_id 락 + expire_run/expire_if_overdue

**Files:**
- Modify: `src/workflow_engine/engine/executor.py`
- Modify: `src/workflow_engine/bootstrap.py`
- Modify: `tests/test_executor.py`

- [ ] **Step 1: executor.py 갱신**

`src/workflow_engine/engine/executor.py` 전체:

```python
import asyncio
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from workflow_engine.adapters.run_store import RunNotFoundError
from workflow_engine.domain.errors import WorkflowEngineError
from workflow_engine.domain.run import (
    ApprovalState, NodeState, NodeStatus, RunStatus,
    WorkflowErrorData, WorkflowRun,
)
from workflow_engine.domain.workflow import WorkflowDefinition, WorkflowNode
from workflow_engine.engine.approval_timer import ApprovalTimer
from workflow_engine.engine.input_mapping import render_inputs
from workflow_engine.engine.ports import RunStore
from workflow_engine.engine.registries import AITaskRegistry, ToolRegistry
from workflow_engine.engine.validator import topological_sort, validate_workflow


class WorkflowExecutor:
    def __init__(
        self,
        store: RunStore,
        tool_registry: ToolRegistry,
        ai_registry: AITaskRegistry,
        approval_timer: ApprovalTimer | None = None,
    ):
        self.store = store
        self.tool_registry = tool_registry
        self.ai_registry = ai_registry
        self.approval_timer = approval_timer
        self._run_locks: dict[str, asyncio.Lock] = {}

    def _lock_for(self, run_id: str) -> asyncio.Lock:
        if run_id not in self._run_locks:
            self._run_locks[run_id] = asyncio.Lock()
        return self._run_locks[run_id]

    async def start(self, workflow: WorkflowDefinition, input_data: dict) -> WorkflowRun:
        validate_workflow(workflow)
        # 멱등성: 같은 inquiry로 활성 또는 COMPLETED run이 있으면 기존 반환
        inquiry_id = input_data.get("inquiry_id")
        if inquiry_id is not None and hasattr(self.store, "find_by_inquiry"):
            existing = self.store.find_by_inquiry(inquiry_id)
            if existing is not None and existing.status in {
                RunStatus.PENDING, RunStatus.RUNNING,
                RunStatus.WAITING_APPROVAL, RunStatus.COMPLETED,
            }:
                return existing
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

    async def submit_approval(
        self, workflow: WorkflowDefinition, run_id: str,
        decision: str, reason: str | None = None,
    ) -> WorkflowRun:
        async with self._lock_for(run_id):
            run = self.store.get(run_id)
            if run.status != RunStatus.WAITING_APPROVAL or run.approval is None:
                raise WorkflowEngineError("승인 대기 상태가 아닙니다.")
            now = datetime.now(timezone.utc)
            if now > run.approval.deadline_at:
                run.status = RunStatus.TIMED_OUT
                run.error = WorkflowErrorData(
                    code="APPROVAL_TIMEOUT", message="승인 대기 시간이 초과되었습니다.",
                    node_key=run.approval.node_key,
                )
                run.updated_at = now
                if self.approval_timer is not None:
                    self.approval_timer.cancel(run_id)
                return self.store.save(run)

            if self.approval_timer is not None:
                self.approval_timer.cancel(run_id)
            run.approval.decision = decision
            run.approval.reason = reason
            run.approval.decided_at = now

            if decision == "reject":
                run.status = RunStatus.REJECTED
                run.updated_at = now
                return self.store.save(run)

            if decision != "approve":
                return self._fail_run(
                    run, run.current_node_key or "",
                    WorkflowEngineError(f"Unknown approval decision: {decision}"),
                )

            approval_node = run.approval.node_key
            run.node_states[approval_node].status = NodeStatus.COMPLETED
            run.context["nodes"][approval_node] = {
                "decision": "approve", "decided_at": now.isoformat(),
            }
            run.status = RunStatus.RUNNING
            run.updated_at = now
            self.store.save(run)
        return await self._execute_from_order(
            workflow, run, topological_sort(workflow), start_after=approval_node,
        )

    async def expire_run(self, run_id: str) -> None:
        """ApprovalTimer 콜백. WAITING_APPROVAL이면 TIMED_OUT으로 전환."""
        async with self._lock_for(run_id):
            try:
                run = self.store.get(run_id)
            except RunNotFoundError:
                return
            if run.status != RunStatus.WAITING_APPROVAL:
                return
            now = datetime.now(timezone.utc)
            run.status = RunStatus.TIMED_OUT
            run.error = WorkflowErrorData(
                code="APPROVAL_TIMEOUT", message="승인 대기 시간이 초과되었습니다.",
                node_key=run.approval.node_key if run.approval else None,
            )
            run.updated_at = now
            self.store.save(run)

    async def expire_if_overdue(self, run_id: str) -> WorkflowRun:
        """GET 안전망. deadline 경과 발견 시 만료 처리 후 최신 run 반환."""
        async with self._lock_for(run_id):
            run = self.store.get(run_id)
            if run.status == RunStatus.WAITING_APPROVAL and run.approval is not None:
                if datetime.now(timezone.utc) > run.approval.deadline_at:
                    run.status = RunStatus.TIMED_OUT
                    run.error = WorkflowErrorData(
                        code="APPROVAL_TIMEOUT", message="승인 대기 시간이 초과되었습니다.",
                        node_key=run.approval.node_key,
                    )
                    run.updated_at = datetime.now(timezone.utc)
                    self.store.save(run)
            return run

    async def _execute_from_order(
        self, workflow, run, order, start_after=None,
    ):
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
                deadline = datetime.now(timezone.utc) + timedelta(seconds=node.timeout_seconds or 0)
                run.status = RunStatus.WAITING_APPROVAL
                run.node_states[node.key].status = NodeStatus.WAITING
                run.approval = ApprovalState(
                    node_key=node.key, subject=subject, body=body, deadline_at=deadline,
                )
                run.updated_at = datetime.now(timezone.utc)
                self.store.save(run)
                if self.approval_timer is not None:
                    self.approval_timer.schedule(run.run_id, deadline)
                return run

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
            return await self.ai_registry.run(node.task or "", input_data)
        if node.type == "human_approval":
            return input_data
        raise WorkflowEngineError(f"Unsupported node type: {node.type}")

    def _fail_run(self, run, node_key, exc):
        message = str(exc)
        code = getattr(exc, "code", "NODE_EXECUTION_FAILED")
        error = WorkflowErrorData(code=code, message=message, node_key=node_key)
        run.status = RunStatus.FAILED
        run.error = error
        if node_key in run.node_states:
            run.node_states[node_key].status = NodeStatus.FAILED
            run.node_states[node_key].error = error
        run.updated_at = datetime.now(timezone.utc)
        return self.store.save(run)
```

- [ ] **Step 2: bootstrap.py에 ApprovalTimer 조립 추가**

`_assemble` 함수 갱신:

```python
def _assemble(*, store, retry, mock_api, classify_ai, generate_ai) -> AppDependencies:
    from workflow_engine.engine.approval_timer import ApprovalTimer
    
    tool_registry = ToolRegistry({
        "inquiry_get": InquiryGetTool(mock_api, retry),
        "crm_lookup": CRMLookupTool(mock_api, retry),
        "email_send": EmailSendTool(mock_api, retry),
    })
    ai_registry = AITaskRegistry(
        tasks={"classify_email": classify_email, "generate_reply": generate_reply},
        profiles={"classify_email": classify_ai, "generate_reply": generate_ai},
    )
    timer = ApprovalTimer()
    executor = WorkflowExecutor(
        store=store,
        tool_registry=tool_registry,
        ai_registry=ai_registry,
        approval_timer=timer,
    )
    timer.set_on_expire(executor.expire_run)
    return AppDependencies(
        executor=executor,
        store=store,
        workflow_paths={
            "customer_support_auto_reply": Path("workflows/customer_support_auto_reply.yaml"),
        },
    )
```

- [ ] **Step 3: tests/test_executor.py에 lock + timer 케이스 추가**

기존 `_executor` 헬퍼 갱신:

```python
def _executor(client, approval_timer=None):
    from workflow_engine.adapters.fake_ai import FakeAI
    from workflow_engine.engine.registries import AITaskRegistry, ToolRegistry
    from workflow_engine.nodes.llm import classify_email, generate_reply

    classify_ai = FakeAI({"category": "billing"})
    generate_ai = FakeAI({
        "subject": "Re: 카드 결제가 계속 실패합니다",
        "body": "예상 처리 기한 3영업일, 접수 확인 번호 ACK-001 안내드립니다.",
    })
    return WorkflowExecutor(
        store=RunStoreAdapter(),
        tool_registry=ToolRegistry({
            "inquiry_get": InquiryGetTool(client),
            "crm_lookup": CRMLookupTool(client),
            "email_send": EmailSendTool(client),
        }),
        ai_registry=AITaskRegistry(
            tasks={"classify_email": classify_email, "generate_reply": generate_reply},
            profiles={"classify_email": classify_ai, "generate_reply": generate_ai},
        ),
        approval_timer=approval_timer,
    )
```

기존 6개 테스트는 그대로 (위 헬퍼 시그니처가 호환되도록 default 파라미터). 새 테스트 추가:

```python
async def test_active_timer_expires_run_after_deadline():
    import asyncio
    from datetime import datetime, timezone
    from workflow_engine.engine.approval_timer import ApprovalTimer

    client = FakeMockServerAdapter()
    timer = ApprovalTimer()
    executor = _executor(client, approval_timer=timer)
    timer.set_on_expire(executor.expire_run)
    workflow = load_workflow(Path("workflows/customer_support_auto_reply.yaml"))

    run = await executor.start(workflow, {"inquiry_id": "INQ-002"})
    # 강제로 deadline을 매우 짧게
    run.approval.deadline_at = datetime.now(timezone.utc)
    executor.store.save(run)
    timer.schedule(run.run_id, run.approval.deadline_at)

    await asyncio.sleep(0.1)
    refreshed = executor.store.get(run.run_id)
    assert refreshed.status == RunStatus.TIMED_OUT
    assert refreshed.error.code == "APPROVAL_TIMEOUT"


async def test_approve_cancels_active_timer():
    import asyncio
    from workflow_engine.engine.approval_timer import ApprovalTimer

    client = FakeMockServerAdapter()
    timer = ApprovalTimer()
    executor = _executor(client, approval_timer=timer)
    timer.set_on_expire(executor.expire_run)
    workflow = load_workflow(Path("workflows/customer_support_auto_reply.yaml"))

    run = await executor.start(workflow, {"inquiry_id": "INQ-002"})
    completed = await executor.submit_approval(workflow, run.run_id, "approve")
    assert completed.status == RunStatus.COMPLETED
    # 타이머가 취소되었는지: 추가 sleep 후에도 status 변하지 않음
    await asyncio.sleep(0.05)
    refreshed = executor.store.get(run.run_id)
    assert refreshed.status == RunStatus.COMPLETED


async def test_expire_if_overdue_lazy_expires_when_timer_lost():
    from datetime import datetime, timedelta, timezone

    client = FakeMockServerAdapter()
    executor = _executor(client)  # timer 없음 (시뮬레이트: 프로세스 재시작 후 타이머 손실)
    workflow = load_workflow(Path("workflows/customer_support_auto_reply.yaml"))

    run = await executor.start(workflow, {"inquiry_id": "INQ-002"})
    run.approval.deadline_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    executor.store.save(run)

    refreshed = await executor.expire_if_overdue(run.run_id)
    assert refreshed.status == RunStatus.TIMED_OUT
    assert refreshed.error.code == "APPROVAL_TIMEOUT"
```

- [ ] **Step 4: 전체 테스트 통과**

```bash
python -m pytest -q
```

Expected: 모든 테스트 PASS.

- [ ] **Step 5: Commit**

```bash
git add src/workflow_engine/engine/executor.py src/workflow_engine/bootstrap.py tests/test_executor.py
git commit -m "feat: integrate ApprovalTimer, run_id locks, and expire_if_overdue into executor"
```

---

### Task 26: api/routes.get_workflow_run에 expire_if_overdue 호출

**Files:**
- Modify: `src/workflow_engine/api/routes.py`

- [ ] **Step 1: get_workflow_run 핸들러 갱신**

```python
@app.get(
    "/workflow-runs/{run_id}",
    response_model=WorkflowRun,
    summary="워크플로우 실행 상태 조회",
    description="실행 ID로 현재 상태, 컨텍스트, 노드 상태, 승인 정보를 조회합니다. 승인 대기 중이면 deadline 경과 시 자동으로 TIMED_OUT 상태로 갱신됩니다.",
    tags=["워크플로우 실행"],
)
async def get_workflow_run(run_id: str):
    try:
        return await deps.executor.expire_if_overdue(run_id)
    except RunNotFoundError as exc:
        raise HTTPException(status_code=404, detail="워크플로우 실행을 찾을 수 없습니다.") from exc
```

- [ ] **Step 2: tests/test_api.py에 lazy 만료 테스트 추가**

```python
def test_get_endpoint_lazy_expires_overdue_run(client, deps):
    from datetime import datetime, timedelta, timezone
    started = client.post("/workflow-runs", json={
        "workflow_key": "customer_support_auto_reply",
        "inquiry_id": "INQ-002",
    }).json()
    run_id = started["run_id"]
    # deadline을 강제로 과거로
    run = deps.store.get(run_id)
    run.approval.deadline_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    deps.store.save(run)

    response = client.get(f"/workflow-runs/{run_id}")
    assert response.status_code == 200
    assert response.json()["status"] == "TIMED_OUT"
```

- [ ] **Step 3: 테스트 통과**

```bash
python -m pytest tests/test_api.py -v
```

Expected: 새 테스트 포함 모두 PASS.

- [ ] **Step 4: Commit**

```bash
git add src/workflow_engine/api/routes.py tests/test_api.py
git commit -m "feat: get_workflow_run lazily expires overdue runs"
```

---

### Task 27: RunStoreAdapter에 inquiry index + find_by_inquiry

**Files:**
- Modify: `src/workflow_engine/adapters/run_store.py`
- Modify: `tests/test_run_store.py`

- [ ] **Step 1: 실패하는 테스트 작성/추가 (`tests/test_run_store.py`)**

기존 파일에 추가:

```python
from datetime import datetime, timezone

from workflow_engine.adapters.run_store import RunStoreAdapter
from workflow_engine.domain.run import NodeState, RunStatus, WorkflowRun


def _new_run(run_id: str, inquiry_id: str, status=RunStatus.PENDING) -> WorkflowRun:
    now = datetime.now(timezone.utc)
    return WorkflowRun(
        run_id=run_id,
        workflow_key="customer_support_auto_reply",
        status=status,
        current_node_key=None,
        context={"input": {"inquiry_id": inquiry_id}, "nodes": {}},
        node_states={"x": NodeState()},
        created_at=now,
        updated_at=now,
    )


def test_find_by_inquiry_returns_none_when_unseen():
    store = RunStoreAdapter()
    assert store.find_by_inquiry("INQ-999") is None


def test_find_by_inquiry_returns_latest_run_for_inquiry():
    store = RunStoreAdapter()
    run1 = _new_run("run_1", "INQ-001", status=RunStatus.WAITING_APPROVAL)
    store.save(run1)
    found = store.find_by_inquiry("INQ-001")
    assert found is not None
    assert found.run_id == "run_1"


def test_find_by_inquiry_updates_index_on_save():
    store = RunStoreAdapter()
    run1 = _new_run("run_1", "INQ-001", status=RunStatus.REJECTED)
    store.save(run1)
    run2 = _new_run("run_2", "INQ-001", status=RunStatus.WAITING_APPROVAL)
    store.save(run2)
    found = store.find_by_inquiry("INQ-001")
    # 새 run이 등록되면 그 쪽으로 인덱스 갱신
    assert found.run_id == "run_2"
```

- [ ] **Step 2: 테스트 실패 확인**

```bash
python -m pytest tests/test_run_store.py -v
```

Expected: 새 테스트 FAIL — `find_by_inquiry` 미구현.

- [ ] **Step 3: RunStoreAdapter 갱신**

```python
from workflow_engine.domain.run import WorkflowRun


class RunNotFoundError(Exception):
    pass


class RunStoreAdapter:
    def __init__(self):
        self._runs: dict[str, WorkflowRun] = {}
        self._runs_by_inquiry: dict[str, str] = {}

    def save(self, run: WorkflowRun) -> WorkflowRun:
        self._runs[run.run_id] = run
        inquiry_id = run.context.get("input", {}).get("inquiry_id")
        if inquiry_id is not None:
            self._runs_by_inquiry[inquiry_id] = run.run_id
        return run

    def get(self, run_id: str) -> WorkflowRun:
        try:
            return self._runs[run_id]
        except KeyError as exc:
            raise RunNotFoundError(run_id) from exc

    def list_runs(self) -> list[WorkflowRun]:
        return list(self._runs.values())

    def find_by_inquiry(self, inquiry_id: str) -> WorkflowRun | None:
        run_id = self._runs_by_inquiry.get(inquiry_id)
        if run_id is None:
            return None
        return self._runs.get(run_id)
```

- [ ] **Step 4: 테스트 통과 확인**

```bash
python -m pytest tests/test_run_store.py -v
```

Expected: 모든 테스트 PASS.

- [ ] **Step 5: Commit**

```bash
git add src/workflow_engine/adapters/run_store.py tests/test_run_store.py
git commit -m "feat: add inquiry_id index and find_by_inquiry to RunStoreAdapter"
```

---

### Task 28: 멱등성 통합 테스트 (tests/test_idempotency.py)

**Files:**
- Create: `tests/test_idempotency.py`

- [ ] **Step 1: 테스트 작성**

```python
from datetime import datetime, timezone

from workflow_engine.domain.run import RunStatus


def test_same_inquiry_returns_same_run_when_waiting_approval(client, deps):
    first = client.post("/workflow-runs", json={
        "workflow_key": "customer_support_auto_reply",
        "inquiry_id": "INQ-002",
    }).json()
    second = client.post("/workflow-runs", json={
        "workflow_key": "customer_support_auto_reply",
        "inquiry_id": "INQ-002",
    }).json()
    assert first["run_id"] == second["run_id"]
    assert first["status"] == second["status"]


def test_same_inquiry_returns_same_run_after_completion(client):
    started = client.post("/workflow-runs", json={
        "workflow_key": "customer_support_auto_reply",
        "inquiry_id": "INQ-002",
    }).json()
    client.post(f"/workflow-runs/{started['run_id']}/approval", json={"decision": "approve"})
    second = client.post("/workflow-runs", json={
        "workflow_key": "customer_support_auto_reply",
        "inquiry_id": "INQ-002",
    }).json()
    assert started["run_id"] == second["run_id"]
    assert second["status"] == "COMPLETED"


def test_rejected_inquiry_allows_new_run(client):
    started = client.post("/workflow-runs", json={
        "workflow_key": "customer_support_auto_reply",
        "inquiry_id": "INQ-002",
    }).json()
    client.post(
        f"/workflow-runs/{started['run_id']}/approval",
        json={"decision": "reject", "reason": "내용 부정확"},
    )
    second = client.post("/workflow-runs", json={
        "workflow_key": "customer_support_auto_reply",
        "inquiry_id": "INQ-002",
    }).json()
    assert started["run_id"] != second["run_id"]


def test_timed_out_inquiry_allows_new_run(client, deps):
    from datetime import datetime, timedelta, timezone
    started = client.post("/workflow-runs", json={
        "workflow_key": "customer_support_auto_reply",
        "inquiry_id": "INQ-002",
    }).json()
    run = deps.store.get(started["run_id"])
    run.approval.deadline_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    deps.store.save(run)
    # GET으로 lazy 만료 트리거
    client.get(f"/workflow-runs/{started['run_id']}")
    second = client.post("/workflow-runs", json={
        "workflow_key": "customer_support_auto_reply",
        "inquiry_id": "INQ-002",
    }).json()
    assert started["run_id"] != second["run_id"]
```

- [ ] **Step 2: 테스트 통과**

```bash
python -m pytest tests/test_idempotency.py -v
```

Expected: 4개 PASS.

- [ ] **Step 3: Commit**

```bash
git add tests/test_idempotency.py
git commit -m "test: add idempotency integration tests for inquiry-based natural key"
```

---

### Task 29: tests/test_loader.py 신설

**Files:**
- Create: `tests/test_loader.py`

- [ ] **Step 1: 테스트 작성**

```python
from pathlib import Path

import pytest
import yaml

from workflow_engine.engine.loader import load_workflow


def test_load_workflow_parses_yaml_into_definition(tmp_path: Path):
    yaml_text = """
workflow_key: test_wf
version: "1.0.0"
nodes:
  - key: a
    type: tool
    tool: foo
  - key: b
    type: human_approval
    timeout_seconds: 60
    depends_on: [a]
"""
    path = tmp_path / "wf.yaml"
    path.write_text(yaml_text, encoding="utf-8")
    workflow = load_workflow(path)
    assert workflow.workflow_key == "test_wf"
    assert len(workflow.nodes) == 2
    assert workflow.nodes[0].key == "a"
    assert workflow.nodes[1].timeout_seconds == 60


def test_load_workflow_loads_real_customer_support_yaml():
    workflow = load_workflow(Path("workflows/customer_support_auto_reply.yaml"))
    keys = [node.key for node in workflow.nodes]
    assert "fetch_inquiry" in keys
    assert "wait_for_approval" in keys
    assert "send_reply_email" in keys
```

- [ ] **Step 2: 테스트 통과**

```bash
python -m pytest tests/test_loader.py -v
```

Expected: 2개 PASS.

- [ ] **Step 3: Commit**

```bash
git add tests/test_loader.py
git commit -m "test: add YAML loader tests"
```

---

### Task 30: Phase 4 마무리 검증 — 수동 OpenAI + 수동 timeout

- [ ] **Step 1: 전체 테스트 통과**

```bash
python -m pytest -q
```

Expected: 모든 테스트 PASS.

- [ ] **Step 2: 수동 timeout 만료 확인**

`workflows/customer_support_auto_reply.yaml`의 `timeout_seconds: 1800`을 잠시 `5`로 변경 후:

```bash
python -m workflow_engine.main &
SERVER_PID=$!
sleep 2

RUN_ID=$(curl -s -X POST http://localhost:8000/workflow-runs \
  -H "Content-Type: application/json" \
  -d '{"workflow_key":"customer_support_auto_reply","inquiry_id":"INQ-002"}' \
  | python -c "import sys, json; print(json.load(sys.stdin)['run_id'])")

echo "Started: $RUN_ID"
sleep 7
curl -s http://localhost:8000/workflow-runs/$RUN_ID | python -m json.tool

kill $SERVER_PID
```

Expected: `status: TIMED_OUT`, `error.code: APPROVAL_TIMEOUT`.

원복:
```bash
git checkout workflows/customer_support_auto_reply.yaml
```

- [ ] **Step 3: 수동 OpenAI 호출 (선택)**

`.env`에 `LLM_PROVIDER=openai`와 `OPENAI_API_KEY` 설정 후 위 curl을 실행. 응답의 `body`에 `예상 처리 기한`, `접수 확인 번호`가 포함되는지 육안 확인.

- [ ] **Step 4: tag (선택)**

```bash
git tag refactor-phase-4-complete
```

---

## Phase 5 — README + .env.example + 마무리

---

### Task 31: README 갱신

**Files:**
- Modify: `README.md`

- [ ] **Step 1: README.md 전체 교체**

```markdown
# AI Workflow Builder Mini Engine

고객 문의 자동 응답 시나리오를 처리하는 미니 워크플로우 엔진.

## 기능

1. YAML 워크플로우 정의 (DAG, 순환 검사)
2. 순차 실행 + 노드 간 컨텍스트 전달
3. 외부 호출 transient error에 대한 Exponential Backoff 재시도
4. LLM Tool Use 패턴: Tool / LLM 노드 분리, 표준 입출력 인터페이스
5. Human-in-the-Loop 승인 노드 (능동 타임아웃 포함)
6. inquiry_id 기반 시작 멱등성

## 실행 환경

- Python 3.13
- Docker 및 Docker Compose (Mock API 서버용)

## Mock API 서버 실행

```bash
cd mock-server
docker compose up --build
```

Mock 서버: `http://localhost:8080` (Swagger: `/docs`)

## 워크플로우 엔진 설치

```bash
python3.13 -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev]"
cp .env.example .env
```

## 환경 변수

```
MOCK_API_BASE_URL=http://localhost:8080
MOCK_API_KEY=mock-api-key-12345

LLM_PROVIDER=fake                      # 또는 openai
OPENAI_API_KEY=
OPENAI_MODEL=gpt-4.1-mini              # fallback
OPENAI_CLASSIFY_MODEL=gpt-4.1-mini     # 분류 액션 (가벼운 모델 권장)
OPENAI_GENERATE_MODEL=gpt-4.1-mini     # 생성 액션 (필요 시 큰 모델로 오버라이드)
OPENAI_TEMPERATURE=0
```

## API 서버 실행

```bash
python -m workflow_engine.main
```

Swagger 문서: `http://localhost:8000/docs`

## 호출 예시

```bash
# 워크플로우 시작
curl -X POST http://localhost:8000/workflow-runs \
  -H "Content-Type: application/json" \
  -d '{"workflow_key":"customer_support_auto_reply","inquiry_id":"INQ-002"}'

# 상태 조회
curl http://localhost:8000/workflow-runs/<run_id>

# 승인
curl -X POST http://localhost:8000/workflow-runs/<run_id>/approval \
  -H "Content-Type: application/json" \
  -d '{"decision":"approve"}'

# 거부
curl -X POST http://localhost:8000/workflow-runs/<run_id>/approval \
  -H "Content-Type: application/json" \
  -d '{"decision":"reject","reason":"답변 내용이 부정확함"}'
```

## 디렉토리 구조

```
src/workflow_engine/
├── main.py            # uvicorn 진입점
├── app.py             # FastAPI 인스턴스 + 라우트 wiring
├── bootstrap.py       # 의존성 조립
├── config.py          # Settings
├── api/               # HTTP 인터페이스 정의
│   ├── routes.py
│   └── schemas.py
├── domain/            # 순수 데이터·정책·예외 (외부 의존 없음)
│   ├── workflow.py
│   ├── run.py
│   ├── reply_policy.py
│   └── errors.py
├── engine/            # orchestration
│   ├── executor.py
│   ├── validator.py
│   ├── loader.py
│   ├── input_mapping.py
│   ├── retry.py
│   ├── ports.py
│   ├── registries.py
│   └── approval_timer.py
├── nodes/             # 등록 가능 단위
│   ├── tools.py
│   ├── llm.py
│   └── prompts.py
└── adapters/          # 외부 I/O 구현
    ├── openai.py
    ├── fake_ai.py
    ├── mock_api.py
    └── run_store.py
```

의존 방향: `api → bootstrap → engine + nodes + adapters → domain` (단방향).

## 설계 결정

- **워크플로우 정의**: YAML, `key`는 워크플로우 내부 참조, `type + tool/task`가 재사용 단위.
- **LLM 노드**: 액션 기반 레지스트리 (`task` 필드가 곧 레지스트리 키). 액션마다 다른 어댑터/모델 분리 가능.
- **프롬프트**: `nodes/prompts.py` 상수로 분리, system/user 메시지 분리, `engine/input_mapping`의 `{{ }}` 렌더링 재사용. LangChain 미사용.
- **출력 검증**: classify는 5개 카테고리 화이트리스트, generate는 카테고리별 필수 포함 항목 substring 검증.
- **능동 타임아웃**: per-run `asyncio.Task` (`engine/approval_timer.py`). GET 엔드포인트에 lazy 안전망. 부하 측면에서 폴링보다 효율적.
- **동시성**: `WorkflowExecutor`에 run_id별 `asyncio.Lock`으로 같은 run에 대한 결정/만료 race 차단.
- **멱등성**: `inquiry_id` 자연 키. 활성·COMPLETED run이 있으면 기존 반환, REJECTED/TIMED_OUT/FAILED는 새 run 허용.
- **어댑터 추상화**: `AI` Protocol(`chat_json`)이 프로바이더 중립. 다른 프로바이더는 어댑터 클래스 추가만으로 지원 가능.
- **Composition root**: `bootstrap.py`에 의존성 조립 책임을 모음. `app.py`는 라우트 wiring만 담당.

## 트레이드오프 (안 한 것)

- **영속화**: in-memory 유지. 운영 시 SQLite/Redis로 교체.
- **멀티 프로바이더 어댑터**: AI Protocol 추상화로 충분. 두 번째 구현체는 요구가 생길 때 추가 (YAGNI).
- **노드 병렬 실행**: PDF 선택 과제, 범위 외.
- **LangChain**: 자체 렌더링 ~10줄로 충분, 의존성 비용 회피.
- **LLM 재시도**: 출력 비결정성 회피를 위해 미적용. 노드 단위 최대 1회.

## 확장 포인트

- **새 tool**: `nodes/tools.py`에 클래스 추가 + `bootstrap.py:_assemble`에 등록.
- **새 LLM 액션**: `nodes/llm.py`에 함수 추가 + `nodes/prompts.py`에 템플릿 + `bootstrap.py`에 등록.
- **새 프로바이더**: `adapters/<name>.py` 신설 (`chat_json` 구현) + `bootstrap.py`에서 어댑터 교체.
- **새 워크플로우**: `workflows/<name>.yaml` 추가 + `bootstrap.py:workflow_paths`에 등록.

## 보안

- API Key는 환경변수, `.env`는 `.gitignore` (커밋 금지).
- Mock API Key와 OpenAI API Key는 분리된 환경변수.
- 승인 API는 평가 MVP에서 인증 생략. 운영 시 인증 + 권한 + 감사 로그 필요.
- LLM 프롬프트의 고객 정보는 응답 생성에 필요한 필드만 포함 (이름, 플랜, 상태, 이메일).
- 응답 생성 system prompt에 PDF의 금지 사항 7항목 항상 포함.

## 한계

- Run store / 만료 타이머 / run-level lock / 멱등성 인덱스 모두 in-memory → **단일 worker 전제**. 멀티 worker 또는 영속화 필요 시 외부 저장소(Redis/PostgreSQL)로 이동.
- 노드 병렬 실행 미지원.
- LLM 호출은 노드 단위 최대 1회 (재시도 미적용).
- generate_reply 필수 포함 항목 검증은 substring 매칭. 의미 검증은 별도 LLM judge 등 향후 작업.
- 워크플로우는 `customer_support_auto_reply` 1개 등록.

## 테스트

```bash
python -m pytest -q
```

자동 테스트는 OpenAI 호출 없이 `FakeAI`로 동작. OpenAI 연동은 환경변수 설정 후 수동 검증.
```

- [ ] **Step 2: Commit**

```bash
git add README.md
git commit -m "docs: rewrite README with new architecture, design decisions, tradeoffs"
```

---

### Task 32: 죽은 코드 / 사용하지 않는 import 정리

**Files:**
- Modify: 다양

- [ ] **Step 1: 모든 src/test 파일에서 사용하지 않는 import 제거**

```bash
# 수동 점검: 각 파일을 열어 import 후 미사용 식별자 제거
# (자동화 도구로 ruff 등을 쓸 수 있다면 권장)
```

- [ ] **Step 2: pyproject.toml의 의존성 점검 (변경 없으면 skip)**

`langchain`, `unused` 등이 들어가 있지 않은지 확인.

- [ ] **Step 3: tests/test_executor.py의 `FakeMockServerAdapter` 클래스 — 새 이름과 일관**

기존 `FakeMockServerAdapter`라는 클래스명이 test_executor.py 안에 정의되어 있을 수 있음. `FakeMockAPIAdapter`와 헷갈리지 않도록 확인. test 내부 클래스명은 어차피 외부 영향 없으므로 그대로 두어도 되나, 일관성 위해 외부 어댑터와 혼동 없는 이름이 좋음 (예: `LocalFakeMockAPI`).

- [ ] **Step 4: 전체 테스트 통과**

```bash
python -m pytest -q
```

- [ ] **Step 5: Commit (변경분 있을 때만)**

```bash
git add -A
git commit -m "chore: remove unused imports and tidy test fakes" || true
```

---

### Task 33: 최종 검증

- [ ] **Step 1: 전체 테스트 + Coverage**

```bash
python -m pytest -q
```

Expected: 모든 테스트 PASS.

- [ ] **Step 2: 서버 정상 흐름 수동 검증**

```bash
python -m workflow_engine.main &
SERVER_PID=$!
sleep 2

# 1. 시작
RESP=$(curl -s -X POST http://localhost:8000/workflow-runs \
  -H "Content-Type: application/json" \
  -d '{"workflow_key":"customer_support_auto_reply","inquiry_id":"INQ-002"}')
echo "$RESP" | python -m json.tool
RUN_ID=$(echo "$RESP" | python -c "import sys, json; print(json.load(sys.stdin)['run_id'])")

# 2. 멱등성 (같은 run 반환되어야 함)
RESP2=$(curl -s -X POST http://localhost:8000/workflow-runs \
  -H "Content-Type: application/json" \
  -d '{"workflow_key":"customer_support_auto_reply","inquiry_id":"INQ-002"}')
RUN_ID2=$(echo "$RESP2" | python -c "import sys, json; print(json.load(sys.stdin)['run_id'])")
test "$RUN_ID" = "$RUN_ID2" && echo "Idempotency OK" || echo "Idempotency FAIL"

# 3. 조회
curl -s http://localhost:8000/workflow-runs/$RUN_ID | python -m json.tool

# 4. 승인
curl -s -X POST http://localhost:8000/workflow-runs/$RUN_ID/approval \
  -H "Content-Type: application/json" \
  -d '{"decision":"approve"}' | python -m json.tool

kill $SERVER_PID
```

Expected:
- 1/2/3/4 모두 200 응답
- 1번 status: WAITING_APPROVAL
- 2번 같은 run_id (멱등성 OK)
- 3번 변동 없는 상태 조회
- 4번 status: COMPLETED + send_reply_email node 결과

- [ ] **Step 3: git diff 점검**

```bash
git log --oneline main..HEAD | head -50
git diff main --stat | tail -20
```

예상치 못한 변경 없는지 확인.

- [ ] **Step 4: tag (선택)**

```bash
git tag refactor-complete
```

- [ ] **Step 5: 최종 정리 — 별도 커밋이 없으면 task 종료**

---

## Self-Review Notes

이 plan은 spec의 다음 섹션을 모두 커버한다:

- **Architecture > 디렉토리 구조**: Phase 1 (Tasks 1-9)
- **Component Designs > 1. 능동 타임아웃**: Phase 4 (Tasks 24-25, 30)
- **Component Designs > 2. 동시성 — run_id별 락**: Phase 4 (Task 25)
- **Component Designs > 3. 시작 멱등성**: Phase 4 (Tasks 25, 27, 28)
- **Component Designs > 4. LLM 출력 검증**: Phase 2 (Tasks 10, 11, 15)
- **Component Designs > 5. 프롬프트 분리**: Phase 2 (Task 12)
- **Component Designs > 6. 액션 기반 LLM 레지스트리**: Phase 2 (Tasks 13, 14, 16, 17)
- **Component Designs > 7. 어댑터 변경**: Phase 1 (Task 8) + Phase 2 (Tasks 13, 14)
- **Component Designs > 8. Composition root + ApprovalTimer wiring**: Phase 3 (Tasks 19-22) + Phase 4 (Task 25)
- **Component Designs > 9. Settings 변경**: Phase 3 (Task 18)
- **Data Flow / Error Handling**: Tasks 25, 26, 28에서 검증
- **Testing Strategy**: Phase 1-5 전체에서 TDD로 진행
- **Migration Phases**: 5단계 그대로 매핑
- **Security / Limitations**: Phase 5 README (Task 31)

전체 task 수: 33개. 평균 소요 시간 task당 5-15분 (TDD step 단위로는 2-5분).

Phase 종료 후 검증 체크포인트:
- Phase 1: Task 9
- Phase 2: Task 17
- Phase 3: Task 23
- Phase 4: Task 30
- Phase 5: Task 33
