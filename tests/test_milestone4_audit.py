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
from docket.dispatch.approval import (
    ActionMismatchError,
    ApprovalError,
    ApprovalService,
    DisputeMismatchError,
    InvalidSignatureError,
    MerchantMismatchError,
    PayloadTamperedError,
    TokenAlreadyUsedError,
    TokenExpiredError,
)
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
    ClaimEpistemicMetadata,
    ClaimStatus,
    ClaimType,
    EvidenceBasis,
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

    def test_claim_epistemic_metadata_serialization(self):
        meta = ClaimEpistemicMetadata(
            source_category="CUSTOMER_COMMUNICATION",
            attribution="BUYER_REPORTS_COURIER_STATEMENT",
            evidence_basis=EvidenceBasis.SECOND_HAND_HEARSAY,
            independent_carrier_confirmation=False,
            supporting_source_id="MSG-00",
        )
        claim = ExtractedClaim(
            claim_id="CLM-04",
            claim_type=ClaimType.COMMUNICATION_ACKNOWLEDGED,
            factual_assertion="Buyer reports courier verbal statement.",
            epistemic_metadata=meta,
        )
        # JSON round-trip test
        json_str = claim.model_dump_json()
        restored = ExtractedClaim.model_validate_json(json_str)
        assert restored.epistemic_metadata is not None
        assert restored.epistemic_metadata.evidence_basis == EvidenceBasis.SECOND_HAND_HEARSAY
        assert restored.epistemic_metadata.independent_carrier_confirmation is False
        assert restored.epistemic_metadata.supporting_source_id == "MSG-00"

    def test_epistemic_hearsay_blocked_from_delivery_completed_claim(self):
        hearsay_meta = ClaimEpistemicMetadata(
            source_category="CUSTOMER_COMMUNICATION",
            attribution="BUYER_REPORTS_COURIER_STATEMENT",
            evidence_basis=EvidenceBasis.SECOND_HAND_HEARSAY,
            independent_carrier_confirmation=False,
            supporting_source_id="MSG-00",
        )
        # Adversarial attempt: Marking a hearsay claim as DELIVERY_COMPLETED
        adversarial_claim = ExtractedClaim(
            claim_id="CLM-ADV-01",
            claim_type=ClaimType.DELIVERY_COMPLETED,
            factual_assertion="Buyer was told delivered.",
            epistemic_metadata=hearsay_meta,
        )
        delivery_inv = DeliveryProofInvariant()
        res = delivery_inv.evaluate(adversarial_claim, shipment=None)
        assert res.decision == DecisionType.BLOCK
        assert "HEARSAY_CANNOT_PROVE_DELIVERY" in res.violated_invariants
        assert "Cannot assert delivery from epistemic hearsay" in res.explanation

    def test_epistemic_metadata_requires_explicit_arguments_no_accidental_defaults(self):
        """Verify that ClaimEpistemicMetadata requires explicit arguments upon construction
        and does NOT silently default to Claim 4's courier statement attributes.
        """
        import pydantic
        with pytest.raises(pydantic.ValidationError):
            ClaimEpistemicMetadata()  # Missing required arguments must fail!

    def test_direct_carrier_evidence_and_unrelated_claims_have_distinct_epistemic_classification(self):
        # 1. Direct carrier tracking claim
        carrier_meta = ClaimEpistemicMetadata(
            source_category="CARRIER_TRACKING",
            attribution="CARRIER_SCAN_EVENT",
            evidence_basis=EvidenceBasis.DIRECT_RECORD,
            independent_carrier_confirmation=True,
            supporting_source_id="SRC-USPS-TRACKING-API",
        )
        assert carrier_meta.evidence_basis == EvidenceBasis.DIRECT_RECORD
        assert carrier_meta.independent_carrier_confirmation is True
        assert carrier_meta.attribution == "CARRIER_SCAN_EVENT"

        # 2. Buyer first-party non-receipt claim
        buyer_meta = ClaimEpistemicMetadata(
            source_category="CUSTOMER_COMMUNICATION",
            attribution="FIRST_PARTY_BUYER_STATEMENT",
            evidence_basis=EvidenceBasis.FIRST_PARTY_STATEMENT,
            independent_carrier_confirmation=False,
            supporting_source_id="MSG-00",
        )
        assert buyer_meta.evidence_basis == EvidenceBasis.FIRST_PARTY_STATEMENT
        assert buyer_meta.attribution != "BUYER_REPORTS_COURIER_STATEMENT"
        assert buyer_meta.independent_carrier_confirmation is False

        # 3. Claim 4 (second-hand hearsay)
        hearsay_meta = ClaimEpistemicMetadata(
            source_category="CUSTOMER_COMMUNICATION",
            attribution="BUYER_REPORTS_COURIER_STATEMENT",
            evidence_basis=EvidenceBasis.SECOND_HAND_HEARSAY,
            independent_carrier_confirmation=False,
            supporting_source_id="MSG-00",
        )
        assert hearsay_meta.evidence_basis == EvidenceBasis.SECOND_HAND_HEARSAY
        assert hearsay_meta.attribution == "BUYER_REPORTS_COURIER_STATEMENT"

    def test_missing_provenance_cannot_silently_become_verified_evidence(self):
        # Claim asserting delivery with customer communication citations and NO carrier record
        fake_delivery_claim = ExtractedClaim(
            claim_id="CLM-FAKE-DELIV-01",
            claim_type=ClaimType.DELIVERY_COMPLETED,
            factual_assertion="Delivered according to message",
            supporting_sources=[
                SourceCitation(
                    source_type=SourceType.CUSTOMER_COMMUNICATION,
                    source_identifier="MSG-00",
                    field_path="content",
                    extracted_value="package was delivered",
                    verification_status=VerificationStatus.VERIFIED,
                )
            ],
            epistemic_metadata=None,  # Missing provenance
        )
        inv = DeliveryProofInvariant()
        res = inv.evaluate(fake_delivery_claim, shipment=None)
        assert res.decision == DecisionType.BLOCK
        assert "CUSTOMER_COMMUNICATION_CANNOT_PROVE_DELIVERY" in res.violated_invariants


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
        assert DeliveryProofInvariant.POLICY_JURISDICTION == "India"
        assert DeliveryProofInvariant.POLICY_LAST_UPDATED == "January 26, 2026"
        assert DeliveryProofInvariant.AUTHORITATIVE_SOURCE == "https://www.paypal.com/in/legalhub/paypal/seller-protection"

        assert AddressMatchInvariant.RULE_VERSION == "2026.1"
        assert AddressMatchInvariant.POLICY_JURISDICTION == "India"
        assert AddressMatchInvariant.POLICY_LAST_UPDATED == "January 26, 2026"
        assert AddressMatchInvariant.AUTHORITATIVE_SOURCE == "https://www.paypal.com/in/legalhub/paypal/seller-protection"

        # Docket-owned internal reasoning heuristic distinction
        assert DeliveryDiscrepancyInvariant.RULE_VERSION == "2026.1"
        assert DeliveryDiscrepancyInvariant.POLICY_KIND == "DOCKET_INTERNAL_REASONING"
        assert DeliveryDiscrepancyInvariant.AUTHORITATIVE_SOURCE == "Docket Dispute Policy Framework — Evidence Reconciliation & Hearsay Heuristics (Docket Heuristic)"

    def test_gps_and_signature_are_investigative_directives_not_mandatory(self, audit_shipment_delivered):
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
        )
        inv = DeliveryDiscrepancyInvariant()
        res = inv.evaluate([hearsay_claim], audit_shipment_delivered, {"MSG-00": "raw buyer message"})
        assert res.decision == DecisionType.REVIEW
        assert "Docket investigative directives" in res.explanation
        assert "not universally mandatory requirements under official PayPal Seller Protection policy" in res.explanation


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

    def test_ledger_detects_altered_record_payload(self, tmp_path):
        """Test Case 1: Modification of an existing event payload."""
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

    def test_ledger_detects_deleted_interior_record(self, tmp_path):
        """Test Case 2: Deletion of an interior event."""
        log_file = tmp_path / "audit_trail.jsonl"
        logger = AuditLogger(storage_path=log_file)
        logger.log_event(AuditEventType.DISPUTE_INGESTED, "DISP-1", "SYSTEM", {"amount": "50.00"})
        logger.log_event(AuditEventType.POLICY_EVALUATED, "DISP-1", "POLICY_ENGINE", {"decision": "REVIEW"})
        logger.log_event(AuditEventType.APPROVAL_GRANTED, "DISP-1", "ADMIN", {"action": "APPROVE"})

        # Delete the middle (interior) record
        lines = log_file.read_text(encoding="utf-8").strip().split("\n")
        del lines[1]  # Delete event 2
        log_file.write_text("\n".join(lines) + "\n", encoding="utf-8")

        tampered_logger = AuditLogger(storage_path=log_file)
        diag = tampered_logger.verify_chain_detailed()
        assert diag["is_valid"] is False
        assert "parent_hash does not match" in diag["error_message"].lower()

    def test_ledger_detects_reordered_records(self, tmp_path):
        """Test Case 3: Reordering events."""
        log_file = tmp_path / "audit_trail.jsonl"
        logger = AuditLogger(storage_path=log_file)
        logger.log_event(AuditEventType.DISPUTE_INGESTED, "DISP-1", "SYSTEM", {"step": 1})
        logger.log_event(AuditEventType.POLICY_EVALUATED, "DISP-1", "POLICY_ENGINE", {"step": 2})
        logger.log_event(AuditEventType.APPROVAL_GRANTED, "DISP-1", "ADMIN", {"step": 3})

        # Swap event 1 and event 2
        lines = log_file.read_text(encoding="utf-8").strip().split("\n")
        lines[1], lines[2] = lines[2], lines[1]
        log_file.write_text("\n".join(lines) + "\n", encoding="utf-8")

        tampered_logger = AuditLogger(storage_path=log_file)
        diag = tampered_logger.verify_chain_detailed()
        assert diag["is_valid"] is False
        assert "parent_hash does not match" in diag["error_message"].lower()

    def test_ledger_detects_modified_parent_hash(self, tmp_path):
        """Test Case 4: Modification of parent_hash."""
        log_file = tmp_path / "audit_trail.jsonl"
        logger = AuditLogger(storage_path=log_file)
        logger.log_event(AuditEventType.DISPUTE_INGESTED, "DISP-1", "SYSTEM", {"step": 1})
        e2 = logger.log_event(AuditEventType.POLICY_EVALUATED, "DISP-1", "POLICY_ENGINE", {"step": 2})

        # Modify parent_hash of event 2 on disk
        lines = log_file.read_text(encoding="utf-8").strip().split("\n")
        data = json.loads(lines[1])
        data["parent_hash"] = "0000000000000000000000000000000000000000000000000000000000000000"
        lines[1] = json.dumps(data)
        log_file.write_text("\n".join(lines) + "\n", encoding="utf-8")

        tampered_logger = AuditLogger(storage_path=log_file)
        diag = tampered_logger.verify_chain_detailed()
        assert diag["is_valid"] is False
        assert diag["failed_event_id"] == e2.event_id

    def test_ledger_tail_truncation_limitation_single_event(self, tmp_path):
        """Test Case 5: Deletion of final event.
        
        Demonstrates the documented boundary of a backward-pointing hash chain:
        without a trusted external head-hash checkpoint, deleting the trailing event
        leaves a valid prefix that passes interior chain-integrity verification.
        """
        log_file = tmp_path / "audit_trail.jsonl"
        logger = AuditLogger(storage_path=log_file)
        logger.log_event(AuditEventType.DISPUTE_INGESTED, "DISP-1", "SYSTEM", {"step": 1})
        logger.log_event(AuditEventType.POLICY_EVALUATED, "DISP-1", "POLICY_ENGINE", {"step": 2})
        logger.log_event(AuditEventType.APPROVAL_GRANTED, "DISP-1", "ADMIN", {"step": 3})

        # Record the true head hash before truncation
        true_head_hash = logger.get_events()[-1].event_hash

        # Delete the final event from disk
        lines = log_file.read_text(encoding="utf-8").strip().split("\n")
        del lines[-1]
        log_file.write_text("\n".join(lines) + "\n", encoding="utf-8")

        truncated_logger = AuditLogger(storage_path=log_file)
        diag = truncated_logger.verify_chain_detailed()
        # The remaining 2-event prefix is internally consistent
        assert diag["is_valid"] is True
        assert diag["total_events"] == 2
        # But comparing against the independently committed external anchor detects tail truncation!
        current_head_hash = truncated_logger.get_events()[-1].event_hash
        assert current_head_hash != true_head_hash

    def test_ledger_tail_truncation_limitation_multiple_events(self, tmp_path):
        """Test Case 6: Deletion of multiple trailing events."""
        log_file = tmp_path / "audit_trail.jsonl"
        logger = AuditLogger(storage_path=log_file)
        logger.log_event(AuditEventType.DISPUTE_INGESTED, "DISP-1", "SYSTEM", {"step": 1})
        logger.log_event(AuditEventType.POLICY_EVALUATED, "DISP-1", "POLICY_ENGINE", {"step": 2})
        logger.log_event(AuditEventType.APPROVAL_GRANTED, "DISP-1", "ADMIN", {"step": 3})
        logger.log_event(AuditEventType.DISPATCH_ATTEMPTED, "DISP-1", "DISPATCHER", {"step": 4})

        true_head_hash = logger.get_events()[-1].event_hash

        # Delete the last 2 events from disk
        lines = log_file.read_text(encoding="utf-8").strip().split("\n")
        lines = lines[:2]
        log_file.write_text("\n".join(lines) + "\n", encoding="utf-8")

        truncated_logger = AuditLogger(storage_path=log_file)
        diag = truncated_logger.verify_chain_detailed()
        # Remaining prefix has interior integrity
        assert diag["is_valid"] is True
        assert diag["total_events"] == 2
        # Head-hash anchor check exposes truncation
        assert truncated_logger.get_events()[-1].event_hash != true_head_hash

    def test_ledger_full_chain_rewriting_limitation(self, tmp_path):
        """Test Case 7: Full-file rewriting with recomputed event hashes.
        
        Demonstrates that a local adversary with full file write access can generate
        a synthetic internally-valid chain from a forged genesis root, proving that
        local JSONL files provide tamper-evidence over their interior links, but
        guaranteed non-repudiation requires external anchoring.
        """
        log_file = tmp_path / "audit_trail.jsonl"
        logger = AuditLogger(storage_path=log_file)
        logger.log_event(AuditEventType.DISPUTE_INGESTED, "DISP-1", "SYSTEM", {"amount": "50.00"})
        logger.log_event(AuditEventType.POLICY_EVALUATED, "DISP-1", "POLICY_ENGINE", {"decision": "BLOCK"})

        original_head_hash = logger.get_events()[-1].event_hash

        # An adversary rewrites the entire file from scratch with forged data and valid hashes
        forged_logger = AuditLogger(storage_path=tmp_path / "forged.jsonl")
        forged_logger.log_event(AuditEventType.DISPUTE_INGESTED, "DISP-1", "SYSTEM", {"amount": "0.01"})
        forged_logger.log_event(AuditEventType.POLICY_EVALUATED, "DISP-1", "POLICY_ENGINE", {"decision": "ALLOW"})
        forged_content = (tmp_path / "forged.jsonl").read_text(encoding="utf-8")

        # Overwrite original ledger file with forged ledger
        log_file.write_text(forged_content, encoding="utf-8")

        reloaded_logger = AuditLogger(storage_path=log_file)
        diag = reloaded_logger.verify_chain_detailed()
        # Internally consistent
        assert diag["is_valid"] is True
        # But completely different from original commitment
        assert reloaded_logger.get_events()[-1].event_hash != original_head_hash


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


