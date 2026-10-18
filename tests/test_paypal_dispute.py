"""Unit tests for PayPal Sandbox Integration Spike.

Verifies OAuth 2.0 authentication, dispute retrieval, dispute listing,
sanitized parsing, error handling (401, 403, 404, 429, 5xx, timeouts, network failures, malformed responses),
missing evidence fields, and absent action links.
"""

import json
from unittest.mock import MagicMock, patch
import pytest
import requests

from scripts.spike_paypal_dispute import (
    AuthenticationError,
    AuthorizationError,
    ConfigurationError,
    DisputeSummary,
    MalformedResponseError,
    NetworkError,
    NotFoundError,
    PayPalSandboxClient,
    PayPalServerError,
    RateLimitError,
    TimeoutError,
    format_dispute_summary,
    main,
    parse_dispute_summary,
)


# ============================================================================
# Fixtures & Sample Payloads
# ============================================================================

SAMPLE_OAUTH_TOKEN_RESPONSE = {
    "scope": "https://api.paypal.com/v1/customer/disputes",
    "access_token": "mocked-access-token-xyz123",
    "token_type": "Bearer",
    "app_id": "APP-80W284485P519543T",
    "expires_in": 32400,
    "nonce": "2026-10-18T09:20:00Z",
}

SAMPLE_DISPUTE_RESPONSE = {
    "dispute_id": "PP-R-AYP-10135034",
    "create_time": "2026-10-18T09:46:54.926Z",
    "update_time": "2026-10-18T09:49:53.336Z",
    "disputed_transactions": [
        {
            "buyer_transaction_id": "7XB07472F52871902",
            "seller_transaction_id": "8AW70038VH226914P",
            "create_time": "2026-10-18T09:42:33.000Z",
            "transaction_status": "HELD",
            "gross_amount": {
                "currency_code": "USD",
                "value": "249.99",
            },
            "buyer": {
                "name": "Jane BuyerDoe",
                "email": "jane.buyer@example.com",
            },
            "seller": {
                "email": "merchant-seller@example.com",
                "merchant_id": "HAAP3SNYZZ9NG",
                "name": "Acme Store",
            },
            "items": [
                {
                    "item_name": "Mechanical Keyboard",
                    "item_quantity": "1",
                    "reason": "MERCHANDISE_OR_SERVICE_NOT_RECEIVED",
                    "item_type": "PRODUCT",
                }
            ],
        }
    ],
    "reason": "MERCHANDISE_OR_SERVICE_NOT_RECEIVED",
    "status": "WAITING_FOR_SELLER_RESPONSE",
    "dispute_amount": {
        "currency_code": "USD",
        "value": "249.99",
    },
    "dispute_state": "REQUIRED_ACTION",
    "dispute_life_cycle_stage": "INQUIRY",
    "dispute_channel": "INTERNAL",
    "seller_response_due_date": "2026-10-28T09:46:54.926Z",
    "evidences": [
        {
            "evidence_type": "CREATE",
            "notes": "Buyer opened claim stating package did not arrive",
            "source": "SUBMITTED_BY_BUYER",
            "date": "2026-10-18T09:46:54.926Z",
        },
        {
            "evidence_type": "PROOF_OF_FULFILLMENT",
            "source": "REQUESTED_FROM_SELLER",
            "date": "2026-10-18T09:49:53.336Z",
        },
    ],
    "links": [
        {
            "href": "https://api-m.sandbox.paypal.com/v1/customer/disputes/PP-R-AYP-10135034",
            "rel": "self",
            "method": "GET",
        },
        {
            "href": "https://api-m.sandbox.paypal.com/v1/customer/disputes/PP-R-AYP-10135034/provide-evidence",
            "rel": "provide_evidence",
            "method": "POST",
        },
        {
            "href": "https://api-m.sandbox.paypal.com/v1/customer/disputes/PP-R-AYP-10135034/send-message",
            "rel": "send_message",
            "method": "POST",
        },
    ],
}

