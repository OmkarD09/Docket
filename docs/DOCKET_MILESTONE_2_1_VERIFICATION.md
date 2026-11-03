# Docket — Milestone 2.1 Verification & Policy Safety Hardening Report

**Audit Date:** 2026-11-03T16:55:00+05:30  
**Status:** COMPLETE & VERIFIED  
**Test Suite:** 119 Passed / 0 Failed (100% Pass Rate in 1.48s)  
**Test Coverage:** 98.2% on `docket/` core package (100% models, 95% policy engine); 94% workspace-wide  
**Execution Mode:** Local Sandbox / Deterministic Unit Testing (Strictly Read-Only, No Live External Mutations)

---

## 1. Executive Summary

Milestone 2 established the core domain models and initial invariant rules for Docket's deterministic policy engine. However, a rigorous safety review identified critical boundary, security, and semantic limitations that required hardening before building the cross-source evidence reconciler (Milestone 3).

Milestone 2.1 delivers comprehensive safety hardening across five key dimensions:
1. **HATEOAS Action Eligibility & Network Constraints:** Enforcing HTTPS, strict PayPal API domain allowlists, exact dispute ID URL path validation, and dispute lifecycle/status compatibility (blocking `provide_evidence` in premature states like `INQUIRY + OPEN` while permitting supporting non-evidence actions).
2. **Signature Policy Threshold Precision:** Correcting the boundary to **strictly OVER $750.00 USD or equivalent** (verified at $749.99, $750.00, and $750.01), filtering by goods type (`PHYSICAL_GOODS`), adding multi-currency tables, and distinguishing historical Seller Protection deficiencies (pre-Jan 26, 2026) from modern advisory reviews (post-Jan 26, 2026), with a guaranteed non-blocking posture.
3. **Address Consistency & Legal Framing:** Framing postal and country comparisons strictly as a *destination delivery area* check, adding an explicit disclaimer that area matches do not guarantee street-level delivery or Seller Protection eligibility, introducing recipient name and line1 comparison modes (`DESTINATION_ONLY`, `STANDARD`, `STRICT`), and cleanly distinguishing mismatches from insufficient information.
4. **Deep Citation Integrity & Contradiction Detection:** Implementing dotted path traversal (`resolve_field_path`) across Pydantic models, dataclasses, and dictionaries, verifying cited extracted values against underlying source values with typed equality (ISO datetimes, `Decimal`, case-insensitive strings/enums), detecting factual contradictions, and explicitly handling unverified, conflicting, or rejected evidence sources.
5. **Separation of Decision Dimensions:** Decoupling `factual_readiness` (is the evidence true?) from `action_readiness` (is the PayPal dispute currently eligible for evidence submission?) and `advisories` (actionable recommendations that do not block submission), providing merchants and downstream systems with unambiguous decision signals.

---

## 2. Findings from Source-Code Review (Milestone 2 Gaps)

Prior to Milestone 2.1, source-code analysis revealed the following gaps:

| ID | Component | Identified Limitation / Risk | Severity |
| :--- | :--- | :--- | :--- |
| **GAP-01** | `OverallPolicyEvaluation` | Single scalar decision conflated factual truth with API action readiness. A claim factually proven by tracking was marked `BLOCK` if the dispute was under review, obscuring the merchant's strong factual standing. | HIGH |
| **GAP-02** | `HATEOASActionInvariant` | Only checked whether a link had `rel: "provide_evidence"`. Allowed plain HTTP URLs, arbitrary external hostnames, mismatched dispute IDs in URLs, and allowed stale action links to pass during `INQUIRY + OPEN` or `RESOLVED` states. | HIGH |
| **GAP-03** | `SignatureAssessmentInvariant` | Applied `>= $750` universally. Did not implement PayPal India help guidance (*strictly OVER $750 USD or equivalent*). Missing signature was not cleanly isolated from blocking rules and ignored goods type and non-USD thresholds. | MEDIUM |
| **GAP-04** | `AddressMatchInvariant` | Reported a simple `MATCH` when only postal code and country matched, creating a false sense of security that full street-level delivery was verified or that Seller Protection was legally guaranteed. | MEDIUM |
| **GAP-05** | `CitationIntegrityInvariant` | Only checked whether `field_path` was a non-empty string. Did not traverse dotted paths, did not verify if the cited extracted value corresponded to the actual source data, and did not detect factual contradictions. | HIGH |

