from typing import Any, Awaitable, Callable

from workflow_engine.domain.errors import WorkflowEngineError
from workflow_engine.engine.ports import AI, Tool

TaskFn = Callable[[AI, dict[str, Any]], Awaitable[dict[str, Any]]]


class ToolRegistry:
    def __init__(self, tools: dict[str, Tool]):
        self._tools = tools

    def get(self, name: str) -> Tool:
        try:
            return self._tools[name]
        except KeyError as exc:
            raise KeyError(f"Unknown tool: {name}") from exc


class AITaskRegistry:
    def __init__(self, tasks: dict[str, TaskFn], profiles: dict[str, AI]):
        self._tasks = tasks
        self._profiles = profiles

    async def run(self, task_name: str, input_data: dict[str, Any]) -> dict[str, Any]:
        task_fn = self._tasks.get(task_name)
        if task_fn is None:
            raise WorkflowEngineError(f"Unknown AI task: {task_name}")
        adapter = self._profiles.get(task_name)
        if adapter is None:
            raise WorkflowEngineError(f"No AI profile registered for task: {task_name}")
        return await task_fn(adapter, input_data)
