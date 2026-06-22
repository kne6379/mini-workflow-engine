# AI Workflow Builder — Mini Engine

YAML로 정의한 DAG를 받아 LLM 분류, Tool 호출, Human 승인 노드를 순차 실행하는 워크플로우 실행 엔진입니다. 고객 지원 자동 응답 시나리오 (`Inquiry → Classify → CRM → Generate → Approve → Email`) 를 6노드 워크플로우로 구현했습니다.

---

## 1. 빠른 실행

### 1.1 Docker Compose

```bash
cp .env.example .env
# .env의 OPENAI_API_KEY 값을 채웁니다.
docker compose up --build
```

- Mock API Swagger: http://localhost:8080/docs
- Workflow Engine Swagger: http://localhost:8000/docs

### 1.2 환경 변수

| 변수 | 기본값 | 설명 |
|---|---|---|
| `MOCK_API_BASE_URL` | `http://localhost:8080` | Mock API 주소 |
| `MOCK_API_KEY` | `mock-api-key-12345` | Mock API 인증 키 |
| `OPENAI_API_KEY` | (필수) | 미설정 시 부팅 실패 |
| `OPENAI_MODEL` | `gpt-4.1-mini` | 분류·생성 공용 fallback |
| `OPENAI_CLASSIFY_MODEL` | `""` | 비면 `OPENAI_MODEL` 사용 |
| `OPENAI_GENERATE_MODEL` | `""` | 비면 `OPENAI_MODEL` 사용 |
| `OPENAI_TEMPERATURE` | `0` | |

자동 테스트는 `FakeAI`를 주입하므로 OpenAI 키 없이 실행됩니다.

### 1.3 호출 예시

워크플로우 키: `customer_support_auto_reply`

```bash
# 워크플로우 시작 (fetch → classify → lookup → generate 까지 실행 후 일시정지)
curl -s -X POST http://localhost:8000/workflow-runs \
  -H "Content-Type: application/json" \
  -d '{"workflow_key":"customer_support_auto_reply","inquiry_id":"INQ-002"}'

# 상태 조회 (deadline 경과 시 자동 TIMED_OUT 갱신)
curl -s http://localhost:8000/workflow-runs/<run_id>

# 승인 → send_reply_email 실행 후 COMPLETED
curl -s -X POST http://localhost:8000/workflow-runs/<run_id>/approval \
  -H "Content-Type: application/json" \
  -d '{"decision":"approve"}'

# 거부 → 메일 발송 없이 REJECTED 종료
curl -s -X POST http://localhost:8000/workflow-runs/<run_id>/approval \
  -H "Content-Type: application/json" \
  -d '{"decision":"reject","reason":"답변 내용 부정확"}'
```

---

## 2. 시스템 아키텍처

### 2.1 런타임 조립 구조

YAML 정의가 어떻게 로드되어 외부 시스템까지 도달하는지의 호출 경로입니다.

```text
┌──────────────────────────────────────────────────────────────┐
│ HTTP Client (curl, Swagger UI)                               │
└───────────────┬──────────────────────────────────────────────┘
                │ POST /workflow-runs
                │ POST /workflow-runs/{id}/approval
                │ GET  /workflow-runs/{id}
                ▼
┌──────────────────────────────────────────────────────────────┐
│ FastAPI App  (src/app.py, src/api/routes.py)                 │
│ ─ load_workflow(YAML)                                        │
└───────────────┬──────────────────────────────────────────────┘
                ▼
┌──────────────────────────────────────────────────────────────┐
│ WorkflowExecutor  (src/engine/executor.py)                   │
│ ─ validate_workflow + topological_sort                       │
│ ─ Tool input/output schema 검증                               │
│ ─ RetryExecutor, ApprovalTimer, RunStoreAdapter              │
│ ─ pause / resume / fail / expire                             │
└───────────────┬──────────────────────────────┬───────────────┘
                │                              │
                ▼                              ▼
┌──────────────────────────────┐  ┌────────────────────────────┐
│ ToolRegistry                 │  │ AITaskRegistry             │
│ ├─ inquiry_get               │  │ ├─ classify_email          │
│ ├─ crm_lookup                │  │ └─ generate_reply          │
│ └─ email_send                │  │    (schema + prompt)       │
└───────────────┬──────────────┘  └──────────────┬─────────────┘
                ▼                                ▼
┌──────────────────────────────┐  ┌────────────────────────────┐
│ MockAPIAdapter               │  │ OpenAIAdapter              │
│ (httpx + auth header)        │  │ (json_object mode)        │
└───────────────┬──────────────┘  └──────────────┬─────────────┘
                ▼                                ▼
┌──────────────────────────────┐  ┌────────────────────────────┐
│ Mock API :8080               │  │ OpenAI Chat Completions    │
│ Inquiry / CRM / Email        │  │ API                        │
└──────────────────────────────┘  └────────────────────────────┘
```

