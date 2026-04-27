from typing import Any

from pydantic import ValidationError

from src.domain.errors import LLMOutputValidationError
from src.domain.reply_policy import (
    CATEGORY_GUIDELINES, CATEGORY_TONE,
    PLAN_RULES, REQUIRED_INCLUDES,
)
from src.engine.ports import AI
from src.nodes.llm_schemas import (
    ClassifyEmailInput,
    ClassifyEmailOutput,
    GenerateReplyInput,
    GenerateReplyOutput,
)
from src.nodes.prompts import (
    CLASSIFY_SYSTEM, CLASSIFY_USER_TEMPLATE,
    GENERATE_SYSTEM, GENERATE_USER_TEMPLATE,
    render_template,
)


async def classify_email(ai: AI, input_data: dict[str, Any]) -> dict[str, Any]:
    validated_input = ClassifyEmailInput.model_validate(input_data)
    user = render_template(CLASSIFY_USER_TEMPLATE, validated_input.model_dump())
    response = await ai.chat_json(system=CLASSIFY_SYSTEM, user=user)
    try:
        return ClassifyEmailOutput.model_validate(response).model_dump()
    except ValidationError as exc:
        raise LLMOutputValidationError(f"알 수 없는 category: {response.get('category')!r}") from exc


async def generate_reply(ai: AI, input_data: dict[str, Any]) -> dict[str, Any]:
    validated_input = GenerateReplyInput.model_validate(input_data)
    category = validated_input.category
    plan = validated_input.customer.plan or ""
    context = validated_input.model_dump()
    user_context = {
        **context,
        "tone": CATEGORY_TONE[category],
        "guideline": CATEGORY_GUIDELINES[category],
        "plan_rule": PLAN_RULES.get(plan, ""),
        "required_includes": ", ".join(REQUIRED_INCLUDES[category]) or "(없음)",
    }
    user = render_template(GENERATE_USER_TEMPLATE, user_context)
    response = await ai.chat_json(system=GENERATE_SYSTEM, user=user)
    try:
        return GenerateReplyOutput.model_validate(response).model_dump()
    except ValidationError as exc:
        raise LLMOutputValidationError("LLM 응답의 subject 또는 body가 비어있습니다.") from exc
