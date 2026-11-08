"""Tests for Docket Minimal SQLite Persistence & Architecture Verification.

Verifies:
1. Schema initialization, PRAGMA foreign_keys = ON, PRAGMA journal_mode = WAL.
2. Dispute CRUD, decimal-safe monetary representation without float precision loss.
3. Source records persistence (Order, Shipment, Refund, Customer Communication).
4. Relational integrity & foreign key CASCADE deletion.
5. Extracted claims with epistemic metadata and source citations.
6. Policy evaluation persistence (invariants and advisories).
7. Merchant approval records persistence.
8. Webhook receipt deduplication with atomic SQLite UNIQUE constraints.
9. Backend restart simulation: close DB connection, re-open from disk, verify full case preservation.
10. Cryptographic hash-chain persistence in SQLite & mathematical tamper detection.
11. Full FastAPI end-to-end webhook ingestion, approval, and server restart survival.
"""

from datetime import datetime, timedelta, timezone
from decimal import Decimal
import json
from pathlib import Path
import sqlite3
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
    VerificationStatus,
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
from docket.api.app import create_app


@pytest.fixture
def db_conn(tmp_path):
    db_file = tmp_path / "test_docket.db"
    conn = DatabaseConnection(db_path=db_file)
    yield conn
    conn.close()


@pytest.fixture
def repo(db_conn):
    return DocketRepository(connection=db_conn)


# ============================================================================
# 1. Schema & Pragmas
# ============================================================================

def test_schema_initialization_and_pragmas(db_conn):
    """Verify that foreign keys are enforced and WAL mode is active."""
    row_fk = db_conn.fetchone("PRAGMA foreign_keys")
    assert row_fk[0] == 1, "Foreign keys must be enabled"

    row_journal = db_conn.fetchone("PRAGMA journal_mode")
    assert str(row_journal[0]).lower() == "wal", "WAL mode must be active for disk databases"

    # Verify all 7 required tables exist
    tables = [
        "disputes",
        "source_records",
        "extracted_claims",
        "policy_evaluations",
        "merchant_approvals",
        "webhook_receipts",
        "audit_events",
    ]
    for table in tables:
        row = db_conn.fetchone(
            "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
            (table,),
        )
        assert row is not None, f"Table {table} must exist"


# ============================================================================
# 2. Decimal-Safe Dispute Persistence
# ============================================================================

def test_dispute_crud_and_decimal_safety(repo):
    """Ensure monetary amounts are stored as exact decimal text without float truncation."""
    dispute = DisputeCase(
        dispute_id="PP-R-TEST-DECIMAL-01",
        reason=DisputeReason.MERCHANDISE_OR_SERVICE_NOT_RECEIVED,
        lifecycle_stage=DisputeLifecycleStage.CHARGEBACK,
        status=DisputeStatus.WAITING_FOR_SELLER_RESPONSE,
        dispute_amount=Money(value=Decimal("1234567.89"), currency_code="USD"),
        seller_response_due_date=datetime(2026, 12, 1, 12, 0, 0, tzinfo=timezone.utc),
        dispute_create_time=datetime(2026, 11, 1, 10, 0, 0, tzinfo=timezone.utc),
        buyer_transaction_id="TX-BUYER-888",
    )

    repo.save_dispute(dispute)

    # Inspect raw text in SQLite
    raw_row = repo.conn.fetchone(
        "SELECT amount, currency FROM disputes WHERE dispute_id = ?",
        (dispute.dispute_id,),
    )
    assert raw_row["amount"] == "1234567.89", "Stored as precise decimal string"
    assert raw_row["currency"] == "USD"

    # Reconstruct domain model
    loaded = repo.get_dispute(dispute.dispute_id)
    assert loaded is not None
    assert loaded.dispute_id == dispute.dispute_id
    assert loaded.dispute_amount.value == Decimal("1234567.89")
    assert isinstance(loaded.dispute_amount.value, Decimal)
    assert loaded.buyer_transaction_id == "TX-BUYER-888"


# ============================================================================
# 3. Source Records & Relational Integrity
# ============================================================================

