import json
from typing import Any

from openai import AsyncOpenAI

from workflow_engine.errors import WorkflowEngineError
from workflow_engine.policies import CATEGORIES, CATEGORY_GUIDELINES, PLAN_RULES, PROHIBITED_RULES


def validate_category(category: str) -> str:
    if category not in CATEGORIES:
        raise WorkflowEngineError(f"Invalid category from AI: {category}")
    return category


class FakeAIAdapter:
    async def run_task(self, task_name: str, input_data: dict[str, Any]) -> dict[str, Any]:
        if task_name == "classify_email":
            return {"category": self._classify(input_data)}
        if task_name == "generate_reply":
            inquiry = input_data["inquiry"]
            customer = input_data["customer"]
            category = input_data["category"]
            subject = f"Re: {inquiry['subject']}"
            body = (
                f"안녕하세요 {customer.get('name', '고객')}님. "
                f"{customer.get('plan', '고객')} 플랜 문의를 확인했습니다. "
                f"{CATEGORY_GUIDELINES[category]}"
            )
            return {"subject": subject, "body": body}
        raise WorkflowEngineError(f"Unknown AI task: {task_name}")

    def _classify(self, input_data: dict[str, Any]) -> str:
        text = f"{input_data.get('subject', '')} {input_data.get('body', '')}"
        if any(keyword in text for keyword in ["결제", "청구", "환불", "요금", "카드"]):
            return "billing"
        if any(keyword in text for keyword in ["API", "오류", "버그", "웹훅", "장애"]):
            return "technical"
        if any(keyword in text for keyword in ["계정", "비밀번호", "SSO", "권한", "로그인"]):
            return "account"
        if any(keyword in text for keyword in ["기능", "추가", "개선", "요청"]):
            return "feature_request"
        return "general"


class OpenAIAdapter:
    def __init__(self, api_key: str, model: str):
        self.client = AsyncOpenAI(api_key=api_key)
        self.model = model

    async def run_task(self, task_name: str, input_data: dict[str, Any]) -> dict[str, Any]:
        if task_name == "classify_email":
            return await self._classify_email(input_data)
        if task_name == "generate_reply":
            return await self._generate_reply(input_data)
        raise WorkflowEngineError(f"Unknown AI task: {task_name}")

    async def _classify_email(self, input_data: dict[str, Any]) -> dict[str, Any]:
        prompt = (
            "다음 고객 문의를 billing, technical, account, feature_request, general 중 하나로 분류하고 "
            "JSON 형식으로만 응답하세요. 필요한 키는 category 하나입니다.\n"
            f"제목: {input_data['subject']}\n본문: {input_data['body']}"
        )
        parsed = await self._json_response(prompt)
        return {"category": validate_category(parsed["category"])}

    async def _generate_reply(self, input_data: dict[str, Any]) -> dict[str, Any]:
        category = input_data["category"]
        customer = input_data["customer"]
        inquiry = input_data["inquiry"]
        prompt = (
            "고객 문의 답변 초안을 JSON 형식으로만 작성하세요. 필요한 키는 subject, body입니다.\n"
            f"문의: {json.dumps(inquiry, ensure_ascii=False)}\n"
            f"고객: {json.dumps(customer, ensure_ascii=False)}\n"
            f"카테고리: {category}\n"
            f"응답 가이드라인: {CATEGORY_GUIDELINES[category]}\n"
            f"플랜 규칙: {PLAN_RULES.get(customer.get('plan', ''), '')}\n"
            f"금지 사항: {json.dumps(PROHIBITED_RULES, ensure_ascii=False)}"
        )
        parsed = await self._json_response(prompt)
        return {"subject": parsed["subject"], "body": parsed["body"]}

    async def _json_response(self, prompt: str) -> dict[str, Any]:
        response = await self.client.chat.completions.create(
            model=self.model,
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"},
        )
        content = response.choices[0].message.content or "{}"
        return json.loads(content)
