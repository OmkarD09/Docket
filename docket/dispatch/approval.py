"""Docket Merchant Approval Service & Cryptographic Token Engine.

Provides tamper-evident HMAC authorization tokens, expiration validation,
merchant approval recording, and structured human-readable decision summaries.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
import hashlib
import hmac
import json
import os
import secrets
import threading
from typing import Any, Dict, Optional
from uuid import uuid4

from docket.models.dispute import DisputeCase
from docket.models.dispatch import (
    ApprovalDecision,
    ApprovalRequest,
    MerchantApprovalRecord,
)
from docket.models.policy import DecisionType, OverallPolicyEvaluation
from docket.models.reconciliation import ReconciledDisputeBundle


# ============================================================================
# Exceptions
# ============================================================================

class ApprovalError(Exception):
    """Base exception for approval operations."""


class InvalidSignatureError(ApprovalError):
    """Raised when token HMAC signature verification fails."""


class PayloadTamperedError(ApprovalError):
    """Raised when proposed evidence payload has been modified since token creation."""


class TokenExpiredError(ApprovalError):
    """Raised when an approval token has passed its expiration timestamp."""


class DisputeMismatchError(ApprovalError):
    """Raised when approval token was issued for a different dispute ID."""


class MerchantMismatchError(ApprovalError):
    """Raised when approval token was issued for a different merchant user ID."""


class ActionMismatchError(ApprovalError):
    """Raised when approval token was issued for a different action."""


class EvaluationMismatchError(ApprovalError):
    """Raised when approval record evaluation ID does not match current policy evaluation."""


class EvidenceVersionMismatchError(ApprovalError):
    """Raised when approval record evidence version does not match current evidence package."""


class TokenAlreadyUsedError(ApprovalError):
    """Raised when an approval token nonce has already been consumed (replay attack detected)."""


# ============================================================================
# Approval Service
# ============================================================================

class ApprovalService:
    """Manages cryptographic approval tokens and merchant authorization gates.

    Architectural & Concurrency Boundaries:
    - Thread-Safe Single-Process Replay Protection: Nonce checking and consumption are
      synchronized via an internal threading.Lock to guarantee atomic check-and-consume
      under concurrent requests.
    - Process-Restart & Multi-Worker Boundary: `_consumed_nonces` is an in-memory set.
      It does NOT provide durable persistence across process restarts or cross-process
      synchronization across multiple OS worker processes (e.g. gunicorn/uvicorn multi-worker
      deployments) without an external distributed store such as Redis or a shared database.
    """

    DEFAULT_TTL_SECONDS = 86400  # 24 hours

    def __init__(
        self,
        secret_key: Optional[str] = None,
        repository: Optional[Any] = None,
    ):
        self.secret_key = secret_key or os.environ.get("DOCKET_APPROVAL_SECRET", "docket-default-dev-secret-key-replace-in-prod")
        self.repository = repository
        self._consumed_nonces: set[str] = set()
        self._lock = threading.Lock()
        if self.repository:
            try:
                self._consumed_nonces.update(self.repository.list_consumed_nonces())
            except Exception:
                pass

    def _hash_payload(self, payload: Dict[str, Any]) -> str:
        """Compute canonical SHA-256 hex digest of JSON payload."""
        canonical_json = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical_json.encode("utf-8")).hexdigest()

    def _generate_signature(
        self,
        dispute_id: str,
        merchant_user_id: str,
        action: str,
        nonce: str,
        exp_ts: int,
        payload_hash: str,
    ) -> str:
        """Generate HMAC-SHA256 signature binding all critical authorization parameters."""
        message = f"{dispute_id}:{merchant_user_id}:{action}:{nonce}:{exp_ts}:{payload_hash}".encode("utf-8")
        return hmac.new(self.secret_key.encode("utf-8"), message, hashlib.sha256).hexdigest()

    def _generate_legacy_signature(self, dispute_id: str, nonce: str, exp_ts: int, payload_hash: str) -> str:
        """Fallback generator for legacy 5-part token compatibility."""
        message = f"{dispute_id}:{nonce}:{exp_ts}:{payload_hash}".encode("utf-8")
        return hmac.new(self.secret_key.encode("utf-8"), message, hashlib.sha256).hexdigest()

    def create_approval_request(
        self,
        dispute: DisputeCase,
        policy_evaluation: OverallPolicyEvaluation,
        proposed_payload: Dict[str, Any],
        merchant_user_id: str = "merchant_admin",
        action: str = "provide_evidence",
        ttl_seconds: Optional[int] = None,
        bundle: Optional[ReconciledDisputeBundle] = None,
    ) -> ApprovalRequest:
        """Create a new approval request ticket with an HMAC authorization token binding merchant and action."""
        approval_id = f"appr_{uuid4().hex[:12]}"
        nonce = secrets.token_hex(8)
        
        ttl = self.DEFAULT_TTL_SECONDS if ttl_seconds is None else ttl_seconds
        expires_at = datetime.now(timezone.utc) + timedelta(seconds=ttl)
        exp_ts = int(expires_at.timestamp())
        
        payload_hash = self._hash_payload(proposed_payload)
        sig = self._generate_signature(dispute.dispute_id, merchant_user_id, action, nonce, exp_ts, payload_hash)
        
        token = f"{dispute.dispute_id}.{merchant_user_id}.{action}.{nonce}.{exp_ts}.{payload_hash}.{sig}"
        human_summary = self.generate_human_summary(dispute, bundle, policy_evaluation)
        eval_id = getattr(policy_evaluation, "evaluation_id", None) or f"eval_{dispute.dispute_id}"
        ev_version = bundle.reconciled_at.isoformat() if bundle else None

        return ApprovalRequest(
            approval_id=approval_id,
            dispute_id=dispute.dispute_id,
            merchant_user_id=merchant_user_id,
            action=action,
            overall_decision=policy_evaluation.overall_decision.value,
            factual_readiness=policy_evaluation.factual_readiness.value,
            action_readiness=policy_evaluation.action_readiness.value,
            evaluation_id=eval_id,
            evidence_version=ev_version,
            proposed_payload=proposed_payload,
            payload_hash=payload_hash,
            summary_for_human=human_summary,
            created_at=datetime.now(timezone.utc),
            expires_at=expires_at,
            nonce=nonce,
            token=token,
        )

    def verify_token(
        self,
        token: str,
        dispute_id: str,
        payload: Dict[str, Any],
        merchant_user_id: Optional[str] = None,
        action: Optional[str] = None,
        consume_nonce: bool = True,
        dispatch_id: Optional[str] = None,
    ) -> bool:
        """Verify token signature, expiration, bound parameters, and atomic nonce replay prevention.
        
        Raises:
            InvalidSignatureError: If signature is invalid or token malformed.
            DisputeMismatchError: If token dispute ID doesn't match target dispute.
            MerchantMismatchError: If token merchant user ID doesn't match target merchant.
            ActionMismatchError: If token action doesn't match target action.
            TokenExpiredError: If token has expired.
            PayloadTamperedError: If payload doesn't match signed payload hash.
            TokenAlreadyUsedError: If token nonce has already been consumed (replay attack).
        """
        parts = token.split(".")
        if len(parts) == 7:
            tok_dispute_id, tok_merchant_id, tok_action, tok_nonce, tok_exp_ts_str, tok_payload_hash, tok_sig = parts
            is_legacy = False
        elif len(parts) == 5:
            tok_dispute_id, tok_nonce, tok_exp_ts_str, tok_payload_hash, tok_sig = parts
            tok_merchant_id = merchant_user_id or "merchant_admin"
            tok_action = action or "provide_evidence"
            is_legacy = True
        else:
            raise InvalidSignatureError("Malformed approval token: invalid segment count.")

        if tok_dispute_id != dispute_id:
            raise DisputeMismatchError(
                f"Dispute mismatch: token was issued for {tok_dispute_id}, but attempted on {dispute_id}."
            )

        if merchant_user_id and tok_merchant_id != merchant_user_id:
            raise MerchantMismatchError(
                f"Merchant mismatch: token was issued for {tok_merchant_id}, but presented by {merchant_user_id}."
            )

        if action and tok_action != action:
            raise ActionMismatchError(
                f"Action mismatch: token was issued for action '{tok_action}', but attempted for '{action}'."
            )

        try:
            tok_exp_ts = int(tok_exp_ts_str)
        except ValueError:
            raise InvalidSignatureError("Malformed approval token: invalid timestamp format.")

        # Check payload integrity
        current_payload_hash = self._hash_payload(payload)
        if current_payload_hash != tok_payload_hash:
            raise PayloadTamperedError(
                "Payload integrity verification failed: proposed evidence payload was modified after token issuance."
            )

        # Check token expiration
        exp_dt = datetime.fromtimestamp(tok_exp_ts, tz=timezone.utc)
        if datetime.now(timezone.utc) > exp_dt:
            raise TokenExpiredError(
                f"Approval token has expired on {exp_dt.isoformat()} (current: {datetime.now(timezone.utc).isoformat()})."
            )

        # Verify cryptographic signature
        if is_legacy:
            expected_sig = self._generate_legacy_signature(tok_dispute_id, tok_nonce, tok_exp_ts, tok_payload_hash)
        else:
            expected_sig = self._generate_signature(
                tok_dispute_id, tok_merchant_id, tok_action, tok_nonce, tok_exp_ts, tok_payload_hash
            )

        if not hmac.compare_digest(expected_sig, tok_sig):
            raise InvalidSignatureError("Approval token cryptographic signature verification failed.")

        # Atomic anti-replay check under concurrent execution & database durability
        with self._lock:
            if tok_nonce in self._consumed_nonces:
                raise TokenAlreadyUsedError(
                    f"Approval token nonce '{tok_nonce}' has already been consumed. Replay attack blocked."
                )

            if self.repository and self.repository.is_nonce_consumed(tok_nonce):
                self._consumed_nonces.add(tok_nonce)
                raise TokenAlreadyUsedError(
                    f"Approval token nonce '{tok_nonce}' has already been consumed in database. Replay attack blocked."
                )

            if consume_nonce:
                if self.repository:
                    consumed = self.repository.consume_approval_record(tok_nonce, dispatch_id=dispatch_id)
                    if not consumed and self.repository.is_nonce_consumed(tok_nonce):
                        self._consumed_nonces.add(tok_nonce)
                        raise TokenAlreadyUsedError(
                            f"Approval token nonce '{tok_nonce}' has already been consumed. Replay attack blocked."
                        )
                self._consumed_nonces.add(tok_nonce)

        return True

    def record_approval(
        self,
        request: ApprovalRequest,
        merchant_user_id: str,
        decision: ApprovalDecision,
        rejection_reason: Optional[str] = None,
        client_ip: Optional[str] = None,
        user_agent: Optional[str] = None,
    ) -> MerchantApprovalRecord:
        """Record an affirmative approval or explicit rejection by a human merchant with bound metadata."""
        return MerchantApprovalRecord(
            approval_id=request.approval_id,
            dispute_id=request.dispute_id,
            merchant_user_id=merchant_user_id,
            decision=decision,
            action=request.action,
            payload_hash=request.payload_hash,
            evaluation_id=request.evaluation_id,
            evidence_version=request.evidence_version,
            nonce=request.nonce,
            rejection_reason=rejection_reason,
            approved_at=datetime.now(timezone.utc),
            approval_token=request.token,
            client_ip=client_ip,
            user_agent=user_agent,
            is_consumed=False,
        )

    def generate_human_summary(
        self,
        dispute: DisputeCase,
        bundle: Optional[ReconciledDisputeBundle],
        evaluation: OverallPolicyEvaluation,
    ) -> str:
        """Generate human-readable audit briefing for merchant decision-making."""
        lines = [
            "================================================================================",
            "                   DISPUTE REVIEW & EVIDENCE AUTHORIZATION                      ",
            "================================================================================",
            f"Dispute ID: {dispute.dispute_id}",
            f"Reason: {dispute.reason}",
            f"Lifecycle Stage: {dispute.lifecycle_stage.value}",
            f"Status: {dispute.status.value}",
            f"Amount: {dispute.dispute_amount.value} {dispute.dispute_amount.currency_code}",
        ]

        if dispute.seller_response_due_date:
            lines.append(f"Seller Response Due Date: {dispute.seller_response_due_date.isoformat()}")

        lines.append("--------------------------------------------------------------------------------")
        lines.append("RECONCILED EVIDENCE SUMMARY:")

        if bundle and bundle.matched_shipments:
            for s in bundle.matched_shipments:
                lines.append(f"  - Carrier: {s.carrier_name}")
                lines.append(f"  - Tracking Number: {s.tracking_number}")
                lines.append(f"  - Status: {s.tracking_status.value}")
                if s.delivery_timestamp:
                    lines.append(f"  - Delivery Timestamp: {s.delivery_timestamp.isoformat()}")
                if s.shipment_address:
                    lines.append(
                        f"  - Delivery Area: {s.shipment_address.city or ''}, "
                        f"{s.shipment_address.state_or_province or ''} {s.shipment_address.postal_code or ''} "
                        f"({s.shipment_address.country_code or ''})"
                    )
                if s.recipient_signature_present is not None:
                    lines.append(f"  - Signature Present: {s.recipient_signature_present}")
        else:
            lines.append("  - No matched carrier tracking records found.")

        lines.append("--------------------------------------------------------------------------------")
        lines.append("POLICY ENGINE EVALUATION:")
        lines.append(f"  - Overall Decision: {evaluation.overall_decision.value}")
        lines.append(f"  - Factual Readiness: {evaluation.factual_readiness.value}")
        lines.append(f"  - Action Readiness: {evaluation.action_readiness.value}")

        if evaluation.advisories:
            lines.append("  - Advisories:")
            for adv in evaluation.advisories:
                lines.append(f"    * [{adv.rule_identifier}] {adv.explanation}")

        lines.append("--------------------------------------------------------------------------------")
        if evaluation.is_ready_for_submission():
            lines.append("Recommendation: Ready for submission. Verified evidence matches dispute criteria.")
        else:
            lines.append("Recommendation: Submission BLOCKED by deterministic policy rules. Do not submit.")
        lines.append("================================================================================")

        return "\n".join(lines)

