"""Tests for Docket's cross-source evidence reconciler (Milestone 3).

Following TDD methodology (tdd-workflow):
Validates multi-key correlation, discrepancy detection, shipment and refund linking,
automated source citation generation, and integration with the deterministic policy engine.
"""

from __future__ import annotations

from datetime import datetime, timezone, timedelta
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
)
from docket.models.evidence import (
    Address,
    ClaimType,
    CustomerMessageRecord,
    ExtractedClaim,
    OrderRecord,
    RefundRecord,
    ShipmentRecord,
    SourceCitation,
    SourceType,
    TrackingStatus,
    VerificationStatus,
)
from docket.models.reconciliation import (
    CandidateMatch,
    DiscrepancySeverity,
    MatchConfidence,
    MatchStrategy,
    ReconciledDisputeBundle,
    ReconciliationDiscrepancy,
    ReconciliationStatus,
)
from docket.policy.engine import PolicyEngine
from docket.reconciliation.engine import EvidenceReconciler


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def sample_dispute() -> DisputeCase:
    return DisputeCase(
        dispute_id="PP-D-TEST-1001",
        reason=DisputeReason.MERCHANDISE_OR_SERVICE_NOT_RECEIVED,
        lifecycle_stage=DisputeLifecycleStage.CHARGEBACK,
        status=DisputeStatus.WAITING_FOR_SELLER_RESPONSE,
        dispute_amount=Money(value=Decimal("150.00"), currency_code="USD"),
        requested_evidence_types=["PROOF_OF_DELIVERY"],
        seller_response_due_date=datetime(2026, 11, 20, 12, 0, tzinfo=timezone.utc),
        available_hateoas_actions=[
            HATEOASLink(
                href="https://api-m.sandbox.paypal.com/v1/customer/disputes/PP-D-TEST-1001/provide-evidence",
                rel="provide_evidence",
                method="POST",
            )
        ],
        disputed_transaction_id="TX-SELLER-9999",
        seller_transaction_id="TX-SELLER-9999",
        buyer_transaction_id="TX-BUYER-8888",
        dispute_create_time=datetime(2026, 10, 20, 14, 0, tzinfo=timezone.utc),
        transaction_create_time=datetime(2026, 10, 15, 10, 30, tzinfo=timezone.utc),
        buyer_email="buyer@example.com",
        buyer_name="Alice Buyer",
        seller_email="merchant@example.com",
    )


@pytest.fixture
def sample_order() -> OrderRecord:
    return OrderRecord(
        order_id="ORD-2026-5544",
        paypal_transaction_id="TX-SELLER-9999",
        order_timestamp=datetime(2026, 10, 15, 10, 30, tzinfo=timezone.utc),
        gross_amount=Money(value=Decimal("150.00"), currency_code="USD"),
        customer_email="buyer@example.com",
        customer_name="Alice Buyer",
        shipping_address=Address(
            recipient_name="Alice Buyer",
            line1="123 Market St",
            city="San Jose",
            state_or_province="CA",
            postal_code="95131",
            country_code="US",
        ),
        tracking_numbers=["TRK-FEDEX-123456"],
        items=[{"item_name": "Ergonomic Chair", "quantity": 1, "price": "150.00"}],
    )


@pytest.fixture
def sample_shipment() -> ShipmentRecord:
    return ShipmentRecord(
        internal_order_id="ORD-2026-5544",
        tracking_number="TRK-FEDEX-123456",
        carrier_name="FEDEX",
        tracking_status=TrackingStatus.DELIVERED,
        shipment_timestamp=datetime(2026, 10, 16, 9, 0, tzinfo=timezone.utc),
        delivery_timestamp=datetime(2026, 10, 18, 15, 30, tzinfo=timezone.utc),
        shipment_address=Address(
            recipient_name="Alice Buyer",
            line1="123 Market St",
            city="San Jose",
            state_or_province="CA",
            postal_code="95131",
            country_code="US",
        ),
        source_identifier="SRC-FEDEX-API",
        recipient_signature_present=True,
        signed_by="A. Buyer",
    )