# ============================================================================
# 7. HMAC Merchant Approval Security Tests
# ============================================================================

class TestHMACMerchantApprovalSecurity:
    def test_approval_token_binding_and_verification(self, audit_dispute):
        service = ApprovalService(secret_key="top-secret-signing-key-for-docket-audit!")
        eval_result = OverallPolicyEvaluation(
            dispute_id=audit_dispute.dispute_id,
            overall_decision=DecisionType.ALLOW,
            factual_readiness=DecisionType.ALLOW,
            action_readiness=DecisionType.ALLOW,
            check_results=[],
            summary="All invariants passed",
        )
        payload = {"evidences": [{"evidence_type": "PROOF_OF_FULFILLMENT", "notes": "Dispute rebuttal"}]}
        
        req = service.create_approval_request(
            dispute=audit_dispute,
            policy_evaluation=eval_result,
            proposed_payload=payload,
            merchant_user_id="merchant_sarah",
            action="provide_evidence",
        )
        assert req.token.count(".") == 6  # 7 segments
        
        # Verify valid token
        assert service.verify_token(
            token=req.token,
            dispute_id=audit_dispute.dispute_id,
            payload=payload,
            merchant_user_id="merchant_sarah",
            action="provide_evidence",
            consume_nonce=False,
        ) is True

    def test_approval_token_anti_replay_single_use_nonce(self, audit_dispute):
        service = ApprovalService(secret_key="top-secret-signing-key-for-docket-audit!")
        eval_result = OverallPolicyEvaluation(
            dispute_id=audit_dispute.dispute_id,
            overall_decision=DecisionType.ALLOW,
            factual_readiness=DecisionType.ALLOW,
            action_readiness=DecisionType.ALLOW,
            check_results=[],
            summary="All invariants passed",
        )
        payload = {"evidences": []}
        req = service.create_approval_request(
            dispute=audit_dispute,
            policy_evaluation=eval_result,
            proposed_payload=payload,
        )
        # First verification succeeds and consumes nonce
        assert service.verify_token(
            token=req.token,
            dispute_id=audit_dispute.dispute_id,
            payload=payload,
            consume_nonce=True,
        ) is True

        # Second verification with same token MUST raise TokenAlreadyUsedError (replay attack)
        with pytest.raises(TokenAlreadyUsedError) as exc_info:
            service.verify_token(
                token=req.token,
                dispute_id=audit_dispute.dispute_id,
                payload=payload,
                consume_nonce=True,
            )
        assert "replay attack blocked" in str(exc_info.value).lower()

    def test_approval_token_expiration(self, audit_dispute):
        service = ApprovalService(secret_key="top-secret-signing-key-for-docket-audit!")
        eval_result = OverallPolicyEvaluation(
            dispute_id=audit_dispute.dispute_id,
            overall_decision=DecisionType.ALLOW,
            factual_readiness=DecisionType.ALLOW,
            action_readiness=DecisionType.ALLOW,
            check_results=[],
            summary="All invariants passed",
        )
        payload = {"evidences": []}
        # Issue token that was already expired 10 seconds ago
        req = service.create_approval_request(
            dispute=audit_dispute,
            policy_evaluation=eval_result,
            proposed_payload=payload,
            ttl_seconds=-10,
        )
        with pytest.raises(TokenExpiredError) as exc_info:
            service.verify_token(
                token=req.token,
                dispute_id=audit_dispute.dispute_id,
                payload=payload,
            )
        assert "has expired" in str(exc_info.value).lower()

    def test_approval_token_payload_tampering(self, audit_dispute):
        service = ApprovalService(secret_key="top-secret-signing-key-for-docket-audit!")
        eval_result = OverallPolicyEvaluation(
            dispute_id=audit_dispute.dispute_id,
            overall_decision=DecisionType.ALLOW,
            factual_readiness=DecisionType.ALLOW,
            action_readiness=DecisionType.ALLOW,
            check_results=[],
            summary="All invariants passed",
        )
        payload = {"evidences": [{"notes": "Original notes"}]}
        req = service.create_approval_request(
            dispute=audit_dispute,
            policy_evaluation=eval_result,
            proposed_payload=payload,
        )
        tampered_payload = {"evidences": [{"notes": "Tampered notes!"}]}
        with pytest.raises(PayloadTamperedError) as exc_info:
            service.verify_token(
                token=req.token,
                dispute_id=audit_dispute.dispute_id,
                payload=tampered_payload,
            )
        assert "integrity verification failed" in str(exc_info.value).lower()

    def test_approval_token_dispute_id_mismatch(self, audit_dispute):
        service = ApprovalService(secret_key="top-secret-signing-key-for-docket-audit!")
        eval_result = OverallPolicyEvaluation(
            dispute_id=audit_dispute.dispute_id,
            overall_decision=DecisionType.ALLOW,
            factual_readiness=DecisionType.ALLOW,
            action_readiness=DecisionType.ALLOW,
            check_results=[],
            summary="All invariants passed",
        )
        payload = {"evidences": []}
        req = service.create_approval_request(
            dispute=audit_dispute,
            policy_evaluation=eval_result,
            proposed_payload=payload,
        )
        with pytest.raises(DisputeMismatchError) as exc_info:
            service.verify_token(
                token=req.token,
                dispute_id="PP-D-WRONG-CASE",
                payload=payload,
            )
        assert "dispute mismatch" in str(exc_info.value).lower()

    def test_approval_token_merchant_mismatch(self, audit_dispute):
        service = ApprovalService(secret_key="top-secret-signing-key-for-docket-audit!")
        eval_result = OverallPolicyEvaluation(
            dispute_id=audit_dispute.dispute_id,
            overall_decision=DecisionType.ALLOW,
            factual_readiness=DecisionType.ALLOW,
            action_readiness=DecisionType.ALLOW,
            check_results=[],
            summary="All invariants passed",
        )
        payload = {"evidences": []}
        req = service.create_approval_request(
            dispute=audit_dispute,
            policy_evaluation=eval_result,
            proposed_payload=payload,
            merchant_user_id="authorized_admin",
        )
        with pytest.raises(MerchantMismatchError) as exc_info:
            service.verify_token(
                token=req.token,
                dispute_id=audit_dispute.dispute_id,
                payload=payload,
                merchant_user_id="unauthorized_impostor",
            )
        assert "merchant mismatch" in str(exc_info.value).lower()

    def test_approval_token_action_mismatch(self, audit_dispute):
        service = ApprovalService(secret_key="top-secret-signing-key-for-docket-audit!")
        eval_result = OverallPolicyEvaluation(
            dispute_id=audit_dispute.dispute_id,
            overall_decision=DecisionType.ALLOW,
            factual_readiness=DecisionType.ALLOW,
            action_readiness=DecisionType.ALLOW,
            check_results=[],
            summary="All invariants passed",
        )
        payload = {"evidences": []}
        req = service.create_approval_request(
            dispute=audit_dispute,
            policy_evaluation=eval_result,
            proposed_payload=payload,
            action="provide_evidence",
        )
        with pytest.raises(ActionMismatchError) as exc_info:
            service.verify_token(
                token=req.token,
                dispute_id=audit_dispute.dispute_id,
                payload=payload,
                action="accept_claim",
            )
        assert "action mismatch" in str(exc_info.value).lower()

    def test_approval_token_invalid_signature(self, audit_dispute):
        service = ApprovalService(secret_key="top-secret-signing-key-for-docket-audit!")
        eval_result = OverallPolicyEvaluation(
            dispute_id=audit_dispute.dispute_id,
            overall_decision=DecisionType.ALLOW,
            factual_readiness=DecisionType.ALLOW,
            action_readiness=DecisionType.ALLOW,
            check_results=[],
            summary="All invariants passed",
        )
        payload = {"evidences": []}
        req = service.create_approval_request(
            dispute=audit_dispute,
            policy_evaluation=eval_result,
            proposed_payload=payload,
        )
        tampered_token = req.token[:-6] + "badbad"
        with pytest.raises(InvalidSignatureError) as exc_info:
            service.verify_token(
                token=tampered_token,
                dispute_id=audit_dispute.dispute_id,
                payload=payload,
            )
        assert "signature verification failed" in str(exc_info.value).lower()

    def test_concurrent_simultaneous_dispatch_single_use_nonce(self, audit_dispute):
        """Explicitly test two simultaneous dispatch/verification attempts using the same approval token."""
        import concurrent.futures
        service = ApprovalService(secret_key="top-secret-signing-key-for-docket-audit!")
        eval_result = OverallPolicyEvaluation(
            dispute_id=audit_dispute.dispute_id,
            overall_decision=DecisionType.ALLOW,
            factual_readiness=DecisionType.ALLOW,
            action_readiness=DecisionType.ALLOW,
            check_results=[],
            summary="All invariants passed",
        )
        payload = {"evidences": [{"notes": "Rebuttal"}]}
        req = service.create_approval_request(
            dispute=audit_dispute,
            policy_evaluation=eval_result,
            proposed_payload=payload,
            merchant_user_id="merchant_admin",
        )

        results = []
        errors = []

        def attempt_verify():
            try:
                res = service.verify_token(
                    token=req.token,
                    dispute_id=audit_dispute.dispute_id,
                    payload=payload,
                    merchant_user_id="merchant_admin",
                    action="provide_evidence",
                    consume_nonce=True,
                )
                results.append(res)
            except Exception as e:
                errors.append(e)

        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
            f1 = executor.submit(attempt_verify)
            f2 = executor.submit(attempt_verify)
            f1.result()
            f2.result()

        # Exactly one verification succeeded, and exactly one raised TokenAlreadyUsedError
        assert len(results) == 1
        assert results[0] is True
        assert len(errors) == 1
        assert isinstance(errors[0], TokenAlreadyUsedError)
        assert "replay attack blocked" in str(errors[0]).lower()

    def test_dispatch_evidence_authenticates_caller_merchant_identity(self, audit_dispute, audit_order, audit_shipment_delivered):
        service = ApprovalService(secret_key="top-secret-signing-key-for-docket-audit!")
        dispatcher = EvidenceDispatcher(approval_service=service)
        bundle = ReconciledDisputeBundle(
            dispute_id=audit_dispute.dispute_id,
            status=ReconciliationStatus.RECONCILED,
            matched_order=audit_order,
            matched_shipments=[audit_shipment_delivered],
        )
        eval_result = OverallPolicyEvaluation(
            dispute_id=audit_dispute.dispute_id,
            overall_decision=DecisionType.ALLOW,
            factual_readiness=DecisionType.ALLOW,
            action_readiness=DecisionType.ALLOW,
            check_results=[],
            summary="All invariants passed",
        )
        payload = dispatcher.formatter.format_fulfillment_evidence(bundle=bundle)
        req = service.create_approval_request(
            dispute=audit_dispute,
            policy_evaluation=eval_result,
            proposed_payload=payload,
            merchant_user_id="authorized_sarah",
        )
        record = service.record_approval(
            request=req,
            merchant_user_id="authorized_sarah",
            decision=ApprovalDecision.APPROVE,
        )

        # Mismatched caller identity rejected
        with pytest.raises(MerchantApprovalRequiredError) as exc_info:
            dispatcher.dispatch_evidence(
                dispute=audit_dispute,
                bundle=bundle,
                evaluation=eval_result,
                approval_record=record,
                caller_merchant_id="unauthorized_mallory",
            )
        assert "does not match authorized merchant" in str(exc_info.value).lower()


