"""Tests for Milestone 6: Controlled Evidence Submission & Merchant Approval Gate.

Tests:
1. Approval Models & Token Security (HMAC signing, expiration, tampering detection).
2. Human Summary Generation (Factual grounding, clear decisions, advisories).
3. PayPal Evidence Payload Formatting (Adheres to PayPal provide-evidence schema).
4. Deterministic Pre-Submission Policy Gate (Blocks unverified claims, requires readiness).
5. Merchant Approval Verification Gate (Rejects unapproved, expired, or tampered submissions).
6. Idempotency Lock (Prevents duplicate submissions to PayPal).
7. Action Dispatcher with Mocked PayPal Client (HATEOAS resolution, correlation ID capture, error handling).
8. Append-Only Hash-Chained Audit Trail (Tamper-evident cryptographic ledger).
"""

from datetime import datetime, timedelta, timezone
from decimal import Decimal
import json
import os
from pathlib import Path
import pytest
from unittest.mock import MagicMock, patch

from docket.models.dispute import (
    DisputeCase,
    DisputeLifecycleStage,
    DisputeReason,
    DisputeStatus,
    HATEOASLink,
    Money,
)
from docket.models.evidence import (
    Address,
    ExtractedClaim,
    OrderRecord,
    ShipmentRecord,
    SourceCitation,
    TrackingStatus,
)
from docket.models.policy import (
    DecisionType,
    OverallPolicyEvaluation,
    PolicyCheckResult,
)
from docket.models.reconciliation import (
    MatchConfidence,
    MatchStrategy,
    ReconciledDisputeBundle,
    ReconciliationStatus,
)
from docket.models.dispatch import (
    ApprovalDecision,
    ApprovalRequest,
    DispatchResult,
    EvidencePayload,
    MerchantApprovalRecord,
)
from docket.models.audit import AuditEvent, AuditEventType
from docket.dispatch.approval import (
    ApprovalService,
    InvalidSignatureError,
    PayloadTamperedError,
    TokenExpiredError,
)
from docket.dispatch.dispatcher import (
    DuplicateSubmissionError,
    EvidenceDispatcher,
    EvidencePayloadFormatter,
    MerchantApprovalRequiredError,
    SubmissionBlockedError,
    SubmissionRejectedError,
)
from docket.audit.logger import AuditLogger, AuditVerificationError


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture
def secret_key() -> str:
    return "test-audit-approval-secret-key-32chars!"


@pytest.fixture
def valid_dispute_case() -> DisputeCase:
    return DisputeCase(
        dispute_id="PP-R-NKI-10193390",
        reason="MERCHANDISE_OR_SERVICE_NOT_RECEIVED",
        lifecycle_stage=DisputeLifecycleStage.INQUIRY,
        status=DisputeStatus.WAITING_FOR_SELLER_RESPONSE,
        dispute_amount=Money(value=Decimal("25.00"), currency_code="USD"),
        requested_evidence_types=["PROOF_OF_FULFILLMENT"],
        requested_evidence_sources=["REQUESTED_FROM_SELLER"],
        seller_response_due_date=datetime(2026, 11, 7, 13, 37, 42, tzinfo=timezone.utc),
        available_hateoas_actions=[
            HATEOASLink(
                href="https://api-m.sandbox.paypal.com/v1/customer/disputes/PP-R-NKI-10193390/provide-evidence",
                rel="provide_evidence",
                method="POST",
            )
        ],
        disputed_transaction_id="4R073105U90937213",
        seller_transaction_id="4R073105U90937213",
        buyer_transaction_id="4H384663R6471042S",
    )


@pytest.fixture
def valid_shipment() -> ShipmentRecord:
    return ShipmentRecord(
        internal_order_id="ORD-10193390",
        tracking_number="9400111899223197428490",
        carrier_name="USPS",
        tracking_status=TrackingStatus.DELIVERED,
        shipment_timestamp=datetime(2026, 10, 15, 10, 0, 0, tzinfo=timezone.utc),
        delivery_timestamp=datetime(2026, 10, 18, 14, 22, 0, tzinfo=timezone.utc),
        shipment_address=Address(
            recipient_name="John Doe",
            line1="123 Main St",
            city="San Jose",
            state_or_province="CA",
            postal_code="95131",
            country_code="US",
        ),
        source_identifier="carrier_tracking_usps",
        recipient_signature_present=True,
    )


