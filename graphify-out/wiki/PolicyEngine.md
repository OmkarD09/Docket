# PolicyEngine

> God node · 59 connections · `docket/policy/engine.py`

**Community:** [Community 10](Community_10.md)

## Connections by Relation

### calls
- run_milestone_6_verification() `EXTRACTED`
- create_app() `EXTRACTED`
- load_initial_cases() `EXTRACTED`
- .run_scenario() `EXTRACTED`
- .test_end_to_end_verified_delivery_ready_for_submission() `EXTRACTED`
- .test_end_to_end_defining_scenario_label_created_blocked() `EXTRACTED`
- .test_factually_supported_claim_retains_allow_when_dispute_state_blocks_action() `EXTRACTED`
- .test_engine_evaluates_against_real_sandbox_fixture() `EXTRACTED`
- .test_action_eligible_dispute_blocks_when_claim_is_unsupported() `EXTRACTED`
- .test_advisories_isolated_from_blocking_decisions() `EXTRACTED`
- .test_e2e_ai_extracted_claim_blocked_by_policy_on_label_created() `EXTRACTED`
- .test_e2e_ai_truthful_label_created_claim_allowed() `EXTRACTED`
- .test_policy_engine_review_summary_branch() `EXTRACTED`
- .test_defining_scenario_inr_label_created_hard_refusal() `EXTRACTED`
- .test_engine_allows_fully_verified_claim() `EXTRACTED`
- .test_engine_collects_all_violations_without_short_circuiting() `EXTRACTED`

### contains
- policy/engine.py `EXTRACTED`

### imports
- test_ai_extractor.py `EXTRACTED`
- app.py `EXTRACTED`
- test_policy_engine.py `EXTRACTED`
- test_reconciliation.py `EXTRACTED`
- verify_dispatch_pipeline.py `EXTRACTED`
- eval/runner.py `EXTRACTED`
- policy/__init__.py `EXTRACTED`

### method
- .evaluate() `EXTRACTED`
- .__init__() `EXTRACTED`

### rationale_for
- Central deterministic policy validation coordinator for Docket. Executes all… `EXTRACTED`

### references
- 1. Project Status Matrix `INFERRED`
- 5. Deterministic Policy & Refusal Barrier (`docket/policy/engine.py` - HARDENED IN MILESTONE 2.1) `INFERRED`
- 6. Synthetic Evaluation Benchmark Suite (`docket/eval/` - IMPLEMENTED & VERIFIED IN MILESTONE 5) `INFERRED`
- ADR-013: Synthetic Evaluation Benchmark Suite and Empirical Refusal Metrics `INFERRED`
- ADR-009: Decoupled Independent Invariants with Multi-Finding Engine Aggregation `INFERRED`
- ADR-012: Pluggable AI Fact Extraction with Prompt Injection Defense and Verbatim Grounding `INFERRED`
- 3.2 Invariant Hardening (`docket/policy/engine.py`) `INFERRED`
- 4. AI Semantic Fact Extractor (`docket/ai/` - IMPLEMENTED & VERIFIED IN MILESTONE 4) `INFERRED`
- Scope of Next Task: `INFERRED`
- 1. Executive Summary `INFERRED`
- 3.2 AI Extractor Test Matrix (\[`tests/test_ai_extractor.py`\](file:///c:/Users/ACER/Downloads/Docket/tests/test_ai_extractor.py)) `INFERRED`
- 5. End-to-End Safety Pipeline Verification `INFERRED`
- 2.2 Benchmark Runner (\[`docket/eval/runner.py`\](file:///c:/Users/ACER/Downloads/Docket/docket/eval/runner.py)) `INFERRED`
- 3. Cross-Source Evidence Reconciler (`docket/reconciliation/` - IMPLEMENTED & VERIFIED IN MILESTONE 3) `INFERRED`
- 1. Executive Summary `INFERRED`
- 5. End-to-End Defining Scenario Verification `INFERRED`
- ADR-003: Deterministic Refusal Barrier Overrides AI Output `INFERRED`
- ADR-011: Multi-Key Evidence Reconciliation with Email Conflict Isolation `INFERRED`
- 3.2 Reconciliation Test Matrix (`tests/test_reconciliation.py`) `INFERRED`

### uses
- [ExtractedClaim](ExtractedClaim.md) `INFERRED`
- [DisputeCase](DisputeCase.md) `INFERRED`
- [OrderRecord](OrderRecord.md) `INFERRED`
- ShipmentRecord `INFERRED`
- DecisionType `INFERRED`
- OverallPolicyEvaluation `INFERRED`
- TestReconcilerPolicyEngineIntegration `INFERRED`
- BenchmarkRunner `INFERRED`
- TestDomainModelsAndEdgeCases `INFERRED`
- TestEndToEndAIPolicyPipeline `INFERRED`
- PolicyCheckResult `INFERRED`
- TestPolicyEngineIntegration `INFERRED`
- TestSeparatedDecisionDimensions `INFERRED`

---

*Part of the graphify knowledge wiki. See [index](index.md) to navigate.*