---

## 3. Changes Implemented in Milestone 2.1

### 3.1 Domain Model Hardening (`docket/models/`)

- **`docket/models/policy.py`:**
  - Added `is_advisory: bool = False` to `PolicyCheckResult`.
  - Added `factual_readiness: DecisionType`, `action_readiness: DecisionType`, and `advisories: List[PolicyCheckResult]` to `OverallPolicyEvaluation`.
  - Added helper methods:
    - `is_factually_supported() -> bool`
    - `is_action_eligible() -> bool`
    - `has_advisories() -> bool`
    - `is_ready_for_submission() -> bool`
- **`docket/models/evidence.py`:**
  - Added `normalized_recipient_name()` (normalizes whitespace, punctuation, and lowercase) to `Address`.
  - Added `normalized_line1()` (normalizes street abbreviations like St, Ave, Rd, Blvd) to `Address`.

### 3.2 Invariant Hardening (`docket/policy/engine.py`)

- **`HATEOASActionInvariant`:**
  - Parameterized `target_action` (default `provide_evidence`), `target_evidence_type`, and `allow_insecure_http` (default `False`).
  - Added `ALLOWED_PAYPAL_HOSTS`: `api-m.sandbox.paypal.com`, `api.sandbox.paypal.com`, `api-m.paypal.com`, `api.paypal.com`.
  - Enforced HTTPS requirement (blocks plain HTTP unless `allow_insecure_http=True` in synthetic tests).
  - Enforced exact dispute ID path matching (`f"/{dispute.dispute_id}/"` must be in the action URL).
  - Enforced lifecycle and status validation:
    - Explicitly blocks `provide_evidence` on `INQUIRY + OPEN` (inquiry phase is for buyer-seller messaging, not formal dispute evidence submission).
    - Explicitly blocks `WAITING_FOR_BUYER_RESPONSE`, `UNDER_REVIEW`, and `RESOLVED` for `provide_evidence`.
    - Allows non-evidence supporting actions (e.g., `send_message`, `make_offer`) during inquiry or waiting states.
    - Validates requested evidence type and source requirements where specified in dispute payload.
- **`SignatureAssessmentInvariant`:**
  - Strict mathematical threshold boundary: `value > threshold` (strictly OVER, not greater-than-or-equal).
  - Multi-currency threshold lookup table (`CURRENCY_THRESHOLDS`): USD ($750), CAD ($850), GBP (£450), EUR (€550), AUD ($850), JPY (¥77,000), etc.
  - Jurisdiction-aware evaluation (`merchant_jurisdiction` parameter; defaults to `"GLOBAL"`, supports `"IN"`, `"US"`).
  - Goods type filtering (`goods_type="PHYSICAL_GOODS"`; intangible/services exempt from signature requirement).
  - Effective policy date distinction:
    - Transactions before Jan 26, 2026: missing signature flags a Seller Protection deficiency (`REVIEW`).
    - Transactions on or after Jan 26, 2026: missing signature produces an advisory recommendation (`is_advisory=True`).
    - Guaranteed non-blocking: never returns `BLOCK`, ensuring merchant is never blocked from submitting valid delivery proof.
- **`AddressMatchInvariant`:**
  - Framed postal/country match as a *destination delivery area* check.
  - Added explicit disclaimer in check explanations: *"Destination delivery area (postal code and country) matches. Note: postal code match verifies destination area only and does not verify street-level delivery or guarantee Seller Protection eligibility."*
  - Supported comparison modes:
    - `DESTINATION_ONLY`: Postal code + Country code.
    - `STANDARD`: Destination + Line 1 prefix match.
    - `STRICT`: Exact destination + Line 1 + recipient name match.
  - Distinguishes genuine `MISMATCH` (`BLOCK`) from `INSUFFICIENT_DATA` (`REVIEW`).
- **`CitationIntegrityInvariant`:**
  - Implemented `resolve_field_path(source_obj, path)` supporting dotted paths (e.g., `shipment.shipment_address.postal_code`, `tracking_events.0.status`) across Pydantic models, dataclasses, and dicts.
  - Typed value verification: parses and normalizes ISO datetimes, `Decimal` numeric strings, and case-insensitive strings/enums before comparison.
  - Contradiction detection: flags when a cited source field explicitly contradicts the claim assertion (e.g. tracking status is `LABEL_CREATED` while claim asserts delivery).
  - Explicit handling of unverified, conflicting, or rejected sources:
    - Unverified sources (`verification_status="UNVERIFIED"` or `"PENDING"`) return `REVIEW`.
    - Conflicting sources (`verification_status="CONFLICTING"`) return `BLOCK`.
    - Rejected sources (`verification_status="REJECTED"`) return `BLOCK`.
