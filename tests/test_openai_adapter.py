from unittest.mock import AsyncMock, MagicMock

from src.adapters.openai import OpenAIAdapter


async def test_openai_adapter_passes_system_and_user_messages():
    adapter = OpenAIAdapter(api_key="test", model="gpt-4.1-mini")
    fake_completion = MagicMock()
    fake_completion.choices = [MagicMock(message=MagicMock(content='{"ok": true}'))]
    adapter.client.chat.completions.create = AsyncMock(return_value=fake_completion)

    result = await adapter.chat_json(system="be helpful", user="hi")

    assert result == {"ok": True}
    call = adapter.client.chat.completions.create.call_args
    assert call.kwargs["messages"] == [
        {"role": "system", "content": "be helpful"},
        {"role": "user", "content": "hi"},
    ]
    assert call.kwargs["response_format"] == {"type": "json_object"}


async def test_openai_adapter_uses_temperature_zero_by_default():
    adapter = OpenAIAdapter(api_key="test", model="gpt-4.1-mini")
    fake_completion = MagicMock()
    fake_completion.choices = [MagicMock(message=MagicMock(content="{}"))]
    adapter.client.chat.completions.create = AsyncMock(return_value=fake_completion)

    await adapter.chat_json(system="s", user="u")

    assert adapter.client.chat.completions.create.call_args.kwargs["temperature"] == 0
