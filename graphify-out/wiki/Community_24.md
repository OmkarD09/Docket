# Community 24

> 40 nodes

## Key Concepts

- **test_paypal_dispute.py** (65 connections) — `tests/test_paypal_dispute.py`
- **main()** (18 connections) — `scripts/spike_paypal_dispute.py`
- **parse_dispute_summary()** (9 connections) — `scripts/spike_paypal_dispute.py`
- **format_dispute_summary()** (7 connections) — `scripts/spike_paypal_dispute.py`
- **DisputeSummary** (6 connections) — `scripts/spike_paypal_dispute.py`
- **test_format_dispute_summary_empty_evidence()** (4 connections) — `tests/test_paypal_dispute.py`
- **test_get_access_token_cached_when_reused()** (4 connections) — `tests/test_paypal_dispute.py`
- **test_get_access_token_success()** (4 connections) — `tests/test_paypal_dispute.py`
- **test_main_catches_client_configuration_error()** (4 connections) — `tests/test_paypal_dispute.py`
- **test_main_handles_exceptions_gracefully()** (4 connections) — `tests/test_paypal_dispute.py`
- **test_parse_dispute_summary_complete()** (4 connections) — `tests/test_paypal_dispute.py`
- **test_parse_dispute_summary_strict_sanitization_no_pii()** (4 connections) — `tests/test_paypal_dispute.py`
- **test_explicit_credentials_accepted()** (3 connections) — `tests/test_paypal_dispute.py`
- **test_main_cli_force_list_flag()** (3 connections) — `tests/test_paypal_dispute.py`
- **test_main_lists_disputes_when_dispute_id_not_configured()** (3 connections) — `tests/test_paypal_dispute.py`
- **test_main_missing_credentials_reports_blocked_without_crash()** (3 connections) — `tests/test_paypal_dispute.py`
- **test_main_retrieves_configured_dispute_id()** (3 connections) — `tests/test_paypal_dispute.py`
- **test_main_with_existing_custom_env_file()** (3 connections) — `tests/test_paypal_dispute.py`
- **test_parse_dispute_summary_absent_actions_and_evidences()** (3 connections) — `tests/test_paypal_dispute.py`
- **test_paypal_dispute_error_str()** (3 connections) — `tests/test_paypal_dispute.py`
- **parametrize** (1 connections)
- **Parse raw dispute response into a sanitized summary without PII or credentials.…** (1 connections) — `scripts/spike_paypal_dispute.py`
- **Format DisputeSummary into a human-readable, sanitized console report.** (1 connections) — `scripts/spike_paypal_dispute.py`
- **CLI execution for the read-only Sandbox spike.** (1 connections) — `scripts/spike_paypal_dispute.py`
- **Unit tests for PayPal Sandbox Integration Spike. Verifies OAuth 2.0…** (1 connections) — `tests/test_paypal_dispute.py`
- *... and 15 more nodes in this community*

## Relationships

- [Community 13](Community_13.md) (28 shared connections)
- [Community 43](Community_43.md) (18 shared connections)
- [Community 254](Community_254.md) (7 shared connections)
- [Community 220](Community_220.md) (4 shared connections)
- [Community 465](Community_465.md) (3 shared connections)
- [Community 356](Community_356.md) (1 shared connections)
- [Community 2](Community_2.md) (1 shared connections)
- [Community 484](Community_484.md) (1 shared connections)

## Source Files

- `scripts/spike_paypal_dispute.py`
- `tests/test_paypal_dispute.py`

## Audit Trail

- EXTRACTED: 114 (95%)
- INFERRED: 6 (5%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [index](index.md) to navigate.*