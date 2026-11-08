"""Docket Tamper-Evident Audit Logger & Cryptographic Hash-Chain Engine.

Maintains an append-only, tamper-evident JSONL audit ledger where each event
records the SHA-256 hash of its predecessor, establishing interior chain-integrity
verification for dispute evidence and merchant approvals.

Architectural Guarantees & Operational Boundaries:
- Tamper-Evident Hash Chain: Detects modification of any existing event payload,
  modification of parent_hash links, reordering of events, and deletion of any
  interior event.
- Interior Chain-Integrity Verification: Guarantees that the sequence from the
  genesis event up to any verified event has not been tampered with or modified.
- No Guaranteed Tail-Truncation Detection Without External Anchor: A backward-pointing
  hash chain cannot independently detect deletion of its final event or multiple
  trailing events from disk, as any valid prefix remains internally consistent.
  Independent detection of tail truncation requires a trusted external head-hash
  checkpoint or external commitment.
- No Guaranteed Protection Against Full-Chain Rewriting: Without external root
  anchoring, a local adversary with full file write access could recompute hashes
  from a new genesis root.
- Terminology: This component is a tamper-evident audit ledger with interior
  integrity verification, not an immutable external consensus ledger.
"""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union
from uuid import uuid4

from docket.models.audit import AuditEvent, AuditEventType


# ============================================================================
# Exceptions
# ============================================================================

class AuditError(Exception):
    """Base exception for audit logging errors."""


class AuditVerificationError(AuditError):
    """Raised when audit chain integrity verification detects tampering or corruption."""


# ============================================================================
# Audit Logger
# ============================================================================

