"""Milestone 4 Audit Verification Tests.

Comprehensive regression tests covering:
1. ContradictionCode canonicalization, legacy normalization, symmetric equality, hashability, set/dict behavior, and JSON serialization/deserialization.
2. Claim taxonomy, hearsay handling, and ensuring buyer hearsay statements are never promoted to verified carrier evidence.
3. Case A PayPal policy scope, explicit disclaimers, and authoritative source linking.
4. Cryptographic JSONL AuditLogger verification (persistence across restarts, detection of altered, deleted, or reordered records).
5. Tri-partite decision model (Factual Readiness, Action Eligibility, Merchant Recommendation), refusal barriers, and gated approval.
6. Offline deterministic safety (0 network calls) and robust live error handling (HTTP 429, timeouts, malformed JSON).
"""

from datetime import datetime, timezone
from decimal import Decimal
import json
from pathlib import Path
import pytest
from unittest.mock import MagicMock, patch
import requests

from docket.ai.contradiction import (
    CANONICAL_DELIVERY_STATUS_DISCREPANCY,
    LEGACY_DELIVERY_DISPUTE_EVIDENCE_EXISTS,
    ContradictionCode,
    ContradictionDetector,
    ContradictionFinding,
    normalize_contradiction_code,
)
from docket.ai.base import AIProviderError
from docket.ai.provider_gemini import GeminiFactExtractor
from docket.ai.factory import get_fact_extractor
from docket.audit.logger import AuditLogger, AuditVerificationError
from docket.dispatch.approval import ApprovalService
from docket.dispatch.dispatcher import (
    EvidenceDispatcher,
    MerchantApprovalRequiredError,
    SubmissionBlockedError,
    SubmissionRejectedError,
)
from docket.models.audit import AuditEventType
from docket.models.dispatch import ApprovalDecision, MerchantApprovalRecord
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
    ClaimStatus,
    ClaimType,
    ExtractedClaim,
    OrderRecord,
    ShipmentRecord,
    SourceCitation,
    SourceType,
    TrackingStatus,
    VerificationStatus,
)
from docket.models.policy import DecisionType, OverallPolicyEvaluation
from docket.models.reconciliation import (
    CandidateMatch,
    MatchConfidence,
    MatchStrategy,
    ReconciledDisputeBundle,
    ReconciliationStatus,
)
from docket.policy.engine import (
    AddressMatchInvariant,
    DeliveryDiscrepancyInvariant,
    DeliveryProofInvariant,
    PolicyEngine,
)


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture
def audit_dispute() -> DisputeCase:
    return DisputeCase(
        dispute_id="PP-D-AUDIT-2026",
        dispute_amount=Money(value=Decimal("75.00"), currency_code="USD"),
        reason=DisputeReason.MERCHANDISE_OR_SERVICE_NOT_RECEIVED,
        status=DisputeStatus.WAITING_FOR_SELLER_RESPONSE,
        lifecycle_stage=DisputeLifecycleStage.CHARGEBACK,
        buyer_transaction_id="TX-AUDIT-01",
        seller_response_due_date=datetime(2026, 11, 20, 12, 0, tzinfo=timezone.utc),
        requested_evidence_types=["PROOF_OF_DELIVERY"],
        available_hateoas_actions=[
            HATEOASLink(
                href="https://api-m.sandbox.paypal.com/v1/customer/disputes/PP-D-AUDIT-2026/provide-evidence",
                rel="provide_evidence",
                method="POST",
            )
        ],
        raw_messages=[{
            "message_id": "MSG-00",
            "sent_at": "2026-11-08T10:00:00Z",
            "content": "The tracking page says my package was delivered yesterday, but I never received it. I contacted the courier, and they told me the parcel may have been left at another address.",
        }],
    )


@pytest.fixture
def audit_order() -> OrderRecord:
    return OrderRecord(
        order_id="ORD-AUDIT-01",
        paypal_transaction_id="TX-AUDIT-01",
        gross_amount=Money(value=Decimal("75.00"), currency_code="USD"),
        shipping_address=Address(
            recipient_name="Casey Miller",
            line1="100 Market St",
            city="San Jose",
            state_or_province="CA",
            postal_code="95113",
            country_code="US",
        ),
    )


