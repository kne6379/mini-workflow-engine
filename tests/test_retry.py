import pytest

from workflow_engine.engine.retry import RetryExecutor, RetryPolicy, TransientExternalError


async def test_retry_executor_retries_transient_errors():
    attempts = 0

    async def operation():
        nonlocal attempts
        attempts += 1
        if attempts < 3:
            raise TransientExternalError("service unavailable")
        return {"ok": True}

    executor = RetryExecutor(RetryPolicy(max_attempts=3, initial_delay_seconds=0))
    result = await executor.run("email_send", operation)

    assert result == {"ok": True}
    assert attempts == 3


async def test_retry_executor_raises_after_attempts_are_exhausted():
    attempts = 0

    async def operation():
        nonlocal attempts
        attempts += 1
        raise TransientExternalError("service unavailable")

    executor = RetryExecutor(RetryPolicy(max_attempts=3, initial_delay_seconds=0))

    with pytest.raises(TransientExternalError):
        await executor.run("email_send", operation)

    assert attempts == 3
