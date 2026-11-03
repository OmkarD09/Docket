# Docket — Project Status & Evidence Ledger

**Last Audit Timestamp:** 2026-11-03T19:30:00+05:30  
**Environment:** Windows 11 / Python 3.14.8 / Node v24.21.0 / Vite 8.3.5 / Antigravity 2.0  
**Active Milestone:** Milestone 7 (Merchant Command Desk UI — Final Graphite & Signal Blue Redesign, AG Grid v36 Quartz Theme, FastAPI Backend) — COMPLETE  

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
| **Workspace File Audit** | **VERIFIED** | Clean structure verified: `docket/`, `scripts/`, `tests/`, `docs/`, `artifacts/`, `requirements-dev.txt`, `.gitignore`, `.env.example`, `pytest.ini`. |
| **Secret Protection & Git Hygiene** | **VERIFIED** | `.env` is populated locally and strictly excluded in `.gitignore`. No credentials tracked in git. Credential rotation status is **UNKNOWN**. |
| **Unit Test Suite (222 Tests)** | **VERIFIED** | **222 passing tests** (51 dispute spike + 68 policy engine + 27 evidence reconciliation + 30 AI fact extraction + 10 eval suite + 24 dispatch and audit + 12 API endpoint tests) executed via `pytest`: exited code 0 in 1.67s. Zero regressions. |
| **Code Coverage (97% Total, 97% Docket)** | **VERIFIED** | `docket/models/`: **99.6%** coverage (539 stmts).<br>`docket/policy/engine.py`: **95%** coverage (244 stmts).<br>`docket/reconciliation/engine.py`: **97%** coverage (163 stmts).<br>`docket/ai/`: **96.3%** coverage (337 stmts).<br>`docket/eval/`: **96.6%** coverage (245 stmts).<br>`docket/dispatch/`: **95.8%** coverage (214 stmts).<br>`docket/audit/`: **93.3%** coverage (90 stmts).<br>`docket/api/`: **92.1%** coverage (225 stmts).<br>`docket/` core package total: **97%** coverage (2159 statements, 65 misses).<br>`scripts/spike_paypal_dispute.py`: **99%** coverage.<br>`scripts/create_test_order.py`: 0% coverage. |
| **Pydantic v2 Domain Models** | **VERIFIED** | Implemented across `docket/models/`: `DisputeCase`, `ShipmentRecord`, `Address`, `SourceCitation`, `ExtractedClaim`, `OrderRecord`, `CustomerMessageRecord`, `RefundRecord`, `CandidateMatch`, `ReconciledDisputeBundle`, `ReconciliationDiscrepancy`, `PolicyCheckResult`, `OverallPolicyEvaluation`, `EvalExpectation`, `EvalScenario`, `EvalResult`, `EvalScorecard`, `ApprovalDecision`, `ApprovalRequest`, `MerchantApprovalRecord`, `EvidencePayload`, `DispatchResult`, `AuditEvent`, `AuditEventType`. |
| **Deterministic Policy Engine (Hardened)** | **VERIFIED** | Implemented in `docket/policy/engine.py`: `DeliveryProofInvariant` (hard refusal on `LABEL_CREATED` and `IN_TRANSIT`), `AddressMatchInvariant` (destination delivery area check with explicit Seller Protection disclaimer), `HATEOASActionInvariant` (HTTPS enforcement, allowed PayPal host constraint, exact dispute ID check, lifecycle/status validation, evidence type/source matching), `SignatureAssessmentInvariant` (strict `> $750.00` boundary, multi-currency lookup, pre/post-Jan 26 2026 distinction, non-blocking advisory), `CitationIntegrityInvariant` (dotted path traversal with list indexing, typed equality, excerpt containment for text fields, contradiction detection, unverified/conflicting/rejected source handling). |
| **Multi-Dimensional Decision Evaluation** | **VERIFIED** | `OverallPolicyEvaluation` exposes independent `factual_readiness`, `action_readiness`, and `advisories` dimensions, allowing a claim to be factually validated even if an API action is currently blocked by dispute status. |
| **Cross-Source Evidence Reconciler** | **VERIFIED** | Implemented in `docket/reconciliation/engine.py`: Multi-key matching (exact transaction ID, exact order ID, secondary email + amount + 24h window, tertiary 7-day window); email conflict preclusion; anomaly detection (`TIMELINE_PARADOX`, `CURRENCY_MISMATCH`, `AMOUNT_MISMATCH`, `ADDRESS_MISMATCH`, `PRIOR_REFUND_OVERLAP`); multi-source graph linking (shipments, customer messages, refunds); and automated `SourceCitation` generation. |
| **AI Semantic Fact Extraction & Citations** | **VERIFIED** | Implemented in `docket/ai/`: `PromptInjectionGuard` (scans override patterns, role manipulation, action bait, tag boundary encapsulation), `VerbatimCitationVerifier` (verifies exact substrings and character offsets against source documents), `ContradictionDetector` (flags non-receipt assertions contradicted by carrier delivery, prior refund overlaps, split shipments), pluggable multi-provider REST adapters (OpenAI `json_schema`, Anthropic Claude tool use, Gemini function declarations), and `DeterministicFactExtractor` for 100% offline testing. |
| **Synthetic Evaluation Suite (20 Scenarios)** | **VERIFIED** | Implemented in `docket/eval/` (`models.py`, `scenarios.py`, `runner.py`) and verified by `tests/test_eval_suite.py`. Benchmark executed across 20 labeled scenarios spanning all dispute reasons and fraud vectors: **100% accuracy (20/20)**, **100% refusal recall (5/5)**, **100% refusal precision**, **100% Label Created refusal rate**, and **100% prompt injection threat detection**. Matrix exported to `artifacts/docket_evaluation_matrix.json`. |
| **Controlled Evidence Submission & Dispatch Gate** | **VERIFIED** | Implemented in `docket/dispatch/` (`approval.py`, `dispatcher.py`) and verified by `tests/test_dispatch_and_audit.py` and `scripts/verify_dispatch_pipeline.py`. Pre-submission refusal barrier (`is_ready_for_submission()` requirement), HMAC cryptographic approval tokens with payload integrity verification, expiration enforcement, idempotency duplicate prevention, and PayPal `provide-evidence` schema payload formatting. |
| **Cryptographic Hash-Chained Audit Ledger** | **VERIFIED** | Implemented in `docket/audit/` (`logger.py`) and verified by `tests/test_dispatch_and_audit.py`. Append-only JSONL ledger (`artifacts/audit_trail.jsonl`) with parent-hash chaining and SHA-256 event fingerprints; verified unbroken with `verify_chain_integrity()`. |
| **Defining Scenario Verification** | **VERIFIED** | Validated in both unit tests (`test_e2e_ai_extracted_claim_blocked_by_policy_on_label_created`), Benchmark Scenario 01 (`SCENARIO_01_INR_LABEL_CREATED`), and dispatch tests (`test_dispatcher_refuses_when_policy_blocks`): an AI-proposed delivery claim is mathematically refused (`RULE_DELIVERY_PROOF`) by `PolicyEngine` when carrier tracking indicates `LABEL_CREATED`, precluding external dispatch. |
| **FastAPI REST API Layer** | **VERIFIED** | Implemented in `docket/api/app.py` and verified by `tests/test_api_endpoints.py` (12 tests passing). Exposes endpoints for dispute summaries, case details, HMAC approval ticketing, affirmative authorization, policy-enforced dispatch, cryptographic audit inspection, and benchmark scorecard. |
| **Merchant Command Desk UI (AG Grid v36)** | **VERIFIED** | Implemented in `frontend/`: React 19 + TypeScript + AG Grid Community v36 with `themeQuartz.withParams`. Official **Graphite & Signal Blue** design system (Stripe/fintech-inspired, high density, light theme, zero AI slop), persistent collapsible sidebar, top navigation with breadcrumbs, pinned left columns, monospace monetary figures, custom policy cell badges, split-screen evidence drawer, HMAC approval desk, append-only audit trail viewer, and 20/20 benchmark matrix dashboard. Verified via `tsc -b && vite build` (0 errors, production bundle in 2.41s) and headless browser screenshots at 1440x900 and 1280x720. |
| **Unified Dev Runner (`scripts/run_dev.py`)** | **VERIFIED** | Single-command launch orchestrating FastAPI uvicorn server (port 8000) and Vite React dev server (port 5173) with graceful SIGINT termination. |
| **Live PayPal Sandbox OAuth 2.0** | **REPORTED** | Historical handshake on 2026-10-18 succeeded, returning real Bearer token. Live API calls withheld during audit/milestone. |
| **Live Dispute Listing Endpoint** | **REPORTED** | `GET /v1/customer/disputes` returned HTTP 200 OK with `items: []` on initial sandbox setup. |
| **Orders v2 Creation (`scripts/create_test_order.py`)** | **VERIFIED (CODE)** | `POST /v2/checkout/orders` helper exists; hardcodes `NO_SHIPPING` and requires test coverage. |
| **Captured Transaction Record** | **REPORTED** | Captured USD order ID `09P720153W688771J`, capture ID `4R073105U90937213` ($25.00 USD). |
| **Real Sandbox Dispute Retrieval** | **VERIFIED (FIXTURE)** | Real payload `docs/fixtures/real_sandbox_dispute_inr.json` parsed into typed `DisputeCase` via `DisputeCase.from_paypal_response()`. Active `provide_evidence` action verified. Successfully reconciled, evaluated, approved, and dispatched in `scripts/verify_dispatch_pipeline.py`. |
| **End-to-End Packaging & Video (< 3 min)** | **PLANNED** | Scoped in Milestone 8. |

---

## 2. Next Immediate Blockers & Priorities

1. **Packaging, Video Script & Submission Readiness (Milestone 8):**
   - Produce a concise, high-impact demonstration video script (< 3 minutes) highlighting the defining scenario (Label Created refusal vs Verified Delivery allow), the AG Grid triage desk, the HMAC merchant approval desk, and the cryptographic audit trail.
   - Assemble `README.md` and Devpost submission assets highlighting PayPal AI Hackathon main track and AG Grid sponsor track eligibility.
2. **Orders Helper Hardening (`scripts/create_test_order.py`):**
   - Update shipping preference to include physical shipping address and write unit tests in `tests/test_paypal_checkout.py`.
