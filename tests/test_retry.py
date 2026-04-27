import pytest

from workflow_engine.engine.retry import RetryExecutor, RetryPolicy


async def test_retry_executor_retries_any_exception_until_success():
    attempts = 0

    async def operation():
        nonlocal attempts
        attempts += 1
        if attempts < 3:
            raise RuntimeError("transient failure")
        return {"ok": True}

    executor = RetryExecutor(RetryPolicy(max_attempts=3, initial_delay_seconds=0))
    result = await executor.run("op", operation)

    assert result == {"ok": True}
    assert attempts == 3


async def test_retry_executor_raises_last_exception_after_attempts_are_exhausted():
    attempts = 0

    async def operation():
        nonlocal attempts
        attempts += 1
        raise ValueError(f"failure {attempts}")

    executor = RetryExecutor(RetryPolicy(max_attempts=3, initial_delay_seconds=0))

    with pytest.raises(ValueError, match="failure 3"):
        await executor.run("op", operation)

    assert attempts == 3
