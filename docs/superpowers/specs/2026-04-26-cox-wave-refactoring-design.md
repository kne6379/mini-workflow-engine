# Cox-Wave Workflow Engine Refactoring Design

작성일: 2026-04-26
대상 브랜치: `codex/mini-workflow-engine`
선행 문서: `docs/superpowers/specs/2026-04-26-mini-workflow-engine-design.md` (기존 MVP 설계)

## Goal

기존 MVP 워크플로우 엔진을 평가 가독성과 코드 구조 양쪽에서 정돈한다. 평가 기준은 두 가지:

1. **PDF 요구사항 누락분 메우기**: 능동 타임아웃, generate 출력 검증, 멱등성, system/user 메시지 분리, 액션별 모델 분리.
2. **코드 구조 정리**: top-level 평면화 해소, 명명 모호성 제거, 의존성 조립 책임 분리.

영속화, 구조화 로깅, 멀티 프로바이더 어댑터, 노드 병렬 실행은 범위 외이며 README 한계로 명시한다.

## Scope

### 포함

- 디렉토리 재구조화 (옵션 A: 5개 폴더 + app.py 최상위)
- 승인 노드의 능동 타임아웃 처리 (`ApprovalTimer`)
- run_id별 `asyncio.Lock`으로 동시성 race 차단
- inquiry_id 자연 키 기반 시작 멱등성
- LLM 출력 검증 강화 (`generate_reply`의 카테고리별 필수 포함 항목)
- 프롬프트 분리 + system/user 메시지 분리
- 액션 기반 LLM 레지스트리 (액션별 모델 분리 가능)
- Composition root 분리 (`bootstrap.py`)
- README 갱신 (설계 배경, 트레이드오프, 확장 포인트, 한계)

### 제외

- Run 영속화 (in-memory 유지)
- 구조화 로깅 / 트레이싱
- 통합 Docker Compose (워크플로우 엔진은 로컬 실행)
- Anthropic 등 추가 프로바이더 어댑터 신설
- 노드별 `WorkflowNode.model` 필드 추가
- 노드 병렬 실행
- LLM 호출에 대한 재시도

## Architecture

### 디렉토리 구조

```
src/workflow_engine/
├── main.py            # uvicorn 진입점
├── app.py             # create_app(deps) — FastAPI 인스턴스 + 라우트 wiring
├── bootstrap.py       # 의존성 조립 (build_dependencies, build_test_dependencies)
├── config.py          # Settings
├── api/               # HTTP 인터페이스 정의 전용
│   ├── routes.py      # 엔드포인트 함수 + register_routes
│   └── schemas.py     # 요청/응답 DTO
├── domain/            # 순수 데이터 모델 + 정책 데이터 + 예외 (외부 의존 없음)
│   ├── workflow.py    # WorkflowDefinition, WorkflowNode
│   ├── run.py         # WorkflowRun, NodeState, ApprovalState, *Status
│   ├── reply_policy.py # CATEGORIES, CATEGORY_GUIDELINES, CATEGORY_TONE,
│   │                   # PLAN_RULES, PROHIBITED_RULES, REQUIRED_INCLUDES
│   └── errors.py      # WorkflowEngineError, WorkflowValidationError, InputMappingError,
│                      # LLMOutputValidationError, ApprovalTimeoutError
├── engine/            # orchestration: I/O 추상에만 의존
│   ├── executor.py
│   ├── validator.py   # (구) workflow_validator
│   ├── loader.py      # (구) workflow_loader
│   ├── input_mapping.py
│   ├── retry.py
│   ├── ports.py       # Tool, AI, RunStore Protocol
│   ├── registries.py  # ToolRegistry, AITaskRegistry
│   └── approval_timer.py # ApprovalTimer
├── nodes/             # 등록 가능한 단위
│   ├── tools.py       # InquiryGetTool, CRMLookupTool, EmailSendTool
│   ├── llm.py         # classify_email, generate_reply 함수 + _validate_reply
│   └── prompts.py     # system/user 템플릿 상수 + render_template
└── adapters/          # 외부 시스템 I/O 구현
    ├── openai.py      # OpenAIAdapter
    ├── fake_ai.py     # FakeAI (테스트용)
    ├── mock_api.py    # MockAPIAdapter (외부 Mock 서버 클라이언트)
    └── run_store.py   # RunStoreAdapter (in-memory)
```

