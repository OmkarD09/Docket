#!/usr/bin/env python3
"""Docket - Milestone 1: Read-Only PayPal Sandbox Integration Spike.

Validates PayPal Sandbox integration by:
1. Loading credentials from environment variables / .env.
2. Authenticating via OAuth 2.0 client-credentials flow against https://api-m.sandbox.paypal.com.
3. Fetching a specific dispute or listing available merchant disputes in the sandbox.
4. Parsing a sanitized, PII-free summary verifying HATEOAS actions and evidence requirements.

Strictly read-only: no dispute modification, closing, or evidence submission.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass, field
import json
import os
from pathlib import Path
import sys
from typing import Any, Dict, List, Optional
from urllib.parse import urlencode

import requests
from dotenv import load_dotenv

# Default Sandbox Host as documented by PayPal
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
# Data Models for Sanitized Output
# ============================================================================

@dataclass
class RequestedEvidence:
    evidence_type: str
    source: str
    date: Optional[str] = None


@dataclass
class DisputeSummary:
    dispute_id: str
    reason: str
    status: str
    life_cycle_stage: str
    amount: str
    currency: str
    seller_response_due_date: Optional[str]
    requested_evidences: List[Dict[str, str]] = field(default_factory=list)
    available_actions: List[str] = field(default_factory=list)
    has_provide_evidence_action: bool = False


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
            msg = f"PayPal rate limit exceeded (HTTP 429)."
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
            raise MalformedResponseError(
                f"Failed to decode JSON from OAuth token response: {e}"
            ) from e

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


# ============================================================================
# Response Sanitization & Parsing
# ============================================================================

def parse_dispute_summary(data: Dict[str, Any]) -> DisputeSummary:
    """Parse raw dispute response into a sanitized summary without PII or credentials.

    Extracts:
    - Dispute ID
    - Dispute reason
    - Status & lifecycle stage
    - Amount & currency
    - Seller response deadline (if available)
    - Requested evidence types and sources
    - Available HATEOAS action names
    - Provide-evidence action presence check
    """
    dispute_id = data.get("dispute_id", "UNKNOWN")
    reason = data.get("reason", "UNKNOWN")
    status = data.get("status", "UNKNOWN")
    life_cycle_stage = data.get("dispute_life_cycle_stage") or data.get("life_cycle_stage") or "UNKNOWN"

    dispute_amount = data.get("dispute_amount") or {}
    amount = str(dispute_amount.get("value", "0.00"))
    currency = str(dispute_amount.get("currency_code", "USD"))

    seller_response_due_date = data.get("seller_response_due_date")

    # Parse requested evidences (only evidence_type and source, omitting buyer notes or document URLs)
    raw_evidences = data.get("evidences") or []
    requested_evidences: List[Dict[str, str]] = []
    for item in raw_evidences:
        if isinstance(item, dict):
            ev_type = item.get("evidence_type", "UNKNOWN")
            source = item.get("source", "UNKNOWN")
            # Only include if requested from seller or explicit evidence type
            if source == "REQUESTED_FROM_SELLER" or "REQUESTED" in source:
                requested_evidences.append({
                    "evidence_type": ev_type,
                    "source": source,
                })

    # Available HATEOAS actions
    links = data.get("links") or []
    available_actions: List[str] = []
    has_provide_evidence = False

    for link in links:
        if isinstance(link, dict):
            rel = link.get("rel")
            if rel:
                available_actions.append(rel)
                if rel in ("provide_evidence", "provide-evidence"):
                    has_provide_evidence = True

    return DisputeSummary(
        dispute_id=dispute_id,
        reason=reason,
        status=status,
        life_cycle_stage=life_cycle_stage,
        amount=amount,
        currency=currency,
        seller_response_due_date=seller_response_due_date,
        requested_evidences=requested_evidences,
        available_actions=available_actions,
        has_provide_evidence_action=has_provide_evidence,
    )


def format_dispute_summary(summary: DisputeSummary) -> str:
    """Format DisputeSummary into a human-readable, sanitized console report."""
    lines = [
        "=" * 60,
        "Docket - PayPal Sandbox Dispute Summary (Sanitized)",
        "=" * 60,
        f"Dispute ID:                 {summary.dispute_id}",
        f"Reason:                     {summary.reason}",
        f"Status:                     {summary.status}",
        f"Lifecycle Stage:            {summary.life_cycle_stage}",
        f"Disputed Amount:            {summary.amount} {summary.currency}",
        f"Seller Response Due Date:   {summary.seller_response_due_date or 'None / Not Applicable'}",
        "-" * 60,
        f"Provide-Evidence Allowed:   {'YES' if summary.has_provide_evidence_action else 'NO'}",
        f"Available HATEOAS Actions:  {', '.join(summary.available_actions) if summary.available_actions else 'None'}",
    ]

    if summary.requested_evidences:
        lines.append("Requested Evidence Requirements:")
        for idx, ev in enumerate(summary.requested_evidences, 1):
            lines.append(f"  {idx}. Type: {ev.get('evidence_type')} | Source: {ev.get('source')}")
    else:
        lines.append("Requested Evidence Requirements: None explicitly requested at this stage.")

    lines.append("=" * 60)
    return "\n".join(lines)


def format_dispute_list(items: List[Dict[str, Any]]) -> str:
    """Format multiple disputes into a concise table for test-case identification."""
    if not items:
        return "No disputes found for this merchant account in the Sandbox."

    lines = [
        "=" * 80,
        f"Docket - Available Sandbox Disputes ({len(items)} found)",
        "=" * 80,
        f"{'Dispute ID':<22} {'Reason':<30} {'Status':<25} {'Amount':<10}",
        "-" * 80,
    ]
    for d in items:
        d_id = d.get("dispute_id", "N/A")
        reason = d.get("reason", "N/A")
        status = d.get("status", "N/A")
        amt_obj = d.get("dispute_amount") or {}
        amt = f"{amt_obj.get('value', '0')} {amt_obj.get('currency_code', '')}"
        lines.append(f"{d_id:<22} {reason:<30} {status:<25} {amt:<10}")

    lines.append("=" * 80)
    lines.append("Tip: Set PAYPAL_DISPUTE_ID in your .env to target a specific dispute for detailed analysis.")
    return "\n".join(lines)


# ============================================================================
# Main Entry Point
# ============================================================================

def main(argv: Optional[List[str]] = None) -> int:
    """CLI execution for the read-only Sandbox spike."""
    parser = argparse.ArgumentParser(
        description="Docket Milestone 1 - Read-Only PayPal Sandbox Dispute Integration Spike"
    )
    parser.add_argument(
        "--dispute-id",
        dest="dispute_id",
        help="Specific dispute ID to inspect (overrides PAYPAL_DISPUTE_ID env var)",
    )
    parser.add_argument(
        "--env-file",
        dest="env_file",
        default=".env",
        help="Path to .env file (default: .env)",
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="Force listing disputes even if PAYPAL_DISPUTE_ID is set",
    )
    args = parser.parse_args(argv)

    # Load environment file if available
    env_path = Path(args.env_file)
    if env_path.is_file():
        load_dotenv(dotenv_path=env_path)
    elif args.env_file == ".env":
        load_dotenv()

    client_id = os.environ.get("PAYPAL_CLIENT_ID")
    client_secret = os.environ.get("PAYPAL_CLIENT_SECRET")
    raw_dispute_id = args.dispute_id or os.environ.get("PAYPAL_DISPUTE_ID")
    target_dispute_id = raw_dispute_id.strip() if raw_dispute_id and raw_dispute_id.strip() else None

    # Check for missing credentials
    if not client_id or not client_secret:
        print(
            "\n[LIVE INTEGRATION BLOCKED]\n"
            "PayPal Sandbox credentials (PAYPAL_CLIENT_ID and/or PAYPAL_CLIENT_SECRET) are not configured.\n"
            "To enable live Sandbox testing:\n"
            "  1. Copy .env.example to .env:  cp .env.example .env\n"
            "  2. Populate your sandbox API credentials from https://developer.paypal.com/dashboard/applications/sandbox\n"
            "  3. Re-run this script:  python scripts/spike_paypal_dispute.py\n",
            file=sys.stderr,
        )
        return 2

    print(f"Connecting to PayPal Sandbox ({SANDBOX_API_BASE})...")
    try:
        client = PayPalSandboxClient(client_id=client_id, client_secret=client_secret)
        # Attempt OAuth token retrieval
        client.get_access_token()
        print("[SUCCESS] OAuth 2.0 access token acquired successfully.")

        if target_dispute_id and not args.list:
            print(f"Fetching dispute details for ID: {target_dispute_id}...")
            dispute_data = client.get_dispute(target_dispute_id)
            summary = parse_dispute_summary(dispute_data)
            print("\n" + format_dispute_summary(summary) + "\n")
        else:
            print("Listing recent sandbox disputes for this account...")
            list_data = client.list_disputes(page_size=10)
            items = list_data.get("items", [])
            print("\n" + format_dispute_list(items) + "\n")

        return 0

    except ConfigurationError as e:
        print(f"[CONFIGURATION ERROR] {e}", file=sys.stderr)
        return 2
    except AuthenticationError as e:
        print(f"[AUTHENTICATION ERROR] {e}", file=sys.stderr)
        return 1
    except AuthorizationError as e:
        print(f"[AUTHORIZATION ERROR] {e}", file=sys.stderr)
        return 1
    except NotFoundError as e:
        print(f"[NOT FOUND ERROR] {e}", file=sys.stderr)
        return 1
    except RateLimitError as e:
        print(f"[RATE LIMIT ERROR] {e}", file=sys.stderr)
        return 1
    except PayPalServerError as e:
        print(f"[SERVER ERROR] {e}", file=sys.stderr)
        return 1
    except (NetworkError, TimeoutError) as e:
        print(f"[NETWORK ERROR] {e}", file=sys.stderr)
        return 1
    except MalformedResponseError as e:
        print(f"[MALFORMED RESPONSE] {e}", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"[UNEXPECTED ERROR] {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
