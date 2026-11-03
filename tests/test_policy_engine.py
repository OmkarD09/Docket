"""Unit tests for Docket Deterministic Policy Engine and Domain Models.

Follows TDD to verify:
1. DeliveryProofInvariant (LABEL_CREATED / IN_TRANSIT refusal on delivery claims,
   pass on DELIVERED, preservation of truthful LABEL_CREATED claims).
2. AddressMatchInvariant (Country/postal code match, mismatch detection,
   distinction between MISMATCH and INSUFFICIENT_DATA).
3. HATEOASActionInvariant (Action presence, URL validation, dispute ID match,
   lifecycle state checks).
4. SignatureRequirementAssessment (Contextual advisory for pre vs. post Jan 26 2026,
   threshold evaluation, non-blocking behavior).
5. CitationIntegrityInvariant (Empty citations, unknown sources, conflicting sources,
   unrelated orders).
6. PolicyEngine Aggregation (Collecting all violations, BLOCK/REVIEW/ALLOW resolution,
   defining INR "Label Created" scenario).
"""

from datetime import datetime, timezone
from decimal import Decimal
import json
from pathlib import Path
import pytest

from docket.models.dispute import (
    DisputeCase,
    DisputeLifecycleStage,
    DisputeReason,
    DisputeStatus,
    HATEOASLink,
    Money,
    RequestedEvidence,
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
from docket.models.policy import (
    DecisionType,
    OverallPolicyEvaluation,
    PolicyCheckResult,
)
from docket.policy.engine import (
    AddressMatchInvariant,
    AddressMatchPolicy,
    CitationIntegrityInvariant,
    DeliveryProofInvariant,
    HATEOASActionInvariant,
    PolicyEngine,
    SignatureAssessmentInvariant,
)


# ============================================================================
# Fixtures & Test Data Helpers
# ============================================================================

@pytest.fixture
def sample_dispute() -> DisputeCase:
    return DisputeCase(
        dispute_id="PP-R-NKI-10193390",
        reason=DisputeReason.MERCHANDISE_OR_SERVICE_NOT_RECEIVED,
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
            ),
            HATEOASLink(
                href="https://api-m.sandbox.paypal.com/v1/customer/disputes/PP-R-NKI-10193390",
                rel="self",
                method="GET",
            ),
        ],
        disputed_transaction_id="4R073105U90937213",
    )


