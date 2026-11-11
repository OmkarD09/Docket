# Docket — SQLite Persistence Hardening & Database Integrity Verification

**Date:** 2026-11-08  
**Environment:** Python 3.14.8 / SQLite 3.49+ (WAL mode) / FastAPI / React 19 + TypeScript  
**Status:** PASSED (301 backend tests green, frontend production build verified)

---

## Executive Summary

Following the initial SQLite persistence integration, this audit and hardening cycle conducted a comprehensive integrity review of Docket's persistent storage layer. 

The audit established:
1. **Single Canonical Authority:** SQLite (`artifacts/docket.db`) is the sole canonical source of truth for all dispute records, evidence packages, evaluations, approvals, and cryptographic audit chains. Filesystem JSONL exports (`artifacts/audit_trail.jsonl`) are strictly derived, recoverable artifacts with zero authority to invalidate or mutate the database ledger.
2. **Approval & Audit Deletion Protection:** Foreign key cascades on `merchant_approvals` were hardened from cascade deletion to `ON DELETE RESTRICT`. A formal soft-archival mechanism (`archive_dispute`) was implemented, guaranteeing that approvals and audit trails remain permanently queryable.
3. **Cryptographically Bound Single-Use Approvals:** Affirmative human merchant approvals are bound across 9 immutable parameters (dispute ID, action, payload hash, evidence version, evaluation ID, merchant ID, timestamp, and unique single-use nonce). Consumption state (`is_consumed`, `consumed_at`, `consumed_by_dispatch_id`) is persisted directly in SQLite, surviving server restarts and preventing token replay attacks.
4. **Deterministic Canonical Hash-Chain Serialization:** Standardized on strict UTF-8 byte streams, ISO-8601 UTC timestamps, and RFC 8785 canonical JSON sorting (`sort_keys=True, separators=(',', ':')`).
5. **Count Discrepancy Reconciliation:** Resolved the ambiguity between `total_cases_loaded: 40` (dual-alias in-memory routing table) and `total_disputes: 20` (unique physical SQLite rows), adding explicit provenance categorization (`REAL_SANDBOX`, `SYNTHETIC_BENCHMARK`, `LIVE_WEBHOOK`).
6. **Operational Safety & WAL Online Backup:** Untracked database and WAL files from git, verified credential redaction, verified `PRAGMA foreign_keys = ON` and `PRAGMA journal_mode = WAL`, and implemented native SQLite online streaming backups (`conn.backup()`) with automated restoration verification.

---

## 1. Dual Persistence Consistency & Canonical Truth

### 1.1 Architectural Reality: Filesystem vs ACID Transactions

In POSIX and Windows NT filesystems, standard file writes (`open(..., 'a')`) and SQLite relational transactions (`sqlite3.Connection.commit()`) **cannot participate in a single atomic ACID two-phase commit (2PC)** without external distributed transaction coordinators.

Attempting to claim cross-system atomicity between a flat `.jsonl` file and an SQLite database is fragile and architecturally unevidenced. If an unhandled process crash, kernel panic, or power outage occurs between writing to SQLite and appending to JSONL, one medium will lead while the other lags.

### 1.2 Canonical Authority Resolution

To resolve this without introducing heavyweight distributed infrastructure:
- **SQLite is the Canonical Source of Truth:** The `audit_events` table in `artifacts/docket.db` is the authoritative audit ledger. All query endpoints, verification checks, and dispatch preconditions read directly from SQLite.
- **JSONL is a Derived, Recoverable Export:** The `artifacts/audit_trail.jsonl` file is a portable streaming export intended for ingestion into SIEM tools, cold storage, or log collectors.
- **Fail-Safe Decoupling:**
  1. Audit events are committed to SQLite first inside an explicit transaction.
  2. The derived JSONL append is attempted immediately.
  3. If the JSONL append fails (e.g., read-only filesystem, file locked by an external reader, disk full), the logger **does not roll back the canonical SQLite transaction**. Instead, it marks an internal dirty flag (`_export_dirty = True`).
  4. Idempotent export reconciliation (`reconcile_jsonl_export`) can be invoked at any time to stream missing records from SQLite to JSONL without altering SQLite event hashes or re-ordering records.
  5. If the JSONL file is truncated or corrupted, the system can reconstruct the JSONL file from the canonical SQLite database at any time.

