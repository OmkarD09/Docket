"""Docket PayPal Sandbox Read-Only Client.

Provides authenticated, strictly read-only retrieval of disputes from the PayPal Disputes API
using the OAuth 2.0 client-credentials flow against https://api-m.sandbox.paypal.com.

Strictly read-only: no dispute modification, closing, or evidence submission.
"""

from __future__ import annotations

import os
from typing import Any, Dict, List, Optional
import requests
from dotenv import load_dotenv

load_dotenv()

SANDBOX_API_BASE = "https://api-m.sandbox.paypal.com"
DEFAULT_TIMEOUT_SECONDS = 30


# ============================================================================
# Exception Hierarchy
# ============================================================================

class PayPalDisputeError(Exception):
    """Base exception for PayPal dispute operations."""
    def __init__(self, message: str, status_code: Optional[int] = None, details: Optional[Any] = None):
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.details = details

    def __str__(self) -> str:
        if self.status_code:
            return f"[{self.status_code}] {self.message}"
        return self.message


class ConfigurationError(PayPalDisputeError):
    """Raised when required environment configuration or credentials are missing."""


class AuthenticationError(PayPalDisputeError):
    """Raised on HTTP 401 or invalid OAuth credentials."""


class AuthorizationError(PayPalDisputeError):
    """Raised on HTTP 403 or lack of API permissions."""


class NotFoundError(PayPalDisputeError):
    """Raised on HTTP 404 when a dispute ID is not found."""


class RateLimitError(PayPalDisputeError):
    """Raised on HTTP 429 when rate limits are exceeded."""


class PayPalServerError(PayPalDisputeError):
    """Raised on HTTP 5xx responses from PayPal."""


class NetworkError(PayPalDisputeError):
    """Raised on connection failures, DNS resolution issues, or SSL errors."""


class TimeoutError(PayPalDisputeError):
    """Raised when an API request exceeds the configured timeout."""


class MalformedResponseError(PayPalDisputeError):
    """Raised when PayPal returns non-JSON or an unexpected schema."""


# ============================================================================
# PayPal Sandbox Client (Read-Only)
# ============================================================================

