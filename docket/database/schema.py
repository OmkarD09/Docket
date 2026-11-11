"""SQLite Database Schema Definitions and Migrations for Docket.

Provides DDL and schema management for:
1. disputes: Core dispute cases with decimal-safe amounts, categorization, and archival.
2. source_records: Linked evidence records (orders, shipments, communications, refunds).
3. extracted_claims: Semantically extracted and policy-checked factual claims.
4. policy_evaluations: Deterministic invariant evaluations and advisory outcomes.
5. merchant_approvals: Tamper-evident affirmative merchant approval records with single-use nonce tracking and deletion protection (ON DELETE RESTRICT).
6. webhook_receipts: Ingested webhook events with atomic idempotency constraints.
7. audit_events: Cryptographically chained backward hash-chain audit ledger entries.
8. schema_migrations: Formal schema versioning ledger for safe, repeatable database migrations.
"""

from __future__ import annotations

from datetime import datetime, timezone
import sqlite3
from typing import Any, Dict, List


TABLES_DDL = """
-- 1. Disputes table with soft-archival and provenance categorization
CREATE TABLE IF NOT EXISTS disputes (
    dispute_id TEXT PRIMARY KEY,
    reason TEXT NOT NULL,
    status TEXT NOT NULL,
    lifecycle_stage TEXT NOT NULL,
    amount TEXT NOT NULL,
    currency TEXT NOT NULL,
    buyer_tx_id TEXT,
    response_due_date TEXT,
    created_at TEXT NOT NULL,
    raw_messages TEXT NOT NULL DEFAULT '[]',
    updated_at TEXT NOT NULL,
    scenario_id TEXT,
    has_prompt_threat INTEGER NOT NULL DEFAULT 0,
    dispute_category TEXT NOT NULL DEFAULT 'SYNTHETIC_BENCHMARK',
    is_archived INTEGER NOT NULL DEFAULT 0,
    archived_at TEXT,
    archival_reason TEXT,
    approval_request TEXT,
    dispatch_result TEXT
);

-- 2. Source records (OrderRecord, ShipmentRecord, CustomerMessageRecord, RefundRecord)
CREATE TABLE IF NOT EXISTS source_records (
    source_id TEXT PRIMARY KEY,
    dispute_id TEXT NOT NULL,
    source_type TEXT NOT NULL,
    record_type TEXT NOT NULL,
    payload TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY (dispute_id) REFERENCES disputes (dispute_id) ON DELETE CASCADE
);

-- 3. Extracted claims with epistemic metadata & citations
CREATE TABLE IF NOT EXISTS extracted_claims (
    claim_id TEXT PRIMARY KEY,
    dispute_id TEXT NOT NULL,
    claim_type TEXT NOT NULL,
    factual_assertion TEXT NOT NULL,
    claim_status TEXT NOT NULL,
    epistemic_metadata TEXT,
    citations TEXT NOT NULL DEFAULT '[]',
    created_at TEXT NOT NULL,
    FOREIGN KEY (dispute_id) REFERENCES disputes (dispute_id) ON DELETE CASCADE
);

-- 4. Policy evaluations (deterministic outcome, rule evaluations, invariant assertions)
CREATE TABLE IF NOT EXISTS policy_evaluations (
    evaluation_id TEXT PRIMARY KEY,
    dispute_id TEXT NOT NULL,
    overall_decision TEXT NOT NULL,
    factual_readiness TEXT NOT NULL,
    action_readiness TEXT NOT NULL,
    check_results TEXT NOT NULL DEFAULT '[]',
    advisories TEXT NOT NULL DEFAULT '[]',
    summary TEXT,
    evaluated_at TEXT NOT NULL,
    FOREIGN KEY (dispute_id) REFERENCES disputes (dispute_id) ON DELETE CASCADE
);

-- 5. Merchant approvals (ON DELETE RESTRICT - prevents ordinary dispute cascade)
CREATE TABLE IF NOT EXISTS merchant_approvals (
    approval_id TEXT PRIMARY KEY,
    dispute_id TEXT NOT NULL,
    merchant_user_id TEXT NOT NULL,
    decision TEXT NOT NULL,
    notes TEXT,
    action TEXT NOT NULL DEFAULT 'provide_evidence',
    payload_hash TEXT NOT NULL DEFAULT '',
    evaluation_id TEXT,
    evidence_version TEXT,
    nonce TEXT,
    is_consumed INTEGER NOT NULL DEFAULT 0,
    consumed_at TEXT,
    consumed_by_dispatch_id TEXT,
    rejection_reason TEXT,
    approved_at TEXT NOT NULL,
    approval_token TEXT,
    client_ip TEXT,
    user_agent TEXT,
    FOREIGN KEY (dispute_id) REFERENCES disputes (dispute_id) ON DELETE RESTRICT
);

-- 6. Webhook receipts (idempotent deduplication ledger)
CREATE TABLE IF NOT EXISTS webhook_receipts (
    event_id TEXT PRIMARY KEY,
    idempotency_key TEXT UNIQUE NOT NULL,
    event_type TEXT NOT NULL,
    dispute_id TEXT,
    payload TEXT NOT NULL,
    received_at TEXT NOT NULL,
    FOREIGN KEY (dispute_id) REFERENCES disputes (dispute_id) ON DELETE SET NULL
);

-- 7. Audit events (tamper-evident SHA-256 backward hash chain)
CREATE TABLE IF NOT EXISTS audit_events (
    event_id TEXT PRIMARY KEY,
    parent_hash TEXT NOT NULL,
    event_hash TEXT NOT NULL,
    event_type TEXT NOT NULL,
    timestamp TEXT NOT NULL,
    dispute_id TEXT NOT NULL,
    actor TEXT NOT NULL,
    payload TEXT NOT NULL
);

-- 8. Schema migrations ledger for safe, versioned upgrades
CREATE TABLE IF NOT EXISTS schema_migrations (
    version INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    applied_at TEXT NOT NULL
);
"""