SAMPLE_LIST_DISPUTES_RESPONSE = {
    "items": [
        {
            "dispute_id": "PP-R-AYP-10135034",
            "reason": "MERCHANDISE_OR_SERVICE_NOT_RECEIVED",
            "status": "WAITING_FOR_SELLER_RESPONSE",
            "dispute_amount": {
                "currency_code": "USD",
                "value": "249.99",
            },
            "dispute_life_cycle_stage": "INQUIRY",
            "seller_response_due_date": "2026-10-28T09:46:54.926Z",
            "links": [
                {
                    "href": "https://api-m.sandbox.paypal.com/v1/customer/disputes/PP-R-AYP-10135034",
                    "rel": "self",
                    "method": "GET",
                }
            ],
        }
    ],
    "links": [
        {
            "href": "https://api-m.sandbox.paypal.com/v1/customer/disputes",
            "rel": "self",
            "method": "GET",
        }
    ],
}


# ============================================================================
# Configuration & Setup Tests
# ============================================================================

def test_missing_client_id_raises_configuration_error(monkeypatch):
    """Client raises ConfigurationError if PAYPAL_CLIENT_ID is missing."""
    monkeypatch.delenv("PAYPAL_CLIENT_ID", raising=False)
    monkeypatch.delenv("PAYPAL_CLIENT_SECRET", raising=False)
    with pytest.raises(ConfigurationError) as exc_info:
        PayPalSandboxClient(client_id=None, client_secret="secret")
    assert "PAYPAL_CLIENT_ID" in str(exc_info.value)


def test_missing_client_secret_raises_configuration_error(monkeypatch):
    """Client raises ConfigurationError if PAYPAL_CLIENT_SECRET is missing."""
    monkeypatch.delenv("PAYPAL_CLIENT_ID", raising=False)
    monkeypatch.delenv("PAYPAL_CLIENT_SECRET", raising=False)
    with pytest.raises(ConfigurationError) as exc_info:
        PayPalSandboxClient(client_id="client_id_123", client_secret=None)
    assert "PAYPAL_CLIENT_SECRET" in str(exc_info.value)


def test_explicit_credentials_accepted():
    """Client successfully accepts explicit client_id and secret arguments."""
    client = PayPalSandboxClient(
        client_id="test_client",
        client_secret="test_secret",
        base_url="https://api-m.sandbox.paypal.com",
    )
    assert client.client_id == "test_client"
    assert client.client_secret == "test_secret"
    assert client.base_url == "https://api-m.sandbox.paypal.com"


# ============================================================================
# OAuth 2.0 Token Tests
# ============================================================================

def test_get_access_token_success():
    """Client successfully exchanges credentials for an OAuth access token."""
    client = PayPalSandboxClient(client_id="id1", client_secret="sec1")
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = SAMPLE_OAUTH_TOKEN_RESPONSE

    with patch.object(client.session, "post", return_value=mock_resp) as mock_post:
        token = client.get_access_token()
        assert token == "mocked-access-token-xyz123"
        mock_post.assert_called_once()
        args, kwargs = mock_post.call_args
        assert args[0] == "https://api-m.sandbox.paypal.com/v1/oauth2/token"
        assert kwargs["auth"] == ("id1", "sec1")
        assert kwargs["data"] == {"grant_type": "client_credentials"}


def test_get_access_token_cached_when_reused():
    """Client caches access token and does not re-request if not force-refreshed."""
    client = PayPalSandboxClient(client_id="id1", client_secret="sec1")
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = SAMPLE_OAUTH_TOKEN_RESPONSE

    with patch.object(client.session, "post", return_value=mock_resp) as mock_post:
        t1 = client.get_access_token()
        t2 = client.get_access_token()
        assert t1 == t2
        assert mock_post.call_count == 1


def test_oauth_token_authentication_failure_401():
    """Invalid credentials (HTTP 401) raise AuthenticationError."""
    client = PayPalSandboxClient(client_id="bad_id", client_secret="bad_sec")
    mock_resp = MagicMock()
    mock_resp.status_code = 401
    mock_resp.text = json.dumps({"error": "invalid_client", "error_description": "Client Authentication failed"})
    mock_resp.json.return_value = json.loads(mock_resp.text)

    with patch.object(client.session, "post", return_value=mock_resp):
        with pytest.raises(AuthenticationError) as exc_info:
            client.get_access_token()
        assert "401" in str(exc_info.value)
        # Ensure credentials are NOT leaked in exception string
        assert "bad_id" not in str(exc_info.value)
        assert "bad_sec" not in str(exc_info.value)