@pytest.fixture
def valid_order() -> OrderRecord:
    return OrderRecord(
        order_id="ORD-10193390",
        paypal_transaction_id="4R073105U90937213",
        customer_email="sb-6oifq53423350@personal.example.com",
        order_amount=Decimal("25.00"),
        currency_code="USD",
        order_timestamp=datetime(2026, 10, 15, 9, 30, 0, tzinfo=timezone.utc),
        shipping_address=Address(
            recipient_name="John Doe",
            line1="123 Main St",
            city="San Jose",
            state_or_province="CA",
            postal_code="95131",
            country_code="US",
        ),
    )


@pytest.fixture
def reconciled_bundle(valid_dispute_case, valid_order, valid_shipment) -> ReconciledDisputeBundle:
    return ReconciledDisputeBundle(
        dispute_id=valid_dispute_case.dispute_id,
        dispute_case=valid_dispute_case,
        status=ReconciliationStatus.RECONCILED,
        match_strategy=MatchStrategy.EXACT_TRANSACTION_ID,
        confidence=MatchConfidence.EXACT,
        matched_order=valid_order,
        matched_shipments=[valid_shipment],
        matched_messages=[],
        matched_refunds=[],
        discrepancies=[],
    )


@pytest.fixture
def approved_policy_evaluation() -> OverallPolicyEvaluation:
    return OverallPolicyEvaluation(
        dispute_id="PP-R-NKI-10193390",
        overall_decision=DecisionType.ALLOW,
        factual_readiness=DecisionType.ALLOW,
        action_readiness=DecisionType.ALLOW,
        advisories=[],
        check_results=[
            PolicyCheckResult(
                decision=DecisionType.ALLOW,
                rule_identifier="RULE_DELIVERY_PROOF",
                explanation="Carrier tracking confirms physical delivery.",
            ),
            PolicyCheckResult(
                decision=DecisionType.ALLOW,
                rule_identifier="RULE_HATEOAS_ACTION",
                explanation="provide_evidence action is available and permitted.",
            ),
        ],
        summary="All evidence checks passed. Delivery verified with matching destination postal code.",
        evaluated_at=datetime(2026, 11, 3, 12, 0, 0, tzinfo=timezone.utc),
    )


@pytest.fixture
def blocked_policy_evaluation() -> OverallPolicyEvaluation:
    return OverallPolicyEvaluation(
        dispute_id="PP-R-NKI-10193390",
        overall_decision=DecisionType.BLOCK,
        factual_readiness=DecisionType.BLOCK,
        action_readiness=DecisionType.ALLOW,
        advisories=[],
        check_results=[
            PolicyCheckResult(
                decision=DecisionType.BLOCK,
                rule_identifier="RULE_DELIVERY_PROOF",
                explanation="Carrier tracking shows LABEL_CREATED only. Delivery unverified.",
                violated_invariants=["LABEL_CREATED"],
            )
        ],
        summary="Factual claims blocked: carrier tracking shows LABEL_CREATED.",
        evaluated_at=datetime(2026, 11, 3, 12, 0, 0, tzinfo=timezone.utc),
    )


# ============================================================================
# 1. Approval Models & Cryptographic Token Security
# ============================================================================

def test_approval_service_token_generation_and_verification(secret_key, valid_dispute_case, approved_policy_evaluation):
    service = ApprovalService(secret_key=secret_key)
    payload = {"evidences": [{"evidence_type": "PROOF_OF_FULFILLMENT"}]}

    req = service.create_approval_request(
        dispute=valid_dispute_case,
        policy_evaluation=approved_policy_evaluation,
        proposed_payload=payload,
        ttl_seconds=3600,
    )

    assert req.approval_id.startswith("appr_")
    assert req.dispute_id == valid_dispute_case.dispute_id
    assert req.token is not None
    assert req.expires_at > datetime.now(timezone.utc)

    # Valid token verification succeeds
    verified = service.verify_token(
        token=req.token,
        dispute_id=valid_dispute_case.dispute_id,
        payload=payload,
    )
    assert verified is True


