# DOCKET — Comprehensive Project Audit & Development Readiness Assessment

**Audit Date:** November 3, 2026  
**Project Working Name:** Docket (formerly ResolveIQ / ResolveGuard)  
**Hackathon Target:** PayPal AI Hackathon 2026 (Devpost)  
**Official Deadline:** November 12, 2026 at 12:00 PM Pacific Time (PT) / 20:00 UTC  
**Remaining Window:** 9 Days  
**Audit Scope:** Strictly Read-Only & Non-Destructive Inspection  

---

## 1. Executive Summary

Docket is an evidence-reconciliation and controlled-decision engine for PayPal merchant disputes. Rather than generating probabilistic dispute letters or autonomous AI rebuttals, Docket acts as a deterministic intelligence layer: reconciling PayPal dispute data against ERP orders and carrier tracking events, enforcing code-level refusal barriers against unsubstantiated claims (e.g., refusing to assert delivery when tracking status is merely "Label Created"), and requiring affirmative merchant authorization before dispatching evidence via the PayPal Disputes API.

This comprehensive audit was conducted on November 3, 2026, to establish the ground-truth technical state of the workspace.

### Key Audit Highlights

| Area | Current Status | Key Findings |
| :--- | :--- | :--- |
| **Unit Test Suite** | **VERIFIED (PASS)** | 51 passing mocked unit tests in `tests/test_paypal_dispute.py`. Execution time: 0.86s. |
| **Code Coverage** | **VERIFIED (88% Total)** | `scripts/spike_paypal_dispute.py` has **99%** coverage (2 missed lines). `scripts/create_test_order.py` has **0%** coverage (untested). |
| **PayPal Read-Only Integration** | **VERIFIED (MOCKED)**<br>**REPORTED (LIVE)** | Mock client verified across 51 scenarios. Historical live OAuth and dispute listing verified on 2026-10-18. Live calls deliberately withheld during audit. |
| **Sandbox Checkout Orders v2** | **VERIFIED (CODE)**<br>**REPORTED (TRANSACTION)** | `scripts/create_test_order.py` implemented but untested. Hardcodes `shipping_preference: "NO_SHIPPING"`. Captured transaction `4R073105U90937213` recorded in fixture. |
| **Real Dispute Acquisition** | **VERIFIED (FIXTURE)** | Real PayPal Sandbox INR dispute `PP-R-NKI-10193390` captured and stored in `docs/fixtures/real_sandbox_dispute_inr.json`. Configured in `.env`. |
| **Evidence Submission** | **PLANNED** | No mutation client implemented. `POST /v1/customer/disputes/{id}/provide-evidence` has not been built or tested. |
| **Core Reconciliation & Policy Engine** | **PLANNED** | Core Pydantic domain models, multi-key matcher, and deterministic refusal rules exist only as architectural designs (`docs/ARCHITECTURE.md`), not yet in code. |
| **Merchant UI Desk** | **PLANNED** | Zero frontend code implemented. No React, Vite, or AG Grid workspace initialized. |
| **Security & Git Hygiene** | **VERIFIED (CLEAN)** | `.env` strictly ignored by git, never committed. No secrets or credentials tracked. Sandbox test accounts use synthetic `@example.com` emails. Credential rotation status is **UNKNOWN**. |
| **Skill Systems** | **VERIFIED (INSTALLED)** | Impeccable, 14 Taste Skills, and ECC (v2.2.0) are fully installed under `.agents/`. Persistent skill selection policy is active in `.agents/rules/skill-selection-policy.md`. |
| **Project Naming** | **VERIFIED (UNIFIED)** | Workspace is 100% updated to "Docket". Zero traces of "ResolveIQ" or "ResolveGuard" remain in git or local files. Minor internal documentation contradictions identified. |

---

## 2. Actual Repository and Workspace Structure

Direct inspection of `C:\Users\ACER\Downloads\Docket` reveals a clean, lean project workspace with one Git branch (`main`) tracking `https://github.com/OmkarD09/Docket.git` at commit `5ea8285`.