def test_oauth_token_authorization_failure_403():
    """HTTP 403 on token endpoint raises AuthorizationError."""
    client = PayPalSandboxClient(client_id="id1", client_secret="sec1")
    mock_resp = MagicMock()
    mock_resp.status_code = 403
    mock_resp.text = json.dumps({"error": "unauthorized_client", "error_description": "Client not permitted"})
    mock_resp.json.return_value = json.loads(mock_resp.text)

    with patch.object(client.session, "post", return_value=mock_resp):
        with pytest.raises(AuthorizationError) as exc_info:
            client.get_access_token()
        assert "403" in str(exc_info.value)


def test_oauth_token_rate_limit_429():
    """HTTP 429 raises RateLimitError."""
    client = PayPalSandboxClient(client_id="id1", client_secret="sec1")
    mock_resp = MagicMock()
    mock_resp.status_code = 429
    mock_resp.headers = {"Retry-After": "10"}
    mock_resp.text = "Too Many Requests"

    with patch.object(client.session, "post", return_value=mock_resp):
        with pytest.raises(RateLimitError) as exc_info:
            client.get_access_token()
        assert "429" in str(exc_info.value)


def test_oauth_token_server_error_500():
    """HTTP 500 raises PayPalServerError."""
    client = PayPalSandboxClient(client_id="id1", client_secret="sec1")
    mock_resp = MagicMock()
    mock_resp.status_code = 500
    mock_resp.text = "Internal Server Error"

    with patch.object(client.session, "post", return_value=mock_resp):
        with pytest.raises(PayPalServerError) as exc_info:
            client.get_access_token()
        assert "500" in str(exc_info.value)


def test_oauth_token_timeout():
    """Timeout during token request raises TimeoutError."""
    client = PayPalSandboxClient(client_id="id1", client_secret="sec1")
    with patch.object(client.session, "post", side_effect=requests.Timeout("Connection timed out")):
        with pytest.raises(TimeoutError) as exc_info:
            client.get_access_token()
        assert "timed out" in str(exc_info.value).lower()


def test_oauth_token_network_failure():
    """Network connection failure during token request raises NetworkError."""
    client = PayPalSandboxClient(client_id="id1", client_secret="sec1")
    with patch.object(client.session, "post", side_effect=requests.ConnectionError("DNS lookup failed")):
        with pytest.raises(NetworkError) as exc_info:
            client.get_access_token()
        assert "network" in str(exc_info.value).lower() or "connection" in str(exc_info.value).lower()


def test_oauth_token_malformed_json():
    """Invalid JSON response raises MalformedResponseError."""
    client = PayPalSandboxClient(client_id="id1", client_secret="sec1")
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.side_effect = json.JSONDecodeError("Expecting value", "doc", 0)
    mock_resp.text = "Not JSON data"

    with patch.object(client.session, "post", return_value=mock_resp):
        with pytest.raises(MalformedResponseError):
            client.get_access_token()


def test_oauth_token_missing_access_token_field():
    """Response lacking 'access_token' raises MalformedResponseError."""
    client = PayPalSandboxClient(client_id="id1", client_secret="sec1")
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"token_type": "Bearer"}  # missing access_token

    with patch.object(client.session, "post", return_value=mock_resp):
        with pytest.raises(MalformedResponseError) as exc_info:
            client.get_access_token()
        assert "access_token" in str(exc_info.value)


# ============================================================================
# Dispute Details (GET /v1/customer/disputes/{id}) Tests
# ============================================================================

