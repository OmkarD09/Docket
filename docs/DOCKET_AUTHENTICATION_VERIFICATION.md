# Docket Merchant Authentication & Sign-In Experience Verification

**Status:** APPROVED & VERIFIED  
**Date:** November 11, 2026  
**Environment:** PayPal Sandbox (REST v1) & Synthetic Benchmark Suite  
**Design System:** Graphite & Signal Blue (#0F172A / #0369A1 / #F8F9FA / #FFFFFF)  
**Test Suite:** 325/325 Tests Passing Green (100%)

---

## 1. Executive Summary

Docket is a mission-critical financial dispute operations engine. Before human merchants can approve proposed evidence or dispatch automated dispute packages to PayPal, their identity must be cryptographically verified. Previously, merchant IDs were accepted from client payloads without server-side principal verification.

This update introduces:
1. **Cryptographically Signed Merchant Sessions:** HMAC-SHA256 token envelopes binding `session_id`, `merchant_user_id`, and expiration timestamp.
2. **Dual-Channel Authentication:** Secure, HttpOnly, SameSite browser cookies alongside standard `Authorization: Bearer <token>` support for automated clients and integration tests.
3. **Anti-Spoofing & Invariant Principal Binding:** State-changing endpoints (`/ticket`, `/authorize`, `/dispatch`, `/archive`, `/refresh`, `/eval/run`) strictly reject unauthenticated callers (HTTP 401) and prevent identity tampering or impersonation (HTTP 403).
4. **Canonical Audit Attribution:** All state transitions and ledger events attribute their `actor` strictly to the verified session principal, preventing client-side actor spoofing.
5. **Dedicated Sign In Page:** A minimal, trustworthy login page in Docket visual identity featuring instant 1-click Judge/Evaluator Access across 3 authentic merchant personas, alongside honest credential verification.
6. **Dynamic TopHeader & Sign-Out:** Interactive operator avatar, role badge, display name, and clear single-click session revocation and cookie destruction.

---

## 2. Security & Architectural Model

### 2.1. Signed Session Envelope Specification

Authentication tokens are constructed as four period-delimited components:
```
<session_id>.<merchant_user_id>.<exp_ts>.<hmac_signature>
```
- **`session_id`:** Random 128-bit hex token (`sess_<hex32>`).
- **`merchant_user_id`:** Canonical identity key (e.g. `merchant_ops_primary`, `merchant_supervisor_admin`).
- **`exp_ts`:** Unix epoch integer timestamp enforcing a default 8-hour session TTL.
- **`hmac_signature`:** Constant-time verified HMAC-SHA256 signature generated over `docket_session_v1:<session_id>:<merchant_user_id>:<exp_ts>` using the server secret key.

### 2.2. Pre-Configured Merchant Personas

| Persona ID | Display Name | Role | Email | Authority Scope |
| :--- | :--- | :--- | :--- | :--- |
| `merchant_ops_primary` | Merchant Operations Primary | `DISPUTE_OPERATIONS_LEAD` | `ops@merchant.example.com` | Lead operator authorized for evidence preparation, approval authorization, and dispatch. |
| `merchant_supervisor_admin` | Risk & Compliance Supervisor | `RISK_SUPERVISOR` | `supervisor@merchant.example.com` | Supervisor with high-value approval authority and audit ledger oversight. |
| `merchant_admin` | Merchant System Admin | `SYSTEM_ADMIN` | `admin@merchant.example.com` | System administrator with global operational permissions. |

### 2.3. Anti-Spoofing & Identity Enforcement

When calling state-changing endpoints:
- If a client supplies a `merchant_user_id` in the request body that differs from the authenticated principal derived from the session token or cookie, the server rejects the request immediately with **HTTP 403 Forbidden**:
  ```json
  {
    "detail": "Merchant identity mismatch: authenticated principal is 'merchant_ops_primary', cannot authorize as 'merchant_supervisor_admin'."
  }
  ```
- If omitted from the request body, `merchant_user_id` is automatically populated from the verified principal.
- The audit trail actor is *always* overridden with `current_merchant.merchant_user_id`.

---

## 3. Dedicated Sign-In UI Experience

The dedicated Sign In page (`frontend/src/components/SignInView.tsx`) adheres strictly to the Docket Design System:
- **Canvas:** `#F8F9FA` with subtle mathematical grid backdrop.
- **Card Surface:** `#FFFFFF` with structural border `#E2E8F0` and layered depth.
- **Primary Branding:** Docket Scale glyph, Graphite `#0F172A`, Signal Blue `#0369A1`.
- **Environment Status Pill:** Prominent, live pulse indicator for `PayPal Sandbox (REST v1) · Read-Only Autonomous Mode`.

### User Workflows:
1. **Judge & Evaluator 1-Click Access (Primary Tab):**
   - Allows hackathon judges to review the platform instantly without friction or mandatory account creation.
   - Persona picker allows toggling between Operations Lead, Risk Supervisor, and System Admin.
   - Generates a real cryptographic backend session via `POST /api/auth/demo-session`.
2. **Operator Credentials Sign-In (Honest Credential Tab):**
   - Email & password inputs validated by backend `POST /api/auth/login`.
   - Clear validation and error state notifications for invalid credentials.
   - Honest demo credentials presented upfront (`ops@merchant.example.com` / `docket2026`).
3. **Session Persistence:**
   - On page reload, `frontend/src/App.tsx` calls `GET /api/auth/me`. If a valid cookie exists, the user bypasses login and resumes work seamlessly.
4. **Interactive TopHeader & Sign-Out:**
   - Displays real user initials (e.g. `MO`, `RS`, `SA`).
   - Displays merchant name and mono-styled role badge.
   - "Sign Out" button calls `POST /api/auth/logout`, invalidating the session on the backend and clearing browser cookies.

---

## 4. Verification & Test Evidence

### 4.1. Automated Authentication Test Suite (`tests/test_authentication.py`)

All 11 dedicated authentication security tests pass green:
1. `test_auth_profiles_catalog`: Verifies demo persona catalog inspection.
2. `test_demo_session_creation`: Verifies backend issues valid HMAC session token and sets HttpOnly cookie.
3. `test_get_current_merchant_me`: Verifies identity derivation via `/api/auth/me`.
4. `test_unauthenticated_requests_rejected_with_401`: Verifies unauthenticated calls to `/ticket`, `/authorize`, `/dispatch`, `/archive`, `/refresh`, `/eval/run` return HTTP 401 with `WWW-Authenticate: Bearer`.
5. `test_bearer_token_authorization`: Verifies API clients can authenticate via Authorization header without cookies.
6. `test_expired_session_rejected`: Verifies tokens past expiration timestamp are rejected with HTTP 401.
7. `test_tampered_hmac_signature_rejected`: Verifies cryptographically altered tokens fail constant-time signature checks.
8. `test_logout_and_session_revocation`: Verifies sign-out revokes session server-side and prevents token replay.
9. `test_anti_impersonation_rejection`: Verifies caller spoofing attempts return HTTP 403 Forbidden.
10. `test_credential_login_honest_flow`: Verifies honest credential authentication and error states.
11. `test_audit_event_actor_strictly_derived_from_principal`: Verifies audit ledger records the exact authenticated merchant as the actor.

### 4.2. Full Test Suite Results

```
collected 325 items

tests\test_ai_extractor.py ................................              [  9%]
tests\test_ai_live_workflow.py ...........                               [ 13%]
tests\test_api_endpoints.py ...............                              [ 17%]
tests\test_authentication.py ...........                                 [ 21%]
tests\test_database_integrity.py .......                                 [ 23%]
tests\test_dispatch_and_audit.py ..........................              [ 31%]
tests\test_eval_suite.py .................                               [ 36%]
tests\test_final_persistence_and_sandbox.py .....                        [ 38%]
tests\test_milestone4_audit.py ......................................... [ 50%]
tests\test_paypal_dispute.py ........................................... [ 66%]
tests\test_policy_engine.py ............................................ [ 88%]
tests\test_reconciliation.py ...........................                 [ 97%]
tests\test_sqlite_persistence.py .........                               [100%]

============================= 325 passed in 5.93s =============================
```

### 4.3. Frontend Compilation Build Status

```
> tsc -b && vite build

vite v8.3.5 building client environment for production...
transforming...
✓ 2060 modules transformed.
rendering chunks...
dist/index.html                     0.45 kB │ gzip:   0.29 kB
dist/assets/index-BNXHq_ZN.css     29.76 kB │ gzip:   5.55 kB
dist/assets/index-CQNNNegv.js   1,515.61 kB │ gzip: 419.86 kB
✓ built in 2.61s
```