@pytest.fixture
def sample_customer_message() -> CustomerMessageRecord:
    return CustomerMessageRecord(
        message_id="MSG-001",
        sender="CUSTOMER",
        recipient="MERCHANT",
        timestamp=datetime(2026, 10, 19, 11, 0, tzinfo=timezone.utc),
        subject="Where is my package?",
        content="I have not received my chair yet.",
        order_id="ORD-2026-5544",
        customer_email="buyer@example.com",
        source_identifier="ZENDESK-TICKET-44321",
    )


@pytest.fixture
def sample_refund() -> RefundRecord:
    return RefundRecord(
        refund_id="REF-9988",
        order_id="ORD-2026-5544",
        paypal_refund_id="PP-REF-1122",
        amount=Money(value=Decimal("20.00"), currency_code="USD"),
        refund_timestamp=datetime(2026, 10, 19, 12, 0, tzinfo=timezone.utc),
        reason="Partial shipping courtesy refund",
        status="COMPLETED",
        source_identifier="MERCHANT-LEDGER",
    )


# ---------------------------------------------------------------------------
# Unit Tests: Dispute Model Rich Metadata Parsing
# ---------------------------------------------------------------------------

class TestDisputeCaseMetadataExtraction:
    """Verify DisputeCase parses richer metadata from PayPal responses."""

    def test_parse_real_sandbox_fixture_rich_fields(self):
        fixture_path = Path("docs/fixtures/real_sandbox_dispute_inr.json")
        assert fixture_path.exists(), "Sandbox fixture must exist"
        with open(fixture_path, "r", encoding="utf-8") as f:
            raw_data = json.load(f)

        dispute = DisputeCase.from_paypal_response(raw_data)
        assert dispute.dispute_id == "PP-R-NKI-10193390"
        assert dispute.buyer_transaction_id == "4H384663R6471042S"
        assert dispute.seller_transaction_id == "4R073105U90937213"
        assert dispute.disputed_transaction_id == "4R073105U90937213"
        assert dispute.buyer_email == "sb-6oifq53423350@personal.example.com"
        assert dispute.buyer_name == "John Doe"
        assert dispute.seller_email == "sb-2mews53303427@business.example.com"
        assert dispute.dispute_create_time is not None
        assert dispute.transaction_create_time is not None
        assert len(dispute.raw_messages) > 0


# ---------------------------------------------------------------------------
# Unit Tests: Multi-Key Correlation Engine
# ---------------------------------------------------------------------------

