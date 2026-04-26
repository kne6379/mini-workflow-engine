import pytest

from workflow_engine.adapters.ai import FakeAIAdapter, validate_category
from workflow_engine.domain.errors import WorkflowEngineError
from workflow_engine.registries import AITaskRegistry


def test_validate_category_accepts_assignment_categories():
    assert validate_category("billing") == "billing"


def test_validate_category_rejects_unknown_category():
    with pytest.raises(WorkflowEngineError):
        validate_category("sales")


async def test_fake_llm_classifies_from_subject_keywords():
    llm = FakeAIAdapter()

    output = await llm.run_task("classify_email", {
        "subject": "카드 결제가 계속 실패합니다",
        "body": "결제 오류가 발생합니다",
    })

    assert output == {"category": "billing"}


async def test_fake_llm_generates_subject_and_body():
    llm = FakeAIAdapter()

    output = await llm.run_task("generate_reply", {
        "inquiry": {"subject": "카드 결제가 계속 실패합니다"},
        "category": "billing",
        "customer": {"name": "김민수", "plan": "Enterprise"},
    })

    assert output["subject"] == "Re: 카드 결제가 계속 실패합니다"
    assert "김민수" in output["body"]
    assert "Enterprise" in output["body"]


def test_ai_task_registry_returns_adapter_task_runner():
    registry = AITaskRegistry(FakeAIAdapter())

    assert registry.ai.__class__.__name__ == "FakeAIAdapter"