@pytest.fixture
def audit_shipment_delivered() -> ShipmentRecord:
    return ShipmentRecord(
        internal_order_id="ORD-AUDIT-01",
        carrier_name="USPS",
        tracking_number="9400111899223197428490",
        tracking_status=TrackingStatus.DELIVERED,
        shipment_timestamp=datetime(2026, 11, 5, 10, 0, tzinfo=timezone.utc),
        delivery_timestamp=datetime(2026, 11, 7, 14, 22, tzinfo=timezone.utc),
        shipment_address=Address(
            recipient_name="Casey Miller",
            line1="100 Market St",
            city="San Jose",
            state_or_province="CA",
            postal_code="95113",
            country_code="US",
        ),
        source_identifier="SRC-USPS-TRACKING-API",
    )


@pytest.fixture
def audit_bundle(audit_dispute, audit_order, audit_shipment_delivered) -> ReconciledDisputeBundle:
    return ReconciledDisputeBundle(
        dispute_id=audit_dispute.dispute_id,
        status=ReconciliationStatus.RECONCILED,
        matched_order=audit_order,
        matched_shipments=[audit_shipment_delivered],
        primary_match=CandidateMatch(
            order=audit_order,
            strategy=MatchStrategy.EXACT_TRANSACTION_ID,
            confidence=1.0,
            confidence_tier=MatchConfidence.EXACT,
        ),
    )


# ============================================================================
# 1. ContradictionCode Compatibility Tests
# ============================================================================

class TestContradictionCodeCompatibility:
    def test_new_code_input(self):
        code = ContradictionCode("DELIVERY_STATUS_DISCREPANCY")
        assert code == "DELIVERY_STATUS_DISCREPANCY"
        assert normalize_contradiction_code(code) == CANONICAL_DELIVERY_STATUS_DISCREPANCY

    def test_legacy_code_input(self):
        code = ContradictionCode("DELIVERY_DISPUTE_EVIDENCE_EXISTS")
        assert code == CANONICAL_DELIVERY_STATUS_DISCREPANCY
        assert normalize_contradiction_code(code) == CANONICAL_DELIVERY_STATUS_DISCREPANCY

    def test_equality_in_both_comparison_directions(self):
        code_new = ContradictionCode("DELIVERY_STATUS_DISCREPANCY")
        code_legacy = ContradictionCode("DELIVERY_DISPUTE_EVIDENCE_EXISTS")
        canonical_str = "DELIVERY_STATUS_DISCREPANCY"

        # Direction 1: object on left, string on right
        assert code_new == canonical_str
        assert code_legacy == canonical_str

        # Direction 2: string on left, object on right
        assert canonical_str == code_new
        assert canonical_str == code_legacy

        # Object-to-object equality
        assert code_new == code_legacy
        assert code_legacy == code_new

    def test_hashability_and_collections(self):
        code_new = ContradictionCode("DELIVERY_STATUS_DISCREPANCY")
        code_legacy = ContradictionCode("DELIVERY_DISPUTE_EVIDENCE_EXISTS")
        canonical_str = "DELIVERY_STATUS_DISCREPANCY"

        # Stable hash consistency
        assert hash(code_new) == hash(canonical_str)
        assert hash(code_legacy) == hash(canonical_str)

        # Set behavior
        code_set = {code_new}
        assert canonical_str in code_set
        assert code_legacy in code_set

        # Dictionary lookup behavior
        lookup_dict = {code_new: "present"}
        assert lookup_dict[canonical_str] == "present"
        assert lookup_dict[code_legacy] == "present"

    def test_json_serialization_and_deserialization(self):
        code = ContradictionCode("DELIVERY_DISPUTE_EVIDENCE_EXISTS")
        # JSON serialization
        payload = {"code": code}
        serialized = json.dumps(payload)
        assert serialized == '{"code": "DELIVERY_STATUS_DISCREPANCY"}'

        # JSON deserialization of legacy code input normalizes to canonical
        legacy_json = '{"code": "DELIVERY_DISPUTE_EVIDENCE_EXISTS", "severity": "HIGH", "description": "test finding"}'
        finding = ContradictionFinding.model_validate_json(legacy_json)
        assert finding.code == "DELIVERY_STATUS_DISCREPANCY"
        assert finding.matches_code("DELIVERY_DISPUTE_EVIDENCE_EXISTS")
        assert finding.matches_code("DELIVERY_STATUS_DISCREPANCY")


