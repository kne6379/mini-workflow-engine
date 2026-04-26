from typing import Any

from workflow_engine.engine.ports import AI


class FakeAI(AI):
    """Test용 결정적 응답 어댑터.

    각 호출마다 미리 등록된 단일 응답을 반환한다. system/user prompt도 보관해
    테스트가 prompt 내용을 단언할 수 있다.

    주의: last_system / last_user는 매 호출마다 덮어써진다. 한 인스턴스로
    두 LLM 호출을 처리하면 첫 호출의 prompt가 유실된다. 두 호출의 prompt를
    모두 검증해야 한다면 액션마다 별도 FakeAI 인스턴스를 주입할 것.
    """

    def __init__(self, response: dict[str, Any]):
        self._response = response
        self.last_system: str | None = None
        self.last_user: str | None = None

    async def chat_json(self, system: str, user: str) -> dict[str, Any]:
        self.last_system = system
        self.last_user = user
        return self._response