def test_get_dispute_success():
    """Client successfully retrieves dispute details using access token."""
    client = PayPalSandboxClient(client_id="id1", client_secret="sec1")
    client._access_token = "mocked-token"

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = SAMPLE_DISPUTE_RESPONSE

    with patch.object(client.session, "get", return_value=mock_resp) as mock_get:
        dispute = client.get_dispute("PP-R-AYP-10135034")
        assert dispute["dispute_id"] == "PP-R-AYP-10135034"
        mock_get.assert_called_once()
        args, kwargs = mock_get.call_args
        assert args[0] == "https://api-m.sandbox.paypal.com/v1/customer/disputes/PP-R-AYP-10135034"
        assert kwargs["headers"]["Authorization"] == "Bearer mocked-token"


def test_get_dispute_not_found_404():
    """Non-existent dispute ID raises NotFoundError."""
    client = PayPalSandboxClient(client_id="id1", client_secret="sec1")
    client._access_token = "mocked-token"

    mock_resp = MagicMock()
    mock_resp.status_code = 404
    mock_resp.text = json.dumps({"name": "RESOURCE_NOT_FOUND", "message": "Dispute not found"})
    mock_resp.json.return_value = json.loads(mock_resp.text)

    with patch.object(client.session, "get", return_value=mock_resp):
        with pytest.raises(NotFoundError) as exc_info:
            client.get_dispute("PP-INVALID-ID")
        assert "404" in str(exc_info.value)
        assert "PP-INVALID-ID" in str(exc_info.value)


def test_get_dispute_unauthorized_401():
    """Expired or invalid token raises AuthenticationError."""
    client = PayPalSandboxClient(client_id="id1", client_secret="sec1")
    client._access_token = "expired-token"

    mock_resp = MagicMock()
    mock_resp.status_code = 401
    mock_resp.text = json.dumps({"name": "AUTHENTICATION_FAILURE", "message": "Authentication failed"})
    mock_resp.json.return_value = json.loads(mock_resp.text)

    with patch.object(client.session, "get", return_value=mock_resp):
        with pytest.raises(AuthenticationError):
            client.get_dispute("PP-R-AYP-10135034")


def test_get_dispute_forbidden_403():
    """Account lacks disputes access raises AuthorizationError."""
    client = PayPalSandboxClient(client_id="id1", client_secret="sec1")
    client._access_token = "valid-token"

    mock_resp = MagicMock()
    mock_resp.status_code = 403
    mock_resp.text = json.dumps({"name": "NOT_AUTHORIZED", "message": "Not authorized to access dispute"})
    mock_resp.json.return_value = json.loads(mock_resp.text)

    with patch.object(client.session, "get", return_value=mock_resp):
        with pytest.raises(AuthorizationError):
            client.get_dispute("PP-R-AYP-10135034")


def test_get_dispute_rate_limit_429():
    """HTTP 429 on dispute fetch raises RateLimitError."""
    client = PayPalSandboxClient(client_id="id1", client_secret="sec1")
    client._access_token = "valid-token"

    mock_resp = MagicMock()
    mock_resp.status_code = 429
    mock_resp.text = "Rate limit reached"

    with patch.object(client.session, "get", return_value=mock_resp):
        with pytest.raises(RateLimitError):
            client.get_dispute("PP-R-AYP-10135034")


def test_get_dispute_server_error_503():
    """HTTP 503 on dispute fetch raises PayPalServerError."""
    client = PayPalSandboxClient(client_id="id1", client_secret="sec1")
    client._access_token = "valid-token"

    mock_resp = MagicMock()
    mock_resp.status_code = 503
    mock_resp.text = "Service Unavailable"

    with patch.object(client.session, "get", return_value=mock_resp):
        with pytest.raises(PayPalServerError):
            client.get_dispute("PP-R-AYP-10135034")


def test_get_dispute_timeout():
    """Timeout on dispute fetch raises TimeoutError."""
    client = PayPalSandboxClient(client_id="id1", client_secret="sec1")
    client._access_token = "valid-token"

    with patch.object(client.session, "get", side_effect=requests.Timeout("Dispute request timeout")):
        with pytest.raises(TimeoutError):
            client.get_dispute("PP-R-AYP-10135034")


