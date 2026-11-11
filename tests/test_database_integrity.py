"""Comprehensive SQLite Persistence Hardening & Database Integrity Tests.

Verifies:
1. Dual persistence consistency (SQLite canonical ledger, derived recoverable JSONL export, failure-injection).
2. Approval & audit retention (ON DELETE RESTRICT blocks cascade deletion; soft-archival preserves approval records).
3. Approval integrity & single-use anti-replay (bound dispute_id, action, payload hash, evaluation ID, merchant ID, nonce; rejected on tampering, wrong dispute, wrong action, replay, and survives reboot before single-use dispatch).
4. Deterministic canonical hash-chain serialization & interior tampering detection.
5. Database count reconciliation (unique cases vs dual-alias keys; categorized breakdown).
6. Operational safety: Online SQLite WAL backup and restoration.
"""

from datetime import datetime, timedelta, timezone
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import sqlite3
from unittest.mock import MagicMock, patch
import pytest
from fastapi.testclient import TestClient

from docket.database.connection import DatabaseConnection
from docket.database.repository import DocketRepository
from docket.models.dispute import (
    DisputeCase,
    DisputeLifecycleStage,
    DisputeReason,
    DisputeStatus,
    Money,
)
from docket.models.evidence import (
    Address,
    ClaimEpistemicMetadata,
    ClaimStatus,
    ClaimType,
    CustomerMessageRecord,
    EvidenceBasis,
    ExtractedClaim,
    OrderRecord,
    RefundRecord,
    ShipmentRecord,
    SourceCitation,
    SourceType,
    TrackingStatus,
)
from docket.models.policy import (
    DecisionType,
    OverallPolicyEvaluation,
    PolicyCheckResult,
)
from docket.models.dispatch import (
    ApprovalDecision,
    ApprovalRequest,
    DispatchResult,
    MerchantApprovalRecord,
)
from docket.models.audit import AuditEvent, AuditEventType
from docket.models.reconciliation import ReconciledDisputeBundle, ReconciliationStatus
from docket.dispatch.approval import (
    ActionMismatchError,
    ApprovalService,
    DisputeMismatchError,
    MerchantMismatchError,
    PayloadTamperedError,
    TokenAlreadyUsedError,
)
from docket.dispatch.dispatcher import (
    EvidenceDispatcher,
    EvidencePayloadFormatter,
    MerchantApprovalRequiredError,
)
from docket.audit.logger import AuditError, AuditLogger
from docket.policy.engine import PolicyEngine
from docket.api.app import create_app


# ============================================================================
# 1. Dual Persistence Consistency & Recoverable JSONL Export
# ============================================================================

def test_canonical_sqlite_and_recoverable_jsonl_export(tmp_path):
    """Verify SQLite is the canonical ledger, JSONL is derived/recoverable, and failed export doesn't corrupt chain."""
    db_file = tmp_path / "canonical_audit.db"
    jsonl_file = tmp_path / "derived_export.jsonl"

    conn = DatabaseConnection(db_path=db_file)
    repo = DocketRepository(connection=conn)
    logger = AuditLogger(storage_path=jsonl_file, repository=repo)

    # 1. Log two normal events
    ev1 = logger.log_event(AuditEventType.DISPUTE_INGESTED, "DISP-CANON-01", "SYSTEM", {"amount": "100.00"})
    ev2 = logger.log_event(AuditEventType.EVIDENCE_RECONCILED, "DISP-CANON-01", "SYSTEM", {"matched": True})

    # Both SQLite and JSONL have 2 events
    assert len(repo.get_audit_events()) == 2
    assert jsonl_file.exists()

    # 2. Failure-injection: Simulate a filesystem failure on JSONL export
    with patch("builtins.open", side_effect=[IOError("Disk full / read-only filesystem"), open]):
        # The canonical SQLite write MUST succeed even if JSONL write raises IOError
        ev3 = logger.log_event(AuditEventType.APPROVAL_GRANTED, "DISP-CANON-01", "merchant_admin", {"token": "ok"})

    # Verify SQLite committed ev3 safely
    db_events = repo.get_audit_events()
    assert len(db_events) == 3
    assert db_events[-1].event_id == ev3.event_id

    # Canonical hash chain in SQLite is 100% valid
    chain_verif = repo.verify_db_audit_chain()
    assert chain_verif["is_valid"] is True
    assert chain_verif["verified_count"] == 3

    # 3. Simulate accidental deletion of JSONL file
    if jsonl_file.exists():
        jsonl_file.unlink()
    assert not jsonl_file.exists()

    # 4. Recover JSONL export from canonical SQLite
    recovered_count = logger.reconcile_jsonl_export()
    assert recovered_count == 3
    assert jsonl_file.exists()

    # Verify JSONL chain verification passes with identical hashes
    jsonl_details = logger.verify_chain_detailed()
    assert jsonl_details["is_valid"] is True
    assert jsonl_details["verified_count"] == 3

    conn.close()


