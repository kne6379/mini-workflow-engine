# Mock API Server

AI Workflow Builder Mock API 서버입니다.
고객 문의 메일 조회, CRM 고객 정보 조회, 이메일 발송을 시뮬레이션합니다.

> **LLM API는 포함되어 있지 않습니다.** 상용 LLM API(OpenAI, Anthropic 등)를 직접 연동해야 합니다.

## 빠른 시작

### Docker (권장)
```bash
docker compose up --build
```

### 직접 실행
```bash
pip install -r requirements.txt
python mock_server.py
```

서버가 시작되면 `http://localhost:8080` 에서 접속할 수 있습니다.

## API 문서

서버 실행 후 `http://localhost:8080/docs` 에서 Swagger UI를 통해 전체 API를 확인할 수 있습니다.

## 인증

모든 API 요청에 Bearer 토큰 인증이 필요합니다.
Swagger UI에서는 우측 상단 **Authorize** 버튼을 클릭하고 아래 키를 입력하세요:

```
mock-api-key-12345
```

curl 사용 시:
```
Authorization: Bearer mock-api-key-12345
```

## 분류 카테고리

고객 문의 메일은 다음 5개 카테고리로 분류됩니다:

| 카테고리 ID | 이름 | 설명 |
|------------|------|------|
| billing | 결제/요금 | 결제 실패, 요금 문의, 환불, 플랜 변경 등 |
| technical | 기술 지원 | API 오류, 시스템 장애, 연동 문제, 버그 리포트 등 |
| account | 계정 관리 | 로그인 문제, 비밀번호 초기화, SSO 설정, 권한 변경 등 |
| feature_request | 기능 요청 | 신규 기능 제안, 개선 요청, 로드맵 문의 등 |
| general | 일반 문의 | 서비스 안내, 온보딩, 계약 관련, 기타 문의 등 |

## 엔드포인트 요약

### Inquiry API (워크플로우 입력 데이터)

| Method | Endpoint | 설명 |
|--------|----------|------|
| GET | `/api/inquiries` | 고객 문의 메일 전체 목록 조회 (20건) |
| GET | `/api/inquiries?category=billing` | 카테고리별 필터링 조회 |
| GET | `/api/inquiries/{inquiry_id}` | 특정 문의 메일 단건 조회 |
| GET | `/api/inquiries/categories/list` | 분류 카테고리 목록 조회 |

### CRM API

| Method | Endpoint | 설명 |
|--------|----------|------|
| POST | `/api/crm/lookup` | 고객 정보 조회 (customer_id 또는 email) |
| GET | `/api/crm/customers` | 전체 고객 목록 조회 |

### Email API

| Method | Endpoint | 설명 |
|--------|----------|------|
| POST | `/api/email/send` | 이메일 발송 (Mock, 10% 확률 503 에러) |
| GET | `/api/email/sent` | 발송 이메일 목록 확인 |

## 테스트용 데이터

### 고객 목록 (5명)

| ID | 이름 | 이메일 | 플랜 | 상태 |
|----|------|--------|------|------|
| C001 | 김민수 | minsu.kim@example.com | Enterprise | active |
| C002 | 이서연 | seoyeon.lee@example.com | Business | active |
| C003 | 박지훈 | jihoon.park@example.com | Free | churned |
| C004 | 최유진 | yujin.choi@example.com | Enterprise | active |
| C005 | 정하늘 | haneul.jung@example.com | Business | active |

### 고객 문의 메일 (20건)

카테고리별 4건씩, 총 20건의 샘플 문의 메일이 포함되어 있습니다.
각 문의 메일에는 `expected_category` 필드가 포함되어 있어 LLM 분류 결과 검증에 활용할 수 있습니다.

| ID | 발신자 | 카테고리 | 제목 |
|----|--------|----------|------|
| INQ-001 ~ INQ-004 | 다양 | billing | 결제 중복, 플랜 변경, 결제 실패, 할인 문의 |
| INQ-005 ~ INQ-008 | 다양 | technical | API 에러, 웹훅 수신, SDK 오류, 대시보드 지연 |
| INQ-009 ~ INQ-012 | 다양 | account | SSO 설정, 권한 변경, 비밀번호 재설정, 계정 이관 |
| INQ-013 ~ INQ-016 | 다양 | feature_request | Slack 알림, 성능 비교, CSV 배치, 스케줄 실행 |
| INQ-017 ~ INQ-020 | 다양 | general | 도입 검토, 계약 갱신, 온보딩 교육, GDPR 확인 |

## API 호출 예시

```bash
# 전체 문의 메일 조회
curl http://localhost:8080/api/inquiries \
  -H "Authorization: Bearer mock-api-key-12345"

# 카테고리별 필터링
curl "http://localhost:8080/api/inquiries?category=billing" \
  -H "Authorization: Bearer mock-api-key-12345"

# 특정 문의 단건 조회 (워크플로우 단건 실행 테스트용)
curl http://localhost:8080/api/inquiries/INQ-001 \
  -H "Authorization: Bearer mock-api-key-12345"

# 분류 카테고리 목록 조회
curl http://localhost:8080/api/inquiries/categories/list \
  -H "Authorization: Bearer mock-api-key-12345"

# CRM 고객 조회
curl -X POST http://localhost:8080/api/crm/lookup \
  -H "Authorization: Bearer mock-api-key-12345" \
  -H "Content-Type: application/json" \
  -d '{"email": "minsu.kim@example.com"}'

# 이메일 발송
curl -X POST http://localhost:8080/api/email/send \
  -H "Authorization: Bearer mock-api-key-12345" \
  -H "Content-Type: application/json" \
  -d '{"to": "minsu.kim@example.com", "subject": "답변 드립니다", "body": "안녕하세요..."}'
```

## 참고사항

- 이메일 발송 API는 **10% 확률로 503 에러**를 반환합니다 (재시도 로직 테스트용)
- CRM 조회 API는 0.1~0.3초의 랜덤 지연이 있습니다
- 모든 데이터는 서버 재시작 시 초기화됩니다
- LLM 연동은 OpenAI, Anthropic 등 상용 API를 직접 사용합니다
- 문의 메일의 `expected_category` 필드는 LLM 분류 정확도 검증용 참고 데이터입니다
