# Docket — Project Status & Evidence Ledger

**Last Audit Timestamp:** 2026-10-18T18:34:00+05:30  
**Environment:** Windows 11 / Python 3.14.8 / Antigravity 2.0  
**Active Milestone:** Milestone 1 (Audit & Technical Foundation)  

---

## 1. Project Status Matrix

Every capability and artifact is classified under one of five strict statuses:
- `VERIFIED`: Confirmed by direct execution and evidence in the current workspace.
- `REPORTED BUT NOT RECHECKED`: Stated in historical logs but requires current verification.
- `PLANNED`: Designed and scoped in roadmap; implementation not yet started.
- `BLOCKED`: Work cannot proceed until an external dependency or user action resolves.
- `UNKNOWN`: Insufficient evidence to determine current status.

| Capability / Artifact | Status | Current Evidence / Findings |
| :--- | :--- | :--- |
| **Workspace File Audit** | **VERIFIED** | Clean structure verified: `scripts/`, `tests/`, `docs/`, `requirements-dev.txt`, `.gitignore`, `.env.example`, `pytest.ini`. No extraneous files. |
| **Secret Protection & Git Hygiene** | **VERIFIED** | `.env` is populated locally and strictly excluded in `.gitignore`. No secrets in source code. |
| **Unit Test Suite (51 Tests)** | **VERIFIED** | 51 passing tests with 99% code coverage executed on Python 3.14: `pytest` exited code 0 in 0.34s. |
| **Error Handling Coverage** | **VERIFIED** | Tested and verified: 401, 403, 404, 429, 500, 503, connection drops, request timeouts, malformed JSON, missing fields. |
| **Live PayPal Sandbox OAuth 2.0** | **VERIFIED** | Handshake against `https://api-m.sandbox.paypal.com/v1/oauth2/token` succeeded, returning real Bearer token. |
| **Live Dispute Listing Endpoint** | **VERIFIED** | `GET /v1/customer/disputes` returned HTTP 200 OK with `items: []` (0 disputes on Indian sandbox account). |
| **Dispute Response Sanitization** | **VERIFIED** | Sanitization functions redact buyer names, emails, transaction IDs, and credentials. Unit tested. |
| **Orders v2 Creation (`scripts/create_test_order.py`)** | **VERIFIED** | `POST /v2/checkout/orders` created orders returning valid approval URLs. |
| **Orders v2 Capture on US Account** | **VERIFIED** | Order `09P720153W688771J` approved by US buyer and captured: status `COMPLETED`, capture ID `4R073105U90937213` ($25.00 USD). |
| **US Sandbox Account Setup** | **VERIFIED** | US Business (`sb-2mews53303427@business.example.com`) and US Personal (`sb-6oifq53423350@personal.example.com`) active and transacting. |
| **Real Sandbox Dispute Retrieval** | **VERIFIED** | Item Not Received dispute `PP-R-NKI-10193390` filed and successfully retrieved via `GET /v1/customer/disputes/PP-R-NKI-10193390`. Real payload saved in `docs/fixtures/real_sandbox_dispute_inr.json`. |
| **HATEOAS State Verification** | **VERIFIED** | Verified on live case: `INQUIRY` + `OPEN` restricts HATEOAS actions to `self`; `provide_evidence` action correctly detected as absent. |
| **Evidence Reconciliation Engine** | **PLANNED** | Scoped in Milestone 3; Pydantic domain models defined in `docs/ARCHITECTURE.md`. |
| **Deterministic Policy Barrier** | **PLANNED** | Scoped in Milestone 3; invariant rules defined in `docs/PRODUCT_BRIEF.md`. |
| **AI Semantic Fact Extraction** | **PLANNED** | Scoped in Milestone 4; prompt schemas and boundary rules defined. |
| **Synthetic Evaluation Suite (15–20 cases)** | **PLANNED** | Scoped in Milestone 5; test cases categorized in `docs/ROADMAP.md`. |
| **Controlled Evidence Submission (POST)** | **PLANNED** | Scoped in Milestone 6; read-only invariant remains active until Milestone 6. |
| **Merchant Command Desk UI (AG Grid)** | **PLANNED** | Scoped in Milestone 7; React + Vite + AG Grid frontend. |
| **End-to-End Packaging & Video (< 3 min)** | **PLANNED** | Scoped in Milestone 8. |

---

## 2. Immediate Blockers & Dependencies

1. **Sandbox Account Regional Restriction:**
   - *Issue:* Test accounts created under India (`IN`) cannot execute peer-to-peer or domestic e-commerce transactions in PayPal Sandbox.
   - *Resolution:* User to generate a **United States (US) Business Account** and a **US Personal Account** in [PayPal Developer Dashboard](https://developer.paypal.com/dashboard/accounts).
   - *Next Immediate Action:* Once credentials are provided, capture a $25 USD order, file an INR dispute, and inspect the real dispute response.
