"""
AI Workflow Builder - Mock API Server
=====================================
Mock 서버입니다. CRM 조회와 이메일 발송을 시뮬레이션합니다.
LLM API는 포함되어 있지 않으며, 상용 API(OpenAI, Anthropic 등)를 직접 연동해야 합니다.
Docker로 실행하거나 직접 Python으로 실행할 수 있습니다.

실행 방법:
  pip install fastapi uvicorn
  python mock_server.py
"""

import time
import random
import uuid
from datetime import datetime
from fastapi import FastAPI, HTTPException, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional

app = FastAPI(
    title="AI Workflow Builder - Mock API Server",
    description=(
        "Mock 서버: 고객 문의 메일 조회, CRM 조회, Email 발송 시뮬레이션\n\n"
        "## 인증\n"
        "모든 API는 Bearer 토큰 인증이 필요합니다.\n\n"
        "우측 상단의 **Authorize** 버튼을 클릭하고 아래 API Key를 입력하세요:\n\n"
        "```\nmock-api-key-12345\n```\n\n"
        "## 분류 카테고리\n"
        "고객 문의 메일은 다음 5개 카테고리로 분류됩니다:\n"
        "- **billing**: 결제, 환불, 청구, 요금\n"
        "- **technical**: 기술 오류, 버그, API, 시스템 장애\n"
        "- **account**: 계정, 로그인, 비밀번호, 권한, SSO\n"
        "- **feature_request**: 기능 요청, 개선 제안\n"
        "- **general**: 일반 문의, 사용법, 기타"
    ),
    version="1.0.0",
)

# ─── Security ────────────────────────────────────────────

security = HTTPBearer(
    scheme_name="Bearer Token",
    description="API Key를 입력하세요. (mock-api-key-12345)",
)

VALID_API_KEY = "mock-api-key-12345"