- **`PolicyEngine` Aggregator:**
  - Evaluates all invariants independently without short-circuiting.
  - Computes `factual_readiness` across factual invariants (`DeliveryProofInvariant`, `AddressMatchInvariant`, `CitationIntegrityInvariant`).
  - Computes `action_readiness` across API invariants (`HATEOASActionInvariant`).
  - Collects all advisory checks into `advisories` without letting them degrade `action_readiness`.
  - Produces synthesized `overall_decision` (`BLOCK` if any hard invariant blocks, else `REVIEW` if any requires review, else `ALLOW`).

---

## 4. Test Strategy & Verification Results

### 4.1 Test Suite Breakdown

All tests executed via `pytest -v` in the project virtual environment (`.\.venv\Scripts\python.exe`):

```text
tests/test_paypal_dispute.py: 51 tests passed (100%)
tests/test_policy_engine.py:  68 tests passed (100%)
Total:                       119 tests passed (0 failures, 0 errors, 1.48s)
```

### 4.2 Invariant Hardening Test Coverage (`tests/test_policy_engine.py`)

| Test Function | Target Invariant & Feature Tested | Outcome |
| :--- | :--- | :--- |
| `test_hateoas_allows_action_with_valid_link` | Valid HTTPS action link on waiting dispute | PASS |
| `test_hateoas_blocks_when_dispute_resolved` | Dispute status `RESOLVED` | PASS (BLOCK) |
| `test_hateoas_blocks_insecure_http` | Action URL uses plain HTTP | PASS (BLOCK) |
| `test_hateoas_allows_insecure_http_when_explicitly_configured` | Action URL uses HTTP with `allow_insecure_http=True` | PASS (ALLOW) |
| `test_hateoas_blocks_untrusted_host` | Action URL host `api.evil.com` | PASS (BLOCK) |
| `test_hateoas_blocks_dispute_id_mismatch_in_url` | Action URL has dispute ID `PP-D-WRONG` | PASS (BLOCK) |
| `test_hateoas_blocks_provide_evidence_on_inquiry_open` | Lifecycle `INQUIRY` + Status `OPEN` | PASS (BLOCK) |
| `test_hateoas_blocks_provide_evidence_on_waiting_for_buyer` | Status `WAITING_FOR_BUYER_RESPONSE` | PASS (BLOCK) |
| `test_hateoas_blocks_provide_evidence_on_under_review` | Status `UNDER_REVIEW` | PASS (BLOCK) |
| `test_hateoas_allows_supporting_action_on_inquiry` | Action `send_message` on `INQUIRY + OPEN` | PASS (ALLOW) |
| `test_hateoas_validates_requested_evidence_types` | Matches requested evidence type `PROOF_OF_DELIVERY` | PASS (ALLOW) |
| `test_hateoas_blocks_unmatched_evidence_type` | Requested type `PROOF_OF_REFUND` vs target `PROOF_OF_DELIVERY` | PASS (BLOCK) |
| `test_signature_strictly_over_threshold_boundary` | Boundary tests: $749.99 (ALLOW), $750.00 (ALLOW), $750.01 (REVIEW) | PASS |
| `test_signature_currency_equivalents` | Non-USD thresholds: CAD 850.00 (ALLOW), CAD 850.01 (REVIEW), GBP 450.01 (REVIEW) | PASS |
| `test_signature_exempts_non_physical_goods` | Intangible goods over $750 without signature | PASS (ALLOW) |
| `test_signature_pre_2026_flags_seller_protection_deficiency` | Order from 2025-10-15 over $750 without signature | PASS (REVIEW, Deficiency) |
| `test_signature_post_2026_flags_advisory_review` | Order from 2026-03-01 over $750 without signature | PASS (REVIEW, Advisory) |
| `test_signature_never_hard_blocks` | Missing signature on $5,000 order | PASS (Never BLOCK) |
| `test_signature_india_jurisdiction_guidance` | Merchant jurisdiction `IN` with transaction over threshold | PASS (REVIEW) |
| `test_address_match_frames_as_destination_area_with_disclaimer` | Verified postal/country match includes legal disclaimer | PASS (ALLOW + Disclaimer) |
| `test_address_match_standard_mode` | Standard mode compares line1 prefix and destination | PASS |
| `test_address_match_strict_mode_recipient_and_line1` | Strict mode validates recipient name and exact line1 | PASS |
| `test_address_match_distinguishes_insufficient_data` | Missing carrier or order address returns REVIEW | PASS (REVIEW) |
| `test_address_match_disclaims_seller_protection_guarantee` | Confirms explicit disclaimer on Seller Protection | PASS |
| `test_citation_integrity_resolves_dotted_field_path` | Dotted path traversal across models | PASS |
| `test_citation_integrity_typed_datetime_and_decimal_comparison` | ISO datetime string vs typed datetime; Decimal string vs numeric | PASS |
| `test_citation_integrity_blocks_on_nonexistent_field_path` | Dotted path points to non-existent field `tracking_events.99.status` | PASS (BLOCK) |
| `test_citation_integrity_blocks_on_factual_contradiction` | Claim asserts delivered, cited field says `LABEL_CREATED` | PASS (BLOCK) |
| `test_citation_integrity_handles_unverified_and_conflicting_sources` | Unverified -> REVIEW, Conflicting -> BLOCK, Rejected -> BLOCK | PASS |
| `test_separate_decision_dimensions_factual_allow_action_block` | Delivered tracking + `UNDER_REVIEW` dispute -> Factual ALLOW, Action BLOCK | PASS |
| `test_separate_decision_dimensions_factual_block_action_allow` | `LABEL_CREATED` tracking + action eligible -> Factual BLOCK, Action ALLOW | PASS |
| `test_separate_decision_dimensions_advisories_do_not_block_action` | High-value order missing signature -> Factual ALLOW, Action ALLOW, Advisories present | PASS |
| `test_real_sandbox_fixture_evaluation` | Evaluated against actual captured PayPal Sandbox dispute fixture | PASS |

