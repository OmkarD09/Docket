# Docket — Engineering Roadmap & Milestone Plan

**Hackathon Target:** PayPal AI Hackathon 2026 (Devpost)  
**Submission Deadline:** November 12, 2026 @ 12:00 PM PST  
**Team Structure:** 3 Developers (Fullstack, Backend/AI, Frontend/UX)  

---

## 1. Roadmap Overview & Timeline

```
┌──────────────────────────────────────────────────────────────────────────────────┐
│                             Docket Phase Timeline                             │
│                                                                                  │
│ [Phase 0] Audit & Technical Foundation (COMPLETE)                                │
│    │                                                                             │
│ [Phase 1] PayPal Checkout Orders v2 Validation (In Progress)                     │
│    │                                                                             │
│ [Phase 2] Real Dispute Acquisition & Payload Audit                               │
│    │                                                                             │
│ [Phase 3] Typed Evidence Model & Deterministic Policy Barrier                    │
│    │                                                                             │
│ [Phase 4] AI Semantic Fact Extraction & Citation Engine                          │
│    │                                                                             │
│ [Phase 5] 20-Case Synthetic Evaluation Benchmark Suite                           │
│    │                                                                             │
│ [Phase 6] Controlled Evidence-Submission Workflow (Human-Gated)                  │
│    │                                                                             │
│ [Phase 7] Merchant Command Desk UI (React + AG Grid)                             │
│    │                                                                             │
│ [Phase 8] Reliability Hardening, Demo Video (<3 min) & Devpost Packaging         │
└──────────────────────────────────────────────────────────────────────────────────┘
```

---

## 2. Phase-by-Phase Milestone Plan

### Phase 0: Project Audit and Technical Foundation
- **Status:** **VERIFIED & COMPLETE**
- **Objective:** Validate live Sandbox API communication, establish TDD test suite, audit workspace, and lock architectural principles.
- **Deliverables:**
  - `scripts/spike_paypal_dispute.py` (OAuth2, listing, detail, sanitization).
  - `tests/test_paypal_dispute.py` (51 unit tests, 99% coverage).
  - `docs/sandbox-spike.md`, `.env.example`, `.gitignore`, `pytest.ini`.
- **Exit Gate:** 100% unit tests pass; live OAuth handshake verified; secrets strictly excluded.

---

### Phase 1: PayPal Sandbox Checkout Validation (Orders v2)
- **Status:** **IN PROGRESS (Blocked on US Sandbox Account)**
- **Objective:** Establish a repeatable e-commerce checkout flow in Sandbox to generate transactions for dispute filing.
- **Dependencies:** User creates a US Business Account and matching US Personal Buyer Account in PayPal Developer Dashboard.
- **Deliverables:**
  - `scripts/create_test_order.py` (Creates order via `POST /v2/checkout/orders`).
  - Capture helper (`POST /v2/checkout/orders/{id}/capture`).
  - Unit tests covering order creation, capture errors, timeouts, and state verification.
- **Acceptance Criteria:**
  1. Order creation returns HTTP 201 with an official buyer approval link.
  2. Buyer approves the transaction in the sandbox browser.
  3. Capture returns HTTP 201 `COMPLETED` with valid `seller_transaction_id` and `buyer_transaction_id`.
- **Exit Gate:** Captured USD transaction ID verified in the merchant dashboard.

---

### Phase 2: Real Dispute Acquisition and Schema Audit
- **Status:** **PLANNED**
- **Objective:** File an Item Not Received dispute on the captured transaction and inspect the raw PayPal Sandbox response payload.
- **Dependencies:** Successful transaction from Phase 1.
- **Deliverables:**
  - Automated or browser-guided dispute submission in buyer Sandbox Resolution Center (`MERCHANDISE_OR_SERVICE_NOT_RECEIVED`).
  - Real payload captured and documented in `docs/fixtures/real_sandbox_dispute_inr.json`.
  - Schema comparison against official PayPal documentation (checking `seller_response_due_date`, `evidences`, `allowed_response_options`, and HATEOAS `links`).
