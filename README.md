# AI Workflow Builder Mini Engine

고객 문의 이메일을 조회하고, `LLM`으로 분류와 답변 생성을 수행한 뒤, 관리자 승인 후 Mock Email API로 발송하는 미니 `workflow engine`입니다. 과제 PDF의 고객 지원 자동 응답 시나리오를 실행 가능한 backend로 구현했습니다.

```text
Inquiry 조회 -> LLM 분류 -> CRM 조회 -> LLM 답변 생성 -> 관리자 승인 -> Email 발송
```

## 과제 요구사항 매핑

| PDF 요구사항 | 구현 방식 | 관련 파일 |
|---|---|---|
| JSON 또는 YAML workflow 정의 | YAML로 workflow를 정의하고 Pydantic model로 로드합니다. | `workflows/customer_support_auto_reply.yaml`, `src/workflow_engine/engine/loader.py`, `src/workflow_engine/domain/workflow.py` |
| `DAG` 기반 실행 순서 결정 및 순환 검사 | `depends_on`으로 graph를 만들고 topological sort 중 cycle을 감지합니다. | `src/workflow_engine/engine/validator.py` |
| 순차 실행 지원 | topological order를 따라 node를 하나씩 실행합니다. | `src/workflow_engine/engine/executor.py` |
| node 간 `context` 전달 | 성공한 node 출력은 `context.nodes.<key>`에 저장되고 후속 node input mapping에서 참조됩니다. | `src/workflow_engine/engine/executor.py`, `src/workflow_engine/engine/input_mapping.py` |
| 오류 발생 시 `Exponential Backoff` retry | transient 외부 오류에만 backoff retry를 적용합니다. | `src/workflow_engine/engine/retry.py`, `src/workflow_engine/nodes/tools.py` |
| `LLM Function Calling` 패턴 추상화 | `Tool`과 `LLM task`를 workflow node로 추상화하고, Tool 결과를 후속 LLM node에 `context`로 피드백합니다. | `src/workflow_engine/engine/ports.py`, `src/workflow_engine/engine/registries.py`, `src/workflow_engine/nodes/llm.py`, `src/workflow_engine/nodes/tools.py` |
| 표준화된 `Tool` 인터페이스 | 모든 Tool은 `execute(input_data) -> dict` 계약을 따릅니다. | `src/workflow_engine/engine/ports.py`, `src/workflow_engine/nodes/tools.py` |
| 상용 LLM API 연동 | OpenAI Chat Completions API를 JSON 응답 모드로 호출합니다. | `src/workflow_engine/adapters/openai.py` |
| Mock CRM / Email API 통합 | Inquiry, CRM, Email API를 Bearer token과 함께 호출합니다. | `src/workflow_engine/adapters/mock_api.py` |
| Human-in-the-Loop 승인 node | 승인 대기 상태에서 run을 pause하고 승인/거부 후 resume 또는 종료합니다. | `src/workflow_engine/engine/executor.py`, `src/workflow_engine/api/routes.py` |
| 승인 timeout 처리 | `ApprovalTimer`로 능동 만료를 처리하고, 조회 시 lazy fallback도 수행합니다. | `src/workflow_engine/engine/approval_timer.py`, `src/workflow_engine/engine/executor.py` |
| 단위 테스트 포함 | validation, mapping, retry, adapters, LLM task, approval, idempotency, API 경로를 검증합니다. | `tests/` |

## 빠른 실행

### 1. Mock API 서버 실행

Docker 사용:

```bash
cd mock-server
docker compose up --build
```

Docker 없이 직접 실행:

```bash
pip install -r mock-server/requirements.txt
python -m uvicorn mock_server:app --app-dir mock-server --host 0.0.0.0 --port 8080
```

Mock API Swagger는 `http://localhost:8080/docs`에서 확인할 수 있습니다.

### 2. Workflow engine 설치

```bash
python3.13 -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev]"
cp .env.example .env
```

