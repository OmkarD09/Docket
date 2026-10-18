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
- **Status:** **PLANNED**
- **Objective:** Implement Pydantic v2 domain schemas and the core code-level refusal barrier that blocks unverified claims.
- **Dependencies:** Phase 0 & Phase 2 schema audit.
- **Deliverables:**
  - `docket/models/`: Pydantic domain models for `Dispute`, `Order`, `TrackingEvent`, `ExtractedClaim`, `PolicyResult`.
  - `docket/reconciliation/`: Cross-source multi-key matcher (Transaction ID, Order ID, Buyer Email).
  - `docket/policy/`: Code-level refusal barrier enforcing:
    - *Delivery Invariant:* Tracking status `LABEL_CREATED` or `IN_TRANSIT` strictly blocks claiming delivery.
    - *Address Match Invariant:* Delivered destination zip/city must match transaction shipping address.
    - *Signature Invariant:* Flags missing signature for orders >= $750.
    - *HATEOAS Invariant:* Verifies `provide_evidence` action is present.
- **Acceptance Criteria:**
  1. Unit tests confirm 100% block rate on "Label Created" delivery claims.
  2. Unit tests verify valid delivery passes policy checks.
- **Exit Gate:** Zero reliance on LLMs for policy gating; 100% deterministic code coverage.

---

### Phase 4: AI Semantic Fact Extraction & Citation Engine
- **Status:** **PLANNED**
- **Objective:** Connect an LLM to extract atomic factual assertions from unstructured documents and communications with strict verbatim citations.
- **Dependencies:** Phase 3 schemas.
- **Deliverables:**
  - `docket/ai/extractor.py`: Structured extraction prompts targeting Pydantic output.
  - Strict citation mapping linking claims to document IDs and character/line offsets.
  - Prompt injection sanitation barrier stripping system instruction overrides from buyer notes.
  - Contradiction detector flagging conflicts between customer claims and internal records.
- **Acceptance Criteria:**
  1. Extracts facts without fabricating dates, amounts, or tracking numbers.
  2. Rejects prompts containing injection attacks without executing instructions.
  3. Outputs confidence scores and flags uncertain inferences.
- **Exit Gate:** Verified JSON schema compliance; all extracted assertions cite physical source records.

---

### Phase 5: Synthetic Evaluation Suite (15–20 Cases)
- **Status:** **PLANNED**
- **Objective:** Build an automated evaluation matrix proving system accuracy and refusal robustness across diverse dispute edge cases.
- **Dependencies:** Phase 3 & 4.
- **Deliverables:**
  - `tests/eval_suite/`: 15–20 labeled scenario fixtures, including:
    1. *INR: Label Created only (Must Refuse).*
    2. *INR: Verified Delivery with Matching Address (Pass).*
    3. *INR: Delivery to Wrong Postal Code (Must Refuse).*
    4. *INR: Order >= $750 without Signature (Policy Flag).*
    5. *SNAD: Buyer asserts wrong color; warehouse slip confirms wrong color (Acknowledge Defect).*
    6. *SNAD: Buyer claims missing items; order invoice shows partial shipment (Flag Split Shipment).*
    7. *INR: Refund already issued prior to dispute (Suggest Claim Acceptance).*
    8. *INR: Tracking timestamp precedes purchase timestamp (Clock Skew / Contradiction).*
    9. *Prompt Injection inside customer email attachment (Block Execution).*
    10. *Dispute already in RESOLVED status (Block Submission).*
    11. *Missing carrier tracking entirely (Evidence Incomplete).*
    12. *Duplicate submission attempt (Idempotency Block).*
- **Acceptance Criteria:**
  1. Automated test runner outputs precision, recall, and refusal metrics.
  2. 100% detection rate on prompt injection and "Label Created" delivery claims.
- **Exit Gate:** Published evaluation scorecard documenting empirical pass/fail rates.

---

### Phase 6: Controlled Evidence-Submission Workflow
- **Status:** **PLANNED**
- **Objective:** Implement the human-in-the-loop merchant approval gate and live submission to PayPal's `POST /v1/customer/disputes/{id}/provide-evidence`.
- **Dependencies:** Phase 2, 3, 4.
- **Deliverables:**
  - `docket/api/submitter.py`: Generates official PayPal `provide_evidence` payload from verified claims.
  - Idempotency and duplicate-submission lock.
  - Merchant approval signature validation.
  - Live Sandbox submission test on our active test case.
- **Acceptance Criteria:**
  1. Submissions without prior merchant approval are rejected with HTTP 403/422.
  2. Successful dispatch receives HTTP 200/204 from PayPal Sandbox and records API correlation ID.
- **Exit Gate:** Successful, verified submission logged in the live PayPal Sandbox Resolution Center.

---

### Phase 7: Merchant Command Desk UI (React + AG Grid)
- **Status:** **PLANNED**
- **Objective:** Build a high-density, accessible merchant operations dashboard matching the **Operate Mode** design system and qualifying for the $5,000 AG Grid partner track.
- **Dependencies:** FastAPI backend endpoints from Phase 3–6.
- **Deliverables:**
  - `frontend/`: React 18 + Vite + TypeScript.
  - **Dispute Queue:** AG Grid table with multi-column filtering, deadline countdown, readiness badges.
  - **Case Workbench:** Clean layout showing dispute metadata and requested evidence types.
  - **Evidence Reconciliation:** Side-by-side claim comparison with green/red conflict highlighting.
  - **Decision & Approval Desk:** Policy evaluation breakdown and gated `Approve & Submit` action.
  - **Audit Trail Drawer:** Chronological timeline of evidence ingestion, policy evaluation, and API results.
- **Acceptance Criteria:**
  1. Merchant can identify evidence gaps within 5 seconds of opening a case.
  2. Submission button is visually and functionally disabled if policy checks fail.
  3. AG Grid implementation utilizes custom cell renderers, sorting, and responsive filtering.
- **Exit Gate:** End-to-end user workflow validated in browser with zero console errors.

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
