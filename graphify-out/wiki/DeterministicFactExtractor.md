# DeterministicFactExtractor

> God node · 45 connections · `docket/ai/deterministic.py`

**Community:** [Community 6](Community_6.md)

## Connections by Relation

### calls
- load_initial_cases() `EXTRACTED`
- get_fact_extractor() `EXTRACTED`
- .__init__() `EXTRACTED`
- .test_extract_buyer_message_facts() `EXTRACTED`
- .test_extract_delivered_tracking_claim() `EXTRACTED`
- .test_extract_label_created_tracking_claim() `EXTRACTED`
- .test_deterministic_extract_from_text() `EXTRACTED`
- .test_deterministic_extract_in_transit_shipment() `EXTRACTED`
- .test_deterministic_flags_suspicious_message_pattern() `EXTRACTED`

### contains
- deterministic.py `EXTRACTED`

### imports
- test_ai_extractor.py `EXTRACTED`
- app.py `EXTRACTED`
- ai/__init__.py `EXTRACTED`
- eval/runner.py `EXTRACTED`
- factory.py `EXTRACTED`

### inherits
- BaseFactExtractor `EXTRACTED`

### method
- .extract_from_bundle() `EXTRACTED`
- .extract_from_text() `EXTRACTED`
- .__init__() `EXTRACTED`

### rationale_for
- Extracts structured facts deterministically from dispute and bundle records. `EXTRACTED`

### references
- 1. Project Status Matrix `INFERRED`
- 6. Synthetic Evaluation Benchmark Suite (`docket/eval/` - IMPLEMENTED & VERIFIED IN MILESTONE 5) `INFERRED`
- ADR-013: Synthetic Evaluation Benchmark Suite and Empirical Refusal Metrics `INFERRED`
- ADR-012: Pluggable AI Fact Extraction with Prompt Injection Defense and Verbatim Grounding `INFERRED`
- 4. AI Semantic Fact Extractor (`docket/ai/` - IMPLEMENTED & VERIFIED IN MILESTONE 4) `INFERRED`
- 1. Executive Summary `INFERRED`
- 2.4 Multi-Provider & Deterministic Extractor Layer `INFERRED`
- Phase 4: AI Semantic Fact Extraction & Citation Engine `INFERRED`
- 2.2 Benchmark Runner (\[`docket/eval/runner.py`\](file:///c:/Users/ACER/Downloads/Docket/docket/eval/runner.py)) `INFERRED`

### uses
- [ExtractedClaim](ExtractedClaim.md) `INFERRED`
- [DisputeCase](DisputeCase.md) `INFERRED`
- [ReconciledDisputeBundle](ReconciledDisputeBundle.md) `INFERRED`
- [SourceCitation](SourceCitation.md) `INFERRED`
- SourceType `INFERRED`
- PromptInjectionGuard `INFERRED`
- ClaimType `INFERRED`
- TrackingStatus `INFERRED`
- ContradictionDetector `INFERRED`
- BenchmarkRunner `INFERRED`
- TestEndToEndAIPolicyPipeline `INFERRED`
- VerbatimCitationVerifier `INFERRED`
- ExtractionResult `INFERRED`
- ClaimStatus `INFERRED`
- TestDeterministicFactExtractor `INFERRED`
- TestFactExtractorFactory `INFERRED`

---

*Part of the graphify knowledge wiki. See [index](index.md) to navigate.*