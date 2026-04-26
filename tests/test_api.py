def test_openapi_documentation_is_korean(client):
    schema = client.get("/openapi.json").json()
    assert schema["info"]["title"] == "AI 워크플로우 실행 엔진"
    assert "워크플로우 실행" in schema["paths"]["/workflow-runs"]["post"]["summary"]


def test_start_workflow_endpoint_returns_run_waiting_for_approval(client):
    response = client.post("/workflow-runs", json={
        "workflow_key": "customer_support_auto_reply",
        "inquiry_id": "INQ-002",
    })
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "WAITING_APPROVAL"
    assert body["current_node_key"] == "wait_for_approval"


def test_start_workflow_endpoint_rejects_unknown_workflow_key(client):
    response = client.post("/workflow-runs", json={
        "workflow_key": "unknown_workflow",
        "inquiry_id": "INQ-002",
    })
    assert response.status_code == 404
    assert response.json()["detail"] == "지원하지 않는 워크플로우입니다."


def test_approval_endpoint_completes_run(client):
    started = client.post("/workflow-runs", json={
        "workflow_key": "customer_support_auto_reply",
        "inquiry_id": "INQ-002",
    }).json()
    response = client.post(f"/workflow-runs/{started['run_id']}/approval", json={"decision": "approve"})
    assert response.status_code == 200
    assert response.json()["status"] == "COMPLETED"


def test_approval_endpoint_returns_404_for_missing_run(client):
    response = client.post("/workflow-runs/run_missing/approval", json={"decision": "approve"})
    assert response.status_code == 404
    assert response.json()["detail"] == "워크플로우 실행을 찾을 수 없습니다."


def test_approval_endpoint_rejects_run_that_is_not_waiting(client):
    started = client.post("/workflow-runs", json={
        "workflow_key": "customer_support_auto_reply",
        "inquiry_id": "INQ-002",
    }).json()
    client.post(f"/workflow-runs/{started['run_id']}/approval", json={"decision": "approve"})
    response = client.post(f"/workflow-runs/{started['run_id']}/approval", json={"decision": "approve"})
    assert response.status_code == 409
    assert response.json()["detail"] == "승인 대기 상태가 아닙니다."


def test_get_endpoint_lazy_expires_overdue_run(client, deps):
    from datetime import datetime, timedelta, timezone
    started = client.post("/workflow-runs", json={
        "workflow_key": "customer_support_auto_reply",
        "inquiry_id": "INQ-002",
    }).json()
    run_id = started["run_id"]
    # deadline을 강제로 과거로
    run = deps.store.get(run_id)
    run.approval.deadline_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    deps.store.save(run)

    response = client.get(f"/workflow-runs/{run_id}")
    assert response.status_code == 200
    assert response.json()["status"] == "TIMED_OUT"
