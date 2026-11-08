# Docket Database Architecture Review & SQLite Persistence Specification

**Document Identifier:** `DOCKET-ARCH-PERSISTENCE-01`  
**Date:** November 8, 2026  
**Status:** IMPLEMENTED & VERIFIED  
**Test Baseline:** 294 passing tests (`pytest` in 4.38s) | Frontend build green (`tsc -b && vite build` in 3.34s)  

---

## Executive Summary

Docket is a dispute operations engine engineered for high-consequence dispute defense, deterministic policy enforcement, semantic claim extraction, and merchant approval governance. 

Early architectural drafts evaluated relational databases as optional under the assumption of single-session evaluation benchmarks. This review reassesses that decision in the context of Docket as a production dispute operations product. 

Payment disputes (e.g., PayPal chargebacks, inquiries, pre-arbitrations) have lifecycles spanning **7 to 30 days**. Over that period, merchant approvals must not evaporate upon server restart, asynchronous webhook retries from payment processors must be deduplicated with ACID guarantees, and evidence reconciliation bundles must remain durable.

This document reports:
1. **An accurate inventory of pre-existing persistence** across disputes, evidence, AI claims, evaluations, approvals, and audit trails.
2. **An architectural evaluation** of persistence requirements, justifying a minimal, zero-dependency SQLite storage engine over premature cloud database infrastructure.
3. **The implemented SQLite schema design** featuring 7 relational tables, strict foreign keys, decimal-safe monetary representation, and atomic transactions.
4. **Preservation of the tamper-evident cryptographic audit ledger**, maintaining backward SHA-256 hash chaining across both append-only JSONL files and relational SQLite tables.
5. **Empirical test verification** proving complete backend restart survival, idempotency enforcement, and zero regressions across all 294 backend tests.

---

## Phase 1 — Pre-Existing Persistence Inventory

An exhaustive code inspection of Docket prior to this migration revealed the following persistence profile:

| State Artifact | Pre-Migration Storage Mechanism | Persistence Across Backend Restart | Relational Integrity / Constraints |
| :--- | :--- | :---: | :--- |
| **Dispute Records** | In-memory `cases_store: Dict[str, CaseData]` in `docket/api/app.py`, populated at startup from static JSON files (`real_sandbox_dispute_inr.json` and `benchmark_scenarios_20.json`). | **NO** (dynamic webhooks / changes lost) | None (in-memory Python dict) |
| **Source Records** (Orders, Shipments, Communications, Refunds) | In-memory inside `CaseData.bundle` (`ReconciledDisputeBundle`). | **NO** | None (in-memory objects) |
| **AI-Extracted Claims & Citations** | In-memory inside `CaseData.claims` (`List[ExtractedClaim]`). | **NO** | None |
| **Policy Evaluations** | In-memory inside `CaseData.evaluation` (`OverallPolicyEvaluation`). | **NO** | None |
| **Merchant Approvals** | In-memory inside `CaseData.approval_record` (`MerchantApprovalRecord`). Nonce check in `ApprovalService._consumed_nonces` was an in-memory `set`. | **NO** | None |
| **Audit Events & Hash Chain** | Persisted to append-only JSONL file `artifacts/audit_trail.jsonl` by `AuditLogger`. | **YES** | Cryptographic hash-chain interior verification |
| **Webhook Receipts** | Only recorded as `DISPUTE_INGESTED` lines in `artifacts/audit_trail.jsonl`. | Partially (log only) | Linear JSONL scan, no database UNIQUE constraint |

### Critical Pre-Migration Gaps Identified
1. **Volatile Operational State:** While the audit trail was written to JSONL, the actual operational dispute state—including merchant approvals, policy evaluations, and evidence reconciliation bundles—resided exclusively in Python process memory. A process reboot or container recycling returned the server to its initial static fixtures, erasing any dynamically ingested disputes or affirmative merchant authorizations.
2. **Missing Relational Foreign Keys:** No mechanism enforced referential integrity between disputes and their supporting carrier records, order invoices, or extracted claims.
3. **Webhook Idempotency Vulnerability:** Webhook deduplication depended on scanning in-memory lists loaded from JSONL. Simultaneous concurrent deliveries or process restarts created potential race conditions without database-level unique constraints.

---

## Phase 2 — Architecture Recommendation

### Reassessing the "Database is Optional" Decision

The earlier assessment that a database is optional was valid *only* for stateless, offline benchmark scoring (e.g., evaluating 20 synthetic scenarios in a single test run). For an active dispute operations system, persistent relational storage is mandatory for the following reasons:

1. **Multi-Day Dispute Lifecycles:** PayPal disputes proceed through `INQUIRY` -> `CHARGEBACK` -> `PRE_ARBITRATION`. Merchant evidence submission windows typically allow 10 to 14 days. Operational state must survive maintenance windows, blue/green deployments, and process restarts.
2. **Merchant Approval Non-Repudiation:** Human authorizations granting approval to dispatch evidence to PayPal are legally and operationally significant. Storing approval records solely in memory risks dispatching evidence without verifiable durable records.
3. **Webhook Retry Windows:** Payment processors resend webhooks with exponential backoff over hours or days. Idempotent deduplication requires atomic, database-enforced unique constraints (`idempotency_key UNIQUE`).
4. **Auditability & Foreign Key Consistency:** Evidence citations must strictly reference valid source records; child claims must cascade-delete when a dispute is expunged.

### Persistence Engine Selection: Why SQLite is Optimal

We evaluated potential storage engines:

| Criteria | SQLite (Standard Library) | PostgreSQL / Supabase | MongoDB / Document DB | Redis |
| :--- | :---: | :---: | :---: | :---: |
| **Operational Dependencies** | **0 (Built into Python `sqlite3`)** | Requires external daemon/cloud service | Requires external daemon | Memory-first; cache only |
| **ACID Transactions** | **Full (`BEGIN IMMEDIATE`)** | Full | Partial / multi-doc overhead | No relational ACID |
| **Foreign Key Enforcement** | **Yes (`PRAGMA foreign_keys = ON`)** | Yes | No | No |
| **WAL Concurrency** | **Yes (`PRAGMA journal_mode = WAL`)** | MVCC | Document locking | Single-threaded |
| **Decimal Precision** | **Exact (`TEXT` storage)** | Exact (`NUMERIC`) | Double-precision float risk | String |
| **Zero-Config Portability** | **Single file (`artifacts/docket.db`)** | Connection strings, migrations, network | Connection strings, clustering | Memory persistence tuning |
| **Benchmark Isolation** | **Trivial (in-memory or `tmp_path`)** | Requires database spin-up/teardown | Requires test instance | Requires test flush |

**Recommendation:**  
SQLite is the optimal, production-grade persistence engine for Docket at this stage. It introduces **zero new infrastructure dependencies**, requires no external services, executes ACID transactions with Write-Ahead Logging (WAL), enforces relational foreign keys, and operates identically across Windows, macOS, Linux, and CI environments.

Cloud databases (PostgreSQL, Supabase) and caches (Redis) are intentionally avoided at this stage to prevent premature operational complexity.

---

## Phase 3 — Minimal SQLite Schema Design & Implementation

The relational layer is implemented in `docket/database/` using standard library `sqlite3`:
- `docket/database/schema.py`: Schema DDL, table declarations, and index creation.
- `docket/database/connection.py`: Thread-safe connection management, WAL mode, foreign keys, and explicit atomic transaction context managers.
- `docket/database/repository.py`: Strongly-typed CRUD repository, Pydantic model serialization/deserialization, and restart hydration.

### Complete Relational Schema (7 Tables, 9 Indexes)

```sql
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

-- Performance and referential indexes
CREATE INDEX IF NOT EXISTS idx_source_records_dispute_id ON source_records(dispute_id);
CREATE INDEX IF NOT EXISTS idx_extracted_claims_dispute_id ON extracted_claims(dispute_id);
CREATE INDEX IF NOT EXISTS idx_policy_evaluations_dispute_id ON policy_evaluations(dispute_id);
CREATE INDEX IF NOT EXISTS idx_merchant_approvals_dispute_id ON merchant_approvals(dispute_id);
CREATE UNIQUE INDEX IF NOT EXISTS idx_webhook_receipts_idempotency_key ON webhook_receipts(idempotency_key);
CREATE INDEX IF NOT EXISTS idx_webhook_receipts_dispute_id ON webhook_receipts(dispute_id);
CREATE INDEX IF NOT EXISTS idx_audit_events_dispute_id ON audit_events(dispute_id);
CREATE INDEX IF NOT EXISTS idx_audit_events_timestamp ON audit_events(timestamp);
CREATE INDEX IF NOT EXISTS idx_audit_events_event_hash ON audit_events(event_hash);
```

