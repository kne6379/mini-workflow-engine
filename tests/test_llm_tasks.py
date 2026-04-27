import pytest

from src.adapters.fake_ai import FakeAI
from src.domain.errors import LLMOutputValidationError
from src.nodes.llm import classify_email, generate_reply


async def test_classify_email_returns_category():
    ai = FakeAI({"category": "billing"})
    result = await classify_email(ai, {"subject": "결제 오류", "body": "..."})
    assert result == {"category": "billing"}


async def test_classify_email_passes_subject_and_body_in_user_prompt():
    ai = FakeAI({"category": "general"})
    await classify_email(ai, {"subject": "Hello", "body": "World"})
    assert "Hello" in ai.last_user
    assert "World" in ai.last_user


async def test_classify_email_rejects_unknown_category():
    ai = FakeAI({"category": "sales"})
    with pytest.raises(LLMOutputValidationError):
        await classify_email(ai, {"subject": "x", "body": "y"})


async def test_generate_reply_returns_subject_and_body():
    body_text = "안녕하세요. 예상 처리 기한 3영업일 이내로 처리하며 접수 확인 번호 ACK-001을 안내드립니다."
    ai = FakeAI({"subject": "Re: 결제 오류", "body": body_text})
    result = await generate_reply(ai, {
        "inquiry": {"subject": "결제 오류", "body": "..."},
        "category": "billing",
        "customer": {"name": "김민수", "plan": "Enterprise", "status": "active"},
    })
    assert result["subject"] == "Re: 결제 오류"
    assert result["body"] == body_text


async def test_generate_reply_rejects_empty_body():
    ai = FakeAI({"subject": "Re: x", "body": "   "})
    with pytest.raises(LLMOutputValidationError):
        await generate_reply(ai, {
            "inquiry": {"subject": "x", "body": "y"},
            "category": "general",
            "customer": {"name": "n", "plan": "Free", "status": "active"},
        })


async def test_generate_reply_passes_general_with_no_required_keywords():
    ai = FakeAI({"subject": "Re: x", "body": "안내해 드리겠습니다"})
    result = await generate_reply(ai, {
        "inquiry": {"subject": "x", "body": "y"},
        "category": "general",
        "customer": {"name": "n", "plan": "Free", "status": "active"},
    })
    assert result["body"] == "안내해 드리겠습니다"


async def test_generate_reply_places_dynamic_context_in_user_message():
    body_text = "예상 처리 기한 3영업일, 접수 확인 번호 ACK-001"
    ai = FakeAI({"subject": "Re: x", "body": body_text})
    await generate_reply(ai, {
        "inquiry": {"subject": "x", "body": "y"},
        "category": "billing",
        "customer": {"name": "n", "plan": "Enterprise", "status": "active"},
    })
    # 정적 (system, 캐시 가능): persona + 금지사항 + 출력 스키마
    assert "확인되지 않은 정보" in ai.last_system
    assert "subject" in ai.last_system
    # 동적 (user, 호출별 변화): 톤 / 가이드라인 / 플랜 규칙 / 필수 포함
    assert "정중하고 신속" in ai.last_user
    assert "예상 처리 기한" in ai.last_user
    assert "전담 매니저" in ai.last_user
    # 동적 정보가 system에 새지 않아야 함
    assert "전담 매니저" not in ai.last_system
    assert "정중하고 신속" not in ai.last_system