### 3. 환경 변수

```env
MOCK_API_BASE_URL=http://localhost:8080
MOCK_API_KEY=mock-api-key-12345

OPENAI_API_KEY=                        # 필수. 미설정 시 서버 기동 실패
OPENAI_MODEL=gpt-4.1-mini              # fallback 기본 모델
OPENAI_CLASSIFY_MODEL=                 # 비면 OPENAI_MODEL 사용
OPENAI_GENERATE_MODEL=                 # 비면 OPENAI_MODEL 사용
OPENAI_TEMPERATURE=0
```

현재 운영 진입점은 OpenAI adapter를 조립하므로 `OPENAI_API_KEY`가 필요합니다. 자동 테스트는 `build_test_dependencies()`가 `FakeAI`를 주입하므로 OpenAI API를 호출하지 않습니다.

### 4. API 서버 실행

```bash
python -m workflow_engine.main
```

Workflow engine Swagger는 `http://localhost:8000/docs`에서 확인할 수 있습니다.

## API 사용 예시

Workflow의 시작점은 Email API가 아니라 Inquiry API에서 조회한 문의 데이터입니다. Email API는 승인 이후 최종 발송 단계에서만 호출됩니다.

```bash
# workflow 시작: fetch/classify/lookup/generate 실행 후 WAITING_APPROVAL 반환
curl -s -X POST http://localhost:8000/workflow-runs \
  -H "Content-Type: application/json" \
  -d '{"workflow_key":"customer_support_auto_reply","inquiry_id":"INQ-002"}'
```

```bash
# 상태 조회
curl -s http://localhost:8000/workflow-runs/<run_id>
```

```bash
# 승인: send_reply_email 실행 후 COMPLETED
curl -s -X POST http://localhost:8000/workflow-runs/<run_id>/approval \
  -H "Content-Type: application/json" \
  -d '{"decision":"approve"}'
```

```bash
# 거부: REJECTED 종료, email 발송 없음
curl -s -X POST http://localhost:8000/workflow-runs/<run_id>/approval \
  -H "Content-Type: application/json" \
  -d '{"decision":"reject","reason":"답변 내용이 부정확함"}'
```

## Workflow 정의

Workflow는 `workflows/customer_support_auto_reply.yaml`에 정의되어 있습니다. PDF는 5단계 흐름을 제시하지만, 구현에서는 Inquiry 조회를 명시적인 `fetch_inquiry` Tool node로 모델링해 6개 node로 구성했습니다.

```text
fetch_inquiry -> classify_inquiry
              -> lookup_customer
classify_inquiry + lookup_customer -> generate_reply
generate_reply -> wait_for_approval -> send_reply_email
```

`key`는 workflow 안에서 node 출력을 참조하기 위한 역할명입니다. 재사용 가능한 실행 단위는 `type + tool/task` 조합입니다. 예를 들어 `lookup_customer`는 이 workflow의 역할명이고, 실제 실행 단위는 `type: tool`과 `tool: crm_lookup`입니다.

각 node의 출력은 `context.nodes.<key>`에 저장됩니다. 후속 node는 `{{ nodes.lookup_customer.customer }}` 같은 input mapping으로 이전 결과를 읽습니다.

## 아키텍처

런타임 조립 흐름은 `main -> bootstrap -> engine/nodes/adapters`를 중심으로 둡니다.

```text
main
  -> bootstrap
      -> engine
      -> nodes
      -> adapters
      -> domain
  -> app/api
```

- `main`: `Settings`를 읽고 FastAPI 앱을 띄우는 진입점
- `bootstrap`: `RunStore`, `MockAPIAdapter`, `OpenAI/FakeAI`, registry, executor를 조립하는 composition root
- `engine`: workflow loading, validation, execution, retry, approval timeout 처리
- `nodes`: workflow에 등록 가능한 `Tool`과 `LLM task` 구현
- `adapters`: OpenAI, Mock API, FakeAI, in-memory RunStore 같은 외부 I/O 구현
- `app/api`: 조립된 executor를 HTTP endpoint로 노출하는 얇은 layer
- `domain`: workflow/run model, reply policy, error 정의

