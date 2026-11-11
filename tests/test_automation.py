"""Comprehensive Tests for Docket Automated Synchronisation & Continuous Audit Integrity.

Covers:
1. Startup SQLite hydration and audit verification.
2. Incremental verification on audit event logging (parent hash and canonical SHA-256).
3. Periodic full-chain verification directly against canonical SQLite audit_events.
4. Detection of tampered database records and integrity status exposure.
5. Sensitive-operation integrity gate blocking /authorize and /dispatch (409 Conflict) on tampered ledger.
6. Multi-worker SQLite coordination locks preventing overlapping reconciliation jobs.
7. Scheduled reconciliation failure handling, exponential backoff, and jitter.
8. Unchanged dispute state detection (no redundant audit log bloat).
9. Webhook-driven synchronization with receipt idempotency.
10. Status and telemetry endpoints (/api/sync/status, /api/audit-trail/status, /api/health).
11. Administrative manual trigger endpoints (/api/admin/sync/trigger, /api/admin/audit/verify).
"""

from datetime import datetime, timedelta, timezone
from decimal import Decimal
import json
from pathlib import Path
import pytest
from fastapi.testclient import TestClient
from unittest.mock import MagicMock, patch

from docket.api.app import create_app
from docket.database.repository import DocketRepository
from docket.audit.logger import AuditLogger, AuditVerificationError
from docket.policy.engine import PolicyEngine
from docket.sync.automation import AutomationService, SyncStatus, AuditStatus
from docket.models.audit import AuditEventType
from docket.models.dispute import (
    DisputeCase,
    DisputeLifecycleStage,
    DisputeReason,
    DisputeStatus,
    Money,
)


@pytest.fixture
def auto_env(tmp_path):
    """Fixture providing isolated temporary database, repository, audit logger, and automation service."""
    db_file = tmp_path / "test_automation.db"
    audit_file = tmp_path / "test_audit.jsonl"
    repository = DocketRepository(db_path=str(db_file))
    audit_logger = AuditLogger(storage_path=str(audit_file), repository=repository)
    policy_engine = PolicyEngine()
    cases_store = {}

    service = AutomationService(
        repository=repository,
        audit_logger=audit_logger,
        policy_engine=policy_engine,
        cases_store=cases_store,
        auto_start=False,
        sync_interval_seconds=60,
        audit_interval_seconds=60,
    )
    return {
        "db_file": db_file,
        "audit_file": audit_file,
        "repository": repository,
        "audit_logger": audit_logger,
        "policy_engine": policy_engine,
        "cases_store": cases_store,
        "service": service,
    }


@pytest.fixture
def test_app_and_client(tmp_path):
    """FastAPI TestClient fixture with isolated SQLite database and disabled background scheduler."""
    db_file = tmp_path / "test_app_auto.db"
    audit_file = tmp_path / "test_app_auto.jsonl"
    with patch.dict("os.environ", {"DOCKET_DISABLE_BG_SCHEDULER": "true"}):
        app = create_app(
            audit_log_path=str(audit_file),
            secret_key="test-automation-secret-key-32chars!",
            db_path=str(db_file),
        )
    client = TestClient(app)
    return app, client, db_file


# ============================================================================
# 1. Startup Synchronization & Audit Verification Tests
# ============================================================================

def test_startup_audit_verification(auto_env):
    """Verify that startup audit verification performs full SHA-256 chain validation."""
    service = auto_env["service"]
    res = service.perform_startup_audit_verification()
    assert res["is_valid"] is True
    assert service.audit_status == AuditStatus.VERIFIED
    assert service.last_verified_at is not None
    assert service.failed_audit_events == 0


def test_startup_sync_sqlite_hydration(auto_env):
    """Verify startup sync hydrates state from SQLite when external API credentials are unset."""
    service = auto_env["service"]
    with patch.dict("os.environ", {"PAYPAL_CLIENT_ID": "", "PAYPAL_CLIENT_SECRET": ""}):
        res = service.perform_startup_sync()
        assert res["success"] is True
        assert service.sync_status == SyncStatus.UP_TO_DATE
        assert service.last_successful_sync is not None
        assert service.sync_error_summary is None


# ============================================================================
# 2. Incremental & Periodic Audit Chain Verification Tests
# ============================================================================

def test_incremental_audit_verification_success(auto_env):
    """Verify incremental verification succeeds when appending valid chained events."""
    audit_logger = auto_env["audit_logger"]
    evt1 = audit_logger.log_event(
        event_type=AuditEventType.DISPUTE_INGESTED,
        dispute_id="PP-R-TEST-001",
        actor="SYSTEM",
        payload={"message": "First test event"},
    )
    assert evt1.parent_hash is not None
    assert evt1.event_hash is not None

    evt2 = audit_logger.log_event(
        event_type=AuditEventType.POLICY_EVALUATED,
        dispute_id="PP-R-TEST-001",
        actor="POLICY_ENGINE",
        payload={"decision": "ALLOW"},
    )
    assert evt2.parent_hash == evt1.event_hash