### 의존 방향

```
api → bootstrap → engine + nodes + adapters → domain
```

`domain/`은 외부에 의존하지 않는다. 다른 레이어가 `domain/`의 데이터·예외만 사용한다.

### 명명 규칙

- 어댑터 파일은 외부 시스템 또는 구현 종류 이름 그대로 (`openai.py`, `mock_api.py`).
- Python 3 absolute import 덕에 `adapters/openai.py`와 외부 SDK `openai`는 충돌하지 않는다.
- `_adapter` 접미사 같은 redundant 접두사는 사용하지 않는다.

## Component Designs

### 1. 능동 타임아웃 (`engine/approval_timer.py`)

per-run `asyncio.Task` 기반. 등록·취소·만료 콜백 책임만 가진다.

```python
class ApprovalTimer:
    def __init__(self) -> None:
        self._tasks: dict[str, asyncio.Task] = {}
        self._on_expire: Callable[[str], Awaitable[None]] | None = None

    def set_on_expire(self, callback: Callable[[str], Awaitable[None]]) -> None:
        self._on_expire = callback

    def schedule(self, run_id: str, deadline_at: datetime) -> None:
        assert self._on_expire is not None, "set_on_expire must be called before schedule"
        # 직전 태스크가 있으면 cancel 후 재등록 (방어적)
        if (existing := self._tasks.get(run_id)) is not None and not existing.done():
            existing.cancel()
        seconds = max(0.0, (deadline_at - datetime.now(timezone.utc)).total_seconds())
        self._tasks[run_id] = asyncio.create_task(self._wait_and_expire(run_id, seconds))

    async def _wait_and_expire(self, run_id: str, seconds: float) -> None:
        try:
            await asyncio.sleep(seconds)
        except asyncio.CancelledError:
            return
        await self._on_expire(run_id)
        self._tasks.pop(run_id, None)

    def cancel(self, run_id: str) -> None:
        task = self._tasks.pop(run_id, None)
        if task is not None and not task.done():
            task.cancel()
```

#### 흐름

- **등록**: 승인 노드 진입 시 `WorkflowExecutor`가 `schedule(run_id, deadline_at)` 호출.
- **조기 결정**: `submit_approval` 시작부에서 `cancel(run_id)` 호출.
- **만료**: 타이머가 `_on_expire(run_id)` 호출 → executor가 status 체크 후 `TIMED_OUT` 전환.
- **lazy 안전망**: `GET /workflow-runs/{id}` 진입 시 `WAITING_APPROVAL` + deadline 경과 발견 시 `TIMED_OUT` 전환.

#### 부하 평가

sleeping `asyncio.Task`는 ~2KB/개, idle CPU 0. 동시 1000개 대기에도 메모리 2MB. 30분 timeout 1개 task의 메모리·CPU 비용은 사실상 0. 폴링 방식보다 효율적.

#### 한계

- 프로세스 재시작 시 타이머 손실. lazy GET 검사가 부분 보완.
- 단일 프로세스 전제 (멀티 worker 환경에서는 동작 안 함).

### 2. 동시성 — run_id별 락

`WorkflowExecutor`에 `_run_locks: dict[str, asyncio.Lock]` 보관. `submit_approval`과 `_expire_run`이 같은 run에 대해 직렬화되도록 보호.

다른 run끼리는 락이 다르므로 병렬성을 잃지 않는다.

### 3. 시작 멱등성 — inquiry_id 자연 키

`RunStoreAdapter`에 `_runs_by_inquiry: dict[str, str]` 인덱스 추가.

정책:

| 기존 run 상태 | 처리 |
|---|---|
| PENDING / RUNNING / WAITING_APPROVAL | 기존 run 반환 |
| COMPLETED | 기존 run 반환 (중복 답장 방지) |
| REJECTED / TIMED_OUT / FAILED | 새 run 생성 허용 (재시도 의미) |

### 4. LLM 출력 검증 (`nodes/llm.py`)

#### `classify_email`

응답의 `category`가 5개 화이트리스트(`CATEGORIES`)에 없으면 `LLMOutputValidationError`.

#### `generate_reply`

3단계 검증:

