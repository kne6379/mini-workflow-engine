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

## 워크플로우 흐름

`workflows/customer_support_auto_reply.yaml`이 정의하는 DAG:

```
fetch_inquiry  →  classify_inquiry  →  lookup_customer  →  generate_reply  →  wait_for_approval  →  send_reply_email
   (Tool)            (LLM)                (Tool)              (LLM)           (HumanApproval)        (Tool)
```

각 노드 출력은 `context.nodes.<key>`에 누적되어 후속 노드에서 `{{ nodes.<key>.<field> }}` 템플릿으로 참조한다.

## Mock API 서버 실행

Docker (권장):

```bash
cd mock-server
docker compose up --build
```

Docker 미사용 시 (python으로 직접 실행):

```bash
pip install -r mock-server/requirements.txt
python -m uvicorn mock_server:app --app-dir mock-server --host 0.0.0.0 --port 8080
```

Mock 서버: http://localhost:8080 (Swagger: /docs, Bearer 토큰 = `mock-api-key-12345`)

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
OPENAI_MODEL=gpt-4.1-mini              # fallback 기본 모델
OPENAI_CLASSIFY_MODEL=                 # 비면 OPENAI_MODEL 사용
OPENAI_GENERATE_MODEL=                 # 비면 OPENAI_MODEL 사용
OPENAI_TEMPERATURE=0
```

## API 서버 실행

```bash
python -m workflow_engine.main
```

Swagger 문서: http://localhost:8000/docs

## 골든 패스 (시작 → 승인 → 발송)

```bash
# 1) 시작 — 노드 4개(fetch/classify/lookup/generate)까지 실행 후 WAITING_APPROVAL
curl -s -X POST http://localhost:8000/workflow-runs \
  -H "Content-Type: application/json" \
  -d '{"workflow_key":"customer_support_auto_reply","inquiry_id":"INQ-002"}'
# → { "run_id":"run_6ebd4e93bc76", "status":"WAITING_APPROVAL",
#     "approval": { "subject":"Re: ...", "body":"...", "deadline_at":"...Z" }, ... }

# 2) 상태 조회 — deadline 경과 시 GET 시점에 lazy 만료(능동 타이머가 1차, 이건 안전망)
curl -s http://localhost:8000/workflow-runs/run_6ebd4e93bc76

# 3) 승인 — send_reply_email 실행 후 COMPLETED
curl -s -X POST http://localhost:8000/workflow-runs/run_6ebd4e93bc76/approval \
  -H "Content-Type: application/json" \
  -d '{"decision":"approve"}'
# → { "status":"COMPLETED",
#     "context": { "nodes": { ..., "send_reply_email": { "message_id":"msg-...", "status":"sent" } } } }
```

## 거부 / 타임아웃

```bash
# 거부 — REJECTED 종료, send_reply_email 미실행
curl -s -X POST http://localhost:8000/workflow-runs/<run_id>/approval \
  -H "Content-Type: application/json" \
  -d '{"decision":"reject","reason":"답변 내용이 부정확함"}'
# → { "status":"REJECTED", "approval": { "decision":"reject", "decided_at":"...Z" } }

# 타임아웃 — yaml의 timeout_seconds 경과 시 자동 TIMED_OUT (능동 타이머)
# workflows/customer_support_auto_reply.yaml: wait_for_approval.timeout_seconds
# → { "status":"TIMED_OUT",
#     "error": { "code":"APPROVAL_TIMEOUT", "node_key":"wait_for_approval", "retryable":false } }
```

## 멱등성

`inquiry_id`가 자연 키. 동일 inquiry로 재요청 시:

| 기존 run 상태 | 동작 |
|---|---|
| RUNNING / WAITING_APPROVAL | 기존 run 그대로 반환 |
| COMPLETED | 기존 run 그대로 반환 |
| REJECTED / TIMED_OUT / FAILED | 새 run 생성 |

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

의존 방향: api → bootstrap → engine + nodes + adapters → domain (단방향).

## 설계 결정

- **워크플로우 정의**: YAML, `key`는 워크플로우 내부 참조, `type + tool/task`가 재사용 단위.
- **LLM 노드**: 액션 기반 레지스트리 (`task` 필드가 곧 레지스트리 키). 액션마다 다른 어댑터/모델 분리 가능.
- **Tool ↔ LLM 피드백 패턴**: PDF에서 요구한 "Tool 실행 결과를 LLM에 피드백"은 워크플로우 DAG의 컨텍스트 전달로 구현된다. Tool 노드 출력은 `context.nodes.<key>`에 저장되고, 후속 LLM 노드가 `inputs`에서 `{{ nodes.lookup_customer.customer }}` 같은 템플릿으로 참조한다. 이 시나리오의 5단계 흐름(classify → lookup_crm → generate → approve → send_email)은 선형 DAG이므로 모델이 자율적으로 tool을 호출하는 agentic 루프가 아니라 1급 시민 노드 + 컨텍스트 매핑 패턴이 PDF 의도에 부합한다고 판단했다. 향후 동적 tool 선택이 필요해지면 `nodes/llm.py:generate_reply`에 OpenAI function calling을 추가하는 식으로 확장 가능하다.
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

## 트러블슈팅

| 증상 | 원인 / 조치 |
|---|---|
| `Cannot connect to the Docker daemon` | Docker Desktop 미기동. 위의 "Docker 미사용 시" 명령으로 우회 |
| `Address already in use` (8000/8080) | 기존 프로세스 종료: `pkill -f workflow_engine.main`, `pkill -f mock_server` |
| `INQ-XXX Not Found` | Mock 데이터에 없는 inquiry_id. `curl -H "Authorization: Bearer mock-api-key-12345" http://localhost:8080/api/inquiries`로 목록 확인 |
| `LLM_PROVIDER=openai`인데 401/응답 빔 | `.env`의 `OPENAI_API_KEY` 누락. 평가용은 기본값 `fake`로 충분 |
| classify에 5개 카테고리 외 값 반환 | 출력 검증에서 `INVALID_LLM_OUTPUT`으로 노드 FAIL → run FAILED |
| generate가 카테고리별 필수 키워드 누락 | 마찬가지로 검증 실패. 프롬프트는 `nodes/prompts.py` 참조 |

## 운영 노트

- **단일 worker 전제**: run store / 만료 타이머 / run-level lock / 멱등성 인덱스가 모두 in-memory. `uvicorn --workers 2` 이상은 race·중복 run 발생 가능.
- **환경변수 우선순위**: 셸 환경 > `.env` > `Settings` 기본값. `LLM_PROVIDER=fake`이면 OpenAI 키 없이 모든 테스트가 통과한다.
- **API Key**: Mock 서버는 Bearer `mock-api-key-12345` 고정. `.env`의 `MOCK_API_KEY`와 일치해야 함.
- **승인 deadline**: 워크플로우 yaml의 `wait_for_approval.timeout_seconds` 값으로 설정 (기본 1800s).

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