def test_incremental_verification_rejects_parent_hash_mismatch(auto_env):
    """Verify that an event with an invalid parent hash is rejected immediately before commit."""
    audit_logger = auto_env["audit_logger"]
    audit_logger.log_event(
        event_type=AuditEventType.DISPUTE_INGESTED,
        dispute_id="PP-R-TEST-002",
        actor="SYSTEM",
        payload={"msg": "Valid first"},
    )
    # Attempting to log with a corrupted internal state should trigger AuditVerificationError
    with patch.object(audit_logger, "_calculate_event_hash", side_effect=["0" * 64, "1" * 64]):
        with pytest.raises(AuditVerificationError, match="Incremental verification failed"):
            audit_logger.log_event(
                event_type=AuditEventType.POLICY_EVALUATED,
                dispute_id="PP-R-TEST-002",
                actor="POLICY_ENGINE",
                payload={"msg": "Should fail"},
            )


def test_periodic_full_chain_verification(auto_env):
    """Verify periodic audit verification checks all events directly in SQLite."""
    service = auto_env["service"]
    audit_logger = auto_env["audit_logger"]

    audit_logger.log_event(AuditEventType.DISPUTE_INGESTED, "PP-R-01", "SYSTEM", {"a": 1})
    audit_logger.log_event(AuditEventType.POLICY_EVALUATED, "PP-R-01", "POLICY_ENGINE", {"b": 2})

    status_data = service.periodic_audit_verification()
    assert status_data["is_valid"] is True
    assert status_data["verified_count"] >= 2
    assert service.audit_status == AuditStatus.VERIFIED


def test_tampered_audit_chain_detection(auto_env):
    """Verify that tampering with a persisted SQLite audit row triggers verification failure."""
    service = auto_env["service"]
    audit_logger = auto_env["audit_logger"]
    repository = auto_env["repository"]

    audit_logger.log_event(AuditEventType.DISPUTE_INGESTED, "PP-R-TAMPER", "SYSTEM", {"orig": "data"})
    evt2 = audit_logger.log_event(AuditEventType.POLICY_EVALUATED, "PP-R-TAMPER", "POLICY_ENGINE", {"orig": "check"})

    # Directly tamper with SQLite audit_events table
    with repository.conn.transaction() as cur:
        cur.execute(
            "UPDATE audit_events SET payload = ? WHERE event_id = ?",
            (json.dumps({"malicious": "injected"}), evt2.event_id),
        )

    # Run periodic verification
    result = service.periodic_audit_verification()
    assert result["is_valid"] is False
    assert service.audit_status == AuditStatus.VERIFICATION_FAILED
    assert service.failed_audit_events >= 1
    assert "recomputed hash" in result["error_message"].lower() or "mismatch" in result["error_message"].lower()


# ============================================================================
# 3. Sensitive-Operation Integrity Gate Tests
# ============================================================================

def test_sensitive_operation_gate_blocking_on_tamper(test_app_and_client):
    """Verify /authorize and /dispatch are rejected with 409 if audit ledger is tampered."""
    app, client, db_file = test_app_and_client

    # 1. Sign in as demo operator
    login_resp = client.post("/api/auth/demo-session", json={"profile_id": "merchant_ops_primary"})
    assert login_resp.status_code == 200
    token = login_resp.json()["token"]
    headers = {"Authorization": f"Bearer {token}"}

    # 2. Ensure an audit event exists in SQLite, then tamper with it
    repo = DocketRepository(db_path=str(db_file))
    logger = AuditLogger(repository=repo)
    test_evt = logger.log_event(
        event_type=AuditEventType.DISPUTE_INGESTED,
        dispute_id="PP-R-NKI-10193390",
        actor="SYSTEM",
        payload={"baseline": "real"},
    )

    with repo.conn.transaction() as cur:
        cur.execute(
            "UPDATE audit_events SET payload = ? WHERE event_id = ?",
            (json.dumps({"tampered": "malicious"}), test_evt.event_id),
        )

    # 3. Attempting to authorize should be blocked by the sensitive operation gate (409)
    auth_resp = client.post(
        "/api/disputes/PP-R-NKI-10193390/authorize",
        json={"ticket_id": "TCK-FAKE-001", "decision": "APPROVE"},
        headers=headers,
    )
    assert auth_resp.status_code == 409
    assert "integrity failure detected" in auth_resp.json()["detail"].lower()

    # 4. Attempting to dispatch should also be blocked by the sensitive operation gate (409)
    dispatch_resp = client.post(
        "/api/disputes/PP-R-NKI-10193390/dispatch",
        json={"ticket_id": "TCK-FAKE-001", "approval_token": "FAKE_TOKEN"},
        headers=headers,
    )
    assert dispatch_resp.status_code == 409
    assert "integrity failure detected" in dispatch_resp.json()["detail"].lower()


