# Docket — Final Persistence and Sandbox Integration Readiness Report

**Date:** 2026-11-09  
**Environment:** Python 3.14.8 / SQLite 3.49+ (WAL mode) / FastAPI / React 19 + TypeScript  
**Status:** FULLY INTEGRATED & VERIFIED (306 backend tests passing, frontend production build verified, live PayPal Sandbox dispute persisted)

---

## Executive Summary

This review concludes the persistence and sandbox integration hardening cycle for Docket. All four areas specified in the review mandate have been audited, hardened, and verified with automated test coverage:

1. **Cryptographic Serialization Clarification:** Verified exact JSON canonicalization semantics. Corrected previous documentation that prematurely claimed strict RFC 8785 compliance: Docket uses Python standard library `json.dumps(sort_keys=True, separators=(',', ':'))` for deterministic compact JSON hashing. Documented the `v1` ordered delimiter-separated fingerprint envelope, preserved 100% of historical audit event hashes (65 verified events in SQLite and JSONL), and verified that historical hashes are never regenerated.
2. **Merchant Approval Security Hardened:** Eliminated unnecessary plaintext token exposures, added strict immediate pre-dispatch validation across 5 bound dimensions (dispute ID, action, payload hash, evaluation ID, evidence version), hardened atomic single-use nonce consumption in SQLite, and verified concurrent replay immunity across 10 threads without executing PayPal mutations.
3. **Retention & Versioned Migrations:** Created a formal `schema_migrations` ledger in SQLite tracking version 1 (`001_initial_relational_schema`) and version 2 (`002_soft_archival_and_approvals`). Verified that soft archival preserves approval and audit queryability. Verified online streaming WAL backup restoration. Accurately standardized terminology: Docket's hash chain is **tamper-evident**, not inherently immutable.
4. **Live PayPal Sandbox Persistence Confirmed:** Performed an authentic, strictly read-only retrieval of dispute `PP-R-NKI-10193390` from `https://api-m.sandbox.paypal.com` using backend OAuth 2.0 client credentials. Persisted the live dispute in `artifacts/docket.db` with provenance `REAL_SANDBOX`. Recorded the ingestion in the audit ledger with actor `PAYPAL_SANDBOX_API`. Reconciled `/api/health` counts to `real_sandbox: 1`, `synthetic_benchmark: 19`, `total_unique_cases: 20`, and verified restart survival.

---

## 1. Cryptographic Serialization & Historical Integrity

### 1.1 Conformance Analysis: RFC 8785 vs Python Canonical JSON