상태는 `RunStoreAdapter` (in-memory) 가 보관합니다. `bootstrap.build_dependencies` 가 모든 컴포넌트를 한 곳에서 조립하는 composition root입니다.

### 2.2 워크플로우 DAG

`workflows/customer_support_auto_reply.yaml` 의 6개 노드 의존 관계입니다.

```text
                 ┌────────────────────┐
                 │   fetch_inquiry    │   tool · inquiry_get
                 │   (Mock Inquiry)   │
                 └─────────┬──────────┘
                           │
              ┌────────────┴────────────┐
              ▼                         ▼
   ┌────────────────────┐    ┌────────────────────┐
   │  classify_inquiry  │    │   lookup_customer  │
   │  llm · classify    │    │   tool · crm_lookup│
   │  retry: 3          │    │                    │
   └─────────┬──────────┘    └─────────┬──────────┘
             │                         │
             └────────────┬────────────┘
                          ▼
               ┌────────────────────┐
               │   generate_reply   │   llm · generate_reply
               │   retry: 3         │   (category + customer + policy)
               └─────────┬──────────┘
                         │
                         ▼
               ┌────────────────────┐
               │  wait_for_approval │   human_approval
               │  timeout: 60s      │   → WAITING_APPROVAL (pause)
               └─────────┬──────────┘
                         │  approve
                         ▼
               ┌────────────────────┐
               │  send_reply_email  │   tool · email_send
               │  retry: 5          │   (Mock Email, 10% 503)
               └────────────────────┘
```

각 노드의 출력은 `context.nodes.<key>` 에 저장되며, 후속 노드는 `{{ nodes.fetch_inquiry.inquiry.subject }}` 같은 input mapping으로 참조합니다.

### 2.3 실행 상태 전이

```text
PENDING ──► RUNNING ──► WAITING_APPROVAL ──► RUNNING ──► COMPLETED
              │                │   │                       
              │                │   └── reject ─► REJECTED  
              │                └────── timeout ► TIMED_OUT 
              └──────────── 노드 실패 ────────► FAILED      
```

## 3. Workflow 정의 규약

### 3.1 노드 스키마 (`src/domain/workflow.py`)

| 필드 | 타입 | 비고 |
|---|---|---|
| `key` | str | workflow-local 식별자. `context.nodes` 에서 출력 참조 시 사용 |
| `type` | `tool` \| `llm` \| `human_approval` | 실행 방식 |
| `tool` | str | `type=tool` 일 때 `ToolRegistry` 키 |
| `task` | str | `type=llm` 일 때 `AITaskRegistry` 키 |
| `depends_on` | list[str] | DAG 간선 |
| `inputs` | dict | input mapping 템플릿 (`{{ ... }}`) |
| `timeout_seconds` | int | `human_approval` 전용 |
| `retry.max_attempts` | int | 생략 시 단일 시도 |

### 3.2 노드 입출력 스키마

Tool 노드는 `input_model` 과 `output_model` 로 Pydantic 스키마를 노출하고, `WorkflowExecutor` 가 Tool 실행 전후에 입력 payload와 adapter 응답을 검증합니다. 검증된 출력은 `context.nodes.<key>` 에 저장됩니다.

| Tool | Input schema | Output schema |
|---|---|---|
| `inquiry_get` | `InquiryGetInput` | `InquiryGetOutput` |
| `crm_lookup` | `CRMLookupInput` | `CRMLookupOutput` |
| `email_send` | `EmailSendInput` | `EmailSendOutput` |

LLM task도 입력과 JSON 응답을 Pydantic 스키마로 검증합니다.

| LLM task | Input schema | Output schema |
|---|---|---|
| `classify_email` | `ClassifyEmailInput` | `ClassifyEmailOutput` |
| `generate_reply` | `GenerateReplyInput` | `GenerateReplyOutput` |