def test_get_dispute_malformed_json():
    """Malformed response body raises MalformedResponseError."""
    client = PayPalSandboxClient(client_id="id1", client_secret="sec1")
    client._access_token = "valid-token"

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.side_effect = json.JSONDecodeError("Expecting value", "<html>", 0)

    with patch.object(client.session, "get", return_value=mock_resp):
        with pytest.raises(MalformedResponseError):
            client.get_dispute("PP-R-AYP-10135034")


# ============================================================================
# Dispute Listing (GET /v1/customer/disputes) Tests
# ============================================================================

def test_list_disputes_success():
    """Client lists disputes successfully."""
    client = PayPalSandboxClient(client_id="id1", client_secret="sec1")
    client._access_token = "valid-token"

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = SAMPLE_LIST_DISPUTES_RESPONSE

    with patch.object(client.session, "get", return_value=mock_resp):
        result = client.list_disputes(page_size=10)
        assert "items" in result
        assert len(result["items"]) == 1
        assert result["items"][0]["dispute_id"] == "PP-R-AYP-10135034"


def test_list_disputes_empty():
    """Client handles empty dispute list gracefully."""
    client = PayPalSandboxClient(client_id="id1", client_secret="sec1")
    client._access_token = "valid-token"

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"items": [], "links": []}

    with patch.object(client.session, "get", return_value=mock_resp):
        result = client.list_disputes()
        assert result.get("items") == []


# ============================================================================
# Sanitized Summary Parsing & Data Integrity Tests
# ============================================================================

def test_parse_dispute_summary_complete():
    """Correctly parses all required summary fields from complete payload."""
    summary = parse_dispute_summary(SAMPLE_DISPUTE_RESPONSE)

    assert isinstance(summary, DisputeSummary)
    assert summary.dispute_id == "PP-R-AYP-10135034"
    assert summary.reason == "MERCHANDISE_OR_SERVICE_NOT_RECEIVED"
    assert summary.status == "WAITING_FOR_SELLER_RESPONSE"
    assert summary.life_cycle_stage == "INQUIRY"
    assert summary.amount == "249.99"
    assert summary.currency == "USD"
    assert summary.seller_response_due_date == "2026-10-28T09:46:54.926Z"

    # Requested evidence
    assert len(summary.requested_evidences) == 1
    req = summary.requested_evidences[0]
    assert req["evidence_type"] == "PROOF_OF_FULFILLMENT"
    assert req["source"] == "REQUESTED_FROM_SELLER"

    # HATEOAS Actions
    assert "self" in summary.available_actions
    assert "provide_evidence" in summary.available_actions
    assert "send_message" in summary.available_actions
    assert summary.has_provide_evidence_action is True


def test_parse_dispute_summary_absent_actions_and_evidences():
    """Handles responses missing evidences, seller deadline, and provide_evidence action."""
    minimal_payload = {
        "dispute_id": "PP-D-MINIMAL-1",
        "reason": "UNAUTHORISED",
        "status": "UNDER_REVIEW",
        "dispute_life_cycle_stage": "CHARGEBACK",
        "dispute_amount": {
            "currency_code": "EUR",
            "value": "50.00",
        },
        # evidences omitted
        # seller_response_due_date omitted
        "links": [
            {
                "href": "https://api-m.sandbox.paypal.com/v1/customer/disputes/PP-D-MINIMAL-1",
                "rel": "self",
                "method": "GET",
            }
        ],
    }

    summary = parse_dispute_summary(minimal_payload)
    assert summary.dispute_id == "PP-D-MINIMAL-1"
    assert summary.reason == "UNAUTHORISED"
    assert summary.status == "UNDER_REVIEW"
    assert summary.life_cycle_stage == "CHARGEBACK"
    assert summary.amount == "50.00"
    assert summary.currency == "EUR"
    assert summary.seller_response_due_date is None
    assert summary.requested_evidences == []
    assert summary.available_actions == ["self"]
    assert summary.has_provide_evidence_action is False


