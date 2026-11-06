# ExtractedClaim

> God node · 92 connections · `docket/models/evidence.py`

**Community:** [Community 0](Community_0.md)

## Connections by Relation

### calls
- load_all_scenarios() `EXTRACTED`
- run_milestone_6_verification() `EXTRACTED`
- load_initial_cases() `EXTRACTED`
- .extract_from_bundle() `EXTRACTED`
- .test_end_to_end_verified_delivery_ready_for_submission() `EXTRACTED`
- .extract_from_bundle() `EXTRACTED`
- .extract_from_bundle() `EXTRACTED`
- .extract_from_bundle() `EXTRACTED`
- .test_end_to_end_defining_scenario_label_created_blocked() `EXTRACTED`
- .test_factually_supported_claim_retains_allow_when_dispute_state_blocks_action() `EXTRACTED`
- .test_engine_evaluates_against_real_sandbox_fixture() `EXTRACTED`
- .test_action_eligible_dispute_blocks_when_claim_is_unsupported() `EXTRACTED`
- .test_advisories_isolated_from_blocking_decisions() `EXTRACTED`
- .test_e2e_ai_extracted_claim_blocked_by_policy_on_label_created() `EXTRACTED`
- .test_e2e_ai_truthful_label_created_claim_allowed() `EXTRACTED`
- .test_policy_engine_review_summary_branch() `EXTRACTED`
- .test_citation_field_path_nested_resolution() `EXTRACTED`
- .test_citation_field_path_nonexistent_blocked() `EXTRACTED`
- .test_citation_rejected_source_blocked() `EXTRACTED`
- .test_citation_unverified_source_triggers_review() `EXTRACTED`
- *…and 20 more `calls` connection(s) not listed (lowest-degree first to go)*

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
- verify_dispatch_pipeline.py `EXTRACTED`
- deterministic.py `EXTRACTED`
- models.py `EXTRACTED`
- eval/runner.py `EXTRACTED`
- provider_openai.py `EXTRACTED`
- provider_anthropic.py `EXTRACTED`
- provider_gemini.py `EXTRACTED`
- base.py `EXTRACTED`
- contradiction.py `EXTRACTED`

### inherits
- BaseModel `EXTRACTED`

### rationale_for
- A structured assertion of fact with supporting citations. `EXTRACTED`

### references
- .evaluate() `EXTRACTED`
- .evaluate() `EXTRACTED`
- .evaluate() `EXTRACTED`
- .check_contradictions() `EXTRACTED`
- .extract_from_text() `EXTRACTED`
- .__init__() `EXTRACTED`
- .extract_from_text() `EXTRACTED`
- .extract_from_text() `EXTRACTED`
- .extract_from_text() `EXTRACTED`
- .extract_from_text() `EXTRACTED`

### uses
- [PolicyEngine](PolicyEngine.md) `INFERRED`
- [DeterministicFactExtractor](DeterministicFactExtractor.md) `INFERRED`
- DeliveryProofInvariant `INFERRED`
- ContradictionDetector `INFERRED`
- TestReconcilerPolicyEngineIntegration `INFERRED`
- BenchmarkRunner `INFERRED`
- TestDomainModelsAndEdgeCases `INFERRED`
- AnthropicFactExtractor `INFERRED`
- GeminiFactExtractor `INFERRED`
- OpenAIFactExtractor `INFERRED`
- CitationIntegrityInvariant `INFERRED`
- BaseFactExtractor `INFERRED`
- TestEndToEndAIPolicyPipeline `INFERRED`
- EvalScenario `INFERRED`
- ExtractionResult `INFERRED`
- TestDeliveryProofInvariant `INFERRED`
- TestPolicyEngineIntegration `INFERRED`
- TestSeparatedDecisionDimensions `INFERRED`
- TestCitationIntegrityHardening `INFERRED`
- TestCitationIntegrityInvariant `INFERRED`
- *…and 2 more `uses` connection(s) not listed (lowest-degree first to go)*

---

*Part of the graphify knowledge wiki. See [index](index.md) to navigate.*