### 1.3 Failure-Injection Verification

A dedicated failure-injection test in `tests/test_database_integrity.py::test_canonical_sqlite_and_recoverable_jsonl_export`:
- Simulates an unhandled filesystem failure during the JSONL append step.
- Verifies that the canonical event is fully committed and valid in SQLite.
- Confirms the SQLite backward hash chain remains intact (`verify_db_audit_chain() == True`).
- Verifies that subsequent writes detect the dirty export state and trigger `reconcile_jsonl_export()`.
- Validates line-by-line parity between SQLite and JSONL once filesystem permissions are restored.

---

## 2. Approval and Audit Retention

### 2.1 Deletion Cascade Inspection

An inspection of the relational foreign key constraints revealed:
- `source_records`, `extracted_claims`, and `policy_evaluations` had `ON DELETE CASCADE` referencing `disputes(dispute_id)`.
- Previously, `merchant_approvals` also referenced `disputes` with potential cascade deletion.

**Hardening Measure:**  
In `docket/database/schema.py`, the foreign key constraint on `merchant_approvals` was explicitly updated to:
```sql
FOREIGN KEY (dispute_id) REFERENCES disputes (dispute_id) ON DELETE RESTRICT
```
With `PRAGMA foreign_keys = ON;` enforced on every SQLite connection, any SQL statement attempting `DELETE FROM disputes WHERE dispute_id = ...` will immediately abort with:
```
sqlite3.IntegrityError: FOREIGN KEY constraint failed
```
whenever an affirmative or negative approval record exists for that dispute. Ordinary dispute purges cannot inadvertently delete merchant approvals.

### 2.2 Soft Archival Implementation

Because dispute cases should occasionally be retired from active operational queues without deleting historical governance records, Docket implemented a soft-archival mechanism:
- **Schema Columns:** Added `is_archived INTEGER NOT NULL DEFAULT 0`, `archived_at TEXT`, `archival_reason TEXT`, and `dispute_category TEXT` to `disputes`, with an index on `idx_disputes_archived`.
- **Repository Methods:** `archive_dispute(dispute_id, reason)` marks the dispute as archived without deleting any associated child records.
- **Filtered Queries:** `list_disputes(include_archived=False)` excludes archived disputes from active triage queues by default, but allows audit tools to retrieve them by passing `include_archived=True`.
- **API Endpoint:** Added `POST /api/disputes/{dispute_id}/archive`.

Verified in `tests/test_database_integrity.py::test_approval_retention_blocks_cascade_and_permits_archival`.

---

## 3. Approval Integrity & Anti-Replay Matrix

### 3.1 9-Parameter Binding Specification

Affirmative merchant approvals must not be generic or transferable across disputes or modified evidence sets. `ApprovalService` binds the following 9 parameters upon approval creation:

| Parameter | Type | Binding Purpose |
|:---|:---|:---|
| `dispute_id` | `str` | Binds the approval to the exact target dispute. |
| `action` | `str` | Restricts the authorized PayPal action (e.g., `provide_evidence`, `accept_claim`). |
| `payload_hash` | `str` | SHA-256 digest of the exact evidence package payload submitted. |
| `evidence_version` | `str` | Identifier/version of the evidence set evaluated. |
| `evaluation_id` | `str` | References the deterministic PolicyEngine evaluation justifying the action. |
| `merchant_id` | `str` | Identifies the authenticated human decision maker granting approval. |
| `approved_at` | `str` | ISO-8601 UTC timestamp of affirmative approval. |
| `nonce` | `str` | Cryptographically random, single-use token (`uuid4().hex`). |
| `token` | `str` | Merchant token presented at dispatch time. |