# ============================================================================
# 4. Coordination Locks & Overlapping Job Prevention Tests
# ============================================================================

def test_coordination_lock_prevents_duplicate_reconciliation(auto_env):
    """Verify SQLite coordination locks prevent multiple workers from running sync simultaneously."""
    repository = auto_env["repository"]
    worker_1 = "worker_proc_1001"
    worker_2 = "worker_proc_1002"

    # Worker 1 acquires coordination lock
    acquired = repository.acquire_coordination_lock("paypal_reconciliation", worker_1, ttl_seconds=60)
    assert acquired is True

    # Worker 2 attempts to acquire same lock and is blocked
    acquired_2 = repository.acquire_coordination_lock("paypal_reconciliation", worker_2, ttl_seconds=60)
    assert acquired_2 is False

    # Worker 1 releases lock
    released = repository.release_coordination_lock("paypal_reconciliation", worker_1)
    assert released is True

    # Now Worker 2 can acquire lock
    acquired_3 = repository.acquire_coordination_lock("paypal_reconciliation", worker_2, ttl_seconds=60)
    assert acquired_3 is True


def test_service_skips_when_db_locked(auto_env):
    """Verify reconcile_paypal_disputes skips execution when another worker holds coordination lock."""
    service = auto_env["service"]
    repository = auto_env["repository"]

    # Another worker holds the lock
    repository.acquire_coordination_lock("paypal_reconciliation", "competing_worker", ttl_seconds=120)

    result = service.reconcile_paypal_disputes(force=False)
    assert result["success"] is True
    assert result["status"] == "SKIPPED_COORDINATION_LOCK"


# ============================================================================
# 5. Scheduled Sync Backoff & Unchanged State Detection Tests
# ============================================================================

def test_sync_failure_exponential_backoff(auto_env):
    """Verify exponential backoff calculation and DELAYED/FAILED status transitions on error."""
    service = auto_env["service"]

    # Mock PayPal client to raise error
    with patch("docket.paypal.client.PayPalSandboxClient") as mock_client:
        mock_instance = MagicMock()
        mock_instance.get_dispute.side_effect = ConnectionError("PayPal sandbox gateway timeout")
        mock_client.return_value = mock_instance

        with patch.dict("os.environ", {"PAYPAL_CLIENT_ID": "mock_id", "PAYPAL_CLIENT_SECRET": "mock_sec"}):
            # Failure 1
            res1 = service.reconcile_paypal_disputes(force=True)
            assert res1["success"] is False
            assert service.consecutive_sync_failures == 1
            assert service.sync_status == SyncStatus.DELAYED
            assert service.next_sync_due > datetime.now(timezone.utc)

            # Failure 2
            res2 = service.reconcile_paypal_disputes(force=True)
            assert res2["success"] is False
            assert service.consecutive_sync_failures == 2
            assert service.sync_status == SyncStatus.DELAYED

            # Failure 3 -> Status transitions to FAILED
            res3 = service.reconcile_paypal_disputes(force=True)
            assert res3["success"] is False
            assert service.consecutive_sync_failures == 3
            assert service.sync_status == SyncStatus.FAILED


def test_unchanged_state_avoids_redundant_audit_events(auto_env):
    """Verify unchanged PayPal dispute payloads do not append redundant audit log entries."""
    service = auto_env["service"]
    audit_logger = auto_env["audit_logger"]
    cases_store = auto_env["cases_store"]

    # Initial event count
    initial_events_count = len(audit_logger.get_events())

    mock_dispute_dict = {
        "dispute_id": "PP-R-NKI-10193390",
        "create_time": "2026-10-15T12:00:00Z",
        "status": "WAITING_FOR_SELLER_RESPONSE",
        "dispute_life_cycle_stage": "INQUIRY",
        "dispute_amount": {"currency_code": "USD", "value": "25.00"},
        "reason": "MERCHANDISE_OR_SERVICE_NOT_RECEIVED",
    }

    # Setup matching case in cases_store
    mock_case = MagicMock()
    mock_case.dispute.status.value = "WAITING_FOR_SELLER_RESPONSE"
    mock_case.dispute.dispute_amount.value = Decimal("25.00")
    mock_case.dispute.lifecycle_stage.value = "INQUIRY"
    cases_store["PP-R-NKI-10193390"] = mock_case

    with patch("docket.paypal.client.PayPalSandboxClient") as mock_client:
        mock_instance = MagicMock()
        mock_instance.get_dispute.return_value = mock_dispute_dict
        mock_client.return_value = mock_instance

        with patch.dict("os.environ", {"PAYPAL_CLIENT_ID": "mock_id", "PAYPAL_CLIENT_SECRET": "mock_sec"}):
            res = service.reconcile_paypal_disputes(force=True)
            assert res["success"] is True
            assert res["state_changed"] is False

    # Event count must remain unchanged (zero ledger bloat)
    post_events_count = len(audit_logger.get_events())
    assert post_events_count == initial_events_count