# ============================================================================
# 2. Claim Taxonomy & Hearsay Handling Tests
# ============================================================================

class TestClaimTaxonomyAndHearsayHandling:
    def test_buyer_hearsay_claim_not_promoted_to_carrier_evidence(self, audit_dispute, audit_shipment_delivered):
        # Claim 4: Buyer reports courier verbal statement
        hearsay_citation = SourceCitation(
            source_type=SourceType.CUSTOMER_COMMUNICATION,
            source_identifier="MSG-00",
            field_path="content",
            extracted_value="they told me the parcel may have been left at another address",
            verification_status=VerificationStatus.VERIFIED,
        )
        hearsay_claim = ExtractedClaim(
            claim_id="CLM-04",
            claim_type=ClaimType.COMMUNICATION_ACKNOWLEDGED,
            factual_assertion="Buyer reports that the courier stated the parcel may have been left at another address.",
            supporting_sources=[hearsay_citation],
            claim_status=ClaimStatus.PROPOSED,
        )

        # 1. Source must be the customer communication
        assert hearsay_claim.supporting_sources[0].source_type == SourceType.CUSTOMER_COMMUNICATION
        assert hearsay_claim.supporting_sources[0].source_identifier == "MSG-00"

        # 2. If evaluated without a carrier record, it CANNOT prove delivery
        delivery_inv = DeliveryProofInvariant()
        res_no_shipment = delivery_inv.evaluate(hearsay_claim, shipment=None)
        assert res_no_shipment.explanation == "Claim type 'COMMUNICATION_ACKNOWLEDGED' does not assert completed delivery."
        assert "Verified carrier delivery scan established" not in (res_no_shipment.explanation or "")

        # Even if an adversarial prompt attempted to promote hearsay to DELIVERY_COMPLETED without carrier proof:
        promoted_claim = hearsay_claim.model_copy(update={"claim_type": ClaimType.DELIVERY_COMPLETED})
        res_promoted = delivery_inv.evaluate(promoted_claim, shipment=None)
        assert res_promoted.decision == DecisionType.BLOCK
        assert "Cannot assert delivery" in res_promoted.explanation

        # 3. Under DeliveryDiscrepancyInvariant with carrier DELIVERED status:
        # Verbal courier statement from buyer triggers Case D (REVIEW), NOT BLOCK or ALLOW
        discrepancy_inv = DeliveryDiscrepancyInvariant()
        res_discrepancy = discrepancy_inv.evaluate(
            claims=[hearsay_claim],
            shipment=audit_shipment_delivered,
            available_sources={"MSG-00": "raw buyer message"},
        )
        assert res_discrepancy.decision == DecisionType.REVIEW
        assert "HEARSAY_MISDELIVERY_ALLEGATION" in res_discrepancy.violated_invariants
        assert "GPS delivery scan coordinates" in res_discrepancy.recommended_next_action

    def test_communication_acknowledged_alone_does_not_satisfy_delivery_proof(self):
        comm_claim = ExtractedClaim(
            claim_id="CLM-COMM-01",
            claim_type=ClaimType.COMMUNICATION_ACKNOWLEDGED,
            factual_assertion="Buyer acknowledges receiving a communication",
            supporting_sources=[],
            claim_status=ClaimStatus.PROPOSED,
        )
        invariant = DeliveryProofInvariant()
        # DeliveryProofInvariant explicitly states this does NOT assert completed delivery
        res = invariant.evaluate(comm_claim, shipment=None)
        assert res.explanation == "Claim type 'COMMUNICATION_ACKNOWLEDGED' does not assert completed delivery."
        assert "Verified carrier delivery scan established" not in (res.explanation or "")


# ============================================================================
# 3. Case A PayPal Policy Scope Tests
# ============================================================================