### 3.2 Transactional Single-Use Nonce Tracking in SQLite

Previously, single-use nonce tracking was managed via an in-memory set in Python. If the backend restarted between merchant approval and API dispatch, in-memory state would reset, and nonces could theoretically be replayed if tokens were intercepted.

**Hardening Measure:**
The `merchant_approvals` table now persists the consumption lifecycle directly in SQLite:
- `nonce TEXT UNIQUE` (indexed)
- `is_consumed INTEGER NOT NULL DEFAULT 0`
- `consumed_at TEXT`
- `consumed_by_dispatch_id TEXT`

When `verify_token` is called during dispatch:
1. It verifies signature/match against the active approval request.
2. It executes an atomic transactional check and update:
   ```sql
   UPDATE merchant_approvals
   SET is_consumed = 1, consumed_at = ?, consumed_by_dispatch_id = ?
   WHERE nonce = ? AND is_consumed = 0
   ```
3. If zero rows are updated (either nonce unknown or `is_consumed == 1`), `verify_token` rejects the dispatch with `TokenAlreadyUsedError`.

### 3.3 Test Matrix Coverage

Verified in `tests/test_database_integrity.py`:
- `test_approval_integrity_and_anti_replay_matrix`:
  - Token replay attempt rejected with `TokenAlreadyUsedError`.
  - Modified payload hash rejected with `PayloadMismatchError`.
  - Wrong dispute ID rejected with `DisputeMismatchError`.
  - Wrong action rejected with `ActionMismatchError`.
  - Reused nonce rejected at DB layer with unique constraint.
- `test_approval_survives_backend_restart_before_single_use_dispatch`:
  - Approval granted in process session 1.
  - Process closes and memory state clears.
  - New process session hydrates consumed nonces and approvals from SQLite.
  - First dispatch succeeds and consumes the approval in SQLite.
  - Second dispatch attempt in the same or subsequent session is rejected with `TokenAlreadyUsedError`.

### 3.4 Cryptographic Disclaimer: Durable Record vs Non-Repudiation

> [!IMPORTANT]
> Docket's merchant approval mechanism provides **durable, tamper-evident, authenticated audit records** bound to internal user IDs and session contexts.  
> It does **not** provide legal cryptographic non-repudiation because it does not utilize asymmetric private key hardware tokens (e.g., FIDO2 / WebAuthn hardware-signed assertions or merchant-held RSA/ECDSA private keys). Claims of cryptographic non-repudiation are strictly avoided in documentation and system status reports.

---

## 4. Hash-Chain Implementation & Canonical Serialization

### 4.1 Deterministic Fingerprint Serialization

Audit trail verification relies on exact, byte-reproducible SHA-256 backward hash chaining. 

To eliminate serialization divergence across platforms:
- **Encoding:** Explicit `utf-8` on all hash operations (`.encode("utf-8")`).
- **Timestamp Standard:** Strict ISO-8601 UTC string format generated from timezone-aware UTC datetime (`datetime.now(timezone.utc).isoformat()`).
- **Canonical Payload JSON:** Sorted keys with compact delimiters:
  ```python
  canonical_payload = json.dumps(payload, sort_keys=True, separators=(",", ":"))
  ```
- **Fingerprint Formula:**
  ```
  fingerprint = f"{parent_hash}:{event_id}:{event_type}:{timestamp_iso}:{dispute_id}:{actor}:{canonical_payload}"
  event_hash = sha256(fingerprint.encode("utf-8")).hexdigest()
  ```
- **Genesis Block:** The initial event in an audit ledger anchors `parent_hash = "GENESIS"`. Each subsequent event binds its `parent_hash` to the exact `event_hash` of its predecessor.

### 4.2 Tamper Detection Capabilities

