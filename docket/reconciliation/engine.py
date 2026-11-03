"""Cross-source evidence reconciler for Docket (Milestone 3).

Correlates PayPal disputes with internal merchant orders, carrier tracking shipments,
customer communication threads, and refund records using deterministic multi-key matching.
"""

from __future__ import annotations

from datetime import datetime, timezone, timedelta
from decimal import Decimal
from typing import Any, Dict, List, Optional

from docket.models.dispute import DisputeCase, Money
from docket.models.evidence import (
    CustomerMessageRecord,
    OrderRecord,
    RefundRecord,
    ShipmentRecord,
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


class EvidenceReconciler:
    """Multi-source evidence correlation and reconciliation engine."""

    def __init__(
        self,
        orders: Optional[List[OrderRecord]] = None,
        shipments: Optional[List[ShipmentRecord]] = None,
        communications: Optional[List[CustomerMessageRecord]] = None,
        refunds: Optional[List[RefundRecord]] = None,
    ) -> None:
        self.orders: List[OrderRecord] = orders or []
        self.shipments: List[ShipmentRecord] = shipments or []
        self.communications: List[CustomerMessageRecord] = communications or []
        self.refunds: List[RefundRecord] = refunds or []

        # Index orders by PayPal transaction ID
        self._orders_by_tx: Dict[str, List[OrderRecord]] = {}
        # Index orders by Order ID
        self._orders_by_id: Dict[str, OrderRecord] = {}
        for o in self.orders:
            self._orders_by_id[o.order_id] = o
            if o.paypal_transaction_id:
                clean_tx = o.paypal_transaction_id.strip()
                self._orders_by_tx.setdefault(clean_tx, []).append(o)

        # Index shipments by internal order ID
        self._shipments_by_order: Dict[str, List[ShipmentRecord]] = {}
        self._shipments_by_tracking: Dict[str, ShipmentRecord] = {}
        for s in self.shipments:
            self._shipments_by_order.setdefault(s.internal_order_id, []).append(s)
            if s.tracking_number:
                self._shipments_by_tracking[s.tracking_number.strip()] = s

        # Index communications by order ID and customer email
        self._comms_by_order: Dict[str, List[CustomerMessageRecord]] = {}
        self._comms_by_email: Dict[str, List[CustomerMessageRecord]] = {}
        for c in self.communications:
            if c.order_id:
                self._comms_by_order.setdefault(c.order_id, []).append(c)
            if c.customer_email:
                self._comms_by_email.setdefault(c.customer_email.strip().lower(), []).append(c)

        # Index refunds by order ID
        self._refunds_by_order: Dict[str, List[RefundRecord]] = {}
        for r in self.refunds:
            self._refunds_by_order.setdefault(r.order_id, []).append(r)

    def reconcile_dispute(self, dispute: DisputeCase) -> ReconciledDisputeBundle:
        """Reconcile a single PayPal dispute against merchant records."""
        candidate_matches: List[CandidateMatch] = []
        matched_tx_keys = [
            dispute.seller_transaction_id,
            dispute.buyer_transaction_id,
            dispute.disputed_transaction_id,
        ]

        # 1. Exact Transaction ID Search
        exact_matched_orders: List[OrderRecord] = []
        for tx_id in matched_tx_keys:
            if tx_id and tx_id.strip() in self._orders_by_tx:
                for ord_match in self._orders_by_tx[tx_id.strip()]:
                    if ord_match not in exact_matched_orders:
                        exact_matched_orders.append(ord_match)

        for ord_match in exact_matched_orders:
            discrepancies = self._evaluate_order_discrepancies(dispute, ord_match)
            candidate_matches.append(
                CandidateMatch(
                    order=ord_match,
                    strategy=MatchStrategy.EXACT_TRANSACTION_ID,
                    confidence=1.0,
                    confidence_tier=MatchConfidence.EXACT,
                    match_reasons=[f"Exact PayPal transaction ID match: {ord_match.paypal_transaction_id}"],
                    discrepancies=discrepancies,
                )
            )

        # 2. Secondary Multi-Attribute Search (if no exact matches found)
        if not candidate_matches:
            for order in self.orders:
                match_result = self._score_secondary_match(dispute, order)
                if match_result:
                    candidate_matches.append(match_result)

        # 3. Resolve candidates and status
        if not candidate_matches:
            return ReconciledDisputeBundle(
                dispute_id=dispute.dispute_id,
                status=ReconciliationStatus.ORPHAN_DISPUTE,
                matched_order=None,
                reconciled_at=datetime.now(timezone.utc),
            )

        # Sort candidates by confidence descending
        candidate_matches.sort(key=lambda c: c.confidence, reverse=True)

        # Ambiguity detection: if top 2 candidates have very close/identical confidence
        if (
            len(candidate_matches) >= 2
            and candidate_matches[0].confidence < 1.0
            and abs(candidate_matches[0].confidence - candidate_matches[1].confidence) < 0.05
        ):
            return ReconciledDisputeBundle(
                dispute_id=dispute.dispute_id,
                status=ReconciliationStatus.AMBIGUOUS,
                matched_order=None,
                candidate_matches=candidate_matches,
                reconciled_at=datetime.now(timezone.utc),
            )

        primary_match = candidate_matches[0]
        matched_order = primary_match.order
        all_discrepancies = list(primary_match.discrepancies)

        # 4. Multi-Source Linking for Matched Order
        matched_shipments = self._link_shipments(dispute, matched_order)
        matched_comms = self._link_communications(dispute, matched_order)
        matched_refunds = self._link_refunds(matched_order)

        # Check address discrepancy between order and primary shipment
        if matched_order.shipping_address:
            for s in matched_shipments:
                if s.shipment_address:
                    order_postal = matched_order.shipping_address.normalized_postal_code()
                    shipment_postal = s.shipment_address.normalized_postal_code()
                    if order_postal and shipment_postal and order_postal != shipment_postal:
                        all_discrepancies.append(
                            ReconciliationDiscrepancy(
                                code="ADDRESS_MISMATCH",
                                severity=DiscrepancySeverity.WARNING,
                                description=f"Shipment postal code '{shipment_postal}' does not match order postal code '{order_postal}'.",
                                dispute_value=order_postal,
                                order_value=shipment_postal,
                            )
                        )

        # Check prior refunds
        if matched_refunds:
            completed_refunds = [r for r in matched_refunds if r.status.upper() == "COMPLETED"]
            if completed_refunds:
                all_discrepancies.append(
                    ReconciliationDiscrepancy(
                        code="PRIOR_REFUND_OVERLAP",
                        severity=DiscrepancySeverity.WARNING,
                        description=f"Found {len(completed_refunds)} completed refund record(s) on order.",
                    )
                )

        # 5. Determine overall reconciliation status
        status = ReconciliationStatus.RECONCILED
        if all_discrepancies:
            status = ReconciliationStatus.DISCREPANCY_DETECTED

        return ReconciledDisputeBundle(
            dispute_id=dispute.dispute_id,
            status=status,
            matched_order=matched_order,
            matched_shipments=matched_shipments,
            matched_communications=matched_comms,
            matched_refunds=matched_refunds,
            primary_match=primary_match,
            candidate_matches=candidate_matches,
            discrepancies=all_discrepancies,
            reconciled_at=datetime.now(timezone.utc),
        )

    def reconcile_batch(self, disputes: List[DisputeCase]) -> List[ReconciledDisputeBundle]:
        """Batch reconcile a collection of disputes."""
        return [self.reconcile_dispute(d) for d in disputes]

    def _score_secondary_match(
        self,
        dispute: DisputeCase,
        order: OrderRecord,
    ) -> Optional[CandidateMatch]:
        """Compute secondary multi-signal match confidence between dispute and order."""
        score = 0.0
        reasons: List[str] = []
        discrepancies: List[ReconciliationDiscrepancy] = []

        # 1. Email matching
        if dispute.buyer_email and order.customer_email:
            if dispute.buyer_email.strip().lower() == order.customer_email.strip().lower():
                score += 0.40
                reasons.append(f"Buyer email exact match: {order.customer_email}")
            else:
                # Distinct non-matching customer emails preclude accidental cross-customer correlation
                return None

        # 2. Amount and Currency matching
        if dispute.dispute_amount and order.gross_amount:
            if dispute.dispute_amount.currency_code != order.gross_amount.currency_code:
                discrepancies.append(
                    ReconciliationDiscrepancy(
                        code="CURRENCY_MISMATCH",
                        severity=DiscrepancySeverity.CRITICAL,
                        description=(
                            f"Order currency '{order.gross_amount.currency_code}' "
                            f"does not match dispute currency '{dispute.dispute_amount.currency_code}'."
                        ),
                        dispute_value=dispute.dispute_amount.currency_code,
                        order_value=order.gross_amount.currency_code,
                    )
                )
            elif dispute.dispute_amount.value == order.gross_amount.value:
                score += 0.35
                reasons.append(f"Amount exact match: {order.gross_amount.value} {order.gross_amount.currency_code}")
            else:
                discrepancies.append(
                    ReconciliationDiscrepancy(
                        code="AMOUNT_MISMATCH",
                        severity=DiscrepancySeverity.WARNING,
                        description=(
                            f"Order gross amount '{order.gross_amount.value}' "
                            f"differs from dispute amount '{dispute.dispute_amount.value}'."
                        ),
                        dispute_value=str(dispute.dispute_amount.value),
                        order_value=str(order.gross_amount.value),
                    )
                )

        # 3. Timestamp proximity
        is_within_24h = False
        comp_time = dispute.transaction_create_time or dispute.dispute_create_time
        if comp_time and order.order_timestamp:
            # Timeline paradox: order placed after dispute was opened
            if dispute.dispute_create_time and order.order_timestamp > (dispute.dispute_create_time + timedelta(hours=1)):
                discrepancies.append(
                    ReconciliationDiscrepancy(
                        code="TIMELINE_PARADOX",
                        severity=DiscrepancySeverity.CRITICAL,
                        description=(
                            f"Order timestamp ({order.order_timestamp.isoformat()}) is after "
                            f"the dispute create time ({dispute.dispute_create_time.isoformat()})."
                        ),
                        dispute_value=dispute.dispute_create_time.isoformat(),
                        order_value=order.order_timestamp.isoformat(),
                    )
                )
            else:
                delta_sec = abs((comp_time - order.order_timestamp).total_seconds())
                if delta_sec <= 86400:  # <= 24 hours
                    score += 0.25
                    is_within_24h = True
                    reasons.append("Order timestamp within 24 hours of transaction")
                elif delta_sec <= 7 * 86400:  # <= 7 days
                    score += 0.15
                    reasons.append("Order timestamp within 7 days of transaction")

        if score < 0.40:
            return None

        # Assign strategy & tier
        if is_within_24h and score >= 0.85:
            confidence = min(round(score, 2), 0.95)
            strategy = MatchStrategy.SECONDARY_EMAIL_TIME_AMOUNT
            tier = MatchConfidence.HIGH
        elif score >= 0.60:
            confidence = min(round(score, 2), 0.80)
            strategy = MatchStrategy.PARTIAL_EMAIL_AMOUNT
            tier = MatchConfidence.MEDIUM
        else:
            confidence = min(round(score, 2), 0.55)
            strategy = MatchStrategy.PARTIAL_ADDRESS_AMOUNT
            tier = MatchConfidence.LOW

        return CandidateMatch(
            order=order,
            strategy=strategy,
            confidence=confidence,
            confidence_tier=tier,
            match_reasons=reasons,
            discrepancies=discrepancies,
        )

    def _evaluate_order_discrepancies(
        self,
        dispute: DisputeCase,
        order: OrderRecord,
    ) -> List[ReconciliationDiscrepancy]:
        """Evaluate discrepancies for an exact or candidate match."""
        discrepancies: List[ReconciliationDiscrepancy] = []

        if dispute.dispute_amount and order.gross_amount:
            if dispute.dispute_amount.currency_code != order.gross_amount.currency_code:
                discrepancies.append(
                    ReconciliationDiscrepancy(
                        code="CURRENCY_MISMATCH",
                        severity=DiscrepancySeverity.CRITICAL,
                        description=(
                            f"Order currency '{order.gross_amount.currency_code}' "
                            f"does not match dispute currency '{dispute.dispute_amount.currency_code}'."
                        ),
                        dispute_value=dispute.dispute_amount.currency_code,
                        order_value=order.gross_amount.currency_code,
                    )
                )
            elif dispute.dispute_amount.value != order.gross_amount.value:
                discrepancies.append(
                    ReconciliationDiscrepancy(
                        code="AMOUNT_MISMATCH",
                        severity=DiscrepancySeverity.WARNING,
                        description=(
                            f"Order gross amount '{order.gross_amount.value}' "
                            f"differs from dispute amount '{dispute.dispute_amount.value}'."
                        ),
                        dispute_value=str(dispute.dispute_amount.value),
                        order_value=str(order.gross_amount.value),
                    )
                )

        if dispute.dispute_create_time and order.order_timestamp:
            if order.order_timestamp > (dispute.dispute_create_time + timedelta(hours=1)):
                discrepancies.append(
                    ReconciliationDiscrepancy(
                        code="TIMELINE_PARADOX",
                        severity=DiscrepancySeverity.CRITICAL,
                        description=(
                            f"Order timestamp ({order.order_timestamp.isoformat()}) is after "
                            f"dispute create time ({dispute.dispute_create_time.isoformat()})."
                        ),
                        dispute_value=dispute.dispute_create_time.isoformat(),
                        order_value=order.order_timestamp.isoformat(),
                    )
                )

        return discrepancies

    def _link_shipments(
        self,
        dispute: DisputeCase,
        order: OrderRecord,
    ) -> List[ShipmentRecord]:
        """Find and correlate all shipments related to the order."""
        matched: List[ShipmentRecord] = []

        # 1. Match by order ID
        for s in self._shipments_by_order.get(order.order_id, []):
            if s not in matched:
                matched.append(s)

        # 2. Match by tracking numbers on the order
        for tn in order.tracking_numbers:
            clean_tn = tn.strip()
            if clean_tn in self._shipments_by_tracking:
                s = self._shipments_by_tracking[clean_tn]
                if s not in matched:
                    matched.append(s)

        return matched

    def _link_communications(
        self,
        dispute: DisputeCase,
        order: OrderRecord,
    ) -> List[CustomerMessageRecord]:
        """Correlate customer communication records."""
        matched: List[CustomerMessageRecord] = []

        for c in self._comms_by_order.get(order.order_id, []):
            if c not in matched:
                matched.append(c)

        if order.customer_email:
            for c in self._comms_by_email.get(order.customer_email.strip().lower(), []):
                if c not in matched:
                    matched.append(c)

        return matched

    def _link_refunds(self, order: OrderRecord) -> List[RefundRecord]:
        """Correlate existing refund records."""
        matched: List[RefundRecord] = []

        for r in self._refunds_by_order.get(order.order_id, []):
            if r not in matched:
                matched.append(r)

        return matched
