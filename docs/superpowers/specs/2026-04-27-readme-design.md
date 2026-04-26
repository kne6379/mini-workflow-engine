# README Design

작성일: 2026-04-27
대상 프로젝트: AI Workflow Builder Mini Engine

## Goal

README를 평가자가 과제 PDF 요구사항과 구현을 빠르게 대조할 수 있는 문서로 재작성한다. 단순 실행 안내가 아니라, 구현이 어떤 요구사항을 충족하는지와 왜 현재 구조를 선택했는지를 함께 설명하는 평가자 설득형 문서로 만든다.

본문은 한국어로 작성하고, `DAG`, `Tool`, `LLM`, `context`, `OpenAI`, `FastAPI`, `Exponential Backoff` 같은 기술 키워드는 원문을 유지한다.

## Audience

주 독자는 과제 평가자다. 평가자는 다음을 빠르게 확인하려고 한다.

- 제출물이 실행 가능한가.
- PDF 필수 요구사항을 빠짐없이 다뤘는가.
- 설계 결정의 이유와 한계를 설명할 수 있는가.
- OpenAI/Mock API/Human approval 흐름이 과제 시나리오와 맞는가.
- 테스트가 핵심 성공/오류 경로를 검증하는가.

따라서 README는 사용법보다 요구사항 매핑과 설계 설명을 앞쪽에 둔다. 실행 방법은 초반부에 배치하되, 문서의 중심은 설계 방어와 요구사항 대응이다.

## Document Shape

중간 길이 문서로 작성한다. 목표 분량은 약 180-250줄이다. 너무 짧게 줄여 설계 의도가 사라지지 않게 하고, 내부 구현 문서처럼 지나치게 깊어지지도 않게 한다.

섹션 순서는 아래를 따른다.

1. 프로젝트 개요
2. 과제 요구사항 매핑
3. 빠른 실행
4. API 사용 예시
5. Workflow 정의
6. 아키텍처
7. 주요 설계 결정
8. LLM 응답 정책
9. 오류 처리와 Retry
10. 테스트
11. 보안
12. 한계와 트레이드오프

## Section Design

### 1. 프로젝트 개요

고객 문의 이메일을 처리하는 미니 workflow engine임을 한 문단으로 설명한다.

핵심 흐름:

```text
Inquiry 조회 -> LLM 분류 -> CRM 조회 -> LLM 답변 생성 -> 관리자 승인 -> Email 발송
```

PDF 시나리오의 구현물이라는 점을 명확히 하되, 과제 PDF 내용을 길게 반복하지 않는다.

### 2. 과제 요구사항 매핑

README 초반의 핵심 섹션이다. 표 형태로 PDF 요구사항, 구현 방식, 관련 파일을 매핑한다.

표 컬럼:

- PDF 요구사항
- 구현 방식
- 관련 파일

포함할 항목:

- YAML workflow 정의
- DAG 기반 실행 순서 결정 및 cycle detection
- 순차 실행
- node 간 `context` 전달
- 오류 발생 시 `Exponential Backoff` retry
- `LLM` / `Tool` node abstraction
- OpenAI 연동
- Mock CRM / Email API 통합
- Human approval pause/resume
- 승인/거부 API endpoint
- 승인 timeout 처리
- 단위 테스트 포함

이 표는 평가자가 체크리스트처럼 읽을 수 있어야 한다. 각 설명은 한 문장 수준으로 짧게 쓴다.

### 3. 빠른 실행

실행 가능성을 빠르게 보여준다.

순서:

1. Python 3.13 가상환경 생성
2. 의존성 설치
3. `.env.example` 복사
4. Mock API 서버 실행
5. workflow engine 실행
6. Swagger URL 안내

기본값은 `LLM_PROVIDER=fake`라 OpenAI API key 없이도 실행 가능하다고 명시한다. 실제 OpenAI 연동을 확인하려면 `LLM_PROVIDER=openai`, `OPENAI_API_KEY`를 설정하도록 안내한다.

### 4. API 사용 예시

평가자가 수동으로 흐름을 따라갈 수 있게 `curl` 예시를 제공한다.

포함할 endpoint:

- `POST /workflow-runs`
- `GET /workflow-runs/{run_id}`
- `POST /workflow-runs/{run_id}/approval` with `approve`
- `POST /workflow-runs/{run_id}/approval` with `reject`

PDF의 주의사항도 짧게 반영한다. Workflow 시작점은 Email API가 아니라 Inquiry API에서 조회한 문의 데이터이며, Email API는 최종 발송 단계에서만 사용된다.

### 5. Workflow 정의

`workflows/customer_support_auto_reply.yaml` 파일을 중심으로 설명한다.

PDF는 5단계 흐름을 제시하지만, 구현은 입력 조회를 명시적인 `fetch_inquiry` Tool node로 모델링해 6개 node를 사용한다.

흐름:

```text
fetch_inquiry -> classify_inquiry
              -> lookup_customer
classify_inquiry + lookup_customer -> generate_reply
generate_reply -> wait_for_approval -> send_reply_email
```

`key`는 workflow 내부의 역할명이고, 재사용 가능한 실행 단위는 `type + tool/task` 조합이라고 설명한다.

### 6. 아키텍처

아키텍처 설명은 `main -> bootstrap -> engine / nodes / adapters` 흐름을 중심으로 작성한다.

구조:

```text
main
  -> bootstrap
      -> engine
      -> nodes
      -> adapters
      -> domain
  -> app/api
```

각 책임:

- `main`: 설정을 읽고 FastAPI 앱을 띄우는 진입점
- `bootstrap`: `RunStore`, `MockAPIAdapter`, `OpenAI/FakeAI`, registry, executor를 조립하는 composition root
- `engine`: workflow loading, validation, execution, retry, approval timeout 처리
- `nodes`: workflow에 등록 가능한 `Tool`과 `LLM task` 구현
- `adapters`: OpenAI, Mock API, FakeAI, in-memory RunStore 같은 외부 I/O 구현
- `app/api`: 조립된 executor를 HTTP endpoint로 노출하는 얇은 layer
- `domain`: workflow/run 모델, reply policy, error 정의

요청 처리 흐름은 별도로 짧게 보여준다.

```text
POST /workflow-runs
  -> api route
  -> executor.start()
  -> workflow validation
  -> nodes 실행
  -> adapters 호출
  -> WAITING_APPROVAL 반환
```

### 7. 주요 설계 결정

설계 사고력을 보여주는 핵심 섹션이다. 각 항목은 2-4문장으로 짧고 구체적으로 쓴다.

포함할 결정:

- YAML workflow를 선택한 이유
- `key`와 `type + tool/task`를 분리한 이유
- `Tool` / `LLM` node abstraction
- Tool 실행 결과를 `context.nodes.<key>`에 저장하고 후속 LLM node가 input mapping으로 참조하는 구조
- OpenAI adapter는 prompt 조립을 모르고, prompt 조립과 출력 검증은 `nodes/llm.py`가 담당하는 구조
- Human approval에서 run snapshot을 저장하고 `WAITING_APPROVAL` 상태로 pause하는 방식
- `ApprovalTimer`와 `GET` lazy fallback을 함께 둔 이유
- `inquiry_id` 기준 멱등성으로 중복 발송을 막는 방식

특히 `LLM Function Calling 패턴`은 명확히 방어한다. OpenAI의 tool-call API를 직접 쓰는 agent loop가 아니라, 과제의 고정 DAG 시나리오에 맞춰 Function Calling 패턴을 workflow node와 context feedback으로 추상화했다고 설명한다.

### 8. LLM 응답 정책

PDF의 맞춤형 응답 조건이 코드에 어떻게 반영됐는지 설명한다.

포함할 내용:

- 5개 category whitelist
- category별 tone/guideline
- plan별 응답 차별화 rule
- prohibited response rules
- required includes
- `generate_reply` 출력 검증

이 섹션은 LLM을 단순 호출하는 것이 아니라, 과제 정책을 prompt와 validation으로 고정했다는 점을 보여준다.

### 9. 오류 처리와 Retry

Retry 적용 범위를 명확히 한다.

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

retry exhausted 시 run과 node가 `FAILED`로 기록된다고 설명한다.

### 10. 테스트

테스트 실행 명령을 먼저 제공한다.

```bash
python -m pytest -q
```

테스트 범위:

- workflow loading/validation
- input mapping
- retry
- tool contracts
- Mock API adapter
- OpenAI adapter
- LLM task validation
- approval timer
- idempotency
- executor pause/resume/failure
- API endpoints

자동 테스트는 OpenAI 실제 호출 없이 `FakeAI`를 사용한다고 명시한다. OpenAI 연동은 환경변수 설정 후 수동 검증 대상으로 둔다.

### 11. 보안

보안 고려사항을 간결하게 정리한다.

- OpenAI API key는 환경변수로 주입
- `.env`는 commit 금지
- Mock API key와 OpenAI API key는 분리
- Mock API 호출에는 Bearer token 사용
- LLM prompt에는 응답 생성에 필요한 고객 필드만 포함
- 승인 API는 평가 MVP에서 인증을 생략했으며, 운영 환경에서는 authentication, authorization, audit log가 필요

### 12. 한계와 트레이드오프

한계를 숨기지 않고 명확히 쓴다.

- RunStore는 in-memory
- 단일 worker 전제
- node 병렬 실행 미지원
- LLM 호출 retry 미적용
- `generate_reply` 검증은 substring 기반
- workflow는 `customer_support_auto_reply` 하나만 등록
- multi-provider는 `AI` protocol로 확장 지점만 준비

이 섹션은 미구현 사항을 약점이 아니라 범위 관리와 trade-off로 보이게 작성한다.

## Tone and Style

- 평가자를 직접 설득하되 과장하지 않는다.
- "완벽한 production system"처럼 표현하지 않는다.
- "과제 MVP", "운영 전환 시 필요한 보완" 같은 표현으로 범위를 명확히 한다.
- 파일 경로는 backtick으로 표시한다.
- 표는 요구사항 매핑에만 사용하고, 나머지는 짧은 문단과 bullet 중심으로 쓴다.
- 코드 블록은 실행 명령, curl, architecture/data-flow diagram에만 사용한다.

## Out of Scope for README

README에는 다음을 길게 넣지 않는다.

- 전체 Pydantic model 정의
- 모든 테스트 케이스 목록의 상세 assertion
- Mock server 내부 구현 설명
- 과제 PDF 원문의 장문 재서술
- 향후 제품 로드맵

## Acceptance Criteria

README 작성이 완료되면 다음을 만족해야 한다.

- PDF 필수 요구사항과 구현 파일을 초반 표에서 바로 확인할 수 있다.
- OpenAI API key 없이도 fake mode로 실행 가능한 경로가 명확하다.
- 실제 OpenAI 연동 방법이 별도로 안내되어 있다.
- Workflow가 PDF의 5단계에 `fetch_inquiry`를 추가한 6 node 구조인 이유가 설명되어 있다.
- `LLM Function Calling 패턴`을 workflow node abstraction으로 해석한 이유가 명확하다.
- `main -> bootstrap -> engine/nodes/adapters` 중심의 아키텍처가 드러난다.
- 보안, 한계, trade-off가 별도 섹션으로 정리되어 있다.
- 문서는 중간 길이이며, 평가자가 3-5분 안에 핵심을 파악할 수 있다.
