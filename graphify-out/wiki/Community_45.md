# Community 45

> 28 nodes

## Key Concepts

- **EvidenceDispatcher** (31 connections) — `docket/dispatch/dispatcher.py`
- **ApprovalDecision** (25 connections) — `docket/models/dispatch.py`
- **.create_approval_request()** (25 connections) — `docket/dispatch/approval.py`
- **.dispatch_evidence()** (25 connections) — `docket/dispatch/dispatcher.py`
- **SubmissionBlockedError** (18 connections) — `docket/dispatch/dispatcher.py`
- **.record_approval()** (15 connections) — `docket/dispatch/approval.py`
- **MerchantApprovalRecord** (14 connections) — `docket/models/dispatch.py`
- **test_dispatcher_hateoas_insecure_http_rejected()** (12 connections) — `tests/test_dispatch_and_audit.py`
- **test_dispatcher_hateoas_untrusted_host_rejected()** (12 connections) — `tests/test_dispatch_and_audit.py`
- **test_dispatcher_hateoas_missing_action()** (11 connections) — `tests/test_dispatch_and_audit.py`
- **test_dispatcher_idempotency_prevents_duplicate_dispatch()** (11 connections) — `tests/test_dispatch_and_audit.py`
- **test_dispatcher_refuses_when_policy_blocks()** (11 connections) — `tests/test_dispatch_and_audit.py`
- **test_dispatcher_refuses_when_approval_rejected()** (10 connections) — `tests/test_dispatch_and_audit.py`
- **test_dispatcher_http_network_exception_handling()** (9 connections) — `tests/test_dispatch_and_audit.py`
- **test_dispatcher_paypal_server_error_handling()** (9 connections) — `tests/test_dispatch_and_audit.py`
- **test_approval_service_records_merchant_decision()** (7 connections) — `tests/test_dispatch_and_audit.py`
- **._resolve_provide_evidence_url()** (5 connections) — `docket/dispatch/dispatcher.py`
- **.is_approved()** (3 connections) — `docket/models/dispatch.py`
- **Enum** (2 connections)
- **str** (1 connections)
- **Record an affirmative approval or explicit rejection by a human merchant.** (1 connections) — `docket/dispatch/approval.py`
- **Create a new approval request ticket with an HMAC authorization token.** (1 connections) — `docket/dispatch/approval.py`
- **Controls and executes evidence submissions to PayPal Disputes API.** (1 connections) — `docket/dispatch/dispatcher.py`
- **Extract and validate the HATEOAS action URL for provide_evidence.** (1 connections) — `docket/dispatch/dispatcher.py`
- **Perform guarded evidence dispatch to PayPal Disputes API.** (1 connections) — `docket/dispatch/dispatcher.py`
- *... and 3 more nodes in this community*

## Relationships

- [Community 35](Community_35.md) (50 shared connections)
- [Community 2](Community_2.md) (28 shared connections)
- [Community 77](Community_77.md) (11 shared connections)
- [Community 39](Community_39.md) (8 shared connections)
- [Community 292](Community_292.md) (7 shared connections)
- [Community 13](Community_13.md) (6 shared connections)
- [Community 49](Community_49.md) (4 shared connections)
- [Community 7](Community_7.md) (3 shared connections)
- [Community 5](Community_5.md) (3 shared connections)
- [Community 4](Community_4.md) (3 shared connections)
- [Community 12](Community_12.md) (2 shared connections)
- [Community 10](Community_10.md) (1 shared connections)

## Source Files

- `docket/dispatch/approval.py`
- `docket/dispatch/dispatcher.py`
- `docket/models/dispatch.py`
- `tests/test_dispatch_and_audit.py`

## Audit Trail

- EXTRACTED: 107 (55%)
- INFERRED: 88 (45%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [index](index.md) to navigate.*