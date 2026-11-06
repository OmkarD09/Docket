# DisputeCase

> God node · 72 connections · `docket/models/dispute.py`

**Community:** [Community 2](Community_2.md)

## Connections by Relation

### calls
- _create_base_dispute() `EXTRACTED`

### contains
- dispute.py `EXTRACTED`

### imports
- test_dispatch_and_audit.py `EXTRACTED`
- test_ai_extractor.py `EXTRACTED`
- app.py `EXTRACTED`
- test_policy_engine.py `EXTRACTED`
- test_reconciliation.py `EXTRACTED`
- models/__init__.py `EXTRACTED`
- scenarios.py `EXTRACTED`
- policy/engine.py `EXTRACTED`
- dispatcher.py `EXTRACTED`
- verify_dispatch_pipeline.py `EXTRACTED`
- approval.py `EXTRACTED`
- deterministic.py `EXTRACTED`
- models.py `EXTRACTED`
- reconciliation/engine.py `EXTRACTED`
- provider_openai.py `EXTRACTED`
- provider_anthropic.py `EXTRACTED`
- provider_gemini.py `EXTRACTED`
- base.py `EXTRACTED`

### inherits
- BaseModel `EXTRACTED`

### method
- .from_paypal_response() `EXTRACTED`
- .get_action_link() `EXTRACTED`
- .has_action() `EXTRACTED`
- .is_seller_response_required() `EXTRACTED`

### rationale_for
- Core domain model representing a PayPal dispute. `EXTRACTED`

### references
- .reconcile_dispute() `EXTRACTED`
- 1. Project Status Matrix `INFERRED`
- .evaluate() `EXTRACTED`
- .create_approval_request() `EXTRACTED`
- .dispatch_evidence() `EXTRACTED`
- .extract_from_bundle() `EXTRACTED`
- .evaluate() `EXTRACTED`
- .extract_from_bundle() `EXTRACTED`
- .extract_from_bundle() `EXTRACTED`
- .extract_from_bundle() `EXTRACTED`
- .generate_human_summary() `EXTRACTED`
- ._score_secondary_match() `EXTRACTED`
- .reconcile_batch() `EXTRACTED`
- ._evaluate_order_discrepancies() `EXTRACTED`
- ._link_communications() `EXTRACTED`
- ._link_shipments() `EXTRACTED`
- Scope of Next Task: `INFERRED`
- .extract_from_bundle() `EXTRACTED`
- .__init__() `EXTRACTED`
- ._resolve_provide_evidence_url() `EXTRACTED`
- *…and 3 more `references` connection(s) not listed (lowest-degree first to go)*

### uses
- [EvidenceReconciler](EvidenceReconciler.md) `INFERRED`
- [PolicyEngine](PolicyEngine.md) `INFERRED`
- [DeterministicFactExtractor](DeterministicFactExtractor.md) `INFERRED`
- [ApprovalService](ApprovalService.md) `INFERRED`
- HATEOASActionInvariant `INFERRED`
- load_all_scenarios() `INFERRED`
- EvidenceDispatcher `INFERRED`
- run_milestone_6_verification() `INFERRED`
- TestReconcilerPolicyEngineIntegration `INFERRED`
- TestDomainModelsAndEdgeCases `INFERRED`
- AnthropicFactExtractor `INFERRED`
- GeminiFactExtractor `INFERRED`
- OpenAIFactExtractor `INFERRED`
- BaseFactExtractor `INFERRED`
- EvalScenario `INFERRED`
- load_initial_cases() `INFERRED`
- TestPolicyEngineIntegration `INFERRED`
- CaseData `INFERRED`
- sample_dispute() `INFERRED`
- sample_dispute() `INFERRED`
- *…and 3 more `uses` connection(s) not listed (lowest-degree first to go)*

---

*Part of the graphify knowledge wiki. See [index](index.md) to navigate.*