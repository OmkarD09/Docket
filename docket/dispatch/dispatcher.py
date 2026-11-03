"""Docket Evidence Dispatcher & PayPal API Action Submitter.

Enforces pre-submission deterministic policy gates, merchant authorization
token verification, duplicate prevention via idempotency locks, payload
formatting adhering to PayPal's provide-evidence schema, and HATEOAS URL routing.
"""

from __future__ import annotations

from datetime import datetime, timezone
import json
from typing import Any, Dict, List, Optional, Set
from urllib.parse import urlparse
import requests

from docket.models.dispute import DisputeCase, HATEOASLink
from docket.models.dispatch import (
    ApprovalDecision,
    DispatchResult,
    EvidenceInfoPayload,
    EvidenceItemPayload,
    EvidencePayload,
    MerchantApprovalRecord,
    TrackingInfoPayload,
)
from docket.models.policy import DecisionType, OverallPolicyEvaluation
from docket.models.reconciliation import ReconciledDisputeBundle
from docket.dispatch.approval import ApprovalService
from docket.models.audit import AuditEventType


# ============================================================================
# Exceptions
# ============================================================================

class DispatchError(Exception):
    """Base exception for evidence dispatch failures."""


class SubmissionBlockedError(DispatchError):
    """Raised when policy engine refusal barrier blocks submission."""


class MerchantApprovalRequiredError(DispatchError):
    """Raised when submission is attempted without verified merchant approval."""


class SubmissionRejectedError(DispatchError):
    """Raised when merchant explicitly rejected evidence submission."""


class DuplicateSubmissionError(DispatchError):
    """Raised when an evidence submission for a dispute has already been submitted."""


# ============================================================================
# Evidence Payload Formatter
# ============================================================================

