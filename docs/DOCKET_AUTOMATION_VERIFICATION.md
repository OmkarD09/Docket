# Docket — Automatic Synchronisation & Continuous Audit Integrity Verification

## Executive Summary

Docket is a financial dispute operations and policy evaluation platform. In production financial operations, dispute synchronisation and cryptographic audit integrity verification are critical system responsibilities that must run autonomously rather than relying on manual operator intervention.

This verification report documents the implementation of automated PayPal Sandbox synchronisation, continuous background audit verification, sensitive-operation integrity gating, and the removal of manual merchant buttons in favour of live telemetry indicators in the Docket Command Desk.

---

## 1. Automated PayPal State Synchronisation

### 1.1 Startup Synchronisation & SQLite Hydration
- **Startup Hydration:** On backend initialization (`create_app`), Docket hydrates all active dispute records, evidentiary claims, source citations, policy evaluation results, and approval records directly from relational SQLite tables (`disputes`, `source_records`, `extracted_claims`, `policy_evaluations`, `merchant_approvals`).
- **Connection Verification:** Validates PayPal Sandbox REST API v1 OAuth2 credentials (`PAYPAL_CLIENT_ID`, `PAYPAL_CLIENT_SECRET`).
- **Target Reconciliation:** Reconciles the genuine merchant dispute (`PP-R-NKI-10193390`) via strictly read-only API requests (`GET /v1/customer/disputes/{id}`).
- **Synthetic Fixture Distinction:** Synthetic benchmark scenarios (Scenarios 01–19) remain isolated from live PayPal reconciliation.

### 1.2 Unchanged State Detection & Audit Ledger Integrity
- **Change Detection:** Incoming dispute payloads are compared against existing in-memory and SQLite dispute states (status, lifecycle stage, dispute amount).
- **Zero Redundant Events:** If the dispute payload matches the current state, Docket updates synchronization telemetry timestamps (`last_successful_sync`, `last_attempted_sync`) without appending redundant `DISPUTE_SYNCHRONIZED` events to the audit ledger.
- **Genuine Mutation Logging:** Only actual lifecycle or status transitions emit canonical audit events (`DISPUTE_SYNCHRONIZED`, `DISPUTE_INGESTED`).

### 1.3 Scheduled Reconciliation, Backoff, and Multi-Worker Locking
- **Configurable Polling Interval:** Default 60-second periodic polling interval, configurable via `DOCKET_SYNC_INTERVAL_SECONDS`.
- **Exponential Backoff with Jitter:** On network or API failures, Docket calculates:
  $$\text{backoff} = \min(300, \text{base\_interval} \times 2^{\min(\text{failures}, 4)}) + \text{jitter}(1.0, 5.0)$$
- **Status State Machine:**
  - `1–2` consecutive failures $\to$ `DELAYED`
  - `3+` consecutive failures $\to$ `FAILED`
  - Successful reconciliation $\to$ resets counter to 0 and transitions to `UP_TO_DATE`.
- **Distributed Coordination Locks:**
  - Database-backed lock in SQLite (`system_coordination_locks` table) with lease expiration timestamps (`expires_at`), preventing duplicate concurrent reconciliation jobs across multiple worker processes or instances.
  - In-process non-blocking threading lock (`threading.Lock(blocking=False)`) preventing overlapping runs in the same worker process.

### 1.4 Webhook-Driven Updates & Idempotency
- **Supported Events:** Handles `CUSTOMER.DISPUTE.CREATED`, `CUSTOMER.DISPUTE.UPDATED`, and `CUSTOMER.DISPUTE.RESOLVED`.
- **Atomic Idempotency:** Validates against the `webhook_receipts` SQLite table. If a webhook with the identical `event_id` or `idempotency_key` has already been recorded, duplicate processing is skipped, and a `DUPLICATE_WEBHOOK_IGNORED` audit entry is safely recorded without altering dispute state.

---

## 2. Automatic Audit Chain Verification

### 2.1 Incremental Verification on Every Event Write
- **Pre-Commit Verification:** Every call to `AuditLogger.log_event()` incrementally verifies:
  1. Canonical JSON serialization of event attributes and payload.
  2. Cryptographic SHA-256 fingerprint generation.
  3. Parent hash linkage matching the chain head (`parent_hash == expected_parent`).
- **Tamper Prevention:** Any severed parent hash link or serialization discrepancy raises an immediate `AuditVerificationError` before database transaction commit.

### 2.2 Periodic Full-Chain Verification
- **Background Interval:** Runs full mathematical verification across the entire `audit_events` SQLite table at configurable intervals (default 60 seconds).
- **Verification Metrics:** Calculates total events, verified events, and failed events.
- **Documented Security Boundary:** Consistent with cryptographic principles, local SHA-256 hash chains guarantee interior integrity and tamper-evidence, but cannot independently detect tail truncation without an external checkpoint or external ledger anchoring.