### Key Engineering Guarantees
1. **Decimal-Safe Monetary Values:** Monetary quantities are stored as `TEXT` (e.g., `"25.00"`, `"1234567.89"`) and serialized to/from Python `Decimal`. This prevents IEEE 754 binary floating-point roundoff issues (e.g., `0.1 + 0.2 != 0.3`).
2. **Explicit Atomic Transactions:** The database uses `isolation_level=None` with an explicit `BEGIN IMMEDIATE` context manager:
   ```python
   @contextmanager
   def transaction(self):
       with self._lock:
           cur = self._conn.cursor()
           try:
               cur.execute("BEGIN IMMEDIATE")
               yield cur
               cur.execute("COMMIT")
           except Exception:
               cur.execute("ROLLBACK")
               raise
           finally:
               cur.close()
   ```
3. **Enforced Foreign Keys & Cascading Deletes:** `PRAGMA foreign_keys = ON;` is executed on every connection. Deleting a dispute automatically cascades to all its source records, claims, evaluations, and approvals.
4. **Write-Ahead Logging (WAL) Mode:** `PRAGMA journal_mode = WAL;` and `PRAGMA synchronous = NORMAL;` allow concurrent readers without locking writers.

---

## Phase 4 — Cryptographic Audit Ledger Preservation

The cryptographic audit ledger implementation in `docket/audit/logger.py` is fully preserved with dual-layer durability:

1. **JSONL File Storage (`artifacts/audit_trail.jsonl`):** Retained as an append-only flat file for fast stream consumption, command-line inspection, and backward compatibility.
2. **Relational Table Storage (`audit_events`):** Every audit event logged is mirrored into the SQLite `audit_events` table within an atomic transaction.
3. **SHA-256 Backward Hash Chaining:**
   - Genesis event: `parent_hash = "GENESIS"`.
   - Subsequent events: `parent_hash = prev_event.event_hash`.
   - Fingerprint formula:
     $$\text{SHA-256}(\text{parent\_hash} \parallel \text{event\_id} \parallel \text{event\_type} \parallel \text{timestamp} \parallel \text{dispute\_id} \parallel \text{actor} \parallel \text{canonical\_payload})$$
4. **Cryptographic Verification & Tamper Detection:**
   - Both `audit_logger.verify_chain_detailed()` (JSONL) and `repository.verify_db_audit_chain()` (SQLite) verify mathematical chain continuity from genesis to head.
   - Any modification of payload text, timestamps, actor IDs, or parent hashes breaks the chain and triggers immediate mathematical failure.
5. **Accurate Terminology Maintained:**
   - Docket’s audit trail is accurately documented as a **tamper-evident hash chain with interior integrity verification**, not an immutable external consensus ledger.
   - It reliably detects interior payload alteration, link modification, event reordering, and interior event deletion.
   - Tail truncation (deletion of final events) cannot be detected purely from the chain without an external head-hash checkpoint.

---

## Phase 5 — Functional Preservation & Offline Determinism

1. **20 Benchmark Scenarios:** All 20 synthetic offline benchmark scenarios in `docs/fixtures/benchmark_scenarios_20.json` continue to run completely offline without requiring network calls or cloud services.
2. **Graceful Seeding & Hydration:**
   - On backend startup (`create_app`), `DocketRepository.load_persisted_cases()` inspects SQLite.
   - If SQLite already contains cases (e.g., following a restart), cases are hydrated directly from the database with their latest approval records and dispatch results.
   - If SQLite is empty, `load_initial_cases()` seeds the database with the real sandbox case and benchmark scenarios.
3. **Backward-Compatible Interfaces:**
   - `create_app()` accepts optional `audit_log_path`, `secret_key`, and `db_path`. In automated tests passing temporary audit paths, `db_path` is automatically isolated in `tmp_path`.
   - `AuditLogger` accepts an optional `repository` reference while continuing to operate standalone if omitted.

---

## Phase 6 — Verification Evidence

A comprehensive verification test suite (`tests/test_sqlite_persistence.py`) was created and executed alongside the full regression suite.

### 1. SQLite Persistence Suite (`tests/test_sqlite_persistence.py`)

