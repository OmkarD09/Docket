# Money

> God node · 60 connections · `docket/models/dispute.py`

**Community:** [Community 4](Community_4.md)

## Connections by Relation

### calls
- load_all_scenarios() `EXTRACTED`
- run_milestone_6_verification() `EXTRACTED`
- load_initial_cases() `EXTRACTED`
- .from_paypal_response() `EXTRACTED`
- _create_base_dispute() `EXTRACTED`
- .test_advisories_isolated_from_blocking_decisions() `EXTRACTED`
- .test_policy_engine_review_summary_branch() `EXTRACTED`
- .test_refund_overlap_contradiction() `EXTRACTED`
- .test_signature_boundary_749_99_allowed() `EXTRACTED`
- .test_signature_boundary_750_00_allowed() `EXTRACTED`
- .test_signature_boundary_750_01_post_2026_advisory() `EXTRACTED`
- .test_signature_boundary_750_01_pre_2026_review_deficiency() `EXTRACTED`
- .test_signature_goods_type_digital_goods_allowed() `EXTRACTED`
- .test_signature_never_returns_block() `EXTRACTED`
- .test_signature_unmapped_currency_returns_indeterminate_review() `EXTRACTED`
- .test_post_2026_over_750_without_signature_returns_advisory_review() `EXTRACTED`
- .test_post_2026_under_750_allowed() `EXTRACTED`
- .test_pre_2026_over_750_with_signature_allowed() `EXTRACTED`
- .test_pre_2026_over_750_without_signature_returns_review_advisory() `EXTRACTED`
- .test_signature_indeterminate_when_date_missing() `EXTRACTED`
- *…and 6 more `calls` connection(s) not listed (lowest-degree first to go)*

### contains
- dispute.py `EXTRACTED`

### imports
- test_dispatch_and_audit.py `EXTRACTED`
- test_ai_extractor.py `EXTRACTED`
- app.py `EXTRACTED`
- test_policy_engine.py `EXTRACTED`
- test_reconciliation.py `EXTRACTED`
- models/__init__.py `EXTRACTED`
- evidence.py `EXTRACTED`
- scenarios.py `EXTRACTED`
- verify_dispatch_pipeline.py `EXTRACTED`
- reconciliation/engine.py `EXTRACTED`

### inherits
- BaseModel `EXTRACTED`

### method
- .validate_non_negative() `EXTRACTED`
- .validate_currency() `EXTRACTED`

### rationale_for
- Monetary amount with strict Decimal precision and 3-letter currency code. `EXTRACTED`

### references
- ADR-008: Pydantic v2 Core Domain Modeling with Explicit Non-Silent Validation `INFERRED`

### uses
- [OrderRecord](OrderRecord.md) `INFERRED`
- TestReconcilerPolicyEngineIntegration `INFERRED`
- TestDomainModelsAndEdgeCases `INFERRED`
- RefundRecord `INFERRED`
- TestSeparatedDecisionDimensions `INFERRED`
- TestEvidenceReconcilerMatching `INFERRED`
- TestContradictionDetector `INFERRED`
- TestSignatureAssessmentHardening `INFERRED`
- TestEvidenceReconcilerDiscrepancies `INFERRED`
- TestSignatureAssessmentInvariant `INFERRED`
- sample_dispute() `INFERRED`
- sample_dispute() `INFERRED`
- sample_dispute() `INFERRED`
- valid_dispute_case() `INFERRED`
- sample_order() `INFERRED`
- sample_order() `INFERRED`
- sample_order() `INFERRED`
- sample_refund() `INFERRED`

---

*Part of the graphify knowledge wiki. See [index](index.md) to navigate.*