def test_source_records_and_cascade_deletion(repo):
    """Verify source records persistence and foreign key CASCADE deletion upon dispute removal."""
    dispute = DisputeCase(
        dispute_id="PP-R-CASCADE-01",
        reason=DisputeReason.MERCHANDISE_OR_SERVICE_NOT_RECEIVED,
        lifecycle_stage=DisputeLifecycleStage.INQUIRY,
        status=DisputeStatus.WAITING_FOR_SELLER_RESPONSE,
        dispute_amount=Money(value=Decimal("50.00"), currency_code="USD"),
    )
    repo.save_dispute(dispute)

    order = OrderRecord(
        order_id="ORD-CASCADE-99",
        paypal_transaction_id="TX-CASCADE-99",
        gross_amount=Money(value=Decimal("50.00"), currency_code="USD"),
        customer_email="buyer@example.com",
    )
    shipment = ShipmentRecord(
        internal_order_id="ORD-CASCADE-99",
        tracking_number="TRACK-CASCADE-99",
        carrier_name="FedEx",
        tracking_status=TrackingStatus.DELIVERED,
        source_identifier="carrier_tracking_fedex",
    )

    repo.save_source_record(
        dispute_id=dispute.dispute_id,
        source_id="ord_ORD-CASCADE-99",
        source_type=SourceType.ORDER_INVOICE.value,
        record_type="OrderRecord",
        payload=order.model_dump(mode="json"),
    )
    repo.save_source_record(
        dispute_id=dispute.dispute_id,
        source_id="ship_TRACK-CASCADE-99",
        source_type=SourceType.CARRIER_TRACKING.value,
        record_type="ShipmentRecord",
        payload=shipment.model_dump(mode="json"),
    )

    records = repo.get_source_records(dispute.dispute_id)
    assert len(records) == 2

    # Attempt to insert orphan child referencing non-existent dispute
    with pytest.raises(sqlite3.IntegrityError):
        with repo.conn.transaction() as cur:
            repo.save_source_record(
                dispute_id="NON_EXISTENT_DISPUTE",
                source_id="orphan_01",
                source_type="OTHER",
                record_type="OrderRecord",
                payload={},
                cur=cur,
            )

    # Delete parent dispute and verify CASCADE deletion of source records
    with repo.conn.transaction() as cur:
        cur.execute("DELETE FROM disputes WHERE dispute_id = ?", (dispute.dispute_id,))

    records_after = repo.get_source_records(dispute.dispute_id)
    assert len(records_after) == 0, "Source records must be deleted by cascade"


# ============================================================================
# 4. Extracted Claims & Epistemic Metadata Persistence
# ============================================================================

def test_claims_with_epistemic_metadata(repo):
    """Ensure epistemic metadata (carrier confirmation, evidence basis) round-trips correctly."""
    dispute = DisputeCase(
        dispute_id="PP-R-CLAIM-01",
        reason=DisputeReason.MERCHANDISE_OR_SERVICE_NOT_RECEIVED,
        lifecycle_stage=DisputeLifecycleStage.INQUIRY,
        status=DisputeStatus.WAITING_FOR_SELLER_RESPONSE,
        dispute_amount=Money(value=Decimal("75.00"), currency_code="USD"),
    )
    repo.save_dispute(dispute)

    epistemic = ClaimEpistemicMetadata(
        source_category="CARRIER_TRACKING",
        attribution="USPS Tracking Service",
        evidence_basis=EvidenceBasis.DIRECT_RECORD,
        independent_carrier_confirmation=True,
        supporting_source_id="carrier_tracking_usps",
    )
    citation = SourceCitation(
        source_type=SourceType.CARRIER_TRACKING,
        source_identifier="carrier_tracking_usps",
        field_path="delivery_timestamp",
        extracted_value="2026-10-18T14:22:00Z",
        verification_status=VerificationStatus.VERIFIED,
    )
    claim = ExtractedClaim(
        claim_id="CLM-TEST-01",
        claim_type=ClaimType.DELIVERY_COMPLETED,
        factual_assertion="Item delivered to 95131 on Oct 18.",
        supporting_sources=[citation],
        claim_status=ClaimStatus.SUPPORTED,
        epistemic_metadata=epistemic,
    )

    repo.save_claims(dispute.dispute_id, [claim])

    loaded_claims = repo.get_claims(dispute.dispute_id)
    assert len(loaded_claims) == 1
    c = loaded_claims[0]
    assert c.claim_id == "CLM-TEST-01"
    assert c.claim_type == ClaimType.DELIVERY_COMPLETED
    assert c.epistemic_metadata is not None
    assert c.epistemic_metadata.evidence_basis == EvidenceBasis.DIRECT_RECORD
    assert c.epistemic_metadata.independent_carrier_confirmation is True
    assert len(c.supporting_sources) == 1
    assert c.supporting_sources[0].field_path == "delivery_timestamp"


