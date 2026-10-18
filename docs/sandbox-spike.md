# Docket - Milestone 1: PayPal Sandbox Integration Spike

## 1. Overview & Objectives

Docket is an evidence-reconciliation and controlled-decision system for PayPal disputes. This first milestone establishes a reliable, strictly read-only technical foundation by validating the PayPal Sandbox API integration without modifying live dispute records or deploying full application infrastructure.

### Milestone 1 Scope
- **Read-only validation:** Connects to `https://api-m.sandbox.paypal.com`.
- **Authentication:** Implements OAuth 2.0 client-credentials grant flow.
- **Dispute discovery:** Inspects a targeted dispute (`GET /v1/customer/disputes/{dispute_id}`) or queries the merchant's sandbox dispute list (`GET /v1/customer/disputes`).
- **Sanitization & Schema Audit:** Parses response structure, checking lifecycle stage, seller deadline, requested evidence requirements, and HATEOAS action links (`provide_evidence`, `send_message`, etc.) while redacting buyer PII.
- **Safety Boundaries:** Pure read-only operation. Does not create, escalate, accept, refund, or submit evidence to disputes.

---

## 2. Architecture & File Layout

```text
Docket/
├── docs/
│   └── sandbox-spike.md              # Technical documentation and verification guide
├── scripts/
│   ├── __init__.py
│   └── spike_paypal_dispute.py       # Standalone read-only diagnostic utility
├── tests/
│   ├── __init__.py
│   └── test_paypal_dispute.py        # Comprehensive mocked unit & integration test suite
├── .env.example                      # Template for sandbox API credentials
├── .gitignore                        # Excludes secrets, venvs, and cache files
├── pytest.ini                        # Test runner configuration
└── requirements-dev.txt              # Minimal development dependencies
```

---

## 3. Quick Start (Windows PowerShell)

### Step 1: Environment Setup
Ensure Python 3.10+ is available on your machine:
```powershell
# Create a local virtual environment
python -m venv .venv

# Activate the virtual environment
.\.venv\Scripts\Activate.ps1

# Upgrade pip and install development dependencies
python -m pip install --upgrade pip
pip install -r requirements-dev.txt
```

