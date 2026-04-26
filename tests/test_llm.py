import pytest

from workflow_engine.errors import WorkflowEngineError
from workflow_engine.llm import FakeLLMClient, LLMTaskRegistry, validate_category


def test_validate_category_accepts_assignment_categories():
    assert validate_category("billing") == "billing"


def test_validate_category_rejects_unknown_category():
    with pytest.raises(WorkflowEngineError):
        validate_category("sales")


async def test_fake_llm_classifies_from_subject_keywords():
    llm = FakeLLMClient()

    output = await llm.run_task("classify_email", {
        "subject": "카드 결제가 계속 실패합니다",
        "body": "결제 오류가 발생합니다",
    })

    assert output == {"category": "billing"}


async def test_fake_llm_generates_subject_and_body():
    llm = FakeLLMClient()

    output = await llm.run_task("generate_reply", {
        "inquiry": {"subject": "카드 결제가 계속 실패합니다"},
        "category": "billing",
        "customer": {"name": "김민수", "plan": "Enterprise"},
    })

    assert output["subject"] == "Re: 카드 결제가 계속 실패합니다"
    assert "김민수" in output["body"]
    assert "Enterprise" in output["body"]


def test_llm_task_registry_returns_client_task_runner():
    registry = LLMTaskRegistry(FakeLLMClient())

    assert registry.client.__class__.__name__ == "FakeLLMClient"