class EvidencePayloadFormatter:
    """Formats reconciled evidence into PayPal's official provide-evidence JSON structure."""

    KNOWN_CARRIERS: Set[str] = {
        "USPS",
        "FEDEX",
        "UPS",
        "DHL",
        "CANADAPOST",
        "ROYALMAIL",
        "AUSTRALIAPOST",
        "HERMES",
        "ONTRAC",
        "LASERSHIP",
        "DPD",
    }

    def _normalize_carrier_name(self, raw_carrier: str) -> tuple[str, Optional[str]]:
        """Map carrier name to PayPal recognized enum or OTHER + carrier_name_other."""
        cleaned = raw_carrier.strip()
        upper = cleaned.upper().replace(" ", "")

        if upper in self.KNOWN_CARRIERS:
            return upper, None

        for known in self.KNOWN_CARRIERS:
            if known in upper:
                return known, None

        return "OTHER", cleaned

    def format_fulfillment_evidence(
        self,
        bundle: ReconciledDisputeBundle,
        notes: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Generate official PayPal provide-evidence payload dictionary."""
        tracking_info_list: List[Dict[str, Any]] = []

        for shipment in bundle.matched_shipments:
            carrier_name, carrier_other = self._normalize_carrier_name(shipment.carrier_name)
            t_info: Dict[str, Any] = {
                "carrier_name": carrier_name,
                "tracking_number": shipment.tracking_number,
            }
            if carrier_other:
                t_info["carrier_name_other"] = carrier_other

            tracking_info_list.append(t_info)

        # Build grounded notes
        if notes:
            note_text = notes
        elif bundle.matched_shipments:
            s0 = bundle.matched_shipments[0]
            deliv_str = s0.delivery_timestamp.isoformat() if s0.delivery_timestamp else "verified"
            dest_str = f" to recipient matching postal code {s0.shipment_address.postal_code}" if s0.shipment_address and s0.shipment_address.postal_code else ""
            note_text = (
                f"Docket Verified Evidence: Package {s0.tracking_number} ({s0.carrier_name}) "
                f"delivered on {deliv_str}{dest_str}."
            )
        else:
            note_text = "Docket Verified Evidence: Order fulfilled and reconciled."

        evidence_item: Dict[str, Any] = {
            "evidence_type": "PROOF_OF_FULFILLMENT",
            "notes": note_text,
        }

        if tracking_info_list:
            evidence_item["evidence_info"] = {
                "tracking_info": tracking_info_list,
            }

        return {
            "evidences": [evidence_item],
        }


# ============================================================================
# Action Dispatcher
# ============================================================================

class EvidenceDispatcher:
    """Controls and executes evidence submissions to PayPal Disputes API."""

    ALLOWED_PAYPAL_HOSTS: Set[str] = {
        "api-m.sandbox.paypal.com",
        "api-m.paypal.com",
        "api.sandbox.paypal.com",
        "api.paypal.com",
    }

    def __init__(
        self,
        approval_service: ApprovalService,
        audit_logger: Optional[Any] = None,
        http_client: Optional[Any] = None,
        allow_insecure_http: bool = False,
        formatter: Optional[EvidencePayloadFormatter] = None,
    ):
        self.approval_service = approval_service
        self.audit_logger = audit_logger
        self.http_client = http_client or requests.Session()
        self.allow_insecure_http = allow_insecure_http
        self.formatter = formatter or EvidencePayloadFormatter()

        self._submitted_disputes: Set[str] = set()
        self._in_progress_disputes: Set[str] = set()

    def _resolve_provide_evidence_url(self, dispute: DisputeCase) -> str:
        """Extract and validate the HATEOAS action URL for provide_evidence."""
        target_link: Optional[HATEOASLink] = None
        for link in dispute.available_hateoas_actions:
            if link.rel == "provide_evidence":
                target_link = link
                break

        if not target_link:
            raise SubmissionBlockedError(
                f"Dispute {dispute.dispute_id} does not expose an eligible 'provide_evidence' HATEOAS action."
            )

        parsed = urlparse(target_link.href)

        if not self.allow_insecure_http and parsed.scheme.lower() != "https":
            raise SubmissionBlockedError(
                f"Insecure scheme '{parsed.scheme}' rejected for action URL: {target_link.href}"
            )

        if parsed.hostname and parsed.hostname.lower() not in self.ALLOWED_PAYPAL_HOSTS:
            raise SubmissionBlockedError(
                f"Untrusted host '{parsed.hostname}' rejected for PayPal action URL: {target_link.href}"
            )

        return target_link.href

    def dispatch_evidence(
        self,
        dispute: DisputeCase,
        bundle: ReconciledDisputeBundle,
        evaluation: OverallPolicyEvaluation,
        approval_record: Optional[MerchantApprovalRecord],
        idempotency_key: Optional[str] = None,
        custom_notes: Optional[str] = None,
        auth_token: Optional[str] = None,
    ) -> DispatchResult:
        """Perform guarded evidence dispatch to PayPal Disputes API."""
        now = datetime.now(timezone.utc)

        # 1. Deterministic Policy Engine Refusal Barrier
        if not evaluation.is_ready_for_submission():
            violated = [c.rule_identifier for c in evaluation.check_results if c.decision == DecisionType.BLOCK]
            raise SubmissionBlockedError(
                f"Policy engine refusal barrier blocked submission: {evaluation.summary} "
                f"Violated rules: {violated}"
            )

        # 2. Merchant Approval Verification Gate
        if approval_record is None:
            raise MerchantApprovalRequiredError(
                f"Merchant approval is strictly required before dispatching evidence for dispute {dispute.dispute_id}."
            )

        if not approval_record.is_approved():
            raise SubmissionRejectedError(
                f"Merchant rejected evidence submission for dispute {dispute.dispute_id}: "
                f"{approval_record.rejection_reason or 'No rejection reason specified.'}"
            )

        # Format target payload
        payload = self.formatter.format_fulfillment_evidence(bundle=bundle, notes=custom_notes)

        # Verify cryptographic token and payload integrity
        self.approval_service.verify_token(
            token=approval_record.approval_token,
            dispute_id=dispute.dispute_id,
            payload=payload,
        )

        # 3. Idempotency Lock
        if dispute.dispute_id in self._submitted_disputes or dispute.dispute_id in self._in_progress_disputes:
            raise DuplicateSubmissionError(
                f"Evidence submission for dispute {dispute.dispute_id} is already in progress or completed."
            )

        self._in_progress_disputes.add(dispute.dispute_id)

        # 4. Resolve Action URL
        action_url = self._resolve_provide_evidence_url(dispute)

        # 5. Log Dispatch Attempt
        if self.audit_logger:
            self.audit_logger.log_event(
                event_type=AuditEventType.DISPATCH_ATTEMPTED,
                dispute_id=dispute.dispute_id,
                actor=approval_record.merchant_user_id,
                payload={
                    "approval_id": approval_record.approval_id,
                    "target_url": action_url,
                    "idempotency_key": idempotency_key,
                    "payload": payload,
                },
            )

        # 6. Execute Dispatch
        headers: Dict[str, str] = {
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        if auth_token:
            headers["Authorization"] = f"Bearer {auth_token}"

        try:
            resp = self.http_client.post(
                action_url,
                json=payload,
                headers=headers,
                timeout=30,
            )
            status_code = resp.status_code
            correlation_id = resp.headers.get("Paypal-Debug-Id") or resp.headers.get("paypal-debug-id")
            
            try:
                val = resp.json()
                resp_body = val if isinstance(val, dict) else {"raw_text": str(val)}
            except Exception:
                resp_body = {"raw_text": str(resp.text)}

        except Exception as e:
            self._in_progress_disputes.discard(dispute.dispute_id)
            if self.audit_logger:
                self.audit_logger.log_event(
                    event_type=AuditEventType.DISPATCH_FAILED,
                    dispute_id=dispute.dispute_id,
                    actor="SYSTEM",
                    payload={"error": str(e)},
                )
            return DispatchResult(
                success=False,
                dispute_id=dispute.dispute_id,
                submission_timestamp=now,
                error_message=f"HTTP connection failed: {e}",
            )

        self._in_progress_disputes.discard(dispute.dispute_id)

        # 7. Evaluate API Response
        if 200 <= status_code < 300:
            self._submitted_disputes.add(dispute.dispute_id)
            if self.audit_logger:
                self.audit_logger.log_event(
                    event_type=AuditEventType.DISPATCH_SUCCEEDED,
                    dispute_id=dispute.dispute_id,
                    actor="SYSTEM",
                    payload={
                        "status_code": status_code,
                        "correlation_id": correlation_id,
                        "response": resp_body,
                    },
                )
            return DispatchResult(
                success=True,
                dispute_id=dispute.dispute_id,
                submission_timestamp=now,
                paypal_status_code=status_code,
                paypal_response_body=resp_body,
                correlation_id=correlation_id,
            )
        else:
            if self.audit_logger:
                self.audit_logger.log_event(
                    event_type=AuditEventType.DISPATCH_FAILED,
                    dispute_id=dispute.dispute_id,
                    actor="SYSTEM",
                    payload={
                        "status_code": status_code,
                        "correlation_id": correlation_id,
                        "response": resp_body,
                    },
                )
            return DispatchResult(
                success=False,
                dispute_id=dispute.dispute_id,
                submission_timestamp=now,
                paypal_status_code=status_code,
                paypal_response_body=resp_body,
                correlation_id=correlation_id,
                error_message=f"PayPal API returned error status HTTP {status_code}",
            )
