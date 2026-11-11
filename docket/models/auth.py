"""Docket Merchant Authentication & Session Domain Models.

Cryptographically secured session principals for merchant dispute operations.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, Optional
from pydantic import BaseModel, Field


class AuthenticatedMerchant(BaseModel):
    """Authenticated merchant principal derived strictly from server-validated sessions."""
    merchant_user_id: str
    email: str
    display_name: str
    role: str
    session_id: str
    issued_at: datetime
    expires_at: datetime

    def is_expired(self) -> bool:
        from datetime import timezone
        return datetime.now(timezone.utc) >= self.expires_at


class DemoMerchantProfile(BaseModel):
    """Pre-configured demo merchant persona available for instant workspace access."""
    profile_id: str
    merchant_user_id: str
    email: str
    display_name: str
    role: str
    description: str


class DemoSessionRequest(BaseModel):
    """Request payload to issue a demo merchant session."""
    profile_id: Optional[str] = "merchant_ops_primary"


class LoginRequest(BaseModel):
    """Request payload for credential-based authentication."""
    email: Optional[str] = None
    password: Optional[str] = None
    profile_id: Optional[str] = None


class AuthSessionResponse(BaseModel):
    """Response returned upon successful session issuance."""
    success: bool
    merchant: AuthenticatedMerchant
    token: str
    expires_at: str
    environment: str = "PAYPAL_SANDBOX_REST_V1"