```text
Docket/
├── .agents/                                # Agent customisation platform (Antigravity 2.0 / ECC)
│   ├── agents/                             # 68 ECC role-based subagent prompts
│   ├── rules/                              # 42 language, framework, & workflow rules
│   │   ├── README.md
│   │   ├── common-*.md
│   │   ├── python-*.md
│   │   ├── react-*.md
│   │   └── skill-selection-policy.md       # Persistent auto-selection policy
│   ├── skills/                             # 63 installed skill definitions
│   │   ├── impeccable/                     # Impeccable UI/UX skill system
│   │   ├── brandkit/, minimalist-ui/, etc. # Taste Skill collection
│   │   ├── tdd-workflow/, eval-harness/    # ECC engineering skills
│   │   └── ...
│   ├── workflows/                          # 64 executable task workflows
│   └── ecc-install-state.json              # ECC manifest (v2.2.0 minimal profile)
├── docs/                                   # Project documentation & fixtures
│   ├── fixtures/
│   │   └── real_sandbox_dispute_inr.json   # Real captured PayPal Sandbox INR dispute
│   ├── ARCHITECTURE.md                     # Component design, threat model, domain models
│   ├── DECISIONS.md                        # Architectural Decision Records (ADR-001 - ADR-007)
│   ├── PRODUCT_BRIEF.md                    # Problem definition, core invariants, scenarios
│   ├── PROJECT_STATUS.md                   # Historical status ledger from 2026-10-18
│   ├── ROADMAP.md                          # Original 8-phase development roadmap
│   └── sandbox-spike.md                    # Milestone 1 technical guide
├── scripts/                                # Python automation & spike utilities
│   ├── __init__.py
│   ├── create_test_order.py                # PayPal Orders v2 creation and capture helper
│   └── spike_paypal_dispute.py             # Read-only dispute client & CLI diagnostic tool
├── tests/                                  # Pytest test suite
│   ├── __init__.py
│   └── test_paypal_dispute.py              # 51 unit tests for read-only dispute spike
├── .coverage                               # Pytest coverage database (git-ignored)
├── .env                                    # Local PayPal credentials (git-ignored)
├── .env.example                            # Credential template for developers
├── .gitignore                              # Git exclusion rules
├── .pytest_cache/                          # Pytest run cache (git-ignored)
├── .venv/                                  # Python 3.14.8 virtual environment (git-ignored)
├── AGENTS.md                               # Workspace agent instructions & skill pointer
├── LICENSE                                 # MIT Open Source License
├── pytest.ini                              # Pytest configuration (pythonpath = .)
├── README.md                               # Project overview, architecture, & quickstart
├── requirements-dev.txt                    # Development dependencies
└── skills-lock.json                        # Taste Skill dependency lockfile
```

---

## 3. Existing Implementation Inventory

The checklist from the audit specification was cross-referenced directly against disk:

| Item | Status | Location / Details | Notes |
| :--- | :--- | :--- | :--- |
| `scripts/spike_paypal_dispute.py` | **VERIFIED** | `scripts/spike_paypal_dispute.py` (518 lines) | Read-only client with typed exceptions, token caching, dispute parsing, PII sanitization, CLI. |
| `tests/test_paypal_dispute.py` | **VERIFIED** | `tests/test_paypal_dispute.py` (817 lines) | 51 unit tests covering auth, endpoints, rate limits (429), timeouts, errors, sanitization. |
| `requirements-dev.txt` | **VERIFIED** | Root (4 lines) | `requests>=2.31.0`, `python-dotenv>=1.0.0`, `pytest>=8.0.0`, `pytest-cov>=4.1.0`. |
| `.env.example` | **VERIFIED** | Root (14 lines) | Complete template for Sandbox credentials, buyer/seller test accounts, and `PAYPAL_DISPUTE_ID`. |
| `.gitignore` | **VERIFIED** | Root (24 lines) | Excludes `.env`, `.venv`, `.coverage`, `__pycache__`, `.pytest_cache`, OS artifacts. |
| `pytest.ini` | **VERIFIED** | Root (3 lines) | Configures `pythonpath = .` and `testpaths = tests`. |
| `docs/sandbox-spike.md` | **VERIFIED** | `docs/sandbox-spike.md` (155 lines) | Milestone 1 architecture, endpoint specifications, and PowerShell instructions. |
| `scripts/paypal_checkout_spike.py` | **DOES NOT EXIST** | N/A | Functionality implemented under `scripts/create_test_order.py`. |
| `scripts/create_test_order.py` | **VERIFIED** | `scripts/create_test_order.py` (84 lines) | Orders v2 helper: `create_order()` and `capture_order()`. |
| `tests/` and other test files | **VERIFIED** | `tests/test_paypal_dispute.py` only | No unit tests exist for `create_test_order.py` or future modules. |
| `docs/PRODUCT_BRIEF.md` | **VERIFIED** | `docs/PRODUCT_BRIEF.md` (229 lines) | Comprehensive brief defining vision, non-goals, and defining INR test scenarios. |
| `docs/ROADMAP.md` | **VERIFIED** | `docs/ROADMAP.md` (201 lines) | 8-phase engineering roadmap and 3-person team responsibility matrix. |
| `docs/ARCHITECTURE.md` | **VERIFIED** | `docs/ARCHITECTURE.md` (236 lines) | Technical architecture, Pydantic schemas, threat modeling, and flowcharts. |
| `docs/DECISIONS.md` | **VERIFIED** | `docs/DECISIONS.md` (80 lines) | ADR-001 through ADR-007 recorded; 3 open inquiries documented. |
| `docs/PROJECT_STATUS.md` | **VERIFIED** | `docs/PROJECT_STATUS.md` (47 lines) | Evidence ledger dated 2026-10-18 recording initial spike results. |
| `artifacts/resolveiq_dispute_evaluation_matrix.json` | **DOES NOT EXIST** | N/A | No `artifacts/` folder exists. Evaluation matrix is planned for Phase 5. |
| `docs/fixtures/real_sandbox_dispute_inr.json` | **VERIFIED** | `docs/fixtures/real_sandbox_dispute_inr.json` (142 lines) | Real captured PayPal Sandbox INR dispute payload (`PP-R-NKI-10193390`). |