class AuditLogger:
    """Append-only tamper-evident cryptographic hash-chain ledger for Docket dispute operations.
    
    Provides interior chain-integrity verification over dispute lifecycle events.
    Notice: Does not provide guaranteed protection against malicious full-chain rewriting
    or guaranteed tail-truncation detection without an external anchor.
    """

    DEFAULT_LOG_PATH = Path("artifacts/audit_trail.jsonl")

    def __init__(
        self,
        storage_path: Optional[Union[str, Path]] = None,
        repository: Optional[Any] = None,
    ):
        self.storage_path = Path(storage_path) if storage_path else self.DEFAULT_LOG_PATH
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)
        self.repository = repository
        self._events: List[AuditEvent] = []
        self._load_existing_events()
        if self.repository and self._events:
            try:
                self.repository.sync_audit_events_from_jsonl(self._events)
            except Exception:
                pass

    def _load_existing_events(self) -> None:
        """Load and parse any existing audit events from the storage file."""
        if not self.storage_path.exists():
            return

        with open(self.storage_path, "r", encoding="utf-8") as f:
            for line_no, line in enumerate(f, start=1):
                stripped = line.strip()
                if stripped:
                    try:
                        data = json.loads(stripped)
                    except json.JSONDecodeError as e:
                        raise AuditVerificationError(f"Corrupt JSON at line {line_no}: {e}")
                    # Convert timestamp back to datetime
                    if isinstance(data.get("timestamp"), str):
                        data["timestamp"] = datetime.fromisoformat(data["timestamp"])
                    self._events.append(AuditEvent(**data))

    def _calculate_event_hash(
        self,
        parent_hash: str,
        event_id: str,
        event_type: str,
        timestamp_iso: str,
        dispute_id: str,
        actor: str,
        payload: Dict[str, Any],
    ) -> str:
        """Compute cryptographic SHA-256 hash chaining event attributes and payload."""
        canonical_payload = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        fingerprint = (
            f"{parent_hash}:{event_id}:{event_type}:{timestamp_iso}:"
            f"{dispute_id}:{actor}:{canonical_payload}"
        )
        return hashlib.sha256(fingerprint.encode("utf-8")).hexdigest()

    def log_event(
        self,
        event_type: AuditEventType,
        dispute_id: str,
        actor: str,
        payload: Optional[Dict[str, Any]] = None,
    ) -> AuditEvent:
        """Append a new tamper-evident event to the cryptographic audit trail."""
        event_payload = payload or {}
        parent_hash = self._events[-1].event_hash if self._events else "GENESIS"
        event_id = f"evt_{uuid4().hex[:12]}"
        now = datetime.now(timezone.utc)
        now_iso = now.isoformat()

        event_hash = self._calculate_event_hash(
            parent_hash=parent_hash,
            event_id=event_id,
            event_type=event_type.value,
            timestamp_iso=now_iso,
            dispute_id=dispute_id,
            actor=actor,
            payload=event_payload,
        )

        event = AuditEvent(
            event_id=event_id,
            parent_hash=parent_hash,
            event_hash=event_hash,
            event_type=event_type,
            timestamp=now,
            dispute_id=dispute_id,
            actor=actor,
            payload=event_payload,
        )

        self._events.append(event)

        # Append to disk immediately
        event_dict = event.model_dump()
        event_dict["timestamp"] = now_iso
        event_dict["event_type"] = event.event_type.value

        with open(self.storage_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(event_dict, separators=(",", ":")) + "\n")

        # Mirror to relational SQLite audit ledger if repository configured
        if self.repository:
            try:
                self.repository.save_audit_event(event)
            except Exception:
                pass

        return event

    def get_events(self, dispute_id: Optional[str] = None) -> List[AuditEvent]:
        """Retrieve audit events, optionally filtered by dispute ID."""
        if dispute_id:
            return [e for e in self._events if e.dispute_id == dispute_id]
        return list(self._events)

    def log_dispute_ingestion(
        self,
        dispute_id: str,
        actor: str,
        payload: Dict[str, Any],
        idempotency_key: Optional[str] = None,
        record_duplicate_attempt: bool = True,
    ) -> Tuple[AuditEvent, bool]:
        """Log a dispute ingestion event with deterministic idempotency verification.

        If an identical dispute ingestion for this dispute_id with identical status and amount
        (or matching idempotency_key) has already been recorded in the ledger:
          - Prevents duplicate logical dispute ingestion.
          - If record_duplicate_attempt is True, records a DUPLICATE_WEBHOOK_RECEIVED event
            in the cryptographic audit trail for delivery-attempt observability without mutating
            the logical dispute state.
          - Returns (event, is_duplicate=True).

        If new:
          - Records DISPUTE_INGESTED in the audit trail.
          - Returns (new_event, is_duplicate=False).
        """
        reason = payload.get("reason")
        status = payload.get("status")
        amount = payload.get("amount")
        currency = payload.get("currency")

        # 1. Check in-memory/JSONL history for duplicate
        for existing_event in self._events:
            if existing_event.event_type == AuditEventType.DISPUTE_INGESTED and existing_event.dispute_id == dispute_id:
                p = existing_event.payload
                matches_key = idempotency_key and p.get("idempotency_key") == idempotency_key
                matches_snapshot = (
                    p.get("reason") == reason
                    and p.get("status") == status
                    and p.get("amount") == amount
                    and p.get("currency") == currency
                )
                if matches_key or matches_snapshot:
                    if record_duplicate_attempt:
                        dup_payload = {
                            "original_event_id": existing_event.event_id,
                            "original_timestamp": existing_event.timestamp.isoformat(),
                            "idempotency_key": idempotency_key or f"{dispute_id}:{status}:{amount}",
                            "delivery_reason": "REPEATED_WEBHOOK_DELIVERY",
                            **payload,
                        }
                        dup_event = self.log_event(
                            event_type=AuditEventType.DUPLICATE_WEBHOOK_RECEIVED,
                            dispute_id=dispute_id,
                            actor=actor,
                            payload=dup_payload,
                        )
                        return dup_event, True
                    return existing_event, True

        # 2. Check relational database unique constraint if available
        if self.repository and idempotency_key:
            try:
                is_db_dup, orig_event_id = self.repository.record_webhook_receipt(
                    event_id=f"rec_{uuid4().hex[:12]}",
                    dispute_id=dispute_id,
                    event_type="DISPUTE_INGESTED",
                    idempotency_key=idempotency_key,
                    payload=payload,
                )
                if is_db_dup:
                    if record_duplicate_attempt:
                        dup_payload = {
                            "original_event_id": orig_event_id,
                            "idempotency_key": idempotency_key,
                            "delivery_reason": "REPEATED_WEBHOOK_DELIVERY",
                            **payload,
                        }
                        dup_event = self.log_event(
                            event_type=AuditEventType.DUPLICATE_WEBHOOK_RECEIVED,
                            dispute_id=dispute_id,
                            actor=actor,
                            payload=dup_payload,
                        )
                        return dup_event, True
                    return self._events[-1], True
            except Exception:
                pass

        ingest_payload = dict(payload)
        if idempotency_key:
            ingest_payload["idempotency_key"] = idempotency_key

        event = self.log_event(
            event_type=AuditEventType.DISPUTE_INGESTED,
            dispute_id=dispute_id,
            actor=actor,
            payload=ingest_payload,
        )

        if self.repository and not idempotency_key:
            try:
                self.repository.record_webhook_receipt(
                    event_id=event.event_id,
                    dispute_id=dispute_id,
                    event_type="DISPUTE_INGESTED",
                    idempotency_key=f"auto_{dispute_id}_{event.event_id}",
                    payload=payload,
                )
            except Exception:
                pass

        return event, False

    def verify_chain_detailed(self) -> Dict[str, Any]:
        """Perform mathematical verification across the entire audit log, returning structured diagnostics.

        Does not raise AuditVerificationError; instead captures detailed error context for telemetry and UI.
        """
        now_iso = datetime.now(timezone.utc).isoformat()
        if not self.storage_path.exists():
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

        records: List[Dict[str, Any]] = []
        with open(self.storage_path, "r", encoding="utf-8") as f:
            for line_no, line in enumerate(f, start=1):
                stripped = line.strip()
                if stripped:
                    try:
                        records.append(json.loads(stripped))
                    except json.JSONDecodeError as e:
                        return {
                            "is_valid": False,
                            "total_events": len(records),
                            "verified_count": 0,
                            "failed_count": 1,
                            "last_verified_at": now_iso,
                            "failed_event_id": None,
                            "error_message": f"Corrupt JSON at line {line_no}: {e}",
                            "event_verifications": [],
                        }

        total = len(records)
        event_verifications = []
        failed_event_id = None
        error_message = None
        verified_count = 0

        chain_broken = False
        for i, rec in enumerate(records):
            event_id = rec.get("event_id", f"index_{i}")
            parent_hash = rec.get("parent_hash")
            event_hash = rec.get("event_hash")
            event_type = rec.get("event_type")
            ts_iso = rec.get("timestamp")
            dispute_id = rec.get("dispute_id")
            actor = rec.get("actor")
            payload = rec.get("payload", {})

            # 1. Verify parent hash link
            parent_valid = False
            if chain_broken:
                parent_valid = False
                if not error_message:
                    error_message = f"Chain already broken before event {event_id}."
                    failed_event_id = event_id
            elif i == 0:
                parent_valid = (parent_hash == "GENESIS")
                if not parent_valid and not error_message:
                    error_message = f"Genesis event {event_id} parent_hash '{parent_hash}' != 'GENESIS'."
                    failed_event_id = event_id
            else:
                prev_event_hash = records[i - 1].get("event_hash")
                parent_valid = (parent_hash == prev_event_hash)
                if not parent_valid and not error_message:
                    error_message = (
                        f"Event {event_id} parent_hash does not match previous hash '{prev_event_hash}'."
                    )
                    failed_event_id = event_id

            # 2. Recalculate event hash
            expected_hash = self._calculate_event_hash(
                parent_hash=parent_hash,
                event_id=event_id,
                event_type=event_type,
                timestamp_iso=ts_iso,
                dispute_id=dispute_id,
                actor=actor,
                payload=payload,
            )
            hash_valid = (event_hash == expected_hash)
            if not hash_valid and not error_message:
                error_message = (
                    f"Event {event_id} hash mismatch. Computed '{expected_hash}' != recorded '{event_hash}'."
                )
                failed_event_id = event_id

            is_event_valid = (not chain_broken) and parent_valid and hash_valid
            if not is_event_valid:
                chain_broken = True
            else:
                verified_count += 1

            event_verifications.append({
                "event_id": event_id,
                "index": i,
                "is_valid": is_event_valid,
                "parent_valid": parent_valid,
                "hash_valid": hash_valid,
            })

        is_valid = (verified_count == total) and (total > 0)
        if total == 0:
            is_valid = True

        return {
            "is_valid": is_valid,
            "total_events": total,
            "verified_count": verified_count,
            "failed_count": total - verified_count,
            "last_verified_at": now_iso,
            "failed_event_id": failed_event_id,
            "error_message": error_message,
            "event_verifications": event_verifications,
        }

    def verify_chain_integrity(self) -> bool:
        """Verify unbroken hash chain and payload integrity across the entire audit log.

        Raises:
            AuditVerificationError: If an unbroken link is severed or an entry was tampered with.
        """
        details = self.verify_chain_detailed()
        if not details["is_valid"]:
            raise AuditVerificationError(
                f"Audit chain verification failed: {details['error_message']}"
            )
        return True
