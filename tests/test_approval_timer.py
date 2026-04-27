import asyncio
from datetime import datetime, timedelta, timezone

import pytest

from src.engine.approval_timer import ApprovalTimer


async def test_schedule_fires_callback_after_deadline():
    fired: list[str] = []

    async def on_expire(run_id: str) -> None:
        fired.append(run_id)

    timer = ApprovalTimer()
    timer.set_on_expire(on_expire)
    deadline = datetime.now(timezone.utc) + timedelta(milliseconds=50)
    timer.schedule("run_1", deadline)
    await asyncio.sleep(0.15)
    assert fired == ["run_1"]


async def test_cancel_prevents_callback():
    fired: list[str] = []

    async def on_expire(run_id: str) -> None:
        fired.append(run_id)

    timer = ApprovalTimer()
    timer.set_on_expire(on_expire)
    deadline = datetime.now(timezone.utc) + timedelta(milliseconds=100)
    timer.schedule("run_1", deadline)
    timer.cancel("run_1")
    await asyncio.sleep(0.2)
    assert fired == []


async def test_schedule_replaces_previous_task_for_same_run_id():
    fired: list[tuple[str, float]] = []

    async def on_expire(run_id: str) -> None:
        fired.append((run_id, asyncio.get_event_loop().time()))

    timer = ApprovalTimer()
    timer.set_on_expire(on_expire)
    deadline_a = datetime.now(timezone.utc) + timedelta(milliseconds=200)
    timer.schedule("run_1", deadline_a)
    deadline_b = datetime.now(timezone.utc) + timedelta(milliseconds=50)
    timer.schedule("run_1", deadline_b)  # 새 태스크가 직전 태스크를 cancel해야 함
    await asyncio.sleep(0.3)
    assert len(fired) == 1


async def test_schedule_with_past_deadline_fires_immediately():
    fired: list[str] = []

    async def on_expire(run_id: str) -> None:
        fired.append(run_id)

    timer = ApprovalTimer()
    timer.set_on_expire(on_expire)
    deadline = datetime.now(timezone.utc) - timedelta(seconds=5)
    timer.schedule("run_1", deadline)
    await asyncio.sleep(0.05)
    assert fired == ["run_1"]


def test_schedule_without_callback_raises_assertion():
    timer = ApprovalTimer()
    with pytest.raises(AssertionError):
        timer.schedule("run_1", datetime.now(timezone.utc))