# ============================================================================
# 2. Approval & Audit Retention (Foreign Key RESTRICT & Soft Archival)
# ============================================================================

def test_approval_retention_blocks_cascade_and_permits_archival(tmp_path):
    """Verify that dispute deletion cascade is blocked when merchant approvals exist, and soft-archival preserves audit."""
    db_file = tmp_path / "retention_test.db"
    conn = DatabaseConnection(db_path=db_file)
    repo = DocketRepository(connection=conn)

    dispute = DisputeCase(
        dispute_id="PP-R-RETAIN-01",
        reason=DisputeReason.MERCHANDISE_OR_SERVICE_NOT_RECEIVED,
        lifecycle_stage=DisputeLifecycleStage.CHARGEBACK,
        status=DisputeStatus.WAITING_FOR_SELLER_RESPONSE,
        dispute_amount=Money(value=Decimal("200.00"), currency_code="USD"),
    )
    repo.save_dispute(dispute)

    approval = MerchantApprovalRecord(
        approval_id="appr_retain_01",
        dispute_id=dispute.dispute_id,
        merchant_user_id="audit_compliance_officer",
        decision=ApprovalDecision.APPROVE,
        action="provide_evidence",
        payload_hash="sha256_mock_hash",
        nonce="nonce_retain_01",
        approved_at=datetime.now(timezone.utc),
        approval_token="tok_retain_valid",
    )
    repo.save_approval_record(approval)

    # 1. Attempt hard-delete: MUST be blocked by ON DELETE RESTRICT
    with pytest.raises(sqlite3.IntegrityError) as excinfo:
        with repo.conn.transaction() as cur:
            cur.execute("DELETE FROM disputes WHERE dispute_id = ?", (dispute.dispute_id,))
    assert "FOREIGN KEY constraint failed" in str(excinfo.value)

    # Verify approval record is still completely intact
    appr_check = repo.get_approval_record(dispute.dispute_id)
    assert appr_check is not None
    assert appr_check.approval_id == "appr_retain_01"

    # 2. Soft-archival: Archive dispute for compliance retention
    archived = repo.archive_dispute(dispute.dispute_id, reason="COMPLIANCE_ARCHIVAL_RETENTION")
    assert archived is True
    assert repo.is_dispute_archived(dispute.dispute_id) is True

    # 3. Verify approval record remains available after dispute archival
    appr_after_archive = repo.get_approval_record(dispute.dispute_id)
    assert appr_after_archive is not None
    assert appr_after_archive.approval_id == "appr_retain_01"
    assert appr_after_archive.merchant_user_id == "audit_compliance_officer"

    # 4. Verify list_disputes filters archived disputes by default when requested
    active_disputes = repo.list_disputes(include_archived=False)
    assert not any(d.dispute_id == dispute.dispute_id for d in active_disputes)

    all_disputes = repo.list_disputes(include_archived=True)
    assert any(d.dispute_id == dispute.dispute_id for d in all_disputes)

    conn.close()


# ============================================================================
# 3. Approval Integrity & Single-Use Anti-Replay Verification
# ============================================================================

