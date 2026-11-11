"""Evidence, shipment, address, citation, and claim models for Docket."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
import re
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, ConfigDict, Field

from docket.models.dispute import Money


class TrackingStatus(str, Enum):
    """Normalized carrier shipment tracking statuses."""
    LABEL_CREATED = "LABEL_CREATED"
    IN_TRANSIT = "IN_TRANSIT"
    OUT_FOR_DELIVERY = "OUT_FOR_DELIVERY"
    DELIVERED = "DELIVERED"
    RETURNED = "RETURNED"
    EXCEPTION = "EXCEPTION"
    UNKNOWN = "UNKNOWN"


class Address(BaseModel):
    """Physical delivery or billing address."""
    model_config = ConfigDict(arbitrary_types_allowed=True)

    recipient_name: Optional[str] = None
    line1: Optional[str] = None
    line2: Optional[str] = None
    city: Optional[str] = None
    state_or_province: Optional[str] = None
    postal_code: Optional[str] = None
    country_code: Optional[str] = Field(default=None, max_length=3)

    def normalized_postal_code(self) -> Optional[str]:
        """Normalize postal codes (e.g. '95131-1234' -> '95131', strip spaces)."""
        if not self.postal_code:
            return None
        raw = self.postal_code.strip().upper()
        # For US ZIP+4 format 12345-6789, take the base 5 digits for standard comparison
        if re.match(r"^\d{5}-\d{4}$", raw):
            return raw.split("-")[0]
        # Otherwise strip internal whitespace
        return re.sub(r"\s+", "", raw)

    def normalized_country(self) -> Optional[str]:
        """Normalize country code to 2-letter uppercase string."""
        if not self.country_code:
            return None
        return self.country_code.strip().upper()

    def normalized_city(self) -> Optional[str]:
        """Normalize city name for comparison."""
        if not self.city:
            return None
        return self.city.strip().lower()

    def normalized_recipient_name(self) -> Optional[str]:
        """Normalize recipient name for comparison (strip punctuation, extra spaces, lowercase)."""
        if not self.recipient_name:
            return None
        cleaned = re.sub(r"[^\w\s]", "", self.recipient_name).strip().lower()
        return re.sub(r"\s+", " ", cleaned)

    def normalized_line1(self) -> Optional[str]:
        """Normalize street line1 for comparison."""
        if not self.line1:
            return None
        cleaned = re.sub(r"[^\w\s]", "", self.line1).strip().lower()
        return re.sub(r"\s+", " ", cleaned)



class ShipmentRecord(BaseModel):
    """Carrier tracking and fulfillment record for an order."""
    model_config = ConfigDict(arbitrary_types_allowed=True)

    internal_order_id: str
    tracking_number: str
    carrier_name: str
    tracking_status: TrackingStatus
    shipment_timestamp: Optional[datetime] = None
    delivery_timestamp: Optional[datetime] = None
    shipment_address: Optional[Address] = None
    source_identifier: str
    recipient_signature_present: Optional[bool] = None
    signed_by: Optional[str] = None
    source_provenance: str = "SYNTHETIC_FIXTURE"


class SourceType(str, Enum):
    """Categorized origin of an evidence citation."""
    CARRIER_TRACKING = "CARRIER_TRACKING"
    ORDER_INVOICE = "ORDER_INVOICE"
    PAYPAL_API = "PAYPAL_API"
    CUSTOMER_COMMUNICATION = "CUSTOMER_COMMUNICATION"
    WAREHOUSE_RECORD = "WAREHOUSE_RECORD"
    REFUND_LEDGER = "REFUND_LEDGER"
    OTHER = "OTHER"


class VerificationStatus(str, Enum):
    """Reliability state of an evidence source."""
    VERIFIED = "VERIFIED"
    UNVERIFIED = "UNVERIFIED"
    CONFLICTING = "CONFLICTING"
    REJECTED = "REJECTED"


class SourceCitation(BaseModel):
    """A granular, auditable pointer to a factual statement in a source record."""
    model_config = ConfigDict(frozen=True)

    source_type: SourceType
    source_identifier: str
    field_path: str
    extracted_value: str
    verification_status: VerificationStatus = VerificationStatus.VERIFIED


class ClaimType(str, Enum):
    """The factual assertion category of an extracted claim."""
    DELIVERY_COMPLETED = "DELIVERY_COMPLETED"
    SHIPMENT_IN_PROGRESS = "SHIPMENT_IN_PROGRESS"
    LABEL_CREATED = "LABEL_CREATED"
    REFUND_ISSUED = "REFUND_ISSUED"
    ITEM_MATCHES_DESCRIPTION = "ITEM_MATCHES_DESCRIPTION"
    REPLACEMENT_OFFERED = "REPLACEMENT_OFFERED"
    COMMUNICATION_ACKNOWLEDGED = "COMMUNICATION_ACKNOWLEDGED"
    NON_RECEIPT_ASSERTED = "NON_RECEIPT_ASSERTED"
    OTHER = "OTHER"


class ClaimStatus(str, Enum):
    """State of a proposed claim through policy validation."""
    PROPOSED = "PROPOSED"
    SUPPORTED = "SUPPORTED"
    UNSUPPORTED = "UNSUPPORTED"
    REFUSED = "REFUSED"
    CONFLICTING = "CONFLICTING"


class EvidenceBasis(str, Enum):
    """Epistemic classification of evidence supporting a claim."""
    DIRECT_RECORD = "DIRECT_RECORD"
    FIRST_PARTY_STATEMENT = "FIRST_PARTY_STATEMENT"
    SECOND_HAND_HEARSAY = "SECOND_HAND_HEARSAY"
    UNVERIFIED = "UNVERIFIED"


class ClaimEpistemicMetadata(BaseModel):
    """Structured epistemic classification and attribution for an extracted claim.
    
    Prevents confusing customer communications or hearsay with direct carrier records.
    Requires explicit provenance metadata upon construction to avoid leaking attribution.
    """
    model_config = ConfigDict(arbitrary_types_allowed=True)

    source_category: str
    attribution: str
    evidence_basis: EvidenceBasis
    independent_carrier_confirmation: bool
    supporting_source_id: Optional[str] = None


class ExtractedClaim(BaseModel):
    """A structured assertion of fact with supporting citations."""
    model_config = ConfigDict(arbitrary_types_allowed=True)

    claim_id: str
    claim_type: ClaimType
    factual_assertion: str
    normalized_value: Optional[Dict[str, Any]] = None
    supporting_sources: List[SourceCitation] = Field(default_factory=list)
    claim_status: ClaimStatus = ClaimStatus.PROPOSED
    epistemic_metadata: Optional[ClaimEpistemicMetadata] = None


class OrderRecord(BaseModel):
    """Internal merchant order details correlated with a PayPal dispute."""
    model_config = ConfigDict(arbitrary_types_allowed=True)

    order_id: str
    paypal_transaction_id: Optional[str] = None
    order_timestamp: Optional[datetime] = None
    gross_amount: Optional[Money] = None
    customer_email: Optional[str] = None
    customer_name: Optional[str] = None
    shipping_address: Optional[Address] = None
    tracking_numbers: List[str] = Field(default_factory=list)
    refund_ids: List[str] = Field(default_factory=list)
    items: List[Dict[str, Any]] = Field(default_factory=list)
    source_provenance: str = "SYNTHETIC_FIXTURE"


class CustomerMessageRecord(BaseModel):
    """Customer support, email, or messaging log."""
    model_config = ConfigDict(arbitrary_types_allowed=True)

    message_id: str
    sender: str
    recipient: Optional[str] = None
    timestamp: datetime
    subject: Optional[str] = None
    content: str
    order_id: Optional[str] = None
    customer_email: Optional[str] = None
    source_identifier: str = "SUPPORT_LOGS"


class RefundRecord(BaseModel):
    """Internal or PayPal ledger record of a refund."""
    model_config = ConfigDict(arbitrary_types_allowed=True)

    refund_id: str
    order_id: str
    paypal_refund_id: Optional[str] = None
    amount: Money
    refund_timestamp: datetime
    reason: Optional[str] = None
    status: str = "COMPLETED"
    source_identifier: str = "REFUND_LEDGER"