- **Acceptance Criteria:**
  1. Dispute appears in `GET /v1/customer/disputes`.
  2. `GET /v1/customer/disputes/{dispute_id}` returns full details.
  3. `scripts/spike_paypal_dispute.py` prints sanitized summary of the real dispute.
- **Exit Gate:** Real dispute ID configured in `.env` and successfully audited.

---

### Phase 3: Typed Evidence Model & Deterministic Policy Barrier
- **Status:** **VERIFIED & COMPLETE**
- **Objective:** Implement Pydantic v2 domain schemas and the core code-level refusal barrier that blocks unverified claims.
- **Dependencies:** Phase 0 & Phase 2 schema audit.
- **Deliverables:**
  - `docket/models/`: Pydantic domain models for `DisputeCase`, `ShipmentRecord`, `OrderRecord`, `RefundRecord`, `SourceCitation`, `ExtractedClaim`, `PolicyCheckResult`, `OverallPolicyEvaluation`.
  - `docket/reconciliation/`: Cross-source multi-key matcher (Transaction ID, Order ID, Buyer Email).
  - `docket/policy/`: Code-level refusal barrier enforcing:
    - *Delivery Invariant:* Tracking status `LABEL_CREATED` or `IN_TRANSIT` strictly blocks claiming delivery.
    - *Address Match Invariant:* Delivered destination zip/city must match transaction shipping address.
    - *Signature Invariant:* Strictly flags missing signature for orders > $750.00; pre/post-Jan 2026 distinction.
    - *HATEOAS Invariant:* Verifies `provide_evidence` action eligibility and prevents unpermitted API states.
    - *Citation Integrity Invariant:* Deep traversal, typed matching, and contradiction detection.
- **Acceptance Criteria:**
  1. Unit tests confirm 100% block rate on "Label Created" delivery claims.
  2. Unit tests verify valid delivery passes policy checks.
- **Exit Gate:** Zero reliance on LLMs for policy gating; 100% deterministic code coverage.

---

### Phase 4: AI Semantic Fact Extraction & Citation Engine
- **Status:** **VERIFIED & COMPLETE**
- **Objective:** Connect an LLM to extract atomic factual assertions from unstructured documents and communications with strict verbatim citations.
- **Dependencies:** Phase 3 schemas.
- **Deliverables:**
  - `docket/ai/`: Structured extraction prompts targeting Pydantic output (`BaseFactExtractor`, OpenAI, Claude, Gemini, `DeterministicFactExtractor`).
  - Strict citation mapping linking claims to document IDs and character/line offsets (`VerbatimCitationVerifier`).
  - Prompt injection sanitation barrier stripping system instruction overrides from buyer notes (`PromptInjectionGuard`).
  - Contradiction detector flagging conflicts between customer claims and internal records (`ContradictionDetector`).
- **Acceptance Criteria:**
  1. Extracts facts without fabricating dates, amounts, or tracking numbers.
  2. Rejects prompts containing injection attacks without executing instructions.
  3. Outputs confidence scores and flags uncertain inferences.
- **Exit Gate:** Verified JSON schema compliance; all extracted assertions cite physical source records.

---

