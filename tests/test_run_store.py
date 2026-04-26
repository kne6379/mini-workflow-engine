from datetime import datetime, timezone

import pytest

from workflow_engine.domain.run import NodeState, RunStatus, WorkflowRun
from workflow_engine.adapters.run_store import RunStoreAdapter, RunNotFoundError


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