### 2.3 Sensitive-Operation Integrity Gate
- **Pre-Execution Gate:** Prior to merchant approval (`POST /api/disputes/{id}/authorize`) or evidence dispatch (`POST /api/disputes/{id}/dispatch`):
  1. Validates the merchant's authenticated principal (`AuthenticatedMerchant`).
  2. Validates approval ticket status, payload hash matching, and single-use nonces.
  3. **Full Audit Chain Integrity Verification:** Runs a full SQLite verification via `verify_sensitive_operation_gate()`.
- **Integrity Blocking:** If any record in the SQLite audit ledger has been modified, tampered with, or corrupted, the sensitive operation is immediately blocked with **HTTP 409 Conflict**:
  ```json
  {
    "detail": "Sensitive operation blocked: audit ledger integrity failure detected: Hash mismatch at event 'evt_...'"
  }
  ```

---

## 3. Frontend Experience & UI Transformation

### 3.1 Removal of Manual Operator Actions
- **Sync State Button:** Removed from `TopHeader.tsx`.
- **Verify Chain Button:** Removed from `AuditTrailView.tsx`.
- **Refresh from PayPal / Sync Button:** Removed from `DisputeDetailPanel.tsx` drawer header.
- The open dispute detail drawer now continuously and silently synchronizes with backend updates every 8 seconds without manual operator intervention.
- Normal operators are freed from having to manually trigger synchronization or ledger verifications.

### 3.2 Live Status Telemetry Indicators in TopHeader
The top navigation header now displays two compact, real-time status indicators designed in Docket's **Graphite & Signal Blue** design system:

| Indicator | Statuses | Visual Presentation | Telemetry Details |
| :--- | :--- | :--- | :--- |
| **PayPal Sandbox** | `UP_TO_DATE`, `SYNCING`, `DELAYED`, `FAILED` | Emerald / Amber / Rose dot or spinning loader | Last sync relative time, reconciled dispute counts, environment, retry status |
| **Audit Ledger** | `VERIFIED`, `VERIFYING`, `INTEGRITY_WARNING`, `VERIFICATION_FAILED` | Emerald ShieldCheck, Amber Loader, Rose AlertOctagon | Verified records count vs total records, last verification time, tail truncation notice |

### 3.3 Autonomous UI Polling
- `frontend/src/App.tsx` establishes conservative background polling (every 8 seconds) fetching:
  - `GET /api/sync/status`
  - `GET /api/audit-trail/status`
  - `GET /api/disputes` (silent background refresh without layout shift or blocking spinners)
- If telemetry requests fail transiently, the UI preserves the last successfully retrieved status and timestamp without error flashing.

---

## 4. Administrative Maintenance Endpoints

For operational recovery, diagnostics, and administrator overrides, Docket exposes secured administrative maintenance endpoints restricted to authenticated supervisors (`DISPUTE_SUPERVISOR_ADMIN`):

| Method | Endpoint | Description | Security |
| :--- | :--- | :--- | :--- |
| `POST` | `/api/admin/sync/trigger` | Triggers immediate on-demand PayPal dispute reconciliation | Bearer token or HttpOnly cookie (`DISPUTE_SUPERVISOR_ADMIN`) |
| `POST` | `/api/admin/audit/verify` | Triggers immediate full SQLite audit chain mathematical verification | Bearer token or HttpOnly cookie (`DISPUTE_SUPERVISOR_ADMIN`) |
| `GET` | `/api/sync/status` | Exposes public sync telemetry state | Unrestricted read-only |
| `GET` | `/api/audit-trail/status`| Exposes public audit integrity verification telemetry | Unrestricted read-only |

---

## 5. Verification & Test Suite Summary

### 5.1 Automated Test Suite (`tests/test_automation.py`)
15 comprehensive automated tests were written and verified green:
- `test_startup_audit_verification`: Full SHA-256 chain validation on startup.
- `test_startup_sync_sqlite_hydration`: Hydrates state from SQLite and establishes connection.
- `test_incremental_audit_verification_success`: Validates SHA-256 hash chaining on append.
- `test_incremental_verification_rejects_parent_hash_mismatch`: Rejects severed links before commit.
- `test_periodic_full_chain_verification`: Verifies all SQLite rows during periodic background cycles.
- `test_tampered_audit_chain_detection`: Verifies tamper detection when payload is modified.
- `test_sensitive_operation_gate_blocking_on_tamper`: Rejects `/authorize` and `/dispatch` with HTTP 409 Conflict if audit ledger tampering is detected.
- `test_coordination_lock_prevents_duplicate_reconciliation`: SQLite coordination lease test.
- `test_service_skips_when_db_locked`: Verifies workers gracefully skip locked jobs.
- `test_sync_failure_exponential_backoff`: Validates retry backoff and status transitions.
- `test_unchanged_state_avoids_redundant_audit_events`: Verifies zero ledger bloat for identical payloads.
- `test_webhook_synchronization_and_idempotency`: Validates duplicate webhook rejection.
- `test_sync_status_endpoint`: Verifies telemetry schema and intervals.
- `test_audit_trail_status_endpoint`: Verifies verified event counts and tail truncation notice.
- `test_admin_manual_maintenance_endpoints`: Tests secured admin override triggers.

### 5.2 Frontend Production Build
`npm --prefix frontend run build` (`tsc -b && vite build`) compiles with zero TypeScript errors or warnings.