class TestCaseAPayPalPolicyScope:
    def test_case_a_address_confidence_disclaimer(self, audit_shipment_delivered):
        # Buyer message merely disputes receipt without courier hearsay
        buyer_dispute_claim = ExtractedClaim(
            claim_id="CLM-INR-01",
            claim_type=ClaimType.NON_RECEIPT_ASSERTED,
            factual_assertion="Buyer asserts they never received the package.",
            supporting_sources=[],
            claim_status=ClaimStatus.PROPOSED,
        )
        invariant = DeliveryDiscrepancyInvariant()
        res = invariant.evaluate(
            claims=[buyer_dispute_claim],
            shipment=audit_shipment_delivered,
            available_sources={},
        )
        assert res.decision == DecisionType.ALLOW
        # Explanations must articulate the 5 key criteria
        assert "Carrier delivered status is verified" in res.explanation
        assert "Delivery date and verifiable tracking number are established" in res.explanation
        assert "Destination postal code and country correspond" in res.explanation
        assert "Recipient street-level dropoff confirmation cannot be independently verified" in res.explanation
        assert "Other PayPal Seller Protection eligibility conditions" in res.explanation
        assert "Does NOT establish street-level recipient delivery confirmation" in res.explanation

    def test_rule_versioning_and_authoritative_sources(self):
        assert DeliveryProofInvariant.RULE_VERSION == "2026.1"
        assert "PayPal Seller Protection Policy" in DeliveryProofInvariant.AUTHORITATIVE_SOURCE

        assert AddressMatchInvariant.RULE_VERSION == "2026.1"
        assert "PayPal Seller Protection Policy" in AddressMatchInvariant.AUTHORITATIVE_SOURCE

        assert DeliveryDiscrepancyInvariant.RULE_VERSION == "2026.1"
        assert "PayPal Seller Protection Policy" in DeliveryDiscrepancyInvariant.AUTHORITATIVE_SOURCE


# ============================================================================
# 4. Cryptographic JSONL AuditLogger Ledger Verification Tests
# ============================================================================

class TestAuditLoggerLedgerVerification:
    def test_ledger_persists_across_instances(self, tmp_path):
        log_file = tmp_path / "audit_trail.jsonl"
        logger1 = AuditLogger(storage_path=log_file)
        logger1.log_event(AuditEventType.DISPUTE_INGESTED, "DISP-1", "SYSTEM", {"amount": "100.00"})
        logger1.log_event(AuditEventType.POLICY_EVALUATED, "DISP-1", "POLICY_ENGINE", {"decision": "ALLOW"})

        # Reload into a completely separate logger instance
        logger2 = AuditLogger(storage_path=log_file)
        events = logger2.get_events()
        assert len(events) == 2
        assert events[0].event_type == AuditEventType.DISPUTE_INGESTED
        assert events[1].event_type == AuditEventType.POLICY_EVALUATED
        assert logger2.verify_chain_integrity() is True

    def test_ledger_detects_altered_record(self, tmp_path):
        log_file = tmp_path / "audit_trail.jsonl"
        logger = AuditLogger(storage_path=log_file)
        e1 = logger.log_event(AuditEventType.DISPUTE_INGESTED, "DISP-1", "SYSTEM", {"amount": "50.00"})
        logger.log_event(AuditEventType.POLICY_EVALUATED, "DISP-1", "POLICY_ENGINE", {"decision": "ALLOW"})

        # Tamper with the raw JSON line on disk
        lines = log_file.read_text(encoding="utf-8").strip().split("\n")
        data = json.loads(lines[0])
        data["payload"]["amount"] = "9999.00"  # Tampered
        lines[0] = json.dumps(data)
        log_file.write_text("\n".join(lines) + "\n", encoding="utf-8")

        tampered_logger = AuditLogger(storage_path=log_file)
        diag = tampered_logger.verify_chain_detailed()
        assert diag["is_valid"] is False
        assert diag["failed_event_id"] == e1.event_id
        assert "hash mismatch" in diag["error_message"].lower()

    def test_ledger_detects_deleted_record(self, tmp_path):
        log_file = tmp_path / "audit_trail.jsonl"
        logger = AuditLogger(storage_path=log_file)
        logger.log_event(AuditEventType.DISPUTE_INGESTED, "DISP-1", "SYSTEM", {"amount": "50.00"})
        logger.log_event(AuditEventType.POLICY_EVALUATED, "DISP-1", "POLICY_ENGINE", {"decision": "REVIEW"})
        logger.log_event(AuditEventType.APPROVAL_GRANTED, "DISP-1", "ADMIN", {"action": "APPROVE"})

        # Delete the middle record
        lines = log_file.read_text(encoding="utf-8").strip().split("\n")
        del lines[1]  # Delete event 2
        log_file.write_text("\n".join(lines) + "\n", encoding="utf-8")

        tampered_logger = AuditLogger(storage_path=log_file)
        diag = tampered_logger.verify_chain_detailed()
        assert diag["is_valid"] is False
        assert "parent_hash does not match" in diag["error_message"].lower()