# ============================================================================
# 5. Policy Evaluations & Merchant Approvals Persistence
# ============================================================================

def test_evaluations_and_approvals_persistence(repo):
    """Verify evaluation invariant diagnostics and merchant approval record durability."""
    dispute = DisputeCase(
        dispute_id="PP-R-APPR-01",
        reason=DisputeReason.MERCHANDISE_OR_SERVICE_NOT_RECEIVED,
        lifecycle_stage=DisputeLifecycleStage.INQUIRY,
        status=DisputeStatus.WAITING_FOR_SELLER_RESPONSE,
        dispute_amount=Money(value=Decimal("120.00"), currency_code="USD"),
    )
    repo.save_dispute(dispute)

    chk1 = PolicyCheckResult(
        decision=DecisionType.ALLOW,
        rule_identifier="DELIVERY_CONFIRMATION_INVARIANT",
        explanation="Direct carrier delivery confirmed.",
    )
    chk2 = PolicyCheckResult(
        decision=DecisionType.REVIEW,
        rule_identifier="BUYER_NON_RECEIPT_CONTRADICTION",
        explanation="Advisory note on buyer claim.",
        is_advisory=True,
    )
    evaluation = OverallPolicyEvaluation(
        dispute_id=dispute.dispute_id,
        overall_decision=DecisionType.ALLOW,
        factual_readiness=DecisionType.ALLOW,
        action_readiness=DecisionType.ALLOW,
        check_results=[chk1],
        advisories=[chk2],
        summary="Ready for merchant submission.",
    )
    repo.save_policy_evaluation(dispute.dispute_id, evaluation)

    loaded_eval = repo.get_policy_evaluation(dispute.dispute_id)
    assert loaded_eval is not None
    assert loaded_eval.overall_decision == DecisionType.ALLOW
    assert len(loaded_eval.check_results) == 1
    assert loaded_eval.check_results[0].rule_identifier == "DELIVERY_CONFIRMATION_INVARIANT"
    assert len(loaded_eval.advisories) == 1

    # Save Approval Record
    approval = MerchantApprovalRecord(
        approval_id="appr_sec_999",
        dispute_id=dispute.dispute_id,
        merchant_user_id="merchant_admin",
        decision=ApprovalDecision.APPROVE,
        approved_at=datetime.now(timezone.utc),
        approval_token="hmac_valid_token_abc",
        client_ip="192.168.1.50",
        user_agent="Mozilla/5.0 Test",
    )
    repo.save_approval_record(approval)

    loaded_appr = repo.get_approval_record(dispute.dispute_id)
    assert loaded_appr is not None
    assert loaded_appr.approval_id == "appr_sec_999"
    assert loaded_appr.is_approved() is True
    assert loaded_appr.client_ip == "192.168.1.50"


# ============================================================================
# 6. Webhook Idempotency Constraint
# ============================================================================

def test_webhook_idempotency_constraint(repo):
    """Verify that duplicate idempotency_keys are caught by the SQLite UNIQUE constraint."""
    idemp_key = "idemp_unique_key_001"
    payload = {"reason": "MERCHANDISE_OR_SERVICE_NOT_RECEIVED", "amount": "25.00"}

    # First attempt: new receipt
    is_dup1, orig_id1 = repo.record_webhook_receipt(
        event_id="rec_01",
        dispute_id="PP-R-IDEMP-01",
        event_type="DISPUTE_INGESTED",
        idempotency_key=idemp_key,
        payload=payload,
    )
    assert is_dup1 is False
    assert orig_id1 == "rec_01"

    # Second attempt with same key: caught by SQLite unique constraint
    is_dup2, orig_id2 = repo.record_webhook_receipt(
        event_id="rec_02",
        dispute_id="PP-R-IDEMP-01",
        event_type="DISPUTE_INGESTED",
        idempotency_key=idemp_key,
        payload=payload,
    )
    assert is_dup2 is True
    assert orig_id2 == "rec_01"

    # Third attempt with new key: passes
    is_dup3, orig_id3 = repo.record_webhook_receipt(
        event_id="rec_03",
        dispute_id="PP-R-IDEMP-01",
        event_type="DISPUTE_INGESTED",
        idempotency_key="idemp_unique_key_002",
        payload=payload,
    )
    assert is_dup3 is False
    assert orig_id3 == "rec_03"