def test_approval_integrity_and_anti_replay_matrix(tmp_path):
    """Verify approval binding to dispute_id, action, payload hash, evaluation_id, merchant_id, single-use nonce."""
    db_file = tmp_path / "approval_integrity.db"
    conn = DatabaseConnection(db_path=db_file)
    repo = DocketRepository(connection=conn)
    appr_service = ApprovalService(repository=repo)

    dispute = DisputeCase(
        dispute_id="PP-R-INTEG-01",
        reason=DisputeReason.MERCHANDISE_OR_SERVICE_NOT_RECEIVED,
        lifecycle_stage=DisputeLifecycleStage.CHARGEBACK,
        status=DisputeStatus.WAITING_FOR_SELLER_RESPONSE,
        dispute_amount=Money(value=Decimal("50.00"), currency_code="USD"),
    )
    repo.save_dispute(dispute)

    evaluation = OverallPolicyEvaluation(
        dispute_id=dispute.dispute_id,
        overall_decision=DecisionType.ALLOW,
        summary="Policy check passed.",
    )
    target_payload = {"evidences": [{"evidence_type": "PROOF_OF_FULFILLMENT", "notes": "Shipped via USPS"}]}

    # 1. Create approval ticket
    ticket = appr_service.create_approval_request(
        dispute=dispute,
        policy_evaluation=evaluation,
        proposed_payload=target_payload,
        merchant_user_id="lead_merchant",
        action="provide_evidence",
    )
    assert ticket.evaluation_id == f"eval_{dispute.dispute_id}"
    assert ticket.payload_hash == appr_service._hash_payload(target_payload)

    # 2. Record merchant approval
    approval_rec = appr_service.record_approval(
        request=ticket,
        merchant_user_id="lead_merchant",
        decision=ApprovalDecision.APPROVE,
        client_ip="127.0.0.1",
    )
    assert approval_rec.action == "provide_evidence"
    assert approval_rec.payload_hash == ticket.payload_hash
    assert approval_rec.nonce == ticket.nonce
    assert approval_rec.is_consumed is False
    repo.save_approval_record(approval_rec)

    # 3. Test: Modified payload after approval must be rejected
    tampered_payload = {"evidences": [{"evidence_type": "PROOF_OF_FULFILLMENT", "notes": "TAMPERED PAYLOAD"}]}
    with pytest.raises(PayloadTamperedError):
        appr_service.verify_token(
            token=ticket.token,
            dispute_id=dispute.dispute_id,
            payload=tampered_payload,
            merchant_user_id="lead_merchant",
            action="provide_evidence",
            consume_nonce=False,
        )

    # 4. Test: Wrong dispute ID must be rejected
    with pytest.raises(DisputeMismatchError):
        appr_service.verify_token(
            token=ticket.token,
            dispute_id="PP-R-WRONG-DISPUTE-99",
            payload=target_payload,
            merchant_user_id="lead_merchant",
            action="provide_evidence",
            consume_nonce=False,
        )

    # 5. Test: Wrong action must be rejected
    with pytest.raises(ActionMismatchError):
        appr_service.verify_token(
            token=ticket.token,
            dispute_id=dispute.dispute_id,
            payload=target_payload,
            merchant_user_id="lead_merchant",
            action="accept_claim",
            consume_nonce=False,
        )

    # 6. Test: Wrong merchant identity must be rejected
    with pytest.raises(MerchantMismatchError):
        appr_service.verify_token(
            token=ticket.token,
            dispute_id=dispute.dispute_id,
            payload=target_payload,
            merchant_user_id="unauthorized_attacker",
            action="provide_evidence",
            consume_nonce=False,
        )

    # 7. Test: Valid verification & atomic single-use consumption
    verified = appr_service.verify_token(
        token=ticket.token,
        dispute_id=dispute.dispute_id,
        payload=target_payload,
        merchant_user_id="lead_merchant",
        action="provide_evidence",
        consume_nonce=True,
        dispatch_id="disp_test_01",
    )
    assert verified is True
    assert repo.is_nonce_consumed(ticket.nonce) is True

    # 8. Test: Approval Replay attack blocked
    with pytest.raises(TokenAlreadyUsedError):
        appr_service.verify_token(
            token=ticket.token,
            dispute_id=dispute.dispute_id,
            payload=target_payload,
            merchant_user_id="lead_merchant",
            action="provide_evidence",
            consume_nonce=True,
        )

    conn.close()