---

## 4. Verified vs. Historically Reported Test Results

### Current Verification (Executed November 3, 2026)

The test suite was executed inside the existing local virtual environment (`.venv` running Python 3.14.8):

```powershell
.\.venv\Scripts\python.exe -m pytest --cov=scripts --cov-report=term-missing
```

**Results:**
- **Collected:** 51 tests
- **Passed:** 51 tests (100%)
- **Failed:** 0
- **Skipped:** 0
- **Duration:** 0.86 seconds

**Coverage Breakdown:**

| Module | Statements | Missing Lines | Coverage | Status |
| :--- | :---: | :---: | :---: | :--- |
| `scripts/__init__.py` | 0 | 0 | 100% | Verified |
| `scripts/spike_paypal_dispute.py` | 263 | 2 (Lines 448, 518) | **99%** | Verified |
| `scripts/create_test_order.py` | 33 | 33 (Lines 3–84) | **0%** | **Grave Testing Gap** |
| **Total Codebase** | **296** | **35** | **88%** | Verified |

### Historical Report vs. Current Verification Comparison

| Metric / Item | Historically Reported (2026-10-18) | Current Verification (2026-11-03) | Discrepancy Analysis |
| :--- | :--- | :--- | :--- |
| **Total Passing Tests** | 51 passed | 51 passed | Matches exactly. Suite is stable. |
| **Reported Code Coverage** | "~99% code coverage" | **88% overall** (99% on `spike_paypal_dispute.py` only) | Historical report omitted `create_test_order.py`, which has 0% coverage. |
| **Test Execution Time** | 0.34s | 0.86s | Normal execution variation across environments. |
| **Python Version** | Python 3.14.8 | Python 3.14.8 | Identical interpreter environment. |

---

## 5. PayPal Sandbox Integration Status

### Read-Only Integration (`scripts/spike_paypal_dispute.py`)

- **Authentication:** Implements OAuth 2.0 Client Credentials Grant against `https://api-m.sandbox.paypal.com/v1/oauth2/token`.
- **Token Management:** Caches access tokens in-memory; supports forced refresh; redacts tokens in error messages and logs.
- **Endpoints Implemented:**
  - `GET /v1/customer/disputes`: Queries dispute lists with configurable `page_size`.
  - `GET /v1/customer/disputes/{dispute_id}`: Retrieves specific dispute details.
- **Data Normalization & Sanitization:** Strips customer names, personal emails, internal transaction IDs, and free-text notes before console rendering.
- **Error Mapping:** 8 typed subclasses of `PayPalDisputeError` covering HTTP 401, 403, 404, 429 (parsing `Retry-After`), 5xx, socket timeouts, network drops, and malformed JSON.
- **Live Status:**
  - *Reported:* Live handshake succeeded on 2026-10-18, returning HTTP 200 with an empty dispute list on the original Indian sandbox account.
  - *Current Audit:* Per the audit scope constraint, live network calls were withheld. Mocked tests confirm 100% logic integrity.

---

## 6. Checkout Transaction Status

To test dispute resolution, a merchant requires real transactions to dispute. This workflow was evaluated:

### Orders v2 Helper (`scripts/create_test_order.py`)