# ============================================================================
# 6. Webhook-Driven Updates & Idempotency Tests
# ============================================================================

def test_webhook_synchronization_and_idempotency(auto_env):
    """Verify webhook dispute ingestion updates state and rejects duplicate webhook delivery."""
    service = auto_env["service"]

    event_payload = {
        "id": "WH-AUTO-10001",
        "event_type": "CUSTOMER.DISPUTE.UPDATED",
        "create_time": "2026-11-10T14:00:00Z",
        "resource": {
            "dispute_id": "PP-R-WH-001",
            "create_time": "2026-11-01T10:00:00Z",
            "status": "UNDER_REVIEW",
            "dispute_life_cycle_stage": "CHARGEBACK",
            "dispute_amount": {"currency_code": "USD", "value": "120.00"},
            "reason": "UNAUTHORISED",
        },
    }

    resource = event_payload["resource"]
    # First delivery: processes successfully
    success1, is_duplicate1, msg1 = service.handle_webhook_dispute_update(
        event_type=event_payload["event_type"],
        dispute_id=resource["dispute_id"],
        payload=resource,
        idempotency_key=event_payload["id"],
    )
    assert success1 is True
    assert is_duplicate1 is False

    # Second delivery with identical webhook event ID: idempotent rejection
    success2, is_duplicate2, msg2 = service.handle_webhook_dispute_update(
        event_type=event_payload["event_type"],
        dispute_id=resource["dispute_id"],
        payload=resource,
        idempotency_key=event_payload["id"],
    )
    assert success2 is True
    assert is_duplicate2 is True


# ============================================================================
# 7. Telemetry & Administrative API Endpoints Tests
# ============================================================================

def test_sync_status_endpoint(test_app_and_client):
    """Verify GET /api/sync/status returns accurate synchronisation telemetry."""
    _, client, _ = test_app_and_client
    resp = client.get("/api/sync/status")
    assert resp.status_code == 200
    data = resp.json()

    assert data["status"] in ("CONNECTED", "SYNCING", "UP_TO_DATE", "DELAYED", "FAILED")
    assert "last_successful_sync" in data
    assert "last_attempted_sync" in data
    assert "reconciled_records" in data
    assert data["environment"] == "PAYPAL_SANDBOX_REST_V1"
    assert data["interval_seconds"] > 0


def test_audit_trail_status_endpoint(test_app_and_client):
    """Verify GET /api/audit-trail/status returns continuous verification integrity state."""
    _, client, _ = test_app_and_client
    resp = client.get("/api/audit-trail/status")
    assert resp.status_code == 200
    data = resp.json()

    assert data["status"] in ("VERIFIED", "VERIFYING", "INTEGRITY_WARNING", "VERIFICATION_FAILED")
    assert "total_events" in data
    assert "verified_events" in data
    assert "failed_events" in data
    assert "tail_truncation_notice" in data
    assert "tail truncation" in data["tail_truncation_notice"].lower()


def test_admin_manual_maintenance_endpoints(test_app_and_client):
    """Verify secured admin endpoints /api/admin/sync/trigger and /api/admin/audit/verify."""
    _, client, _ = test_app_and_client

    # 1. Unauthenticated request rejected with 401
    unauth_resp = client.post("/api/admin/sync/trigger")
    assert unauth_resp.status_code == 401

    # 2. Authenticate as supervisor
    login_resp = client.post("/api/auth/demo-session", json={"profile_id": "merchant_supervisor_admin"})
    assert login_resp.status_code == 200
    token = login_resp.json()["token"]
    headers = {"Authorization": f"Bearer {token}"}

    # 3. Authenticated manual sync trigger
    sync_resp = client.post("/api/admin/sync/trigger", headers=headers)
    assert sync_resp.status_code == 200
    sync_data = sync_resp.json()
    assert sync_data["success"] is True
    assert "status" in sync_data

    # 4. Authenticated manual audit verification trigger
    audit_resp = client.post("/api/admin/audit/verify", headers=headers)
    assert audit_resp.status_code == 200
    audit_data = audit_resp.json()
    assert audit_data["is_valid"] is True
    assert "total_events" in audit_data