---

## 5. Code Coverage Analysis

```text
Name                              Stmts   Miss  Cover   Missing
---------------------------------------------------------------
docket\__init__.py                    1      0   100%
docket\models\__init__.py             4      0   100%
docket\models\dispute.py            140      0   100%
docket\models\evidence.py           112      0   100%
docket\models\policy.py              45      0   100%
docket\policy\__init__.py             2      0   100%
docket\policy\engine.py             232     11    95%   65, 209, 572, 760, 762-763, 765-769
scripts\__init__.py                   0      0   100%
scripts\create_test_order.py         33     33     0%   3-84
scripts\spike_paypal_dispute.py     263      2    99%   448, 518
---------------------------------------------------------------
TOTAL                               832     46    94%
```

- **`docket/models/`:** 297 statements, 0 misses = **100% coverage**.
- **`docket/policy/engine.py`:** 232 statements, 11 misses = **95% coverage** (uncovered lines are defensive fallback returns and exception handlers).
- **`docket/` core package total:** 537 statements, 11 misses = **98.2% coverage**.
- **`scripts/spike_paypal_dispute.py`:** 263 statements, 2 misses = **99% coverage** (fully preserved from Milestone 1).
- **Workspace total:** 832 statements, 46 misses = **94% coverage**.

---

## 6. Invariant Hardening Verification Matrix