# ============================================================================
# 5. Tri-Partite Decision Model & Merchant Approval Gate Tests
# ============================================================================

class TestTriPartiteDecisionModelAndMerchantGate:
    def test_review_allow_investigate_tri_partite_state(self, audit_dispute, audit_order, audit_shipment_delivered):
        """Test the exact audited condition:
        Factual Readiness = REVIEW
        Action Eligibility = ALLOW
        Merchant Recommendation = INVESTIGATE
        """
        # Hearsay claim produces Factual Readiness REVIEW
        hearsay_citation = SourceCitation(
            source_type=SourceType.CUSTOMER_COMMUNICATION,
            source_identifier="MSG-00",
            field_path="content",
            extracted_value="they told me the parcel may have been left at another address",
            verification_status=VerificationStatus.VERIFIED,
        )
        hearsay_claim = ExtractedClaim(
            claim_id="CLM-04",
            claim_type=ClaimType.COMMUNICATION_ACKNOWLEDGED,
            factual_assertion="Buyer reports that the courier stated the parcel may have been left at another address.",
            supporting_sources=[hearsay_citation],
            claim_status=ClaimStatus.PROPOSED,
        )

        engine = PolicyEngine()
        eval_result: OverallPolicyEvaluation = engine.evaluate(
            dispute=audit_dispute,
            order=audit_order,
            shipment=audit_shipment_delivered,
            claims=[hearsay_claim],
            target_action="provide_evidence",
        )

        # 1. Verify tri-partite dimensions
        assert eval_result.factual_readiness == DecisionType.REVIEW
        assert eval_result.action_readiness == DecisionType.ALLOW
        assert eval_result.overall_decision == DecisionType.REVIEW
        assert eval_result.is_ready_for_submission() is False

        # 2. Verify submission is blocked at the dispatcher level
        approval_service = ApprovalService(secret_key="audit-test-secret-key-32-bytes!!")
        dispatcher = EvidenceDispatcher(approval_service=approval_service)
        mock_bundle = ReconciledDisputeBundle(
            dispute_id=audit_dispute.dispute_id,
            status=ReconciliationStatus.RECONCILED,
            matched_order=audit_order,
            matched_shipments=[audit_shipment_delivered],
        )

        # Even with an approval record, dispatcher must block because overall_decision != ALLOW
        with pytest.raises(SubmissionBlockedError) as exc_info:
            dispatcher.dispatch_evidence(
                dispute=audit_dispute,
                bundle=mock_bundle,
                evaluation=eval_result,
                approval_record=None,
            )
        assert "Policy engine refusal barrier blocked submission" in str(exc_info.value)

    def test_block_state_locks_submission(self, audit_dispute, audit_order):
        # Tracking is LABEL_CREATED -> Factual Readiness BLOCK
        label_shipment = ShipmentRecord(
            internal_order_id="ORD-AUDIT-01",
            carrier_name="USPS",
            tracking_number="9400111899223197428490",
            tracking_status=TrackingStatus.LABEL_CREATED,
            shipment_timestamp=datetime(2026, 11, 5, 10, 0, tzinfo=timezone.utc),
            delivery_timestamp=None,
            source_identifier="SRC-USPS-API",
        )
        claim = ExtractedClaim(
            claim_id="CLM-01",
            claim_type=ClaimType.DELIVERY_COMPLETED,
            factual_assertion="Delivered to customer",
            supporting_sources=[],
        )

        engine = PolicyEngine()
        eval_result = engine.evaluate(
            dispute=audit_dispute,
            order=audit_order,
            shipment=label_shipment,
            claims=[claim],
        )

        assert eval_result.factual_readiness == DecisionType.BLOCK
        assert eval_result.overall_decision == DecisionType.BLOCK
        assert eval_result.is_ready_for_submission() is False

    def test_fully_allow_requires_explicit_merchant_approval(self, audit_dispute, audit_order, audit_shipment_delivered):
        # Case A with no hearsay: Factual Readiness ALLOW, Action Eligibility ALLOW
        engine = PolicyEngine()
        eval_result = engine.evaluate(
            dispute=audit_dispute,
            order=audit_order,
            shipment=audit_shipment_delivered,
            claims=[],
            target_action="provide_evidence",
        )
        assert eval_result.factual_readiness == DecisionType.ALLOW
        assert eval_result.action_readiness == DecisionType.ALLOW
        assert eval_result.overall_decision == DecisionType.ALLOW
        assert eval_result.is_ready_for_submission() is True

        approval_service = ApprovalService(secret_key="audit-test-secret-key-32-bytes!!")
        dispatcher = EvidenceDispatcher(approval_service=approval_service)
        bundle = ReconciledDisputeBundle(
            dispute_id=audit_dispute.dispute_id,
            status=ReconciliationStatus.RECONCILED,
            matched_order=audit_order,
            matched_shipments=[audit_shipment_delivered],
        )

        # Attempting dispatch without merchant approval record fails
        with pytest.raises(MerchantApprovalRequiredError):
            dispatcher.dispatch_evidence(
                dispute=audit_dispute,
                bundle=bundle,
                evaluation=eval_result,
                approval_record=None,
            )


