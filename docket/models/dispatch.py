"""Docket Dispatch & Approval Domain Models.

Models for merchant approval gates, cryptographic authorization tokens,
payload formatting, and PayPal dispatch results.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class ApprovalDecision(str, Enum):
    """Merchant approval decision."""
    APPROVE = "APPROVE"
    REJECT = "REJECT"


class TrackingInfoPayload(BaseModel):
    """Tracking details within PayPal evidence payload."""
    carrier_name: str
    carrier_name_other: Optional[str] = None
    tracking_number: str
    tracking_url: Optional[str] = None


class EvidenceInfoPayload(BaseModel):
    """Evidence information container for tracking."""
    tracking_info: List[TrackingInfoPayload] = Field(default_factory=list)


class EvidenceItemPayload(BaseModel):
    """Single evidence entry for PayPal provide-evidence API."""
    evidence_type: str = "PROOF_OF_FULFILLMENT"
    evidence_info: Optional[EvidenceInfoPayload] = None
    notes: Optional[str] = None


class EvidencePayload(BaseModel):
    """Top-level container for PayPal provide-evidence API request body."""
    evidences: List[EvidenceItemPayload] = Field(default_factory=list)


class ApprovalRequest(BaseModel):
    """Merchant approval ticket awaiting affirmative authorization."""
    approval_id: str
    dispute_id: str
    overall_decision: str
    factual_readiness: str
    action_readiness: str
    proposed_payload: Dict[str, Any]
    payload_hash: str
    summary_for_human: str
    created_at: datetime
    expires_at: datetime
    nonce: str
    token: str


class MerchantApprovalRecord(BaseModel):
    """Immutable record of merchant approval action."""
    approval_id: str
    dispute_id: str
    merchant_user_id: str
    decision: ApprovalDecision
    rejection_reason: Optional[str] = None
    approved_at: datetime
    approval_token: str
    client_ip: Optional[str] = None
    user_agent: Optional[str] = None

    def is_approved(self) -> bool:
        return self.decision == ApprovalDecision.APPROVE


class DispatchResult(BaseModel):
    """Outcome of live or simulated PayPal API dispatch."""
    success: bool
    dispute_id: str
    submission_timestamp: datetime
    paypal_status_code: Optional[int] = None
    paypal_response_body: Optional[Dict[str, Any]] = None
    correlation_id: Optional[str] = None
    audit_id: Optional[str] = None
    error_message: Optional[str] = None