class TestEvidenceReconcilerMatching:
    """Verify multi-key correlation strategies."""

    def test_exact_seller_transaction_id_match(self, sample_dispute, sample_order, sample_shipment):
        reconciler = EvidenceReconciler(
            orders=[sample_order],
            shipments=[sample_shipment],
        )

        bundle = reconciler.reconcile_dispute(sample_dispute)

        assert bundle.status == ReconciliationStatus.RECONCILED
        assert bundle.matched_order is not None
        assert bundle.matched_order.order_id == "ORD-2026-5544"
        assert bundle.primary_match is not None
        assert bundle.primary_match.strategy == MatchStrategy.EXACT_TRANSACTION_ID
        assert bundle.primary_match.confidence == 1.0
        assert bundle.primary_match.confidence_tier == MatchConfidence.EXACT
        assert len(bundle.matched_shipments) == 1
        assert bundle.matched_shipments[0].tracking_number == "TRK-FEDEX-123456"

    def test_exact_buyer_transaction_id_match(self, sample_dispute, sample_order):
        # Order stores buyer transaction ID instead of seller transaction ID
        sample_order.paypal_transaction_id = "TX-BUYER-8888"
        reconciler = EvidenceReconciler(orders=[sample_order])

        bundle = reconciler.reconcile_dispute(sample_dispute)

        assert bundle.status == ReconciliationStatus.RECONCILED
        assert bundle.matched_order.order_id == "ORD-2026-5544"
        assert bundle.primary_match.strategy == MatchStrategy.EXACT_TRANSACTION_ID
        assert bundle.primary_match.confidence == 1.0

    def test_secondary_match_email_amount_time_within_24h(self, sample_dispute, sample_order):
        # Transaction ID is missing in order (e.g. ERP has internal order ID only)
        sample_order.paypal_transaction_id = None
        # Order timestamp 2 hours before transaction create time
        sample_order.order_timestamp = sample_dispute.transaction_create_time - timedelta(hours=2)
        sample_order.customer_email = "buyer@example.com"
        sample_order.gross_amount = Money(value=Decimal("150.00"), currency_code="USD")

        reconciler = EvidenceReconciler(orders=[sample_order])
        bundle = reconciler.reconcile_dispute(sample_dispute)

        assert bundle.status == ReconciliationStatus.RECONCILED
        assert bundle.matched_order.order_id == "ORD-2026-5544"
        assert bundle.primary_match.strategy == MatchStrategy.SECONDARY_EMAIL_TIME_AMOUNT
        assert bundle.primary_match.confidence >= 0.85
        assert bundle.primary_match.confidence_tier == MatchConfidence.HIGH

    def test_secondary_match_email_amount_within_7_days(self, sample_dispute, sample_order):
        sample_order.paypal_transaction_id = None
        sample_order.order_timestamp = sample_dispute.transaction_create_time - timedelta(days=5)

        reconciler = EvidenceReconciler(orders=[sample_order])
        bundle = reconciler.reconcile_dispute(sample_dispute)

        assert bundle.status == ReconciliationStatus.RECONCILED
        assert bundle.primary_match.strategy == MatchStrategy.PARTIAL_EMAIL_AMOUNT
        assert 0.60 <= bundle.primary_match.confidence < 0.85
        assert bundle.primary_match.confidence_tier == MatchConfidence.MEDIUM

    def test_orphan_dispute_unlinked(self, sample_dispute):
        # Empty order catalog
        reconciler = EvidenceReconciler(orders=[])
        bundle = reconciler.reconcile_dispute(sample_dispute)

        assert bundle.status == ReconciliationStatus.ORPHAN_DISPUTE
        assert bundle.matched_order is None
        assert bundle.primary_match is None
        assert not bundle.is_reconciled()

    def test_ambiguous_matches_multiple_candidates(self, sample_dispute, sample_order):
        sample_order.paypal_transaction_id = None
        # Create a second similar order for the same buyer
        order2 = sample_order.model_copy(update={
            "order_id": "ORD-2026-9999",
            "order_timestamp": sample_dispute.transaction_create_time - timedelta(hours=1),
        })

        reconciler = EvidenceReconciler(orders=[sample_order, order2])
        bundle = reconciler.reconcile_dispute(sample_dispute)

        assert bundle.status == ReconciliationStatus.AMBIGUOUS
        assert bundle.is_ambiguous()
        assert len(bundle.candidate_matches) >= 2


# ---------------------------------------------------------------------------
# Unit Tests: Discrepancy Detection
# ---------------------------------------------------------------------------

