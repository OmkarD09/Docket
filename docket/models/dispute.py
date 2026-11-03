"""Dispute domain models and PayPal API response mapping for Docket."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, ConfigDict, Field, field_validator


class DisputeLifecycleStage(str, Enum):
    """PayPal dispute lifecycle stages."""
    INQUIRY = "INQUIRY"
    CHARGEBACK = "CHARGEBACK"
    PRE_ARBITRATION = "PRE_ARBITRATION"
    ARBITRATION = "ARBITRATION"


class DisputeStatus(str, Enum):
    """Current status of a PayPal dispute."""
    OPEN = "OPEN"
    WAITING_FOR_SELLER_RESPONSE = "WAITING_FOR_SELLER_RESPONSE"
    WAITING_FOR_BUYER_RESPONSE = "WAITING_FOR_BUYER_RESPONSE"
    UNDER_REVIEW = "UNDER_REVIEW"
    RESOLVED = "RESOLVED"
    OTHER = "OTHER"


class DisputeReason(str, Enum):
    """Categorized dispute reasons from PayPal."""
    MERCHANDISE_OR_SERVICE_NOT_RECEIVED = "MERCHANDISE_OR_SERVICE_NOT_RECEIVED"
    MERCHANDISE_OR_SERVICE_NOT_AS_DESCRIBED = "MERCHANDISE_OR_SERVICE_NOT_AS_DESCRIBED"
    UNAUTHORISED = "UNAUTHORISED"
    CREDIT_NOT_PROCESSED = "CREDIT_NOT_PROCESSED"
    DUPLICATE_TRANSACTION = "DUPLICATE_TRANSACTION"
    INCORRECT_AMOUNT = "INCORRECT_AMOUNT"
    PAYMENT_BY_OTHER_MEANS = "PAYMENT_BY_OTHER_MEANS"
    CANCELED_RECURRING_BILLING = "CANCELED_RECURRING_BILLING"
    PROBLEM_WITH_REMITTANCE = "PROBLEM_WITH_REMITTANCE"
    OTHER = "OTHER"


class Money(BaseModel):
    """Monetary amount with strict Decimal precision and 3-letter currency code."""
    model_config = ConfigDict(frozen=True)

    value: Decimal
    currency_code: str = Field(default="USD", min_length=3, max_length=3)

    @field_validator("value")
    @classmethod
    def validate_non_negative(cls, v: Decimal) -> Decimal:
        if v < Decimal("0.00"):
            raise ValueError("Monetary amount cannot be negative")
        return v

    @field_validator("currency_code")
    @classmethod
    def validate_currency(cls, v: str) -> str:
        clean = v.strip().upper()
        if len(clean) != 3 or not clean.isalpha():
            raise ValueError(f"Invalid currency code: {v}")
        return clean


class RequestedEvidence(BaseModel):
    """Evidence requested by PayPal from a party."""
    model_config = ConfigDict(frozen=True)

    evidence_type: str
    source: str
    date: Optional[datetime] = None


class HATEOASLink(BaseModel):
    """HATEOAS actionable link returned by PayPal."""
    model_config = ConfigDict(frozen=True)

    href: str
    rel: str
    method: Optional[str] = "GET"


class DisputeCase(BaseModel):
    """Core domain model representing a PayPal dispute."""
    model_config = ConfigDict(arbitrary_types_allowed=True)

    dispute_id: str = Field(min_length=1)
    reason: DisputeReason | str
    lifecycle_stage: DisputeLifecycleStage
    status: DisputeStatus
    dispute_amount: Money
    requested_evidence_types: List[str] = Field(default_factory=list)
    requested_evidence_sources: List[str] = Field(default_factory=list)
    seller_response_due_date: Optional[datetime] = None
    available_hateoas_actions: List[HATEOASLink] = Field(default_factory=list)
    disputed_transaction_id: Optional[str] = None
    buyer_transaction_id: Optional[str] = None
    seller_transaction_id: Optional[str] = None
    dispute_create_time: Optional[datetime] = None
    transaction_create_time: Optional[datetime] = None
    buyer_email: Optional[str] = None
    buyer_name: Optional[str] = None
    seller_email: Optional[str] = None
    raw_messages: List[Dict[str, Any]] = Field(default_factory=list)

    def has_action(self, rel: str) -> bool:
        """Check if an actionable link is present (normalizing hyphens and underscores)."""
        normalized_target = rel.strip().lower().replace("-", "_")
        for link in self.available_hateoas_actions:
            if link.rel.strip().lower().replace("-", "_") == normalized_target:
                return True
        return False

    def get_action_link(self, rel: str) -> Optional[HATEOASLink]:
        """Retrieve a specific HATEOAS link by rel."""
        normalized_target = rel.strip().lower().replace("-", "_")
        for link in self.available_hateoas_actions:
            if link.rel.strip().lower().replace("-", "_") == normalized_target:
                return link
        return None

    def is_seller_response_required(self) -> bool:
        """Returns True if the dispute currently requires merchant action."""
        return self.status == DisputeStatus.WAITING_FOR_SELLER_RESPONSE

    @classmethod
    def from_paypal_response(cls, data: Dict[str, Any]) -> DisputeCase:
        """Parse raw PayPal API JSON into a strongly-typed DisputeCase domain model."""
        dispute_id = data.get("dispute_id")
        if not dispute_id:
            raise ValueError("PayPal response missing required 'dispute_id'")

        # Lifecycle stage
        raw_stage = data.get("dispute_life_cycle_stage") or data.get("life_cycle_stage") or "INQUIRY"
        try:
            lifecycle_stage = DisputeLifecycleStage(raw_stage)
        except ValueError:
            lifecycle_stage = DisputeLifecycleStage.INQUIRY

        # Status
        raw_status = data.get("status", "OPEN")
        try:
            status = DisputeStatus(raw_status)
        except ValueError:
            status = DisputeStatus.OTHER

        # Reason
        raw_reason = data.get("reason", "OTHER")
        try:
            reason = DisputeReason(raw_reason)
        except ValueError:
            reason = raw_reason

        # Amount
        dispute_amount_dict = data.get("dispute_amount") or {}
        val_str = str(dispute_amount_dict.get("value", "0.00"))
        curr = dispute_amount_dict.get("currency_code", "USD")
        dispute_amount = Money(value=Decimal(val_str), currency_code=curr)

        # Dates
        seller_due: Optional[datetime] = None
        raw_due = data.get("seller_response_due_date")
        if raw_due:
            try:
                seller_due = datetime.fromisoformat(raw_due.replace("Z", "+00:00"))
            except Exception:
                seller_due = None

        dispute_created: Optional[datetime] = None
        raw_created = data.get("create_time")
        if raw_created:
            try:
                dispute_created = datetime.fromisoformat(raw_created.replace("Z", "+00:00"))
            except Exception:
                dispute_created = None

        # Evidence requirements
        evidences = data.get("evidences") or []
        req_types: List[str] = []
        req_sources: List[str] = []
        for item in evidences:
            if isinstance(item, dict):
                ev_type = item.get("evidence_type")
                source = item.get("source")
                if ev_type and ev_type not in req_types:
                    req_types.append(ev_type)
                if source and source not in req_sources:
                    req_sources.append(source)

        # HATEOAS links
        links_data = data.get("links") or []
        links: List[HATEOASLink] = []
        for link in links_data:
            if isinstance(link, dict) and "href" in link and "rel" in link:
                links.append(HATEOASLink(
                    href=link["href"],
                    rel=link["rel"],
                    method=link.get("method", "GET"),
                ))

        # Transactions
        tx_list = data.get("disputed_transactions") or []
        buyer_tx_id: Optional[str] = None
        seller_tx_id: Optional[str] = None
        buyer_email: Optional[str] = None
        buyer_name: Optional[str] = None
        seller_email: Optional[str] = None
        tx_created: Optional[datetime] = None

        if tx_list and isinstance(tx_list, list) and isinstance(tx_list[0], dict):
            first_tx = tx_list[0]
            buyer_tx_id = first_tx.get("buyer_transaction_id")
            seller_tx_id = first_tx.get("seller_transaction_id")
            raw_tx_time = first_tx.get("create_time")
            if raw_tx_time:
                try:
                    tx_created = datetime.fromisoformat(raw_tx_time.replace("Z", "+00:00"))
                except Exception:
                    tx_created = None
            buyer_obj = first_tx.get("buyer") or {}
            if isinstance(buyer_obj, dict):
                buyer_email = buyer_obj.get("email")
                buyer_name = buyer_obj.get("name")
            seller_obj = first_tx.get("seller") or {}
            if isinstance(seller_obj, dict):
                seller_email = seller_obj.get("email")

        disputed_tx_id = seller_tx_id or buyer_tx_id
        messages = data.get("messages") or []

        return cls(
            dispute_id=dispute_id,
            reason=reason,
            lifecycle_stage=lifecycle_stage,
            status=status,
            dispute_amount=dispute_amount,
            requested_evidence_types=req_types,
            requested_evidence_sources=req_sources,
            seller_response_due_date=seller_due,
            available_hateoas_actions=links,
            disputed_transaction_id=disputed_tx_id,
            buyer_transaction_id=buyer_tx_id,
            seller_transaction_id=seller_tx_id,
            dispute_create_time=dispute_created,
            transaction_create_time=tx_created,
            buyer_email=buyer_email,
            buyer_name=buyer_name,
            seller_email=seller_email,
            raw_messages=messages if isinstance(messages, list) else [],
        )

