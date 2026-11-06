# ApprovalService

> God node · 44 connections · `docket/dispatch/approval.py`

**Community:** [Community 35](Community_35.md)

## Connections by Relation

### calls
- run_milestone_6_verification() `EXTRACTED`
- create_app() `EXTRACTED`
- test_dispatcher_hateoas_insecure_http_rejected() `EXTRACTED`
- test_dispatcher_hateoas_untrusted_host_rejected() `EXTRACTED`
- test_dispatcher_hateoas_missing_action() `EXTRACTED`
- test_dispatcher_idempotency_prevents_duplicate_dispatch() `EXTRACTED`
- test_dispatcher_refuses_when_policy_blocks() `EXTRACTED`
- test_dispatcher_refuses_when_approval_rejected() `EXTRACTED`
- test_dispatcher_http_network_exception_handling() `EXTRACTED`
- test_dispatcher_paypal_server_error_handling() `EXTRACTED`
- test_approval_service_detects_invalid_signature_or_key() `EXTRACTED`
- test_approval_service_detects_payload_tampering() `EXTRACTED`
- test_approval_service_detects_token_expiration() `EXTRACTED`
- test_approval_service_records_merchant_decision() `EXTRACTED`
- test_dispatcher_refuses_when_approval_record_missing() `EXTRACTED`
- test_approval_service_token_dispute_mismatch() `EXTRACTED`
- test_approval_service_token_malformed_formats() `EXTRACTED`
- test_approval_service_token_generation_and_verification() `EXTRACTED`
- test_human_summary_generation_contains_critical_sections() `EXTRACTED`

### contains
- approval.py `EXTRACTED`

### imports
- test_dispatch_and_audit.py `EXTRACTED`
- app.py `EXTRACTED`
- dispatcher.py `EXTRACTED`
- verify_dispatch_pipeline.py `EXTRACTED`
- dispatch/__init__.py `EXTRACTED`

### method
- .create_approval_request() `EXTRACTED`
- .verify_token() `EXTRACTED`
- .record_approval() `EXTRACTED`
- .generate_human_summary() `EXTRACTED`
- ._hash_payload() `EXTRACTED`
- ._generate_signature() `EXTRACTED`
- .__init__() `EXTRACTED`

### rationale_for
- Manages cryptographic approval tokens and merchant authorization gates. `EXTRACTED`

### references
- ADR-014: Controlled Evidence Submission, Cryptographic Merchant Approval Tokens, and Immutable Audit Ledger `INFERRED`
- Phase 6: Controlled Evidence-Submission Workflow `INFERRED`
- 7. Merchant Approval Gate & Action Dispatcher (`docket/dispatch/` - IMPLEMENTED & VERIFIED IN MILESTONE 6) `INFERRED`
- .__init__() `EXTRACTED`

### uses
- [DisputeCase](DisputeCase.md) `INFERRED`
- [ReconciledDisputeBundle](ReconciledDisputeBundle.md) `INFERRED`
- OverallPolicyEvaluation `INFERRED`
- EvidenceDispatcher `INFERRED`
- ApprovalDecision `INFERRED`
- MerchantApprovalRecord `INFERRED`
- ApprovalRequest `INFERRED`

---

*Part of the graphify knowledge wiki. See [index](index.md) to navigate.*