요청 처리 흐름:

```text
POST /workflow-runs
  -> api route
  -> executor.start()
  -> workflow validation
  -> nodes 실행
  -> adapters 호출
  -> WAITING_APPROVAL 반환
```

## 주요 설계 결정

**YAML workflow**

Workflow는 평가자가 읽고 수정하기 쉬워야 하므로 YAML을 사용했습니다. node 간 연결은 `depends_on`으로 표현하고, 실행 전 validator가 dependency와 cycle을 확인합니다.

**`key`와 `type + tool/task` 분리**

`key`는 workflow-local 이름이고, `type + tool/task`는 실제 실행 단위입니다. 이렇게 나누면 같은 Tool을 다른 workflow에서 다른 역할명으로 재사용할 수 있습니다.

**`Tool` / `LLM` node abstraction**

과제의 `LLM Function Calling` 요구는 OpenAI tool-call API를 그대로 노출하기보다 workflow node로 추상화했습니다. 이 시나리오는 고정된 DAG 흐름이므로 모델이 자율적으로 Tool을 선택하는 agent loop보다, Tool 결과를 `context`에 저장하고 후속 LLM node가 참조하는 구조가 더 단순하고 검증 가능합니다.

**Prompt 조립과 OpenAI 호출 분리**

`nodes/llm.py`는 prompt 조립, 정책 주입, 출력 검증을 담당합니다. `adapters/openai.py`는 system/user 메시지를 받아 JSON 응답을 호출하는 역할만 갖습니다.

**Human approval pause/resume**

`wait_for_approval` node에 도달하면 run snapshot을 저장하고 `WAITING_APPROVAL` 상태로 멈춥니다. 승인 시 남은 node부터 실행하고, 거부 시 email 발송 없이 `REJECTED`로 종료합니다.

**승인 timeout**

`ApprovalTimer`는 per-run `asyncio.Task`로 deadline에 run을 `TIMED_OUT` 처리합니다. 프로세스 재시작 등으로 timer가 손실되는 경우를 보완하기 위해 `GET /workflow-runs/{run_id}`에서도 deadline을 확인합니다.

**`inquiry_id` 기반 멱등성**

같은 inquiry로 활성 run 또는 완료 run이 있으면 기존 run을 반환합니다. 이미 완료된 문의에 중복 답장을 보내지 않기 위한 정책입니다. `REJECTED`, `TIMED_OUT`, `FAILED`는 재시도 의미로 새 run 생성을 허용합니다.

## LLM 응답 정책

과제의 맞춤형 응답 조건은 `src/workflow_engine/domain/reply_policy.py`와 `src/workflow_engine/nodes/prompts.py`에 반영했습니다.

- `classify_email`은 `billing`, `technical`, `account`, `feature_request`, `general` 중 하나만 허용합니다.
- `generate_reply` prompt에는 category별 tone/guideline, plan별 차별화 rule, 금지 사항을 포함합니다.
- `generate_reply` 출력은 `subject`와 `body`가 비어 있지 않은지 확인합니다.
- category별 필수 포함 항목은 prompt guide와 Human approval 단계에서 검수합니다.

이 검증은 LLM 응답을 완전히 의미적으로 보장하지는 않지만, 과제 MVP에서는 PDF 정책을 prompt에 명시하고 사람이 승인 단계에서 최종 검수하는 데 초점을 맞췄습니다.

## 오류 처리와 Retry

Retry는 transient 외부 오류에만 적용합니다.

Retry 대상:

- HTTP timeout
- network transport error
- HTTP `408`, `429`, `500`, `502`, `503`, `504`

Retry하지 않는 대상:

- workflow validation error
- input mapping error
- invalid LLM output
- human rejection
- authentication/authorization error