### Phase 5: Synthetic Evaluation Suite (15–20 Cases)
- **Status:** **VERIFIED & COMPLETE**
- **Objective:** Build an automated evaluation matrix proving system accuracy and refusal robustness across diverse dispute edge cases.
- **Dependencies:** Phase 3 & 4.
- **Deliverables:**
  - `docket/eval/`: Benchmark models (`EvalExpectation`, `EvalScenario`, `EvalResult`, `EvalScorecard`), benchmark runner (`BenchmarkRunner`), and 20 labeled scenarios (`docket/eval/scenarios.py`).
  - Labeled scenario catalog:
    1. *INR: Label Created only (Must Refuse).*
    2. *INR: Verified Delivery with Matching Address (Pass).*
    3. *INR: Delivery to Wrong Postal Code (Must Refuse).*
    4. *INR: Pre-2026 Order > $750 without Signature (Seller Protection Deficiency).*
    5. *INR: Post-2026 Order > $750 without Signature (Advisory Only).*
    6. *INR: Prior Refund Overlap (Anomalous Claim).*
    7. *INR: Physical In-Transit (Refuse Delivery Proof).*
    8. *INR: Timeline Paradox (Order placed after dispute).*
    9. *INR: Currency Mismatch (EUR vs USD).*
    10. *Adversarial: Prompt Injection in buyer note (Flagged & Refused).*
    11. *INR: Orphan Dispute (No matching order).*
    12. *INR: Ambiguous Multiple Orders (Confidence split).*
    13. *Action Gate: Inquiry + Open (Action BLOCK).*
    14. *Action Gate: Dispute Already Resolved (Action BLOCK).*
    15. *Action Gate: Untrusted Phishing Host (Action BLOCK).*
    16. *SNAD: Split Shipment Partial Delivery.*
    17. *INR: Intangible Goods Exemption (> $750 exempt from signature).*
    18. *INR: Fabricated Citation (Refused by citation integrity).*
    19. *INR: Partial Amount Dispute ($50 vs $200).*
    20. *Baseline: Real Captured Sandbox Fixture (`PP-R-NKI-10193390`).*
- **Acceptance Criteria:**
  1. Automated test runner outputs precision, recall, and refusal metrics.
  2. 100% detection rate on prompt injection and "Label Created" delivery claims.
- **Exit Gate:** Published evaluation scorecard artifact `artifacts/docket_evaluation_matrix.json` documenting empirical 100% accuracy and 100% refusal recall.

---

### Phase 6: Controlled Evidence-Submission Workflow
- **Status:** **VERIFIED & COMPLETE**
- **Objective:** Implement the human-in-the-loop merchant approval gate and live submission to PayPal's `POST /v1/customer/disputes/{id}/provide-evidence`.
- **Dependencies:** Phase 2, 3, 4, 5.
- **Deliverables:**
  - `docket/dispatch/`:
    - `approval.py`: `ApprovalService`, HMAC token creation, payload tampering detection, expiration verification, and merchant approval records.
    - `dispatcher.py`: `EvidenceDispatcher`, `EvidencePayloadFormatter` adhering to PayPal's official `provide-evidence` schema, HATEOAS URL routing, and idempotency lock.
  - `docket/audit/`:
    - `logger.py`: `AuditLogger` append-only JSONL cryptographic hash-chain ledger (`artifacts/audit_trail.jsonl`).
  - Verification script: `scripts/verify_dispatch_pipeline.py` verifying full end-to-end execution.
- **Acceptance Criteria:**
  1. Submissions without verified merchant approval are strictly blocked (`MerchantApprovalRequiredError`).
  2. Submissions with unverified delivery or policy violations are strictly blocked (`SubmissionBlockedError`).
  3. Tampered evidence payloads immediately fail cryptographic verification (`PayloadTamperedError`).
  4. Duplicate submissions are prevented via idempotency lock (`DuplicateSubmissionError`).
  5. Audit ledger maintains unbroken SHA-256 hash chaining verified via `verify_chain_integrity()`.
- **Exit Gate:** Verified test suite (210 tests passing) and intact cryptographic audit trail artifact.

---