class PayPalSandboxClient:
    """Read-only client for querying PayPal Sandbox disputes."""

    def __init__(
        self,
        client_id: Optional[str] = None,
        client_secret: Optional[str] = None,
        base_url: str = SANDBOX_API_BASE,
        timeout: int = DEFAULT_TIMEOUT_SECONDS,
        session: Optional[requests.Session] = None,
    ):
        self.client_id = client_id or os.environ.get("PAYPAL_CLIENT_ID")
        self.client_secret = client_secret or os.environ.get("PAYPAL_CLIENT_SECRET")
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.session = session or requests.Session()
        self._access_token: Optional[str] = None

        if not self.client_id:
            raise ConfigurationError(
                "Missing PAYPAL_CLIENT_ID. Please set PAYPAL_CLIENT_ID in your environment or .env file."
            )
        if not self.client_secret:
            raise ConfigurationError(
                "Missing PAYPAL_CLIENT_SECRET. Please set PAYPAL_CLIENT_SECRET in your environment or .env file."
            )

    def _safe_error_message(self, resp: requests.Response) -> str:
        """Extract error summary from response without revealing internal tokens."""
        try:
            data = resp.json()
            if isinstance(data, dict):
                return data.get("error_description") or data.get("message") or data.get("error") or resp.text
        except Exception:
            pass
        return resp.text[:300] if resp.text else f"HTTP {resp.status_code}"

    def get_access_token(self, force_refresh: bool = False) -> str:
        """Obtain an OAuth 2.0 access token via client-credentials flow."""
        if self._access_token and not force_refresh:
            return self._access_token

        url = f"{self.base_url}/v1/oauth2/token"
        headers = {
            "Accept": "application/json",
            "Accept-Language": "en_US",
        }
        data = {"grant_type": "client_credentials"}

        try:
            resp = self.session.post(
                url,
                auth=(self.client_id, self.client_secret),
                data=data,
                headers=headers,
                timeout=self.timeout,
            )
        except requests.Timeout as e:
            raise TimeoutError(f"OAuth token request timed out after {self.timeout}s: {e}") from e
        except requests.ConnectionError as e:
            raise NetworkError(f"Network connection failed during OAuth token request: {e}") from e
        except requests.RequestException as e:
            raise NetworkError(f"Request failed during OAuth token request: {e}") from e

        if resp.status_code == 401:
            raise AuthenticationError(
                f"PayPal OAuth authentication failed (HTTP 401): {self._safe_error_message(resp)}",
                status_code=401,
            )
        elif resp.status_code == 403:
            raise AuthorizationError(
                f"PayPal OAuth authorization failed (HTTP 403): {self._safe_error_message(resp)}",
                status_code=403,
            )
        elif resp.status_code == 429:
            retry_after = resp.headers.get("Retry-After")
            msg = "PayPal rate limit exceeded (HTTP 429)."
            if retry_after:
                msg += f" Retry-After: {retry_after}s"
            raise RateLimitError(msg, status_code=429)
        elif resp.status_code >= 500:
            raise PayPalServerError(
                f"PayPal server error during OAuth token request (HTTP {resp.status_code}): {self._safe_error_message(resp)}",
                status_code=resp.status_code,
            )
        elif resp.status_code != 200:
            raise PayPalDisputeError(
                f"Unexpected response status (HTTP {resp.status_code}): {self._safe_error_message(resp)}",
                status_code=resp.status_code,
            )

        try:
            payload = resp.json()
        except Exception as e:
            raise MalformedResponseError(f"Failed to decode JSON from OAuth token response: {e}") from e

        if not isinstance(payload, dict) or "access_token" not in payload:
            raise MalformedResponseError("OAuth token response is missing required 'access_token' field")

        token = str(payload["access_token"])
        self._access_token = token
        return token

    def _authenticated_get(self, endpoint: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Execute a read-only GET request with Bearer authorization and robust error mapping."""
        token = self.get_access_token()
        url = f"{self.base_url}{endpoint}"
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {token}",
        }

        try:
            resp = self.session.get(url, headers=headers, params=params, timeout=self.timeout)
        except requests.Timeout as e:
            raise TimeoutError(f"Request to {endpoint} timed out after {self.timeout}s: {e}") from e
        except requests.ConnectionError as e:
            raise NetworkError(f"Network error during request to {endpoint}: {e}") from e
        except requests.RequestException as e:
            raise NetworkError(f"Request error during request to {endpoint}: {e}") from e

        if resp.status_code == 200:
            try:
                data = resp.json()
                if not isinstance(data, dict):
                    raise MalformedResponseError(f"Expected JSON object response from {endpoint}, got {type(data).__name__}")
                return data
            except Exception as e:
                raise MalformedResponseError(f"Failed to parse JSON response from {endpoint}: {e}") from e

        error_msg = self._safe_error_message(resp)

        if resp.status_code == 401:
            raise AuthenticationError(
                f"Unauthorized access to {endpoint} (HTTP 401): {error_msg}",
                status_code=401,
            )
        elif resp.status_code == 403:
            raise AuthorizationError(
                f"Forbidden access to {endpoint} (HTTP 403): {error_msg}",
                status_code=403,
            )
        elif resp.status_code == 404:
            raise NotFoundError(
                f"Resource not found at {endpoint} (HTTP 404): {error_msg}",
                status_code=404,
            )
        elif resp.status_code == 429:
            retry_after = resp.headers.get("Retry-After")
            msg = f"Rate limited on {endpoint} (HTTP 429)."
            if retry_after:
                msg += f" Retry-After: {retry_after}s"
            raise RateLimitError(msg, status_code=429)
        elif resp.status_code >= 500:
            raise PayPalServerError(
                f"PayPal server error on {endpoint} (HTTP {resp.status_code}): {error_msg}",
                status_code=resp.status_code,
            )
        else:
            raise PayPalDisputeError(
                f"Request to {endpoint} failed (HTTP {resp.status_code}): {error_msg}",
                status_code=resp.status_code,
            )

    def get_dispute(self, dispute_id: str) -> Dict[str, Any]:
        """Fetch details of a specific dispute: GET /v1/customer/disputes/{dispute_id}."""
        if not dispute_id or not dispute_id.strip():
            raise ConfigurationError("Dispute ID cannot be empty.")
        clean_id = dispute_id.strip()
        return self._authenticated_get(f"/v1/customer/disputes/{clean_id}")

    def list_disputes(self, page_size: int = 10) -> Dict[str, Any]:
        """List disputes for the merchant account: GET /v1/customer/disputes."""
        params = {"page_size": max(1, min(page_size, 50))}
        return self._authenticated_get("/v1/customer/disputes", params=params)
