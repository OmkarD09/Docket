# OrderRecord

> God node · 43 connections · `docket/models/evidence.py`

**Community:** [Community 5](Community_5.md)

## Connections by Relation

### calls
- load_all_scenarios() `EXTRACTED`
- run_milestone_6_verification() `EXTRACTED`
- load_initial_cases() `EXTRACTED`
- .test_real_sandbox_fixture_reconciliation_and_evaluation() `EXTRACTED`

### contains
- evidence.py `EXTRACTED`

### imports
- test_dispatch_and_audit.py `EXTRACTED`
- test_ai_extractor.py `EXTRACTED`
- app.py `EXTRACTED`
- test_policy_engine.py `EXTRACTED`
- test_reconciliation.py `EXTRACTED`
- models/__init__.py `EXTRACTED`
- scenarios.py `EXTRACTED`
- policy/engine.py `EXTRACTED`
- reconciliation.py `EXTRACTED`
- verify_dispatch_pipeline.py `EXTRACTED`
- models.py `EXTRACTED`
- reconciliation/engine.py `EXTRACTED`

### inherits
- BaseModel `EXTRACTED`

### rationale_for
- Internal merchant order details correlated with a PayPal dispute. `EXTRACTED`

### references
- .evaluate() `EXTRACTED`
- .evaluate() `EXTRACTED`
- .evaluate() `EXTRACTED`
- .evaluate() `EXTRACTED`
- ._score_secondary_match() `EXTRACTED`
- ._evaluate_order_discrepancies() `EXTRACTED`
- ._link_communications() `EXTRACTED`
- ._link_shipments() `EXTRACTED`
- .__init__() `EXTRACTED`
- ._link_refunds() `EXTRACTED`

### uses
- [ReconciledDisputeBundle](ReconciledDisputeBundle.md) `INFERRED`
- [EvidenceReconciler](EvidenceReconciler.md) `INFERRED`
- [Money](Money.md) `INFERRED`
- [PolicyEngine](PolicyEngine.md) `INFERRED`
- AddressMatchInvariant `INFERRED`
- DeliveryProofInvariant `INFERRED`
- SignatureAssessmentInvariant `INFERRED`
- TestReconcilerPolicyEngineIntegration `INFERRED`
- EvalScenario `INFERRED`
- CandidateMatch `INFERRED`
- sample_order() `INFERRED`
- sample_order() `INFERRED`
- sample_order() `INFERRED`
- valid_order() `INFERRED`

---

*Part of the graphify knowledge wiki. See [index](index.md) to navigate.*