def test_approval_survives_backend_restart_before_single_use_dispatch(tmp_path):
    """Verify approval generated in Session 1 survives process reboot, can be verified once, and replayed is blocked."""
    db_file = tmp_path / "approval_restart.db"

    # --- SESSION 1: Create approval and save to database ---
    conn1 = DatabaseConnection(db_path=db_file)
    repo1 = DocketRepository(connection=conn1)
    svc1 = ApprovalService(repository=repo1)

    dispute = DisputeCase(
        dispute_id="PP-R-REBOOT-01",
        reason=DisputeReason.MERCHANDISE_OR_SERVICE_NOT_RECEIVED,
        lifecycle_stage=DisputeLifecycleStage.CHARGEBACK,
        status=DisputeStatus.WAITING_FOR_SELLER_RESPONSE,
        dispute_amount=Money(value=Decimal("75.00"), currency_code="USD"),
    )
    repo1.save_dispute(dispute)
    eval_res = OverallPolicyEvaluation(dispute_id=dispute.dispute_id, overall_decision=DecisionType.ALLOW, summary="OK")
    payload = {"evidences": [{"notes": "Authentic fulfillment proof"}]}

    req = svc1.create_approval_request(dispute, eval_res, payload, merchant_user_id="supervisor_alice")
    appr_rec = svc1.record_approval(req, merchant_user_id="supervisor_alice", decision=ApprovalDecision.APPROVE)
    repo1.save_approval_record(appr_rec)

    # Simulate abrupt process termination
    conn1.close()

    # --- SESSION 2: Brand new server instance boots ---
    conn2 = DatabaseConnection(db_path=db_file)
    repo2 = DocketRepository(connection=conn2)
    svc2 = ApprovalService(repository=repo2)

    # 1. Verify approval record is still unconsumed after reboot
    loaded_appr = repo2.get_approval_record(dispute.dispute_id)
    assert loaded_appr is not None
    assert loaded_appr.is_consumed is False
    assert loaded_appr.nonce == req.nonce

    # 2. First dispatch consumes it successfully
    v1 = svc2.verify_token(
        token=loaded_appr.approval_token,
        dispute_id=dispute.dispute_id,
        payload=payload,
        merchant_user_id="supervisor_alice",
        action="provide_evidence",
        consume_nonce=True,
        dispatch_id="disp_live_01",
    )
    assert v1 is True
    assert repo2.is_nonce_consumed(req.nonce) is True

    # 3. Immediate replay in Session 2 is blocked
    with pytest.raises(TokenAlreadyUsedError):
        svc2.verify_token(
            token=loaded_appr.approval_token,
            dispute_id=dispute.dispute_id,
            payload=payload,
            merchant_user_id="supervisor_alice",
            action="provide_evidence",
            consume_nonce=True,
        )

    # Simulate another reboot (Session 3)
    conn2.close()

    # --- SESSION 3: Replay must STILL be blocked after another reboot ---
    conn3 = DatabaseConnection(db_path=db_file)
    repo3 = DocketRepository(connection=conn3)
    svc3 = ApprovalService(repository=repo3)

    assert repo3.is_nonce_consumed(req.nonce) is True
    with pytest.raises(TokenAlreadyUsedError):
        svc3.verify_token(
            token=loaded_appr.approval_token,
            dispute_id=dispute.dispute_id,
            payload=payload,
            merchant_user_id="supervisor_alice",
            action="provide_evidence",
            consume_nonce=True,
        )

    conn3.close()


# ============================================================================
# 4. Hash-Chain Implementation & Canonical Serialization Verification
# ============================================================================

def test_canonical_hash_chain_determinism_and_tamper_detection(tmp_path):
    """Verify UTF-8 encoding, stable timestamp format, deterministic canonical JSON, and interior tamper detection."""
    db_file = tmp_path / "hash_determinism.db"
    conn = DatabaseConnection(db_path=db_file)
    repo = DocketRepository(connection=conn)
    logger = AuditLogger(storage_path=tmp_path / "chain_audit.jsonl", repository=repo)

    # Canonical event logging
    payload1 = {"currency": "USD", "amount": "49.99", "reason": "INR"}
    ev1 = logger.log_event(AuditEventType.DISPUTE_INGESTED, "DISP-CHAIN-01", "PAYPAL_WEBHOOK", payload1)

    # Check exact fingerprint formula
    now_iso = ev1.timestamp.isoformat()
    canonical_json = json.dumps(payload1, sort_keys=True, separators=(",", ":"))
    expected_fingerprint = f"GENESIS:{ev1.event_id}:{ev1.event_type.value}:{now_iso}:DISP-CHAIN-01:PAYPAL_WEBHOOK:{canonical_json}"
    expected_hash = hashlib.sha256(expected_fingerprint.encode("utf-8")).hexdigest()
    assert ev1.event_hash == expected_hash

    # Event 2 chaining
    payload2 = {"status": "WAITING_FOR_SELLER_RESPONSE"}
    ev2 = logger.log_event(AuditEventType.DISPUTE_INGESTED, "DISP-CHAIN-01", "SYSTEM", payload2)
    assert ev2.parent_hash == ev1.event_hash

    # Event 3 chaining
    payload3 = {"decision": "APPROVE"}
    ev3 = logger.log_event(AuditEventType.APPROVAL_GRANTED, "DISP-CHAIN-01", "merchant_admin", payload3)
    assert ev3.parent_hash == ev2.event_hash

    # Valid chain check
    assert repo.verify_db_audit_chain()["is_valid"] is True

    # Interior deletion test: Delete event 2
    with repo.conn.transaction() as cur:
        cur.execute("DELETE FROM audit_events WHERE event_id = ?", (ev2.event_id,))

    # Verification must detect broken parent link between ev1 and ev3
    broken_verif = repo.verify_db_audit_chain()
    assert broken_verif["is_valid"] is False
    assert broken_verif["failed_event_id"] == ev3.event_id
    assert "Broken parent link" in broken_verif["error_message"]

    conn.close()


