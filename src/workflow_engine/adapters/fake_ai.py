from typing import Any

from workflow_engine.domain.errors import WorkflowEngineError
from workflow_engine.domain.reply_policy import CATEGORY_GUIDELINES


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
