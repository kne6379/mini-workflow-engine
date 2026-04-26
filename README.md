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

코드는 경량 ports/adapters 구조로 나눴습니다. `ports.py`는 엔진이 기대하는 계약을 정의하고, `engine/`은 실행 순서 결정, 입력 매핑, 재시도, pause/resume을 담당합니다. `adapters/`에는 제공 Mock 서버를 호출하는 `MockServerAdapter`, OpenAI/Fake AI를 다루는 `OpenAIAdapter`와 `FakeAIAdapter`, 실행 상태를 저장하는 `RunStoreAdapter`를 둡니다.

## 테스트

```bash
python -m pytest -q
```

자동 테스트는 네트워크와 비용 문제를 피하기 위해 Fake AI를 사용합니다. OpenAI 연동은 환경 변수를 설정한 뒤 수동으로 확인합니다.

## 보안 고려사항

- 실제 OpenAI API Key는 커밋하지 않습니다.
- Mock API Key와 OpenAI API Key는 환경 변수로 주입합니다.
- 과제 MVP의 승인 API는 인증을 생략합니다.
- 운영 환경에서는 승인 API에 인증과 권한 검사가 필요합니다.

## 한계

- Run store는 in-memory입니다.
- 순차 실행만 지원합니다.
- 병렬 실행, 조건 분기, 시각적 빌더는 범위에서 제외했습니다.
