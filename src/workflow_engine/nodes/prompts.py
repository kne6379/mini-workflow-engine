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