# ============================================================================
# 5. Database Count Reconciliation & Case Categorization
# ============================================================================

def test_database_count_reconciliation_and_provenance(tmp_path):
    """Verify that total_cases_loaded, alias index keys, and database counts are cleanly reconciled."""
    audit_file = tmp_path / "counts_audit.jsonl"
    db_file = tmp_path / "counts.db"

    app = create_app(audit_log_path=str(audit_file), db_path=str(db_file))
    client = TestClient(app)

    # 1. Check initial baseline counts
    resp = client.get("/api/health")
    assert resp.status_code == 200
    data = resp.json()

    # Exactly 20 unique disputes: 1 real sandbox + 19 synthetic benchmark scenarios
    assert data["total_cases_loaded"] == 20
    assert data["case_counts"]["total_unique_cases"] == 20
    assert data["case_counts"]["alias_lookup_keys"] == 40  # 20 disputes each having a scenario alias
    assert data["database"]["total_disputes"] == 20
    assert data["database"]["breakdown"]["real_sandbox"] == 1
    assert data["database"]["breakdown"]["synthetic_benchmark"] == 19
    assert data["database"]["breakdown"]["live_webhook"] == 0

    # 2. Ingest 1 live webhook dispute
    webhook_payload = {
        "dispute_id": "PP-R-RECON-LIVE-01",
        "reason": "MERCHANDISE_OR_SERVICE_NOT_RECEIVED",
        "status": "WAITING_FOR_SELLER_RESPONSE",
        "amount": "99.00",
        "currency": "USD",
        "idempotency_key": "idemp_recon_01",
    }
    client.post("/api/webhooks/paypal", json=webhook_payload)

    # 3. Check health counts again
    resp2 = client.get("/api/health")
    data2 = resp2.json()
    assert data2["total_cases_loaded"] == 21
    assert data2["case_counts"]["total_unique_cases"] == 21
    assert data2["case_counts"]["live_webhook_disputes"] == 1
    assert data2["database"]["total_disputes"] == 21
    assert data2["database"]["breakdown"]["live_webhook"] == 1

    # 4. Soft-archive the dispute
    client.post("/api/disputes/PP-R-RECON-LIVE-01/archive", json={"reason": "TEST_ARCHIVAL"})

    resp3 = client.get("/api/health")
    data3 = resp3.json()
    assert data3["database"]["archived_disputes"] == 1
    assert data3["database"]["active_disputes"] == 20


# ============================================================================
# 6. Operational Safety: Online SQLite WAL Backup & Restoration
# ============================================================================

def test_sqlite_wal_online_backup_and_restoration(tmp_path):
    """Verify that native online backup flushes WAL pages consistently without corruption."""
    source_db = tmp_path / "live_source.db"
    backup_db = tmp_path / "live_backup.db"

    # Source database instance
    src_conn = DatabaseConnection(db_path=source_db)
    src_repo = DocketRepository(connection=src_conn)
    src_logger = AuditLogger(storage_path=tmp_path / "src_audit.jsonl", repository=src_repo)

    # Populate source data
    for i in range(5):
        d = DisputeCase(
            dispute_id=f"PP-R-BACKUP-{i:02d}",
            reason=DisputeReason.MERCHANDISE_OR_SERVICE_NOT_RECEIVED,
            lifecycle_stage=DisputeLifecycleStage.INQUIRY,
            status=DisputeStatus.WAITING_FOR_SELLER_RESPONSE,
            dispute_amount=Money(value=Decimal("10.00"), currency_code="USD"),
        )
        src_repo.save_dispute(d)
        src_logger.log_event(AuditEventType.DISPUTE_INGESTED, d.dispute_id, "SYSTEM", {"seq": i})

    # Perform online atomic backup while source connection is active
    saved_path = src_conn.backup(backup_db)
    assert saved_path.exists()

    # Open backup database with a fresh connection
    b_conn = DatabaseConnection(db_path=backup_db)
    b_repo = DocketRepository(connection=b_conn)

    # Verify all 5 disputes and 5 audit events are intact and verified
    assert b_repo.count_disputes() == 5
    b_events = b_repo.get_audit_events()
    assert len(b_events) == 5

    # Verify cryptographic hash chain inside restored backup
    chain_verif = b_repo.verify_db_audit_chain()
    assert chain_verif["is_valid"] is True
    assert chain_verif["verified_count"] == 5

    src_conn.close()
    b_conn.close()

