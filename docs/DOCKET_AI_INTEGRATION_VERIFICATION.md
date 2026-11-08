# DOCKET — AI Integration Audit & Live Extraction Verification

**Specification:** Milestone 4 / AI Integration Vertical Slice & Gemini 3.8 Live Verification  
**Environment:** Python 3.14.8 | FastAPI | React 19 / TypeScript | Cryptographic JSONL Chained Ledger  
**Date:** November 2026  
**Status:** **AUDITED, HARDENED & VERIFIED** (263/263 Tests Passing)

---

## 1. Executive Summary

Docket is an evidence-reconciliation and controlled-decision platform for PayPal merchant disputes. This document provides a complete audit of Docket's AI capabilities, details the migration and compatibility verification for Google Gemini 3.8 Flash, establishes strict epistemic and citation boundaries, audits the cryptographic ledger architecture, and presents the verified end-to-end semantic extraction workflow and policy decisions across five distinct evidential cases.

### Key Outcomes
- **Dual Model Verification Architecture (Gemini 3.8 Flash & Gemini 2.5 Flash):**
  - Upgraded the Gemini REST adapter (`GeminiFactExtractor`) to support Google's reasoning/thinking models. Implemented streaming candidate aggregation via `streamGenerateContent`, dynamic chunk concatenation, and comprehensive `usageMetadata` parsing (capturing `thoughtsTokenCount`, `promptTokenCount`, and `candidatesTokenCount`).
  - Verified `GEMINI_MODEL=gemini-3.8-flash` loading and real API request dispatch to `https://generativelanguage.googleapis.com/v1beta/models/gemini-3.8-flash:streamGenerateContent`.
  - Transparently recorded live API responses: Gemini 3.8 Flash confirmed adapter readiness and request URL, but real-time extraction is currently blocked by Google AI Studio Free Tier's daily request limit of 20 requests/day per project/model (HTTP 429 `RESOURCE_EXHAUSTED`). The raw successful execution log from earlier in the session (`task-2859`, extracting 4 structured claims via function calling) has been preserved in [`artifacts/task_2859_raw_gemini_38_evidence.json`](file:///artifacts/task_2859_raw_gemini_38_evidence.json).
  - Gemini 2.5 Flash completed the full end-to-end extraction and policy pipeline in 4.48s with 100% citation verification, preserved in [`artifacts/live_gemini_smoke_test_result.json`](file:///artifacts/live_gemini_smoke_test_result.json).
- **Sound ContradictionCode Normalization:** Replaced custom string equality hacks with a canonical code (`DELIVERY_STATUS_DISCREPANCY`), an explicit legacy normalization function (`normalize_contradiction_code`), and automatic normalization on construction. Guaranteed standard symmetric string equality, hash consistency, dictionary/set lookups, and JSON serialization/deserialization.
- **Refined Claim Taxonomy & Epistemic Boundaries:** Added `NON_RECEIPT_ASSERTED` to `ClaimType`. Replaced ambiguous `OTHER` types with domain-aligned categories (`NON_RECEIPT_ASSERTED` and `COMMUNICATION_ACKNOWLEDGED`). Enforced a strict epistemic boundary: buyer statements reporting courier remarks are treated strictly as buyer hearsay (`COMMUNICATION_ACKNOWLEDGED`), never promoted to independent carrier evidence.
- **100% Verbatim Citation Verification:** Every extracted claim is validated against real source documents using `VerbatimCitationVerifier`, extracting exact character offsets (`[start:end]`). Fabricated or hallucinated excerpts are rejected.
- **Calibrated Case A Address Confidence & Seller Protection Scope:** Case A explicitly scopes `ALLOW` to verified carrier tracking status within the transaction destination area (postal code and country matched). It explicitly articulates five distinct criteria and disclaims guaranteed street-level recipient delivery confirmation or guaranteed PayPal Seller Protection dispute victory. Rules are versioned (`2026.1`) and linked to authoritative guidelines.
- **Tri-Partite UI Decision Presentation:** Decoupled `Factual Readiness`, `Action Eligibility`, and `Merchant Recommendation`. When PayPal allows action (`ALLOW`) but factual review is required (`REVIEW`), the UI displays "Factual Review Outstanding" and locks evidence dispatch until human resolution of the directive.
- **Cryptographic Ledger Reality Audit:** Audited the storage engine: Docket utilizes an append-only, tamper-evident JSONL cryptographic hash-chain ledger (`artifacts/audit_trail.jsonl`), not an SQLite relational database. SHA-256 hash chaining detects altered, deleted, or reordered records.
- **Comprehensive Regression Verification:** 263 backend tests passing in 2.80s (including 19 new milestone 4 audit tests); frontend production build (`tsc -b && vite build`) green in 1.87s.

---

## 2. Phase 1 — Gemini 3.8 Flash Migration & REST Adapter Compatibility

Google's Gemini 3.8 Flash (`models/gemini-3.8-flash`) introduces integrated thinking tokens (`"thinking": true`). In the Gemini REST API (`v1beta`), this requires specific adapter adjustments:

| Dimension | Gemini 2.5 Flash | Gemini 3.8 Flash | Docket Adapter Implementation (`provider_gemini.py`) |
|---|---|---|---|
| **Thinking Support** | Optional / Model variant | Enabled by default (`thinking: true`) | Adapter supports thinking mode seamlessly via streaming candidate assembly. |
| **HTTP Transport** | Unary `generateContent` or `streamGenerateContent` | `streamGenerateContent` required for thinking models (unary sheds load or times out) | `_post_generate` uses `streamGenerateContent`, aggregating candidate parts across chunks. |
| **Function Calling** | Forced mode `ANY` | Function calling with `thoughtSignature` parts | Parses `functionCall` arguments while preserving `thoughtSignature` metadata. |
| **Usage Metadata** | `promptTokenCount`, `candidatesTokenCount`, `totalTokenCount` | Adds `thoughtsTokenCount` in final stream chunk | Extracts full token breakdown including `thoughtsTokenCount` into `SemanticWorkflowResult.usage_metadata`. |
| **Error Handling** | Standard HTTP status codes | 503 / 429 quota handling | Defensively captures HTTP errors and extracts structured error messages without corrupting application state. |

---

## 3. Phase 2 — Live Gemini API Smoke Test Verification

### Input Test Data
- **Buyer Message (`MSG-00`):**
  > "The tracking page says my package was delivered yesterday, but I never received it. I contacted the courier, and they told me the parcel may have been left at another address."
- **Order Record (`ORD-LIVE-7701`):** Casey Miller, $75.00 USD, Postal Code: `95113`.
- **Carrier Tracking (`SRC-USPS-TRACKING-API`):** USPS tracking `9400111899223197428490`, Status: `DELIVERED` on `2026-11-07T14:22:00Z`, Postal Code: `95113`.
- **Valid Source Whitelist:** `['MSG-00', 'ORD-LIVE-7701', 'SRC-USPS-TRACKING-API']`.

### A. Gemini 3.8 Flash Live Verification Evidence & Status
- **Configured Model:** `gemini-3.8-flash` (loaded from `GEMINI_MODEL` environment variable)
- **Live Provider Request URL:** `https://generativelanguage.googleapis.com/v1beta/models/gemini-3.8-flash:streamGenerateContent`
- **Credential Status:** `Configured (Present)` — sensitive credential strings strictly redacted
- **Live Execution Diagnostics:**
  - Real HTTP requests were dispatched directly to Google's live endpoint.
  - The live API returned **HTTP 429 (`RESOURCE_EXHAUSTED`)**:
    ```json
    {
      "error": {
        "code": 429,
        "message": "Quota exceeded for metric: generativelanguage.googleapis.com/generate_content_free_tier_requests, limit: 20, model: gemini-3.8-flash, description: Generate content requests per day limit exceeded on Free Tier. See https://aistudio.google.com/docs/rate-limits.\nPlease retry in 18h...",
        "status": "RESOURCE_EXHAUSTED",
        "details": [
          {
            "@type": "type.googleapis.com/google.rpc.QuotaFailure",
            "violations": [
              {
                "quotaMetric": "generativelanguage.googleapis.com/generate_content_free_tier_requests",
                "quotaId": "GenerateRequestsPerDayPerProjectPerModel-FreeTier",
                "quotaDimensions": {
                  "location": "global",
                  "model": "gemini-3.8-flash"
                },
                "quotaValue": "20"
              }
            ]
          }
        ]
      }
    }
    ```
  - **Audit Finding:** The Google AI Studio Free Tier enforces a cap of 20 requests/day for `gemini-3.8-flash` on this project. This is a per-project Free Tier quota limit, not a universal multi-tier limit. Real live extraction via Gemini 3.8 remains blocked by daily quota exhaustion until the window resets or billing is activated.
  - **Historical Successful Invocation (`task-2859`):** Earlier in this session (`task-2859`), before the 20 RPD cap was reached, a live request to `gemini-3.8-flash` successfully extracted 4 structured claims via `record_extracted_claims` with valid function arguments. Raw evidence preserved in [`artifacts/task_2859_raw_gemini_38_evidence.json`](file:///artifacts/task_2859_raw_gemini_38_evidence.json).
  - **Preserved Raw Diagnostics Artifact:** [`artifacts/live_gemini_38_smoke_test_result.json`](file:///artifacts/live_gemini_38_smoke_test_result.json).

### B. Gemini 2.5 Flash Complete Pipeline Verification Evidence
To verify the complete semantic extraction, verbatim citation verification, contradiction detection, and deterministic policy pipeline against a live model without quota throttling, the test was executed with `gemini-2.5-flash`:

```
==============================================================================
 DOCKET — LIVE GEMINI API SMOKE TEST EXECUTION
==============================================================================
Provider:            Google Gemini REST API
Model:               gemini-2.5-flash
Credential:          Configured (Present)
Timestamp:           2026-11-08T13:10:39.025492+00:00

Executing live API request through SemanticExtractionWorkflow...

==============================================================================
 LIVE API RESPONSE & PIPELINE VERIFICATION RESULTS
==============================================================================

1. Execution Metadata:
   - Provider:             GEMINI
   - Model:                gemini-2.5-flash
   - Live Network Call:    True
   - Latency:              4479.30 ms
   - Usage Metadata:       {
                             "promptTokenCount": 782,
                             "candidatesTokenCount": 346,
                             "thoughtsTokenCount": 436,
                             "totalTokenCount": 1564,
                             "serviceTier": "standard"
                           }

2. Extracted Structured Claims (4 claim(s)):
   Claim #1:
     - ID:                 PP-D-LIVE-2026-MSG-00-1
     - Type:               COMMUNICATION_ACKNOWLEDGED
     - Assertion:          Buyer reports that the tracking page states the package was delivered yesterday.
     - Status:             PROPOSED
     - Sources Cited:      1 (MSG-00)
   Claim #2:
     - ID:                 PP-D-LIVE-2026-MSG-00-2
     - Type:               NON_RECEIPT_ASSERTED
     - Assertion:          Buyer asserts that they never received the package.
     - Status:             PROPOSED
     - Sources Cited:      1 (MSG-00)
   Claim #3:
     - ID:                 PP-D-LIVE-2026-MSG-00-3
     - Type:               COMMUNICATION_ACKNOWLEDGED
     - Assertion:          Buyer asserts that they contacted the courier.
     - Status:             PROPOSED
     - Sources Cited:      1 (MSG-00)
   Claim #4:
     - ID:                 PP-D-LIVE-2026-MSG-00-4
     - Type:               COMMUNICATION_ACKNOWLEDGED
     - Assertion:          Buyer reports that the courier stated the parcel may have been left at another address.
     - Status:             PROPOSED
     - Sources Cited:      1 (MSG-00)

3. Verbatim Citation Verification:
   Citation #1:
     - Source ID:          MSG-00 (CUSTOMER_COMMUNICATION)
     - Cited Excerpt:      "The tracking page says my package was delivered yesterday"
     - Verification:       PASS (VERIFIED)
     - Field Path:         content
     - Character Offsets:  [0:57]
   Citation #2:
     - Source ID:          MSG-00 (CUSTOMER_COMMUNICATION)
     - Cited Excerpt:      "I never received it."
     - Verification:       PASS (VERIFIED)
     - Field Path:         content
     - Character Offsets:  [63:83]
   Citation #3:
     - Source ID:          MSG-00 (CUSTOMER_COMMUNICATION)
     - Cited Excerpt:      "I contacted the courier"
     - Verification:       PASS (VERIFIED)
     - Field Path:         content
     - Character Offsets:  [84:107]
   Citation #4:
     - Source ID:          MSG-00 (CUSTOMER_COMMUNICATION)
     - Cited Excerpt:      "they told me the parcel may have been left at another address."
     - Verification:       PASS (VERIFIED)
     - Field Path:         content
     - Character Offsets:  [113:175]

4. Cross-Source Contradictions (1 finding(s)):
   - [HIGH] DELIVERY_STATUS_DISCREPANCY: Delivery discrepancy: Buyer asserts non-delivery, but carrier USPS tracking 9400111899223197428490 shows package was DELIVERED.

5. Deterministic PolicyEngine Evaluation:
   - Overall Decision:     REVIEW
   - Factual Readiness:    REVIEW
   - Action Readiness:     ALLOW
   - Invariant Violations: ['HEARSAY_MISDELIVERY_ALLEGATION']
   - Summary:              Policy checks require merchant review or additional evidence before proceeding.
   - Recommended Action:   Contact carrier to request GPS delivery scan coordinates and delivery confirmation before submitting rebuttal.

Execution evidence saved to: artifacts\live_gemini_smoke_test_result.json
==============================================================================
```

---

## 4. Phase 3 — ContradictionCode Normalization & Claim Taxonomy Audit

### ContradictionCode Normalization & Compatibility
A carrier `DELIVERED` scan alongside a buyer non-receipt statement represents an empirical **delivery discrepancy**, not a strict logical impossibility.

Docket adopts `DELIVERY_STATUS_DISCREPANCY` as the canonical code and provides robust compatibility:
1. **Explicit Normalization Function:** `normalize_contradiction_code(code: str) -> str` maps `DELIVERY_DISPUTE_EVIDENCE_EXISTS` to `DELIVERY_STATUS_DISCREPANCY`.
2. **Standard Construction Normalization:** `ContradictionCode(str)` normalizes on instantiation in `__new__`. It avoids custom string equality hacks that break transitivity and hash consistency.
3. **Compatibility Guarantees (Verified by 5 dedicated tests in `test_milestone4_audit.py`):**
   - New code input produces canonical string.
   - Legacy code input produces canonical string.
   - Symmetric equality in both directions (`code == "DELIVERY_STATUS_DISCREPANCY"` and `"DELIVERY_STATUS_DISCREPANCY" == code`).
   - Stable hashability: `hash(code_new) == hash(code_legacy) == hash("DELIVERY_STATUS_DISCREPANCY")`.
   - Native set membership (`legacy_code in {new_code}`) and dictionary key lookups.
   - JSON serialization outputs `"DELIVERY_STATUS_DISCREPANCY"`; deserializing legacy JSON normalizes at boundary via `ContradictionFinding` validator.

### Claim Taxonomy Detail
- **Claim #1 (`COMMUNICATION_ACKNOWLEDGED`):** *"Buyer reports that the tracking page states the package was delivered yesterday."* (Buyer reporting tracking status)
- **Claim #2 (`NON_RECEIPT_ASSERTED`):** *"Buyer asserts that they never received the package."* (Direct buyer assertion of non-receipt; feeds directly into `DELIVERY_STATUS_DISCREPANCY`)
- **Claim #3 (`COMMUNICATION_ACKNOWLEDGED`):** *"Buyer asserts that they contacted the courier."* (Buyer reporting an inquiry attempt)
- **Claim #4 (`COMMUNICATION_ACKNOWLEDGED`):** *"Buyer reports that the courier stated the parcel may have been left at another address."* (Buyer hearsay; activates `HEARSAY_MISDELIVERY_ALLEGATION` invariant)

### Epistemic Hearsay Safeguards
Buyer-reported courier statements are strictly categorized under `CUSTOMER_COMMUNICATION` with `COMMUNICATION_ACKNOWLEDGED`. Docket's deterministic policy engine enforces that:
1. `COMMUNICATION_ACKNOWLEDGED` claims never satisfy physical delivery requirements under `DeliveryProofInvariant`.
2. Verbal courier hearsay reported by a buyer triggers `HEARSAY_MISDELIVERY_ALLEGATION` (requiring merchant review of GPS coordinates), but is never promoted to independent carrier evidence (`CARRIER_CONFIRMED_MISDELIVERY`), which requires an official carrier tracking exception record.

---

## 5. Phase 4 — Policy Engine Review & The Five Evidential Cases

Docket establishes clear distinctions across all five scenarios:

```mermaid
flowchart TD
    Start["Dispute Evidence Evaluation"] --> CheckCarrier{"Carrier Tracking Status?"}
    
    CheckCarrier -->|"LABEL_CREATED / IN_TRANSIT"| CaseE["Case E: Delivery Not Completed<br><b>Decision: BLOCK</b><br>(LABEL_CREATED / IN_TRANSIT)"]
    
    CheckCarrier -->|"DELIVERED"| CheckAddress{"Destination Address Verified?"}
    
    CheckAddress -->|"No (Missing Data)"| CaseB["Case B: Incomplete Address Proof<br><b>Decision: REVIEW</b><br>(CARRIER_ADDRESS_MISSING)"]
    
    CheckAddress -->|"Yes (Postal Code Matched)"| CheckCarrierMisdelivery{"Official Carrier Confirms Misdelivery?"}
    
    CheckCarrierMisdelivery -->|"Yes (Carrier Exception / Return)"| CaseC["Case C: Official Misdelivery<br><b>Decision: BLOCK</b><br>(CARRIER_CONFIRMED_MISDELIVERY)"]
    
    CheckCarrierMisdelivery -->|"No"| CheckBuyerHearsay{"Buyer Alleges Courier Misdelivery?"}
    
    CheckBuyerHearsay -->|"Yes (Verbal Courier Hearsay)"| CaseD["Case D: Unverified Misdelivery Allegation<br><b>Decision: REVIEW</b><br>(HEARSAY_MISDELIVERY_ALLEGATION)"]
    
    CheckBuyerHearsay -->|"No (Buyer Merely Disputes Receipt)"| CaseA["Case A: Verified Delivery vs INR<br><b>Decision: ALLOW</b><br>(Compliant Evidence Submission)"]
```

#### Case A: Carrier DELIVERED, matching destination postal code, buyer disputes receipt
- **Facts:** Carrier tracking confirms DELIVERED with valid timestamp to destination postal code `95113`. Buyer message states: *"I never received it."*
- **Policy Decision:** **`ALLOW`** (Action Readiness: `ALLOW`; Factual Readiness: `ALLOW`)
- **Authoritative Source & Version:** `RULE_DELIVERY_DISCREPANCY` (v2026.1), linked to *PayPal Seller Protection Policy — Disputed Delivery & Hearsay Reconciliation (US / Global)*.
- **Five Evidential Distinctions & Scope Disclaimer:**
  1. *Carrier Delivered Status:* Verified `DELIVERED` scan present in official carrier tracking record.
  2. *Delivery Date & Verifiable Tracking:* Valid delivery timestamp and online verifiable tracking number established.
  3. *Destination Delivery Area:* Carrier delivery scan destination postal code and country correspond to the order shipping address.
  4. *Recipient Dropoff Scope Limitation:* Confirms destination delivery area correspondence only. Does NOT establish street-level recipient delivery confirmation (e.g. GPS dropoff coordinates or recipient signature).
  5. *Seller Protection Limitations:* Postal-code/country correspondence satisfies INR documentary submission requirements, but does NOT establish complete PayPal Seller Protection eligibility (which additionally depends on account standing, item eligibility, transaction type, chargeback channel, and non-tampering conditions outside local evidence scope). Does NOT guarantee dispute success.
- **Recommended Action:** *"Evidence package satisfies destination area delivery check. Final rebuttal submission requires affirmative merchant authorization."*

#### Case B: Carrier DELIVERED, but destination address cannot be verified
- **Facts:** Carrier tracking status is DELIVERED, but carrier scan lacks destination city/postal code.
- **Policy Decision:** **`REVIEW`**
- **Rationale:** `AddressMatchInvariant` flags `CARRIER_ADDRESS_MISSING`. Docket refuses to assume delivery to the correct destination without proof.

#### Case C: Carrier DELIVERED, while independently recorded carrier source confirms misdelivery
- **Facts:** Official carrier tracking record or exception log indicates delivery exception, return to sender, or misdelivery to wrong zip code.
- **Policy Decision:** **`BLOCK`**
- **Rationale:** `DeliveryDiscrepancyInvariant` flags `CARRIER_CONFIRMED_MISDELIVERY`. Merchant cannot assert completed delivery when official carrier records refute it.

#### Case D: Buyer merely reports that courier verbally mentioned misdelivery (No carrier record)
- **Facts:** Carrier tracking confirms DELIVERED to matching postal code `95113`. Buyer message reports: *"I contacted the courier, and they told me the parcel may have been left at another address."*
- **Policy Decision:** **`REVIEW`**
- **Rationale:** Docket does not treat a carrier delivery scan as infallible proof of delivery. However, Docket does not hard-block evidence submission based on unverified buyer hearsay. The legitimate factual discrepancy requires merchant review and carrier GPS delivery scan investigation. Recommended action: *"Contact carrier to request GPS delivery scan coordinates and delivery confirmation before submitting rebuttal."*

#### Case E: Carrier tracking is LABEL_CREATED or IN_TRANSIT
- **Facts:** Tracking status is `LABEL_CREATED` or `IN_TRANSIT`, but delivery is asserted.
- **Policy Decision:** **`BLOCK`**
- **Rationale:** Strict `DeliveryProofInvariant` violation (`LABEL_CREATED`). Physical delivery has not occurred.

---

## 6. Phase 5 — UI Decision Presentation & Approval Gate Architecture

To ensure operational safety, the Docket user interface explicitly decouples three orthogonal dimensions:

1. **Factual Readiness (`ALLOW` | `REVIEW` | `BLOCK`):** Has all required evidence been cross-validated, citations verified, and discrepancies resolved?
2. **Action Eligibility (`ALLOW` | `REVIEW` | `BLOCK`):** Does the current dispute lifecycle state in PayPal permit merchant response?
3. **Merchant Recommendation (`AUTHORIZE` | `INVESTIGATE` | `HOLD / REFUND`):** What specific operational directive is recommended to the human operator?

### Safety Guardrail: Gated Execution on Tri-Partite State
Under Case D, PayPal action eligibility is `ALLOW` (the dispute is open and awaiting seller evidence), but factual readiness is `REVIEW` (due to courier hearsay).
- **Presentation Invariant:** The UI displays **`REVIEW REQUIRED`** in amber, shows a dedicated alert explaining that factual review is outstanding, displays the specific directive (*"Contact carrier to request GPS delivery scan coordinates and delivery confirmation before submitting rebuttal"*), and locks the submission approval gate.
- **Backend Refusal Barrier:** `OverallPolicyEvaluation.is_ready_for_submission()` returns `False`. If dispatch is attempted, `EvidenceDispatcher` raises `SubmissionBlockedError`. Zero PayPal API mutations are performed.

---

## 7. Phase 6 — Cryptographic Ledger Implementation Audit (SQLite Reality Check)

Docket's audit ledger implementation was inspected against architectural requirements:

| Dimension | Audit Finding & Verification | Technical Reality |
|---|---|---|
| **Underlying Database** | SQLite is **NOT** used | Append-only JSONL file at `artifacts/audit_trail.jsonl` |
| **Storage Location** | Configurable, defaults to `artifacts/audit_trail.jsonl` | Local file storage with immediate filesystem flush |
| **Schema & Models** | Pydantic model `AuditEvent` (`docket/models/audit.py`) | Fields: `event_id`, `parent_hash`, `event_hash`, `event_type`, `timestamp`, `dispute_id`, `actor`, `payload` |
| **Transactional Atomicity** | Single-line append with OS flush (`with open(..., "a")`) | Relies on POSIX/Windows append atomicity; no ACID relational transaction manager |
| **Persistence Across Restarts** | **VERIFIED** | `_load_existing_events()` parses and validates existing chain on startup |
| **Tamper Detection** | **VERIFIED** | Cryptographic SHA-256 hash chaining detects altered payloads, deleted records, and reordered lines |
| **Immutability Classification** | **Tamper-Evident**, not physically immutable | Chaining provides verifiable mathematical proof of tampering; not write-once-read-many (WORM) hardware |

---

## 8. Phase 7 — Regression & Build Verification

### 1. Pytest Test Suite
```bash
python -m pytest
```
```
============================= test session starts =============================
platform win32 -- Python 3.14.8, pytest-8.4.2, pluggy-1.6.0
rootdir: C:\Users\ACER\Downloads\Docket
configfile: pytest.ini
testpaths: tests
collected 263 items

tests\test_ai_extractor.py ................................              [ 12%]
tests\test_ai_live_workflow.py ...........                               [ 16%]
tests\test_api_endpoints.py ............                                 [ 21%]
tests\test_dispatch_and_audit.py ..........................              [ 31%]
tests\test_eval_suite.py ............                                    [ 35%]
tests\test_milestone4_audit.py ...................                       [ 42%]
tests\test_paypal_dispute.py ........................................... [ 58%]
........                                                                 [ 61%]
tests\test_policy_engine.py ............................................ [ 78%]
.............................                                            [ 89%]
tests\test_reconciliation.py ...........................                 [100%]

============================= 263 passed in 2.80s =============================
```

### 2. Frontend Production Build
```bash
npm --prefix frontend run build
```
```
✓ 2059 modules transformed.
dist/index.html                     0.45 kB │ gzip:   0.29 kB
dist/assets/index-DohP2Fai.css     22.89 kB │ gzip:   4.51 kB
dist/assets/index-CKlXoZ97.js   1,491.41 kB │ gzip: 413.82 kB
✓ built in 1.87s
```

### 3. Safety Guardrails & Secrets Protection
- **Default Application Mode:** `DOCKET_AI_MODE=offline` preserved as default in `.env` and `docket/ai/factory.py`.
- **Zero Credential Exposure:** `GEMINI_API_KEY` masked in all outputs; logging reports presence only (`Configured (Present)`).
- **Human Merchant Gate:** Final dispute dispatch strictly requires affirmative HMAC-signed merchant approval; 0 autonomous PayPal API mutations.
- **Benchmark Suite Isolation:** 20-scenario golden benchmark remains 100% offline and deterministic.

---

## 9. Completed Checks, Failed Checks & Remaining Limitations

### Completed Checks
- [x] Gemini REST adapter upgraded to support `streamGenerateContent`, dynamic candidate chunk assembly, and `thoughtsTokenCount`.
- [x] Verified configuration loading of `GEMINI_MODEL=gemini-3.8-flash` and request URL targeting Google's live endpoint.
- [x] Preserved raw execution evidence for Gemini 3.8 historical call in `artifacts/task_2859_raw_gemini_38_evidence.json`.
- [x] Verified live end-to-end extraction and deterministic policy workflow with `gemini-2.5-flash` in `artifacts/live_gemini_smoke_test_result.json`.
- [x] Resolved custom string equality issues: implemented canonical code `DELIVERY_STATUS_DISCREPANCY` with symmetric equality, hash consistency, set/dict compatibility, and JSON serialization.
- [x] Verified epistemic boundaries: buyer hearsay statements cannot be promoted to independently verified carrier evidence.
- [x] Clarified Case A PayPal policy scope: explicitly separated delivery area postal correspondence from street-level recipient delivery and full Seller Protection eligibility.
- [x] Audited audit ledger: verified append-only JSONL cryptographic hash-chaining and corrected SQLite misconceptions.
- [x] Verified tri-partite decision model: Factual Readiness `REVIEW` + Action Eligibility `ALLOW` locks evidence dispatch and displays `REVIEW REQUIRED` with directive.
- [x] Full regression test suite passing (263/263 passed in 2.80s); frontend production build clean.

### Failed Checks
- [ ] **Gemini 3.8 Real-Time Extraction Execution:** Real-time API extraction with `gemini-3.8-flash` currently fails with HTTP 429 (`RESOURCE_EXHAUSTED` / `GenerateRequestsPerDayPerProjectPerModel-FreeTier` limit: 20 RPD on Google AI Studio Free Tier).

### Remaining Limitations
1. **Free-Tier Model Rate Limits:** Live extraction with Gemini 3.8 requires a billing account attached in Google AI Studio or waiting for the 24-hour Free Tier quota reset window.
2. **Local Delivery Confidence Ceiling:** Local delivery verification confirms postal code and country destination area correspondence; street-level dropoff validation requires external carrier GPS coordinates.
3. **No Autonomous Dispatch:** Docket operates strictly as a human-in-the-loop decision-support system; merchant approval remains mandatory before any PayPal dispute evidence submission.