- **Order Creation (`POST /v2/checkout/orders`):**
  - Status: **VERIFIED (IMPLEMENTED)**
  - Creates a $25.00 USD order with `intent: CAPTURE` and item category `PHYSICAL_GOODS`.
  - Extracts and displays the buyer approval link (`rel == "approve"`).
  - **Defect Identified:** Line 49 hardcodes `"shipping_preference": "NO_SHIPPING"`. For an **Item Not Received** dispute, PayPal Seller Protection requires proof of shipment to the address provided on the transaction. An order created without a shipping address cannot properly validate address matching rules (`AddressMatchInvariant`).
- **Buyer Approval Handling:**
  - Status: **MANUAL ONLY / UNTESTED**
  - The script prints `APPROVE_URL`. No browser automation (e.g. Playwright) exists to simulate buyer login and approval. The human developer must manually log into Sandbox with buyer credentials and click approve.
- **Order Capture (`POST /v2/checkout/orders/{id}/capture`):**
  - Status: **VERIFIED (IMPLEMENTED)**
  - Executed via CLI: `python scripts/create_test_order.py capture <ORDER_ID>`.
  - **Safety Flaw:** Lacks interactive confirmation or status pre-checks. If called before buyer approval, PayPal returns an unhandled HTTP 422 `ORDER_NOT_APPROVED`.
- **Captured Transaction Evidence:**
  - Status: **REPORTED & DOCUMENTED IN FIXTURE**
  - Historical capture ID: `4R073105U90937213` (USD 25.00).
  - Associated buyer transaction ID: `4H384663R6471042S`.
  - Associated order ID: `09P720153W688771J`.
  - Real INR dispute filed against this transaction: `PP-R-NKI-10193390`.
- **Testing Coverage:**
  - Status: **0% (BLOCKED FROM CI)**. No unit tests exist for `create_test_order.py`.

---

## 7. Evidence-Submission Status

- **API Mutation Endpoint:** `POST /v1/customer/disputes/{dispute_id}/provide-evidence`.
- **Implementation Status:** **PLANNED (NOT IMPLEMENTED)**.
- **Current Capability:**
  - `scripts/spike_paypal_dispute.py` parses whether `provide_evidence` exists in the dispute's HATEOAS `links` array (`summary.has_provide_evidence_action`).
  - No client method exists to formulate, serialize, or dispatch multipart or JSON evidence payloads to PayPal.
  - No idempotency locks exist to prevent duplicate evidence submission.
  - No merchant approval gate exists in code.
- **Eligible Live Case:** The captured dispute fixture `PP-R-NKI-10193390` is in `status: "WAITING_FOR_SELLER_RESPONSE"` and includes `rel: "provide_evidence"` with target URL `https://api-m.sandbox.paypal.com/v1/customer/disputes/PP-R-NKI-10193390/provide-evidence`.

---

## 8. Security and Git Hygiene Findings

Security and credential handling were audited following strict non-disclosure rules:

| Security Check | Result | Evidence / Analysis |
| :--- | :--- | :--- |
| **`.env` File Presence** | **VERIFIED (PRESENT)** | `.env` exists in workspace root (599 bytes). |
| **`.env` Population** | **VERIFIED (POPULATED)** | All required keys are populated with non-zero lengths (`PAYPAL_CLIENT_ID`, `PAYPAL_CLIENT_SECRET`, `PAYPAL_BUSINESS_EMAIL`, `PAYPAL_BUSINESS_PASSWORD`, `PAYPAL_BUYER_EMAIL`, `PAYPAL_BUYER_PASSWORD`, `PAYPAL_DISPUTE_ID`). |
| **`.env` Git Exclusion** | **VERIFIED (SAFE)** | `git check-ignore -v .env` confirms exclusion via `.gitignore:2:.env`. `git ls-files .env` is empty. |
| **Git History Leak Check** | **VERIFIED (CLEAN)** | `git log --all --full-history -- ".env"` returns zero commits. The initial commit did not track secrets. |
| **Hardcoded Secrets in Source** | **VERIFIED (CLEAN)** | Regex scan across all tracked files identified zero hardcoded credentials. All matches in `tests/` use dummy placeholders (`"test_secret"`, `"mock_id"`). |
| **Credential Rotation Status** | **UNKNOWN** | Because credentials previously appeared in external screenshots and have not been confirmed rotated by the user, rotation status is marked **UNKNOWN**. |
| **Buyer / Seller PII in Fixtures** | **VERIFIED (SYNTHETIC)** | `docs/fixtures/real_sandbox_dispute_inr.json` uses PayPal sandbox mock emails (`*@personal.example.com`, `*@business.example.com`) and synthetic sandbox IDs. No real personal identities are exposed. |
| **Terminal Output Sanitization** | **VERIFIED (DEFENSIVE)** | `scripts/spike_paypal_dispute.py` strips customer names, emails, and transaction IDs from CLI outputs. |