# ============================================================================
# 7. Backend Restart Simulation (Connection Close & Re-open)
# ============================================================================

def test_backend_restart_simulation(tmp_path):
    """Simulate a complete process restart: save case, close connection, re-open, and verify state."""
    db_file = tmp_path / "restart_simulation.db"

    # Session 1: Create connection, ingest case, save full bundle
    conn1 = DatabaseConnection(db_path=db_file)
    repo1 = DocketRepository(connection=conn1)

    dispute = DisputeCase(
        dispute_id="PP-R-RESTART-01",
        reason=DisputeReason.MERCHANDISE_OR_SERVICE_NOT_RECEIVED,
        lifecycle_stage=DisputeLifecycleStage.CHARGEBACK,
        status=DisputeStatus.WAITING_FOR_SELLER_RESPONSE,
        dispute_amount=Money(value=Decimal("89.95"), currency_code="USD"),
    )
    order = OrderRecord(
        order_id="ORD-RESTART-01",
        paypal_transaction_id="TX-RESTART-01",
        gross_amount=Money(value=Decimal("89.95"), currency_code="USD"),
        customer_email="restart_user@example.com",
    )
    shipment = ShipmentRecord(
        internal_order_id="ORD-RESTART-01",
        tracking_number="TRACK-RESTART-01",
        carrier_name="UPS",
        tracking_status=TrackingStatus.DELIVERED,
        source_identifier="carrier_tracking_ups",
    )
    bundle = ReconciledDisputeBundle(
        dispute_id=dispute.dispute_id,
        status=ReconciliationStatus.RECONCILED,
        matched_order=order,
        matched_shipments=[shipment],
    )
    eval_res = OverallPolicyEvaluation(
        dispute_id=dispute.dispute_id,
        overall_decision=DecisionType.ALLOW,
        factual_readiness=DecisionType.ALLOW,
        action_readiness=DecisionType.ALLOW,
        summary="Evaluation survives restart.",
    )
    approval = MerchantApprovalRecord(
        approval_id="appr_restart_01",
        dispute_id=dispute.dispute_id,
        merchant_user_id="supervisor_bob",
        decision=ApprovalDecision.APPROVE,
        approved_at=datetime.now(timezone.utc),
        approval_token="tok_restart_valid",
    )

    repo1.save_full_case(
        dispute=dispute,
        bundle=bundle,
        evaluation=eval_res,
        claims=[],
        scenario_id="SCENARIO_RESTART_TEST",
        has_prompt_threat=False,
        approval_record=approval,
    )

    # Terminate Session 1 (simulates server shutdown)
    conn1.close()

    # Session 2: Fresh process start
    conn2 = DatabaseConnection(db_path=db_file)
    repo2 = DocketRepository(connection=conn2)

    persisted = repo2.load_persisted_cases()
    assert len(persisted) == 1
    p = persisted[0]

    assert p["dispute"].dispute_id == "PP-R-RESTART-01"
    assert p["dispute"].dispute_amount.value == Decimal("89.95")
    assert p["scenario_id"] == "SCENARIO_RESTART_TEST"
    assert p["bundle"].matched_order.order_id == "ORD-RESTART-01"
    assert len(p["bundle"].matched_shipments) == 1
    assert p["bundle"].matched_shipments[0].tracking_number == "TRACK-RESTART-01"
    assert p["evaluation"].overall_decision == DecisionType.ALLOW
    assert p["approval_record"] is not None
    assert p["approval_record"].merchant_user_id == "supervisor_bob"
    assert p["approval_record"].is_approved() is True

    conn2.close()


# ============================================================================
# 8. Audit Hash Chain in Database & Tamper Detection
# ============================================================================