retry exhausted 시 run과 해당 node는 `FAILED`로 기록됩니다.

## 테스트

```bash
python -m pytest -q
```

테스트는 OpenAI 실제 호출 없이 `FakeAI`와 test dependencies로 동작합니다. 주요 검증 범위는 다음과 같습니다.

- workflow loading / validation
- input mapping
- retry
- Tool contracts
- Mock API adapter
- OpenAI adapter
- LLM task validation
- approval timer
- idempotency
- executor pause/resume/failure
- API endpoints

OpenAI 연동은 `.env`에 `OPENAI_API_KEY`를 설정한 뒤 수동으로 확인합니다.

## 기술 스택 선택 근거

- `Python 3.13`: 과제 권장 언어이며, 비동기 HTTP 처리와 테스트 생태계가 충분합니다.
- `FastAPI`: 짧은 코드로 API endpoint와 Swagger 문서를 함께 제공할 수 있어 평가자가 동작을 확인하기 쉽습니다.
- `Pydantic` / `pydantic-settings`: workflow/run schema와 환경변수 설정을 명시적으로 검증하기 위해 사용했습니다.
- `httpx`: Mock API와 같은 외부 HTTP 호출을 async로 처리하고 timeout/transport error를 retry 정책과 연결하기 쉽습니다.
- `PyYAML`: workflow 정의를 사람이 읽고 수정하기 쉬운 YAML 파일로 관리하기 위해 사용했습니다.
- `OpenAI SDK`: 상용 LLM 연동 요구사항을 직접 만족하고, adapter 경계 뒤로 숨겨 다른 provider로 확장할 수 있게 했습니다.
- `pytest` / `pytest-asyncio`: executor, adapter, approval flow 같은 async 경로를 단위 테스트로 검증하기 위해 사용했습니다.

## 보안

- **인증 정보 관리**: OpenAI API key는 환경변수로 주입하고 repository에 커밋하지 않습니다. `.env`는 `.gitignore` 대상이며, `.env.example`에는 값이 비어 있는 placeholder만 둡니다.
- **외부 API 인증**: Mock API key와 OpenAI API key는 분리합니다. Mock API 호출에는 `Authorization: Bearer mock-api-key-12345`를 사용합니다.
- **권한 통제**: 승인 API는 과제 MVP에서 인증을 생략했습니다. 운영 환경에서는 관리자만 승인/거부할 수 있도록 authentication, authorization, audit log가 필요합니다.
- **데이터 최소화**: LLM prompt에는 응답 생성에 필요한 고객 필드만 포함합니다. 내부 시스템 구조, 다른 고객 사례, 보안 우회 방법은 prompt 정책에서 금지합니다.
- **비밀값 노출 방지**: README와 테스트는 실제 OpenAI key를 요구하지 않으며, 자동 테스트는 `FakeAI`를 주입해 외부 LLM 호출과 비용 발생을 피합니다.

## 한계와 트레이드오프

- RunStore, approval timer, run-level lock, idempotency index는 모두 in-memory입니다. 단일 worker를 전제로 하며, 운영 전환 시 Redis/PostgreSQL 같은 외부 저장소가 필요합니다.
- node 병렬 실행은 지원하지 않습니다. PDF에서 병렬 실행은 선택 과제이므로 범위에서 제외했습니다.
- LLM 호출은 node 단위 최대 1회이며 retry하지 않습니다. 비결정적 출력을 반복 호출하는 대신 실패를 명확히 드러내는 쪽을 선택했습니다.
- `generate_reply`의 필수 포함 항목은 prompt와 Human approval 단계에서 검수합니다. 자동 의미 검증이 필요하면 별도 LLM judge나 rule engine이 필요합니다.
- 등록된 workflow는 `customer_support_auto_reply` 하나입니다.
- multi-provider는 `AI` protocol로 확장 지점만 준비했고, 실제 adapter는 OpenAI만 구현했습니다.