### Phase 7: Merchant Command Desk UI (React + AG Grid)
- **Status:** **VERIFIED & COMPLETE**
- **Objective:** Build a high-density, accessible merchant operations dashboard matching the **Operate Mode** design system and qualifying for the $5,000 AG Grid partner track.
- **Dependencies:** FastAPI backend endpoints from Phase 3–6.
- **Deliverables:**
  - `docket/api/app.py`: FastAPI REST API exposing 8 endpoints for dispute triage, details, HMAC approval ticketing, affirmative authorization, policy dispatch, cryptographic audit logging, and benchmark scorecard.
  - `frontend/`: React 19 + Vite + TypeScript.
  - **Dispute Queue:** AG Grid v36 table (`@ag-grid-community/core` + `ag-grid-react`) using `themeQuartz.withParams`, pinned columns, custom cell renderers for status, amounts, policy decisions, prompt threat shields, and violated invariants.
  - **Case Workbench (`DisputeDetailPanel`):** Split drawer with multi-tab inspection: Cross-Source Evidence Graph, Policy Barrier Diagnostics, and Affirmative Merchant Approval Desk.
  - **Audit Trail Drawer (`AuditTrailView`):** Chronological timeline of evidence ingestion, policy evaluation, and API results with unbroken SHA-256 hash chaining verification pill.
  - **Benchmark Scorecard (`EvalScorecardView`):** Interactive matrix for the 20/20 formal benchmark suite displaying 100% accuracy, 100% refusal recall/precision, and prompt threat detection.
  - **Local Dev Orchestrator:** `scripts/run_dev.py` for single-command launch of both backend and frontend.
- **Acceptance Criteria:**
  1. Merchant can identify evidence gaps within 5 seconds of opening a case.
  2. Submission button is visually and functionally disabled if policy checks fail.
  3. AG Grid implementation utilizes custom cell renderers, sorting, and responsive filtering.
  4. TypeScript compilation and Vite bundling pass cleanly with zero errors (`tsc -b && vite build`).
  5. 100% backend test pass rate maintained with 12 new API tests (222 total passing tests).
- **Exit Gate:** Production frontend bundle built (`dist/`), backend API tested, and end-to-end local development verified.

---

### Phase 8: End-to-End Reliability, Demo Video & Hackathon Submission
- **Status:** **PLANNED**
- **Objective:** Final integration testing, packaging, 3-minute video production, and Devpost submission.
- **Dependencies:** All previous phases.
- **Deliverables:**
  - Unified local run script (`./run.ps1` or `docker-compose.yml`).
  - Public GitHub repository with MIT License and thorough `README.md`.
  - **Demo Video (< 3 minutes):**
    - Act 1 (0:00 - 0:45): The problem (merchant facing INR dispute; danger of LLM hallucinating delivery when tracking only says "Label Created").
    - Act 2 (0:45 - 1:45): Docket in action (AG Grid triage, side-by-side reconciliation, deterministic refusal barrier stopping false claim).
    - Act 3 (1:45 - 2:30): Verified delivery case (evidence matched, merchant approval, live PayPal Sandbox API submission receipt).
    - Act 4 (2:30 - 3:00): Architecture, safety guarantees, and audit trail.
  - Devpost submission text, architecture diagrams, and testing instructions.
- **Exit Gate:** Submitted before the November 12, 2026 deadline.

---

## 3. Team Ownership Matrix (3-Person Split)

| Workstream | Team Member | Primary Responsibilities | Hand-off Interfaces |
| :--- | :--- | :--- | :--- |
| **Backend & PayPal Integration** | **Developer 1 (Lead Backend)** | - PayPal API client & OAuth token lifecycle.<br>- Orders v2 Checkout & dispute acquisition.<br>- Controlled evidence submission endpoint.<br>- SQLite persistence & audit logging. | - REST API endpoints (`/api/disputes`, `/api/orders`, `/api/submit`).<br>- Pydantic schemas. |
| **Core Engine, AI & Evaluation** | **Developer 2 (AI & Domain Lead)** | - Evidence reconciliation multi-key matching.<br>- Deterministic policy engine & refusal invariants.<br>- LLM structured fact extraction & citations.<br>- 15–20 case synthetic evaluation suite. | - `reconcile()` and `evaluate_policy()` core services.<br>- JSON evaluation benchmark report. |
| **Frontend, UX & Demonstration** | **Developer 3 (Frontend & Design Lead)** | - React + Vite + TypeScript application.<br>- AG Grid integration (Dispute Queue & triage).<br>- Impeccable Operate design system & CSS tokens.<br>- Side-by-side reconciliation & approval desk.<br>- Demo video recording & UI polish. | - Consumes REST API.<br>- Demo script & walkthrough screen recordings. |