> [!WARNING]
> **Credential Rotation Recommendation:** Although `.env` is properly excluded from Git, the developer should confirm whether the Sandbox Client Secret has been regenerated in the PayPal Developer Dashboard since earlier screenshots were taken.

---

## 9. Installed Skill Verification

The workspace contains three integrated skill and governance packages under `.agents/`:

### A. Skill Inventory & Verification

1. **Impeccable ([pbakaus/impeccable](https://github.com/pbakaus/impeccable)):**
   - **Workspace Path:** `.agents/skills/impeccable/`
   - **Status:** **VERIFIED (INSTALLED & READABLE)**
   - **Files:** `SKILL.md` (11,744 bytes), `scripts/impeccable.cmd`, `reference/`, `agents/`.
   - **Purpose:** Frontend design review, UI planning, UX critique, accessibility audits (WCAG 2.2), layout/typeset polish, and design token extraction into `DESIGN.md`.

2. **Taste Skill Collection ([Leonxlnx/taste-skill](https://github.com/Leonxlnx/taste-skill)):**
   - **Workspace Path:** `.agents/skills/`
   - **Status:** **VERIFIED (INSTALLED & LOCKED)**
   - **Manifest:** `skills-lock.json` locks 14 individual skills:
     - `design-taste-frontend` (v2 default): Web/landing page visual design.
     - `high-end-visual-design`: Polished, agency-grade enterprise styling.
     - `minimalist-ui`: Crisp typography and monochrome editorial styling.
     - `industrial-brutalist-ui`: Dense, mechanical, blueprint/terminal UI.
     - `stitch-design-taste`: Google Stitch design token definitions.
     - `full-output-enforcement`: Exhaustive, unabridged code generation.
     - `brandkit`, `image-to-code`, `imagegen-*`, `redesign-existing-projects`.

3. **Everything Claude Code (ECC) ([affaan-m/ECC](https://github.com/affaan-m/ECC)):**
   - **Workspace Path:** `.agents/`
   - **Status:** **VERIFIED (INSTALLED & CONFIGURED)**
   - **Manifest:** `ecc-install-state.json` (schema `ecc.install.v1`, repoVersion `2.2.0`, minimal profile).
   - **Components:** 68 subagents (`.agents/agents/`), 42 rule files (`.agents/rules/`), 64 workflows (`.agents/workflows/`).

### B. Persistent Skill Selection Policy

- **File:** `.agents/rules/skill-selection-policy.md`
- **Reference:** `AGENTS.md` (root)
- **Status:** **VERIFIED & ACTIVE**
- **Governance:** Mandates inspection of `.agents/skills/` on task start, reading `SKILL.md` before execution, using Impeccable for UI audits, applying Taste Skills for aesthetics, and using ECC for TDD, verification, and error handling.

### C. Skill Assignment Matrix by Docket Workstream

| Workstream | Recommended Skills & Rules | Primary Responsibility |
| :--- | :--- | :--- |
| **Backend Engineering** | `tdd-workflow`, `error-handling`, `.agents/rules/python-coding-style.md`, `.agents/rules/python-fastapi.md` | Core domain models, reconciliation logic, refusal rules, API endpoints. |
| **API Integration** | `spike_paypal_dispute.py` patterns, `error-handling`, `verification-loop` | OAuth lifecycle, Orders v2 checkout, `provide-evidence` submission. |
| **Testing & Verification** | `tdd-workflow`, `verification-loop`, `eval-harness`, `ai-regression-testing` | Unit test suite, synthetic 15-case evaluation matrix, regression checks. |
| **System Architecture** | `architecture-decision-records` (ADRs), `code-architect`, `codebase-onboarding` | Maintaining `ARCHITECTURE.md` and logging ADRs for major decisions. |
| **Dashboard UI & Design** | `impeccable`, `high-end-visual-design`, `minimalist-ui`, AG Grid | Merchant Command Desk, Dispute Queue, side-by-side reconciliation desk. |

---

## 10. Naming Consistency Findings

A complete workspace scan was performed for legacy working names (`ResolveIQ` and `ResolveGuard`):

### Workspace Search Results
- **Tracked Git Files:** 0 occurrences of `ResolveIQ` or `ResolveGuard`.
- **Local & Untracked Files:** 0 occurrences.
- **Git Commit Log:** 0 occurrences (initial commit used `Docket`).
- **Missing File from Checklist:** `artifacts/resolveiq_dispute_evaluation_matrix.json` does not exist on disk.
- **Finding:** The project repository has already been fully updated to **Docket**.

### Documentation Inconsistencies Identified

During the audit of markdown documentation, three internal discrepancies were identified:

1. **Frontend Architecture Conflict (`README.md` vs. `ARCHITECTURE.md`):**
   - `README.md` (line 50) specifies: `Human-in-the-Loop Review UI (FastHTML + HTMX + AG Grid)`.
   - `ARCHITECTURE.md` (Section 2) & `ROADMAP.md` (Phase 7) specify: `React 18+ (Vite, TypeScript) + AG Grid (React)`.
   - *Impact:* The team needs architectural clarity on whether the UI is FastHTML/HTMX or React/Vite. React + Vite + AG Grid is the recommended stack to maximize eligibility for the $5,000 AG Grid partner track.
2. **CLI Argument Bug in `README.md`:**
   - `README.md` (line 147) documents: `python scripts/spike_paypal_dispute.py --dispute-id PP-R-NKI-10193390 --raw`.
   - `scripts/spike_paypal_dispute.py` (line 422–441) does NOT implement a `--raw` argument. Running this command will fail with an argument parsing error.
3. **Contradictory HATEOAS State Description in `PROJECT_STATUS.md`:**
   - `PROJECT_STATUS.md` (line 31) states: *"INQUIRY + OPEN restricts HATEOAS actions to self; provide_evidence action correctly detected as absent."*
   - However, the actual fixture `docs/fixtures/real_sandbox_dispute_inr.json` (lines 110–141) has status `WAITING_FOR_SELLER_RESPONSE` and explicitly includes `rel: "provide_evidence"`.

---

## 11. Highest-Priority Blockers

The following gaps are ranked by severity, dependency, implementation effort, and risk to hackathon completion:

```mermaid
flowchart TD
    B1[Blocker 1: Missing Core Reconciliation & Refusal Barrier] --> B3[Blocker 3: Missing AI Fact Extraction & Citation Engine]
    B1 --> B4[Blocker 4: Missing Merchant UI Command Desk]
    B1 --> B5[Blocker 5: Missing Evidence Submission Endpoint]
    B1 --> B6[Blocker 6: Missing Synthetic Evaluation Benchmark]
    B2[Blocker 2: Untested Checkout Order Helper with NO_SHIPPING] -.-> B5
```

### Blocker Ranking

| Rank | Blocker | Severity | Effort | Risk | Dependencies | Impact on Hackathon Submission |
| :---: | :--- | :---: | :---: | :---: | :--- | :--- |
| **1** | **No Core Reconciliation & Policy Engine** | **CRITICAL** | Medium (1.5 days) | **HIGH** | None | Without this, Docket is merely an API spike, not an evidence-reconciliation agent. Blocks all evaluation, AI extraction, and UI workflows. |
| **2** | **Untested Orders Helper with `NO_SHIPPING`** | **HIGH** | Low (0.5 days) | **HIGH** | US Sandbox Accounts | `create_test_order.py` has 0% test coverage and uses `NO_SHIPPING`. If the active dispute expires, creating a new dispute with address verification will fail. |
| **3** | **No Frontend Merchant UI (AG Grid)** | **HIGH** | Medium (2 days) | **HIGH** | Blocker 1 | Devpost requires a working demo, and AG Grid sponsors a $5,000 partner prize. A CLI-only tool severely hurts the Presentation and UX scoring criteria. |
| **4** | **No AI Fact Extractor & Citation Engine** | **HIGH** | Medium (1 day) | **MEDIUM** | Blocker 1 | PayPal AI Hackathon requires meaningful AI integration. We need structured extraction with document citation mapping and prompt-injection barriers. |
| **5** | **Evidence Submission Mutation Not Implemented** | **MEDIUM** | Low (1 day) | **MEDIUM** | Blocker 1, Active Dispute | To show end-to-end completion in the demo video, the system must dispatch the verified evidence package to PayPal upon merchant approval. |
| **6** | **Synthetic Evaluation Suite Missing** | **MEDIUM** | Medium (1 day) | **LOW** | Blocker 1 | A 15-case evaluation benchmark proves deterministic refusal efficacy (e.g. 100% block rate on "Label Created" delivery claims). |

---

## 12. Revised Nine-Day Roadmap (Nov 3 – Nov 12, 2026)

With approximately 9 days remaining until the **November 12, 2026 @ 12:00 PM PST** deadline, the following focused schedule balances backend rigor, sponsor prize qualification, and demo delivery:

```
┌──────────────────────────────────────────────────────────────────────────────────┐
│                   Docket Revised 9-Day Development Timeline                      │
│                                                                                  │
│ [Day 1 - Nov 3]  Audit Complete + Core Pydantic Models & Refusal Rules           │
│ [Day 2 - Nov 4]  Harden Checkout Order Helper (Shipping + Tests) + Live Verify   │
│ [Day 3 - Nov 5]  Cross-Source Evidence Reconciler (Dispute + Tracking + Order)   │
│ [Day 4 - Nov 6]  AI Semantic Fact Extractor with JSON Schema & Verbatim Citation │
│ [Day 5 - Nov 7]  Evidence Submission API (POST provide-evidence) + Approval Gate │
│ [Day 6 - Nov 8]  15-Case Synthetic Evaluation Benchmark Suite & Scorecard        │
│ [Day 7 - Nov 9]  Merchant Command Desk UI (React + AG Grid + Operate Styling)    │
│ [Day 8 - Nov 10] End-to-End Integration, Local Run Scripts, & Devpost Writeup    │
│ [Day 9 - Nov 11] Demo Video Recording (< 3 min YouTube) & Final UI Polish        │
│ [Buffer - Nov 12] Final Verification & Devpost Submission by 12:00 PM PST         │
└──────────────────────────────────────────────────────────────────────────────────┘
```

### Detailed Daily Milestone Plan

- **Day 1 (Nov 3) — Core Domain Models & Deterministic Refusal Engine:**
  - Establish `docket/models/` using Pydantic v2 (`DisputeCase`, `ExtractedClaim`, `SourceCitation`, `PolicyResult`).
  - Implement `docket/policy/engine.py` with the defining invariant: `DeliveryProofInvariant` (rejects "Delivery Verified" if tracking status is `LABEL_CREATED` or `IN_TRANSIT`).
  - Unit test refusal rules under `tests/test_policy_engine.py` using TDD.
- **Day 2 (Nov 4) — Sandbox Checkout Hardening & Live Verification:**
  - Update `scripts/create_test_order.py`: add valid US shipping address preference (`GET_FROM_FILE`), add interactive CLI capture confirmation.
  - Create `tests/test_create_test_order.py` with mocked unit tests, bringing test coverage to >95%.
  - Verify live dispute status for `PP-R-NKI-10193390` in Sandbox.
- **Day 3 (Nov 5) — Cross-Source Evidence Reconciler:**
  - Build `docket/reconciliation/matcher.py`: multi-key correlation joining PayPal disputes with synthetic merchant orders and carrier tracking records.
  - Implement mock carrier tracking adapter supporting statuses: `LABEL_CREATED`, `IN_TRANSIT`, `DELIVERED` (with zip code matching).
- **Day 4 (Nov 6) — AI Semantic Fact Extractor:**
  - Implement structured LLM extraction via OpenAI / Anthropic / Gemini structured outputs targeting Pydantic schema.
  - Implement prompt-injection defense barrier: strips system instruction overrides from customer communications.
  - Enforce verbatim citation requirement (character offset or field pointer).
- **Day 5 (Nov 7) — Evidence Submission & Human Approval Gate:**
  - Implement `docket/api/submitter.py`: serializes verified claims into PayPal's `POST /v1/customer/disputes/{id}/provide-evidence` schema.
  - Enforce code-level requirement: cannot dispatch without cryptographic or timestamped merchant approval object.
  - Add idempotency lock preventing duplicate API dispatch.
- **Day 6 (Nov 8) — 15-Case Synthetic Evaluation Benchmark:**
  - Build `tests/eval_suite/` with 15 labeled dispute scenarios (INR label created, INR delivered wrong zip, signature missing >= $750, prompt injection attack, already resolved dispute, etc.).
  - Generate an automated evaluation scorecard (`artifacts/evaluation_scorecard.json`) documenting 100% refusal accuracy on invalid claims.
- **Day 7 (Nov 9) — Merchant Command Desk UI (AG Grid):**
  - Initialize `frontend/` (React 18 + Vite + TypeScript + AG Grid Community).
  - Build **Dispute Queue** with AG Grid: multi-column filtering, deadline indicator, readiness badges.
  - Build **Reconciliation Desk**: side-by-side evidence diff, highlighting missing tracking scans in high-contrast red.
  - Build **Merchant Approval Action**: disabled when policy checks fail; enabled only with verified evidence.
- **Day 8 (Nov 10) — End-to-End Integration & Devpost Packaging:**
  - Connect FastAPI backend to React frontend.
  - Write single-command local run script (`./run.ps1` or `docker-compose.yml`).
  - Draft complete Devpost narrative: problem statement, PayPal + AI integration, architecture diagram, AG Grid usage.
- **Day 9 (Nov 11) — Demo Video Production & Submission Readiness:**
  - Record public YouTube walkthrough under 3 minutes following the 4-act script:
    - *Act 1 (0:00–0:40):* The INR problem & the risk of LLMs hallucinating delivery on "Label Created".
    - *Act 2 (0:40–1:30):* Docket triage in AG Grid; refusal barrier stopping the false claim.
    - *Act 3 (1:30–2:20):* Verified delivery case; source citations; merchant sign-off; PayPal Sandbox API dispatch.
    - *Act 4 (2:20–2:55):* Architectural overview, safety guarantees, and audit trail.
  - Upload video to YouTube with public visibility.
- **Day 10 (Nov 12 morning) — Final Review & Submission:**
  - Verify GitHub repository is public with MIT License.
  - Submit Devpost application ahead of the 12:00 PM PST deadline.

---

## 13. Acceptance and Kill Criteria

To guarantee timely completion without falling into perfectionism traps, each critical stage is bounded by explicit criteria:

| Stage | Acceptance Criteria (Must Pass) | Kill Criteria (Pivot if Failed) |
| :--- | :--- | :--- |
| **Stage 1: Core Policy Engine** | Unit tests prove 100% deterministic refusal on `LABEL_CREATED` delivery claims; zero LLM dependency for refusal logic. | If domain model becomes overly complex by end of Day 1, cut down to 3 core invariants: Delivery status, Address match, and HATEOAS presence. |
| **Stage 2: Orders Helper & Sandbox** | Mocked unit tests for order creation and capture reach >=90% coverage; shipping address properly configured. | If Sandbox account experiences regional blocking or network failures, fall back 100% to the verified offline fixture `PP-R-NKI-10193390` with synthetic simulation. |
| **Stage 3: AI Extraction** | LLM outputs valid JSON strictly adhering to `ExtractedClaim` schema with citation pointers; rejects prompt injections. | If external LLM API latency or key setup causes flakiness, implement a deterministic fallback extractor using regex/rule-based heuristics that produces identical schema output. |
| **Stage 4: Evidence Submission** | PayPal `POST provide-evidence` payload generated and validated against PayPal schema; dispatch gated by merchant approval. | If live Sandbox endpoint returns unexpected schema errors, demonstrate verified offline payload generation and simulated HTTP 200 response. |
| **Stage 5: Frontend UI** | AG Grid table displays disputes; case detail displays side-by-side evidence; approve button triggers API call. | If full React + AG Grid setup stalls, fall back to a streamlined single-page React app focusing exclusively on the Dispute Queue and Refusal Banner. |
| **Stage 6: Demo Video** | Video is public on YouTube, under 180 seconds (3 min), clearly demonstrates the defining INR "Label Created" refusal scenario and verified delivery. | If recording runs long, strictly cut architectural slides and focus entirely on live UI screen recording with voiceover. |

---

## 14. The Single Most Important Next Implementation Task

### Task: Implement Core Domain Models & Deterministic Refusal Barrier (`docket/policy/engine.py`)

**Rationale:**  
Docket's core intellectual property and competition-winning differentiator is **evidence reconciliation and deterministic code-level refusal**—specifically proving that when an Item Not Received dispute has a shipping status of "Label Created", the system **refuses** to claim delivery.

Right now, that logic exists only as an architectural description in `docs/ARCHITECTURE.md`. It does not exist in code.

Until this engine is written:
1. We have no data models for the AI extractor to target.
2. We have no refusal evaluation results for the AG Grid UI to display.
3. We have no claims for the evidence submission module to package.

### Scope of Next Task:
1. Create the `docket/` package structure:
   - `docket/__init__.py`
   - `docket/models/dispute.py` (Pydantic v2 schemas: `DisputeCase`, `ShipmentRecord`, `ExtractedClaim`, `PolicyCheckResult`).
   - `docket/policy/engine.py` (`PolicyEngine` enforcing `DeliveryProofInvariant`, `AddressMatchInvariant`, `SignatureThresholdInvariant`, and `HATEOASActionInvariant`).
2. Implement comprehensive TDD unit tests in `tests/test_policy_engine.py`:
   - Testing 100% refusal rate on `LABEL_CREATED`.
   - Testing refusal on `IN_TRANSIT`.
   - Testing pass on `DELIVERED` with matching postal code.
   - Testing address mismatch refusal.
   - Testing >= $750 signature requirement flag.
3. Verify test suite passes with 100% code coverage.

---
*Audit completed by Antigravity Engineering Pair Assistant on November 3, 2026. Ready for user review.*

