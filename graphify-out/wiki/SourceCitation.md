# SourceCitation

> God node · 60 connections · `docket/models/evidence.py`

**Community:** [Community 0](Community_0.md)

## Connections by Relation

### calls
- load_all_scenarios() `EXTRACTED`
- .extract_from_bundle() `EXTRACTED`
- .extract_from_bundle() `EXTRACTED`
- .extract_from_bundle() `EXTRACTED`
- .verify_citation() `EXTRACTED`
- .test_factually_supported_claim_retains_allow_when_dispute_state_blocks_action() `EXTRACTED`
- .test_engine_evaluates_against_real_sandbox_fixture() `EXTRACTED`
- .test_action_eligible_dispute_blocks_when_claim_is_unsupported() `EXTRACTED`
- .test_advisories_isolated_from_blocking_decisions() `EXTRACTED`
- .test_policy_engine_review_summary_branch() `EXTRACTED`
- .test_citation_field_path_nested_resolution() `EXTRACTED`
- .test_citation_field_path_nonexistent_blocked() `EXTRACTED`
- .test_citation_rejected_source_blocked() `EXTRACTED`
- .test_citation_unverified_source_triggers_review() `EXTRACTED`
- .test_citation_value_mismatch_contradiction_blocked() `EXTRACTED`
- .test_citation_pointing_to_nonexistent_source_blocked() `EXTRACTED`
- .test_citation_with_conflicting_source_triggers_review() `EXTRACTED`
- .test_valid_claim_with_verified_citation_allowed() `EXTRACTED`
- .test_delivery_claim_allowed_when_delivered_and_complete() `EXTRACTED`
- .test_delivery_claim_blocked_when_in_transit() `EXTRACTED`
- *…and 7 more `calls` connection(s) not listed (lowest-degree first to go)*

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
- reconciliation.py `EXTRACTED`
- verify_dispatch_pipeline.py `EXTRACTED`
- deterministic.py `EXTRACTED`
- provider_openai.py `EXTRACTED`
- provider_anthropic.py `EXTRACTED`
- provider_gemini.py `EXTRACTED`
- base.py `EXTRACTED`
- citation_verifier.py `EXTRACTED`

### inherits
- BaseModel `EXTRACTED`

### rationale_for
- A granular, auditable pointer to a factual statement in a source record. `EXTRACTED`

### references
- .to_citations() `EXTRACTED`

### uses
- [ReconciledDisputeBundle](ReconciledDisputeBundle.md) `INFERRED`
- [DeterministicFactExtractor](DeterministicFactExtractor.md) `INFERRED`
- TestDomainModelsAndEdgeCases `INFERRED`
- AnthropicFactExtractor `INFERRED`
- GeminiFactExtractor `INFERRED`
- OpenAIFactExtractor `INFERRED`
- ExtractionResult `INFERRED`
- VerbatimCitationVerifier `INFERRED`
- TestDeliveryProofInvariant `INFERRED`
- TestPolicyEngineIntegration `INFERRED`
- TestSeparatedDecisionDimensions `INFERRED`
- TestCitationIntegrityHardening `INFERRED`
- TestCitationIntegrityInvariant `INFERRED`
- CitationVerificationResult `INFERRED`

---

*Part of the graphify knowledge wiki. See [index](index.md) to navigate.*