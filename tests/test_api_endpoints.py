"""Tests for Milestone 7: Docket FastAPI REST API Endpoints.

Tests:
1. GET /api/health - Service health and version check.
2. GET /api/disputes - High-density dispute summaries for AG Grid triage.
3. GET /api/disputes/{id} - Full case deep dive (order, shipments, claims, policy diagnostic).
4. POST /api/disputes/{id}/ticket - HMAC approval ticket generation.
5. POST /api/disputes/{id}/authorize - Human merchant approval recording.
6. POST /api/disputes/{id}/dispatch - Controlled evidence submission to PayPal.
7. GET /api/audit-trail - Cryptographic hash-chained audit ledger inspection.
8. GET /api/eval/scorecard - Official 20-scenario benchmark evaluation results.
"""

from decimal import Decimal
import json
import pytest
from fastapi.testclient import TestClient
from unittest.mock import MagicMock, patch

from docket.api.app import create_app


@pytest.fixture
def client(tmp_path):
    audit_file = tmp_path / "test_api_audit_trail.jsonl"
    app = create_app(audit_log_path=audit_file)
    with TestClient(app) as test_client:
        test_client.post("/api/auth/demo-session", json={"profile_id": "merchant_supervisor_admin"})
        yield test_client


def test_api_health(client):
    resp = client.get("/api/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert "version" in data
    assert "timestamp" in data


def test_api_get_disputes_list(client):
    resp = client.get("/api/disputes")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    assert len(data) >= 20  # Catalog + Sandbox fixture

    # Find the real sandbox dispute
    sandbox_disp = next((d for d in data if d["dispute_id"] == "PP-R-NKI-10193390"), None)
    assert sandbox_disp is not None
    assert sandbox_disp["amount"] == "25.00"
    assert sandbox_disp["currency"] == "USD"
    assert sandbox_disp["reason"] == "MERCHANDISE_OR_SERVICE_NOT_RECEIVED"
    assert sandbox_disp["lifecycle_stage"] == "INQUIRY"
    assert sandbox_disp["status"] == "WAITING_FOR_SELLER_RESPONSE"
    assert sandbox_disp["factual_readiness"] in ["ALLOW", "REVIEW", "BLOCK"]
    assert sandbox_disp["action_readiness"] in ["ALLOW", "REVIEW", "BLOCK"]

    # Check for Label Created scenario (SCENARIO_01)
    scen01 = next((d for d in data if d.get("scenario_id") == "SCENARIO_01_INR_LABEL_CREATED" or d["dispute_id"] == "SCENARIO_01_INR_LABEL_CREATED"), None)
    assert scen01 is not None
    assert scen01["overall_decision"] == "BLOCK"
    assert scen01["is_ready_for_submission"] is False
    assert "LABEL_CREATED" in str(scen01["violated_invariants"])


def test_api_get_dispute_detail(client):
    resp = client.get("/api/disputes/PP-R-NKI-10193390")
    assert resp.status_code == 200
    data = resp.json()

    assert data["dispute_id"] == "PP-R-NKI-10193390"
    assert "dispute" in data
    assert "matched_order" in data
    assert "matched_shipments" in data
    assert "claims" in data
    assert "evaluation" in data
    assert "proposed_payload" in data
    assert data["evaluation"]["overall_decision"] == "ALLOW"
    assert data["evaluation"]["is_ready_for_submission"] is True


def test_api_get_dispute_detail_not_found(client):
    resp = client.get("/api/disputes/NONEXISTENT-DISPUTE-999")
    assert resp.status_code == 404
    assert "not found" in resp.json()["detail"].lower()


def test_api_generate_approval_ticket(client):
    resp = client.post("/api/disputes/PP-R-NKI-10193390/ticket")
    assert resp.status_code == 200
    data = resp.json()

    assert data["dispute_id"] == "PP-R-NKI-10193390"
    assert data["approval_id"].startswith("appr_")
    assert "token" in data
    assert "payload_hash" in data
    assert "summary_for_human" in data
    assert "expires_at" in data


def test_api_authorize_dispute_approve(client):
    # 1. Generate ticket
    client.post("/api/disputes/PP-R-NKI-10193390/ticket")

    # 2. Authorize
    auth_resp = client.post(
        "/api/disputes/PP-R-NKI-10193390/authorize",
        json={
            "merchant_user_id": "merchant_supervisor_admin",
            "decision": "APPROVE",
            "notes": "Verified delivery proof matches order",
        },
    )
    assert auth_resp.status_code == 200
    record = auth_resp.json()
    assert record["decision"] == "APPROVE"
    assert record["merchant_user_id"] == "merchant_supervisor_admin"
    assert record["dispute_id"] == "PP-R-NKI-10193390"


def test_api_authorize_dispute_reject(client):
    client.post("/api/disputes/PP-R-NKI-10193390/ticket")

    rej_resp = client.post(
        "/api/disputes/PP-R-NKI-10193390/authorize",
        json={
            "merchant_user_id": "merchant_supervisor_admin",
            "decision": "REJECT",
            "rejection_reason": "Waiting on carrier claims response",
        },
    )
    assert rej_resp.status_code == 200
    record = rej_resp.json()
    assert record["decision"] == "REJECT"
    assert record["rejection_reason"] == "Waiting on carrier claims response"


def test_api_dispatch_blocked_by_policy(client):
    # Try dispatching SCENARIO_01 (Label Created)
    disp_resp = client.post(
        "/api/disputes/SCENARIO_01_INR_LABEL_CREATED/dispatch",
        json={"idempotency_key": "idemp_test_block"},
    )
    assert disp_resp.status_code == 400
    assert "blocked" in disp_resp.json()["detail"].lower()


def test_api_dispatch_unapproved_rejected(client):
    # Reset dispute state or use unapproved dispute
    disp_resp = client.post(
        "/api/disputes/SCENARIO_02_INR_DELIVERED_MATCHING_ADDRESS/dispatch",
        json={"idempotency_key": "idemp_unapproved"},
    )
    assert disp_resp.status_code == 400
    assert "approval is strictly required" in disp_resp.json()["detail"].lower()


def test_api_dispatch_success_flow(client):
    # 1. Generate ticket
    client.post("/api/disputes/PP-R-NKI-10193390/ticket")

    # 2. Authorize
    client.post(
        "/api/disputes/PP-R-NKI-10193390/authorize",
        json={
            "merchant_user_id": "merchant_supervisor_admin",
            "decision": "APPROVE",
        },
    )

    # 3. Dispatch
    with patch("requests.Session.post") as mock_post:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"status": "SUCCESS"}
        mock_resp.headers = {"Paypal-Debug-Id": "pp_corr_api_test_123"}
        mock_post.return_value = mock_resp

        disp_resp = client.post(
            "/api/disputes/PP-R-NKI-10193390/dispatch",
            json={"idempotency_key": "idemp_api_test_01"},
        )
        assert disp_resp.status_code == 200
        data = disp_resp.json()
        assert data["success"] is True
        assert data["correlation_id"] == "pp_corr_api_test_123"
        assert data["paypal_status_code"] == 200