INDEXES_DDL = """
-- Indexes for high-performance querying and referential integrity
CREATE INDEX IF NOT EXISTS idx_source_records_dispute_id ON source_records(dispute_id);
CREATE INDEX IF NOT EXISTS idx_extracted_claims_dispute_id ON extracted_claims(dispute_id);
CREATE INDEX IF NOT EXISTS idx_policy_evaluations_dispute_id ON policy_evaluations(dispute_id);
CREATE INDEX IF NOT EXISTS idx_merchant_approvals_dispute_id ON merchant_approvals(dispute_id);
CREATE INDEX IF NOT EXISTS idx_merchant_approvals_nonce ON merchant_approvals(nonce);
CREATE UNIQUE INDEX IF NOT EXISTS idx_webhook_receipts_idempotency_key ON webhook_receipts(idempotency_key);
CREATE INDEX IF NOT EXISTS idx_webhook_receipts_dispute_id ON webhook_receipts(dispute_id);
CREATE INDEX IF NOT EXISTS idx_audit_events_dispute_id ON audit_events(dispute_id);
CREATE INDEX IF NOT EXISTS idx_audit_events_timestamp ON audit_events(timestamp);
CREATE INDEX IF NOT EXISTS idx_audit_events_event_hash ON audit_events(event_hash);
CREATE INDEX IF NOT EXISTS idx_disputes_category ON disputes(dispute_category);
CREATE INDEX IF NOT EXISTS idx_disputes_archived ON disputes(is_archived);
"""

SCHEMA_DDL = TABLES_DDL + "\n" + INDEXES_DDL


