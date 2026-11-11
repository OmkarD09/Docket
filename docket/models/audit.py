"""Docket Audit Domain Models.

Models for append-only, tamper-evident cryptographic audit logs.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Dict, Optional
from pydantic import BaseModel, Field


class AuditEventType(str, Enum):
    """Categorized lifecycle events in Docket's dispute processing."""
    DISPUTE_INGESTED = "DISPUTE_INGESTED"
    DISPUTE_SYNCHRONIZED = "DISPUTE_SYNCHRONIZED"
    DUPLICATE_WEBHOOK_RECEIVED = "DUPLICATE_WEBHOOK_RECEIVED"
    DUPLICATE_WEBHOOK_IGNORED = "DUPLICATE_WEBHOOK_IGNORED"
    EVIDENCE_RECONCILED = "EVIDENCE_RECONCILED"
    POLICY_EVALUATED = "POLICY_EVALUATED"
    APPROVAL_REQUESTED = "APPROVAL_REQUESTED"
    APPROVAL_GRANTED = "APPROVAL_GRANTED"
    APPROVAL_REJECTED = "APPROVAL_REJECTED"
    APPROVAL_EXPIRED = "APPROVAL_EXPIRED"
    APPROVAL_CONSUMED = "APPROVAL_CONSUMED"
    DISPATCH_ATTEMPTED = "DISPATCH_ATTEMPTED"
    DISPATCH_SUCCEEDED = "DISPATCH_SUCCEEDED"
    DISPATCH_FAILED = "DISPATCH_FAILED"
    AUDIT_VERIFICATION_FAILED = "AUDIT_VERIFICATION_FAILED"
    AUDIT_VERIFICATION_RECOVERED = "AUDIT_VERIFICATION_RECOVERED"
    RECONCILIATION_COMPLETED = "RECONCILIATION_COMPLETED"
    RECONCILIATION_FAILED = "RECONCILIATION_FAILED"


class AuditEvent(BaseModel):
    """Cryptographically chained audit trail entry."""
    event_id: str
    parent_hash: str
    event_hash: str
    event_type: AuditEventType
    timestamp: datetime
    dispute_id: str
    actor: str
    payload: Dict[str, Any] = Field(default_factory=dict)

