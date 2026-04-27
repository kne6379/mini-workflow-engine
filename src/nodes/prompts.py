from typing import Any

from src.engine.input_mapping import render_inputs


def render_template(template: str, context: dict[str, Any]) -> str:
    """input_mapping의 {{ ... }} 렌더링을 prompt 템플릿에 재사용."""
    return str(render_inputs({"_": template}, context)["_"])


CLASSIFY_SYSTEM = (
    "당신은 고객 문의 메일을 5개 카테고리 중 하나로 분류하는 도우미입니다.\n"
    "카테고리 정의:\n"
    "- billing: 결제, 환불, 청구, 요금 관련\n"
    "- technical: 기술 오류, 버그, API, 시스템 장애\n"
    "- account: 계정, 로그인, 비밀번호, 권한, SSO\n"
    "- feature_request: 기능 요청, 개선 제안\n"
    "- general: 일반 문의, 사용법, 기타\n"
    "출력 스키마 (JSON):\n"
    '{ "category": "billing" | "technical" | "account" | "feature_request" | "general" }\n'
    "스키마 외 다른 키는 포함하지 마세요."
)
CLASSIFY_USER_TEMPLATE = "제목: {{ subject }}\n본문: {{ body }}"

GENERATE_SYSTEM = (
    "당신은 고객 지원 이메일 답변 초안을 작성하는 도우미입니다.\n"
    "금지 사항:\n"
    "- 확인되지 않은 정보를 단정하지 않는다.\n"
    "- 구체적 금액을 직접 언급하지 않는다.\n"
    "- 타 고객 사례를 언급하지 않는다.\n"
    "- 내부 시스템 구조를 노출하지 않는다.\n"
    "- 보안 정책 우회 방법을 안내하지 않는다.\n"
    "- 확정되지 않은 출시 일정을 약속하지 않는다.\n"
    "- 경쟁사 제품과 비교하지 않는다.\n"
    "출력 스키마 (JSON):\n"
    '{ "subject": string, "body": string }\n'
    "스키마 외 다른 키는 포함하지 마세요. 두 값 모두 비어있지 않은 문자열이어야 합니다."
)
GENERATE_USER_TEMPLATE = (
    "## 문의\n"
    "제목: {{ inquiry.subject }}\n"
    "본문: {{ inquiry.body }}\n"
    "카테고리: {{ category }}\n"
    "\n"
    "## 고객\n"
    "이름 {{ customer.name }}, 플랜 {{ customer.plan }}, 상태 {{ customer.status }}\n"
    "\n"
    "## 작성 규칙\n"
    "- 톤: {{ tone }}\n"
    "- 가이드라인: {{ guideline }}\n"
    "- {{ customer.plan }} 플랜 규칙: {{ plan_rule }}\n"
    "- 본문에 다음 정보를 반드시 포함하세요: {{ required_includes }}"
)
