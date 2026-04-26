import asyncio
from collections.abc import Awaitable, Callable
from datetime import datetime, timezone


class ApprovalTimer:
    """per-run asyncio Task로 승인 deadline을 능동적으로 감시한다."""

    def __init__(self) -> None:
        self._tasks: dict[str, asyncio.Task] = {}
        self._on_expire: Callable[[str], Awaitable[None]] | None = None

    def set_on_expire(self, callback: Callable[[str], Awaitable[None]]) -> None:
        self._on_expire = callback

    def schedule(self, run_id: str, deadline_at: datetime) -> None:
        assert self._on_expire is not None, "set_on_expire must be called before schedule"
        existing = self._tasks.get(run_id)
        if existing is not None and not existing.done():
            existing.cancel()
        seconds = max(0.0, (deadline_at - datetime.now(timezone.utc)).total_seconds())
        self._tasks[run_id] = asyncio.create_task(self._wait_and_expire(run_id, seconds))

    async def _wait_and_expire(self, run_id: str, seconds: float) -> None:
        try:
            await asyncio.sleep(seconds)
        except asyncio.CancelledError:
            return
        assert self._on_expire is not None
        await self._on_expire(run_id)
        self._tasks.pop(run_id, None)

    def cancel(self, run_id: str) -> None:
        task = self._tasks.pop(run_id, None)
        if task is not None and not task.done():
            task.cancel()