def test_api_audit_trail_endpoint(client):
    # Hit health or disputes to generate audit events
    client.post("/api/disputes/PP-R-NKI-10193390/ticket")

    resp = client.get("/api/audit-trail")
    assert resp.status_code == 200
    data = resp.json()
    assert "events" in data
    assert "chain_intact" in data
    assert data["chain_intact"] is True
    assert len(data["events"]) > 0


def test_api_eval_scorecard_endpoint(client):
    resp = client.get("/api/eval/scorecard")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_scenarios"] == 20
    assert data["passed_scenarios"] == 20
    assert data["accuracy_rate"] == 100.0
    assert data["refusal_recall"] == 100.0
    assert data["refusal_precision"] == 100.0
    assert data["label_created_refusal_rate"] == 100.0
    assert data["prompt_injection_detection_rate"] == 100.0


def test_api_dispute_lifecycle_endpoint(client):
    """Verify dedicated lifecycle endpoint returns isolated chronological events with global indices."""
    client.post("/api/disputes/PP-R-NKI-10193390/ticket")

    resp = client.get("/api/disputes/PP-R-NKI-10193390/lifecycle")
    assert resp.status_code == 200
    data = resp.json()
    assert data["dispute_id"] == "PP-R-NKI-10193390"
    assert "events" in data
    assert data["total_events"] == len(data["events"])
    assert data["total_events"] > 0

    # Every lifecycle event must strictly belong to the specified dispute
    for ev in data["events"]:
        assert ev["dispute_id"] == "PP-R-NKI-10193390"
        assert "global_chain_index" in ev
        assert ev["global_chain_index"] >= 1
        assert "event_id" in ev
        assert "timestamp" in ev
        assert "result" in ev


def test_api_audit_trail_filtered_by_dispute(client):
    """Verify /api/audit-trail query parameter correctly filters by dispute_id without cross-dispute contamination."""
    resp = client.get("/api/audit-trail?dispute_id=PP-R-NKI-10193390")
    assert resp.status_code == 200
    data = resp.json()
    for ev in data["events"]:
        assert ev["dispute_id"] == "PP-R-NKI-10193390"


def test_api_lifecycle_simulated_dispatch_label(client):
    """Verify simulated dispatch events are clearly labeled and not misrepresented as live PayPal submissions."""
    client.post("/api/disputes/PP-R-NKI-10193390/ticket")
    client.post(
        "/api/disputes/PP-R-NKI-10193390/authorize",
        json={"merchant_user_id": "merchant_supervisor_admin", "decision": "APPROVE"},
    )

    with patch("requests.Session.post") as mock_post:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"status": "SUCCESS"}
        mock_resp.headers = {"Paypal-Debug-Id": "pp_corr_simulated_test"}
        mock_post.return_value = mock_resp

        client.post(
            "/api/disputes/PP-R-NKI-10193390/dispatch",
            json={"idempotency_key": "idemp_sim_test_01"},
        )

    resp = client.get("/api/disputes/PP-R-NKI-10193390/lifecycle")
    assert resp.status_code == 200
    data = resp.json()

    succ_event = next((e for e in data["events"] if e["event_type"] == "DISPATCH_SUCCEEDED"), None)
    assert succ_event is not None
    assert succ_event["is_simulated"] is True
    assert "Simulated" in succ_event["result"]