def test_approval_service_detects_payload_tampering(secret_key, valid_dispute_case, approved_policy_evaluation):
    service = ApprovalService(secret_key=secret_key)
    original_payload = {"evidences": [{"evidence_type": "PROOF_OF_FULFILLMENT"}]}

    req = service.create_approval_request(
        dispute=valid_dispute_case,
        policy_evaluation=approved_policy_evaluation,
        proposed_payload=original_payload,
    )

    tampered_payload = {"evidences": [{"evidence_type": "PROOF_OF_FULFILLMENT", "notes": "HACKED NOTE"}]}

    with pytest.raises(PayloadTamperedError) as exc_info:
        service.verify_token(
            token=req.token,
            dispute_id=valid_dispute_case.dispute_id,
            payload=tampered_payload,
        )
    assert "Payload integrity verification failed" in str(exc_info.value)


def test_approval_service_detects_token_expiration(secret_key, valid_dispute_case, approved_policy_evaluation):
    service = ApprovalService(secret_key=secret_key)
    payload = {"evidences": [{"evidence_type": "PROOF_OF_FULFILLMENT"}]}

    # Negative TTL creates an immediately expired token
    req = service.create_approval_request(
        dispute=valid_dispute_case,
        policy_evaluation=approved_policy_evaluation,
        proposed_payload=payload,
        ttl_seconds=-10,
    )

    with pytest.raises(TokenExpiredError) as exc_info:
        service.verify_token(
            token=req.token,
            dispute_id=valid_dispute_case.dispute_id,
            payload=payload,
        )
    assert "Approval token has expired" in str(exc_info.value)


def test_approval_service_detects_invalid_signature_or_key(secret_key, valid_dispute_case, approved_policy_evaluation):
    service1 = ApprovalService(secret_key=secret_key)
    service2 = ApprovalService(secret_key="completely-different-secret-key-32chars")
    payload = {"evidences": [{"evidence_type": "PROOF_OF_FULFILLMENT"}]}

    req = service1.create_approval_request(
        dispute=valid_dispute_case,
        policy_evaluation=approved_policy_evaluation,
        proposed_payload=payload,
    )

    with pytest.raises(InvalidSignatureError):
        service2.verify_token(
            token=req.token,
            dispute_id=valid_dispute_case.dispute_id,
            payload=payload,
        )


def test_approval_service_records_merchant_decision(secret_key, valid_dispute_case, approved_policy_evaluation):
    service = ApprovalService(secret_key=secret_key)
    payload = {"evidences": [{"evidence_type": "PROOF_OF_FULFILLMENT"}]}

    req = service.create_approval_request(
        dispute=valid_dispute_case,
        policy_evaluation=approved_policy_evaluation,
        proposed_payload=payload,
    )

    record = service.record_approval(
        request=req,
        merchant_user_id="merchant_admin_1",
        decision=ApprovalDecision.APPROVE,
        client_ip="192.168.1.100",
    )

    assert record.decision == ApprovalDecision.APPROVE
    assert record.merchant_user_id == "merchant_admin_1"
    assert record.dispute_id == valid_dispute_case.dispute_id
    assert record.is_approved() is True


# ============================================================================
# 2. Human Summary Generation
# ============================================================================

def test_human_summary_generation_contains_critical_sections(secret_key, valid_dispute_case, reconciled_bundle, approved_policy_evaluation):
    service = ApprovalService(secret_key=secret_key)
    summary = service.generate_human_summary(
        dispute=valid_dispute_case,
        bundle=reconciled_bundle,
        evaluation=approved_policy_evaluation,
    )

    assert "DISPUTE REVIEW & EVIDENCE AUTHORIZATION" in summary
    assert "Dispute ID: PP-R-NKI-10193390" in summary
    assert "Reason: MERCHANDISE_OR_SERVICE_NOT_RECEIVED" in summary
    assert "Amount: 25.00 USD" in summary
    assert "Tracking Number: 9400111899223197428490" in summary
    assert "Carrier: USPS" in summary
    assert "Status: DELIVERED" in summary
    assert "Decision: ALLOW" in summary
    assert "Recommendation:" in summary


# ============================================================================
# 3. PayPal Evidence Payload Formatter
# ============================================================================