### 3.3 input mapping 규칙 (`src/engine/input_mapping.py`)

- 단일 토큰 (`"{{ nodes.fetch_inquiry.inquiry }}"`) → 원본 객체 그대로 전달
- 혼합 문자열 (`"제목: {{ subject }}"`) → 문자열 치환
- 경로는 `context.input.*` 또는 `context.nodes.<key>.*`
- 경로 미존재 시 `InputMappingError` (retry 대상 아님)

### 3.4 워크플로우 검증 (`src/engine/validator.py`)

부팅 시점이 아니라 `executor.start()` 시점에 1회 수행합니다.
- 노드 키 중복
- `depends_on` 미존재 노드 참조
- 타입별 필수 필드 (`tool`/`task`/`timeout_seconds`)
- `topological_sort` 결과로 사이클 감지 (Kahn 알고리즘)

---

## 4. 아키텍처 결정 배경

### 4.1 YAML + DAG 순차 실행
평가자가 읽고 수정하기 쉬운 YAML로 워크플로우를 표현하고, `depends_on` 으로 그래프를 구성합니다. 실행기는 DAG 검증 후 토폴로지 순서대로 노드를 순차 실행합니다. 각 노드의 입력, 출력, 실패 지점이 실행 상태에 남기 때문에 승인 대기와 외부 API 실패를 추적하기 쉽습니다.

### 4.2 `key` 와 `type + tool/task` 의 분리
`key` 는 워크플로우 내부 역할명, `type + tool/task` 는 실제 실행 단위입니다. 같은 `crm_lookup` Tool을 다른 워크플로우에서 다른 역할명으로 재사용할 수 있고, YAML이 read-friendly 해집니다.

### 4.3 LLM Function Calling 의 추상화 방향
OpenAI Function Calling API를 그대로 노출하지 않고, **Tool 결과를 `context` 에 저장 → 후속 LLM 노드가 input mapping으로 참조**하는 구조로 추상화했습니다. 이 시나리오는 DAG가 고정되어 있어, 모델이 자율적으로 Tool 을 선택하는 agent loop보다 결정적이고 검증 가능한 파이프라인이 더 적합합니다.

Tool 입출력 계약은 executor에서 강제하고, LLM task 입출력 계약은 각 task 함수에서 Pydantic 스키마로 검증합니다.

### 4.4 Human-in-the-Loop pause / resume
`human_approval` 노드 도달 시 run을 `WAITING_APPROVAL` 로 저장하고 즉시 반환합니다. `submit_approval` 호출 시 토폴로지 순서의 **승인 노드 다음 노드부터** 재개합니다. 거부 시 메일 발송 없이 `REJECTED` 종료합니다.

### 4.5 승인 타임아웃의 이중 안전망
- **능동**: `ApprovalTimer` 가 per-run `asyncio.Task` 로 deadline 까지 대기 후 `TIMED_OUT` 처리
- **수동(lazy)**: `GET /workflow-runs/{run_id}` 응답 직전에 deadline 경과 여부를 재확인

프로세스 재시작 등으로 in-memory 타이머가 손실되어도 조회 시점에 만료가 반영됩니다.

### 4.6 Retry 범위 한정
Retry는 `render_inputs` 이후의 노드 실행 단위를 감쌉니다. Tool 노드는 input schema 검증, 외부 호출, output schema 검증이 같은 retry 단위에 있고, LLM 노드는 task 내부의 입력 검증, LLM 호출, 출력 검증이 같은 retry 단위에 있습니다. `render_inputs` 같은 context 경로 오류는 retry budget을 소비하지 않고 즉시 `FAILED` 로 떨어집니다. 정책은 노드별 YAML 선언으로만 활성화하고 (`retry.max_attempts`), backoff 곡선은 `WorkflowExecutor.default_retry_policy` 기본값 (`0.5s × 2 → cap 5s`) 을 사용합니다.

| 노드 | retry | 근거 |
|---|---|---|
| `fetch_inquiry` / `lookup_customer` | 없음 | mock GET/POST 안정적 |
| `classify_inquiry` / `generate_reply` | 3 | OpenAI rate limit / 일시 5xx |
| `wait_for_approval` | 없음 | human_approval 은 retry inert |
| `send_reply_email` | 5 | mock email API 가 10% 확률 503 |

