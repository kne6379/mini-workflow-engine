from typing import Any


class FakeAI:
    """Test용 결정적 응답 어댑터.

    각 호출마다 미리 등록된 단일 응답을 반환한다. system/user prompt도 보관해
    테스트가 prompt 내용을 단언할 수 있다.
    """

    def __init__(self, response: dict[str, Any]):
        self._response = response
        self.last_system: str | None = None
        self.last_user: str | None = None

    async def chat_json(self, system: str, user: str) -> dict[str, Any]:
        self.last_system = system
        self.last_user = user
        return self._response
