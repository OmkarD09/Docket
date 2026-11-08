"""Semantic contradiction detection between claims and internal records."""

from __future__ import annotations

from typing import Any, List, Optional
from pydantic import BaseModel, ConfigDict

from docket.models.dispute import DisputeReason
from docket.models.evidence import ClaimType, ExtractedClaim, TrackingStatus
from docket.models.reconciliation import ReconciledDisputeBundle


class ContradictionCode(str):
    """String subclass providing clearer finding identifiers while maintaining backwards compatibility."""
    legacy_alias: Optional[str] = None

    def __new__(cls, value: str, legacy_alias: Optional[str] = None):
        obj = str.__new__(cls, value)
        obj.legacy_alias = legacy_alias
        return obj

    def __eq__(self, other: Any) -> bool:
        return super().__eq__(other) or (self.legacy_alias is not None and self.legacy_alias == other)

    def __hash__(self) -> int:
        return super().__hash__()


class ContradictionFinding(BaseModel):
    """An identified factual contradiction or delivery discrepancy between evidence sources."""
    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)

    code: Any
    severity: str  # "HIGH", "MEDIUM", "LOW"
    description: str
    conflicting_claim_id: Optional[str] = None


class ContradictionDetector:
    """Detects factual conflicts between customer claims, merchant orders, and carrier feeds."""

    def check_contradictions(
        self,
        proposed_claim: ExtractedClaim,
        bundle: ReconciledDisputeBundle,
        dispute_reason: DisputeReason | str,
    ) -> List[ContradictionFinding]:
        """Cross-check a proposed claim against ground-truth facts in the reconciled bundle."""
        findings: List[ContradictionFinding] = []
        shipment = bundle.get_primary_shipment()

        reason_str = dispute_reason.value if isinstance(dispute_reason, DisputeReason) else str(dispute_reason)
        is_inr = "NOT_RECEIVED" in reason_str

        # 1. Buyer claims item not received, but carrier tracking shows DELIVERED
        # Note: A carrier DELIVERED scan and a buyer non-receipt statement represent a factual delivery discrepancy,
        # not necessarily a logical impossibility. We classify this as DELIVERY_STATUS_DISCREPANCY.
        if is_inr and shipment and shipment.tracking_status == TrackingStatus.DELIVERED:
            # Check if claim asserts non-receipt
            assertion_lower = proposed_claim.factual_assertion.lower()
            is_non_receipt = (
                any(term in assertion_lower for term in ["never arrived", "not received", "never received", "did not receive", "never delivered", "missing package"])
                or getattr(proposed_claim.claim_type, "value", str(proposed_claim.claim_type)) == "NON_RECEIPT_ASSERTED"
            )

            if is_non_receipt:
                findings.append(
                    ContradictionFinding(
                        code=ContradictionCode("DELIVERY_STATUS_DISCREPANCY", legacy_alias="DELIVERY_DISPUTE_EVIDENCE_EXISTS"),
                        severity="HIGH",
                        description=(
                            f"Delivery discrepancy: Buyer asserts non-delivery, but carrier {shipment.carrier_name} tracking "
                            f"{shipment.tracking_number} shows package was DELIVERED."
                        ),
                        conflicting_claim_id=proposed_claim.claim_id,
                    )
                )

        # 2. Claim asserts delivery, but carrier status is not DELIVERED
        if proposed_claim.claim_type == ClaimType.DELIVERY_COMPLETED:
            if shipment and shipment.tracking_status != TrackingStatus.DELIVERED:
                findings.append(
                    ContradictionFinding(
                        code="CLAIM_CONTRADICTS_CARRIER_STATUS",
                        severity="HIGH",
                        description=(
                            f"Claim asserts delivery completed, but carrier tracking status is "
                            f"'{shipment.tracking_status.value}'."
                        ),
                        conflicting_claim_id=proposed_claim.claim_id,
                    )
                )

        return findings

    def check_bundle_anomalies(self, bundle: ReconciledDisputeBundle) -> List[ContradictionFinding]:
        """Detect anomalies across the reconciled bundle (e.g. prior refunds, split shipments)."""
        findings: List[ContradictionFinding] = []

        # 1. Prior Refund Overlap
        completed_refunds = [r for r in bundle.matched_refunds if r.status.upper() == "COMPLETED"]
        if completed_refunds:
            total_refunded = sum(r.amount.value for r in completed_refunds)
            findings.append(
                ContradictionFinding(
                    code="PRIOR_REFUND_OVERLAP",
                    severity="HIGH",
                    description=(
                        f"Found {len(completed_refunds)} completed refund record(s) totaling "
                        f"{total_refunded} for this order. Rebuttal should account for prior refunds."
                    ),
                )
            )

        # 2. Split Shipments with Incomplete Fulfillment
        if len(bundle.matched_shipments) > 1:
            undelivered = [s for s in bundle.matched_shipments if s.tracking_status != TrackingStatus.DELIVERED]
            if undelivered:
                findings.append(
                    ContradictionFinding(
                        code="SPLIT_SHIPMENT_PARTIAL_DELIVERY",
                        severity="MEDIUM",
                        description=(
                            f"Order has {len(bundle.matched_shipments)} split shipments, of which "
                            f"{len(undelivered)} are still in transit or pending pickup."
                        ),
                    )
                )

        return findings