def test_evidence_payload_formatter_standard_fulfillment(reconciled_bundle):
    formatter = EvidencePayloadFormatter()
    payload = formatter.format_fulfillment_evidence(
        bundle=reconciled_bundle,
        notes="Package verified delivered to recipient destination postal code 95131.",
    )

    assert "evidences" in payload
    assert len(payload["evidences"]) == 1
    evidence = payload["evidences"][0]
    assert evidence["evidence_type"] == "PROOF_OF_FULFILLMENT"
    assert "evidence_info" in evidence
    tracking = evidence["evidence_info"]["tracking_info"][0]
    assert tracking["carrier_name"] == "USPS"
    assert tracking["tracking_number"] == "9400111899223197428490"
    assert "postal code 95131" in evidence["notes"]


def test_evidence_payload_formatter_other_carrier_mapping(reconciled_bundle, valid_shipment):
    # Set an unrecognized carrier
    valid_shipment.carrier_name = "BlueDartExpress"
    formatter = EvidencePayloadFormatter()
    payload = formatter.format_fulfillment_evidence(bundle=reconciled_bundle)

    evidence = payload["evidences"][0]
    tracking = evidence["evidence_info"]["tracking_info"][0]
    assert tracking["carrier_name"] == "OTHER"
    assert tracking["carrier_name_other"] == "BlueDartExpress"


# ============================================================================
# 4. Pre-Submission Policy Refusal Barrier
# ============================================================================

def test_dispatcher_refuses_when_policy_blocks(secret_key, valid_dispute_case, reconciled_bundle, blocked_policy_evaluation):
    service = ApprovalService(secret_key=secret_key)
    dispatcher = EvidenceDispatcher(approval_service=service)

    # Even if merchant mistakenly approved it, dispatcher must refuse
    req = service.create_approval_request(
        dispute=valid_dispute_case,
        policy_evaluation=blocked_policy_evaluation,
        proposed_payload={"evidences": []},
    )
    record = service.record_approval(
        request=req,
        merchant_user_id="merchant_admin",
        decision=ApprovalDecision.APPROVE,
    )

    with pytest.raises(SubmissionBlockedError) as exc_info:
        dispatcher.dispatch_evidence(
            dispute=valid_dispute_case,
            bundle=reconciled_bundle,
            evaluation=blocked_policy_evaluation,
            approval_record=record,
        )
    assert "Policy engine refusal barrier blocked submission" in str(exc_info.value)
    assert "RULE_DELIVERY_PROOF" in str(exc_info.value)


# ============================================================================
# 5. Merchant Approval Verification Gate
# ============================================================================

def test_dispatcher_refuses_when_approval_record_missing(valid_dispute_case, reconciled_bundle, approved_policy_evaluation):
    dispatcher = EvidenceDispatcher(approval_service=ApprovalService("test-key"))

    with pytest.raises(MerchantApprovalRequiredError) as exc_info:
        dispatcher.dispatch_evidence(
            dispute=valid_dispute_case,
            bundle=reconciled_bundle,
            evaluation=approved_policy_evaluation,
            approval_record=None,
        )
    assert "Merchant approval is strictly required" in str(exc_info.value)


def test_dispatcher_refuses_when_approval_rejected(secret_key, valid_dispute_case, reconciled_bundle, approved_policy_evaluation):
    service = ApprovalService(secret_key=secret_key)
    dispatcher = EvidenceDispatcher(approval_service=service)

    req = service.create_approval_request(
        dispute=valid_dispute_case,
        policy_evaluation=approved_policy_evaluation,
        proposed_payload={"evidences": []},
    )
    record = service.record_approval(
        request=req,
        merchant_user_id="merchant_admin",
        decision=ApprovalDecision.REJECT,
        rejection_reason="Waiting for carrier claims investigation",
    )

    with pytest.raises(SubmissionRejectedError) as exc_info:
        dispatcher.dispatch_evidence(
            dispute=valid_dispute_case,
            bundle=reconciled_bundle,
            evaluation=approved_policy_evaluation,
            approval_record=record,
        )
    assert "Merchant rejected evidence submission" in str(exc_info.value)


# ============================================================================
# 6. Idempotency Lock
# ============================================================================