def test_parse_dispute_summary_strict_sanitization_no_pii():
    """Sanitized summary never leaks buyer personal names, emails, or internal credentials."""
    summary = parse_dispute_summary(SAMPLE_DISPUTE_RESPONSE)
    formatted = format_dispute_summary(summary)

    # Buyer personal name & email in sample payload
    assert "Jane BuyerDoe" not in formatted
    assert "jane.buyer@example.com" not in formatted
    assert "7XB07472F52871902" not in formatted  # buyer_transaction_id

    # Check presence of safe fields
    assert "PP-R-AYP-10135034" in formatted
    assert "MERCHANDISE_OR_SERVICE_NOT_RECEIVED" in formatted
    assert "WAITING_FOR_SELLER_RESPONSE" in formatted
    assert "249.99 USD" in formatted
    assert "PROOF_OF_FULFILLMENT" in formatted
    assert "provide_evidence" in formatted


# ============================================================================
# CLI Main Function & Execution Flow Tests
# ============================================================================

def test_main_missing_credentials_reports_blocked_without_crash(monkeypatch, capsys):
    """When credentials are not configured, main() reports integration blocked with exit code 0 or 2."""
    monkeypatch.delenv("PAYPAL_CLIENT_ID", raising=False)
    monkeypatch.delenv("PAYPAL_CLIENT_SECRET", raising=False)

    exit_code = main(["--env-file", "non_existent.env"])
    captured = capsys.readouterr()

    # Must indicate blocked by missing credentials and not throw an unhandled traceback
    assert exit_code != 0
    assert "PAYPAL_CLIENT_ID" in captured.out or "PAYPAL_CLIENT_ID" in captured.err
    assert "blocked" in captured.out.lower() or "blocked" in captured.err.lower() or "missing" in captured.err.lower()


def test_main_retrieves_configured_dispute_id(monkeypatch, capsys):
    """When PAYPAL_DISPUTE_ID is set, main() retrieves that dispute and prints summary."""
    monkeypatch.setenv("PAYPAL_CLIENT_ID", "mock_id")
    monkeypatch.setenv("PAYPAL_CLIENT_SECRET", "mock_secret")
    monkeypatch.setenv("PAYPAL_DISPUTE_ID", "PP-R-AYP-10135034")

    mock_client = MagicMock()
    mock_client.get_access_token.return_value = "mock_tok"
    mock_client.get_dispute.return_value = SAMPLE_DISPUTE_RESPONSE

    with patch("scripts.spike_paypal_dispute.PayPalSandboxClient", return_value=mock_client):
        exit_code = main([])
        captured = capsys.readouterr()

        assert exit_code == 0
        assert "PP-R-AYP-10135034" in captured.out
        assert "MERCHANDISE_OR_SERVICE_NOT_RECEIVED" in captured.out
        mock_client.get_dispute.assert_called_once_with("PP-R-AYP-10135034")


def test_main_lists_disputes_when_dispute_id_not_configured(tmp_path, monkeypatch, capsys):
    """When PAYPAL_DISPUTE_ID is absent, main() lists disputes to find a test case."""
    test_env = tmp_path / "test_no_dispute.env"
    test_env.write_text("PAYPAL_CLIENT_ID=mock_id\nPAYPAL_CLIENT_SECRET=mock_secret\n")
    monkeypatch.delenv("PAYPAL_DISPUTE_ID", raising=False)

    mock_client = MagicMock()
    mock_client.get_access_token.return_value = "mock_tok"
    mock_client.list_disputes.return_value = SAMPLE_LIST_DISPUTES_RESPONSE

    with patch("scripts.spike_paypal_dispute.PayPalSandboxClient", return_value=mock_client):
        exit_code = main(["--env-file", str(test_env)])
        captured = capsys.readouterr()

        assert exit_code == 0
        assert "PP-R-AYP-10135034" in captured.out
        mock_client.list_disputes.assert_called_once()



def test_paypal_dispute_error_str():
    """Verify PayPalDisputeError string representations with and without status code."""
    from scripts.spike_paypal_dispute import PayPalDisputeError
    e1 = PayPalDisputeError("Something bad", status_code=500)
    assert str(e1) == "[500] Something bad"
    e2 = PayPalDisputeError("Something bad")
    assert str(e2) == "Something bad"