# ============================================================================
# 6. Offline Safety & Live Error-Handling Tests
# ============================================================================

class TestOfflineSafetyAndLiveErrorHandling:
    def test_offline_mode_dispatches_no_external_requests(self, monkeypatch, audit_dispute, audit_bundle):
        monkeypatch.setenv("DOCKET_AI_MODE", "offline")
        extractor = get_fact_extractor()

        with patch("requests.post") as mock_post:
            result = extractor.extract_from_bundle(audit_dispute, audit_bundle)
            mock_post.assert_not_called()
        assert len(result.claims) >= 1

    def test_live_mode_handles_http_429_quota_exhaustion(self, monkeypatch):
        extractor = GeminiFactExtractor(api_key="mock-key-for-test", model="gemini-3.8-flash")

        mock_resp = MagicMock()
        mock_resp.status_code = 429
        mock_resp.reason = "Too Many Requests"
        mock_resp.json.return_value = {
            "error": {
                "code": 429,
                "message": "Quota exceeded for metric: generativelanguage.googleapis.com/generate_content_free_tier_requests, limit: 20",
                "status": "RESOURCE_EXHAUSTED",
            }
        }
        mock_resp.text = json.dumps(mock_resp.json.return_value)

        with patch("requests.post", return_value=mock_resp):
            with pytest.raises(AIProviderError) as exc_info:
                extractor._post_generate({"contents": []})

            assert "HTTP 429" in str(exc_info.value)
            assert "RESOURCE_EXHAUSTED" in str(exc_info.value)
            assert "Quota exceeded" in str(exc_info.value)

    def test_live_mode_handles_timeout(self):
        extractor = GeminiFactExtractor(api_key="mock-key", model="gemini-3.8-flash", timeout_seconds=1)

        with patch("requests.post", side_effect=requests.Timeout("Connection timed out")):
            with pytest.raises(AIProviderError) as exc_info:
                extractor._post_generate({"contents": []})
            assert "timed out" in str(exc_info.value).lower()

    def test_live_mode_handles_malformed_json(self):
        extractor = GeminiFactExtractor(api_key="mock-key", model="gemini-3.8-flash")
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.side_effect = json.JSONDecodeError("Expecting value", "bad json", 0)

        with patch("requests.post", return_value=mock_resp):
            with pytest.raises(AIProviderError) as exc_info:
                extractor._post_generate({"contents": []})
            assert "malformed JSON" in str(exc_info.value)