def _apply_migrations(conn: sqlite3.Connection) -> None:
    """Safely apply versioned, non-destructive schema migrations to the database."""
    cur = conn.cursor()
    try:
        cur.execute("CREATE TABLE IF NOT EXISTS schema_migrations (version INTEGER PRIMARY KEY, name TEXT NOT NULL, applied_at TEXT NOT NULL)")
        applied_versions = {row[0] for row in cur.execute("SELECT version FROM schema_migrations").fetchall()}

        now_iso = datetime.now(timezone.utc).isoformat()

        # Migration 1: Base Relational Schema
        if 1 not in applied_versions:
            cur.execute(
                "INSERT OR IGNORE INTO schema_migrations (version, name, applied_at) VALUES (?, ?, ?)",
                (1, "001_initial_relational_schema", now_iso),
            )

        # Migration 2: Soft Archival, Provenance Categorization, and 9-Parameter Approvals
        if 2 not in applied_versions:
            # Check disputes columns
            cur.execute("PRAGMA table_info(disputes)")
            disp_cols = {row[1] for row in cur.fetchall()}
            if "dispute_category" not in disp_cols:
                cur.execute("ALTER TABLE disputes ADD COLUMN dispute_category TEXT NOT NULL DEFAULT 'SYNTHETIC_BENCHMARK'")
            if "is_archived" not in disp_cols:
                cur.execute("ALTER TABLE disputes ADD COLUMN is_archived INTEGER NOT NULL DEFAULT 0")
            if "archived_at" not in disp_cols:
                cur.execute("ALTER TABLE disputes ADD COLUMN archived_at TEXT")
            if "archival_reason" not in disp_cols:
                cur.execute("ALTER TABLE disputes ADD COLUMN archival_reason TEXT")

            # Check merchant_approvals columns
            cur.execute("PRAGMA table_info(merchant_approvals)")
            appr_cols = {row[1] for row in cur.fetchall()}
            if "action" not in appr_cols:
                cur.execute("ALTER TABLE merchant_approvals ADD COLUMN action TEXT NOT NULL DEFAULT 'provide_evidence'")
            if "payload_hash" not in appr_cols:
                cur.execute("ALTER TABLE merchant_approvals ADD COLUMN payload_hash TEXT NOT NULL DEFAULT ''")
            if "evaluation_id" not in appr_cols:
                cur.execute("ALTER TABLE merchant_approvals ADD COLUMN evaluation_id TEXT")
            if "evidence_version" not in appr_cols:
                cur.execute("ALTER TABLE merchant_approvals ADD COLUMN evidence_version TEXT")
            if "nonce" not in appr_cols:
                cur.execute("ALTER TABLE merchant_approvals ADD COLUMN nonce TEXT")
            if "is_consumed" not in appr_cols:
                cur.execute("ALTER TABLE merchant_approvals ADD COLUMN is_consumed INTEGER NOT NULL DEFAULT 0")
            if "consumed_at" not in appr_cols:
                cur.execute("ALTER TABLE merchant_approvals ADD COLUMN consumed_at TEXT")
            if "consumed_by_dispatch_id" not in appr_cols:
                cur.execute("ALTER TABLE merchant_approvals ADD COLUMN consumed_by_dispatch_id TEXT")
            if "approval_token" not in appr_cols:
                cur.execute("ALTER TABLE merchant_approvals ADD COLUMN approval_token TEXT")

            cur.execute(
                "INSERT OR IGNORE INTO schema_migrations (version, name, applied_at) VALUES (?, ?, ?)",
                (2, "002_soft_archival_and_approvals", now_iso),
            )

        conn.commit()
    finally:
        cur.close()


def get_schema_version(conn: sqlite3.Connection) -> int:
    """Return the current maximum applied schema migration version."""
    cur = conn.cursor()
    try:
        row = cur.execute("SELECT MAX(version) FROM schema_migrations").fetchone()
        return row[0] if (row and row[0] is not None) else 0
    except sqlite3.OperationalError:
        return 0
    finally:
        cur.close()


def get_applied_migrations(conn: sqlite3.Connection) -> List[Dict[str, Any]]:
    """Return a list of applied schema migrations with their version, name, and timestamp."""
    cur = conn.cursor()
    try:
        rows = cur.execute("SELECT version, name, applied_at FROM schema_migrations ORDER BY version ASC").fetchall()
        return [{"version": r[0], "name": r[1], "applied_at": r[2]} for r in rows]
    except sqlite3.OperationalError:
        return []
    finally:
        cur.close()


def initialize_schema(conn: sqlite3.Connection) -> None:
    """Execute DDL statements and versioned migrations to ensure all required tables and indexes exist."""
    cur = conn.cursor()
    try:
        cur.executescript(TABLES_DDL)
        _apply_migrations(conn)
        cur.executescript(INDEXES_DDL)
    finally:
        cur.close()
