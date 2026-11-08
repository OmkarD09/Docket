"""Docket SQLite Repository Layer.

Handles typed CRUD operations, domain model serialization/deserialization,
relational foreign key integrity, atomic transactions, and deduplicated
webhook ingestion.
"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import sqlite3
from typing import Any, Dict, List, Optional, Tuple, Union

from docket.database.connection import DatabaseConnection
from docket.models.dispute import (
    DisputeCase,
    DisputeLifecycleStage,
    DisputeReason,
    DisputeStatus,
    HATEOASLink,
    Money,
)
from docket.models.evidence import (
    Address,
    ClaimEpistemicMetadata,
    ClaimStatus,
    ClaimType,
    CustomerMessageRecord,
    EvidenceBasis,
    ExtractedClaim,
    OrderRecord,
    RefundRecord,
    ShipmentRecord,
    SourceCitation,
    SourceType,
    TrackingStatus,
    VerificationStatus,
)
from docket.models.policy import (
    DecisionType,
    OverallPolicyEvaluation,
    PolicyCheckResult,
)
from docket.models.dispatch import (
    ApprovalDecision,
    ApprovalRequest,
    DispatchResult,
    MerchantApprovalRecord,
)
from docket.models.audit import AuditEvent, AuditEventType
from docket.models.reconciliation import (
    CandidateMatch,
    MatchConfidence,
    MatchStrategy,
    ReconciledDisputeBundle,
    ReconciliationDiscrepancy,
    ReconciliationStatus,
)


class DocketRepository:
    """Relational repository providing durable persistence for Docket dispute operations."""

    def __init__(self, connection: Optional[DatabaseConnection] = None, db_path: Optional[Union[str, Path]] = None):
        if connection:
            self.conn = connection
        else:
            self.conn = DatabaseConnection(db_path=db_path)

    # ========================================================================
    # Disputes CRUD
    # ========================================================================

    def save_dispute(
        self,
        dispute: DisputeCase,
        scenario_id: Optional[str] = None,
        has_prompt_threat: bool = False,
        approval_request: Optional[ApprovalRequest] = None,
        dispatch_result: Optional[DispatchResult] = None,
        cur: Optional[sqlite3.Cursor] = None,
    ) -> None:
        """Insert or update a dispute record with decimal-safe money formatting."""
        now_iso = datetime.now(timezone.utc).isoformat()
        created_at = (
            dispute.dispute_create_time.isoformat()
            if dispute.dispute_create_time
            else now_iso
        )
        response_due = (
            dispute.seller_response_due_date.isoformat()
            if dispute.seller_response_due_date
            else None
        )
        buyer_tx = dispute.buyer_transaction_id or dispute.disputed_transaction_id
        amount_str = str(dispute.dispute_amount.value)
        currency_str = dispute.dispute_amount.currency_code
        reason_str = (
            dispute.reason.value
            if hasattr(dispute.reason, "value")
            else str(dispute.reason)
        )
        status_str = (
            dispute.status.value
            if hasattr(dispute.status, "value")
            else str(dispute.status)
        )
        stage_str = (
            dispute.lifecycle_stage.value
            if hasattr(dispute.lifecycle_stage, "value")
            else str(dispute.lifecycle_stage)
        )
        raw_msgs = json.dumps(dispute.raw_messages)
        appr_req_json = (
            approval_request.model_dump_json() if approval_request else None
        )
        dispatch_json = (
            dispatch_result.model_dump_json() if dispatch_result else None
        )

        sql = """
        INSERT INTO disputes (
            dispute_id, reason, status, lifecycle_stage, amount, currency,
            buyer_tx_id, response_due_date, created_at, raw_messages, updated_at,
            scenario_id, has_prompt_threat, approval_request, dispatch_result
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(dispute_id) DO UPDATE SET
            reason = excluded.reason,
            status = excluded.status,
            lifecycle_stage = excluded.lifecycle_stage,
            amount = excluded.amount,
            currency = excluded.currency,
            buyer_tx_id = excluded.buyer_tx_id,
            response_due_date = excluded.response_due_date,
            raw_messages = excluded.raw_messages,
            updated_at = excluded.updated_at,
            scenario_id = COALESCE(excluded.scenario_id, disputes.scenario_id),
            has_prompt_threat = excluded.has_prompt_threat,
            approval_request = COALESCE(excluded.approval_request, disputes.approval_request),
            dispatch_result = COALESCE(excluded.dispatch_result, disputes.dispatch_result);
        """
        params = (
            dispute.dispute_id,
            reason_str,
            status_str,
            stage_str,
            amount_str,
            currency_str,
            buyer_tx,
            response_due,
            created_at,
            raw_msgs,
            now_iso,
            scenario_id,
            1 if has_prompt_threat else 0,
            appr_req_json,
            dispatch_json,
        )

        if cur:
            cur.execute(sql, params)
        else:
            with self.conn.transaction() as c:
                c.execute(sql, params)

    def get_dispute(self, dispute_id: str) -> Optional[DisputeCase]:
        """Retrieve a DisputeCase domain object by ID."""
        row = self.conn.fetchone("SELECT * FROM disputes WHERE dispute_id = ?", (dispute_id,))
        if not row:
            return None
        return self._row_to_dispute(row)

    def list_disputes(self) -> List[DisputeCase]:
        """List all stored disputes."""
        rows = self.conn.fetchall("SELECT * FROM disputes ORDER BY created_at DESC")
        return [self._row_to_dispute(r) for r in rows]

    def count_disputes(self) -> int:
        """Count total disputes in storage."""
        row = self.conn.fetchone("SELECT COUNT(*) AS cnt FROM disputes")
        return row["cnt"] if row else 0

    def update_dispute_status(
        self,
        dispute_id: str,
        status: str,
        dispatch_result: Optional[DispatchResult] = None,
        approval_request: Optional[ApprovalRequest] = None,
    ) -> None:
        """Update dispute lifecycle and execution status."""
        now_iso = datetime.now(timezone.utc).isoformat()
        dispatch_json = dispatch_result.model_dump_json() if dispatch_result else None
        appr_json = approval_request.model_dump_json() if approval_request else None

        sql = """
        UPDATE disputes SET
            status = ?,
            updated_at = ?,
            dispatch_result = COALESCE(?, dispatch_result),
            approval_request = COALESCE(?, approval_request)
        WHERE dispute_id = ?;
        """
        self.conn.execute(sql, (status, now_iso, dispatch_json, appr_json, dispute_id))

    def _row_to_dispute(self, row: sqlite3.Row) -> DisputeCase:
        """Deserialize a SQLite disputes row into a DisputeCase."""
        raw_msgs = json.loads(row["raw_messages"]) if row["raw_messages"] else []
        created_dt = (
            datetime.fromisoformat(row["created_at"])
            if row["created_at"]
            else None
        )
        due_dt = (
            datetime.fromisoformat(row["response_due_date"])
            if row["response_due_date"]
            else None
        )

        try:
            reason = DisputeReason(row["reason"])
        except ValueError:
            reason = row["reason"]

        try:
            status = DisputeStatus(row["status"])
        except ValueError:
            status = DisputeStatus.OTHER

        try:
            stage = DisputeLifecycleStage(row["lifecycle_stage"])
        except ValueError:
            stage = DisputeLifecycleStage.INQUIRY

        amount = Money(
            value=Decimal(row["amount"]),
            currency_code=row["currency"],
        )

        return DisputeCase(
            dispute_id=row["dispute_id"],
            reason=reason,
            lifecycle_stage=stage,
            status=status,
            dispute_amount=amount,
            buyer_transaction_id=row["buyer_tx_id"],
            seller_response_due_date=due_dt,
            dispute_create_time=created_dt,
            raw_messages=raw_msgs,
        )

    # ========================================================================
    # Source Records (Order, Shipment, Communication, Refund)
    # ========================================================================

    def save_source_record(
        self,
        dispute_id: str,
        source_id: str,
        source_type: str,
        record_type: str,
        payload: Dict[str, Any],
        cur: Optional[sqlite3.Cursor] = None,
    ) -> None:
        """Insert or replace an evidence source record."""
        now_iso = datetime.now(timezone.utc).isoformat()
        payload_str = json.dumps(payload, separators=(",", ":"))
        sql = """
        INSERT INTO source_records (source_id, dispute_id, source_type, record_type, payload, created_at)
        VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(source_id) DO UPDATE SET
            dispute_id = excluded.dispute_id,
            source_type = excluded.source_type,
            record_type = excluded.record_type,
            payload = excluded.payload;
        """
        params = (source_id, dispute_id, source_type, record_type, payload_str, now_iso)
        if cur:
            cur.execute(sql, params)
        else:
            with self.conn.transaction() as c:
                c.execute(sql, params)

    def get_source_records(self, dispute_id: str) -> List[Dict[str, Any]]:
        """Retrieve all source records associated with a dispute."""
        rows = self.conn.fetchall(
            "SELECT * FROM source_records WHERE dispute_id = ? ORDER BY created_at ASC",
            (dispute_id,),
        )
        results = []
        for r in rows:
            results.append({
                "source_id": r["source_id"],
                "dispute_id": r["dispute_id"],
                "source_type": r["source_type"],
                "record_type": r["record_type"],
                "payload": json.loads(r["payload"]),
                "created_at": r["created_at"],
            })
        return results

    # ========================================================================
    # Extracted Claims & Epistemic Metadata
    # ========================================================================

    def save_claims(
        self,
        dispute_id: str,
        claims: List[ExtractedClaim],
        cur: Optional[sqlite3.Cursor] = None,
    ) -> None:
        """Persist a list of extracted claims and citations for a dispute."""
        now_iso = datetime.now(timezone.utc).isoformat()

        def _do_save(c_cursor: sqlite3.Cursor):
            # Clear existing claims for this dispute to maintain clean state
            c_cursor.execute("DELETE FROM extracted_claims WHERE dispute_id = ?", (dispute_id,))
            for claim in claims:
                ctype = (
                    claim.claim_type.value
                    if hasattr(claim.claim_type, "value")
                    else str(claim.claim_type)
                )
                cstat = (
                    claim.claim_status.value
                    if hasattr(claim.claim_status, "value")
                    else str(claim.claim_status)
                )
                epistemic_json = (
                    claim.epistemic_metadata.model_dump_json()
                    if claim.epistemic_metadata
                    else None
                )
                citations_json = json.dumps(
                    [c.model_dump(mode="json") for c in claim.supporting_sources],
                    separators=(",", ":"),
                )
                c_cursor.execute(
                    """
                    INSERT INTO extracted_claims (
                        claim_id, dispute_id, claim_type, factual_assertion,
                        claim_status, epistemic_metadata, citations, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        claim.claim_id,
                        dispute_id,
                        ctype,
                        claim.factual_assertion,
                        cstat,
                        epistemic_json,
                        citations_json,
                        now_iso,
                    ),
                )

        if cur:
            _do_save(cur)
        else:
            with self.conn.transaction() as c:
                _do_save(c)

    def get_claims(self, dispute_id: str) -> List[ExtractedClaim]:
        """Retrieve and reconstruct ExtractedClaim models for a dispute."""
        rows = self.conn.fetchall(
            "SELECT * FROM extracted_claims WHERE dispute_id = ? ORDER BY created_at ASC",
            (dispute_id,),
        )
        claims: List[ExtractedClaim] = []
        for r in rows:
            raw_citations = json.loads(r["citations"])
            citations = [SourceCitation(**cit) for cit in raw_citations]

            epistemic = None
            if r["epistemic_metadata"]:
                epistemic = ClaimEpistemicMetadata(**json.loads(r["epistemic_metadata"]))

            try:
                ctype = ClaimType(r["claim_type"])
            except ValueError:
                ctype = ClaimType.OTHER

            try:
                cstat = ClaimStatus(r["claim_status"])
            except ValueError:
                cstat = ClaimStatus.PROPOSED

            claims.append(
                ExtractedClaim(
                    claim_id=r["claim_id"],
                    claim_type=ctype,
                    factual_assertion=r["factual_assertion"],
                    supporting_sources=citations,
                    claim_status=cstat,
                    epistemic_metadata=epistemic,
                )
            )
        return claims

    # ========================================================================
    # Policy Evaluations
    # ========================================================================

    def save_policy_evaluation(
        self,
        dispute_id: str,
        evaluation: OverallPolicyEvaluation,
        cur: Optional[sqlite3.Cursor] = None,
    ) -> None:
        """Persist deterministic policy evaluation results."""
        eval_id = f"eval_{dispute_id}"
        chk_json = json.dumps([r.model_dump(mode="json") for r in evaluation.check_results])
        adv_json = json.dumps([a.model_dump(mode="json") for a in evaluation.advisories])
        eval_dt_str = evaluation.evaluated_at.isoformat()

        sql = """
        INSERT INTO policy_evaluations (
            evaluation_id, dispute_id, overall_decision, factual_readiness,
            action_readiness, check_results, advisories, summary, evaluated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(evaluation_id) DO UPDATE SET
            overall_decision = excluded.overall_decision,
            factual_readiness = excluded.factual_readiness,
            action_readiness = excluded.action_readiness,
            check_results = excluded.check_results,
            advisories = excluded.advisories,
            summary = excluded.summary,
            evaluated_at = excluded.evaluated_at;
        """
        params = (
            eval_id,
            dispute_id,
            evaluation.overall_decision.value,
            evaluation.factual_readiness.value,
            evaluation.action_readiness.value,
            chk_json,
            adv_json,
            evaluation.summary,
            eval_dt_str,
        )

        if cur:
            cur.execute(sql, params)
        else:
            with self.conn.transaction() as c:
                c.execute(sql, params)

    def get_policy_evaluation(self, dispute_id: str) -> Optional[OverallPolicyEvaluation]:
        """Retrieve and reconstruct OverallPolicyEvaluation for a dispute."""
        row = self.conn.fetchone(
            "SELECT * FROM policy_evaluations WHERE dispute_id = ?",
            (dispute_id,),
        )
        if not row:
            return None

        chk_results = [PolicyCheckResult(**r) for r in json.loads(row["check_results"])]
        advisories = [PolicyCheckResult(**a) for a in json.loads(row["advisories"])]
        eval_dt = datetime.fromisoformat(row["evaluated_at"])

        return OverallPolicyEvaluation(
            dispute_id=row["dispute_id"],
            overall_decision=DecisionType(row["overall_decision"]),
            factual_readiness=DecisionType(row["factual_readiness"]),
            action_readiness=DecisionType(row["action_readiness"]),
            check_results=chk_results,
            advisories=advisories,
            summary=row["summary"],
            evaluated_at=eval_dt,
        )

    # ========================================================================
    # Merchant Approvals
    # ========================================================================

    def save_approval_record(
        self,
        record: MerchantApprovalRecord,
        cur: Optional[sqlite3.Cursor] = None,
    ) -> None:
        """Persist a merchant approval record."""
        sql = """
        INSERT INTO merchant_approvals (
            approval_id, dispute_id, merchant_user_id, decision,
            rejection_reason, approved_at, approval_token, client_ip, user_agent
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(approval_id) DO UPDATE SET
            decision = excluded.decision,
            rejection_reason = excluded.rejection_reason,
            approved_at = excluded.approved_at,
            approval_token = excluded.approval_token;
        """
        params = (
            record.approval_id,
            record.dispute_id,
            record.merchant_user_id,
            record.decision.value,
            record.rejection_reason,
            record.approved_at.isoformat(),
            record.approval_token,
            record.client_ip,
            record.user_agent,
        )

        if cur:
            cur.execute(sql, params)
        else:
            with self.conn.transaction() as c:
                c.execute(sql, params)

    def get_approval_record(self, dispute_id: str) -> Optional[MerchantApprovalRecord]:
        """Retrieve the latest MerchantApprovalRecord for a dispute."""
        row = self.conn.fetchone(
            "SELECT * FROM merchant_approvals WHERE dispute_id = ? ORDER BY approved_at DESC LIMIT 1",
            (dispute_id,),
        )
        if not row:
            return None

        return MerchantApprovalRecord(
            approval_id=row["approval_id"],
            dispute_id=row["dispute_id"],
            merchant_user_id=row["merchant_user_id"],
            decision=ApprovalDecision(row["decision"]),
            rejection_reason=row["rejection_reason"],
            approved_at=datetime.fromisoformat(row["approved_at"]),
            approval_token=row["approval_token"],
            client_ip=row["client_ip"],
            user_agent=row["user_agent"],
        )

    # ========================================================================
    # Webhook Receipts & Idempotency Constraints
    # ========================================================================

    def record_webhook_receipt(
        self,
        event_id: str,
        dispute_id: Optional[str],
        event_type: str,
        idempotency_key: str,
        payload: Dict[str, Any],
    ) -> Tuple[bool, Optional[str]]:
        """Atomically record incoming webhook notification with strict idempotency constraint.
        
        Returns:
            (is_duplicate: bool, original_event_id: Optional[str])
        """
        now_iso = datetime.now(timezone.utc).isoformat()
        payload_str = json.dumps(payload, sort_keys=True, separators=(",", ":"))

        # If dispute_id is specified, ensure dispute exists so foreign key constraint is satisfied
        if dispute_id:
            reason = payload.get("reason", "MERCHANDISE_OR_SERVICE_NOT_RECEIVED")
            status = payload.get("status", "WAITING_FOR_SELLER_RESPONSE")
            amount = str(payload.get("amount", "0.00"))
            currency = payload.get("currency", "USD")
            with self.conn.transaction() as cur:
                cur.execute(
                    """
                    INSERT OR IGNORE INTO disputes (
                        dispute_id, reason, status, lifecycle_stage, amount, currency, created_at, updated_at
                    ) VALUES (?, ?, ?, 'INQUIRY', ?, ?, ?, ?)
                    """,
                    (dispute_id, reason, status, amount, currency, now_iso, now_iso),
                )

        # Check existing receipt for duplicate idempotency key
        existing = self.conn.fetchone(
            "SELECT event_id FROM webhook_receipts WHERE idempotency_key = ?",
            (idempotency_key,),
        )
        if existing:
            return True, existing["event_id"]

        try:
            with self.conn.transaction() as cur:
                cur.execute(
                    """
                    INSERT INTO webhook_receipts (
                        event_id, dispute_id, event_type, idempotency_key, payload, received_at
                    ) VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (event_id, dispute_id, event_type, idempotency_key, payload_str, now_iso),
                )
            return False, event_id
        except sqlite3.IntegrityError:
            # UNIQUE constraint on idempotency_key caught
            row = self.conn.fetchone(
                "SELECT event_id FROM webhook_receipts WHERE idempotency_key = ?",
                (idempotency_key,),
            )
            orig_id = row["event_id"] if row else None
            return True, orig_id

    # ========================================================================
    # Audit Events & Tamper-Evident Hash-Chain Ledger
    # ========================================================================

    def save_audit_event(
        self,
        event: AuditEvent,
        cur: Optional[sqlite3.Cursor] = None,
    ) -> None:
        """Insert a cryptographically chained audit event row."""
        sql = """
        INSERT INTO audit_events (
            event_id, parent_hash, event_hash, event_type,
            timestamp, dispute_id, actor, payload
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(event_id) DO NOTHING;
        """
        payload_str = json.dumps(event.payload, sort_keys=True, separators=(",", ":"))
        params = (
            event.event_id,
            event.parent_hash,
            event.event_hash,
            event.event_type.value,
            event.timestamp.isoformat(),
            event.dispute_id,
            event.actor,
            payload_str,
        )

        if cur:
            cur.execute(sql, params)
        else:
            with self.conn.transaction() as c:
                c.execute(sql, params)

    def get_audit_events(self, dispute_id: Optional[str] = None) -> List[AuditEvent]:
        """Fetch audit events in chronological order, optionally filtered by dispute ID."""
        if dispute_id:
            rows = self.conn.fetchall(
                "SELECT * FROM audit_events WHERE dispute_id = ? ORDER BY rowid ASC",
                (dispute_id,),
            )
        else:
            rows = self.conn.fetchall("SELECT * FROM audit_events ORDER BY rowid ASC")

        events: List[AuditEvent] = []
        for r in rows:
            events.append(
                AuditEvent(
                    event_id=r["event_id"],
                    parent_hash=r["parent_hash"],
                    event_hash=r["event_hash"],
                    event_type=AuditEventType(r["event_type"]),
                    timestamp=datetime.fromisoformat(r["timestamp"]),
                    dispute_id=r["dispute_id"],
                    actor=r["actor"],
                    payload=json.loads(r["payload"]),
                )
            )
        return events

    def verify_db_audit_chain(self) -> Dict[str, Any]:
        """Perform cryptographic verification across all rows in audit_events table."""
        now_iso = datetime.now(timezone.utc).isoformat()
        rows = self.conn.fetchall("SELECT * FROM audit_events ORDER BY rowid ASC")
        if not rows:
            return {
                "is_valid": True,
                "total_events": 0,
                "verified_count": 0,
                "failed_count": 0,
                "last_verified_at": now_iso,
                "failed_event_id": None,
                "error_message": None,
                "event_verifications": [],
            }

        prev_hash = "GENESIS"
        verified_count = 0
        verifications = []

        for row in rows:
            ev_id = row["event_id"]
            parent_hash = row["parent_hash"]
            ev_hash = row["event_hash"]
            ev_type = row["event_type"]
            ts = row["timestamp"]
            d_id = row["dispute_id"]
            actor = row["actor"]
            p_dict = json.loads(row["payload"])
            canon_p = json.dumps(p_dict, sort_keys=True, separators=(",", ":"))

            # 1. Verify parent hash link
            if parent_hash != prev_hash:
                err = f"Broken parent link at {ev_id}: expected {prev_hash}, got {parent_hash}"
                return {
                    "is_valid": False,
                    "total_events": len(rows),
                    "verified_count": verified_count,
                    "failed_count": len(rows) - verified_count,
                    "last_verified_at": now_iso,
                    "failed_event_id": ev_id,
                    "error_message": err,
                    "event_verifications": verifications,
                }

            # 2. Recompute expected hash
            fingerprint = f"{parent_hash}:{ev_id}:{ev_type}:{ts}:{d_id}:{actor}:{canon_p}"
            expected = hashlib.sha256(fingerprint.encode("utf-8")).hexdigest()
            if ev_hash != expected:
                err = f"Hash mismatch at {ev_id}: payload or metadata modified"
                return {
                    "is_valid": False,
                    "total_events": len(rows),
                    "verified_count": verified_count,
                    "failed_count": len(rows) - verified_count,
                    "last_verified_at": now_iso,
                    "failed_event_id": ev_id,
                    "error_message": err,
                    "event_verifications": verifications,
                }

            verifications.append({"event_id": ev_id, "is_valid": True})
            prev_hash = ev_hash
            verified_count += 1

        return {
            "is_valid": True,
            "total_events": len(rows),
            "verified_count": verified_count,
            "failed_count": 0,
            "last_verified_at": now_iso,
            "failed_event_id": None,
            "error_message": None,
            "event_verifications": verifications,
        }

    # ========================================================================
    # Full Case Persistence & Hydration
    # ========================================================================

    def save_full_case(
        self,
        dispute: DisputeCase,
        bundle: ReconciledDisputeBundle,
        evaluation: OverallPolicyEvaluation,
        claims: List[ExtractedClaim],
        scenario_id: Optional[str] = None,
        has_prompt_threat: bool = False,
        approval_request: Optional[ApprovalRequest] = None,
        approval_record: Optional[MerchantApprovalRecord] = None,
        dispatch_result: Optional[DispatchResult] = None,
    ) -> None:
        """Persist a complete case, evidence bundle, claims, evaluation, and approvals atomically."""
        with self.conn.transaction() as cur:
            # 1. Dispute table
            self.save_dispute(
                dispute=dispute,
                scenario_id=scenario_id,
                has_prompt_threat=has_prompt_threat,
                approval_request=approval_request,
                dispatch_result=dispatch_result,
                cur=cur,
            )

            # 2. Source records from bundle
            if bundle.matched_order:
                self.save_source_record(
                    dispute_id=dispute.dispute_id,
                    source_id=f"ord_{bundle.matched_order.order_id}",
                    source_type=SourceType.ORDER_INVOICE.value,
                    record_type="OrderRecord",
                    payload=bundle.matched_order.model_dump(mode="json"),
                    cur=cur,
                )

            for s in bundle.matched_shipments:
                self.save_source_record(
                    dispute_id=dispute.dispute_id,
                    source_id=f"ship_{s.tracking_number}",
                    source_type=SourceType.CARRIER_TRACKING.value,
                    record_type="ShipmentRecord",
                    payload=s.model_dump(mode="json"),
                    cur=cur,
                )

            for r in bundle.matched_refunds:
                self.save_source_record(
                    dispute_id=dispute.dispute_id,
                    source_id=f"ref_{r.refund_id}",
                    source_type=SourceType.REFUND_LEDGER.value,
                    record_type="RefundRecord",
                    payload=r.model_dump(mode="json"),
                    cur=cur,
                )

            for c in bundle.matched_communications:
                self.save_source_record(
                    dispute_id=dispute.dispute_id,
                    source_id=f"comm_{c.message_id}",
                    source_type=SourceType.CUSTOMER_COMMUNICATION.value,
                    record_type="CustomerMessageRecord",
                    payload=c.model_dump(mode="json"),
                    cur=cur,
                )

            # 3. Claims
            self.save_claims(dispute.dispute_id, claims, cur=cur)

            # 4. Evaluation
            self.save_policy_evaluation(dispute.dispute_id, evaluation, cur=cur)

            # 5. Approval record if exists
            if approval_record:
                self.save_approval_record(approval_record, cur=cur)

    def load_persisted_cases(self) -> List[Dict[str, Any]]:
        """Load all persisted disputes and associated evidence, claims, evaluations, and approvals from SQLite."""
        from docket.reconciliation.engine import EvidenceReconciler

        rows = self.conn.fetchall("SELECT * FROM disputes ORDER BY created_at ASC")
        cases = []
        for row in rows:
            dispute_id = row["dispute_id"]
            dispute = self._row_to_dispute(row)
            source_rows = self.get_source_records(dispute_id)

            orders = [OrderRecord(**sr["payload"]) for sr in source_rows if sr["record_type"] == "OrderRecord"]
            shipments = [ShipmentRecord(**sr["payload"]) for sr in source_rows if sr["record_type"] == "ShipmentRecord"]
            refunds = [RefundRecord(**sr["payload"]) for sr in source_rows if sr["record_type"] == "RefundRecord"]
            comms = [CustomerMessageRecord(**sr["payload"]) for sr in source_rows if sr["record_type"] == "CustomerMessageRecord"]

            reconciler = EvidenceReconciler(
                orders=orders,
                shipments=shipments,
                refunds=refunds,
                communications=comms,
            )
            bundle = reconciler.reconcile_dispute(dispute)
            if not bundle.matched_order and orders:
                # Reconstitute direct correlation from persisted matched records
                bundle = ReconciledDisputeBundle(
                    dispute_id=dispute_id,
                    status=ReconciliationStatus.RECONCILED,
                    matched_order=orders[0],
                    matched_shipments=shipments,
                    matched_refunds=refunds,
                    matched_communications=comms,
                )
            elif not bundle.matched_shipments and shipments:
                bundle = bundle.model_copy(update={"matched_shipments": shipments})
            claims = self.get_claims(dispute_id)
            evaluation = self.get_policy_evaluation(dispute_id)
            approval_record = self.get_approval_record(dispute_id)

            approval_request = None
            if row["approval_request"]:
                approval_request = ApprovalRequest(**json.loads(row["approval_request"]))

            dispatch_result = None
            if row["dispatch_result"]:
                dispatch_result = DispatchResult(**json.loads(row["dispatch_result"]))

            cases.append({
                "dispute": dispute,
                "bundle": bundle,
                "evaluation": evaluation,
                "claims": claims,
                "scenario_id": row["scenario_id"],
                "has_prompt_threat": bool(row["has_prompt_threat"]),
                "approval_request": approval_request,
                "approval_record": approval_record,
                "dispatch_result": dispatch_result,
            })
        return cases

    def sync_audit_events_from_jsonl(self, events: List[AuditEvent]) -> int:
        """Import missing audit events into SQLite table to maintain parity with JSONL log."""
        inserted = 0
        with self.conn.transaction() as cur:
            for event in events:
                row = self.conn.fetchone("SELECT 1 FROM audit_events WHERE event_id = ?", (event.event_id,))
                if not row:
                    self.save_audit_event(event, cur=cur)
                    inserted += 1
        return inserted