### 4.7 `inquiry_id` 멱등성
같은 inquiry로 활성(`PENDING`/`RUNNING`/`WAITING_APPROVAL`) 또는 `COMPLETED` run이 있으면 새로 만들지 않고 기존 run을 반환합니다. 동일 문의에 중복 답장이 나가지 않게 하기 위함입니다. `REJECTED`/`TIMED_OUT`/`FAILED` 는 재시도 의미로 새 run 생성을 허용합니다.

### 4.8 Prompt 조립과 LLM 호출의 분리
`src/nodes/llm.py` 는 입력 스키마 검증, prompt 조립, 정책 (`reply_policy`) 주입, 출력 스키마 검증만 담당합니다. `src/adapters/openai.py` 는 system/user 메시지를 받아 `response_format=json_object` 로 호출하는 얇은 어댑터입니다. provider 교체 시 `AI` 포트만 새로 구현하면 됩니다.

---

## 5. 기술 스택 선택 근거

| 스택 | 사용 이유 |
|---|---|
| **Python 3.13** | async I/O 기반 워크플로우 실행과 타입 힌트 중심 구현에 적합합니다. |
| **FastAPI** | 표준 Python 타입 힌트로 요청/응답 검증을 선언하고 async 엔드포인트를 구성할 수 있습니다. |
| **Pydantic v2 / pydantic-settings** | 워크플로우 정의, 실행 상태, 환경변수 검증을 명시적인 모델로 관리합니다. |
| **httpx** | Mock API 호출을 async client로 처리하고 timeout/error 흐름을 retry와 연결합니다. |
| **PyYAML** | 워크플로우 정의를 코드와 분리해 사람이 읽고 수정하기 쉽게 유지합니다. |
| **OpenAI SDK** | LLM 호출부를 adapter 뒤에 두고 JSON 응답 기반으로 분류/생성 결과를 검증합니다. |
| **pytest / pytest-asyncio / respx** | async 실행 흐름, HTTP adapter, retry, approval 상태 전이를 테스트합니다. |

---

## 6. 보안 고려사항

| 영역 | 적용 |
|---|---|
| **시크릿 관리** | OpenAI / Mock API 키는 환경변수로 주입. `.env` 는 `.gitignore`, `.env.example` 에는 placeholder 만 둠 |
| **외부 API 인증** | Mock API 호출 시 인증 헤더를 포함. Mock 키와 OpenAI 키는 분리 |
| **권한 통제 (한계)** | 승인 API는 MVP 기준 인증 생략. 운영 전환 시 관리자 인증 / 역할 검증 / audit log 필요 |
| **데이터 최소화** | LLM prompt 에는 응답 생성에 필요한 고객 필드만 포함. 내부 시스템 구조·타 고객 사례·보안 우회·구체 금액·확정되지 않은 일정 등은 system prompt 에서 명시적으로 금지 |
| **비용·노출 방지** | 자동 테스트는 `FakeAI` 로 외부 LLM 호출 차단. README · 테스트 어디에도 실제 키를 요구하지 않음 |

---

## 7. 테스트

```bash
uv run --extra dev pytest -q
```

16개 테스트 파일이 다음 영역을 커버합니다.

| 영역 | 파일 |
|---|---|
| Workflow loading / validation | `test_loader.py`, `test_validator.py` |
| Input mapping | `test_input_mapping.py` |
| Retry (exponential backoff) | `test_retry.py` |
| Tool / AI registry / Tool 계약 | `test_tools.py`, `test_ai_registry.py` |
| LLM task 출력 검증 / prompt 렌더링 | `test_llm_tasks.py`, `test_prompts.py` |
| Adapter (Mock API / OpenAI / FakeAI) | `test_mock_api_adapter.py`, `test_openai_adapter.py`, `test_fake_ai.py` |
| Executor (pause / resume / 실패) | `test_executor.py` |
| Approval timer / 멱등성 / RunStore | `test_approval_timer.py`, `test_idempotency.py`, `test_run_store.py` |
| HTTP 엔드포인트 | `test_api.py` |

OpenAI 실제 호출은 `FakeAI` 주입으로 차단됩니다. 실제 LLM 연동 검증은 `.env` 에 `OPENAI_API_KEY` 를 설정한 뒤 수동으로 수행합니다.