Strict RFC 8785 (JSON Canonicalization Scheme / JCS) mandates:
- Canonical floating-point formatting per ECMAScript (e.g., `-0` serialized as `0`, exponential representation rules for numbers $\ge 10^{21}$ or $< 10^{-6}$, integers formatted without fractional parts).
- UTF-16 code-unit sort ordering for JSON object keys.
- Strict string character escaping rules (only `\`, `"`, and control codes `\u0000` through `\u001f` escaped).

**Findings & Documentation Correction:**  
Docket's `AuditLogger` uses Python's standard library:
```python
canonical_payload = json.dumps(payload, sort_keys=True, separators=(",", ":"))
```
While this produces sorted keys without whitespace delimiters, it relies on Python's native number formatting and Unicode string encoding rather than the full RFC 8785 IEEE-754 canonical specification.  
**Correction:** System documentation has been updated to accurately describe the payload serialization as **Python standard library compact sorted-key canonical JSON**, removing unevidenced references to strict RFC 8785 compliance.

### 1.2 Delimiter-Separated Input & Field Boundaries

The event fingerprint is constructed using an ordered, colon-delimited format (Envelope Version `v1`):
```
fingerprint = f"{parent_hash}:{event_id}:{event_type}:{timestamp_iso}:{dispute_id}:{actor}:{canonical_payload}"
event_hash = sha256(fingerprint.encode("utf-8")).hexdigest()
```
- `parent_hash`: 64-character hex SHA-256 digest or `"GENESIS"`.
- `event_id`: Unique `evt_` prefixed 16-character identifier.
- `event_type`: Categorized lifecycle enum string (`AuditEventType`).
- `timestamp_iso`: ISO-8601 UTC timestamp format (`datetime.now(timezone.utc).isoformat()`).
- `dispute_id`: PayPal dispute ID string.
- `actor`: System, user, or webhook actor string.
- `canonical_payload`: Sorted compact JSON string.

Because `parent_hash`, `event_id`, and `event_type` are strictly structured tokens and `canonical_payload` is placed as the terminal segment, field boundary ambiguity is prevented during normal operations.

### 1.3 Historical Event Preservation & Zero Hash Regeneration

Historical event hashes are treated as immutable commitments:
- **SQLite Ledger:** 65 audit events in `artifacts/docket.db` verified valid (`is_valid: True`).
- **JSONL Export:** 65 audit events in `artifacts/audit_trail.jsonl` verified valid (`is_valid: True`).
- **No Hash Regeneration:** Existing hashes are never recalculated, updated, or rewritten in place. Historical backward hash chains remain 100% compatible.

Verified in `tests/test_final_persistence_and_sandbox.py::test_cryptographic_serialization_and_historical_integrity`.

---

## 2. Merchant Approval Security

### 2.1 Elimination of Plaintext Token Exposures

- **API Summaries Protected:** `GET /api/disputes` returns `DisputeSummaryResponse` objects which omit internal HMAC tokens, nonce secrets, and sensitive dispatch payloads.
- **Audit Ledger Sanitized:** Audit events for `APPROVAL_REQUESTED`, `APPROVAL_GRANTED`, and `APPROVAL_REJECTED` record only non-sensitive governance metadata (`approval_id`, `decision`, `rejection_reason`), excluding the authorization token string.
- **Relational Storage Scoped:** In SQLite `merchant_approvals`, tokens are stored solely for single-use dispatch verification and are cleared upon consumption.

### 2.2 Immediate Pre-Dispatch Verification Matrix

In [`docket/dispatch/dispatcher.py`](file:///C:/Users/ACER/Downloads/Docket/docket/dispatch/dispatcher.py), `EvidenceDispatcher.dispatch_evidence` enforces strict pre-dispatch invariant checks immediately before any external call:

| Dimension | Checked Value | Invariant Rule | Mismatch Exception |
|:---|:---|:---|:---|
| **Dispute ID** | `approval_record.dispute_id` | Must match target `dispute.dispute_id` | `DisputeMismatchError` |
| **Action** | `approval_record.action` | Must match authorized action (`"provide_evidence"`) | `ActionMismatchError` |
| **Payload Hash** | `approval_record.payload_hash` | Must match `sha256(canonical(evidence_payload))` | `PayloadTamperedError` |
| **Evaluation ID** | `approval_record.evaluation_id` | Must match current policy `evaluation.evaluation_id` | `EvaluationMismatchError` |
| **Evidence Version** | `approval_record.evidence_version` | Must match `bundle.reconciled_at.isoformat()` | `EvidenceVersionMismatchError` |

If any parameter has drifted (e.g. evidence re-reconciled, policy re-evaluated with new rules, payload altered), dispatch immediately aborts before any network transmission or token consumption.

Verified in `tests/test_final_persistence_and_sandbox.py::test_merchant_approval_pre_dispatch_validation_matrix`.

### 2.3 Transactional Single-Use Nonce Tracking & Concurrent Replay Resistance

In [`docket/database/repository.py`](file:///C:/Users/ACER/Downloads/Docket/docket/database/repository.py), `consume_approval_record` executes an atomic conditional update:
```sql
UPDATE merchant_approvals SET
    is_consumed = 1,
    consumed_at = ?,
    consumed_by_dispatch_id = ?
WHERE nonce = ? AND is_consumed = 0
```
This statement guarantees race-free compare-and-swap (CAS) semantics:
- Executed inside an explicit `BEGIN IMMEDIATE` transaction block protected by thread reentrancy locks.
- If multiple threads or processes attempt to consume the same token nonce concurrently, exactly one transaction will match `is_consumed = 0` and report `cur.rowcount == 1`. All subsequent attempts report `cur.rowcount == 0` and are rejected with `TokenAlreadyUsedError`.

**Verification:**  
In `tests/test_final_persistence_and_sandbox.py::test_concurrent_approval_replay_attempts`, 10 concurrent threads in a `ThreadPoolExecutor` simultaneously attempted to consume the same approval token. Exactly 1 thread succeeded, and exactly 9 threads were rejected with `TokenAlreadyUsedError`. Zero PayPal API mutations were executed.

---

## 3. Retention & Versioned Migrations

### 3.1 Formal Schema Migration Tracking

A dedicated migration tracking table was added to SQLite:
```sql
CREATE TABLE IF NOT EXISTS schema_migrations (
    version INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    applied_at TEXT NOT NULL
);
```

The database tracks two formal migration levels:
- **Version 1 (`001_initial_relational_schema`):** Initial 7 relational tables (`disputes`, `source_records`, `extracted_claims`, `policy_evaluations`, `merchant_approvals`, `webhook_receipts`, `audit_events`).
- **Version 2 (`002_soft_archival_and_approvals`):** Adds soft-archival columns (`dispute_category`, `is_archived`, `archived_at`, `archival_reason`), approval tracking columns (`action`, `payload_hash`, `evaluation_id`, `evidence_version`, `nonce`, `is_consumed`, `consumed_at`, `consumed_by_dispatch_id`), and secondary index structures.

Methods `get_schema_version(conn)` and `get_applied_migrations(conn)` expose migration status programmatically.

### 3.2 Audit & Approval Retention via Soft Archival

- **Cascade Block:** `merchant_approvals` maintains `FOREIGN KEY (dispute_id) REFERENCES disputes (dispute_id) ON DELETE RESTRICT`. Any direct SQL `DELETE FROM disputes` is rejected by SQLite if approvals exist.
- **Soft Archival:** `POST /api/disputes/{dispute_id}/archive` marks `is_archived = 1` and records `archival_reason`.
- **Queryability:** Archived disputes are excluded from active triage queues by default, but historical approval records and backward hash chains remain intact and queryable.

### 3.3 Accurate Governance Terminology

> [!NOTE]
> A cryptographic backward hash chain is **tamper-evident**, not inherently immutable.  
> It guarantees that any post-hoc modification, reordering, or interior deletion of historical records is mathematically detectable upon verification. It does not prevent an administrator with direct filesystem write access from truncating the trailing tail of a database file without independent external anchors or checkpoints. All documentation and API responses adhere strictly to this distinction.

---

## 4. Actual PayPal Sandbox Persistence

### 4.1 Read-Only Live API Retrieval

Using backend sandbox credentials (`PAYPAL_CLIENT_ID` and `PAYPAL_CLIENT_SECRET`), Docket queried the live PayPal Disputes API:
```http
GET https://api-m.sandbox.paypal.com/v1/customer/disputes/PP-R-NKI-10193390
Authorization: Bearer <OAuth2_Token>
```

**Live Retrieval Evidence:**
```json
{
  "dispute_id": "PP-R-NKI-10193390",
  "reason": "MERCHANDISE_OR_SERVICE_NOT_RECEIVED",
  "status": "WAITING_FOR_SELLER_RESPONSE",
  "dispute_life_cycle_stage": "INQUIRY",
  "dispute_amount": {
    "currency_code": "USD",
    "value": "25.00"
  },
  "seller_response_due_date": "2026-11-07T13:37:42.244Z"
}
```
**Safety Guarantee:** Strictly read-only query. No dispute mutations, evidence uploads, status transitions, or closing calls were performed.

### 4.2 SQLite Persistence & Provenance Segregation

The retrieved PayPal dispute was ingested into SQLite:
- **Dispute Record:** Stored in `disputes` with `dispute_category = 'REAL_SANDBOX'`.
- **Evidence Reconciliation:** Matched order `ORD-10193390` (PayPal transaction `4R073105U90937213`) and USPS delivered shipment `9400111899223197428490` persisted in `source_records`.
- **Policy Evaluation:** Evaluated deterministically (`overall_decision: ALLOW`, `factual_readiness: READY`, `action_readiness: READY`) and stored in `policy_evaluations`.
- **Audit Ledger:** Appended `DISPUTE_INGESTED` event with actor `"PAYPAL_SANDBOX_API"`, provenance `"REAL_SANDBOX"`, and live endpoint metadata.

### 4.3 Database Count Reconciliation

The live health endpoint (`GET http://127.0.0.1:8000/api/health`) reports:
```json
{
  "status": "ok",
  "version": "1.0.0",
  "timestamp": "2026-11-09T07:21:46.934233+00:00",
  "total_cases_loaded": 20,
  "case_counts": {
    "total_unique_cases": 20,
    "alias_lookup_keys": 40,
    "real_sandbox_disputes": 1,
    "synthetic_benchmark_scenarios": 19,
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
      "real_sandbox": 1,
      "synthetic_benchmark": 19,
      "live_webhook": 0
    }
  }
}
```

- **Clean Segregation:** 1 genuine live Sandbox dispute (`PP-R-NKI-10193390`) is classified under `REAL_SANDBOX`. The remaining 19 test cases (`SCEN-01` through `SCEN-19`) are classified under `SYNTHETIC_BENCHMARK`.
- **Restart Survival:** Tested and confirmed that `REAL_SANDBOX` provenance survives full application reboot and process restarts.

---

## 5. Final Verification Results

### 5.1 Backend Test Matrix (306 Tests Green)

Executing `python -m pytest`:
```
============================= test session starts =============================
platform win32 -- Python 3.14.8, pytest-8.4.2, pluggy-1.6.0
rootdir: C:\Users\ACER\Downloads\Docket
configfile: pytest.ini
collected 306 items

tests\test_ai_extractor.py ................................              [ 10%]
tests\test_ai_live_workflow.py ...........                               [ 14%]
tests\test_api_endpoints.py ............                                 [ 17%]
tests\test_database_integrity.py .......                                 [ 20%]
tests\test_dispatch_and_audit.py ..........................              [ 28%]
tests\test_eval_suite.py ............                                    [ 32%]
tests\test_final_persistence_and_sandbox.py .....                        [ 34%]
tests\test_milestone4_audit.py ......................................... [ 47%]
tests\test_paypal_dispute.py ........................................... [ 61%]
........                                                                 [ 64%]
tests\test_policy_engine.py ............................................ [ 78%]
.............................                                            [ 88%]
tests\test_reconciliation.py ...........................                 [ 97%]
tests\test_sqlite_persistence.py .........                               [100%]

============================= 306 passed in 6.32s =============================
```

### 5.2 Frontend Production Build

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
✓ built in 3.50s
```

### 5.3 Active Services & Daemons

| Service | Host/Port | Process/Task | Status |
|:---|:---|:---|:---|
| **FastAPI Backend** | `http://127.0.0.1:8000` | task-4606 (uvicorn) | RUNNING / HEALTHY |
| **Vite Frontend Dev** | `http://localhost:5173` | task-4604 (vite) | RUNNING / HEALTHY |
| **SQLite Database** | `artifacts/docket.db` | WAL mode, PRAGMA foreign_keys = ON | 20 disputes, 65 audit events |
| **Knowledge Graph** | `graphify-out/` | 8,406 nodes, 14,343 edges | UPDATED (AST-only) |

---

## 6. Architecture Status Summary

| Capability | Baseline Status | Hardened Final Status |
|:---|:---|:---|
| **JSON Canonicalization** | Premature claim of RFC 8785 | Accurately documented as Python standard library compact canonical JSON (`sort_keys=True, separators=(',', ':')`) |
| **Audit Ledger Verification** | 46 events verified | 65 events verified in both SQLite and JSONL; backward chain 100% valid |
| **Historical Hash Integrity** | Untested | 100% backward hash compatibility; no historical hashes regenerated |
| **Pre-Dispatch Binding** | Partial binding | Invariant checks on dispute ID, action, payload hash, evaluation ID, evidence version |
| **Approval Replay Protection** | In-memory `set()` | Transactional CAS update in SQLite; verified under 10 concurrent threads |
| **Schema Migrations** | Ad-hoc `ALTER TABLE` | Versioned `schema_migrations` ledger (Migration 1 & 2 tracked) |
| **Dispute Deletion Protection** | Cascade risks | `ON DELETE RESTRICT` blocks deletion; soft archival preserves queryability |
| **PayPal Sandbox Provenance** | 0 real sandbox reported | 1 authentic `REAL_SANDBOX` dispute persisted live via OAuth 2.0; 19 `SYNTHETIC_BENCHMARK` |
| **Test Baseline** | 294 tests | 306 tests passing green (100% passing) |

