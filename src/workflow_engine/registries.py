from typing import Any

from workflow_engine.errors import WorkflowEngineError
from workflow_engine.ports import AI, Tool


class ToolRegistry:
    def __init__(self, tools: dict[str, Tool]):
        self._tools = tools

    def get(self, name: str) -> Tool:
        try:
            return self._tools[name]
        except KeyError as exc:
            raise KeyError(f"Unknown tool: {name}") from exc


class AITaskRegistry:
    def __init__(self, ai: AI):
        self.ai = ai

    async def run(self, task_name: str, input_data: dict[str, Any]) -> dict[str, Any]:
        if task_name not in {"classify_email", "generate_reply"}:
            raise WorkflowEngineError(f"Unknown AI task: {task_name}")
        return await self.ai.run_task(task_name, input_data)
