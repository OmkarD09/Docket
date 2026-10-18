# Docket — Product Brief

**Version:** 1.0.0  
**Context:** PayPal AI Hackathon 2026 Submission  
**Focus Area:** Evidence-Reconciliation & Controlled-Decision Agent for PayPal Disputes  

---

## 1. Executive Summary & Vision

**Docket** is an AI-assisted, evidence-reconciliation and controlled-decision system designed for merchants managing payment disputes on PayPal. 

When a customer files a dispute (such as an *Item Not Received* claim), merchants are required to produce specific, compelling, and consistent evidence within strict deadlines. Today, this process is either entirely manual—forcing merchants to frantically cross-reference order management systems, logistics portals, and email records—or carelessly automated with generic LLMs that draft confident, ungrounded responses that invent facts or state that an item was delivered when tracking records only indicate a shipping label was generated.

Docket bridges this gap by acting as a **controlled evidence intelligence layer**. It connects directly to the PayPal Disputes API, ingests internal merchant records, extracts verified facts, identifies critical contradictions and missing proofs, and enforces a **deterministic refusal barrier** that strictly blocks any unsupported factual claim from ever reaching PayPal.

Every claim submitted through Docket is traceable to its source record, and every consequential action requires human-in-the-loop merchant approval.

---

## 2. What Docket Is vs. What It Is NOT

| What Docket IS | What Docket IS NOT |
| :--- | :--- |
| **Evidence Intelligence System:** A tool that evaluates whether available records support specific factual defenses required by PayPal. | **A Chatbot:** It is NOT a conversational chat interface or prompt wrapper that writes generic persuasive dispute letters. |
| **Deterministic Policy Barrier:** A code-level gate that mathematically blocks unverified assertions (e.g. refusing to claim delivery when tracking only says "Label Created"). | **A Blind Defender:** It does NOT automatically defend the merchant or fabricate claims against consumers. |
| **Source-Linked Reasoning Engine:** Every factual statement cites a specific transaction, order, tracking event, or signed document. | **A Legal Arbiter:** It does NOT make legal rulings or guarantee that PayPal will decide in the merchant's favor. |
| **Human-in-the-Loop Workflow:** Merchants explicitly review, authorize, or reject any proposed API response. | **An Autonomous Payment Bot:** It does NOT autonomously accept claims, issue refunds, or move escrowed funds without merchant sign-off. |
| **Actionable Decision Workspace:** Surfaces clear evidence gaps, deadlines, and policy checks in seconds. | **A Passive Dashboard:** It does NOT merely mirror PayPal API JSON without deep cross-source reconciliation. |

---

## 3. The Core Problem We Solve

Consider an online merchant who receives a PayPal dispute for **Item Not Received (INR)** with an active seller response deadline:

```text
               Dispute Alert: $249.99 (INR)
                         │
        ┌────────────────┴────────────────┐
        ▼                                 ▼
   PayPal Record                   Merchant Records
  - Dispute ID                    - Shopify / ERP Order
  - Reason: INR                   - Tracking Number (FedEx/UPS)
  - Deadline: 10 Days             - Customer Support Zendesk Ticket
  - Required: Proof of Delivery   - Inventory / Warehouse Scan
```

In real-world e-commerce, these source records are scattered, contradictory, or incomplete:
1. **The "Label Created" Trap:** The merchant's warehouse printed a label (`Label Created — Awaiting Carrier Pickup`), but the carrier never scanned the package into transit. A naive LLM or rushed merchant might draft: *"The item was shipped with tracking #12345 and delivered."* Submitting this false claim destroys merchant credibility, triggers immediate dispute loss, and exposes the merchant to chargeback penalties.
2. **Address Mismatch:** The tracking record shows delivery, but delivery occurred in a different zip code or city than the buyer's PayPal transaction shipping address.
3. **Prior Refund Overlap:** Customer service already issued a partial store credit or refund, but the dispute was still escalated.
4. **Time Pressures:** Disputes have strict statutory deadlines (typically 10 to 20 days depending on lifecycle stage). Missing the deadline causes automatic forfeiture.

**Docket's Core Principle:**
> *Every factual claim must be traceable to its supporting source, and unsupported claims must be blocked before submission. Docket is equally valuable when it reveals that the merchant does not have enough evidence to contest the dispute.*

---

## 4. Defining Test Scenarios