def test_audit_hash_chain_in_database_and_tamper_detection(repo):
    """Verify cryptographic hash chaining inside SQLite and detection of tampered rows."""
    from docket.audit.logger import AuditLogger

    # Use AuditLogger with repo attached
    logger = AuditLogger(repository=repo)
    ev1 = logger.log_event(AuditEventType.DISPUTE_INGESTED, "DISP-H1", "SYSTEM", {"amount": "10.00"})
    ev2 = logger.log_event(AuditEventType.EVIDENCE_RECONCILED, "DISP-H1", "SYSTEM", {"matched": True})
    ev3 = logger.log_event(AuditEventType.APPROVAL_GRANTED, "DISP-H1", "merchant_admin", {"token": "valid"})

    # Check chain in SQLite
    verif = repo.verify_db_audit_chain()
    assert verif["is_valid"] is True
    assert verif["total_events"] >= 3
    assert verif["failed_count"] == 0

    # Tamper with Event 2 payload directly in the database
    with repo.conn.transaction() as cur:
        cur.execute(
            "UPDATE audit_events SET payload = ? WHERE event_id = ?",
            (json.dumps({"matched": False, "tampered": True}), ev2.event_id),
        )

    # Re-verify and assert mathematical tamper detection
    tampered_verif = repo.verify_db_audit_chain()
    assert tampered_verif["is_valid"] is False
    assert tampered_verif["failed_event_id"] == ev2.event_id
    assert "Hash mismatch" in tampered_verif["error_message"]


# ============================================================================
# 9. FastAPI End-to-End Server Restart Verification
# ============================================================================

def test_fastapi_server_restart_with_webhook_and_approval(tmp_path):
    """Test full HTTP cycle: webhook ingest -> authorize -> restart server -> verify persisted state."""
    audit_file = tmp_path / "server_restart_audit.jsonl"
    db_file = tmp_path / "server_restart_audit.db"

    # Server Instance 1
    app1 = create_app(audit_log_path=str(audit_file), db_path=str(db_file))
    client1 = TestClient(app1)

    # 1. Ingest new dispute via webhook
    webhook_payload = {
        "dispute_id": "PP-R-LIVE-SERVER-01",
        "reason": "MERCHANDISE_OR_SERVICE_NOT_RECEIVED",
        "status": "WAITING_FOR_SELLER_RESPONSE",
        "amount": "64.50",
        "currency": "USD",
        "idempotency_key": "idemp_webhook_live_01",
        "actor": "PAYPAL_WEBHOOK",
    }
    resp_ingest = client1.post("/api/webhooks/paypal", json=webhook_payload)
    assert resp_ingest.status_code == 200
    assert resp_ingest.json()["is_duplicate"] is False

    # Verify present in triage list
    resp_list1 = client1.get("/api/disputes")
    disp_item = next((d for d in resp_list1.json() if d["dispute_id"] == "PP-R-LIVE-SERVER-01"), None)
    assert disp_item is not None
    assert disp_item["amount"] == "64.50"
    assert disp_item["approval_status"] == "PENDING"

    # 2. Authorize dispute
    auth_resp = client1.post(
        "/api/disputes/PP-R-LIVE-SERVER-01/authorize",
        json={"merchant_user_id": "lead_agent", "decision": "APPROVE"},
    )
    assert auth_resp.status_code == 200
    assert auth_resp.json()["decision"] == "APPROVE"

    # Verify triage list shows APPROVED
    resp_list2 = client1.get("/api/disputes")
    disp_updated = next(d for d in resp_list2.json() if d["dispute_id"] == "PP-R-LIVE-SERVER-01")
    assert disp_updated["approval_status"] == "APPROVE"

    # --- SIMULATE SERVER PROCESS REBOOT ---
    # Spin up Server Instance 2 pointing to the exact same database & audit file
    app2 = create_app(audit_log_path=str(audit_file), db_path=str(db_file))
    client2 = TestClient(app2)

    # Check health shows database populated
    health_resp = client2.get("/api/health")
    assert health_resp.status_code == 200
    assert health_resp.json()["database"]["type"] == "sqlite"

    # Check triage list on the new server instance
    resp_list_reboot = client2.get("/api/disputes")
    reboot_disp = next((d for d in resp_list_reboot.json() if d["dispute_id"] == "PP-R-LIVE-SERVER-01"), None)
    assert reboot_disp is not None, "Ingested dispute must survive backend restart"
    assert reboot_disp["approval_status"] == "APPROVE", "Merchant approval must survive backend restart"
    assert reboot_disp["amount"] == "64.50"

    # Check case detail on new server instance
    detail_resp = client2.get("/api/disputes/PP-R-LIVE-SERVER-01")
    assert detail_resp.status_code == 200
    assert detail_resp.json()["approval_record"]["decision"] == "APPROVE"
    assert detail_resp.json()["approval_record"]["merchant_user_id"] == "lead_agent"