| Test Name | Verification Focus | Result |
| :--- | :--- | :---: |
| `test_schema_initialization_and_pragmas` | Verifies 7 tables exist, `foreign_keys=ON`, `journal_mode=WAL` | **PASS** |
| `test_dispute_crud_and_decimal_safety` | Verifies exact string decimal storage (`"1234567.89"`), no float rounding | **PASS** |
| `test_source_records_and_cascade_deletion` | Verifies source record insertion, foreign key integrity, and CASCADE deletion | **PASS** |
| `test_claims_with_epistemic_metadata` | Verifies `ClaimEpistemicMetadata` and `SourceCitation` round-trip | **PASS** |
| `test_evaluations_and_approvals_persistence` | Verifies `OverallPolicyEvaluation` invariants and `MerchantApprovalRecord` | **PASS** |
| `test_webhook_idempotency_constraint` | Verifies duplicate `idempotency_key` triggers SQLite UNIQUE constraint | **PASS** |
| `test_backend_restart_simulation` | Closes DB connection, reopens fresh instance, verifies full case survival | **PASS** |
| `test_audit_hash_chain_in_database_and_tamper_detection` | Verifies SQLite audit hash chain and mathematical tamper detection upon mutation | **PASS** |
| `test_fastapi_server_restart_with_webhook_and_approval` | Full HTTP cycle: Webhook ingest -> Authorize -> Reboot -> Verify state in API | **PASS** |

### 2. Full Regression Suite Execution

```
============================= test session starts =============================
platform win32 -- Python 3.14.8, pytest-8.4.2, pluggy-1.6.0
rootdir: C:\Users\ACER\Downloads\Docket
configfile: pytest.ini
testpaths: tests
plugins: anyio-4.14.2, platformdirs-4.13.3
collected 294 items

tests\test_ai_extractor.py ................................              [ 10%]
tests\test_ai_live_workflow.py ...........                               [ 14%]
tests\test_api_endpoints.py ............                                 [ 18%]
tests\test_dispatch_and_audit.py ..........................              [ 27%]
tests\test_eval_suite.py ............                                    [ 31%]
tests\test_milestone4_audit.py ......................................... [ 45%]
                                                                         [ 45%]
tests\test_paypal_dispute.py ........................................... [ 60%]
........                                                                 [ 62%]
tests\test_policy_engine.py ............................................ [ 77%]
.............................                                            [ 87%]
tests\test_reconciliation.py ...........................                 [ 96%]
tests\test_sqlite_persistence.py .........                               [100%]

============================= 294 passed in 4.38s =============================
```

### 3. Frontend Production Build Verification

```
> frontend@0.0.0 build
> tsc -b && vite build

vite v8.3.5 building client environment for production...
transforming...
✓ 2059 modules transformed.
rendering chunks...
computing gzip size...
dist/index.html                     0.45 kB │ gzip:   0.29 kB
dist/assets/index-DohP2Fai.css     22.89 kB │ gzip:   4.51 kB
dist/assets/index-CKlXoZ97.js   1,491.41 kB │ gzip: 413.82 kB
✓ built in 3.34s
```

---

## File Change Summary

| Component | Path | Description |
| :--- | :--- | :--- |
| **Schema DDL** | `docket/database/schema.py` | 7 tables, 9 indexes, foreign keys, cascades, decimal text money fields. |
| **Connection Manager** | `docket/database/connection.py` | Thread-safe connection management, WAL mode, pragmas, atomic transactions. |
| **Repository Layer** | `docket/database/repository.py` | Typed domain CRUD, Pydantic mapping, webhook idempotency, restart hydration. |
| **Package Exports** | `docket/database/__init__.py` | Module exports for `DatabaseConnection`, `DocketRepository`, `SCHEMA_DDL`. |
| **Audit Logger** | `docket/audit/logger.py` | Dual-write persistence to JSONL and SQLite `audit_events` table. |
| **FastAPI Backend** | `docket/api/app.py` | SQLite hydration on boot, durable webhook ingestion, durable approvals. |
| **Test Suite** | `tests/test_sqlite_persistence.py` | 9 new comprehensive tests verifying schema, CRUD, restarts, and tampering. |
| **Architecture Review** | `docs/DOCKET_DATABASE_ARCHITECTURE_REVIEW.md` | Complete architectural evaluation and verification evidence report. |

---

## Conclusion

The evaluation definitively establishes that Docket requires relational persistence for operational dispute defense. By implementing a minimal, zero-dependency SQLite architecture, Docket achieves:
- **Durable backend restart survival** for dispute cases, evidence bundles, policy evaluations, and merchant approvals.
- **ACID-guaranteed webhook deduplication** via database-enforced unique constraints.
- **Referential integrity** through foreign keys and cascading deletes.
- **Decimal-safe financial precision** with zero float rounding errors.
- **Cryptographic audit continuity** spanning both append-only JSONL files and relational tables.
- **100% backward compatibility**, passing all 294 backend tests and the React frontend build.