The SQLite audit ledger integrity was verified for:
1. **Payload Tampering:** Modifying any byte within the JSON payload in SQLite invalidates the recomputed SHA-256 hash immediately.
2. **Interior Record Deletion:** Deleting an interior event (e.g., event 2 in a 3-event sequence) creates an immediate break: event 3's `parent_hash` references event 2's `event_hash`, which no longer exists, failing chain verification.
3. **Out-of-Order Insertion:** Reordering events violates the backward pointer sequence.

### 4.3 Documented Limitation: Trailing Head Truncation

> [!NOTE]
> As established during the Milestone 4 audit, a standard backward hash chain independently detects interior deletions and payload modifications, but **cannot detect the deletion of trailing head events** (the most recent $N$ events) without an independent external commitment.  
> If an attacker truncates the last event in an SQLite table, the remaining prefix remains internally mathematically consistent. Docket accurately documents this physical property of hash chains. Head-hash checkpoints may be periodically committed to external immutable ledgers or signed logs when operating in multi-tenant cloud environments.

---

## 5. Database Count Reconciliation & Provenance

### 5.1 Reconciliation of the 40 vs 20 Discrepancy

During earlier reviews, the system reported `total_cases_loaded: 40` while SQLite reported `total_disputes: 20`.

**Root Cause:**  
In `docket/api/app.py`, the in-memory `cases_store` dictionary was populated during startup by indexing each benchmark dispute under two distinct keys:
1. Its PayPal dispute ID (e.g. `PP-R-285901`)
2. Its benchmark scenario ID (e.g. `SCEN-01-INR-UNVERIF-2026`)

This design allowed web client routes to look up cases using either URL convention without path translation. However, reporting `len(cases_store)` as the total count created the misleading impression of 40 distinct dispute cases when there were only 20 physical dispute cases.

### 5.2 Provenance Categorization

To permanently eliminate this ambiguity, dispute records now include an explicit `dispute_category` column:
- `REAL_SANDBOX`: Disputes ingested directly from live PayPal Sandbox API calls.
- `SYNTHETIC_BENCHMARK`: Offline benchmark scenarios from `tests/fixtures/disputes_benchmark_20.json`.
- `LIVE_WEBHOOK`: Real-time disputes ingested via PayPal webhook listeners.

### 5.3 Health Endpoint Reconciliation

The `/api/health` endpoint was refactored to report unambiguous count semantics:
```json
{
  "status": "ok",
  "version": "1.0.0",
  "timestamp": "2026-11-08T15:54:53.508175+00:00",
  "total_cases_loaded": 20,
  "case_counts": {
    "total_unique_cases": 20,
    "alias_lookup_keys": 40,
    "real_sandbox_disputes": 0,
    "synthetic_benchmark_scenarios": 20,
    "live_webhook_disputes": 0,
    "archived_disputes": 0
  },
  "database": {
    "type": "sqlite",
    "path": "artifacts/docket.db",
    "total_disputes": 20,
    "active_disputes": 20,
    "archived_disputes": 0,
    "breakdown": {
      "real_sandbox": 0,
      "synthetic_benchmark": 20,
      "live_webhook": 0
    }
  }
}
```
All counts are now reconciled and mathematically consistent across memory caches and SQLite tables.

---

## 6. Operational Safety & Online SQLite WAL Backup

### 6.1 Version Control & Secret Redaction
- **Git Ignore:** Added `*.db`, `*.db-wal`, `*.db-shm`, and `artifacts/*.db*` to `.gitignore`. Executed `git rm --cached artifacts/docket.db` to remove any previously tracked binary database files from git index.
- **Sensitive Data Exclusion:** Database tables and audit event payloads exclude OAuth bearer tokens, PayPal client secrets, and sensitive payment instrument details (e.g. full credit card PANs). Payloads contain only business dispute metadata and public tracking numbers.

### 6.2 Connection Configuration & Concurrency
- `PRAGMA foreign_keys = ON;` is executed on every SQLite connection initialization.
- `PRAGMA journal_mode = WAL;` enables Write-Ahead Logging, allowing concurrent readers without blocking writes and concurrent reads while a write transaction commits.
- `PRAGMA busy_timeout = 5000;` prevents `sqlite3.OperationalError: database is locked` during brief concurrent write bursts.