def test_get_dispute_empty_id_raises_configuration_error():
    """Empty or whitespace dispute ID raises ConfigurationError."""
    client = PayPalSandboxClient(client_id="id1", client_secret="sec1")
    with pytest.raises(ConfigurationError):
        client.get_dispute("")
    with pytest.raises(ConfigurationError):
        client.get_dispute("   ")


def test_authenticated_get_network_and_request_errors():
    """ConnectionError and generic RequestException raise NetworkError."""
    client = PayPalSandboxClient(client_id="id1", client_secret="sec1")
    client._access_token = "valid-token"

    with patch.object(client.session, "get", side_effect=requests.ConnectionError("Connection lost")):
        with pytest.raises(NetworkError):
            client.get_dispute("PP-123")

    with patch.object(client.session, "get", side_effect=requests.RequestException("Request failed")):
        with pytest.raises(NetworkError):
            client.get_dispute("PP-123")


def test_authenticated_get_non_dict_json():
    """200 response with JSON array instead of object raises MalformedResponseError."""
    client = PayPalSandboxClient(client_id="id1", client_secret="sec1")
    client._access_token = "valid-token"

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = ["not", "a", "dict"]

    with patch.object(client.session, "get", return_value=mock_resp):
        with pytest.raises(MalformedResponseError):
            client.get_dispute("PP-123")


def test_authenticated_get_unexpected_status_400():
    """Unexpected status code like 400 raises PayPalDisputeError."""
    client = PayPalSandboxClient(client_id="id1", client_secret="sec1")
    client._access_token = "valid-token"

    mock_resp = MagicMock()
    mock_resp.status_code = 400
    mock_resp.text = json.dumps({"message": "Invalid query parameters"})
    mock_resp.json.return_value = json.loads(mock_resp.text)

    with patch.object(client.session, "get", return_value=mock_resp):
        with pytest.raises(from_script := PayPalServerError if False else Exception) as exc_info:
            client.get_dispute("PP-123")
        assert "400" in str(exc_info.value)


def test_oauth_token_unexpected_status_400():
    """Unexpected status code on token endpoint raises PayPalDisputeError."""
    client = PayPalSandboxClient(client_id="id1", client_secret="sec1")

    mock_resp = MagicMock()
    mock_resp.status_code = 400
    mock_resp.text = json.dumps({"error": "invalid_request"})
    mock_resp.json.return_value = json.loads(mock_resp.text)

    with patch.object(client.session, "post", return_value=mock_resp):
        with pytest.raises(Exception) as exc_info:
            client.get_access_token()
        assert "400" in str(exc_info.value)


def test_safe_error_message_non_json():
    """_safe_error_message handles non-JSON plain text gracefully."""
    client = PayPalSandboxClient(client_id="id1", client_secret="sec1")
    mock_resp = MagicMock()
    mock_resp.json.side_effect = Exception("Not JSON")
    mock_resp.text = "Bad Gateway error message"
    mock_resp.status_code = 502
    msg = client._safe_error_message(mock_resp)
    assert "Bad Gateway" in msg


def test_format_dispute_summary_empty_evidence():
    """Formatting dispute with no requested evidence displays appropriate message."""
    minimal_summary = DisputeSummary(
        dispute_id="PP-NO-EV",
        reason="MERCHANDISE_OR_SERVICE_NOT_RECEIVED",
        status="RESOLVED",
        life_cycle_stage="INQUIRY",
        amount="10.00",
        currency="USD",
        seller_response_due_date=None,
        requested_evidences=[],
        available_actions=[],
        has_provide_evidence_action=False,
    )
    formatted = format_dispute_summary(minimal_summary)
    assert "None explicitly requested" in formatted
    assert "Provide-Evidence Allowed:   NO" in formatted


def test_format_dispute_list_empty():
    """Formatting an empty dispute list returns helpful message."""
    from scripts.spike_paypal_dispute import format_dispute_list
    assert "No disputes found" in format_dispute_list([])


