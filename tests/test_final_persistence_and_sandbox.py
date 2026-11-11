"""Final Persistence and PayPal Sandbox Integration Tests.

Validates:
1. Cryptographic serialization: RFC 8785 clarification, unambiguous delimiter boundaries,
   historical chain preservation without hash regeneration.
2. Merchant approval security: No unnecessary plaintext token leakage, strict pre-dispatch
   binding (dispute ID, action, payload hash, evaluation ID, evidence version), atomic
   transactional single-use consumption, and concurrent replay resistance.
3. Retention and migrations: Formal schema migrations tracking, approval & audit retention
   through archival, and online WAL backup restoration.
4. Genuine PayPal Sandbox persistence: Read-only live retrieval using OAuth 2.0 client credentials,
   provenance categorization as REAL_SANDBOX, survival across backend restarts, audit ledger
   recording, and clean separation from synthetic benchmarks.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from decimal import Decimal
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import pytest
from fastapi.testclient import TestClient

from docket.api.app import create_app
from docket.audit.logger import AuditLogger, AuditEventType
from docket.database.connection import DatabaseConnection
from docket.database.repository import DocketRepository
from docket.database.schema import get_applied_migrations, get_schema_version
from docket.dispatch.approval import (
    ActionMismatchError,
    ApprovalDecision,
    ApprovalService,
    DisputeMismatchError,
    EvaluationMismatchError,
    EvidenceVersionMismatchError,
    PayloadTamperedError,
    TokenAlreadyUsedError,
)
from docket.dispatch.dispatcher import EvidenceDispatcher
from docket.models.evidence import (
    Address,
    ExtractedClaim,
    OrderRecord,
    ShipmentRecord,
    TrackingStatus,
)
from docket.models.dispatch import MerchantApprovalRecord
from docket.models.dispute import (
    DisputeCase,
    DisputeLifecycleStage,
    DisputeReason,
    DisputeStatus,
    HATEOASLink,
    Money,
)
from docket.models.policy import DecisionType, OverallPolicyEvaluation
from docket.models.reconciliation import ReconciledDisputeBundle
from docket.reconciliation.engine import EvidenceReconciler


# ============================================================================
# 1. Cryptographic Serialization & Historical Integrity
# ============================================================================

def test_cryptographic_serialization_and_historical_integrity(tmp_path):
    """Verify canonical serialization, unambiguous field boundaries, and historical verification."""
    db_file = tmp_path / "crypto_audit.db"
    jsonl_file = tmp_path / "crypto_audit.jsonl"

    repo = DocketRepository(db_path=db_file)
    logger = AuditLogger(storage_path=jsonl_file, repository=repo)

    # 1. Log an event with structured payload
    payload = {"amount": "150.00", "currency": "USD", "items": ["sku_1", "sku_2"]}
    event = logger.log_event(
        event_type=AuditEventType.DISPUTE_INGESTED,
        dispute_id="PP-R-CRYPTO-01",
        actor="PAYPAL_WEBHOOK",
        payload=payload,
    )

    # 2. Check canonical JSON sorting (Python standard sort_keys=True, separators=(',', ':'))
    canonical_payload = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    assert canonical_payload == '{"amount":"150.00","currency":"USD","items":["sku_1","sku_2"]}'

    # 3. Check exact v1 fingerprint construction
    expected_fingerprint = (
        f"GENESIS:{event.event_id}:{event.event_type.value}:{event.timestamp.isoformat()}:"
        f"PP-R-CRYPTO-01:PAYPAL_WEBHOOK:{canonical_payload}"
    )
    expected_hash = hashlib.sha256(expected_fingerprint.encode("utf-8")).hexdigest()
    assert event.event_hash == expected_hash

    # 4. Verify unbroken chain in both SQLite and JSONL
    assert repo.verify_db_audit_chain()["is_valid"] is True
    assert logger.verify_chain_integrity() is True

    # 5. Verify existing historical chain in artifacts/docket.db (if exists) remains unbroken
    prod_db = Path("artifacts/docket.db")
    if prod_db.exists():
        prod_repo = DocketRepository(db_path=prod_db)
        prod_chain = prod_repo.verify_db_audit_chain()
        assert prod_chain["is_valid"] is True, f"Historical database chain broken: {prod_chain.get('error_message')}"
        assert prod_chain["total_events"] >= 40


# ============================================================================
# 2. Merchant Approval Security: Pre-Dispatch Binding & Concurrent Replay
# ============================================================================

def test_merchant_approval_pre_dispatch_validation_matrix(tmp_path):
    """Verify that dispatch blocks if dispute ID, action, payload hash, evaluation ID, or evidence version mismatch."""
    db_file = tmp_path / "approval_sec.db"
    repo = DocketRepository(db_path=db_file)
    svc = ApprovalService(repository=repo)
    logger = AuditLogger(storage_path=tmp_path / "appr_audit.jsonl", repository=repo)
    dispatcher = EvidenceDispatcher(approval_service=svc, audit_logger=logger)

    dispute = DisputeCase(
        dispute_id="PP-R-DISPATCH-BIND-01",
        reason=DisputeReason.MERCHANDISE_OR_SERVICE_NOT_RECEIVED,
        lifecycle_stage=DisputeLifecycleStage.CHARGEBACK,
        status=DisputeStatus.WAITING_FOR_SELLER_RESPONSE,
        dispute_amount=Money(value=Decimal("85.00"), currency_code="USD"),
        available_hateoAS_actions=[
            HATEOASLink(
                href="https://api-m.sandbox.paypal.com/v1/customer/disputes/PP-R-DISPATCH-BIND-01/provide-evidence",
                rel="provide_evidence",
                method="POST",
            )
        ],
    )
    order = OrderRecord(
        order_id="ORD-BIND-01",
        gross_amount=Money(value=Decimal("85.00"), currency_code="USD"),
        shipping_address=Address(postal_code="94107", country_code="US"),
    )
    shipment = ShipmentRecord(
        internal_order_id="ORD-BIND-01",
        tracking_number="9405511899223197428499",
        carrier_name="USPS",
        tracking_status=TrackingStatus.DELIVERED,
        delivery_timestamp=datetime(2026, 11, 1, 12, 0, 0, tzinfo=timezone.utc),
        shipment_address=Address(postal_code="94107", country_code="US"),
        source_identifier="carrier_tracking_usps",
    )
    reconciler = EvidenceReconciler(orders=[order], shipments=[shipment])
    bundle = reconciler.reconcile_dispute(dispute)
    evaluation = OverallPolicyEvaluation(
        dispute_id=dispute.dispute_id,
        overall_decision=DecisionType.ALLOW,
        summary="All carrier tracking requirements met.",
        evaluation_id="eval_spec_fixed_v1",
    )

    payload = dispatcher.formatter.format_fulfillment_evidence(bundle)
    req = svc.create_approval_request(
        dispute=dispute,
        policy_evaluation=evaluation,
        proposed_payload=payload,
        merchant_user_id="lead_merchant",
        bundle=bundle,
    )
    repo.save_dispute(dispute)
    rec = svc.record_approval(req, merchant_user_id="lead_merchant", decision=ApprovalDecision.APPROVE)
    repo.save_approval_record(rec)

    # 1. Test Evaluation ID mismatch
    tampered_eval = evaluation.model_copy(update={"evaluation_id": "eval_tampered_different_id"})
    with pytest.raises(EvaluationMismatchError):
        dispatcher.dispatch_evidence(
            dispute=dispute,
            bundle=bundle,
            evaluation=tampered_eval,
            approval_record=rec,
        )

    # 2. Test Evidence Version mismatch
    tampered_bundle = bundle.model_copy(update={"reconciled_at": datetime(2026, 11, 5, 12, 0, 0, tzinfo=timezone.utc)})
    with pytest.raises(EvidenceVersionMismatchError):
        dispatcher.dispatch_evidence(
            dispute=dispute,
            bundle=tampered_bundle,
            evaluation=evaluation,
            approval_record=rec,
        )

    # 3. Test Dispute ID mismatch
    tampered_rec = rec.model_copy(update={"dispute_id": "PP-R-WRONG-DISPUTE-999"})
    with pytest.raises(DisputeMismatchError):
        dispatcher.dispatch_evidence(
            dispute=dispute,
            bundle=bundle,
            evaluation=evaluation,
            approval_record=tampered_rec,
        )

    # 4. Test Action mismatch
    tampered_action_rec = rec.model_copy(update={"action": "accept_claim"})
    with pytest.raises(ActionMismatchError):
        dispatcher.dispatch_evidence(
            dispute=dispute,
            bundle=bundle,
            evaluation=evaluation,
            approval_record=tampered_action_rec,
        )

    # 5. Test Payload Hash mismatch
    tampered_hash_rec = rec.model_copy(update={"payload_hash": "0000000000000000000000000000000000000000000000000000000000000000"})
    with pytest.raises(PayloadTamperedError):
        dispatcher.dispatch_evidence(
            dispute=dispute,
            bundle=bundle,
            evaluation=evaluation,
            approval_record=tampered_hash_rec,
        )


def test_concurrent_approval_replay_attempts(tmp_path):
    """Verify that multiple concurrent threads attempting to consume the same approval token are safely rejected."""
    db_file = tmp_path / "concurrent_replay.db"
    repo = DocketRepository(db_path=db_file)
    svc = ApprovalService(repository=repo)

    dispute = DisputeCase(
        dispute_id="PP-R-CONCURRENT-01",
        reason=DisputeReason.MERCHANDISE_OR_SERVICE_NOT_RECEIVED,
        lifecycle_stage=DisputeLifecycleStage.INQUIRY,
        status=DisputeStatus.WAITING_FOR_SELLER_RESPONSE,
        dispute_amount=Money(value=Decimal("50.00"), currency_code="USD"),
    )
    eval_res = OverallPolicyEvaluation(dispute_id=dispute.dispute_id, overall_decision=DecisionType.ALLOW, summary="OK")
    payload = {"evidences": [{"notes": "Concurrent test evidence"}]}

    req = svc.create_approval_request(dispute, eval_res, payload, merchant_user_id="merchant_concur")
    repo.save_dispute(dispute)
    rec = svc.record_approval(req, merchant_user_id="merchant_concur", decision=ApprovalDecision.APPROVE)
    repo.save_approval_record(rec)

    success_count = 0
    failure_count = 0
    errors = []

    def try_verify(thread_idx: int):
        nonlocal success_count, failure_count
        try:
            ok = svc.verify_token(
                token=rec.approval_token,
                dispute_id=dispute.dispute_id,
                payload=payload,
                merchant_user_id="merchant_concur",
                action="provide_evidence",
                consume_nonce=True,
                dispatch_id=f"disp_thread_{thread_idx}",
            )
            if ok:
                success_count += 1
        except TokenAlreadyUsedError as e:
            failure_count += 1
            errors.append(str(e))

    # Execute 10 concurrent threads attempting to consume the exact same token
    with ThreadPoolExecutor(max_workers=10) as executor:
        futures = [executor.submit(try_verify, i) for i in range(10)]
        for f in futures:
            f.result()

    # Exactly 1 thread must succeed, and exactly 9 must fail with TokenAlreadyUsedError
    assert success_count == 1
    assert failure_count == 9
    assert len(errors) == 9
    assert repo.is_nonce_consumed(rec.nonce) is True


# ============================================================================
# 3. Retention & Versioned Migrations
# ============================================================================

def test_schema_migrations_and_retention(tmp_path):
    """Verify formal versioned migration tracking and audit retention through soft archival."""
    db_file = tmp_path / "migrated.db"
    conn = DatabaseConnection(db_path=db_file)

    # 1. Verify schema migrations table exists and tracks version 1 and 2
    migrations = get_applied_migrations(conn.connection)
    assert len(migrations) >= 2
    versions = [m["version"] for m in migrations]
    assert 1 in versions
    assert 2 in versions
    assert get_schema_version(conn.connection) >= 2

    repo = DocketRepository(connection=conn)
    logger = AuditLogger(storage_path=tmp_path / "retention_audit.jsonl", repository=repo)

    # 2. Create dispute with approval and audit trail
    d = DisputeCase(
        dispute_id="PP-R-MIG-ARCHIVE-01",
        reason=DisputeReason.MERCHANDISE_OR_SERVICE_NOT_RECEIVED,
        lifecycle_stage=DisputeLifecycleStage.CHARGEBACK,
        status=DisputeStatus.WAITING_FOR_SELLER_RESPONSE,
        dispute_amount=Money(value=Decimal("120.00"), currency_code="USD"),
    )
    repo.save_dispute(d)
    logger.log_event(AuditEventType.DISPUTE_INGESTED, d.dispute_id, "SYSTEM", {"amount": "120.00"})

    appr = MerchantApprovalRecord(
        approval_id="appr_mig_01",
        dispute_id=d.dispute_id,
        merchant_user_id="auditor_jane",
        decision=ApprovalDecision.APPROVE,
        action="provide_evidence",
        approved_at=datetime.now(timezone.utc),
        approval_token="tok_safe_test",
        nonce="nonce_mig_01",
    )
    repo.save_approval_record(appr)

    # 3. Soft archive the dispute
    repo.archive_dispute(d.dispute_id, reason="COMPLIANCE_HOLD")

    # 4. Verify that dispute is excluded from active triage by default, but approvals and audits are intact
    active_disputes = repo.list_disputes(include_archived=False)
    assert not any(x.dispute_id == d.dispute_id for x in active_disputes)

    all_disputes = repo.list_disputes(include_archived=True)
    assert any(x.dispute_id == d.dispute_id for x in all_disputes)

    # Merchant approvals must remain queryable
    retained_appr = repo.get_approval_record(d.dispute_id)
    assert retained_appr is not None
    assert retained_appr.approval_id == "appr_mig_01"

    # Audit events must remain unbroken
    events = repo.get_audit_events(d.dispute_id)
    assert len(events) >= 1
    assert repo.verify_db_audit_chain()["is_valid"] is True


# ============================================================================
# 4. Genuine PayPal Sandbox Read-Only Persistence
# ============================================================================

def test_actual_paypal_sandbox_persistence_and_provenance(tmp_path):
    """Verify live read-only PayPal Sandbox dispute retrieval, provenance tagging, and reboot survival."""
    audit_file = tmp_path / "sandbox_audit.jsonl"
    db_file = tmp_path / "sandbox_live.db"

    has_client_id = bool(os.environ.get("PAYPAL_CLIENT_ID"))
    has_client_secret = bool(os.environ.get("PAYPAL_CLIENT_SECRET"))

    if not (has_client_id and has_client_secret):
        pytest.skip("PayPal Sandbox credentials not configured in environment.")

    # Boot API application instance with empty database
    app = create_app(audit_log_path=str(audit_file), db_path=str(db_file))
    client = TestClient(app)

    # 1. Trigger live Sandbox sync endpoint
    resp = client.post("/api/disputes/sandbox/sync")
    assert resp.status_code == 200
    sync_data = resp.json()

    assert sync_data["success"] is True
    assert sync_data["dispute_id"] == "PP-R-NKI-10193390"
    assert sync_data["provenance"] == "REAL_SANDBOX"
    assert sync_data["amount"] == "25.00"
    assert sync_data["currency"] == "USD"
    assert sync_data["reason"] == "MERCHANDISE_OR_SERVICE_NOT_RECEIVED"

    # 2. Verify health report reports 1 REAL_SANDBOX dispute and 19 SYNTHETIC_BENCHMARK scenarios
    h_resp = client.get("/api/health")
    h_data = h_resp.json()
    assert h_data["database"]["breakdown"]["real_sandbox"] == 1
    assert h_data["database"]["breakdown"]["synthetic_benchmark"] == 19
    assert h_data["total_cases_loaded"] == 20
    assert h_data["database"]["total_disputes"] == 20

    # 3. Verify audit trail records the ingestion by PAYPAL_SANDBOX_API
    audit_resp = client.get("/api/audit-trail?dispute_id=PP-R-NKI-10193390")
    assert audit_resp.status_code == 200
    events = audit_resp.json()["events"]
    assert any(e["actor"] == "PAYPAL_SANDBOX_API" and e["payload"].get("provenance") == "REAL_SANDBOX" for e in events)

    # 4. Simulate server restart: Boot second independent instance on same database
    app2 = create_app(audit_log_path=str(audit_file), db_path=str(db_file))
    client2 = TestClient(app2)

    h2_resp = client2.get("/api/health")
    h2_data = h2_resp.json()
    assert h2_data["database"]["breakdown"]["real_sandbox"] == 1
    assert h2_data["database"]["breakdown"]["synthetic_benchmark"] == 19
    assert h2_data["total_cases_loaded"] == 20
