"""Comprehensive Tests for Docket Merchant Authentication & Session Enforcement.

Covers:
1. Demo persona catalog inspection
2. Cryptographic demo session issuance and HttpOnly cookie binding
3. Protected endpoint rejection for unauthenticated callers (401)
4. Expired session rejection (401)
5. Tampered cryptographic HMAC signature rejection (401)
6. Session revocation via sign-out (401)
7. Dual-channel authentication (Cookie & Bearer Header)
8. Anti-impersonation / caller spoofing rejection (403)
9. Honest credential login validation & error states
10. Cryptographic audit trail actor attribution strictly from authenticated principal
"""

from datetime import datetime, timedelta, timezone
from decimal import Decimal
import json
import pytest
from fastapi.testclient import TestClient
from unittest.mock import MagicMock, patch

from docket.api.app import create_app
from docket.auth.service import AuthService


@pytest.fixture
def auth_app_and_client(tmp_path):
    audit_file = tmp_path / "test_auth_audit.jsonl"
    app = create_app(audit_log_path=str(audit_file), secret_key="test-secret-key-for-docket-auth-tests-1234")
    client = TestClient(app)
    return app, client


def test_auth_profiles_catalog(auth_app_and_client):
    """Verify demo persona catalog returns configured merchant profiles."""
    _, client = auth_app_and_client
    resp = client.get("/api/auth/profiles")
    assert resp.status_code == 200
    profiles = resp.json()
    assert isinstance(profiles, list)
    assert len(profiles) >= 3

    ids = [p["profile_id"] for p in profiles]
    assert "ops" in ids or "merchant_ops_primary" in ids
    assert "supervisor" in ids or "merchant_supervisor_admin" in ids


def test_demo_session_creation(auth_app_and_client):
    """Verify backend issues valid HMAC session token and sets HttpOnly cookie."""
    _, client = auth_app_and_client
    resp = client.post("/api/auth/demo-session", json={"profile_id": "merchant_ops_primary"})
    assert resp.status_code == 200
    data = resp.json()

    assert data["success"] is True
    assert "token" in data
    assert data["merchant"]["merchant_user_id"] == "merchant_ops_primary"
    assert data["merchant"]["role"] == "DISPUTE_OPERATIONS_LEAD"
    assert data["environment"] == "PAYPAL_SANDBOX_REST_V1"

    # Verify HttpOnly cookie was set
    assert "docket_session" in client.cookies
    assert client.cookies["docket_session"] == data["token"]


def test_get_current_merchant_me(auth_app_and_client):
    """Verify /api/auth/me resolves current authenticated merchant principal."""
    _, client = auth_app_and_client
    # Prior to session -> 401
    unauth_resp = client.get("/api/auth/me")
    assert unauth_resp.status_code == 401

    # Issue session
    client.post("/api/auth/demo-session", json={"profile_id": "merchant_supervisor_admin"})
    me_resp = client.get("/api/auth/me")
    assert me_resp.status_code == 200
    me_data = me_resp.json()
    assert me_data["merchant_user_id"] == "merchant_supervisor_admin"
    assert me_data["role"] == "RISK_SUPERVISOR"


def test_unauthenticated_requests_rejected_with_401(auth_app_and_client):
    """Verify all sensitive endpoints strictly reject unauthenticated callers."""
    _, client = auth_app_and_client
    dispute_id = "PP-R-NKI-10193390"

    # 1. Ticket generation
    r1 = client.post(f"/api/disputes/{dispute_id}/ticket")
    assert r1.status_code == 401
    assert "Authentication required" in r1.json()["detail"]

    # 2. Authorize
    r2 = client.post(f"/api/disputes/{dispute_id}/authorize", json={"decision": "APPROVE"})
    assert r2.status_code == 401

    # 3. Dispatch
    r3 = client.post(f"/api/disputes/{dispute_id}/dispatch", json={"idempotency_key": "test_idemp"})
    assert r3.status_code == 401

    # 4. Archive
    r4 = client.post(f"/api/disputes/{dispute_id}/archive")
    assert r4.status_code == 401

    # 5. Refresh
    r5 = client.post(f"/api/disputes/{dispute_id}/refresh")
    assert r5.status_code == 401

    # 6. Eval Run
    r6 = client.post("/api/eval/run")
    assert r6.status_code == 401