def test_dispatcher_idempotency_prevents_duplicate_dispatch(secret_key, valid_dispute_case, reconciled_bundle, approved_policy_evaluation):
    service = ApprovalService(secret_key=secret_key)
    mock_client = MagicMock()
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"status": "SUCCESS"}
    mock_resp.headers = {"Paypal-Debug-Id": "pp_corr_12345"}
    mock_client.post.return_value = mock_resp

    dispatcher = EvidenceDispatcher(approval_service=service, http_client=mock_client)

    payload = EvidencePayloadFormatter().format_fulfillment_evidence(bundle=reconciled_bundle)
    req = service.create_approval_request(
        dispute=valid_dispute_case,
        policy_evaluation=approved_policy_evaluation,
        proposed_payload=payload,
    )
    record = service.record_approval(
        request=req,
        merchant_user_id="merchant_admin",
        decision=ApprovalDecision.APPROVE,
    )

    # First dispatch succeeds
    res1 = dispatcher.dispatch_evidence(
        dispute=valid_dispute_case,
        bundle=reconciled_bundle,
        evaluation=approved_policy_evaluation,
        approval_record=record,
        idempotency_key="idemp_key_1",
    )
    assert res1.success is True
    assert res1.correlation_id == "pp_corr_12345"

    # Second dispatch with same dispute raises DuplicateSubmissionError
    with pytest.raises(DuplicateSubmissionError) as exc_info:
        dispatcher.dispatch_evidence(
            dispute=valid_dispute_case,
            bundle=reconciled_bundle,
            evaluation=approved_policy_evaluation,
            approval_record=record,
            idempotency_key="idemp_key_2",
        )
    assert "already in progress or completed" in str(exc_info.value)


# ============================================================================
# 7. Mocked PayPal Client Dispatch & Error Handling
# ============================================================================

def test_dispatcher_paypal_server_error_handling(secret_key, valid_dispute_case, reconciled_bundle, approved_policy_evaluation):
    service = ApprovalService(secret_key=secret_key)
    mock_client = MagicMock()
    mock_resp = MagicMock()
    mock_resp.status_code = 500
    mock_resp.text = "Internal Server Error"
    mock_resp.json.side_effect = ValueError("Non-JSON error response")
    mock_resp.headers = {"Paypal-Debug-Id": "pp_err_9999"}
    mock_client.post.return_value = mock_resp

    dispatcher = EvidenceDispatcher(approval_service=service, http_client=mock_client)

    payload = EvidencePayloadFormatter().format_fulfillment_evidence(bundle=reconciled_bundle)
    req = service.create_approval_request(
        dispute=valid_dispute_case,
        policy_evaluation=approved_policy_evaluation,
        proposed_payload=payload,
    )
    record = service.record_approval(
        request=req,
        merchant_user_id="merchant_admin",
        decision=ApprovalDecision.APPROVE,
    )

    res = dispatcher.dispatch_evidence(
        dispute=valid_dispute_case,
        bundle=reconciled_bundle,
        evaluation=approved_policy_evaluation,
        approval_record=record,
        idempotency_key="idemp_err_test",
    )

    assert res.success is False
    assert res.paypal_status_code == 500
    assert res.correlation_id == "pp_err_9999"


# ============================================================================
# 8. Append-Only Cryptographic Audit Ledger
# ============================================================================

def test_audit_logger_hash_chain_and_verification(tmp_path):
    log_file = tmp_path / "audit_trail.jsonl"
    logger = AuditLogger(storage_path=log_file)

    # Log sequence of events
    e1 = logger.log_event(
        event_type=AuditEventType.DISPUTE_INGESTED,
        dispute_id="PP-R-NKI-10193390",
        actor="SYSTEM",
        payload={"reason": "INR", "amount": "25.00"},
    )
    assert e1.parent_hash == "GENESIS"
    assert len(e1.event_hash) == 64

    e2 = logger.log_event(
        event_type=AuditEventType.POLICY_EVALUATED,
        dispute_id="PP-R-NKI-10193390",
        actor="POLICY_ENGINE",
        payload={"decision": "ALLOW"},
    )
    assert e2.parent_hash == e1.event_hash

    e3 = logger.log_event(
        event_type=AuditEventType.APPROVAL_GRANTED,
        dispute_id="PP-R-NKI-10193390",
        actor="merchant_admin_1",
        payload={"approval_id": "appr_123"},
    )
    assert e3.parent_hash == e2.event_hash

    # Verify chain integrity
    assert logger.verify_chain_integrity() is True


