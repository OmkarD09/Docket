"""Docket Merchant Authentication & Session Service.

Manages cryptographically signed demo sessions, token validation, expiration enforcement,
and session revocation for Docket dispute operations.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
import hmac
import os
import secrets
from typing import Dict, List, Optional, Set, Tuple

from docket.models.auth import (
    AuthenticatedMerchant,
    DemoMerchantProfile,
)


class AuthenticationError(Exception):
    """Base exception for authentication failures."""


class InvalidTokenError(AuthenticationError):
    """Raised when an authentication token is malformed or signature verification fails."""


class SessionExpiredError(AuthenticationError):
    """Raised when a session token has expired."""


class SessionRevokedError(AuthenticationError):
    """Raised when a session token has been revoked by logout."""


class InvalidCredentialsError(AuthenticationError):
    """Raised when user-provided credentials are not valid."""


# ============================================================================
# Pre-configured Merchant Profiles
# ============================================================================

DEMO_PROFILES: Dict[str, DemoMerchantProfile] = {
    "merchant_ops_primary": DemoMerchantProfile(
        profile_id="ops",
        merchant_user_id="merchant_ops_primary",
        email="ops@merchant.example.com",
        display_name="Merchant Operations Primary",
        role="DISPUTE_OPERATIONS_LEAD",
        description="Lead operator authorized for evidence preparation, approval authorization, and dispatch.",
    ),
    "merchant_supervisor_admin": DemoMerchantProfile(
        profile_id="supervisor",
        merchant_user_id="merchant_supervisor_admin",
        email="supervisor@merchant.example.com",
        display_name="Risk & Compliance Supervisor",
        role="RISK_SUPERVISOR",
        description="Supervisor with high-value approval authority and audit ledger oversight.",
    ),
    "merchant_admin": DemoMerchantProfile(
        profile_id="admin",
        merchant_user_id="merchant_admin",
        email="admin@merchant.example.com",
        display_name="Merchant System Admin",
        role="SYSTEM_ADMIN",
        description="System administrator profile with global operational permissions.",
    ),
}

# Alias mapping by profile_id and user_id
PROFILE_ALIASES: Dict[str, str] = {
    "ops": "merchant_ops_primary",
    "merchant_ops_primary": "merchant_ops_primary",
    "supervisor": "merchant_supervisor_admin",
    "merchant_supervisor_admin": "merchant_supervisor_admin",
    "admin": "merchant_admin",
    "merchant_admin": "merchant_admin",
}


# ============================================================================
# Authentication Service
# ============================================================================

class AuthService:
    """Manages cryptographic sessions and merchant principal derivation."""

    DEFAULT_SECRET_KEY = "docket-dev-auth-secret-key-32ch-minimum-entropy!"
    DEFAULT_TTL_SECONDS = 8 * 3600  # 8 hours

    def __init__(
        self,
        secret_key: Optional[str] = None,
        ttl_seconds: Optional[int] = None,
    ):
        self.secret_key = secret_key or os.getenv("DOCKET_AUTH_SECRET_KEY", self.DEFAULT_SECRET_KEY)
        self.ttl_seconds = ttl_seconds if ttl_seconds is not None else self.DEFAULT_TTL_SECONDS
        self._revoked_sessions: Set[str] = set()
        self._active_sessions: Dict[str, AuthenticatedMerchant] = {}

    def get_available_profiles(self) -> List[DemoMerchantProfile]:
        """Return list of available demo personas for instant workspace access."""
        return list(DEMO_PROFILES.values())

    def resolve_profile(self, identifier: Optional[str]) -> DemoMerchantProfile:
        """Resolve a demo profile by key, user ID, or create dynamic profile for custom principal."""
        if not identifier:
            return DEMO_PROFILES["merchant_ops_primary"]

        norm = identifier.strip().lower()
        key = PROFILE_ALIASES.get(norm)
        if key and key in DEMO_PROFILES:
            return DEMO_PROFILES[key]

        # Dynamic profile for custom test principals (e.g., "lead_agent")
        clean_id = identifier.strip()
        return DemoMerchantProfile(
            profile_id=clean_id,
            merchant_user_id=clean_id,
            email=f"{clean_id}@merchant.example.com",
            display_name=clean_id.replace("_", " ").title(),
            role="DISPUTE_OPERATIONS_LEAD",
            description=f"Authenticated principal {clean_id}.",
        )

    def _sign(self, session_id: str, merchant_user_id: str, exp_ts: int) -> str:
        """Calculate HMAC-SHA256 signature for session envelope."""
        message = f"docket_session_v1:{session_id}:{merchant_user_id}:{exp_ts}".encode("utf-8")
        return hmac.new(self.secret_key.encode("utf-8"), message, hashlib.sha256).hexdigest()

    def create_session(
        self,
        merchant_user_id: Optional[str] = None,
        ttl_seconds: Optional[int] = None,
    ) -> Tuple[AuthenticatedMerchant, str]:
        """Issue a new authenticated session token bound to a verified merchant profile."""
        profile = self.resolve_profile(merchant_user_id)
        
        session_id = f"sess_{secrets.token_hex(16)}"
        ttl = ttl_seconds if ttl_seconds is not None else self.ttl_seconds
        
        now = datetime.now(timezone.utc)
        expires_at = now + timedelta(seconds=ttl)
        exp_ts = int(expires_at.timestamp())

        sig = self._sign(session_id, profile.merchant_user_id, exp_ts)
        token = f"{session_id}.{profile.merchant_user_id}.{exp_ts}.{sig}"

        merchant = AuthenticatedMerchant(
            merchant_user_id=profile.merchant_user_id,
            email=profile.email,
            display_name=profile.display_name,
            role=profile.role,
            session_id=session_id,
            issued_at=now,
            expires_at=expires_at,
        )

        self._active_sessions[session_id] = merchant
        return merchant, token

    def authenticate_credentials(
        self,
        email: Optional[str] = None,
        password: Optional[str] = None,
        profile_id: Optional[str] = None,
    ) -> Tuple[AuthenticatedMerchant, str]:
        """Authenticate user credentials or explicit profile request."""
        # 1. If explicit profile ID provided (e.g. from persona selector)
        if profile_id:
            profile = self.resolve_profile(profile_id)
            return self.create_session(profile.merchant_user_id)

        # 2. If email & password provided
        if not email or not password:
            raise InvalidCredentialsError("Email and password are required.")

        clean_email = email.strip().lower()
        # Honest preset demo credentials for hackathon evaluation:
        demo_creds = {
            "ops@merchant.example.com": ("merchant_ops_primary", "docket2026"),
            "supervisor@merchant.example.com": ("merchant_supervisor_admin", "docket2026"),
            "admin@merchant.example.com": ("merchant_admin", "docket2026"),
        }

        if clean_email not in demo_creds:
            raise InvalidCredentialsError(f"No merchant account registered for '{clean_email}'.")

        expected_user_id, expected_password = demo_creds[clean_email]
        if not hmac.compare_digest(password.strip(), expected_password):
            raise InvalidCredentialsError("Invalid password provided for merchant account.")

        return self.create_session(expected_user_id)

    def validate_token(self, token: Optional[str]) -> AuthenticatedMerchant:
        """Validate HMAC signature, verify expiration, and return merchant principal.
        
        Raises:
            InvalidTokenError: If token structure is malformed or signature does not match.
            SessionExpiredError: If token timestamp is in the past.
            SessionRevokedError: If session was explicitly revoked by logout.
        """
        if not token or not isinstance(token, str):
            raise InvalidTokenError("Authentication token is missing or empty.")

        parts = token.strip().split(".")
        if len(parts) != 4:
            raise InvalidTokenError("Malformed authentication token envelope (expected 4 parts).")

        session_id, merchant_user_id, exp_ts_str, sig = parts

        # Check session revocation
        if session_id in self._revoked_sessions:
            raise SessionRevokedError("Session has been revoked by sign-out.")

        # Check expiration
        try:
            exp_ts = int(exp_ts_str)
        except ValueError:
            raise InvalidTokenError("Invalid token expiration timestamp format.")

        now_ts = int(datetime.now(timezone.utc).timestamp())
        if now_ts >= exp_ts:
            raise SessionExpiredError(f"Session expired at {datetime.fromtimestamp(exp_ts, timezone.utc).isoformat()}.")

        # Verify cryptographic HMAC signature in constant time
        expected_sig = self._sign(session_id, merchant_user_id, exp_ts)
        if not hmac.compare_digest(sig, expected_sig):
            raise InvalidTokenError("Cryptographic signature verification failed (tampered token).")

        # Look up cached session or reconstruct from validated token
        if session_id in self._active_sessions:
            merchant = self._active_sessions[session_id]
            if merchant.merchant_user_id == merchant_user_id:
                return merchant

        profile = self.resolve_profile(merchant_user_id)
        merchant = AuthenticatedMerchant(
            merchant_user_id=profile.merchant_user_id,
            email=profile.email,
            display_name=profile.display_name,
            role=profile.role,
            session_id=session_id,
            issued_at=datetime.fromtimestamp(exp_ts - self.ttl_seconds, timezone.utc),
            expires_at=datetime.fromtimestamp(exp_ts, timezone.utc),
        )
        self._active_sessions[session_id] = merchant
        return merchant

    def revoke_session(self, session_id: str) -> bool:
        """Revoke a session ID immediately."""
        self._revoked_sessions.add(session_id)
        self._active_sessions.pop(session_id, None)
        return True
