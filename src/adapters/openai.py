import json
from typing import Any

from openai import AsyncOpenAI

from src.engine.ports import AI


class OpenAIAdapter(AI):
    def __init__(self, api_key: str, model: str, temperature: float = 0):
        self.client = AsyncOpenAI(api_key=api_key)
        self.model = model
        self.temperature = temperature

    async def chat_json(self, system: str, user: str) -> dict[str, Any]:
        response = await self.client.chat.completions.create(
            model=self.model,
            temperature=self.temperature,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            response_format={"type": "json_object"},
        )
        return json.loads(response.choices[0].message.content or "{}")
