"""Docket Immutable Audit Logger & Cryptographic Hash-Chain Engine.

Maintains an append-only, tamper-evident JSONL audit ledger where each event
records the SHA-256 hash of its predecessor, establishing mathematical
integrity verification for dispute evidence and merchant approvals.
"""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Union
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
    """Append-only cryptographic hash-chain ledger for Docket dispute operations."""

    DEFAULT_LOG_PATH = Path("artifacts/audit_trail.jsonl")

    def __init__(self, storage_path: Optional[Union[str, Path]] = None):
        self.storage_path = Path(storage_path) if storage_path else self.DEFAULT_LOG_PATH
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)
        self._events: List[AuditEvent] = []
        self._load_existing_events()

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

        return event

    def get_events(self, dispute_id: Optional[str] = None) -> List[AuditEvent]:
        """Retrieve audit events, optionally filtered by dispute ID."""
        if dispute_id:
            return [e for e in self._events if e.dispute_id == dispute_id]
        return list(self._events)

    def verify_chain_integrity(self) -> bool:
        """Verify unbroken hash chain and payload integrity across the entire audit log.
        
        Raises:
            AuditVerificationError: If an unbroken link is severed or an entry was tampered with.
        """
        if not self.storage_path.exists():
            return True

        records: List[Dict[str, Any]] = []
        with open(self.storage_path, "r", encoding="utf-8") as f:
            for line_no, line in enumerate(f, start=1):
                stripped = line.strip()
                if stripped:
                    try:
                        records.append(json.loads(stripped))
                    except json.JSONDecodeError as e:
                        raise AuditVerificationError(f"Corrupt JSON at line {line_no}: {e}")

        if not records:
            return True

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
            if i == 0:
                if parent_hash != "GENESIS":
                    raise AuditVerificationError(
                        f"Audit chain verification failed at genesis event {event_id}: parent_hash is '{parent_hash}', expected 'GENESIS'."
                    )
            else:
                prev_event_hash = records[i - 1].get("event_hash")
                if parent_hash != prev_event_hash:
                    raise AuditVerificationError(
                        f"Audit chain verification failed at event {event_id}: parent_hash '{parent_hash}' "
                        f"does not match previous event hash '{prev_event_hash}'."
                    )

            # 2. Recalculate and verify event hash
            expected_hash = self._calculate_event_hash(
                parent_hash=parent_hash,
                event_id=event_id,
                event_type=event_type,
                timestamp_iso=ts_iso,
                dispute_id=dispute_id,
                actor=actor,
                payload=payload,
            )

            if event_hash != expected_hash:
                raise AuditVerificationError(
                    f"Audit chain verification failed at event {event_id}: calculated hash '{expected_hash}' "
                    f"does not match recorded event_hash '{event_hash}'. Tampering detected."
                )

        return True