1. `subject`/`body`가 비어 있지 않은 문자열.
2. 카테고리별 `REQUIRED_INCLUDES`의 모든 키워드가 `body`에 substring으로 포함.
3. `general` 카테고리는 `REQUIRED_INCLUDES`가 빈 리스트 → 통과.

```python
REQUIRED_INCLUDES = {
    "billing": ["예상 처리 기한", "접수 확인 번호"],
    "technical": ["문제 인지 여부", "예상 해결 일정"],
    "account": ["보안 절차 안내", "예상 처리 시간"],
    "feature_request": ["피드백 감사", "검토 예정 안내"],
    "general": [],
}
```

substring 검증은 LLM이 prompt에 명시된 표현을 그대로 따르도록 유도하는 데 충분하다. 정밀도는 낮지만 평가 시나리오에 적합.

### 5. 프롬프트 분리 (`nodes/prompts.py`)

system/user 템플릿을 모듈 상수로 분리. `engine/input_mapping.render_inputs`의 `{{ ... }}` 렌더링을 그대로 재사용.

```python
def render_template(template: str, context: dict) -> str:
    return render_inputs({"_": template}, context)["_"]
```

LangChain은 사용하지 않는다. 의존성 비용 대비 이득이 적고, 자체 렌더링 로직(`input_mapping`)이 이미 존재.

#### system / user 메시지 분리

- system: 응답 톤, 응답 가이드라인, 플랜 규칙, 필수 포함 항목, 금지 사항, 출력 형식 지시.
- user: 문의 본문, 분류 카테고리, 고객 정보 등 가변 데이터.

LLM이 system 지시를 더 잘 따르고, prompt 구조가 평가자에게도 읽기 쉽다.

### 6. 액션 기반 LLM 레지스트리 (`engine/registries.py`)

```python
class AITaskRegistry:
    def __init__(self, tasks: dict[str, TaskFn], profiles: dict[str, AI]):
        self._tasks = tasks
        self._profiles = profiles

    async def run(self, task_name: str, input_data: dict) -> dict:
        task_fn = self._tasks.get(task_name)
        if task_fn is None:
            raise WorkflowEngineError(f"Unknown AI task: {task_name}")
        adapter = self._profiles.get(task_name)
        if adapter is None:
            raise WorkflowEngineError(f"No AI profile registered for task: {task_name}")
        return await task_fn(adapter, input_data)
```

#### 두 dict의 역할 분리

- `_tasks`: 액션 이름 → 노드 함수 (코드 작성 시점 결정, 도메인 결정).
- `_profiles`: 액션 이름 → AI 어댑터 (런타임 조립 시점 결정, 운영 결정).

키는 같지만 결정 시점·결정 주체가 다르다. 합치지 않고 분리하는 이유:

- 결정 시점이 달라 각자 자기 시점에 단순.
- 어댑터 인스턴스를 여러 액션에 공유 가능 (`{"a": shared, "b": shared}`).
- 테스트에서 fake 어댑터만 바꾸면 됨.

#### AI Protocol 시그니처 변경

```python
class AI(Protocol):
    async def chat_json(self, system: str, user: str) -> dict[str, Any]: ...
```

어댑터는 prompt 책임을 갖지 않고 순수 LLM 호출자로만 동작. prompt 조립과 검증은 `nodes/llm.py`가 담당.

### 7. 어댑터 변경

#### `OpenAIAdapter`

```python
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

#### `FakeAI`

```python
class FakeAI:
    def __init__(self, response: dict[str, Any]):
        self._response = response
        self.last_system: str | None = None
        self.last_user: str | None = None

    async def chat_json(self, system: str, user: str) -> dict[str, Any]:
        self.last_system = system
        self.last_user = user
        return self._response