### Scenario A: The INR "Label Created" Defect (Mandatory Refusal)
- **Dispute Type:** `MERCHANDISE_OR_SERVICE_NOT_RECEIVED`
- **Available Tracking:** Carrier tracking record status is `LABEL_CREATED`.
- **System Behavior:**
  - Identifies that PayPal requires valid Proof of Delivery (online tracking showing delivery status and recipient address match).
  - Matches the tracking event, noting carrier pickup has not occurred.
  - **Refusal Engine Triggered:** Deterministically refuses to assert delivery.
  - **UI Presentation:** Displays a high-contrast warning badge: `Evidence Gap: Proof of Physical Transit/Delivery Missing`.
  - **Recommended Action:** Advise merchant to accept claim, contact carrier to trace shipment, or message the buyer directly.

### Scenario B: Verified Delivery (Compliant Challenge)
- **Dispute Type:** `MERCHANDISE_OR_SERVICE_NOT_RECEIVED`
- **Available Tracking:** Carrier tracking shows `DELIVERED` with timestamp, destination city/postal code matching the PayPal transaction shipping address, and signature confirmation if over $750.
- **System Behavior:**
  - Verifies signature requirement against dispute threshold.
  - Validates recipient and address consistency.
  - Compiles structured `PROOF_OF_FULFILLMENT` evidence payload referencing tracking number and carrier.
  - Presents case as `Ready for Review` with source citations.
  - Submits to PayPal only upon explicit merchant approval button click.

### Scenario C: Contradictory Records & False Claims
- **Dispute Type:** `MERCHANDISE_OR_SERVICE_NOT_AS_DESCRIBED`
- **Evidence:** Order invoice lists "Model Pro (Black)", warehouse packing slip lists "Model Lite (White)".
- **System Behavior:**
  - Semantic cross-check flags item attribute contradiction (`Conflict Detected`).
  - Blocks automatic rebuttal. Recommends merchant acknowledge exchange or issue partial refund.

---