class TestEvidenceReconcilerDiscrepancies:
    """Verify discrepancy and risk detection during reconciliation."""

    def test_amount_mismatch_detected(self, sample_dispute, sample_order):
        # Order is $200.00, dispute is $150.00 (partial dispute)
        sample_order.gross_amount = Money(value=Decimal("200.00"), currency_code="USD")
        reconciler = EvidenceReconciler(orders=[sample_order])

        bundle = reconciler.reconcile_dispute(sample_dispute)

        assert bundle.status == ReconciliationStatus.DISCREPANCY_DETECTED
        discrepancy_codes = [d.code for d in bundle.discrepancies]
        assert "AMOUNT_MISMATCH" in discrepancy_codes
        amount_disc = next(d for d in bundle.discrepancies if d.code == "AMOUNT_MISMATCH")
        assert amount_disc.severity == DiscrepancySeverity.WARNING

    def test_currency_mismatch_detected(self, sample_dispute, sample_order):
        # Order is EUR, dispute is USD
        sample_order.gross_amount = Money(value=Decimal("150.00"), currency_code="EUR")
        reconciler = EvidenceReconciler(orders=[sample_order])

        bundle = reconciler.reconcile_dispute(sample_dispute)

        assert bundle.status == ReconciliationStatus.DISCREPANCY_DETECTED
        discrepancy_codes = [d.code for d in bundle.discrepancies]
        assert "CURRENCY_MISMATCH" in discrepancy_codes
        curr_disc = next(d for d in bundle.discrepancies if d.code == "CURRENCY_MISMATCH")
        assert curr_disc.severity == DiscrepancySeverity.CRITICAL
        assert bundle.has_critical_discrepancies()

    def test_timeline_paradox_detected(self, sample_dispute, sample_order):
        # Order created 5 days AFTER dispute was opened (impossible timeline)
        sample_order.order_timestamp = sample_dispute.dispute_create_time + timedelta(days=5)
        reconciler = EvidenceReconciler(orders=[sample_order])

        bundle = reconciler.reconcile_dispute(sample_dispute)

        assert bundle.status == ReconciliationStatus.DISCREPANCY_DETECTED
        discrepancy_codes = [d.code for d in bundle.discrepancies]
        assert "TIMELINE_PARADOX" in discrepancy_codes
        time_disc = next(d for d in bundle.discrepancies if d.code == "TIMELINE_PARADOX")
        assert time_disc.severity == DiscrepancySeverity.CRITICAL

    def test_address_discrepancy_between_order_and_shipment(self, sample_dispute, sample_order, sample_shipment):
        # Shipment sent to different postal code
        sample_shipment.shipment_address = Address(
            recipient_name="Alice Buyer",
            line1="999 Different Ave",
            city="New York",
            state_or_province="NY",
            postal_code="10001",
            country_code="US",
        )

        reconciler = EvidenceReconciler(
            orders=[sample_order],
            shipments=[sample_shipment],
        )

        bundle = reconciler.reconcile_dispute(sample_dispute)
        discrepancy_codes = [d.code for d in bundle.discrepancies]
        assert "ADDRESS_MISMATCH" in discrepancy_codes


# ---------------------------------------------------------------------------
# Unit Tests: Multi-Source Linking (Shipments, Messages, Refunds)
# ---------------------------------------------------------------------------

class TestEvidenceReconcilerMultiSourceLinking:
    """Verify linking of carrier shipments, customer messages, and refund ledgers."""

    def test_multi_shipment_linking_and_primary_selection(self, sample_dispute, sample_order, sample_shipment):
        # Two shipments for one split order
        shipment2 = sample_shipment.model_copy(update={
            "tracking_number": "TRK-FEDEX-998877",
            "tracking_status": TrackingStatus.IN_TRANSIT,
        })
        sample_order.tracking_numbers = ["TRK-FEDEX-123456", "TRK-FEDEX-998877"]

        reconciler = EvidenceReconciler(
            orders=[sample_order],
            shipments=[sample_shipment, shipment2],
        )

        bundle = reconciler.reconcile_dispute(sample_dispute)

        assert len(bundle.matched_shipments) == 2
        # Delivered shipment is prioritized as primary
        primary = bundle.get_primary_shipment()
        assert primary is not None
        assert primary.tracking_status == TrackingStatus.DELIVERED
        assert primary.tracking_number == "TRK-FEDEX-123456"

    def test_customer_message_linking(self, sample_dispute, sample_order, sample_customer_message):
        reconciler = EvidenceReconciler(
            orders=[sample_order],
            communications=[sample_customer_message],
        )

        bundle = reconciler.reconcile_dispute(sample_dispute)

        assert len(bundle.matched_communications) == 1
        assert bundle.matched_communications[0].message_id == "MSG-001"
        assert "chair" in bundle.matched_communications[0].content

    def test_refund_record_linking(self, sample_dispute, sample_order, sample_refund):
        reconciler = EvidenceReconciler(
            orders=[sample_order],
            refunds=[sample_refund],
        )

        bundle = reconciler.reconcile_dispute(sample_dispute)

        assert len(bundle.matched_refunds) == 1
        assert bundle.matched_refunds[0].refund_id == "REF-9988"
        assert bundle.matched_refunds[0].amount.value == Decimal("20.00")