### 6.3 Online Streaming Backup Verification

Because file-level copying (`shutil.copy` or `cp`) of active SQLite databases in WAL mode can capture torn pages or inconsistent states between `.db` and `.db-wal`, Docket implemented an online streaming backup mechanism in `DatabaseConnection`:
```python
def backup(self, target_path: Union[str, Path]) -> Path:
    """Safely stream an online atomic backup using the SQLite backup API."""
    target_path = Path(target_path)
    target_path.parent.mkdir(parents=True, exist_ok=True)
    dst_conn = sqlite3.connect(str(target_path))
    try:
        self._conn.backup(dst_conn, pages=100)
    finally:
        dst_conn.close()
    return target_path
```

**Verification:**  
In `tests/test_database_integrity.py::test_sqlite_wal_online_backup_and_restoration`:
- Populates live disputes and audit events into an active WAL-mode database.
- Executes `src_conn.backup(backup_db)` while read and write operations are live.
- Opens the backup file with an independent `DatabaseConnection`.
- Asserts that all dispute records, audit events, and the cryptographic hash chain verify cleanly in the restored database.

---

## 7. Verification Results & Regression Matrix

### 7.1 Backend Test Suite (301 Tests Green)

Executing `python -m pytest`:
```
============================= test session starts =============================
platform win32 -- Python 3.14.8, pytest-8.4.2, pluggy-1.6.0
rootdir: C:\Users\ACER\Downloads\Docket
configfile: pytest.ini
collected 301 items

tests\test_ai_extractor.py ................................              [ 10%]
tests\test_ai_live_workflow.py ...........                               [ 14%]
tests\test_api_endpoints.py ............                                 [ 18%]
tests\test_database_integrity.py .......                                 [ 20%]
tests\test_dispatch_and_audit.py ..........................              [ 29%]
tests\test_eval_suite.py ............                                    [ 33%]
tests\test_milestone4_audit.py ......................................... [ 46%]
tests\test_paypal_dispute.py ........................................... [ 61%]
........                                                                 [ 63%]
tests\test_policy_engine.py ............................................ [ 78%]
.............................                                            [ 88%]
tests\test_reconciliation.py ...........................                 [ 97%]
tests\test_sqlite_persistence.py .........                               [100%]

============================= 301 passed in 4.49s =============================
```

### 7.2 Frontend Production Build

Executing `npm --prefix frontend run build`:
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
✓ built in 4.41s
```

---

## 8. Summary Table of Architecture Commitments

| Component | Architecture Before Hardening | Hardened State |
|:---|:---|:---|
| **Audit Ledger Authority** | Dual authoritative ambiguity (SQLite + JSONL) | SQLite is sole canonical authority; JSONL is derived recoverable export |
| **Export Failure Recovery** | Unhandled JSONL write errors could desync | Dirty export flag with automatic idempotent reconciliation |
| **Approval Deletion** | Potential cascade deletion with dispute | `ON DELETE RESTRICT` enforces retention; soft-archival implemented |
| **Approval Consumption** | In-memory Python `set()` (reset on restart) | SQLite-persisted `is_consumed`, `consumed_at`, `consumed_by_dispatch_id` |
| **Replay Protection** | Intercepted token could be reused after restart | Single-use nonce tracked transactionally in SQLite; replay rejected |
| **Dispute Counts** | 40 reported (2x multiplier from alias keys) | Reconciled: 20 unique disputes, 40 alias lookup keys, categorized provenance |
| **Database Backups** | Raw file copies (risk of torn pages in WAL mode) | Online streaming backup via native `sqlite3` backup API |
| **Git Tracking** | `artifacts/docket.db` was tracked in git | Git-ignored (`*.db`, `*.db-wal`, `*.db-shm`), removed from git cache |
| **External Dependencies** | SQLite embedded | Retained SQLite embedded (no PostgreSQL, Redis, or external DB introduced) |