```

테스트마다 액션별로 다른 `FakeAI` 인스턴스를 주입한다. prompt 내용을 단언할 수 있다.

### 8. Composition root 분리 (`bootstrap.py`)

`AppDependencies` dataclass + `build_dependencies(settings)` + `build_test_dependencies(...)`.

`app.py:create_app(deps)`는 FastAPI 인스턴스 생성과 `register_routes(app, deps)` 호출만 담당하고, 의존성 조립은 `bootstrap.py`에 모인다. `use_fake_dependencies` 같은 분기 플래그가 사라진다.

#### `ApprovalTimer` ↔ `WorkflowExecutor` 인스턴스 wiring 순서

타입 의존은 단방향이다. `WorkflowExecutor`만 `ApprovalTimer`를 직접 의존하고, `ApprovalTimer`는 `Callable[[str], Awaitable[None]]` 콜백 시그니처만 알 뿐 `WorkflowExecutor` 타입을 모른다.

하지만 인스턴스 wiring은 순환적이다. `WorkflowExecutor`는 `timer.schedule()`을 호출하기 위해 timer 인스턴스를 들고 있어야 하고, `ApprovalTimer`의 콜백은 `executor.expire_run`이라는 bound method를 들고 있어야 한다. 두 인스턴스를 동시에 생성하려 하면 어느 쪽을 먼저 만들어도 상대 인스턴스가 필요한 chicken-and-egg 상황이 된다.

해결: 타이머는 콜백을 생성자에서 받지 않고 setter로 주입한다.

```python
# bootstrap.py 안
timer = ApprovalTimer()                                # 콜백 미주입 상태로 생성
executor = WorkflowExecutor(..., approval_timer=timer) # timer 인스턴스 주입
timer.set_on_expire(executor.expire_run)               # 사후 wiring
```

`ApprovalTimer.set_on_expire`는 콜백이 없을 때 `schedule`이 호출되면 예외를 발생시키도록 단언을 둔다 (`assert self._on_expire is not None`).

### 9. Settings 변경

```
OPENAI_CLASSIFY_MODEL=gpt-4.1-mini
OPENAI_GENERATE_MODEL=gpt-4.1-mini
OPENAI_TEMPERATURE=0
```

기존 `OPENAI_MODEL`은 두 모델의 fallback으로 인정해 후방 호환을 유지한다.

## Data Flow

### 정상 흐름 (시작 → 승인 → 발송)

```
POST /workflow-runs
  → routes.start_workflow_run
  → executor.start(workflow, {"inquiry_id": ...})
    → store.find_by_inquiry → 활성/COMPLETED run 있으면 즉시 반환
    → workflow validator → topo sort
    → 순차 실행:
        fetch_inquiry (tool)
        classify_inquiry (llm: classify_email 액션)
        lookup_customer (tool)
        generate_reply (llm: generate_reply 액션, _validate_reply 검증)
    → 승인 노드 진입:
        run.status = WAITING_APPROVAL
        store.save(run)
        approval_timer.schedule(run_id, deadline_at)
    → 응답 반환

POST /workflow-runs/{id}/approval (decision=approve)
  → routes.submit_approval
  → executor._lock_for(run_id) 획득
  → approval_timer.cancel(run_id)
  → deadline 검사 (이미 지났으면 TIMED_OUT)
  → run.status = RUNNING
  → 남은 노드 실행: send_reply_email (tool, retry 적용)
  → run.status = COMPLETED
  → 응답 반환
```

### 만료 흐름

```
ApprovalTimer.task가 sleep 종료
  → _on_expire(run_id) 호출
  → executor._expire_run(run_id):
      lock 획득 → run 상태 확인 → WAITING_APPROVAL이면 TIMED_OUT 전환
```

### 조회 lazy 안전망

```
GET /workflow-runs/{id}
  → routes.get_workflow_run
  → executor.expire_if_overdue(run_id)
      → WAITING_APPROVAL + deadline 경과면 TIMED_OUT 전환
  → 최신 run 반환
