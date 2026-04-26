from workflow_engine.adapters.fake_ai import FakeAI


async def test_fake_ai_returns_registered_response():
    ai = FakeAI({"category": "billing"})
    result = await ai.chat_json(system="sys", user="user")
    assert result == {"category": "billing"}


async def test_fake_ai_records_last_system_and_user():
    ai = FakeAI({"x": 1})
    await ai.chat_json(system="hello", user="world")
    assert ai.last_system == "hello"
    assert ai.last_user == "world"
