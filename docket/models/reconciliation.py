"""Domain models for cross-source evidence reconciliation."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, ConfigDict, Field

from docket.models.evidence import (
    CustomerMessageRecord,
    OrderRecord,
    RefundRecord,
    ShipmentRecord,
    SourceCitation,
    SourceType,
    TrackingStatus,
    VerificationStatus,
)


class MatchStrategy(str, Enum):
    """The algorithm or key used to correlate records."""
    EXACT_TRANSACTION_ID = "EXACT_TRANSACTION_ID"
    EXACT_ORDER_ID = "EXACT_ORDER_ID"
    SECONDARY_EMAIL_TIME_AMOUNT = "SECONDARY_EMAIL_TIME_AMOUNT"
    PARTIAL_EMAIL_AMOUNT = "PARTIAL_EMAIL_AMOUNT"
    PARTIAL_ADDRESS_AMOUNT = "PARTIAL_ADDRESS_AMOUNT"
    MANUAL_OVERRIDE = "MANUAL_OVERRIDE"
    UNLINKED = "UNLINKED"


class MatchConfidence(str, Enum):
    """Confidence tier for evidence linkage."""
    EXACT = "EXACT"         # 1.0 (Exact ID match)
    HIGH = "HIGH"           # >= 0.85 (Multi-signal exact correlation: email + amount + within 24h)
    MEDIUM = "MEDIUM"       # 0.60 - 0.84 (Partial correlation: email + amount within 7d)
    LOW = "LOW"             # 0.30 - 0.59 (Single loose signal)
    NONE = "NONE"           # 0.0 (Unlinked)


class ReconciliationStatus(str, Enum):
    """Overall reconciliation state for a dispute."""
    RECONCILED = "RECONCILED"
    AMBIGUOUS = "AMBIGUOUS"
    ORPHAN_DISPUTE = "ORPHAN_DISPUTE"
    ORPHAN_ORDER = "ORPHAN_ORDER"
    DISCREPANCY_DETECTED = "DISCREPANCY_DETECTED"


class DiscrepancySeverity(str, Enum):
    """Risk severity of an identified discrepancy."""
    CRITICAL = "CRITICAL"
    WARNING = "WARNING"
    INFO = "INFO"


class ReconciliationDiscrepancy(BaseModel):
    """A detected inconsistency between dispute and merchant records."""
    model_config = ConfigDict(frozen=True)

    code: str
    severity: DiscrepancySeverity
    description: str
    dispute_value: Optional[str] = None
    order_value: Optional[str] = None


class CandidateMatch(BaseModel):
    """A potential merchant order candidate for a dispute."""
    model_config = ConfigDict(arbitrary_types_allowed=True)

    order: OrderRecord
    strategy: MatchStrategy
    confidence: float = Field(ge=0.0, le=1.0)
    confidence_tier: MatchConfidence
    match_reasons: List[str] = Field(default_factory=list)
    discrepancies: List[ReconciliationDiscrepancy] = Field(default_factory=list)


class ReconciledDisputeBundle(BaseModel):
    """Unified cross-source evidence bundle for a dispute."""
    model_config = ConfigDict(arbitrary_types_allowed=True)

    dispute_id: str
    status: ReconciliationStatus
    matched_order: Optional[OrderRecord] = None
    matched_shipments: List[ShipmentRecord] = Field(default_factory=list)
    matched_communications: List[CustomerMessageRecord] = Field(default_factory=list)
    matched_refunds: List[RefundRecord] = Field(default_factory=list)
    primary_match: Optional[CandidateMatch] = None
    candidate_matches: List[CandidateMatch] = Field(default_factory=list)
    discrepancies: List[ReconciliationDiscrepancy] = Field(default_factory=list)
    reconciled_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    def is_reconciled(self) -> bool:
        """Returns True if the dispute has a confirmed matched order."""
        return (
            self.status in (ReconciliationStatus.RECONCILED, ReconciliationStatus.DISCREPANCY_DETECTED)
            and self.matched_order is not None
        )

    def is_ambiguous(self) -> bool:
        """Returns True if multiple competing candidate matches exist."""
        return self.status == ReconciliationStatus.AMBIGUOUS

    def has_critical_discrepancies(self) -> bool:
        """Returns True if any discrepancy has CRITICAL severity."""
        return any(d.severity == DiscrepancySeverity.CRITICAL for d in self.discrepancies)

    def get_tracking_numbers(self) -> List[str]:
        """Collect all tracking numbers associated with matched shipments and order."""
        numbers: List[str] = []
        for s in self.matched_shipments:
            if s.tracking_number and s.tracking_number not in numbers:
                numbers.append(s.tracking_number)
        if self.matched_order:
            for tn in self.matched_order.tracking_numbers:
                if tn not in numbers:
                    numbers.append(tn)
        return numbers

    def get_primary_shipment(self) -> Optional[ShipmentRecord]:
        """Return the most relevant shipment record (prioritizing DELIVERED or active)."""
        if not self.matched_shipments:
            return None
        # Priority order
        priority = {
            TrackingStatus.DELIVERED: 0,
            TrackingStatus.OUT_FOR_DELIVERY: 1,
            TrackingStatus.IN_TRANSIT: 2,
            TrackingStatus.LABEL_CREATED: 3,
            TrackingStatus.EXCEPTION: 4,
            TrackingStatus.RETURNED: 5,
            TrackingStatus.UNKNOWN: 6,
        }
        sorted_shipments = sorted(
            self.matched_shipments,
            key=lambda s: priority.get(s.tracking_status, 99)
        )
        return sorted_shipments[0]

    def to_citations(self) -> List[SourceCitation]:
        """Extract structured, traceable SourceCitations from all matched records."""
        citations: List[SourceCitation] = []

        # Order citations
        if self.matched_order:
            order = self.matched_order
            citations.append(SourceCitation(
                source_type=SourceType.ORDER_INVOICE,
                source_identifier=order.order_id,
                field_path="order_id",
                extracted_value=order.order_id,
                verification_status=VerificationStatus.VERIFIED,
            ))
            if order.paypal_transaction_id:
                citations.append(SourceCitation(
                    source_type=SourceType.ORDER_INVOICE,
                    source_identifier=order.order_id,
                    field_path="paypal_transaction_id",
                    extracted_value=order.paypal_transaction_id,
                    verification_status=VerificationStatus.VERIFIED,
                ))
            if order.gross_amount:
                citations.append(SourceCitation(
                    source_type=SourceType.ORDER_INVOICE,
                    source_identifier=order.order_id,
                    field_path="gross_amount.value",
                    extracted_value=str(order.gross_amount.value),
                    verification_status=VerificationStatus.VERIFIED,
                ))
                citations.append(SourceCitation(
                    source_type=SourceType.ORDER_INVOICE,
                    source_identifier=order.order_id,
                    field_path="gross_amount.currency_code",
                    extracted_value=order.gross_amount.currency_code,
                    verification_status=VerificationStatus.VERIFIED,
                ))
            if order.shipping_address and order.shipping_address.postal_code:
                citations.append(SourceCitation(
                    source_type=SourceType.ORDER_INVOICE,
                    source_identifier=order.order_id,
                    field_path="shipping_address.postal_code",
                    extracted_value=order.shipping_address.postal_code,
                    verification_status=VerificationStatus.VERIFIED,
                ))

        # Shipment citations
        for shipment in self.matched_shipments:
            s_id = shipment.source_identifier or f"TRK-{shipment.tracking_number}"
            citations.append(SourceCitation(
                source_type=SourceType.CARRIER_TRACKING,
                source_identifier=s_id,
                field_path="tracking_status",
                extracted_value=shipment.tracking_status.value,
                verification_status=VerificationStatus.VERIFIED,
            ))
            citations.append(SourceCitation(
                source_type=SourceType.CARRIER_TRACKING,
                source_identifier=s_id,
                field_path="tracking_number",
                extracted_value=shipment.tracking_number,
                verification_status=VerificationStatus.VERIFIED,
            ))
            citations.append(SourceCitation(
                source_type=SourceType.CARRIER_TRACKING,
                source_identifier=s_id,
                field_path="carrier_name",
                extracted_value=shipment.carrier_name,
                verification_status=VerificationStatus.VERIFIED,
            ))
            if shipment.delivery_timestamp:
                citations.append(SourceCitation(
                    source_type=SourceType.CARRIER_TRACKING,
                    source_identifier=s_id,
                    field_path="delivery_timestamp",
                    extracted_value=shipment.delivery_timestamp.isoformat(),
                    verification_status=VerificationStatus.VERIFIED,
                ))
            if shipment.shipment_address and shipment.shipment_address.postal_code:
                citations.append(SourceCitation(
                    source_type=SourceType.CARRIER_TRACKING,
                    source_identifier=s_id,
                    field_path="shipment_address.postal_code",
                    extracted_value=shipment.shipment_address.postal_code,
                    verification_status=VerificationStatus.VERIFIED,
                ))
            if shipment.recipient_signature_present is not None:
                citations.append(SourceCitation(
                    source_type=SourceType.CARRIER_TRACKING,
                    source_identifier=s_id,
                    field_path="recipient_signature_present",
                    extracted_value=str(shipment.recipient_signature_present),
                    verification_status=VerificationStatus.VERIFIED,
                ))

        # Refund citations
        for refund in self.matched_refunds:
            r_id = refund.source_identifier or f"REF-{refund.refund_id}"
            citations.append(SourceCitation(
                source_type=SourceType.REFUND_LEDGER,
                source_identifier=r_id,
                field_path="amount.value",
                extracted_value=str(refund.amount.value),
                verification_status=VerificationStatus.VERIFIED,
            ))
            citations.append(SourceCitation(
                source_type=SourceType.REFUND_LEDGER,
                source_identifier=r_id,
                field_path="status",
                extracted_value=refund.status,
                verification_status=VerificationStatus.VERIFIED,
            ))

        return citations