# ---------------------------------------------------------------------------
# Unit Tests: Automated Source Citation Generation
# ---------------------------------------------------------------------------

class TestAutomatedCitationGeneration:
    """Verify bundle converts matched records into verifiable SourceCitations."""

    def test_bundle_generates_source_citations(self, sample_dispute, sample_order, sample_shipment, sample_refund):
        reconciler = EvidenceReconciler(
            orders=[sample_order],
            shipments=[sample_shipment],
            refunds=[sample_refund],
        )

        bundle = reconciler.reconcile_dispute(sample_dispute)
        citations = bundle.to_citations()

        assert len(citations) >= 4
        source_types = [c.source_type for c in citations]
        assert SourceType.CARRIER_TRACKING in source_types
        assert SourceType.ORDER_INVOICE in source_types
        assert SourceType.REFUND_LEDGER in source_types

        # Check tracking status citation
        tracking_citation = next(
            c for c in citations
            if c.source_type == SourceType.CARRIER_TRACKING and c.field_path == "tracking_status"
        )
        assert tracking_citation.extracted_value == "DELIVERED"
        assert tracking_citation.verification_status == VerificationStatus.VERIFIED
        assert tracking_citation.source_identifier == "SRC-FEDEX-API"


# ---------------------------------------------------------------------------
# Unit Tests: End-to-End Integration (Reconciler -> PolicyEngine)
# ---------------------------------------------------------------------------

