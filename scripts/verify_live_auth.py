"""Live Verification Script for Docket Merchant Authentication & Protection.

Tests:
- Profiles listing
- 401 Unauthenticated protection on sensitive endpoints
- Demo session creation and cookie preservation
- Anti-impersonation rejection (403)
- Session persistence
- Honest credential login and error handling
- Sign-out revocation
"""

import sys
from fastapi.testclient import TestClient
from docket.api.app import create_app

def run_verification():
    print("=== DOCKET MERCHANT AUTHENTICATION VERIFICATION SUITE ===")
    app = create_app()
    client = TestClient(app)

    print("\n--- 1. Testing Unauthenticated Access Rejection ---")
    # Try /api/auth/me
    r_me = client.get("/api/auth/me")
    print(f"GET /api/auth/me -> {r_me.status_code} (Expected: 401)")
    assert r_me.status_code == 401, f"Expected 401, got {r_me.status_code}"

    # Try sensitive ticket creation
    r_ticket = client.post("/api/disputes/PP-R-NKI-10193390/ticket")
    print(f"POST /api/disputes/.../ticket -> {r_ticket.status_code} (Expected: 401)")
    assert r_ticket.status_code == 401, f"Expected 401, got {r_ticket.status_code}"

    # Try dispatch
    r_dispatch = client.post("/api/disputes/PP-R-NKI-10193390/dispatch", json={"idempotency_key": "test"})
    print(f"POST /api/disputes/.../dispatch -> {r_dispatch.status_code} (Expected: 401)")
    assert r_dispatch.status_code == 401

    # Try archive
    r_archive = client.post("/api/disputes/PP-R-NKI-10193390/archive")
    print(f"POST /api/disputes/.../archive -> {r_archive.status_code} (Expected: 401)")
    assert r_archive.status_code == 401

    print("\n--- 2. Testing Profiles Listing ---")
    r_prof = client.get("/api/auth/profiles")
    assert r_prof.status_code == 200
    profiles = r_prof.json()
    print(f"Loaded {len(profiles)} demo profiles:")
    for p in profiles:
        print(f"  • {p['display_name']} ({p['merchant_user_id']}) - Role: {p['role']}")

    print("\n--- 3. Testing 1-Click Demo Session Issuance (Judge Flow) ---")
    r_demo = client.post("/api/auth/demo-session", json={"profile_id": "merchant_ops_primary"})
    assert r_demo.status_code == 200
    demo_data = r_demo.json()
    print(f"Issued session for: {demo_data['merchant']['display_name']}")
    print(f"Token prefix: {demo_data['token'][:24]}...")
    print(f"Environment: {demo_data['environment']}")
    assert "docket_session" in client.cookies, "HttpOnly docket_session cookie must be set"

    print("\n--- 4. Testing Identity Derivation via /api/auth/me ---")
    r_me_auth = client.get("/api/auth/me")
    assert r_me_auth.status_code == 200
    me = r_me_auth.json()
    print(f"Resolved principal: {me['display_name']} ({me['email']})")
    assert me["merchant_user_id"] == "merchant_ops_primary"

    print("\n--- 5. Testing Protected Operations with Authenticated Session ---")
    r_ticket_auth = client.post("/api/disputes/PP-R-NKI-10193390/ticket")
    print(f"POST ticket -> {r_ticket_auth.status_code}")
    assert r_ticket_auth.status_code == 200

    print("\n--- 6. Testing Anti-Impersonation Protection (403 Rejection) ---")
    r_spoof = client.post(
        "/api/disputes/PP-R-NKI-10193390/authorize",
        json={"merchant_user_id": "merchant_supervisor_admin", "decision": "APPROVE"},
    )
    print(f"Spoofed authorize (user sending supervisor ID) -> {r_spoof.status_code} (Expected: 403)")
    assert r_spoof.status_code == 403, f"Expected 403, got {r_spoof.status_code}"
    print(f"Detail: {r_spoof.json()['detail']}")

    print("\n--- 7. Testing Legitimate Authorization Matching Principal ---")
    r_legit_auth = client.post(
        "/api/disputes/PP-R-NKI-10193390/authorize",
        json={"decision": "APPROVE", "notes": "Approved by verified operations lead"},
    )
    print(f"Legitimate authorize -> {r_legit_auth.status_code}")
    assert r_legit_auth.status_code == 200

    print("\n--- 8. Testing Sign Out Revocation ---")
    r_logout = client.post("/api/auth/logout")
    print(f"POST /api/auth/logout -> {r_logout.status_code}")
    assert r_logout.status_code == 200

    r_me_after = client.get("/api/auth/me")
    print(f"GET /api/auth/me after logout -> {r_me_after.status_code} (Expected: 401)")
    assert r_me_after.status_code == 401

    print("\n--- 9. Testing Honest Credential Login ---")
    # Invalid password
    r_bad = client.post(
        "/api/auth/login",
        json={"email": "ops@merchant.example.com", "password": "wrongpassword"},
    )
    print(f"Login with bad password -> {r_bad.status_code} (Expected: 401)")
    assert r_bad.status_code == 401

    # Valid demo credentials
    r_cred = client.post(
        "/api/auth/login",
        json={"email": "ops@merchant.example.com", "password": "docket2026"},
    )
    print(f"Login with valid credentials -> {r_cred.status_code}")
    assert r_cred.status_code == 200
    print(f"Signed in as: {r_cred.json()['merchant']['display_name']}")

    print("\n=======================================================")
    print("ALL LIVE MERCHANT AUTHENTICATION CHECKS PASSED GREEN!")
    print("=======================================================")

if __name__ == "__main__":
    run_verification()