## 5. Core Architectural Differentiators

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           Docket Core Engine                             │
│                                                                             │
│  ┌───────────────────────┐        ┌──────────────────────────────────────┐  │
│  │ PayPal Disputes API   │        │ Internal Merchant Records            │  │
│  │ (Live Sandbox)        │        │ (Orders, Tracking, Support Logs)     │  │
│  └──────────┬────────────┘        └──────────────────┬───────────────────┘  │
│             │                                        │                      │
│             ▼                                        ▼                      │
│     ┌────────────────────────────────────────────────────────┐              │
│     │          Cross-Source Evidence Reconciliation          │              │
│     └────────────────────────┬───────────────────────────────┘              │
│                              │                                              │
│                              ▼                                              │
│     ┌────────────────────────────────────────────────────────┐              │
│     │        AI Fact Extraction & Source Citation Map        │              │
│     └────────────────────────┬───────────────────────────────┘              │
│                              │                                              │
│                              ▼                                              │
│     ┌────────────────────────────────────────────────────────┐              │
│     │        DETERMINISTIC REFUSAL & POLICY BARRIER          │              │
│     │   - Checks proof requirements & delivery status        │              │
│     │   - Verifies address & recipient match                 │              │
│     │   - Blocks unverified or conflicting assertions        │              │
│     └────────────────────────┬───────────────────────────────┘              │
│                              │                                              │
│             ┌────────────────┴────────────────┐                             │
│             ▼                                 ▼                             │
│    [Policy Failure]                   [Policy Passed]                       │
│    Action: BLOCK SUBMISSION           Action: STAGE FOR APPROVAL            │
│    Log: Missing Evidence Gap          Log: Verified Claims Audit            │
│                                               │                             │
│                                               ▼                             │
│                                   ┌──────────────────────┐                  │
│                                   │ Merchant UI Approval │                  │
│                                   └──────────┬───────────┘                  │
│                                              │                              │
│                                              ▼                              │
│                                   ┌──────────────────────┐                  │
│                                   │ PayPal API Dispatch  │                  │
│                                   └──────────────────────┘                  │
└─────────────────────────────────────────────────────────────────────────────┘
```

### A. Cross-Source Evidence Reconciliation
Matches disputes to internal orders by buyer email, transaction ID, order number, or date window. Ingests normalized synthetic order, tracking, and refund records alongside real PayPal Sandbox API data.

### B. Source-Linked Claims
Every assertion is a structured object:
```json
{
  "claim_id": "CLM-001",
  "statement": "Shipment label generated via carrier USPS",
  "status": "VERIFIED",
  "source_document_type": "CARRIER_TRACKING",
  "source_document_id": "TRK-94001118992231001",
  "exact_citation_excerpt": "Status: Shipping Label Created, USPS Awaiting Item"
}
```

### C. Deterministic Refusal Barrier (Code-Level Rule Engine)
Independent of the LLM, a strict rules engine validates:
- Does the claim require physical delivery proof?
- Does the tracking status equal `DELIVERED`? If `LABEL_CREATED` or `IN_TRANSIT`, reject the claim.
- Does the recipient zip code match the PayPal buyer shipping address?
- Does the dispute lifecycle stage permit `provide_evidence` according to HATEOAS links?
If any rule fails, the proposed claim is hard-blocked and the system logs an immutable reason.

### D. Bounded AI Semantic Extraction
The LLM is strictly used for unstructured text extraction (e.g. reading customer emails, parsing carrier notes, identifying contradictory statements in returns). The LLM is **never** given API keys to submit to PayPal directly.

### E. Human Approval & Audit Log
Every consequential action requires a merchant confirmation click. An immutable audit record tracks:
- Dispute ID & timestamp.
- Evaluated sources and extracted claims.
- Policy check rules fired (passed and failed).
- Approving user identity and timestamp.
- Exact payload dispatched to PayPal and subsequent HTTP response.

---

## 6. Merchant Product Experience & The 5 Core Views

Designed under the **Operate** mode of our design system: high scanability, high data density, zero fluff, and prominent evidence gap indicators.

1. **Dispute Queue:**
   - Table of active cases with Dispute ID, Reason, Buyer, Amount, Deadline countdown timer, Lifecycle Stage (`INQUIRY`, `CHARGEBACK`), and **Evidence Readiness Badge** (`Ready`, `Incomplete`, `Blocked`, `Action Needed`).
   - Powered by sponsor-aligned AG Grid for rapid multi-column sorting and filtering.
2. **Case Workbench:**
   - Deep view of the dispute details, transaction summary, PayPal requested evidence types (`PROOF_OF_FULFILLMENT`, etc.), and available HATEOAS actions.
3. **Evidence Reconciliation (Side-by-Side Comparison):**
   - Left column: PayPal Dispute claims & buyer assertion.
   - Right column: Merchant internal order details, tracking timeline, and customer communications.
   - Highlighting: Red for contradictions/gaps, green for verified matches.
4. **Decision & Approval Desk:**
   - System recommendation with plain-English justification.
   - Action buttons gated by policy validation:
     - `Submit Evidence to PayPal` (Enabled only if all required claims are verified).
     - `Accept Claim & Refund` (Recommended if evidence is absent and deadline is close).
     - `Message Buyer` (Permitted during Inquiry stage).
5. **Audit Trail & Evidence Binder:**
   - Complete timeline of data ingestion, rules evaluation, merchant approval stamp, and PayPal API receipts.

---

## 7. Dispute Lifecycle State Machine

```text
[Awaiting Evidence]
       │
       ▼
[Reconciling Sources]
       ├── (Missing Proof) ──> [Evidence Incomplete] ──> (Accept Claim / Request Docs)
       ├── (Mismatch)      ──> [Conflict Detected]   ──> (Manual Merchant Review)
       ├── (Rule Failure)  ──> [Blocked by Policy]   ──> (Submission Prohibited)
       └── (All Validated) ──> [Ready for Review]
                                      │
                                      ▼ (Merchant Approves)
                               [Approved for Submission]
                                      │
                                      ▼ (Dispatched to PayPal API)
                               [Submitted to PayPal]
                                      │
                                      ▼ (API Adjudication)
                               [Resolved: WON / LOST]
```

---

## 8. MVP Scope for the PayPal AI Hackathon

- **Core Scenario:** Focus on **Item Not Received (INR)** disputes with carrier tracking evaluation ("Label Created" refusal vs. "Delivered" proof).
- **Secondary Scenario:** Basic **Significantly Not As Described (SNAD)** with product specification mismatch detection.
- **PayPal Integration:** Live Sandbox API connection for OAuth2, Dispute Details, Dispute Listing, and controlled Evidence Submission.
- **AI Integration:** Structured fact extraction and contradiction detection via modern LLM with strict JSON schema output.
- **Deliverables:** Working local web app, demo video (< 3 mins), public open-source repository, comprehensive test coverage (unit + evaluation suite).
