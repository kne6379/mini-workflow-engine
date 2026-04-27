from typing import Any

from src.domain.errors import LLMOutputValidationError
from src.domain.reply_policy import (
    CATEGORIES, CATEGORY_GUIDELINES, CATEGORY_TONE,
    PLAN_RULES, REQUIRED_INCLUDES,
)
from src.engine.ports import AI
from src.nodes.prompts import (
    CLASSIFY_SYSTEM, CLASSIFY_USER_TEMPLATE,
    GENERATE_SYSTEM, GENERATE_USER_TEMPLATE,
    render_template,
)


async def classify_email(ai: AI, input_data: dict[str, Any]) -> dict[str, Any]:
    user = render_template(CLASSIFY_USER_TEMPLATE, input_data)
    response = await ai.chat_json(system=CLASSIFY_SYSTEM, user=user)
    category = response.get("category")
    if category not in CATEGORIES:
        raise LLMOutputValidationError(f"Unknown category: {category!r}")
    return {"category": category}


async def generate_reply(ai: AI, input_data: dict[str, Any]) -> dict[str, Any]:
    category = input_data["category"]
    plan = input_data["customer"].get("plan", "")
    user_context = {
        **input_data,
        "tone": CATEGORY_TONE[category],
        "guideline": CATEGORY_GUIDELINES[category],
        "plan_rule": PLAN_RULES.get(plan, ""),
        "required_includes": ", ".join(REQUIRED_INCLUDES[category]) or "(없음)",
    }
    user = render_template(GENERATE_USER_TEMPLATE, user_context)
    response = await ai.chat_json(system=GENERATE_SYSTEM, user=user)
    _validate_reply(response)
    return {"subject": response["subject"], "body": response["body"]}


def _validate_reply(response: dict[str, Any]) -> None:
    subject = response.get("subject")
    body = response.get("body")
    if not isinstance(subject, str) or not subject.strip():
        raise LLMOutputValidationError("subject가 비어있습니다.")
    if not isinstance(body, str) or not body.strip():
        raise LLMOutputValidationError("body가 비어있습니다.")