def test_audit_logger_detects_tampering(tmp_path):
    log_file = tmp_path / "audit_trail.jsonl"
    logger = AuditLogger(storage_path=log_file)

    logger.log_event(
        event_type=AuditEventType.DISPUTE_INGESTED,
        dispute_id="PP-R-NKI-10193390",
        actor="SYSTEM",
        payload={"reason": "INR"},
    )
    logger.log_event(
        event_type=AuditEventType.APPROVAL_GRANTED,
        dispute_id="PP-R-NKI-10193390",
        actor="merchant_admin_1",
        payload={"approval_id": "appr_1"},
    )

    # Tamper with the log file
    lines = log_file.read_text(encoding="utf-8").strip().split("\n")
    record0 = json.loads(lines[0])
    record0["payload"]["reason"] = "SNAD"  # Maliciously modify recorded payload
    lines[0] = json.dumps(record0)
    log_file.write_text("\n".join(lines) + "\n", encoding="utf-8")

    # Chain verification must fail
    with pytest.raises(AuditVerificationError) as exc_info:
        logger.verify_chain_integrity()
    assert "Audit chain verification failed" in str(exc_info.value)


# ============================================================================
# 9. Additional Edge Cases & Robustness
# ============================================================================

def test_approval_service_token_dispute_mismatch(secret_key, valid_dispute_case, approved_policy_evaluation):
    service = ApprovalService(secret_key=secret_key)
    payload = {"evidences": []}
    req = service.create_approval_request(
        dispute=valid_dispute_case,
        policy_evaluation=approved_policy_evaluation,
        proposed_payload=payload,
    )

    with pytest.raises(Exception) as exc_info:
        service.verify_token(token=req.token, dispute_id="PP-R-DIFFERENT-999", payload=payload)
    assert "Dispute mismatch" in str(exc_info.value)


def test_approval_service_token_malformed_formats(secret_key):
    service = ApprovalService(secret_key=secret_key)
    with pytest.raises(InvalidSignatureError) as exc1:
        service.verify_token(token="too.few.parts", dispute_id="D1", payload={})
    assert "Malformed approval token" in str(exc1.value)

    with pytest.raises(InvalidSignatureError) as exc2:
        service.verify_token(token="D1.nonce.notanint.hash.sig", dispute_id="D1", payload={})
    assert "invalid timestamp format" in str(exc2.value)


def test_dispatcher_hateoas_missing_action(secret_key, valid_dispute_case, reconciled_bundle, approved_policy_evaluation):
    service = ApprovalService(secret_key=secret_key)
    valid_dispute_case.available_hateoas_actions = []  # No provide_evidence action
    dispatcher = EvidenceDispatcher(approval_service=service)

    payload = EvidencePayloadFormatter().format_fulfillment_evidence(bundle=reconciled_bundle)
    req = service.create_approval_request(
        dispute=valid_dispute_case,
        policy_evaluation=approved_policy_evaluation,
        proposed_payload=payload,
    )
    record = service.record_approval(
        request=req,
        merchant_user_id="merchant_admin",
        decision=ApprovalDecision.APPROVE,
    )

    with pytest.raises(SubmissionBlockedError) as exc_info:
        dispatcher.dispatch_evidence(
            dispute=valid_dispute_case,
            bundle=reconciled_bundle,
            evaluation=approved_policy_evaluation,
            approval_record=record,
        )
    assert "does not expose an eligible 'provide_evidence' HATEOAS action" in str(exc_info.value)


def test_dispatcher_hateoas_insecure_http_rejected(secret_key, valid_dispute_case, reconciled_bundle, approved_policy_evaluation):
    service = ApprovalService(secret_key=secret_key)
    valid_dispute_case.available_hateoas_actions = [
        HATEOASLink(
            href="http://api-m.sandbox.paypal.com/v1/customer/disputes/PP-R-NKI-10193390/provide-evidence",
            rel="provide_evidence",
            method="POST",
        )
    ]
    dispatcher = EvidenceDispatcher(approval_service=service, allow_insecure_http=False)

    payload = EvidencePayloadFormatter().format_fulfillment_evidence(bundle=reconciled_bundle)
    req = service.create_approval_request(
        dispute=valid_dispute_case,
        policy_evaluation=approved_policy_evaluation,
        proposed_payload=payload,
    )
    record = service.record_approval(
        request=req,
        merchant_user_id="merchant_admin",
        decision=ApprovalDecision.APPROVE,
    )

    with pytest.raises(SubmissionBlockedError) as exc_info:
        dispatcher.dispatch_evidence(
            dispute=valid_dispute_case,
            bundle=reconciled_bundle,
            evaluation=approved_policy_evaluation,
            approval_record=record,
        )
    assert "Insecure scheme" in str(exc_info.value)