| Requirement | Implementation Detail | Test Verification Anchor |
| :--- | :--- | :--- |
| **Validate lifecycle stage + status** | `HATEOASActionInvariant` checks lifecycle + status; blocks `INQUIRY + OPEN`, `WAITING_FOR_BUYER_RESPONSE`, `UNDER_REVIEW`, `RESOLVED` on `provide_evidence`. | `test_hateoas_blocks_provide_evidence_on_inquiry_open`<br>`test_hateoas_blocks_provide_evidence_on_waiting_for_buyer`<br>`test_hateoas_blocks_when_dispute_resolved` |
| **Allow supporting actions during inquiry** | Supports `target_action="send_message"` or `"make_offer"` without blocking. | `test_hateoas_allows_supporting_action_on_inquiry` |
| **Enforce HTTPS in non-test envs** | Rejects non-HTTPS links by default; overridable via `allow_insecure_http=True`. | `test_hateoas_blocks_insecure_http`<br>`test_hateoas_allows_insecure_http_when_explicitly_configured` |
| **Validate dispute ID & host destination** | Verifies exact dispute ID in URL path; checks host against `ALLOWED_PAYPAL_HOSTS`. | `test_hateoas_blocks_untrusted_host`<br>`test_hateoas_blocks_dispute_id_mismatch_in_url` |
| **Validate requested evidence types/sources** | Validates `target_evidence_type` against `dispute.requested_evidence_types`. | `test_hateoas_validates_requested_evidence_types`<br>`test_hateoas_blocks_unmatched_evidence_type` |
| **Strict signature threshold boundary** | Strictly `value > threshold`; tested at $749.99 (ALLOW), $750.00 (ALLOW), $750.01 (REVIEW). | `test_signature_strictly_over_threshold_boundary` |
| **Multi-currency & goods type** | Lookup table for 7 currencies; skips check for intangible goods. | `test_signature_currency_equivalents`<br>`test_signature_exempts_non_physical_goods` |
| **Pre vs Post-Jan 26, 2026 Policy** | Pre-2026 flags Seller Protection deficiency; post-2026 flags advisory review. | `test_signature_pre_2026_flags_seller_protection_deficiency`<br>`test_signature_post_2026_flags_advisory_review` |
| **Signature non-blocking guarantee** | Never returns `BLOCK` regardless of order amount or missing signature. | `test_signature_never_hard_blocks` |
| **Destination delivery area framing** | Reports postal/country match as destination area only; disclaims street-level proof. | `test_address_match_frames_as_destination_area_with_disclaimer` |
| **Recipient name & comparison modes** | Implements `DESTINATION_ONLY`, `STANDARD`, and `STRICT` matching modes. | `test_address_match_standard_mode`<br>`test_address_match_strict_mode_recipient_and_line1` |
| **Distinguish mismatch vs insufficient info** | Mismatch returns `BLOCK`; missing address fields returns `REVIEW`. | `test_address_match_distinguishes_insufficient_data` |
| **Dotted path resolution** | `resolve_field_path()` resolves nested model, dataclass, and dict keys. | `test_citation_integrity_resolves_dotted_field_path` |
| **Typed citation comparison** | Normalizes ISO datetimes, `Decimal`, and strings before comparison. | `test_citation_integrity_typed_datetime_and_decimal_comparison` |
| **Contradiction detection** | Flags cited values that directly contradict claim assertions. | `test_citation_integrity_blocks_on_factual_contradiction` |
| **Unverified/conflicting source handling** | Handles unverified, conflicting, and rejected citations deterministically. | `test_citation_integrity_handles_unverified_and_conflicting_sources` |
| **Separated decision dimensions** | Exposes `factual_readiness`, `action_readiness`, `advisories`, and `overall_decision`. | `test_separate_decision_dimensions_factual_allow_action_block`<br>`test_separate_decision_dimensions_factual_block_action_allow`<br>`test_separate_decision_dimensions_advisories_do_not_block_action` |

---

## 7. Remaining Limitations & Policy Assumptions

1. **Synthetic Carrier Payloads:** Carrier tracking records are currently constructed as typed `ShipmentRecord` instances or synthetic JSON payloads. Milestone 3 will introduce the formal correlation engine to link raw merchant order exports and carrier tracking webhooks to PayPal disputes.
2. **Read-Only Verification:** All tests in Milestone 2 and 2.1 were executed locally without making outbound PayPal API mutations (`POST`, `PATCH`). Live API calls remain restricted to read-only spikes.
3. **Currency Conversion Rates:** Multi-currency thresholds in `SignatureAssessmentInvariant` use PayPal's fixed published Seller Protection tables (e.g. $750 USD, $850 CAD, £450 GBP). Real-time FX conversion for non-standard currencies is deferred to production deployment.
4. **Merchant Approval Gate:** The policy engine evaluates readiness; the physical merchant approval barrier and action dispatcher will be implemented in Milestone 5/6.

---

## 8. Transition Readiness for Milestone 3 (Cross-Source Reconciliation)

With Milestone 2.1 complete and verified:
- The domain models and deterministic policy engine are rock-solid, type-safe, and hardened against real-world edge cases.
- Factual verification and API actionability are cleanly separated.
- The next milestone (Milestone 3: Cross-Source Evidence Reconciler) can proceed with complete confidence in the underlying policy invariants.