```

## Error Handling

### 새 에러 코드

- `LLM_OUTPUT_VALIDATION_ERROR`: `classify_email` 또는 `generate_reply`의 출력 검증 실패.
- `APPROVAL_TIMEOUT`: 승인 타임아웃.

### 노드 실패

`WorkflowExecutor._fail_run`이 노드별 예외를 잡아 `WorkflowErrorData`로 변환:

- 예외의 `code` 속성이 있으면 그대로 사용 (예: `LLM_OUTPUT_VALIDATION_ERROR`).
- 없으면 기본 `NODE_EXECUTION_FAILED`.

이번 리팩토링에서는 노드별 에러 코드를 별도로 표준화하지 않는다. 새 에러는 `④ generate_reply 출력 검증`과 `① 능동 타임아웃`에 따라오는 두 코드만 추가한다.

## Testing Strategy

### 분류

- 단위 테스트: 순수 함수, 단일 클래스. fake 어댑터 사용.
- 통합 테스트: `bootstrap.build_test_dependencies`로 조립한 executor.
- API 테스트: `FastAPI TestClient` + `build_test_dependencies`.

`tests/` 디렉토리는 평면 유지 (현재 9개 파일 → 14개 정도). 분류 디렉토리화는 규모상 YAGNI.

### `tests/conftest.py`

공통 fixture로 `deps`, `client` 제공. 시나리오별 응답을 받은 fixture(`deps_with_inquiry_billing` 등)는 필요할 때 추가.

### 신규 / 갱신 테스트

- `test_prompts.py`: 신규
- `test_llm_tasks.py`: 신규 (classify/generate 단위 + 검증 실패 케이스)
- `test_approval_timer.py`: 신규
- `test_ai_registry.py`: 신규 (액션 기반 레지스트리)
- `test_idempotency.py`: 신규 (inquiry_id 자연 키)
- `test_executor.py`: 갱신 (락, 타이머, 검증 실패 코드)
- `test_api.py`: 갱신 (build_test_dependencies, lazy 만료, 멱등성)
- `test_loader.py`: 신규 (YAML 로딩)
- 기존 `test_ai.py`: 폐기 또는 chat_json 단위 테스트로 변경

OpenAI 호출은 자동 테스트에서 사용하지 않는다. OpenAI 연동은 환경변수 설정 후 수동 검증.

## Migration Phases

각 Phase 끝에 전체 테스트 통과를 검증한다. 독립 커밋으로 만들어 롤백 가능하게 한다.

### Phase 1 — 디렉토리 골격 + 이동 + 개명

- 새 폴더 생성: `domain/`, `nodes/` (engine/는 이동만)
- 파일 이동:
  - `domain.py` → `domain/workflow.py` + `domain/run.py` (분할)
  - `errors.py` → `domain/errors.py`
  - `policies.py` → `domain/reply_policy.py`
  - `tools.py` → `nodes/tools.py`
  - `ports.py` → `engine/ports.py`
  - `registries.py` → `engine/registries.py`
  - `engine/workflow_validator.py` → `engine/validator.py`
  - `engine/workflow_loader.py` → `engine/loader.py`
  - `adapters/mock_server.py` → `adapters/mock_api.py`
  - `adapters/ai.py` → `adapters/openai.py` + `adapters/fake_ai.py` (분할)
- import 갱신
- 테스트 import 갱신, 로직 변경 없음
- **검증**: 전체 테스트 통과 + 서버 기동 + curl 시작/승인

### Phase 2 — 액션 기반 LLM 레지스트리 + 프롬프트 분리

- `nodes/prompts.py` 신설
- `nodes/llm.py` 신설 (`classify_email`, `generate_reply`, `_validate_reply`)
- `domain/reply_policy.py`에 `REQUIRED_INCLUDES`, `CATEGORY_TONE` 추가
- `domain/errors.py`에 `LLMOutputValidationError` 추가
- `engine/ports.AI`를 `chat_json`으로 변경
- `adapters/openai.py`, `adapters/fake_ai.py` 시그니처 변경
- `engine/registries.AITaskRegistry`를 `tasks` + `profiles` 두 dict 형태로 변경
- `tests/test_llm_tasks.py`, `test_prompts.py`, `test_ai_registry.py` 신설
- 기존 `test_ai.py` 폐기 또는 chat_json 단위 테스트로 변경
- **검증**: 위 + LLM 노드 테스트 통과

### Phase 3 — Bootstrap + app.py + routes.py + schemas.py

- `bootstrap.py` 신설
- `app.py` 최상위 신설 (현 `api.py`의 `create_app` 책임 이관)
- 현 `src/workflow_engine/api.py` (단일 파일) 삭제 후 `src/workflow_engine/api/` 디렉토리 생성
  - 같은 이름의 파일과 패키지는 공존 불가 — 파일을 먼저 삭제한 뒤 디렉토리를 만든다
- `api/routes.py`, `api/schemas.py`, `api/__init__.py` 신설
- `main.py` 갱신 (`bootstrap → create_app → uvicorn` 흐름)
- `tests/conftest.py` fixture 추가
- `test_api.py`에서 `use_fake_dependencies` 플래그 제거
- **검증**: 위 + API 테스트가 새 fixture 패턴 통과

### Phase 4 — 능동 타임아웃 + run_id 락 + 멱등성

- `engine/approval_timer.py` 신설
- `bootstrap.py`에서 `ApprovalTimer` 조립 + executor에 주입
- `WorkflowExecutor`에 `approval_timer`, `_run_locks`, `_expire_run`, `expire_if_overdue` 추가
- 승인 노드 진입 시 `timer.schedule`
- `submit_approval`에서 `timer.cancel` + 락
- `routes.get_workflow_run`에서 `expire_if_overdue` 호출
- `RunStoreAdapter`에 `_runs_by_inquiry` 인덱스 + `find_by_inquiry`
- `executor.start` 앞단에서 inquiry_id 활성/COMPLETED 검사
- 신규 테스트: `test_approval_timer.py`, `test_idempotency.py`, executor 케이스 추가
- **검증**: 전체 테스트 통과 + 수동 OpenAI 1회 + 수동 timeout 만료 1회

### Phase 5 — README + 마무리

- README 갱신 (실행, 환경변수, 설계 배경, 트레이드오프, 확장 포인트, 한계)
- `.env.example` 갱신
- 사용하지 않는 import / 죽은 코드 정리
- 최종 테스트 + git diff 점검

## Security

- API Key는 환경변수로 주입, `.env`는 `.gitignore`에 포함, 커밋 금지.
- Mock API Key와 OpenAI API Key는 분리된 환경변수.
- 승인 API는 평가 MVP에서 인증 생략. 운영 환경에선 인증 + 권한 + 감사 로그 필요.
- LLM 프롬프트의 고객 정보는 응답 생성에 필요한 필드만 포함 (이름, 플랜, 상태, 이메일). 민감정보는 prompt에 미포함.
- 응답 생성 system prompt에 PDF 금지 사항 7항목 항상 포함.

## Limitations

- Run store / 만료 타이머 / run-level lock / 멱등성 인덱스 모두 in-memory → **단일 worker 전제**. 멀티 worker 또는 영속화 필요 시 Redis/PostgreSQL로 이동.
- 노드 병렬 실행 미지원 (PDF 선택 과제, 범위 외).
- LLM 호출은 노드 단위 최대 1회. 재시도 미적용 (출력 비결정성 회피).
- `generate_reply` 필수 포함 항목 검증은 substring 매칭. 의미 검증은 별도 LLM judge 등 향후 작업.
- 워크플로우는 `customer_support_auto_reply` 1개 등록.

## Open Decisions

(이번 리팩토링 시점에 모두 합의됨, 기록용)

| 결정 | 합의 |
|---|---|
| 디렉토리 구조 | 옵션 A 5개 폴더 + app.py 최상위 |
| 어댑터 명명 | 외부 시스템 이름 그대로 (openai.py 등) |
| 능동 타임아웃 구현 | per-run asyncio Task + GET lazy 안전망 |
| 동시성 race | run_id별 asyncio.Lock |
| 멱등성 정책 | inquiry_id 자연 키. COMPLETED 포함 활성=기존 반환, REJECTED/TIMED_OUT/FAILED=새 run 허용 |
| 모델 라우팅 | 액션 기반 레지스트리 (provider/model 명시 필드 미도입) |
| 멀티 프로바이더 어댑터 | 추가 안 함 (AI Protocol 추상화로 충분) |
| 프롬프트 라이브러리 | 자체 구현 (LangChain 미사용) |
| `routes.py` 분리 | 분리함 (api/ 폴더 의미 유지) |
| Run 영속화 | 안 함 (in-memory + worker=1 제약 README 명시) |
| 외부 호출 멱등성 | Mock 503 동작 확인 결과 위험 0, README 한 줄도 추가 안 함 |

## References

- 선행 MVP 설계: `docs/superpowers/specs/2026-04-26-mini-workflow-engine-design.md`
- 과제 명세: `AI_Workflow_Builder_assignment.pdf` (Confidential, 평가용)
- Mock API 코드: `mock-server/mock_server.py`