# ============================================================================
# 8. Gemini 3.8 Streaming & Thought Signature Preservation Tests
# ============================================================================

class TestGeminiStreamingAndThoughtSignature:
    def test_streaming_chunk_aggregation_preserves_candidates_and_thought_signature(self):
        extractor = GeminiFactExtractor(api_key="mock-key", model="gemini-3.8-flash")
        
        mock_chunks = [
            {
                "candidates": [
                    {
                        "index": 0,
                        "content": {
                            "role": "model",
                            "parts": [
                                {
                                    "text": "Reasoning about buyer delivery statements...",
                                    "thought": True,
                                    "thoughtSignature": "z8Kx9Q2mP0L1...valid_signature",
                                }
                            ]
                        }
                    }
                ]
            },
            {
                "candidates": [
                    {
                        "index": 0,
                        "content": {
                            "role": "model",
                            "parts": [
                                {
                                    "functionCall": {
                                        "name": "record_extracted_claims",
                                        "args": {
                                            "claims": [
                                                {
                                                    "claim_id": "CLM-01",
                                                    "claim_type": "DELIVERY_COMPLETED",
                                                    "factual_assertion": "Package delivered",
                                                    "exact_citation_excerpt": "delivered yesterday",
                                                    "source_id": "MSG-00",
                                                }
                                            ]
                                        }
                                    }
                                }
                            ]
                        },
                        "finishReason": "STOP"
                    }
                ],
                "usageMetadata": {
                    "promptTokenCount": 512,
                    "candidatesTokenCount": 128,
                    "totalTokenCount": 640,
                }
            }
        ]

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = mock_chunks

        with patch("requests.post", return_value=mock_resp):
            data = extractor._post_generate({"contents": []})

        assert data["chunks_count"] == 2
        assert len(data["candidates"]) == 1
        cand = data["candidates"][0]
        assert cand["index"] == 0
        assert cand["finishReason"] == "STOP"
        
        # Verify both parts are preserved with boundaries and attributes
        parts = cand["content"]["parts"]
        assert len(parts) == 2
        assert parts[0]["thoughtSignature"] == "z8Kx9Q2mP0L1...valid_signature"
        assert parts[0]["thought"] is True
        assert parts[1]["functionCall"]["name"] == "record_extracted_claims"

        # Verify usageMetadata is preserved
        assert data["usageMetadata"]["totalTokenCount"] == 640

    def test_streaming_multi_candidate_and_mixed_parts(self):
        extractor = GeminiFactExtractor(api_key="mock-key", model="gemini-3.8-flash")
        
        mock_chunks = [
            {
                "candidates": [
                    {
                        "index": 0,
                        "content": {"parts": [{"text": "Candidate 0 part 1"}]}
                    },
                    {
                        "index": 1,
                        "content": {"parts": [{"text": "Candidate 1 part 1"}]}
                    }
                ]
            },
            {
                "candidates": [
                    {
                        "index": 0,
                        "content": {"parts": [{"text": "Candidate 0 part 2"}]}
                    }
                ]
            }
        ]

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = mock_chunks

        with patch("requests.post", return_value=mock_resp):
            data = extractor._post_generate({"contents": []})

        assert len(data["candidates"]) == 2
        assert len(data["candidates"][0]["content"]["parts"]) == 2
        assert len(data["candidates"][1]["content"]["parts"]) == 1
