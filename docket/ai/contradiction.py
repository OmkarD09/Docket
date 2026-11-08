"""Semantic contradiction detection between claims and internal records."""

from __future__ import annotations

from typing import Any, List, Optional
from pydantic import BaseModel, ConfigDict, field_validator

from docket.models.dispute import DisputeReason
from docket.models.evidence import ClaimType, ExtractedClaim, TrackingStatus
from docket.models.reconciliation import ReconciledDisputeBundle


CANONICAL_DELIVERY_STATUS_DISCREPANCY = "DELIVERY_STATUS_DISCREPANCY"
LEGACY_DELIVERY_DISPUTE_EVIDENCE_EXISTS = "DELIVERY_DISPUTE_EVIDENCE_EXISTS"

LEGACY_CONTRADICTION_MAP = {
    LEGACY_DELIVERY_DISPUTE_EVIDENCE_EXISTS: CANONICAL_DELIVERY_STATUS_DISCREPANCY,
}


def normalize_contradiction_code(code: str) -> str:
    """Explicitly normalize legacy contradiction codes to their canonical form.

    Maps 'DELIVERY_DISPUTE_EVIDENCE_EXISTS' -> 'DELIVERY_STATUS_DISCREPANCY'.
    Preserves all other codes unchanged.
    """
    if not isinstance(code, str):
        return str(code)
    return LEGACY_CONTRADICTION_MAP.get(code.strip(), code.strip())


class ContradictionCode(str):
    """Canonical contradiction code type with automatic legacy code normalization upon creation.

    Ensures that both new ('DELIVERY_STATUS_DISCREPANCY') and legacy ('DELIVERY_DISPUTE_EVIDENCE_EXISTS')
    inputs construct an identical canonical string value, guaranteeing:
    - Standard symmetric string equality in both comparison directions (code == "X" and "X" == code).
    - Stable hash consistency: hash(code) == hash(canonical).
    - Native set membership and dictionary key lookup behavior.
    - Clean JSON serialization without custom encoder requirements.
    """

    def __new__(cls, value: str, legacy_alias: Optional[str] = None):
        canonical = normalize_contradiction_code(str(value))
        return super().__new__(cls, canonical)


class ContradictionFinding(BaseModel):
    """An identified factual contradiction or delivery discrepancy between evidence sources."""
    model_config = ConfigDict(frozen=True)

    code: str
    severity: str  # "HIGH", "MEDIUM", "LOW"
    description: str
    conflicting_claim_id: Optional[str] = None

    @field_validator("code", mode="before")
    @classmethod
    def normalize_finding_code(cls, v: Any) -> str:
        """Normalize legacy contradiction codes at deserialization and boundary validation."""
        if isinstance(v, str):
            return normalize_contradiction_code(v)
        return str(v)

    def matches_code(self, candidate_code: str) -> bool:
        """Check if this finding matches candidate_code, accounting for legacy aliases."""
        return self.code == normalize_contradiction_code(candidate_code)


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
                        code=CANONICAL_DELIVERY_STATUS_DISCREPANCY,
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