def verify_token(credentials: HTTPAuthorizationCredentials = Depends(security)) -> str:
    """Bearer 토큰을 검증합니다. 유효하지 않으면 401을 반환합니다."""
    if credentials.credentials != VALID_API_KEY:
        raise HTTPException(
            status_code=401,
            detail=f"Invalid API key. Use '{VALID_API_KEY}'",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return credentials.credentials

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ─── Mock Data ───────────────────────────────────────────

CUSTOMERS = {
    "C001": {
        "customer_id": "C001",
        "name": "김민수",
        "email": "minsu.kim@example.com",
        "company": "테크스타트 주식회사",
        "plan": "Enterprise",
        "status": "active",
        "created_at": "2023-03-15",
        "recent_tickets": [
            {"ticket_id": "T-1001", "subject": "API 연동 오류", "status": "resolved", "date": "2025-01-10"},
            {"ticket_id": "T-1045", "subject": "대시보드 접속 불가", "status": "resolved", "date": "2025-02-03"},
        ],
        "tags": ["vip", "tech-savvy"],
    },
    "C002": {
        "customer_id": "C002",
        "name": "이서연",
        "email": "seoyeon.lee@example.com",
        "company": "글로벌커머스 Inc.",
        "plan": "Business",
        "status": "active",
        "created_at": "2024-01-20",
        "recent_tickets": [
            {"ticket_id": "T-1102", "subject": "결제 실패 문의", "status": "open", "date": "2025-03-01"},
        ],
        "tags": ["billing-issue"],
    },
    "C003": {
        "customer_id": "C003",
        "name": "박지훈",
        "email": "jihoon.park@example.com",
        "company": "데이터플로우 연구소",
        "plan": "Free",
        "status": "churned",
        "created_at": "2024-06-10",
        "recent_tickets": [],
        "tags": ["churned", "researcher"],
    },
    "C004": {
        "customer_id": "C004",
        "name": "최유진",
        "email": "yujin.choi@example.com",
        "company": "스마트팩토리 주식회사",
        "plan": "Enterprise",
        "status": "active",
        "created_at": "2022-11-05",
        "recent_tickets": [
            {"ticket_id": "T-0899", "subject": "온보딩 지원 요청", "status": "resolved", "date": "2024-12-15"},
            {"ticket_id": "T-1200", "subject": "SSO 설정 문의", "status": "open", "date": "2025-03-05"},
        ],
        "tags": ["vip", "enterprise-support"],
    },
    "C005": {
        "customer_id": "C005",
        "name": "정하늘",
        "email": "haneul.jung@example.com",
        "company": "크리에이티브랩",
        "plan": "Business",
        "status": "active",
        "created_at": "2024-09-01",
        "recent_tickets": [
            {"ticket_id": "T-1150", "subject": "기능 추가 요청", "status": "open", "date": "2025-02-20"},
        ],
        "tags": ["feature-request"],
    },
}

# Email → Customer ID mapping
EMAIL_TO_CUSTOMER = {c["email"]: cid for cid, c in CUSTOMERS.items()}

SENT_EMAILS = []

# ─── Inquiry Categories & Sample Data ────────────────────

INQUIRY_CATEGORIES = [
    {"id": "billing", "name": "결제/요금", "description": "결제 실패, 요금 문의, 환불, 플랜 변경 등"},
    {"id": "technical", "name": "기술 지원", "description": "API 오류, 시스템 장애, 연동 문제, 버그 리포트 등"},
    {"id": "account", "name": "계정 관리", "description": "로그인 문제, 비밀번호 초기화, SSO 설정, 권한 변경 등"},
    {"id": "feature_request", "name": "기능 요청", "description": "신규 기능 제안, 개선 요청, 로드맵 문의 등"},
    {"id": "general", "name": "일반 문의", "description": "서비스 안내, 온보딩, 계약 관련, 기타 문의 등"},
]

INQUIRIES = [
    # ── billing (4건) ──
    {
        "inquiry_id": "INQ-001",
        "from": "minsu.kim@example.com",
        "subject": "이번 달 결제가 두 번 청구된 것 같습니다",
        "body": "안녕하세요, 김민수입니다. 3월 청구서를 확인했는데 동일한 금액이 두 번 결제된 것으로 보입니다. 확인 후 중복 결제분 환불 처리 부탁드립니다. 결제 내역 캡처 첨부합니다.",
        "expected_category": "billing",
        "received_at": "2025-03-10T09:15:00Z",
    },
    {
        "inquiry_id": "INQ-002",
        "from": "seoyeon.lee@example.com",
        "subject": "Business에서 Enterprise로 플랜 변경하고 싶습니다",
        "body": "안녕하세요, 글로벌커머스 이서연입니다. 현재 Business 플랜을 사용 중인데 팀 규모가 커져서 Enterprise로 업그레이드하고 싶습니다. 변경 시 요금 차액이 어떻게 되는지, 즉시 적용이 가능한지 안내 부탁드립니다.",
        "expected_category": "billing",
        "received_at": "2025-03-10T10:30:00Z",
    },
    {
        "inquiry_id": "INQ-003",
        "from": "haneul.jung@example.com",
        "subject": "카드 결제 실패 반복 발생",
        "body": "안녕하세요, 정하늘입니다. 어제부터 결제 시도 시 계속 '결제 처리 중 오류가 발생했습니다' 메시지가 나옵니다. 카드사에 확인했는데 카드에는 문제가 없다고 합니다. 해결 방법을 알려주세요.",
        "expected_category": "billing",
        "received_at": "2025-03-10T11:00:00Z",
    },
    {
        "inquiry_id": "INQ-004",
        "from": "yujin.choi@example.com",
        "subject": "연간 결제로 전환 시 할인율 문의",
        "body": "안녕하세요, 최유진입니다. 현재 월간 결제 중인데 연간 결제로 전환하면 할인이 적용되나요? Enterprise 플랜 기준 연간 결제 금액과 할인율을 알려주시면 감사하겠습니다.",
        "expected_category": "billing",
        "received_at": "2025-03-10T13:20:00Z",
    },
    # ── technical (4건) ──
    {
        "inquiry_id": "INQ-005",
        "from": "minsu.kim@example.com",
        "subject": "REST API v2 호출 시 500 에러 발생",
        "body": "안녕하세요, 김민수입니다. 오늘 오전부터 /api/v2/workflows 엔드포인트 호출 시 간헐적으로 500 Internal Server Error가 발생하고 있습니다. 요청 ID는 req-a1b2c3d4이며, 재현 가능합니다. 로그 확인 부탁드립니다.",
        "expected_category": "technical",
        "received_at": "2025-03-10T08:45:00Z",
    },
    {
        "inquiry_id": "INQ-006",
        "from": "jihoon.park@example.com",
        "subject": "웹훅 데이터가 수신되지 않습니다",
        "body": "안녕하세요, 박지훈입니다. 워크플로우 완료 시 설정한 웹훅 URL로 POST 요청이 오지 않고 있습니다. 웹훅 설정은 정상인 것 같은데 어제 저녁부터 수신이 안 됩니다. 서버 측 로그를 확인해 주시겠어요?",
        "expected_category": "technical",
        "received_at": "2025-03-10T09:30:00Z",
    },
    {
        "inquiry_id": "INQ-007",
        "from": "yujin.choi@example.com",
        "subject": "Python SDK 3.2.0 업데이트 후 인증 오류",
        "body": "안녕하세요, 최유진입니다. Python SDK를 3.2.0으로 업데이트한 후 기존에 잘 동작하던 인증이 'InvalidCredentials' 에러를 반환합니다. API 키는 변경하지 않았고, 3.1.x 버전으로 되돌리면 정상 동작합니다.",
        "expected_category": "technical",
        "received_at": "2025-03-10T14:10:00Z",
    },
    {
        "inquiry_id": "INQ-008",
        "from": "seoyeon.lee@example.com",
        "subject": "대시보드 차트 데이터 로딩 지연",
        "body": "안녕하세요, 이서연입니다. 대시보드의 워크플로우 실행 통계 차트가 로딩하는 데 30초 이상 걸립니다. 지난주까지는 2-3초면 로딩됐는데요. 데이터 기간을 줄여도 마찬가지입니다.",
        "expected_category": "technical",
        "received_at": "2025-03-10T15:45:00Z",
    },
    # ── account (4건) ──
    {
        "inquiry_id": "INQ-009",
        "from": "yujin.choi@example.com",
        "subject": "SSO SAML 설정 가이드 요청",
        "body": "안녕하세요, 최유진입니다. 사내 Okta와 SSO 연동을 진행하려 합니다. SAML 2.0 기반으로 설정하려는데 Entity ID와 ACS URL 설정 방법에 대한 가이드를 제공해 주실 수 있나요?",
        "expected_category": "account",
        "received_at": "2025-03-10T09:00:00Z",
    },
    {
        "inquiry_id": "INQ-010",
        "from": "haneul.jung@example.com",
        "subject": "팀원 계정 권한 변경 요청",
        "body": "안녕하세요, 정하늘입니다. 팀원 한 명(dev@creativlab.com)의 권한을 Viewer에서 Editor로 변경하고 싶은데, 관리 콘솔에서 권한 변경 메뉴를 찾지 못하겠습니다. 방법을 알려주세요.",
        "expected_category": "account",
        "received_at": "2025-03-10T10:20:00Z",
    },
    {
        "inquiry_id": "INQ-011",
        "from": "jihoon.park@example.com",
        "subject": "비밀번호 재설정 메일이 오지 않습니다",
        "body": "안녕하세요, 박지훈입니다. 비밀번호를 잊어서 재설정 메일을 요청했는데 30분이 지나도 메일이 도착하지 않습니다. 스팸함도 확인했으나 없습니다. jihoon.park@example.com 계정입니다.",
        "expected_category": "account",
        "received_at": "2025-03-10T11:15:00Z",
    },
    {
        "inquiry_id": "INQ-012",
        "from": "minsu.kim@example.com",
        "subject": "퇴사자 계정 비활성화 및 데이터 이관",
        "body": "안녕하세요, 김민수입니다. 팀원 1명이 퇴사하여 해당 계정(former@techstart.co.kr)을 비활성화해야 합니다. 이 사용자가 만든 워크플로우와 데이터를 다른 계정으로 이관할 수 있나요?",
        "expected_category": "account",
        "received_at": "2025-03-10T16:30:00Z",
    },
    # ── feature_request (4건) ──
    {
        "inquiry_id": "INQ-013",
        "from": "haneul.jung@example.com",
        "subject": "워크플로우 실행 결과 Slack 알림 기능 요청",
        "body": "안녕하세요, 정하늘입니다. 워크플로우 실행이 완료되거나 실패했을 때 Slack 채널로 알림을 받을 수 있는 기능이 있으면 좋겠습니다. 현재는 이메일 알림만 지원되는 것 같은데, Slack 연동도 가능할까요?",
        "expected_category": "feature_request",
        "received_at": "2025-03-10T09:50:00Z",
    },
    {
        "inquiry_id": "INQ-014",
        "from": "minsu.kim@example.com",
        "subject": "워크플로우 버전별 성능 비교 기능",
        "body": "안녕하세요, 김민수입니다. 워크플로우를 버전업할 때마다 이전 버전과 실행 시간, 성공률 등을 비교하고 싶습니다. A/B 테스트처럼 두 버전을 나란히 비교할 수 있는 대시보드가 있으면 매우 유용할 것 같습니다.",
        "expected_category": "feature_request",
        "received_at": "2025-03-10T11:40:00Z",
    },
    {
        "inquiry_id": "INQ-015",
        "from": "seoyeon.lee@example.com",
        "subject": "CSV 대량 데이터 입력 지원 요청",
        "body": "안녕하세요, 이서연입니다. 현재 워크플로우 실행 시 입력값을 하나씩 넣어야 하는데, CSV 파일을 업로드하면 한 번에 여러 건을 배치 실행할 수 있는 기능이 있었으면 합니다. 대량 주문 처리에 꼭 필요한 기능입니다.",
        "expected_category": "feature_request",
        "received_at": "2025-03-10T14:00:00Z",
    },
    {
        "inquiry_id": "INQ-016",
        "from": "yujin.choi@example.com",
        "subject": "워크플로우 스케줄 실행(Cron) 기능 제안",
        "body": "안녕하세요, 최유진입니다. 특정 시간에 워크플로우가 자동으로 실행되는 스케줄 기능을 제안드립니다. 예를 들어 매일 오전 9시에 일일 리포트를 생성하는 워크플로우를 자동 실행하고 싶습니다.",
        "expected_category": "feature_request",
        "received_at": "2025-03-10T16:50:00Z",
    },
    # ── general (4건) ──
    {
        "inquiry_id": "INQ-017",
        "from": "jihoon.park@example.com",
        "subject": "서비스 도입 검토를 위한 자료 요청",
        "body": "안녕하세요, 데이터플로우 연구소 박지훈입니다. 연구 프로젝트에 AI 워크플로우 도입을 검토 중입니다. 기술 소개서와 학술 기관 대상 할인 프로그램이 있는지 안내 부탁드립니다.",
        "expected_category": "general",
        "received_at": "2025-03-10T08:30:00Z",
    },
    {
        "inquiry_id": "INQ-018",
        "from": "seoyeon.lee@example.com",
        "subject": "연간 계약 갱신 절차 문의",
        "body": "안녕하세요, 이서연입니다. 현재 계약이 다음 달에 만료되는데, 갱신 절차와 필요한 서류가 있는지 알려주세요. 또한 계약 조건 변경이 가능한지도 확인 부탁드립니다.",
        "expected_category": "general",
        "received_at": "2025-03-10T10:45:00Z",
    },
    {
        "inquiry_id": "INQ-019",
        "from": "yujin.choi@example.com",
        "subject": "신규 팀원 온보딩 교육 일정 문의",
        "body": "안녕하세요, 최유진입니다. 다음 주에 새로운 팀원 3명이 합류합니다. 온보딩 교육 세션을 예약할 수 있나요? 화요일이나 수요일 오후에 가능하면 좋겠습니다.",
        "expected_category": "general",
        "received_at": "2025-03-10T13:00:00Z",
    },
    {
        "inquiry_id": "INQ-020",
        "from": "haneul.jung@example.com",
        "subject": "데이터 보관 정책 및 GDPR 준수 여부 확인",
        "body": "안녕하세요, 정하늘입니다. 유럽 고객사와 협업하게 되어 데이터 보관 및 처리 정책이 GDPR을 준수하는지 확인이 필요합니다. 관련 문서나 인증 내역을 공유해 주실 수 있나요?",
        "expected_category": "general",
        "received_at": "2025-03-10T15:20:00Z",
    },
]

# ─── 분류 카테고리 정의 ─────────────────────────────────
# billing        : 결제, 환불, 청구, 요금 관련
# technical      : 기술 오류, 버그, API, 시스템 장애
# account        : 계정, 로그인, 비밀번호, 권한, SSO
# feature_request: 기능 요청, 개선 제안
# general        : 일반 문의, 사용법, 기타

CATEGORIES = ["billing", "technical", "account", "feature_request", "general"]

# ─── 고객 문의 메일 샘플 데이터 (20건) ──────────────────

INQUIRIES = {
    "INQ-001": {
        "inquiry_id": "INQ-001",
        "from": "seoyeon.lee@example.com",
        "subject": "이번 달 청구 금액이 이상합니다",
        "body": "안녕하세요, 이번 달 청구서를 확인했는데 지난달보다 금액이 2배 이상 높습니다. Business 플랜을 사용 중인데 추가 요금이 발생한 이유를 알려주세요. 혹시 잘못 청구된 거라면 조정 부탁드립니다.",
        "category": "billing",
        "received_at": "2025-03-10T09:15:00Z",
        "status": "pending",
    },
    "INQ-002": {
        "inquiry_id": "INQ-002",
        "from": "minsu.kim@example.com",
        "subject": "카드 결제가 계속 실패합니다",
        "body": "Enterprise 플랜 갱신을 위해 카드 결제를 시도하고 있는데, '결제 처리 중 오류가 발생했습니다'라는 메시지가 계속 뜹니다. 카드 정보는 정확하고 한도도 충분합니다. 다른 결제 수단을 사용할 수 있는 방법이 있을까요?",
        "category": "billing",
        "received_at": "2025-03-10T10:22:00Z",
        "status": "pending",
    },
    "INQ-003": {
        "inquiry_id": "INQ-003",
        "from": "haneul.jung@example.com",
        "subject": "환불 요청합니다",
        "body": "지난달 Business 플랜에서 Enterprise 플랜으로 업그레이드했는데, 사용해보니 저희 팀 규모에는 맞지 않아서 다시 Business로 다운그레이드하고 싶습니다. 차액에 대한 환불이 가능한지 문의드립니다.",
        "category": "billing",
        "received_at": "2025-03-10T11:05:00Z",
        "status": "pending",
    },
    "INQ-004": {
        "inquiry_id": "INQ-004",
        "from": "yujin.choi@example.com",
        "subject": "세금계산서 발행 요청",
        "body": "안녕하세요, 2025년 1분기 이용 요금에 대한 세금계산서 발행을 요청드립니다. 사업자등록번호와 담당자 정보는 기존에 등록된 것과 동일합니다. 발행 후 yujin.choi@example.com으로 보내주시면 감사하겠습니다.",
        "category": "billing",
        "received_at": "2025-03-10T13:30:00Z",
        "status": "pending",
    },
    "INQ-005": {
        "inquiry_id": "INQ-005",
        "from": "minsu.kim@example.com",
        "subject": "REST API 호출 시 500 에러 발생",
        "body": "오늘 오전부터 /api/v2/data/export 엔드포인트를 호출하면 500 Internal Server Error가 반환됩니다. 어제까지는 정상 동작했습니다. 요청 헤더와 바디는 변경하지 않았고, curl로 테스트해도 동일한 에러가 발생합니다. 긴급하게 확인 부탁드립니다.",
        "category": "technical",
        "received_at": "2025-03-10T08:45:00Z",
        "status": "pending",
    },
    "INQ-006": {
        "inquiry_id": "INQ-006",
        "from": "jihoon.park@example.com",
        "subject": "데이터 동기화가 안 됩니다",
        "body": "대시보드에서 데이터 동기화를 실행하면 '동기화 실패: timeout' 에러가 발생합니다. 데이터 소스는 PostgreSQL이고, 연결 테스트는 통과합니다. 로그를 확인해보니 동기화 작업이 30초 후에 타임아웃되는 것 같은데, 타임아웃 설정을 늘릴 수 있나요?",
        "category": "technical",
        "received_at": "2025-03-10T09:50:00Z",
        "status": "pending",
    },
    "INQ-007": {
        "inquiry_id": "INQ-007",
        "from": "yujin.choi@example.com",
        "subject": "웹훅 이벤트가 수신되지 않습니다",
        "body": "설정 페이지에서 웹훅 URL을 등록하고 테스트 이벤트를 전송했는데, 저희 서버에서 아무런 요청도 수신하지 못하고 있습니다. URL은 https로 시작하고, 방화벽에서 해당 포트도 열어둔 상태입니다. 웹훅 전송 로그를 확인할 수 있는 방법이 있을까요?",
        "category": "technical",
        "received_at": "2025-03-10T14:10:00Z",
        "status": "pending",
    },
    "INQ-008": {
        "inquiry_id": "INQ-008",
        "from": "seoyeon.lee@example.com",
        "subject": "CSV 내보내기 시 한글이 깨집니다",
        "body": "리포트를 CSV로 내보내기 하면 한글 데이터가 전부 깨져서 나옵니다. Excel에서 열면 글자가 다 물음표로 표시됩니다. UTF-8 BOM으로 내보내기 옵션이 있으면 좋겠는데, 현재 어떤 인코딩으로 내보내기 되는지 알 수 있을까요?",
        "category": "technical",
        "received_at": "2025-03-10T15:25:00Z",
        "status": "pending",
    },
    "INQ-009": {
        "inquiry_id": "INQ-009",
        "from": "yujin.choi@example.com",
        "subject": "SSO 설정을 변경하고 싶습니다",
        "body": "현재 Google Workspace SSO를 사용 중인데, Okta로 변경하려고 합니다. SSO 공급자를 변경하는 절차와 기존 사용자들의 세션에 영향이 있는지 알려주세요. 마이그레이션 중 서비스 중단이 발생하는지도 궁금합니다.",
        "category": "account",
        "received_at": "2025-03-10T09:00:00Z",
        "status": "pending",
    },
    "INQ-010": {
        "inquiry_id": "INQ-010",
        "from": "haneul.jung@example.com",
        "subject": "팀원 계정 권한 변경 요청",
        "body": "저희 팀에서 신규 입사자가 들어왔는데, 기존 팀원과 동일한 Editor 권한을 부여하고 싶습니다. 관리자 페이지에서 권한 설정을 찾지 못했는데, 어디서 변경할 수 있는지 안내 부탁드립니다. 초대 링크 발송 방법도 알려주시면 감사하겠습니다.",
        "category": "account",
        "received_at": "2025-03-10T10:35:00Z",
        "status": "pending",
    },
    "INQ-011": {
        "inquiry_id": "INQ-011",
        "from": "jihoon.park@example.com",
        "subject": "비밀번호를 분실했습니다",
        "body": "비밀번호 재설정 이메일을 요청했는데 30분이 지나도 메일이 오지 않습니다. 스팸 폴더도 확인했는데 없습니다. 계정 이메일은 jihoon.park@example.com이 맞습니다. 수동으로 비밀번호를 초기화해주시거나, 다른 복구 방법을 알려주세요.",
        "category": "account",
        "received_at": "2025-03-10T11:20:00Z",
        "status": "pending",
    },
    "INQ-012": {
        "inquiry_id": "INQ-012",
        "from": "minsu.kim@example.com",
        "subject": "2FA 인증 앱을 변경하고 싶습니다",
        "body": "휴대폰을 교체하면서 기존 2FA 인증 앱(Google Authenticator) 정보가 사라졌습니다. 현재 로그인이 불가능한 상태입니다. 백업 코드도 분실한 상태인데, 본인 인증 후 2FA를 초기화할 수 있는 방법이 있을까요?",
        "category": "account",
        "received_at": "2025-03-10T14:45:00Z",
        "status": "pending",
    },
    "INQ-013": {
        "inquiry_id": "INQ-013",
        "from": "haneul.jung@example.com",
        "subject": "Slack 연동 기능을 추가해주세요",
        "body": "현재 이메일 알림만 지원되는데, Slack 채널로 알림을 받을 수 있으면 좋겠습니다. 특히 워크플로우 실행 결과나 오류 발생 시 Slack 웹훅으로 알림을 보내는 기능이 있으면 팀 운영에 큰 도움이 될 것 같습니다.",
        "category": "feature_request",
        "received_at": "2025-03-10T09:30:00Z",
        "status": "pending",
    },
    "INQ-014": {
        "inquiry_id": "INQ-014",
        "from": "minsu.kim@example.com",
        "subject": "API Rate Limit 상향 요청",
        "body": "현재 분당 100건의 API 호출 제한이 있는데, 저희 서비스 특성상 분당 500건 이상 호출이 필요합니다. Enterprise 플랜에서 Rate Limit을 상향할 수 있는 옵션이 있는지, 또는 별도 협의가 가능한지 문의드립니다.",
        "category": "feature_request",
        "received_at": "2025-03-10T11:00:00Z",
        "status": "pending",
    },
    "INQ-015": {
        "inquiry_id": "INQ-015",
        "from": "yujin.choi@example.com",
        "subject": "대시보드 커스터마이징 기능 요청",
        "body": "기본 제공되는 대시보드 레이아웃 외에, 사용자가 위젯을 자유롭게 배치하고 저장할 수 있는 커스텀 대시보드 기능이 있었으면 합니다. 팀별로 다른 대시보드를 사용하고 싶은데, 현재는 모든 팀원이 동일한 뷰를 봐야 해서 불편합니다.",
        "category": "feature_request",
        "received_at": "2025-03-10T13:15:00Z",
        "status": "pending",
    },
    "INQ-016": {
        "inquiry_id": "INQ-016",
        "from": "jihoon.park@example.com",
        "subject": "다크 모드를 지원해주세요",
        "body": "장시간 대시보드를 보면서 작업하는데 눈이 많이 피로합니다. 다크 모드 옵션을 추가해주시면 좋겠습니다. 시스템 설정에 따라 자동 전환되는 기능도 함께 지원되면 더 좋을 것 같습니다.",
        "category": "feature_request",
        "received_at": "2025-03-10T16:00:00Z",
        "status": "pending",
    },
    "INQ-017": {
        "inquiry_id": "INQ-017",
        "from": "seoyeon.lee@example.com",
        "subject": "서비스 이용 약관 문의",
        "body": "저희 회사에서 서비스 도입을 검토 중인데, 데이터 처리 약관(DPA)과 관련 보안 인증(SOC 2, ISO 27001) 보유 여부를 확인하고 싶습니다. 관련 문서를 받아볼 수 있을까요?",
        "category": "general",
        "received_at": "2025-03-10T09:10:00Z",
        "status": "pending",
    },
    "INQ-018": {
        "inquiry_id": "INQ-018",
        "from": "jihoon.park@example.com",
        "subject": "교육 자료나 튜토리얼이 있나요?",
        "body": "서비스를 처음 사용하는 팀원들을 위한 온보딩 자료가 있으면 공유 부탁드립니다. 영상 튜토리얼이나 단계별 가이드 문서가 있으면 좋겠습니다. 특히 워크플로우 생성과 데이터 연동 부분에 대한 가이드가 필요합니다.",
        "category": "general",
        "received_at": "2025-03-10T10:40:00Z",
        "status": "pending",
    },
    "INQ-019": {
        "inquiry_id": "INQ-019",
        "from": "yujin.choi@example.com",
        "subject": "서비스 점검 일정 문의",
        "body": "다음 주에 중요한 데모가 예정되어 있어서, 혹시 서비스 점검이나 업데이트 일정이 있는지 미리 확인하고 싶습니다. 정기 점검이 있다면 시간대와 예상 소요 시간을 알려주세요.",
        "category": "general",
        "received_at": "2025-03-10T14:00:00Z",
        "status": "pending",
    },
    "INQ-020": {
        "inquiry_id": "INQ-020",
        "from": "haneul.jung@example.com",
        "subject": "담당 영업 매니저 연결 요청",
        "body": "현재 Business 플랜을 사용 중인데, Enterprise 플랜으로 업그레이드를 검토하고 있습니다. 팀 규모나 사용 패턴에 맞는 견적을 받아보고 싶은데, 담당 영업 매니저와 미팅을 잡을 수 있을까요?",
        "category": "general",
        "received_at": "2025-03-10T16:30:00Z",
        "status": "pending",
    },
}


# ─── Models ──────────────────────────────────────────────

class CRMLookupRequest(BaseModel):
    customer_id: Optional[str] = None
    email: Optional[str] = None

class EmailSendRequest(BaseModel):
    to: str
    subject: str
    body: str
    reply_to: Optional[str] = None


# ─── Health Check ────────────────────────────────────────

@app.get("/health")
def health_check():
    return {"status": "ok", "timestamp": datetime.now().isoformat()}


# ─── CRM Endpoints ──────────────────────────────────────

@app.post("/api/crm/lookup")
def crm_lookup(req: CRMLookupRequest, _token: str = Depends(verify_token)):
    """고객 정보를 조회합니다. customer_id 또는 email로 검색 가능합니다."""

    # Simulate latency
    time.sleep(random.uniform(0.1, 0.3))

    customer = None

    if req.customer_id:
        customer = CUSTOMERS.get(req.customer_id)
    elif req.email:
        cid = EMAIL_TO_CUSTOMER.get(req.email)
        if cid:
            customer = CUSTOMERS.get(cid)

    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")

    return {
        "success": True,
        "data": customer,
        "timestamp": datetime.now().isoformat(),
    }


@app.get("/api/crm/customers")
def list_customers(_token: str = Depends(verify_token)):
    """전체 고객 목록을 조회합니다."""

    return {
        "success": True,
        "data": list(CUSTOMERS.values()),
        "total": len(CUSTOMERS),
    }


# ─── Inquiry Endpoints (고객 문의 메일) ─────────────────

@app.get("/api/inquiries")
def list_inquiries(
    category: Optional[str] = None,
    status: Optional[str] = None,
    _token: str = Depends(verify_token),
):
    """고객 문의 메일 목록을 조회합니다. category 또는 status로 필터링할 수 있습니다.

    - **category**: billing, technical, account, feature_request, general
    - **status**: pending, processing, resolved
    """

    results = list(INQUIRIES.values())

    if category:
        results = [inq for inq in results if inq["category"] == category]
    if status:
        results = [inq for inq in results if inq["status"] == status]

    return {
        "success": True,
        "data": results,
        "total": len(results),
        "categories": CATEGORIES,
    }


@app.get("/api/inquiries/{inquiry_id}")
def get_inquiry(inquiry_id: str, _token: str = Depends(verify_token)):
    """특정 문의 메일을 조회합니다."""

    inquiry = INQUIRIES.get(inquiry_id)
    if not inquiry:
        raise HTTPException(status_code=404, detail="Inquiry not found")

    return {
        "success": True,
        "data": inquiry,
    }


@app.get("/api/inquiries/categories/summary")
def get_category_summary(_token: str = Depends(verify_token)):
    """카테고리별 문의 건수를 조회합니다."""

    summary = {cat: 0 for cat in CATEGORIES}
    for inq in INQUIRIES.values():
        summary[inq["category"]] += 1

    return {
        "success": True,
        "data": summary,
        "categories": CATEGORIES,
    }


# ─── Email Endpoints ────────────────────────────────────

@app.post("/api/email/send")
def send_email(req: EmailSendRequest, _token: str = Depends(verify_token)):
    """이메일을 발송합니다 (Mock: 실제 발송하지 않고 기록만 남깁니다)."""

    # Simulate latency
    time.sleep(random.uniform(0.1, 0.2))

    # Simulate occasional failure (10% chance)
    if random.random() < 0.1:
        raise HTTPException(status_code=503, detail="Email service temporarily unavailable. Please retry.")

    email_record = {
        "message_id": f"msg-{uuid.uuid4().hex[:12]}",
        "to": req.to,
        "subject": req.subject,
        "body": req.body,
        "reply_to": req.reply_to,
        "status": "sent",
        "sent_at": datetime.now().isoformat(),
    }
    SENT_EMAILS.append(email_record)

    return {
        "success": True,
        "data": email_record,
    }


@app.get("/api/email/sent")
def list_sent_emails(_token: str = Depends(verify_token)):
    """발송된 이메일 목록을 조회합니다."""

    return {
        "success": True,
        "data": SENT_EMAILS,
        "total": len(SENT_EMAILS),
    }


# ─── Inquiry Endpoints ──────────────────────────────────

@app.get("/api/inquiries")
def list_inquiries(
    category: Optional[str] = None,
    _token: str = Depends(verify_token),
):
    """
    고객 문의 메일 목록을 조회합니다.
    워크플로우의 입력 데이터로 사용됩니다.

    - **category** (선택): billing, technical, account, feature_request, general 중 하나로 필터링
    """

    if category:
        filtered = [inq for inq in INQUIRIES if inq["expected_category"] == category]
        if not filtered:
            raise HTTPException(
                status_code=404,
                detail=f"No inquiries found for category '{category}'. "
                       f"Valid categories: billing, technical, account, feature_request, general",
            )
        return {
            "success": True,
            "data": filtered,
            "total": len(filtered),
            "category": category,
        }

    return {
        "success": True,
        "data": INQUIRIES,
        "total": len(INQUIRIES),
    }


@app.get("/api/inquiries/{inquiry_id}")
def get_inquiry(inquiry_id: str, _token: str = Depends(verify_token)):
    """
    특정 문의 메일을 조회합니다. 워크플로우 단건 실행 테스트에 사용합니다.

    - **inquiry_id**: INQ-001 ~ INQ-020
    """

    inquiry = next((inq for inq in INQUIRIES if inq["inquiry_id"] == inquiry_id), None)
    if not inquiry:
        raise HTTPException(status_code=404, detail=f"Inquiry '{inquiry_id}' not found")

    return {
        "success": True,
        "data": inquiry,
    }


@app.get("/api/inquiries/categories/list")
def list_categories(_token: str = Depends(verify_token)):
    """
    분류 카테고리 목록을 조회합니다.
    LLM에 분류를 요청할 때 이 카테고리 목록을 프롬프트에 포함할 수 있습니다.
    """

    return {
        "success": True,
        "data": INQUIRY_CATEGORIES,
        "total": len(INQUIRY_CATEGORIES),
    }


# ─── Run Server ──────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    print("=" * 55)
    print("  Mock API Server Starting...")
    print("  Inquiry API: http://localhost:8080/api/inquiries/")
    print("  CRM API:     http://localhost:8080/api/crm/")
    print("  Email API:   http://localhost:8080/api/email/")
    print("  Docs:        http://localhost:8080/docs")
    print("  API Key:     mock-api-key-12345")
    print("=" * 55)
    uvicorn.run(app, host="0.0.0.0", port=8080)
