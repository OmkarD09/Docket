# Docket — Architectural Decision Records (ADRs) & Decisions Log

**Last Updated:** 2026-10-18  
**Format:** Architectural Decision Record (ADR) + Open Inquiries  

---

## 1. Material Decisions Made

### ADR-001: Python Spike for Milestone 1 Integration Validation
- **Status:** ACCEPTED & VERIFIED
- **Context:** We needed a rapid, rock-solid way to prove PayPal Sandbox OAuth 2.0 authentication, endpoint compatibility, and response parsing without pre-committing to a monolithic framework.
- **Decision:** Built a standalone Python diagnostic utility (`scripts/spike_paypal_dispute.py`) using `requests` and `pytest`.
- **Consequences:** 
  - Validated live Sandbox connection in hours (51 passing unit tests, 99% coverage).
  - Provided clean verification scripts without web framework overhead.
  - Set the foundation for Python/FastAPI backend core.

---

### ADR-002: Strictly Read-Only Milestone 1 Integration
- **Status:** ACCEPTED & ENFORCED
- **Context:** Early API integration testing risks accidental state changes, duplicate claims, or unwanted balance movement on sandbox merchant accounts.
- **Decision:** Restricted Milestone 1 exclusively to HTTP GET operations (`/v1/customer/disputes`, `/v1/customer/disputes/{id}`) and OAuth token generation. Banned all POST/PUT/PATCH mutation endpoints (no dispute creation, evidence submission, refunds, offers, or closures).
- **Consequences:** Safe, auditable technical foundation established with zero risk of corrupted dispute states.

---

### ADR-003: Deterministic Refusal Barrier Overrides AI Output
- **Status:** ACCEPTED
- **Context:** Commercial LLMs often draft confident, agreeable dispute rebuttals that hallucinate delivery or claim an item was received when tracking only says "Label Created — Awaiting Carrier Pickup".
- **Decision:** Implemented a two-tier architecture:
  1. The LLM acts solely as an analyst extracting structured facts and citations.
  2. A deterministic code-level rule engine (`PolicyEngine`) evaluates hard business logic (e.g., carrier tracking status must equal `DELIVERED`, address must match PayPal shipping address, signature confirmation required for orders >= $750).
  - If a rule fails, the claim is **hard-blocked**. The LLM cannot bypass the refusal barrier.
- **Consequences:** Guarantees that Docket never submits unverified delivery claims to PayPal.

---

### ADR-004: PayPal Orders v2 Checkout Helper for Sandbox Dispute Simulation
- **Status:** ACCEPTED
- **Context:** PayPal Sandbox personal accounts often block direct peer-to-peer sending via the *Send & Request* UI with *"Your account is not supported for this action"*.
- **Decision:** Implemented `scripts/create_test_order.py` utilizing the official PayPal Orders v2 REST API (`POST /v2/checkout/orders` with `intent: CAPTURE`) to generate standard e-commerce orders, display the official buyer approval URL, and capture payments via API after buyer confirmation.
- **Consequences:** Provides a reproducible e-commerce checkout flow to generate real transaction IDs eligible for buyer protection disputes.

---

### ADR-005: US Sandbox Business Account Profile for Complete API Access
- **Status:** ACCEPTED (Pending User Sandbox Account Creation)
- **Context:** The initial sandbox accounts were registered in India (`IN`). Due to domestic Indian payment regulations, PayPal blocks INR payments between two Indian accounts in sandbox. Furthermore, international cross-border payments into an Indian sandbox account require export purpose codes.
- **Decision:** Advised creating a United States (`US`) Business Sandbox Account and matching US Personal Buyer account.
- **Consequences:** Unlocks native USD transactions, eliminating regulatory friction and providing 100% feature parity with PayPal's standard Disputes API developer documentation.

---

### ADR-006: Sponsor-Aligned Frontend Architecture with AG Grid
- **Status:** ACCEPTED
- **Context:** AG Grid is an official partner of the PayPal AI Hackathon offering a dedicated sponsor prize track (**Best Use of AG Studio / AG Grid** with $5,000 for 1st place). A merchant dispute desk inherently requires a dense, sortable, multi-column triage grid.
- **Decision:** Selected React + TypeScript + AG Grid for the merchant frontend interface (Dispute Queue, Evidence Grid).
- **Consequences:** 
  - Directly qualifies Docket for the $5,000 partner prize category.
  - Delivers a high-performance, professional enterprise data grid matching the **Operate** mode of our design system.

---

### ADR-007: Human-in-the-Loop Merchant Approval Gate
- **Status:** ACCEPTED
- **Context:** Autonomous AI agents submitting legal or financial rebuttals to financial networks create severe liability and regulatory risks for merchants.
- **Decision:** All consequential actions (submitting evidence to PayPal, accepting claims, issuing refunds, sending messages) require affirmative human merchant click-through with an audit trail recording the merchant identity and timestamp.
- **Consequences:** Prevents automated false submissions and ensures regulatory compliance.

---

## 2. Open Decisions & Unresolved Questions

| Question | Options Under Consideration | Tradeoffs & Evaluation Criteria | Status |
| :--- | :--- | :--- | :--- |
| **Q1: AI Provider for Semantic Fact Extraction** | Option A: Claude 3.5 Sonnet / Haiku<br>Option B: OpenAI GPT-4o / GPT-4o-mini<br>Option C: Google Gemini 1.5 Pro | - Cost, speed, and strict JSON schema support.<br>- All three support structured outputs.<br>- Recommendation: Anthropic Claude 3.5 Sonnet or OpenAI GPT-4o for highest citation precision. | OPEN |
| **Q2: Carrier Tracking Adapter Implementation** | Option A: Fully synthetic carrier tracking simulator with realistic JSON payloads.<br>Option B: Integration with EasyPost Sandbox API. | - EasyPost requires separate third-party sandbox keys and setup complexity for judges.<br>- Synthetic carrier simulator allows simulating deterministic edge cases (label created, wrong zip code, delivered) with 100% reproducibility. | RECOMMENDED: Option A (Synthetic adapter with real FedEx/UPS schemas) |
| **Q3: Local Deployment vs. Cloud Hosted** | Option A: Local single-command run (`npm run dev` + `uvicorn`).<br>Option B: Hosted Vercel + Render instance. | - Devpost judging requires working demo access. Both a public local-run repo and a deployed demo are permitted.<br>- Strategy: Build local-first, containerize or deploy to Render/Vercel for bonus judge convenience. | OPEN |
