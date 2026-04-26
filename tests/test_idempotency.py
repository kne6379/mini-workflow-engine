def test_same_inquiry_returns_same_run_when_waiting_approval(client, deps):
    first = client.post("/workflow-runs", json={
        "workflow_key": "customer_support_auto_reply",
        "inquiry_id": "INQ-002",
    }).json()
    second = client.post("/workflow-runs", json={
        "workflow_key": "customer_support_auto_reply",
        "inquiry_id": "INQ-002",
    }).json()
    assert first["run_id"] == second["run_id"]
    assert first["status"] == second["status"]


def test_same_inquiry_returns_same_run_after_completion(client):
    started = client.post("/workflow-runs", json={
        "workflow_key": "customer_support_auto_reply",
        "inquiry_id": "INQ-002",
    }).json()
    client.post(f"/workflow-runs/{started['run_id']}/approval", json={"decision": "approve"})
    second = client.post("/workflow-runs", json={
        "workflow_key": "customer_support_auto_reply",
        "inquiry_id": "INQ-002",
    }).json()
    assert started["run_id"] == second["run_id"]
    assert second["status"] == "COMPLETED"


def test_rejected_inquiry_allows_new_run(client):
    started = client.post("/workflow-runs", json={
        "workflow_key": "customer_support_auto_reply",
        "inquiry_id": "INQ-002",
    }).json()
    client.post(
        f"/workflow-runs/{started['run_id']}/approval",
        json={"decision": "reject", "reason": "내용 부정확"},
    )
    second = client.post("/workflow-runs", json={
        "workflow_key": "customer_support_auto_reply",
        "inquiry_id": "INQ-002",
    }).json()
    assert started["run_id"] != second["run_id"]


def test_timed_out_inquiry_allows_new_run(client, deps):
    from datetime import datetime, timedelta, timezone
    started = client.post("/workflow-runs", json={
        "workflow_key": "customer_support_auto_reply",
        "inquiry_id": "INQ-002",
    }).json()
    run = deps.store.get(started["run_id"])
    run.approval.deadline_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    deps.store.save(run)
    # GET으로 lazy 만료 트리거
    client.get(f"/workflow-runs/{started['run_id']}")
    second = client.post("/workflow-runs", json={
        "workflow_key": "customer_support_auto_reply",
        "inquiry_id": "INQ-002",
    }).json()
    assert started["run_id"] != second["run_id"]