class TestReconcilerPolicyEngineIntegration:
    """Verify reconciled bundle feeds cleanly into the deterministic PolicyEngine."""

    def test_end_to_end_defining_scenario_label_created_blocked(self, sample_dispute, sample_order, sample_shipment):
        # Defining scenario: tracking is LABEL_CREATED
        sample_shipment.tracking_status = TrackingStatus.LABEL_CREATED
        sample_shipment.delivery_timestamp = None

        reconciler = EvidenceReconciler(
            orders=[sample_order],
            shipments=[sample_shipment],
        )
        bundle = reconciler.reconcile_dispute(sample_dispute)
        assert bundle.is_reconciled()

        # Propose delivery completion claim based on bundle
        claim = ExtractedClaim(
            claim_id="CLM-001",
            claim_type=ClaimType.DELIVERY_COMPLETED,
            factual_assertion="Item was delivered to buyer",
            supporting_sources=bundle.to_citations(),
        )

        engine = PolicyEngine()
        evaluation = engine.evaluate(
            dispute=sample_dispute,
            claim=claim,
            shipment=bundle.get_primary_shipment(),
            order=bundle.matched_order,
        )

        # Must be hard-blocked by PolicyEngine
        assert not evaluation.is_factually_supported()
        assert evaluation.factual_readiness.value == "BLOCK"
        rule_ids = [r.rule_identifier for r in evaluation.check_results if r.decision.value == "BLOCK"]
        assert "RULE_DELIVERY_PROOF" in rule_ids

    def test_end_to_end_verified_delivery_ready_for_submission(self, sample_dispute, sample_order, sample_shipment):
        reconciler = EvidenceReconciler(
            orders=[sample_order],
            shipments=[sample_shipment],
        )
        bundle = reconciler.reconcile_dispute(sample_dispute)
        assert bundle.is_reconciled()

        claim = ExtractedClaim(
            claim_id="CLM-002",
            claim_type=ClaimType.DELIVERY_COMPLETED,
            factual_assertion="Item delivered to Alice Buyer at 95131",
            supporting_sources=bundle.to_citations(),
        )

        engine = PolicyEngine()
        evaluation = engine.evaluate(
            dispute=sample_dispute,
            claim=claim,
            shipment=bundle.get_primary_shipment(),
            order=bundle.matched_order,
        )

        # Delivery verified and dispute WAITING_FOR_SELLER_RESPONSE -> Ready for submission
        assert evaluation.is_factually_supported()
        assert evaluation.is_action_eligible()
        assert evaluation.is_ready_for_submission()

    def test_real_sandbox_fixture_reconciliation_and_evaluation(self):
        fixture_path = Path("docs/fixtures/real_sandbox_dispute_inr.json")
        with open(fixture_path, "r", encoding="utf-8") as f:
            raw_data = json.load(f)

        dispute = DisputeCase.from_paypal_response(raw_data)

        # Create simulated merchant order matching real transaction ID
        real_order = OrderRecord(
            order_id="ORD-SHOP-REAL-001",
            paypal_transaction_id=dispute.seller_transaction_id,  # "4R073105U90937213"
            order_timestamp=dispute.transaction_create_time,
            gross_amount=dispute.dispute_amount,  # $25.00 USD
            customer_email=dispute.buyer_email,
            customer_name=dispute.buyer_name,
            shipping_address=Address(
                recipient_name=dispute.buyer_name,
                line1="1 Main St",
                city="San Jose",
                state_or_province="CA",
                postal_code="95131",
                country_code="US",
            ),
            tracking_numbers=["TRK-USPS-REAL-999"],
        )

        real_shipment = ShipmentRecord(
            internal_order_id="ORD-SHOP-REAL-001",
            tracking_number="TRK-USPS-REAL-999",
            carrier_name="USPS",
            tracking_status=TrackingStatus.DELIVERED,
            shipment_timestamp=datetime(2026, 10, 19, 10, 0, tzinfo=timezone.utc),
            delivery_timestamp=datetime(2026, 10, 22, 14, 0, tzinfo=timezone.utc),
            shipment_address=Address(
                recipient_name=dispute.buyer_name,
                line1="1 Main St",
                city="San Jose",
                state_or_province="CA",
                postal_code="95131",
                country_code="US",
            ),
            source_identifier="USPS-API-FEED",
        )

        reconciler = EvidenceReconciler(
            orders=[real_order],
            shipments=[real_shipment],
        )

        bundle = reconciler.reconcile_dispute(dispute)
        assert bundle.is_reconciled()
        assert bundle.matched_order.order_id == "ORD-SHOP-REAL-001"
        assert bundle.primary_match.strategy == MatchStrategy.EXACT_TRANSACTION_ID
        assert len(bundle.matched_shipments) == 1

    def test_batch_reconcile_mixed_outcomes(self, sample_dispute, sample_order):
        orphan_dispute = sample_dispute.model_copy(update={
            "dispute_id": "PP-D-ORPHAN-999",
            "seller_transaction_id": "TX-NON-EXISTENT",
            "buyer_transaction_id": None,
            "disputed_transaction_id": "TX-NON-EXISTENT",
            "buyer_email": "nobody@example.com",
        })

        reconciler = EvidenceReconciler(orders=[sample_order])
        bundles = reconciler.reconcile_batch([sample_dispute, orphan_dispute])

        assert len(bundles) == 2
        assert bundles[0].is_reconciled()
        assert bundles[0].dispute_id == "PP-D-TEST-1001"
        assert not bundles[1].is_reconciled()
        assert bundles[1].status == ReconciliationStatus.ORPHAN_DISPUTE

    def test_tracking_numbers_deduplication(self, sample_dispute, sample_order, sample_shipment):
        sample_order.tracking_numbers = ["TRK-FEDEX-123456", "TRK-FEDEX-999999"]
        reconciler = EvidenceReconciler(
            orders=[sample_order],
            shipments=[sample_shipment],
        )

        bundle = reconciler.reconcile_dispute(sample_dispute)
        tracking_numbers = bundle.get_tracking_numbers()
        assert "TRK-FEDEX-123456" in tracking_numbers
        assert "TRK-FEDEX-999999" in tracking_numbers
        assert len(tracking_numbers) == 2

    def test_primary_shipment_priority_order(self, sample_order):
        s_label = ShipmentRecord(
            internal_order_id=sample_order.order_id,
            tracking_number="TRK-1",
            carrier_name="UPS",
            tracking_status=TrackingStatus.LABEL_CREATED,
            source_identifier="SRC-1",
        )
        s_transit = ShipmentRecord(
            internal_order_id=sample_order.order_id,
            tracking_number="TRK-2",
            carrier_name="UPS",
            tracking_status=TrackingStatus.IN_TRANSIT,
            source_identifier="SRC-2",
        )
        s_delivered = ShipmentRecord(
            internal_order_id=sample_order.order_id,
            tracking_number="TRK-3",
            carrier_name="UPS",
            tracking_status=TrackingStatus.DELIVERED,
            source_identifier="SRC-3",
        )

        bundle = ReconciledDisputeBundle(
            dispute_id="PP-D-TEST",
            status=ReconciliationStatus.RECONCILED,
            matched_order=sample_order,
            matched_shipments=[s_label, s_transit, s_delivered],
        )

        primary = bundle.get_primary_shipment()
        assert primary is not None
        assert primary.tracking_number == "TRK-3"
        assert primary.tracking_status == TrackingStatus.DELIVERED

    def test_case_insensitive_email_matching(self, sample_dispute, sample_order):
        sample_order.paypal_transaction_id = None
        sample_dispute.buyer_email = "  ALICE.BUYER@EXAMPLE.COM  "
        sample_order.customer_email = "alice.buyer@example.com"

        reconciler = EvidenceReconciler(orders=[sample_order])
        bundle = reconciler.reconcile_dispute(sample_dispute)

        assert bundle.is_reconciled()
        assert bundle.matched_order.order_id == sample_order.order_id

    def test_get_primary_shipment_empty_returns_none(self, sample_order):
        bundle = ReconciledDisputeBundle(
            dispute_id="PP-D-TEST-EMPTY",
            status=ReconciliationStatus.RECONCILED,
            matched_order=sample_order,
            matched_shipments=[],
        )
        assert bundle.get_primary_shipment() is None

    def test_secondary_match_currency_mismatch_detected(self, sample_dispute, sample_order):
        sample_order.paypal_transaction_id = None
        sample_order.gross_amount = Money(value=Decimal("150.00"), currency_code="CAD")
        reconciler = EvidenceReconciler(orders=[sample_order])

        bundle = reconciler.reconcile_dispute(sample_dispute)
        # Email matched (0.40) + time matched (0.25) -> candidate exists but has currency discrepancy
        assert bundle.status == ReconciliationStatus.DISCREPANCY_DETECTED
        assert "CURRENCY_MISMATCH" in [d.code for d in bundle.discrepancies]

    def test_secondary_match_timeline_paradox_detected(self, sample_dispute, sample_order):
        sample_order.paypal_transaction_id = None
        sample_order.order_timestamp = sample_dispute.dispute_create_time + timedelta(days=2)
        reconciler = EvidenceReconciler(orders=[sample_order])

        bundle = reconciler.reconcile_dispute(sample_dispute)
        # Even with secondary match, paradox is flagged
        assert bundle.status == ReconciliationStatus.DISCREPANCY_DETECTED
        assert "TIMELINE_PARADOX" in [d.code for d in bundle.discrepancies]

    def test_secondary_match_amount_mismatch_detected(self, sample_dispute, sample_order):
        sample_order.paypal_transaction_id = None
        sample_order.gross_amount = Money(value=Decimal("120.00"), currency_code="USD")
        reconciler = EvidenceReconciler(orders=[sample_order])

        bundle = reconciler.reconcile_dispute(sample_dispute)
        assert bundle.status == ReconciliationStatus.DISCREPANCY_DETECTED
        assert "AMOUNT_MISMATCH" in [d.code for d in bundle.discrepancies]

    def test_comms_linked_by_customer_email(self, sample_dispute, sample_order):
        comm = CustomerMessageRecord(
            message_id="MSG-EMAIL-01",
            sender="CUSTOMER",
            timestamp=datetime(2026, 10, 16, tzinfo=timezone.utc),
            content="Checking on delivery status",
            customer_email="buyer@example.com",
            order_id=None,  # No order ID on ticket
        )
        reconciler = EvidenceReconciler(orders=[sample_order], communications=[comm])
        bundle = reconciler.reconcile_dispute(sample_dispute)

        assert len(bundle.matched_communications) == 1
        assert bundle.matched_communications[0].message_id == "MSG-EMAIL-01"


