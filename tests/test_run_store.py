from datetime import datetime, timezone

import pytest

from src.domain.run import NodeState, RunStatus, WorkflowRun
from src.adapters.run_store import RunStoreAdapter, RunNotFoundError


def test_store_saves_and_returns_run():
    store = RunStoreAdapter()
    now = datetime.now(timezone.utc)
    run = WorkflowRun(
        run_id="run_123",
        workflow_key="customer_support_auto_reply",
        status=RunStatus.PENDING,
        current_node_key=None,
        context={"input": {"inquiry_id": "INQ-002"}, "nodes": {}},
        node_states={"fetch_inquiry": NodeState()},
        created_at=now,
        updated_at=now,
    )

    store.save(run)

    assert store.get("run_123").run_id == "run_123"
    assert store.list_runs() == [run]


def test_store_raises_for_missing_run():
    store = RunStoreAdapter()

    with pytest.raises(RunNotFoundError):
        store.get("missing")


def _new_run(run_id: str, inquiry_id: str, status=RunStatus.PENDING) -> WorkflowRun:
    now = datetime.now(timezone.utc)
    return WorkflowRun(
        run_id=run_id,
        workflow_key="customer_support_auto_reply",
        status=status,
        current_node_key=None,
        context={"input": {"inquiry_id": inquiry_id}, "nodes": {}},
        node_states={"x": NodeState()},
        created_at=now,
        updated_at=now,
    )


def test_find_by_inquiry_returns_none_when_unseen():
    store = RunStoreAdapter()
    assert store.find_by_inquiry("INQ-999") is None


def test_find_by_inquiry_returns_latest_run_for_inquiry():
    store = RunStoreAdapter()
    run1 = _new_run("run_1", "INQ-001", status=RunStatus.WAITING_APPROVAL)
    store.save(run1)
    found = store.find_by_inquiry("INQ-001")
    assert found is not None
    assert found.run_id == "run_1"


def test_find_by_inquiry_updates_index_on_save():
    store = RunStoreAdapter()
    run1 = _new_run("run_1", "INQ-001", status=RunStatus.REJECTED)
    store.save(run1)
    run2 = _new_run("run_2", "INQ-001", status=RunStatus.WAITING_APPROVAL)
    store.save(run2)
    found = store.find_by_inquiry("INQ-001")
    assert found.run_id == "run_2"