def test_dispatcher_hateoas_untrusted_host_rejected(secret_key, valid_dispute_case, reconciled_bundle, approved_policy_evaluation):
    service = ApprovalService(secret_key=secret_key)
    valid_dispute_case.available_hateoas_actions = [
        HATEOASLink(
            href="https://phishing.evil-paypal.com/v1/customer/disputes/PP-R-NKI-10193390/provide-evidence",
            rel="provide_evidence",
            method="POST",
        )
    ]
    dispatcher = EvidenceDispatcher(approval_service=service)

    payload = EvidencePayloadFormatter().format_fulfillment_evidence(bundle=reconciled_bundle)
    req = service.create_approval_request(
        dispute=valid_dispute_case,
        policy_evaluation=approved_policy_evaluation,
        proposed_payload=payload,
    )
    record = service.record_approval(
        request=req,
        merchant_user_id="merchant_admin",
        decision=ApprovalDecision.APPROVE,
    )

    with pytest.raises(SubmissionBlockedError) as exc_info:
        dispatcher.dispatch_evidence(
            dispute=valid_dispute_case,
            bundle=reconciled_bundle,
            evaluation=approved_policy_evaluation,
            approval_record=record,
        )
    assert "Untrusted host" in str(exc_info.value)


def test_dispatcher_http_network_exception_handling(secret_key, valid_dispute_case, reconciled_bundle, approved_policy_evaluation):
    service = ApprovalService(secret_key=secret_key)
    mock_client = MagicMock()
    mock_client.post.side_effect = ConnectionError("DNS resolution failed")

    dispatcher = EvidenceDispatcher(approval_service=service, http_client=mock_client)

    payload = EvidencePayloadFormatter().format_fulfillment_evidence(bundle=reconciled_bundle)
    req = service.create_approval_request(
        dispute=valid_dispute_case,
        policy_evaluation=approved_policy_evaluation,
        proposed_payload=payload,
    )
    record = service.record_approval(
        request=req,
        merchant_user_id="merchant_admin",
        decision=ApprovalDecision.APPROVE,
    )

    res = dispatcher.dispatch_evidence(
        dispute=valid_dispute_case,
        bundle=reconciled_bundle,
        evaluation=approved_policy_evaluation,
        approval_record=record,
        idempotency_key="idemp_conn_err",
    )

    assert res.success is False
    assert "DNS resolution failed" in res.error_message


def test_evidence_payload_formatter_no_shipments(reconciled_bundle):
    reconciled_bundle.matched_shipments = []
    formatter = EvidencePayloadFormatter()
    payload = formatter.format_fulfillment_evidence(bundle=reconciled_bundle)
    assert len(payload["evidences"]) == 1
    assert "evidence_info" not in payload["evidences"][0]
    assert "Order fulfilled and reconciled" in payload["evidences"][0]["notes"]


def test_audit_logger_reloading_and_filtering(tmp_path):
    log_file = tmp_path / "audit_trail.jsonl"
    logger1 = AuditLogger(storage_path=log_file)
    logger1.log_event(AuditEventType.DISPUTE_INGESTED, "DISP_A", "ACTOR1", {"k": "v1"})
    logger1.log_event(AuditEventType.DISPUTE_INGESTED, "DISP_B", "ACTOR2", {"k": "v2"})

    # Reload into fresh logger instance
    logger2 = AuditLogger(storage_path=log_file)
    assert len(logger2.get_events()) == 2
    assert len(logger2.get_events(dispute_id="DISP_A")) == 1
    assert logger2.get_events(dispute_id="DISP_A")[0].dispute_id == "DISP_A"
    assert logger2.verify_chain_integrity() is True


def test_audit_logger_corrupt_file_handling(tmp_path):
    log_file = tmp_path / "corrupt_trail.jsonl"
    log_file.write_text("NOT_VALID_JSON\n", encoding="utf-8")
    with pytest.raises(AuditVerificationError) as exc_info:
        AuditLogger(storage_path=log_file)
    assert "Corrupt JSON" in str(exc_info.value)

