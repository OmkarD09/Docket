# EvidenceReconciler

> God node · 64 connections · `docket/reconciliation/engine.py`

**Community:** [Community 5](Community_5.md)

## Connections by Relation

### calls
- run_milestone_6_verification() `EXTRACTED`
- load_initial_cases() `EXTRACTED`
- .run_scenario() `EXTRACTED`
- .test_end_to_end_verified_delivery_ready_for_submission() `EXTRACTED`
- .test_end_to_end_defining_scenario_label_created_blocked() `EXTRACTED`
- .test_real_sandbox_fixture_reconciliation_and_evaluation() `EXTRACTED`
- .test_currency_mismatch_detected() `EXTRACTED`
- .test_bundle_generates_source_citations() `EXTRACTED`
- .test_address_discrepancy_between_order_and_shipment() `EXTRACTED`
- .test_amount_mismatch_detected() `EXTRACTED`
- .test_ambiguous_matches_multiple_candidates() `EXTRACTED`
- .test_orphan_dispute_unlinked() `EXTRACTED`
- .test_secondary_match_email_amount_time_within_24h() `EXTRACTED`
- .test_multi_shipment_linking_and_primary_selection() `EXTRACTED`
- .test_case_insensitive_email_matching() `EXTRACTED`
- .test_comms_linked_by_customer_email() `EXTRACTED`
- .test_secondary_match_amount_mismatch_detected() `EXTRACTED`
- .test_secondary_match_currency_mismatch_detected() `EXTRACTED`
- .test_tracking_numbers_deduplication() `EXTRACTED`
- .test_timeline_paradox_detected() `EXTRACTED`
- *…and 7 more `calls` connection(s) not listed (lowest-degree first to go)*

### contains
- reconciliation/engine.py `EXTRACTED`

### imports
- app.py `EXTRACTED`
- test_reconciliation.py `EXTRACTED`
- verify_dispatch_pipeline.py `EXTRACTED`
- eval/runner.py `EXTRACTED`
- reconciliation/__init__.py `EXTRACTED`

### method
- .reconcile_dispute() `EXTRACTED`
- ._score_secondary_match() `EXTRACTED`
- .reconcile_batch() `EXTRACTED`
- ._evaluate_order_discrepancies() `EXTRACTED`
- ._link_shipments() `EXTRACTED`
- ._link_communications() `EXTRACTED`
- .__init__() `EXTRACTED`
- ._link_refunds() `EXTRACTED`

### rationale_for
- Multi-source evidence correlation and reconciliation engine. `EXTRACTED`

### references
- 6. Synthetic Evaluation Benchmark Suite (`docket/eval/` - IMPLEMENTED & VERIFIED IN MILESTONE 5) `INFERRED`
- ADR-013: Synthetic Evaluation Benchmark Suite and Empirical Refusal Metrics `INFERRED`
- 2.2 Benchmark Runner (\[`docket/eval/runner.py`\](file:///c:/Users/ACER/Downloads/Docket/docket/eval/runner.py)) `INFERRED`
- 5. End-to-End Defining Scenario Verification `INFERRED`

### uses
- [DisputeCase](DisputeCase.md) `INFERRED`
- [ReconciledDisputeBundle](ReconciledDisputeBundle.md) `INFERRED`
- [OrderRecord](OrderRecord.md) `INFERRED`
- ShipmentRecord `INFERRED`
- TestReconcilerPolicyEngineIntegration `INFERRED`
- BenchmarkRunner `INFERRED`
- RefundRecord `INFERRED`
- ReconciliationStatus `INFERRED`
- CustomerMessageRecord `INFERRED`
- MatchStrategy `INFERRED`
- MatchConfidence `INFERRED`
- CandidateMatch `INFERRED`
- TestEvidenceReconcilerMatching `INFERRED`
- ReconciliationDiscrepancy `INFERRED`
- TestEvidenceReconcilerDiscrepancies `INFERRED`
- DiscrepancySeverity `INFERRED`
- TestEvidenceReconcilerMultiSourceLinking `INFERRED`
- TestAutomatedCitationGeneration `INFERRED`

---

*Part of the graphify knowledge wiki. See [index](index.md) to navigate.*