def test_bearer_token_authorization(auth_app_and_client):
    """Verify clients can authenticate via Authorization: Bearer header without cookies."""
    app, _ = auth_app_and_client
    auth_service = AuthService(secret_key="test-secret-key-for-docket-auth-tests-1234")
    merchant, token = auth_service.create_session("merchant_ops_primary")

    # Fresh client without cookies
    clean_client = TestClient(app)
    headers = {"Authorization": f"Bearer {token}"}

    resp = clean_client.get("/api/auth/me", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["merchant_user_id"] == "merchant_ops_primary"

    # Call protected ticket endpoint
    t_resp = clean_client.post("/api/disputes/PP-R-NKI-10193390/ticket", headers=headers)
    assert t_resp.status_code == 200


def test_expired_session_rejected(auth_app_and_client):
    """Verify tokens with past expiration timestamp are rejected with 401."""
    app, client = auth_app_and_client
    auth_service = AuthService(secret_key="test-secret-key-for-docket-auth-tests-1234")
    # Issue token with negative TTL
    merchant, expired_token = auth_service.create_session("merchant_ops_primary", ttl_seconds=-100)

    clean_client = TestClient(app)
    resp = clean_client.get("/api/auth/me", headers={"Authorization": f"Bearer {expired_token}"})
    assert resp.status_code == 401
    assert "expired" in resp.json()["detail"].lower()


def test_tampered_hmac_signature_rejected(auth_app_and_client):
    """Verify cryptographically tampered session envelopes fail verification."""
    app, client = auth_app_and_client
    auth_service = AuthService(secret_key="test-secret-key-for-docket-auth-tests-1234")
    _, valid_token = auth_service.create_session("merchant_ops_primary")

    parts = valid_token.split(".")
    # Tamper with the user ID part while keeping signature
    tampered_parts = [parts[0], "hacker_attacker_id", parts[2], parts[3]]
    tampered_token = ".".join(tampered_parts)

    clean_client = TestClient(app)
    resp = clean_client.get("/api/auth/me", headers={"Authorization": f"Bearer {tampered_token}"})
    assert resp.status_code == 401
    assert "tampered" in resp.json()["detail"].lower() or "invalid" in resp.json()["detail"].lower()


def test_logout_and_session_revocation(auth_app_and_client):
    """Verify sign-out clears cookie and marks session as revoked on server."""
    _, client = auth_app_and_client
    login_resp = client.post("/api/auth/demo-session", json={"profile_id": "merchant_ops_primary"})
    token = login_resp.json()["token"]

    assert client.get("/api/auth/me").status_code == 200

    # Call logout
    logout_resp = client.post("/api/auth/logout")
    assert logout_resp.status_code == 200
    assert logout_resp.json()["success"] is True

    # Immediate /me call fails
    assert client.get("/api/auth/me").status_code == 401

    # Attempting to reuse revoked token via Bearer header also fails
    reuse_resp = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert reuse_resp.status_code == 401
    assert "revoked" in reuse_resp.json()["detail"].lower()


def test_anti_impersonation_rejection(auth_app_and_client):
    """Verify merchant cannot impersonate another identity by sending a different merchant_user_id."""
    _, client = auth_app_and_client
    # Authenticate as merchant_ops_primary
    client.post("/api/auth/demo-session", json={"profile_id": "merchant_ops_primary"})

    # Attempt to authorize using merchant_supervisor_admin in request body
    disp_id = "PP-R-NKI-10193390"
    client.post(f"/api/disputes/{disp_id}/ticket")

    spoofed_resp = client.post(
        f"/api/disputes/{disp_id}/authorize",
        json={
            "merchant_user_id": "merchant_supervisor_admin",
            "decision": "APPROVE",
        },
    )
    assert spoofed_resp.status_code == 403
    assert "identity mismatch" in spoofed_resp.json()["detail"].lower()

    # Attempt to dispatch using spoofed identity
    spoofed_dispatch = client.post(
        f"/api/disputes/{disp_id}/dispatch",
        json={
            "merchant_user_id": "merchant_admin",
            "idempotency_key": "spoof_key_01",
        },
    )
    assert spoofed_dispatch.status_code == 403
    assert "identity mismatch" in spoofed_dispatch.json()["detail"].lower()


def test_credential_login_honest_flow(auth_app_and_client):
    """Verify honest credential verification with predefined demo credentials."""
    _, client = auth_app_and_client

    # 1. Valid credentials
    resp = client.post(
        "/api/auth/login",
        json={"email": "ops@merchant.example.com", "password": "docket2026"},
    )
    assert resp.status_code == 200
    assert resp.json()["merchant"]["merchant_user_id"] == "merchant_ops_primary"

    # 2. Invalid password
    bad_pass = client.post(
        "/api/auth/login",
        json={"email": "ops@merchant.example.com", "password": "wrongpassword!"},
    )
    assert bad_pass.status_code == 401
    assert "Invalid password" in bad_pass.json()["detail"]

    # 3. Nonexistent account
    no_acct = client.post(
        "/api/auth/login",
        json={"email": "fake@unknown.com", "password": "docket2026"},
    )
    assert no_acct.status_code == 401
    assert "No merchant account" in no_acct.json()["detail"]


def test_audit_event_actor_strictly_derived_from_principal(auth_app_and_client):
    """Verify that state-changing actions record the exact authenticated merchant as actor."""
    _, client = auth_app_and_client
    # Authenticate as supervisor
    client.post("/api/auth/demo-session", json={"profile_id": "merchant_supervisor_admin"})

    disp_id = "PP-R-NKI-10193390"
    client.post(f"/api/disputes/{disp_id}/ticket")
    client.post(
        f"/api/disputes/{disp_id}/authorize",
        json={"decision": "APPROVE", "notes": "Approved by supervisor"},
    )

    trail_resp = client.get(f"/api/disputes/{disp_id}/lifecycle")
    assert trail_resp.status_code == 200
    events = trail_resp.json()["events"]

    auth_grant = next((e for e in events if e["event_type"] == "APPROVAL_GRANTED"), None)
    assert auth_grant is not None
    assert auth_grant["actor"] == "merchant_supervisor_admin"

