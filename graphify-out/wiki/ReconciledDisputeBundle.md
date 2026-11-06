# ReconciledDisputeBundle

> God node · 65 connections · `docket/models/reconciliation.py`

**Community:** [Community 5](Community_5.md)

## Connections by Relation

### calls
- .test_primary_shipment_priority_order() `EXTRACTED`
- .test_get_primary_shipment_empty_returns_none() `EXTRACTED`

### contains
- reconciliation.py `EXTRACTED`

### imports
- test_dispatch_and_audit.py `EXTRACTED`
- test_ai_extractor.py `EXTRACTED`
- app.py `EXTRACTED`
- test_reconciliation.py `EXTRACTED`
- models/__init__.py `EXTRACTED`
- dispatcher.py `EXTRACTED`
- approval.py `EXTRACTED`
- deterministic.py `EXTRACTED`
- reconciliation/engine.py `EXTRACTED`
- provider_openai.py `EXTRACTED`
- provider_anthropic.py `EXTRACTED`
- provider_gemini.py `EXTRACTED`
- base.py `EXTRACTED`
- contradiction.py `EXTRACTED`

### inherits
- BaseModel `EXTRACTED`

### method
- .to_citations() `EXTRACTED`
- .get_primary_shipment() `EXTRACTED`
- .is_reconciled() `EXTRACTED`
- .is_ambiguous() `EXTRACTED`
- .has_critical_discrepancies() `EXTRACTED`
- .get_tracking_numbers() `EXTRACTED`

### rationale_for
- Unified cross-source evidence bundle for a dispute. `EXTRACTED`

### references
- .reconcile_dispute() `EXTRACTED`
- 1. Project Status Matrix `INFERRED`
- .create_approval_request() `EXTRACTED`
- .dispatch_evidence() `EXTRACTED`
- .extract_from_bundle() `EXTRACTED`
- 2.1 Domain Models (`docket/models/reconciliation.py` & `evidence.py`) `INFERRED`
- .check_contradictions() `EXTRACTED`
- .extract_from_bundle() `EXTRACTED`
- .extract_from_bundle() `EXTRACTED`
- .extract_from_bundle() `EXTRACTED`
- .format_fulfillment_evidence() `EXTRACTED`
- .generate_human_summary() `EXTRACTED`
- .check_bundle_anomalies() `EXTRACTED`
- .reconcile_batch() `EXTRACTED`
- .extract_from_bundle() `EXTRACTED`
- .__init__() `EXTRACTED`
- 3. Cross-Source Evidence Reconciler (`docket/reconciliation/` - IMPLEMENTED & VERIFIED IN MILESTONE 3) `INFERRED`
- 1. Executive Summary `INFERRED`

### uses
- [EvidenceReconciler](EvidenceReconciler.md) `INFERRED`
- [SourceCitation](SourceCitation.md) `INFERRED`
- [DeterministicFactExtractor](DeterministicFactExtractor.md) `INFERRED`
- [ApprovalService](ApprovalService.md) `INFERRED`
- [OrderRecord](OrderRecord.md) `INFERRED`
- SourceType `INFERRED`
- ShipmentRecord `INFERRED`
- TrackingStatus `INFERRED`
- EvidenceDispatcher `INFERRED`
- ContradictionDetector `INFERRED`
- TestReconcilerPolicyEngineIntegration `INFERRED`
- VerificationStatus `INFERRED`
- AnthropicFactExtractor `INFERRED`
- GeminiFactExtractor `INFERRED`
- OpenAIFactExtractor `INFERRED`
- EvidencePayloadFormatter `INFERRED`
- BaseFactExtractor `INFERRED`
- RefundRecord `INFERRED`
- CustomerMessageRecord `INFERRED`
- CaseData `INFERRED`
- *…and 2 more `uses` connection(s) not listed (lowest-degree first to go)*

---

*Part of the graphify knowledge wiki. See [index](index.md) to navigate.*