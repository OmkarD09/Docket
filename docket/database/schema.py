"""SQLite Database Schema Definitions and Migrations for Docket.

Provides DDL and schema management for:
1. disputes: Core dispute cases with decimal-safe amounts and lifecycle tracking.
2. source_records: Linked evidence records (orders, shipments, communications, refunds).
3. extracted_claims: Semantically extracted and policy-checked factual claims.
4. policy_evaluations: Deterministic invariant evaluations and advisory outcomes.
5. merchant_approvals: Tamper-evident affirmative merchant approval records.
6. webhook_receipts: Ingested webhook events with atomic idempotency constraints.
7. audit_events: Cryptographically chained backward hash-chain audit ledger entries.
"""

from __future__ import annotations

import sqlite3
from typing import List


SCHEMA_DDL = """
-- 1. Disputes table
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
    citations TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY (dispute_id) REFERENCES disputes (dispute_id) ON DELETE CASCADE
);

-- 4. Policy evaluations with invariant results & advisories
CREATE TABLE IF NOT EXISTS policy_evaluations (
    evaluation_id TEXT PRIMARY KEY,
    dispute_id TEXT NOT NULL,
    overall_decision TEXT NOT NULL,
    factual_readiness TEXT NOT NULL,
    action_readiness TEXT NOT NULL,
    check_results TEXT NOT NULL,
    advisories TEXT NOT NULL,
    summary TEXT NOT NULL,
    evaluated_at TEXT NOT NULL,
    FOREIGN KEY (dispute_id) REFERENCES disputes (dispute_id) ON DELETE CASCADE
);

-- 5. Merchant approval records
CREATE TABLE IF NOT EXISTS merchant_approvals (
    approval_id TEXT PRIMARY KEY,
    dispute_id TEXT NOT NULL,
    merchant_user_id TEXT NOT NULL,
    decision TEXT NOT NULL,
    rejection_reason TEXT,
    approved_at TEXT NOT NULL,
    approval_token TEXT NOT NULL,
    client_ip TEXT,
    user_agent TEXT,
    FOREIGN KEY (dispute_id) REFERENCES disputes (dispute_id) ON DELETE CASCADE
);

-- 6. Webhook receipts with unique idempotency constraint
CREATE TABLE IF NOT EXISTS webhook_receipts (
    event_id TEXT PRIMARY KEY,
    dispute_id TEXT,
    event_type TEXT NOT NULL,
    idempotency_key TEXT UNIQUE NOT NULL,
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

-- Indexes for high-performance querying and referential integrity
CREATE INDEX IF NOT EXISTS idx_source_records_dispute_id ON source_records(dispute_id);
CREATE INDEX IF NOT EXISTS idx_extracted_claims_dispute_id ON extracted_claims(dispute_id);
CREATE INDEX IF NOT EXISTS idx_policy_evaluations_dispute_id ON policy_evaluations(dispute_id);
CREATE INDEX IF NOT EXISTS idx_merchant_approvals_dispute_id ON merchant_approvals(dispute_id);
CREATE UNIQUE INDEX IF NOT EXISTS idx_webhook_receipts_idempotency_key ON webhook_receipts(idempotency_key);
CREATE INDEX IF NOT EXISTS idx_webhook_receipts_dispute_id ON webhook_receipts(dispute_id);
CREATE INDEX IF NOT EXISTS idx_audit_events_dispute_id ON audit_events(dispute_id);
CREATE INDEX IF NOT EXISTS idx_audit_events_timestamp ON audit_events(timestamp);
CREATE INDEX IF NOT EXISTS idx_audit_events_event_hash ON audit_events(event_hash);
"""


def initialize_schema(conn: sqlite3.Connection) -> None:
    """Execute DDL statements to ensure all required tables and indexes exist."""
    cur = conn.cursor()
    try:
        # SQLite executes multiple statements via executescript
        cur.executescript(SCHEMA_DDL)
    finally:
        cur.close()

