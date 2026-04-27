import pytest

from src.adapters.fake_ai import FakeAI
from src.domain.errors import WorkflowEngineError
from src.engine.registries import AITaskRegistry


async def _passthrough(ai, input_data):
    return await ai.chat_json(system="s", user="u")


async def test_registry_dispatches_to_registered_task_and_profile():
    classify_ai = FakeAI({"category": "billing"})
    generate_ai = FakeAI({"subject": "x", "body": "y"})
    registry = AITaskRegistry(
        tasks={"classify_email": _passthrough, "generate_reply": _passthrough},
        profiles={"classify_email": classify_ai, "generate_reply": generate_ai},
    )
    classify_result = await registry.run("classify_email", {})
    generate_result = await registry.run("generate_reply", {})
    assert classify_result == {"category": "billing"}
    assert generate_result == {"subject": "x", "body": "y"}


async def test_registry_uses_separate_adapter_per_action():
    classify_ai = FakeAI({"category": "billing"})
    generate_ai = FakeAI({"subject": "x", "body": "y"})
    registry = AITaskRegistry(
        tasks={"classify_email": _passthrough, "generate_reply": _passthrough},
        profiles={"classify_email": classify_ai, "generate_reply": generate_ai},
    )
    await registry.run("classify_email", {})
    await registry.run("generate_reply", {})
    assert classify_ai.last_user == "u"
    assert generate_ai.last_user == "u"


async def test_registry_raises_for_unknown_task():
    registry = AITaskRegistry(tasks={}, profiles={})
    with pytest.raises(WorkflowEngineError, match="등록되지 않은 AI task"):
        await registry.run("missing", {})


async def test_registry_raises_when_profile_missing():
    registry = AITaskRegistry(
        tasks={"classify_email": _passthrough},
        profiles={},  # 프로필 미등록
    )
    with pytest.raises(WorkflowEngineError, match="AI profile이 없습니다"):
        await registry.run("classify_email", {})