@pytest.fixture
def sample_order() -> OrderRecord:
    return OrderRecord(
        order_id="ORD-2026-1018",
        paypal_transaction_id="4R073105U90937213",
        order_timestamp=datetime(2026, 10, 18, 13, 30, 0, tzinfo=timezone.utc),
        gross_amount=Money(value=Decimal("25.00"), currency_code="USD"),
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
def sample_shipment_label_created() -> ShipmentRecord:
    return ShipmentRecord(
        internal_order_id="ORD-2026-1018",
        tracking_number="94001118992231001",
        carrier_name="USPS",
        tracking_status=TrackingStatus.LABEL_CREATED,
        shipment_timestamp=datetime(2026, 10, 18, 14, 0, 0, tzinfo=timezone.utc),
        delivery_timestamp=None,
        shipment_address=Address(
            recipient_name="John Doe",
            city="San Jose",
            state_or_province="CA",
            postal_code="95131",
            country_code="US",
        ),
        source_identifier="TRK-94001118992231001",
    )


@pytest.fixture
def sample_shipment_delivered() -> ShipmentRecord:
    return ShipmentRecord(
        internal_order_id="ORD-2026-1018",
        tracking_number="94001118992231001",
        carrier_name="USPS",
        tracking_status=TrackingStatus.DELIVERED,
        shipment_timestamp=datetime(2026, 10, 18, 14, 0, 0, tzinfo=timezone.utc),
        delivery_timestamp=datetime(2026, 10, 20, 11, 45, 0, tzinfo=timezone.utc),
        shipment_address=Address(
            recipient_name="John Doe",
            city="San Jose",
            state_or_province="CA",
            postal_code="95131",
            country_code="US",
        ),
        source_identifier="TRK-94001118992231001",
        recipient_signature_present=False,
    )


# ============================================================================
# 1. DeliveryProofInvariant Tests
# ============================================================================

class TestDeliveryProofInvariant:
    """Verifies Docket's defining safety barrier on delivery assertions."""

    def test_delivery_claim_blocked_when_label_created(self, sample_order, sample_shipment_label_created):
        """Mandatory refusal: LABEL_CREATED strictly blocks claiming delivery."""
        invariant = DeliveryProofInvariant()
        claim = ExtractedClaim(
            claim_id="CLM-001",
            claim_type=ClaimType.DELIVERY_COMPLETED,
            factual_assertion="The merchandise was delivered to the buyer.",
            supporting_sources=[
                SourceCitation(
                    source_type=SourceType.CARRIER_TRACKING,
                    source_identifier="TRK-94001118992231001",
                    field_path="tracking_status",
                    extracted_value="LABEL_CREATED",
                )
            ],
        )

        result = invariant.evaluate(claim=claim, shipment=sample_shipment_label_created, order=sample_order)

        assert result.decision == DecisionType.BLOCK
        assert "LABEL_CREATED" in result.violated_invariants
        assert "Label Created" in result.explanation
        assert result.recommended_next_action is not None
        assert "not assert delivery" in result.recommended_next_action.lower()

    def test_delivery_claim_blocked_when_in_transit(self, sample_order, sample_shipment_label_created):
        """IN_TRANSIT strictly blocks claiming delivery completed."""
        sample_shipment_label_created.tracking_status = TrackingStatus.IN_TRANSIT
        invariant = DeliveryProofInvariant()
        claim = ExtractedClaim(
            claim_id="CLM-002",
            claim_type=ClaimType.DELIVERY_COMPLETED,
            factual_assertion="Item delivered to buyer.",
            supporting_sources=[
                SourceCitation(
                    source_type=SourceType.CARRIER_TRACKING,
                    source_identifier="TRK-94001118992231001",
                    field_path="tracking_status",
                    extracted_value="IN_TRANSIT",
                )
            ],
        )

        result = invariant.evaluate(claim=claim, shipment=sample_shipment_label_created, order=sample_order)

        assert result.decision == DecisionType.BLOCK
        assert "IN_TRANSIT" in result.violated_invariants
        assert "in transit" in result.explanation.lower()

    def test_delivery_claim_blocked_when_tracking_missing(self, sample_order):
        """Delivery claim with no shipment record must be blocked."""
        invariant = DeliveryProofInvariant()
        claim = ExtractedClaim(
            claim_id="CLM-003",
            claim_type=ClaimType.DELIVERY_COMPLETED,
            factual_assertion="Item was delivered.",
        )

        result = invariant.evaluate(claim=claim, shipment=None, order=sample_order)

        assert result.decision == DecisionType.BLOCK
        assert "TRACKING_DATA_UNAVAILABLE" in result.violated_invariants

    def test_delivery_claim_blocked_when_tracking_order_mismatched(self, sample_order, sample_shipment_delivered):
        """Tracking record belonging to a different order cannot support delivery."""
        sample_shipment_delivered.internal_order_id = "ORD-DIFFERENT-999"
        invariant = DeliveryProofInvariant()
        claim = ExtractedClaim(
            claim_id="CLM-004",
            claim_type=ClaimType.DELIVERY_COMPLETED,
            factual_assertion="Item delivered.",
            supporting_sources=[
                SourceCitation(
                    source_type=SourceType.CARRIER_TRACKING,
                    source_identifier="TRK-94001118992231001",
                    field_path="tracking_status",
                    extracted_value="DELIVERED",
                )
            ],
        )

        result = invariant.evaluate(claim=claim, shipment=sample_shipment_delivered, order=sample_order)

        assert result.decision == DecisionType.BLOCK
        assert "TRACKING_ORDER_MISMATCH" in result.violated_invariants

    def test_delivery_claim_blocked_when_delivery_date_missing(self, sample_order, sample_shipment_delivered):
        """Proof of delivery requires an established delivery timestamp."""
        sample_shipment_delivered.delivery_timestamp = None
        invariant = DeliveryProofInvariant()
        claim = ExtractedClaim(
            claim_id="CLM-005",
            claim_type=ClaimType.DELIVERY_COMPLETED,
            factual_assertion="Delivered.",
        )

        result = invariant.evaluate(claim=claim, shipment=sample_shipment_delivered, order=sample_order)

        assert result.decision == DecisionType.BLOCK
        assert "DELIVERY_TIMESTAMP_MISSING" in result.violated_invariants

    def test_delivery_claim_allowed_when_delivered_and_complete(self, sample_order, sample_shipment_delivered):
        """DELIVERED with timestamp, carrier, and matching order passes."""
        invariant = DeliveryProofInvariant()
        claim = ExtractedClaim(
            claim_id="CLM-006",
            claim_type=ClaimType.DELIVERY_COMPLETED,
            factual_assertion="Delivered on 2026-10-20.",
            supporting_sources=[
                SourceCitation(
                    source_type=SourceType.CARRIER_TRACKING,
                    source_identifier="TRK-94001118992231001",
                    field_path="delivery_timestamp",
                    extracted_value="2026-10-20T11:45:00Z",
                )
            ],
        )

        result = invariant.evaluate(claim=claim, shipment=sample_shipment_delivered, order=sample_order)

        assert result.decision == DecisionType.ALLOW
        assert len(result.violated_invariants) == 0
        assert "verified" in result.explanation.lower()

    def test_label_created_claim_allowed_when_truthful(self, sample_order, sample_shipment_label_created):
        """CRITICAL: Truthful claim that a label was created MUST NOT be rejected merely because delivery did not happen."""
        invariant = DeliveryProofInvariant()
        claim = ExtractedClaim(
            claim_id="CLM-007",
            claim_type=ClaimType.LABEL_CREATED,
            factual_assertion="A shipping label was created via USPS tracking 94001118992231001.",
            supporting_sources=[
                SourceCitation(
                    source_type=SourceType.CARRIER_TRACKING,
                    source_identifier="TRK-94001118992231001",
                    field_path="tracking_status",
                    extracted_value="LABEL_CREATED",
                )
            ],
        )

        result = invariant.evaluate(claim=claim, shipment=sample_shipment_label_created, order=sample_order)

        assert result.decision == DecisionType.ALLOW
        assert "truthful" in result.explanation.lower() or "matches" in result.explanation.lower()

    def test_shipment_in_progress_claim_allowed_when_in_transit(self, sample_order, sample_shipment_label_created):
        """Truthful claim that shipment is in progress is allowed when status is IN_TRANSIT."""
        sample_shipment_label_created.tracking_status = TrackingStatus.IN_TRANSIT
        invariant = DeliveryProofInvariant()
        claim = ExtractedClaim(
            claim_id="CLM-008",
            claim_type=ClaimType.SHIPMENT_IN_PROGRESS,
            factual_assertion="Package is currently in transit with USPS.",
            supporting_sources=[
                SourceCitation(
                    source_type=SourceType.CARRIER_TRACKING,
                    source_identifier="TRK-94001118992231001",
                    field_path="tracking_status",
                    extracted_value="IN_TRANSIT",
                )
            ],
        )

        result = invariant.evaluate(claim=claim, shipment=sample_shipment_label_created, order=sample_order)

        assert result.decision == DecisionType.ALLOW


# ============================================================================
# 2. AddressMatchInvariant Tests
# ============================================================================

class TestAddressMatchInvariant:
    """Verifies destination address comparison against PayPal transaction address."""

    def test_matching_address_allowed(self, sample_order, sample_shipment_delivered):
        """Matching country and postal code passes standard policy."""
        invariant = AddressMatchInvariant(policy=AddressMatchPolicy.STANDARD)
        result = invariant.evaluate(order=sample_order, shipment=sample_shipment_delivered)

        assert result.decision == DecisionType.ALLOW
        assert len(result.violated_invariants) == 0

    def test_postal_code_mismatch_blocked(self, sample_order, sample_shipment_delivered):
        """Postal code mismatch is detected and blocked."""
        sample_shipment_delivered.shipment_address.postal_code = "90210"
        invariant = AddressMatchInvariant()
        result = invariant.evaluate(order=sample_order, shipment=sample_shipment_delivered)

        assert result.decision == DecisionType.BLOCK
        assert "ADDRESS_POSTAL_CODE_MISMATCH" in result.violated_invariants
        assert "90210" in result.explanation
        assert "95131" in result.explanation

    def test_country_mismatch_blocked(self, sample_order, sample_shipment_delivered):
        """Country mismatch is blocked."""
        sample_shipment_delivered.shipment_address.country_code = "CA"
        invariant = AddressMatchInvariant()
        result = invariant.evaluate(order=sample_order, shipment=sample_shipment_delivered)

        assert result.decision == DecisionType.BLOCK
        assert "ADDRESS_COUNTRY_MISMATCH" in result.violated_invariants

    def test_missing_transaction_address_returns_review(self, sample_order, sample_shipment_delivered):
        """Missing transaction address is INSUFFICIENT_DATA (REVIEW), not a pass or hard mismatch."""
        sample_order.shipping_address = None
        invariant = AddressMatchInvariant()
        result = invariant.evaluate(order=sample_order, shipment=sample_shipment_delivered)

        assert result.decision == DecisionType.REVIEW
        assert "TRANSACTION_ADDRESS_MISSING" in result.violated_invariants
        assert "insufficient" in result.explanation.lower() or "missing" in result.explanation.lower()

    def test_missing_carrier_address_returns_review(self, sample_order, sample_shipment_delivered):
        """Missing carrier delivery address is INSUFFICIENT_DATA (REVIEW)."""
        sample_shipment_delivered.shipment_address = None
        invariant = AddressMatchInvariant()
        result = invariant.evaluate(order=sample_order, shipment=sample_shipment_delivered)

        assert result.decision == DecisionType.REVIEW
        assert "CARRIER_ADDRESS_MISSING" in result.violated_invariants

    def test_normalized_postal_code_comparison(self, sample_order, sample_shipment_delivered):
        """ZIP+4 extension (95131-1234) matches base 5-digit ZIP (95131)."""
        sample_order.shipping_address.postal_code = "95131-1234"
        sample_shipment_delivered.shipment_address.postal_code = "95131"
        invariant = AddressMatchInvariant()
        result = invariant.evaluate(order=sample_order, shipment=sample_shipment_delivered)

        assert result.decision == DecisionType.ALLOW

    def test_strict_policy_city_mismatch_blocked(self, sample_order, sample_shipment_delivered):
        """Under STRICT policy, city mismatch is detected and blocked."""
        sample_shipment_delivered.shipment_address.city = "San Francisco"
        invariant = AddressMatchInvariant(policy=AddressMatchPolicy.STRICT)
        result = invariant.evaluate(order=sample_order, shipment=sample_shipment_delivered)

        assert result.decision == DecisionType.BLOCK
        assert "ADDRESS_CITY_MISMATCH" in result.violated_invariants


# ============================================================================
# 3. HATEOASActionInvariant Tests
# ============================================================================

class TestHATEOASActionInvariant:
    """Verifies dispute action link presence and validity."""

    def test_hateoas_allowed_when_action_present_and_valid(self, sample_dispute):
        """Dispute with valid provide_evidence link is allowed."""
        invariant = HATEOASActionInvariant(target_action="provide_evidence")
        result = invariant.evaluate(dispute=sample_dispute)

        assert result.decision == DecisionType.ALLOW
        assert len(result.violated_invariants) == 0

    def test_hateoas_blocked_when_action_link_missing(self, sample_dispute):
        """Missing provide_evidence link blocks submission."""
        sample_dispute.available_hateoas_actions = [
            HATEOASLink(href="https://api-m.sandbox.paypal.com/v1/customer/disputes/PP-R-NKI-10193390", rel="self", method="GET")
        ]
        invariant = HATEOASActionInvariant(target_action="provide_evidence")
        result = invariant.evaluate(dispute=sample_dispute)

        assert result.decision == DecisionType.BLOCK
        assert "HATEOAS_ACTION_ABSENT" in result.violated_invariants

    def test_hateoas_blocked_when_dispute_resolved(self, sample_dispute):
        """Resolved dispute cannot accept evidence."""
        sample_dispute.status = DisputeStatus.RESOLVED
        invariant = HATEOASActionInvariant(target_action="provide_evidence")
        result = invariant.evaluate(dispute=sample_dispute)

        assert result.decision == DecisionType.BLOCK
        assert "DISPUTE_STATE_NOT_ACTIONABLE" in result.violated_invariants

    def test_hateoas_blocked_when_link_dispute_id_mismatched(self, sample_dispute):
        """Stale or cross-case action link from another dispute is blocked."""
        sample_dispute.available_hateoas_actions = [
            HATEOASLink(
                href="https://api-m.sandbox.paypal.com/v1/customer/disputes/PP-DIFFERENT-99999/provide-evidence",
                rel="provide_evidence",
                method="POST",
            )
        ]
        invariant = HATEOASActionInvariant(target_action="provide_evidence")
        result = invariant.evaluate(dispute=sample_dispute)

        assert result.decision == DecisionType.BLOCK
        assert "HATEOAS_LINK_DISPUTE_MISMATCH" in result.violated_invariants


# ============================================================================
# 4. SignatureRequirementAssessment Tests
# ============================================================================

class TestSignatureAssessmentInvariant:
    """Verifies contextual advisory for signature confirmation (not a hard block)."""

    def test_pre_2026_over_750_with_signature_allowed(self, sample_order, sample_shipment_delivered):
        """Pre-Jan 26, 2026 transaction >= $750 with signature is ALLOW."""
        sample_order.gross_amount = Money(value=Decimal("800.00"), currency_code="USD")
        sample_order.order_timestamp = datetime(2025, 12, 1, 10, 0, 0, tzinfo=timezone.utc)
        sample_shipment_delivered.recipient_signature_present = True

        invariant = SignatureAssessmentInvariant()
        result = invariant.evaluate(order=sample_order, shipment=sample_shipment_delivered)

        assert result.decision == DecisionType.ALLOW

    def test_pre_2026_over_750_without_signature_returns_review_advisory(self, sample_order, sample_shipment_delivered):
        """Pre-Jan 26, 2026 transaction >= $750 without signature returns REVIEW (advisory, not BLOCK)."""
        sample_order.gross_amount = Money(value=Decimal("800.00"), currency_code="USD")
        sample_order.order_timestamp = datetime(2025, 12, 1, 10, 0, 0, tzinfo=timezone.utc)
        sample_shipment_delivered.recipient_signature_present = False

        invariant = SignatureAssessmentInvariant()
        result = invariant.evaluate(order=sample_order, shipment=sample_shipment_delivered)

        # MUST be REVIEW, NEVER BLOCK!
        assert result.decision == DecisionType.REVIEW
        assert "SIGNATURE_RECOMMENDED_PRE_2026" in result.violated_invariants
        assert "advisory" in result.explanation.lower() or "seller protection" in result.explanation.lower()

    def test_post_2026_over_750_without_signature_returns_advisory_review(self, sample_order, sample_shipment_delivered):
        """Post-Jan 26, 2026 high-value transaction without signature returns advisory REVIEW."""
        sample_order.gross_amount = Money(value=Decimal("850.00"), currency_code="USD")
        sample_order.order_timestamp = datetime(2026, 3, 15, 10, 0, 0, tzinfo=timezone.utc)
        sample_shipment_delivered.recipient_signature_present = False

        invariant = SignatureAssessmentInvariant()
        result = invariant.evaluate(order=sample_order, shipment=sample_shipment_delivered)

        assert result.decision == DecisionType.REVIEW
        assert "SIGNATURE_ADVISORY_POST_2026" in result.violated_invariants

    def test_post_2026_under_750_allowed(self, sample_order, sample_shipment_delivered):
        """Transaction under threshold passes without signature check."""
        sample_order.gross_amount = Money(value=Decimal("50.00"), currency_code="USD")
        sample_order.order_timestamp = datetime(2026, 3, 15, 10, 0, 0, tzinfo=timezone.utc)

        invariant = SignatureAssessmentInvariant()
        result = invariant.evaluate(order=sample_order, shipment=sample_shipment_delivered)

        assert result.decision == DecisionType.ALLOW

    def test_signature_indeterminate_when_date_missing(self, sample_order, sample_shipment_delivered):
        """Missing transaction date returns REVIEW (indeterminate)."""
        sample_order.gross_amount = Money(value=Decimal("1200.00"), currency_code="USD")
        sample_order.order_timestamp = None

        invariant = SignatureAssessmentInvariant()
        result = invariant.evaluate(order=sample_order, shipment=sample_shipment_delivered)

        assert result.decision == DecisionType.REVIEW
        assert "SIGNATURE_DATE_INDETERMINATE" in result.violated_invariants


# ============================================================================
# 5. CitationIntegrityInvariant Tests
# ============================================================================

class TestCitationIntegrityInvariant:
    """Verifies that all claims cite existing, unconflicted sources."""

    def test_claim_without_citations_blocked(self):
        """Claim with empty citations list is blocked."""
        claim = ExtractedClaim(
            claim_id="CLM-NOCITE",
            claim_type=ClaimType.DELIVERY_COMPLETED,
            factual_assertion="Item was delivered without proof.",
            supporting_sources=[],
        )
        invariant = CitationIntegrityInvariant()
        result = invariant.evaluate(claim=claim, available_sources={})

        assert result.decision == DecisionType.BLOCK
        assert "CLAIM_WITHOUT_CITATIONS" in result.violated_invariants

    def test_citation_pointing_to_nonexistent_source_blocked(self):
        """Citation referencing an unknown source identifier is blocked."""
        claim = ExtractedClaim(
            claim_id="CLM-BADSOURCE",
            claim_type=ClaimType.DELIVERY_COMPLETED,
            factual_assertion="Delivered.",
            supporting_sources=[
                SourceCitation(
                    source_type=SourceType.CARRIER_TRACKING,
                    source_identifier="TRK-GHOST-999",
                    field_path="status",
                    extracted_value="DELIVERED",
                )
            ],
        )
        invariant = CitationIntegrityInvariant()
        result = invariant.evaluate(claim=claim, available_sources={"TRK-KNOWN-111": "source_obj"})

        assert result.decision == DecisionType.BLOCK
        assert "CITATION_SOURCE_NONEXISTENT" in result.violated_invariants

    def test_citation_with_conflicting_source_triggers_review(self):
        """Citation whose source verification status is CONFLICTING triggers REVIEW."""
        claim = ExtractedClaim(
            claim_id="CLM-CONFLICT",
            claim_type=ClaimType.DELIVERY_COMPLETED,
            factual_assertion="Delivered.",
            supporting_sources=[
                SourceCitation(
                    source_type=SourceType.CARRIER_TRACKING,
                    source_identifier="TRK-KNOWN-111",
                    field_path="status",
                    extracted_value="DELIVERED",
                    verification_status=VerificationStatus.CONFLICTING,
                )
            ],
        )
        invariant = CitationIntegrityInvariant()
        result = invariant.evaluate(claim=claim, available_sources={"TRK-KNOWN-111": "source_obj"})

        assert result.decision == DecisionType.REVIEW
        assert "CITATION_SOURCE_CONFLICTING" in result.violated_invariants

    def test_valid_claim_with_verified_citation_allowed(self):
        """Valid claim with verified citation passes."""
        claim = ExtractedClaim(
            claim_id="CLM-VALID",
            claim_type=ClaimType.DELIVERY_COMPLETED,
            factual_assertion="Delivered.",
            supporting_sources=[
                SourceCitation(
                    source_type=SourceType.CARRIER_TRACKING,
                    source_identifier="TRK-KNOWN-111",
                    field_path="status",
                    extracted_value="DELIVERED",
                    verification_status=VerificationStatus.VERIFIED,
                )
            ],
        )
        invariant = CitationIntegrityInvariant()
        result = invariant.evaluate(claim=claim, available_sources={"TRK-KNOWN-111": {"status": "DELIVERED"}})

        assert result.decision == DecisionType.ALLOW


# ============================================================================
# 6. PolicyEngine Integration & Defining Scenario Tests
# ============================================================================

class TestPolicyEngineIntegration:
    """Verifies multi-rule aggregation and the defining INR 'Label Created' scenario."""

    def test_defining_scenario_inr_label_created_hard_refusal(
        self, sample_dispute, sample_order, sample_shipment_label_created
    ):
        """THE DEFINING HACKATHON SCENARIO:
        Customer files Item Not Received dispute.
        Shipping record says 'Label Created' but does not establish delivery.
        Docket MUST refuse to claim delivery, explain missing evidence, and recommend next action.
        """
        engine = PolicyEngine()
        delivery_claim = ExtractedClaim(
            claim_id="CLM-INR-01",
            claim_type=ClaimType.DELIVERY_COMPLETED,
            factual_assertion="Merchandise was delivered on time.",
            supporting_sources=[
                SourceCitation(
                    source_type=SourceType.CARRIER_TRACKING,
                    source_identifier="TRK-94001118992231001",
                    field_path="tracking_status",
                    extracted_value="LABEL_CREATED",
                )
            ],
        )

        evaluation: OverallPolicyEvaluation = engine.evaluate(
            dispute=sample_dispute,
            order=sample_order,
            shipment=sample_shipment_label_created,
            claims=[delivery_claim],
            target_action="provide_evidence",
        )

        # 1. Overall decision MUST be BLOCK
        assert evaluation.overall_decision == DecisionType.BLOCK

        # 2. Check violated invariants
        all_violations = [v for check in evaluation.check_results for v in check.violated_invariants]
        assert "LABEL_CREATED" in all_violations

        # 3. Explain missing evidence
        delivery_check = next(c for c in evaluation.check_results if c.rule_identifier == "RULE_DELIVERY_PROOF")
        assert "Label Created" in delivery_check.explanation
        assert delivery_check.recommended_next_action is not None

        # 4. HATEOAS action check still ran independently
        hateoas_check = next(c for c in evaluation.check_results if c.rule_identifier == "RULE_HATEOAS_ACTION")
        assert hateoas_check.decision == DecisionType.ALLOW  # HATEOAS was valid, proving independent checks

    def test_engine_collects_all_violations_without_short_circuiting(
        self, sample_dispute, sample_order, sample_shipment_label_created
    ):
        """Engine must collect all violations across rules, never stopping after the first."""
        # Cause Delivery violation (LABEL_CREATED) + Address violation (postal mismatch)
        sample_shipment_label_created.shipment_address.postal_code = "99999"

        engine = PolicyEngine()
        claim = ExtractedClaim(
            claim_id="CLM-MULTI-FAIL",
            claim_type=ClaimType.DELIVERY_COMPLETED,
            factual_assertion="Delivered.",
            supporting_sources=[
                SourceCitation(
                    source_type=SourceType.CARRIER_TRACKING,
                    source_identifier="TRK-94001118992231001",
                    field_path="tracking_status",
                    extracted_value="LABEL_CREATED",
                )
            ],
        )

        evaluation = engine.evaluate(
            dispute=sample_dispute,
            order=sample_order,
            shipment=sample_shipment_label_created,
            claims=[claim],
        )

        rule_ids = [c.rule_identifier for c in evaluation.check_results]
        assert "RULE_DELIVERY_PROOF" in rule_ids
        assert "RULE_ADDRESS_MATCH" in rule_ids

        delivery_result = next(c for c in evaluation.check_results if c.rule_identifier == "RULE_DELIVERY_PROOF")
        address_result = next(c for c in evaluation.check_results if c.rule_identifier == "RULE_ADDRESS_MATCH")

        assert delivery_result.decision == DecisionType.BLOCK
        assert address_result.decision == DecisionType.BLOCK

    def test_engine_allows_fully_verified_claim(
        self, sample_dispute, sample_order, sample_shipment_delivered
    ):
        """When delivery, address, HATEOAS, and citations are verified, engine returns ALLOW."""
        engine = PolicyEngine()
        claim = ExtractedClaim(
            claim_id="CLM-PASS",
            claim_type=ClaimType.DELIVERY_COMPLETED,
            factual_assertion="Item delivered with carrier USPS tracking 94001118992231001.",
            supporting_sources=[
                SourceCitation(
                    source_type=SourceType.CARRIER_TRACKING,
                    source_identifier="TRK-94001118992231001",
                    field_path="delivery_timestamp",
                    extracted_value="2026-10-20T11:45:00Z",
                )
            ],
        )

        evaluation = engine.evaluate(
            dispute=sample_dispute,
            order=sample_order,
            shipment=sample_shipment_delivered,
            claims=[claim],
            target_action="provide_evidence",
        )

        assert evaluation.overall_decision == DecisionType.ALLOW
        assert all(c.decision == DecisionType.ALLOW for c in evaluation.check_results)

    def test_engine_evaluates_against_real_sandbox_fixture(self, sample_order, sample_shipment_label_created):
        """Loads real sandbox fixture docs/fixtures/real_sandbox_dispute_inr.json into DisputeCase and evaluates."""
        fixture_path = Path("docs/fixtures/real_sandbox_dispute_inr.json")
        assert fixture_path.exists()
        raw_data = json.loads(fixture_path.read_text(encoding="utf-8"))

        dispute_case = DisputeCase.from_paypal_response(raw_data)

        assert dispute_case.dispute_id == "PP-R-NKI-10193390"
        assert dispute_case.status == DisputeStatus.WAITING_FOR_SELLER_RESPONSE
        assert dispute_case.has_action("provide_evidence")

        engine = PolicyEngine()
        claim = ExtractedClaim(
            claim_id="CLM-REAL-INR",
            claim_type=ClaimType.DELIVERY_COMPLETED,
            factual_assertion="Delivered.",
            supporting_sources=[
                SourceCitation(
                    source_type=SourceType.CARRIER_TRACKING,
                    source_identifier="TRK-94001118992231001",
                    field_path="tracking_status",
                    extracted_value="LABEL_CREATED",
                )
            ],
        )

        evaluation = engine.evaluate(
            dispute=dispute_case,
            order=sample_order,
            shipment=sample_shipment_label_created,
            claims=[claim],
        )

        # Confirm hard block on real fixture with label-created shipment
        assert evaluation.overall_decision == DecisionType.BLOCK


# ============================================================================
# 7. Domain Models Validation & Edge Case Tests
# ============================================================================

class TestDomainModelsAndEdgeCases:
    """Verifies domain model validation, normalization, and invariant edge cases."""

    def test_money_validation(self):
        """Rejects negative amounts and invalid currency codes."""
        with pytest.raises(ValueError, match="negative"):
            Money(value=Decimal("-1.00"), currency_code="USD")

        with pytest.raises(ValueError, match="currency"):
            Money(value=Decimal("10.00"), currency_code="US")

        with pytest.raises(ValueError, match="currency"):
            Money(value=Decimal("10.00"), currency_code="123")

        m = Money(value=Decimal("15.50"), currency_code="eur")
        assert m.currency_code == "EUR"
        assert m.value == Decimal("15.50")

    def test_dispute_case_helpers(self, sample_dispute):
        """Verifies DisputeCase helper methods."""
        assert sample_dispute.is_seller_response_required() is True
        sample_dispute.status = DisputeStatus.UNDER_REVIEW
        assert sample_dispute.is_seller_response_required() is False

        # Link matching with hyphens and case
        assert sample_dispute.has_action("provide-evidence") is True
        assert sample_dispute.has_action("PROVIDE_EVIDENCE") is True
        assert sample_dispute.has_action("nonexistent_action") is False
        assert sample_dispute.get_action_link("nonexistent_action") is None

    def test_dispute_from_paypal_response_edge_cases(self):
        """Verifies from_paypal_response error and fallback handling."""
        with pytest.raises(ValueError, match="missing required 'dispute_id'"):
            DisputeCase.from_paypal_response({})

        raw = {
            "dispute_id": "PP-TEST-123",
            "dispute_life_cycle_stage": "UNEXPECTED_STAGE",
            "status": "UNEXPECTED_STATUS",
            "reason": "CUSTOM_REASON_STRING",
            "dispute_amount": {"value": "99.95", "currency_code": "USD"},
            "seller_response_due_date": "not-an-iso-date",
            "evidences": [{"evidence_type": "PROOF_OF_SHIPMENT", "source": "SELLER"}],
            "links": [{"href": "https://api-m.sandbox.paypal.com/test", "rel": "self", "method": "GET"}],
            "disputed_transactions": [{"buyer_transaction_id": "TX-BUYER-1"}],
        }

        case = DisputeCase.from_paypal_response(raw)
        assert case.lifecycle_stage == DisputeLifecycleStage.INQUIRY
        assert case.status == DisputeStatus.OTHER
        assert case.reason == "CUSTOM_REASON_STRING"
        assert case.seller_response_due_date is None
        assert case.buyer_transaction_id == "TX-BUYER-1"
        assert case.disputed_transaction_id == "TX-BUYER-1"

    def test_address_normalization_edge_cases(self):
        """Verifies Address normalization with empty fields."""
        addr = Address()
        assert addr.normalized_postal_code() is None
        assert addr.normalized_country() is None
        assert addr.normalized_city() is None
        assert addr.normalized_recipient_name() is None
        assert addr.normalized_line1() is None

        addr2 = Address(
            recipient_name="Mr. John Doe, Jr.",
            line1="123 Main St., Apt. #4B",
            postal_code="SW1A 1AA",
            country_code="gb",
            city="London",
        )
        assert addr2.normalized_postal_code() == "SW1A1AA"
        assert addr2.normalized_country() == "GB"
        assert addr2.normalized_city() == "london"
        assert addr2.normalized_recipient_name() == "mr john doe jr"
        assert addr2.normalized_line1() == "123 main st apt 4b"

    def test_overall_evaluation_methods(self):
        """Verifies OverallPolicyEvaluation methods."""
        res_block = PolicyCheckResult(
            decision=DecisionType.BLOCK,
            rule_identifier="RULE_1",
            explanation="Failed",
            violated_invariants=["INV_1"],
        )
        res_allow = PolicyCheckResult(
            decision=DecisionType.ALLOW,
            rule_identifier="RULE_2",
            explanation="Passed",
            violated_invariants=[],
        )

        eval_block = OverallPolicyEvaluation(
            dispute_id="PP-1",
            overall_decision=DecisionType.BLOCK,
            check_results=[res_block, res_allow],
            advisories=[
                PolicyCheckResult(
                    decision=DecisionType.REVIEW,
                    rule_identifier="RULE_ADV",
                    explanation="Advisory note",
                    violated_invariants=["INV_ADV_1"],
                    is_advisory=True,
                )
            ],
            summary="Blocked",
        )
        assert eval_block.has_blocking_violations() is True
        assert "INV_1" in eval_block.get_violations()
        assert "INV_ADV_1" in eval_block.get_violations()

    def test_delivery_proof_with_returned_or_exception_status(self, sample_order, sample_shipment_delivered):
        """TrackingStatus.RETURNED or EXCEPTION blocks delivery claim."""
        sample_shipment_delivered.tracking_status = TrackingStatus.RETURNED
        invariant = DeliveryProofInvariant()
        claim = ExtractedClaim(
            claim_id="CLM-RET",
            claim_type=ClaimType.DELIVERY_COMPLETED,
            factual_assertion="Delivered.",
        )
        result = invariant.evaluate(claim=claim, shipment=sample_shipment_delivered, order=sample_order)
        assert result.decision == DecisionType.BLOCK
        assert "DELIVERY_STATUS_INVALID" in result.violated_invariants

    def test_hateoas_invalid_url_scheme_blocked(self, sample_dispute):
        """HATEOAS link without http/https is blocked."""
        sample_dispute.available_hateoas_actions = [
            HATEOASLink(href="ftp://invalid-server.com", rel="provide_evidence")
        ]
        invariant = HATEOASActionInvariant(target_action="provide_evidence")
        result = invariant.evaluate(dispute=sample_dispute)
        assert result.decision == DecisionType.BLOCK
        assert "HATEOAS_LINK_INVALID_URL" in result.violated_invariants

    def test_policy_engine_review_summary_branch(self, sample_dispute, sample_order, sample_shipment_delivered):
        """Engine with only REVIEW results produces appropriate REVIEW summary."""
        # Cause only a REVIEW by omitting transaction timestamp on >= $750 order
        sample_order.gross_amount = Money(value=Decimal("800.00"), currency_code="USD")
        sample_order.order_timestamp = None
        sample_shipment_delivered.recipient_signature_present = False

        engine = PolicyEngine()
        claim = ExtractedClaim(
            claim_id="CLM-OK",
            claim_type=ClaimType.DELIVERY_COMPLETED,
            factual_assertion="Delivered.",
            supporting_sources=[
                SourceCitation(
                    source_type=SourceType.CARRIER_TRACKING,
                    source_identifier="TRK-94001118992231001",
                    field_path="delivery_timestamp",
                    extracted_value="2026-10-20T11:45:00Z",
                )
            ],
        )

        evaluation = engine.evaluate(
            dispute=sample_dispute,
            order=sample_order,
            shipment=sample_shipment_delivered,
            claims=[claim],
        )

        assert evaluation.overall_decision == DecisionType.REVIEW
        assert "review" in evaluation.summary.lower()


# ============================================================================
# 8. Milestone 2.1 Hardening Tests
# ============================================================================

class TestHATEOASActionHardening:
    """Verifies hardened HATEOAS validation: lifecycle states, HTTPS, host constraints,
    exact dispute ID path, and supporting action distinctions."""

    def test_hateoas_blocked_when_inquiry_and_open(self, sample_dispute):
        """INQUIRY + OPEN is the buyer-seller discussion phase; provide-evidence is blocked."""
        sample_dispute.lifecycle_stage = DisputeLifecycleStage.INQUIRY
        sample_dispute.status = DisputeStatus.OPEN

        invariant = HATEOASActionInvariant(target_action="provide_evidence")
        result = invariant.evaluate(dispute=sample_dispute)

        assert result.decision == DecisionType.BLOCK
        assert "DISPUTE_INQUIRY_OPEN_SELLER_INELIGIBLE" in result.violated_invariants
        assert "inquiry" in result.explanation.lower()

    def test_hateoas_blocked_when_waiting_for_buyer_response(self, sample_dispute):
        """WAITING_FOR_BUYER_RESPONSE blocks merchant evidence submission."""
        sample_dispute.status = DisputeStatus.WAITING_FOR_BUYER_RESPONSE

        invariant = HATEOASActionInvariant(target_action="provide_evidence")
        result = invariant.evaluate(dispute=sample_dispute)

        assert result.decision == DecisionType.BLOCK
        assert "DISPUTE_STATUS_SELLER_INELIGIBLE" in result.violated_invariants

    def test_hateoas_blocked_when_under_review(self, sample_dispute):
        """UNDER_REVIEW blocks merchant evidence submission."""
        sample_dispute.status = DisputeStatus.UNDER_REVIEW

        invariant = HATEOASActionInvariant(target_action="provide_evidence")
        result = invariant.evaluate(dispute=sample_dispute)

        assert result.decision == DecisionType.BLOCK
        assert "DISPUTE_STATUS_SELLER_INELIGIBLE" in result.violated_invariants

    def test_hateoas_supporting_actions_allowed_in_open_inquiry(self, sample_dispute):
        """Supporting actions like send_message and make_offer ARE allowed in INQUIRY + OPEN."""
        sample_dispute.lifecycle_stage = DisputeLifecycleStage.INQUIRY
        sample_dispute.status = DisputeStatus.OPEN
        sample_dispute.available_hateoas_actions.append(
            HATEOASLink(
                href="https://api-m.sandbox.paypal.com/v1/customer/disputes/PP-R-NKI-10193390/send-message",
                rel="send_message",
                method="POST",
            )
        )

        invariant = HATEOASActionInvariant(target_action="send_message")
        result = invariant.evaluate(dispute=sample_dispute)

        assert result.decision == DecisionType.ALLOW

    def test_hateoas_insecure_http_blocked_by_default(self, sample_dispute):
        """HTTP scheme is blocked by default; HTTPS required."""
        sample_dispute.available_hateoas_actions = [
            HATEOASLink(
                href="http://api-m.sandbox.paypal.com/v1/customer/disputes/PP-R-NKI-10193390/provide-evidence",
                rel="provide_evidence",
                method="POST",
            )
        ]
        invariant = HATEOASActionInvariant(target_action="provide_evidence", allow_insecure_http=False)
        result = invariant.evaluate(dispute=sample_dispute)

        assert result.decision == DecisionType.BLOCK
        assert "HATEOAS_INSECURE_URL" in result.violated_invariants

    def test_hateoas_insecure_http_allowed_when_explicitly_configured(self, sample_dispute):
        """HTTP scheme can be allowed in local test environments if explicitly configured."""
        sample_dispute.available_hateoas_actions = [
            HATEOASLink(
                href="http://api-m.sandbox.paypal.com/v1/customer/disputes/PP-R-NKI-10193390/provide-evidence",
                rel="provide_evidence",
                method="POST",
            )
        ]
        invariant = HATEOASActionInvariant(target_action="provide_evidence", allow_insecure_http=True)
        result = invariant.evaluate(dispute=sample_dispute)

        assert result.decision == DecisionType.ALLOW

    def test_hateoas_unauthorized_host_blocked(self, sample_dispute):
        """Action link targeting unauthorized or phishing domain is blocked."""
        sample_dispute.available_hateoas_actions = [
            HATEOASLink(
                href="https://attacker-controlled-site.com/v1/customer/disputes/PP-R-NKI-10193390/provide-evidence",
                rel="provide_evidence",
                method="POST",
            )
        ]
        invariant = HATEOASActionInvariant(target_action="provide_evidence")
        result = invariant.evaluate(dispute=sample_dispute)

        assert result.decision == DecisionType.BLOCK
        assert "HATEOAS_UNAUTHORIZED_HOST" in result.violated_invariants

    def test_hateoas_exact_path_segment_dispute_id_validation(self, sample_dispute):
        """Dispute ID must match the exact path segment, not merely a substring in URL."""
        sample_dispute.dispute_id = "PP-1"
        sample_dispute.available_hateoas_actions = [
            HATEOASLink(
                href="https://api-m.sandbox.paypal.com/v1/customer/disputes/PP-1999999/provide-evidence",
                rel="provide_evidence",
                method="POST",
            )
        ]
        invariant = HATEOASActionInvariant(target_action="provide_evidence")
        result = invariant.evaluate(dispute=sample_dispute)

        assert result.decision == DecisionType.BLOCK
        assert "HATEOAS_LINK_DISPUTE_MISMATCH" in result.violated_invariants

    def test_hateoas_requested_evidence_type_validation(self, sample_dispute):
        """Validates targeted evidence type against PayPal requested evidence types."""
        sample_dispute.requested_evidence_types = ["PROOF_OF_FULFILLMENT"]
        sample_dispute.requested_evidence_sources = ["REQUESTED_FROM_SELLER"]

        invariant = HATEOASActionInvariant(
            target_action="provide_evidence",
            target_evidence_type="PROOF_OF_DAMAGE",  # Mismatch
        )
        result = invariant.evaluate(dispute=sample_dispute)

        assert result.decision == DecisionType.REVIEW
        assert "EVIDENCE_TYPE_NOT_REQUESTED" in result.violated_invariants


class TestSignatureAssessmentHardening:
    """Verifies signature threshold boundary (OVER $750 USD), jurisdiction,
    goods type, pre vs post Jan 26 2026 distinction, and non-blocking invariant."""

    def test_signature_boundary_749_99_allowed(self, sample_order, sample_shipment_delivered):
        """$749.99 is under $750 threshold: ALLOW."""
        sample_order.gross_amount = Money(value=Decimal("749.99"), currency_code="USD")
        sample_shipment_delivered.recipient_signature_present = False

        invariant = SignatureAssessmentInvariant()
        result = invariant.evaluate(order=sample_order, shipment=sample_shipment_delivered)

        assert result.decision == DecisionType.ALLOW
        assert "below" in result.explanation.lower() or "not required" in result.explanation.lower()

    def test_signature_boundary_750_00_allowed(self, sample_order, sample_shipment_delivered):
        """$750.00 is NOT OVER $750: ALLOW (guidance says OVER $750 USD)."""
        sample_order.gross_amount = Money(value=Decimal("750.00"), currency_code="USD")
        sample_shipment_delivered.recipient_signature_present = False

        invariant = SignatureAssessmentInvariant()
        result = invariant.evaluate(order=sample_order, shipment=sample_shipment_delivered)

        assert result.decision == DecisionType.ALLOW

    def test_signature_boundary_750_01_pre_2026_review_deficiency(self, sample_order, sample_shipment_delivered):
        """$750.01 is OVER $750; pre-Jan 26 2026 without signature is Seller Protection deficiency."""
        sample_order.gross_amount = Money(value=Decimal("750.01"), currency_code="USD")
        sample_order.order_timestamp = datetime(2025, 11, 15, 10, 0, 0, tzinfo=timezone.utc)
        sample_shipment_delivered.recipient_signature_present = False

        invariant = SignatureAssessmentInvariant(merchant_jurisdiction="US")
        result = invariant.evaluate(order=sample_order, shipment=sample_shipment_delivered)

        assert result.decision == DecisionType.REVIEW
        assert "SIGNATURE_SELLER_PROTECTION_DEFICIENCY" in result.violated_invariants
        assert "deficiency" in result.explanation.lower()

    def test_signature_boundary_750_01_post_2026_advisory(self, sample_order, sample_shipment_delivered):
        """$750.01 is OVER $750; post-Jan 26 2026 without signature is advisory REVIEW (never BLOCK)."""
        sample_order.gross_amount = Money(value=Decimal("750.01"), currency_code="USD")
        sample_order.order_timestamp = datetime(2026, 4, 1, 10, 0, 0, tzinfo=timezone.utc)
        sample_shipment_delivered.recipient_signature_present = False

        invariant = SignatureAssessmentInvariant(merchant_jurisdiction="US")
        result = invariant.evaluate(order=sample_order, shipment=sample_shipment_delivered)

        assert result.decision == DecisionType.REVIEW
        assert "SIGNATURE_ADVISORY_POST_2026" in result.violated_invariants

    def test_signature_goods_type_digital_goods_allowed(self, sample_order, sample_shipment_delivered):
        """Digital goods / intangible services do not require physical signature confirmation."""
        sample_order.gross_amount = Money(value=Decimal("1500.00"), currency_code="USD")
        sample_order.order_timestamp = datetime(2025, 10, 1, 10, 0, 0, tzinfo=timezone.utc)
        sample_shipment_delivered.recipient_signature_present = False

        invariant = SignatureAssessmentInvariant(goods_type="DIGITAL_GOODS")
        result = invariant.evaluate(order=sample_order, shipment=sample_shipment_delivered)

        assert result.decision == DecisionType.ALLOW
        assert "digital" in result.explanation.lower()

    def test_signature_unmapped_currency_returns_indeterminate_review(self, sample_order, sample_shipment_delivered):
        """Unmapped currency without known threshold returns indeterminate REVIEW."""
        sample_order.gross_amount = Money(value=Decimal("800.00"), currency_code="XYZ")
        sample_order.order_timestamp = datetime(2026, 2, 1, 10, 0, 0, tzinfo=timezone.utc)
        sample_shipment_delivered.recipient_signature_present = False

        invariant = SignatureAssessmentInvariant()
        result = invariant.evaluate(order=sample_order, shipment=sample_shipment_delivered)

        assert result.decision == DecisionType.REVIEW
        assert "SIGNATURE_CURRENCY_INDETERMINATE" in result.violated_invariants

    def test_signature_never_returns_block(self, sample_order, sample_shipment_delivered):
        """Signature assessment must NEVER return BLOCK, ensuring it remains non-blocking."""
        sample_order.gross_amount = Money(value=Decimal("100000.00"), currency_code="USD")
        sample_order.order_timestamp = datetime(2025, 1, 1, 10, 0, 0, tzinfo=timezone.utc)
        sample_shipment_delivered.recipient_signature_present = False

        invariant = SignatureAssessmentInvariant()
        result = invariant.evaluate(order=sample_order, shipment=sample_shipment_delivered)

        assert result.decision != DecisionType.BLOCK


class TestAddressConsistencyHardening:
    """Verifies that postal/country match is clearly framed as a destination delivery area check,
    compares recipient names, and disclaims Seller Protection guarantees."""

    def test_address_explanation_contains_seller_protection_disclaimer(self, sample_order, sample_shipment_delivered):
        """Passing address check must explicitly disclaim Seller Protection guarantees."""
        invariant = AddressMatchInvariant(policy=AddressMatchPolicy.STANDARD)
        result = invariant.evaluate(order=sample_order, shipment=sample_shipment_delivered)

        assert result.decision == DecisionType.ALLOW
        assert "does not guarantee seller protection" in result.explanation.lower()
        assert "delivery area" in result.explanation.lower()

    def test_address_recipient_name_mismatch_in_strict_mode(self, sample_order, sample_shipment_delivered):
        """STRICT mode blocks when recipient names are completely different."""
        sample_order.shipping_address.recipient_name = "Alice Smith"
        sample_shipment_delivered.shipment_address.recipient_name = "Bob Jones"

        invariant = AddressMatchInvariant(policy=AddressMatchPolicy.STRICT)
        result = invariant.evaluate(order=sample_order, shipment=sample_shipment_delivered)

        assert result.decision == DecisionType.BLOCK
        assert "ADDRESS_RECIPIENT_NAME_MISMATCH" in result.violated_invariants

    def test_address_recipient_name_differs_in_standard_mode(self, sample_order, sample_shipment_delivered):
        """STANDARD mode produces REVIEW when recipient names differ."""
        sample_order.shipping_address.recipient_name = "Alice Smith"
        sample_shipment_delivered.shipment_address.recipient_name = "Bob Jones"

        invariant = AddressMatchInvariant(policy=AddressMatchPolicy.STANDARD)
        result = invariant.evaluate(order=sample_order, shipment=sample_shipment_delivered)

        assert result.decision == DecisionType.REVIEW
        assert "ADDRESS_RECIPIENT_NAME_DIFFERS" in result.violated_invariants

    def test_address_recipient_name_match_allowed(self, sample_order, sample_shipment_delivered):
        """Matching recipient names pass cleanly."""
        sample_order.shipping_address.recipient_name = "John Doe"
        sample_shipment_delivered.shipment_address.recipient_name = "John Doe"

        invariant = AddressMatchInvariant(policy=AddressMatchPolicy.STANDARD)
        result = invariant.evaluate(order=sample_order, shipment=sample_shipment_delivered)

        assert result.decision == DecisionType.ALLOW


class TestCitationIntegrityHardening:
    """Verifies field path traversal, factual value reconciliation, and unverified/conflicting sources."""

    def test_citation_field_path_nonexistent_blocked(self, sample_shipment_delivered):
        """Citation referencing a field path that does not exist in the source record is blocked."""
        claim = ExtractedClaim(
            claim_id="CLM-NOPATH",
            claim_type=ClaimType.DELIVERY_COMPLETED,
            factual_assertion="Delivered.",
            supporting_sources=[
                SourceCitation(
                    source_type=SourceType.CARRIER_TRACKING,
                    source_identifier="TRK-94001118992231001",
                    field_path="nonexistent_attribute_name",
                    extracted_value="DELIVERED",
                )
            ],
        )

        invariant = CitationIntegrityInvariant()
        result = invariant.evaluate(claim=claim, available_sources={"TRK-94001118992231001": sample_shipment_delivered})

        assert result.decision == DecisionType.BLOCK
        assert "CITATION_FIELD_PATH_NONEXISTENT" in result.violated_invariants

    def test_citation_field_path_nested_resolution(self, sample_shipment_delivered):
        """Resolves nested field paths like shipment_address.postal_code."""
        claim = ExtractedClaim(
            claim_id="CLM-NESTED",
            claim_type=ClaimType.DELIVERY_COMPLETED,
            factual_assertion="Delivered to 95131.",
            supporting_sources=[
                SourceCitation(
                    source_type=SourceType.CARRIER_TRACKING,
                    source_identifier="TRK-94001118992231001",
                    field_path="shipment_address.postal_code",
                    extracted_value="95131",
                )
            ],
        )

        invariant = CitationIntegrityInvariant()
        result = invariant.evaluate(claim=claim, available_sources={"TRK-94001118992231001": sample_shipment_delivered})

        assert result.decision == DecisionType.ALLOW

    def test_citation_value_mismatch_contradiction_blocked(self, sample_shipment_label_created):
        """Factual contradiction: citation claims extracted value was DELIVERED, but source record contains LABEL_CREATED."""
        claim = ExtractedClaim(
            claim_id="CLM-CONTRADICT",
            claim_type=ClaimType.DELIVERY_COMPLETED,
            factual_assertion="Package was delivered.",
            supporting_sources=[
                SourceCitation(
                    source_type=SourceType.CARRIER_TRACKING,
                    source_identifier="TRK-94001118992231001",
                    field_path="tracking_status",
                    extracted_value="DELIVERED",  # Contradicts real source value of LABEL_CREATED!
                )
            ],
        )

        invariant = CitationIntegrityInvariant()
        result = invariant.evaluate(claim=claim, available_sources={"TRK-94001118992231001": sample_shipment_label_created})

        assert result.decision == DecisionType.BLOCK
        assert "CITATION_VALUE_MISMATCH" in result.violated_invariants
        assert "contradiction" in result.explanation.lower()

    def test_citation_unverified_source_triggers_review(self, sample_shipment_delivered):
        """Citation marked UNVERIFIED triggers REVIEW."""
        claim = ExtractedClaim(
            claim_id="CLM-UNVER",
            claim_type=ClaimType.DELIVERY_COMPLETED,
            factual_assertion="Delivered.",
            supporting_sources=[
                SourceCitation(
                    source_type=SourceType.CARRIER_TRACKING,
                    source_identifier="TRK-94001118992231001",
                    field_path="tracking_status",
                    extracted_value="DELIVERED",
                    verification_status=VerificationStatus.UNVERIFIED,
                )
            ],
        )

        invariant = CitationIntegrityInvariant()
        result = invariant.evaluate(claim=claim, available_sources={"TRK-94001118992231001": sample_shipment_delivered})

        assert result.decision == DecisionType.REVIEW
        assert "CITATION_SOURCE_UNVERIFIED" in result.violated_invariants

    def test_citation_rejected_source_blocked(self, sample_shipment_delivered):
        """Citation marked REJECTED is blocked."""
        claim = ExtractedClaim(
            claim_id="CLM-REJ",
            claim_type=ClaimType.DELIVERY_COMPLETED,
            factual_assertion="Delivered.",
            supporting_sources=[
                SourceCitation(
                    source_type=SourceType.CARRIER_TRACKING,
                    source_identifier="TRK-94001118992231001",
                    field_path="tracking_status",
                    extracted_value="DELIVERED",
                    verification_status=VerificationStatus.REJECTED,
                )
            ],
        )

        invariant = CitationIntegrityInvariant()
        result = invariant.evaluate(claim=claim, available_sources={"TRK-94001118992231001": sample_shipment_delivered})

        assert result.decision == DecisionType.BLOCK
        assert "CITATION_SOURCE_REJECTED" in result.violated_invariants


class TestSeparatedDecisionDimensions:
    """Verifies that factual claim validation and PayPal submission readiness remain distinguishable,
    and non-blocking advisories are preserved independently."""

    def test_factually_supported_claim_retains_allow_when_dispute_state_blocks_action(
        self, sample_dispute, sample_order, sample_shipment_delivered
    ):
        """Case: Evidence is factually proven (DELIVERED, verified citations, matching address),
        BUT dispute is in INQUIRY + OPEN where provide_evidence is not allowed.
        Factual readiness MUST be ALLOW; Action readiness MUST be BLOCK; Overall is BLOCK.
        """
        sample_dispute.lifecycle_stage = DisputeLifecycleStage.INQUIRY
        sample_dispute.status = DisputeStatus.OPEN

        engine = PolicyEngine()
        claim = ExtractedClaim(
            claim_id="CLM-PROVEN",
            claim_type=ClaimType.DELIVERY_COMPLETED,
            factual_assertion="Package delivered on time.",
            supporting_sources=[
                SourceCitation(
                    source_type=SourceType.CARRIER_TRACKING,
                    source_identifier="TRK-94001118992231001",
                    field_path="tracking_status",
                    extracted_value="DELIVERED",
                )
            ],
        )

        evaluation: OverallPolicyEvaluation = engine.evaluate(
            dispute=sample_dispute,
            order=sample_order,
            shipment=sample_shipment_delivered,
            claims=[claim],
            target_action="provide_evidence",
        )

        # Distinct dimensions
        assert evaluation.factual_readiness == DecisionType.ALLOW
        assert evaluation.is_factually_supported() is True

        assert evaluation.action_readiness == DecisionType.BLOCK
        assert evaluation.is_action_eligible() is False

        assert evaluation.overall_decision == DecisionType.BLOCK
        assert evaluation.is_ready_for_submission() is False

    def test_action_eligible_dispute_blocks_when_claim_is_unsupported(
        self, sample_dispute, sample_order, sample_shipment_label_created
    ):
        """Case: Dispute allows provide-evidence, but claim claims delivery when status is Label Created.
        Action readiness is ALLOW; Factual readiness is BLOCK; Overall is BLOCK.
        """
        engine = PolicyEngine()
        claim = ExtractedClaim(
            claim_id="CLM-FALSE",
            claim_type=ClaimType.DELIVERY_COMPLETED,
            factual_assertion="Delivered.",
            supporting_sources=[
                SourceCitation(
                    source_type=SourceType.CARRIER_TRACKING,
                    source_identifier="TRK-94001118992231001",
                    field_path="tracking_status",
                    extracted_value="LABEL_CREATED",
                )
            ],
        )

        evaluation = engine.evaluate(
            dispute=sample_dispute,
            order=sample_order,
            shipment=sample_shipment_label_created,
            claims=[claim],
            target_action="provide_evidence",
        )

        assert evaluation.action_readiness == DecisionType.ALLOW
        assert evaluation.is_action_eligible() is True

        assert evaluation.factual_readiness == DecisionType.BLOCK
        assert evaluation.is_factually_supported() is False

        assert evaluation.overall_decision == DecisionType.BLOCK

    def test_advisories_isolated_from_blocking_decisions(
        self, sample_dispute, sample_order, sample_shipment_delivered
    ):
        """Non-blocking advisories (like missing signature for high value post-2026) appear in advisories list
        without blocking factual readiness."""
        sample_order.gross_amount = Money(value=Decimal("850.00"), currency_code="USD")
        sample_order.order_timestamp = datetime(2026, 3, 1, 10, 0, 0, tzinfo=timezone.utc)
        sample_shipment_delivered.recipient_signature_present = False

        engine = PolicyEngine()
        claim = ExtractedClaim(
            claim_id="CLM-VALID",
            claim_type=ClaimType.DELIVERY_COMPLETED,
            factual_assertion="Delivered.",
            supporting_sources=[
                SourceCitation(
                    source_type=SourceType.CARRIER_TRACKING,
                    source_identifier="TRK-94001118992231001",
                    field_path="tracking_status",
                    extracted_value="DELIVERED",
                )
            ],
        )

        evaluation = engine.evaluate(
            dispute=sample_dispute,
            order=sample_order,
            shipment=sample_shipment_delivered,
            claims=[claim],
            target_action="provide_evidence",
        )

        assert evaluation.factual_readiness == DecisionType.ALLOW
        assert evaluation.action_readiness == DecisionType.ALLOW
        assert evaluation.has_advisories() is True
        assert len(evaluation.advisories) == 1
        assert evaluation.advisories[0].rule_identifier == "RULE_SIGNATURE_ASSESSMENT"
        assert evaluation.overall_decision == DecisionType.REVIEW  # Promoted to REVIEW for merchant awareness