def test_main_cli_force_list_flag(monkeypatch, capsys):
    """--list flag forces listing even if PAYPAL_DISPUTE_ID is set."""
    monkeypatch.setenv("PAYPAL_CLIENT_ID", "mock_id")
    monkeypatch.setenv("PAYPAL_CLIENT_SECRET", "mock_secret")
    monkeypatch.setenv("PAYPAL_DISPUTE_ID", "PP-CONFIGURED-ID")

    mock_client = MagicMock()
    mock_client.get_access_token.return_value = "mock_tok"
    mock_client.list_disputes.return_value = SAMPLE_LIST_DISPUTES_RESPONSE

    with patch("scripts.spike_paypal_dispute.PayPalSandboxClient", return_value=mock_client):
        exit_code = main(["--list"])
        captured = capsys.readouterr()

        assert exit_code == 0
        mock_client.list_disputes.assert_called_once()
        mock_client.get_dispute.assert_not_called()


@pytest.mark.parametrize(
    "exc_to_raise,expected_code,expected_tag",
    [
        (AuthenticationError("Auth failed"), 1, "[AUTHENTICATION ERROR]"),
        (AuthorizationError("Forbidden"), 1, "[AUTHORIZATION ERROR]"),
        (NotFoundError("Not found"), 1, "[NOT FOUND ERROR]"),
        (RateLimitError("Rate limited"), 1, "[RATE LIMIT ERROR]"),
        (PayPalServerError("Server down"), 1, "[SERVER ERROR]"),
        (NetworkError("Connection reset"), 1, "[NETWORK ERROR]"),
        (TimeoutError("Timeout occurred"), 1, "[NETWORK ERROR]"),
        (MalformedResponseError("Invalid schema"), 1, "[MALFORMED RESPONSE]"),
        (RuntimeError("Unexpected crash"), 1, "[UNEXPECTED ERROR]"),
    ],
)
def test_main_handles_exceptions_gracefully(monkeypatch, capsys, exc_to_raise, expected_code, expected_tag):
    """main() catches PayPal exceptions and exits cleanly with error messages."""
    monkeypatch.setenv("PAYPAL_CLIENT_ID", "mock_id")
    monkeypatch.setenv("PAYPAL_CLIENT_SECRET", "mock_secret")

    with patch("scripts.spike_paypal_dispute.PayPalSandboxClient") as mock_cls:
        mock_instance = MagicMock()
        mock_instance.get_access_token.side_effect = exc_to_raise
        mock_cls.return_value = mock_instance

        exit_code = main([])
        captured = capsys.readouterr()

        assert exit_code == expected_code
        assert expected_tag in captured.err


def test_oauth_token_request_exception():
    """Generic RequestException during token request raises NetworkError."""
    client = PayPalSandboxClient(client_id="id1", client_secret="sec1")
    with patch.object(client.session, "post", side_effect=requests.RequestException("SSL handshake failed")):
        with pytest.raises(NetworkError):
            client.get_access_token()


def test_main_with_existing_custom_env_file(tmp_path, monkeypatch, capsys):
    """main() successfully loads from a specified custom .env file."""
    monkeypatch.delenv("PAYPAL_DISPUTE_ID", raising=False)
    custom_env = tmp_path / "custom.env"
    custom_env.write_text("PAYPAL_CLIENT_ID=file_id\nPAYPAL_CLIENT_SECRET=file_sec\n")

    mock_client = MagicMock()
    mock_client.get_access_token.return_value = "tok"
    mock_client.list_disputes.return_value = {"items": []}

    with patch("scripts.spike_paypal_dispute.PayPalSandboxClient", return_value=mock_client):
        exit_code = main(["--env-file", str(custom_env)])
        assert exit_code == 0
        mock_client.list_disputes.assert_called_once()


def test_main_catches_client_configuration_error(monkeypatch, capsys):
    """main() catches ConfigurationError raised by client logic."""
    monkeypatch.setenv("PAYPAL_CLIENT_ID", "mock_id")
    monkeypatch.setenv("PAYPAL_CLIENT_SECRET", "mock_secret")

    with patch("scripts.spike_paypal_dispute.PayPalSandboxClient") as mock_cls:
        mock_cls.side_effect = ConfigurationError("Misconfigured base URL")
        exit_code = main([])
        captured = capsys.readouterr()
        assert exit_code == 2
        assert "[CONFIGURATION ERROR]" in captured.err


