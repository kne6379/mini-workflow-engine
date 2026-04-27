import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import TypeVar

T = TypeVar("T")


@dataclass(frozen=True)
class RetryPolicy:
    max_attempts: int = 3
    initial_delay_seconds: float = 0.5
    multiplier: float = 2.0
    max_delay_seconds: float = 5.0


class RetryExecutor:
    def __init__(self, policy: RetryPolicy):
        self.policy = policy

    async def run(self, operation: Callable[[], Awaitable[T]]) -> T:
        delay = self.policy.initial_delay_seconds
        last_error: Exception | None = None
        for attempt in range(1, self.policy.max_attempts + 1):
            try:
                return await operation()
            except Exception as exc:
                last_error = exc
                if attempt == self.policy.max_attempts:
                    break
                if delay > 0:
                    await asyncio.sleep(delay)
                delay = min(delay * self.policy.multiplier, self.policy.max_delay_seconds)
        assert last_error is not None
        raise last_error