### Step 2: Configure Sandbox Credentials
Copy `.env.example` to `.env`:
```powershell
Copy-Item .env.example .env
```
Edit `.env` with your PayPal Developer Sandbox credentials obtained from [PayPal Developer Dashboard](https://developer.paypal.com/dashboard/applications/sandbox):
```ini
PAYPAL_CLIENT_ID=your_sandbox_client_id_here
PAYPAL_CLIENT_SECRET=your_sandbox_client_secret_here

# Optional: Set a specific dispute ID to query, or leave blank to list disputes
PAYPAL_DISPUTE_ID=
```

> **Security Note:** `.env` is explicitly ignored in `.gitignore`. Never commit API credentials or token secrets to version control.

### Step 3: Run Unit Tests
Execute the full test suite with coverage reporting:
```powershell
.\.venv\Scripts\python.exe -m pytest -v --cov=scripts --cov-report=term-missing
```

### Step 4: Run the Sandbox Diagnostic Spike
```powershell
# Default run (queries PAYPAL_DISPUTE_ID if set, or lists disputes)
.\.venv\Scripts\python.exe scripts/spike_paypal_dispute.py

# Query a specific dispute ID explicitly
.\.venv\Scripts\python.exe scripts/spike_paypal_dispute.py --dispute-id PP-R-AYP-10135034

# Force listing disputes even if PAYPAL_DISPUTE_ID is defined
.\.venv\Scripts\python.exe scripts/spike_paypal_dispute.py --list
```

---

## 4. PayPal API Details & Schema Inspection

### Endpoints Exercised
1. **OAuth 2.0 Client Credentials Token:**
   - **Method / Path:** `POST /v1/oauth2/token`
   - **Headers:** `Accept: application/json`, `Accept-Language: en_US`, `Authorization: Basic <base64(client_id:client_secret)>`
   - **Body:** `grant_type=client_credentials`
   - **Token Lifecycle:** Scoped, temporary Bearer token cached in-memory for subsequent calls. Never logged or exposed.

2. **List Merchant Disputes:**
   - **Method / Path:** `GET /v1/customer/disputes?page_size=10`
   - **Headers:** `Authorization: Bearer <access_token>`, `Content-Type: application/json`
   - **Purpose:** Enumerates existing sandbox disputes for identifying active test cases.

3. **Get Dispute Details:**
   - **Method / Path:** `GET /v1/customer/disputes/{dispute_id}`
   - **Headers:** `Authorization: Bearer <access_token>`, `Content-Type: application/json`
   - **Key Extracted Fields:**
     - `dispute_id`: Unique PayPal dispute reference.
     - `reason`: Dispute category (e.g., `MERCHANDISE_OR_SERVICE_NOT_RECEIVED`).
     - `status`: Current state (`WAITING_FOR_SELLER_RESPONSE`, `UNDER_REVIEW`, `RESOLVED`, etc.).
     - `dispute_life_cycle_stage`: `INQUIRY`, `CHARGEBACK`, `PRE_ARBITRATION`, or `ARBITRATION`.
     - `dispute_amount`: Currency and numeric value.
     - `seller_response_due_date`: Critical response deadline timestamp.
     - `evidences`: Array of requested evidence documents and sources (`REQUESTED_FROM_SELLER`).
     - `links`: HATEOAS actionable endpoints. Specifically checks for `rel: "provide_evidence"`.

### Data Sanitization & PII Protection
The utility strips out sensitive buyer data (such as `buyer.name`, `buyer.email`, internal transaction IDs, and note free-text) before terminal rendering to ensure auditable, privacy-preserving outputs.

---

## 5. Error Handling & Edge Cases

The utility implements a typed error hierarchy adhering to the workspace error-handling standard:

| Error Type | Trigger Conditions | Handling Behavior |
| :--- | :--- | :--- |
| `ConfigurationError` | Missing client ID or secret | Clean diagnostic exit with instructions; no crash |
| `AuthenticationError` | HTTP 401 on token or dispute endpoint | Sanitized message; credentials never leaked |
| `AuthorizationError` | HTTP 403 (unauthorized API permissions) | Explicit warning to review sandbox app permissions |
| `NotFoundError` | HTTP 404 (invalid dispute ID) | Clarifies non-existent dispute record |
| `RateLimitError` | HTTP 429 | Reports rate limit and parses `Retry-After` header |
| `PayPalServerError` | HTTP 5xx | Distinguishes gateway/upstream failures from client errors |
| `NetworkError` / `TimeoutError` | Socket dropped, DNS failure, request timeout | Reports connectivity timeout without freezing |
| `MalformedResponseError` | Non-JSON response or missing required schema keys | Protects against corrupted response payloads |

---

## 6. Verification Status

| Category | Status | Details |
| :--- | :--- | :--- |
| **Unit Test Suite** | **PASS (51/51)** | 100% of planned unit tests pass with 99% line coverage |
| **Mocked Scenarios** | **VERIFIED** | Auth, retrieval, listing, 401, 403, 404, 429, 500, 503, timeouts, network loss, malformed JSON, absent evidence, absent actions |
| **Live Sandbox API Auth** | **VERIFIED (SUCCESS)** | Connected to `https://api-m.sandbox.paypal.com/v1/oauth2/token` and retrieved valid OAuth 2.0 Bearer token |
| **Live Sandbox Dispute Listing** | **VERIFIED (SUCCESS)** | Queried `GET /v1/customer/disputes`; returned HTTP 200 OK (0 disputes found on this merchant account) |
| **Live Dispute Detail Schema** | **AWAITING SAMPLE CASE** | Live account currently has 0 disputes; specific INR dispute response schema inspection awaits a test dispute ID |


---

## 7. Next Actions (Milestone 2)

Once valid Sandbox credentials are provided and a sample dispute (specifically `MERCHANDISE_OR_SERVICE_NOT_RECEIVED`) is verified:
1. Ingest actual PayPal response payload to confirm exact sandbox schema behavior.
2. Build the evidence reconciliation engine against shipment records (handling our defining scenario: refusing to declare delivery verified when tracking is only "Label Created").
3. Implement controlled merchant confirmation gates prior to any evidence submission.
