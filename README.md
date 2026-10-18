# Docket

> **Controlled Evidence Reconciliation & Decision Engine for PayPal Disputes**  
> *PayPal AI Hackathon 2026 Entry*

[![Tests](https://img.shields.io/badge/tests-51%20passed%20(99%25%20coverage)-brightgreen)](tests/)
[![Python](https://img.shields.io/badge/python-3.12%20%7C%203.13%20%7C%203.14-blue)](https://www.python.org/)
[![License](https://img.shields.io/badge/license-MIT-blue)](LICENSE)

---

## 1. What Is Docket?

**Docket** is an AI-assisted, evidence-reconciliation and controlled-decision system designed for merchants managing payment disputes on PayPal.

When buyers file disputes (e.g. *Item Not Received* or *Significantly Not as Described*), merchants must locate shipping proofs, fulfillment logs, and communication records before strict response deadlines. Under pressure, merchants often submit incomplete documentation or assert unverified claims (such as claiming "Order was delivered" when carrier tracking only shows "Label Created").

Docket solves this by acting as a **controlled evidence intelligence layer**:
1. Connects directly to the **PayPal Disputes API** (`v1/customer/disputes`).
2. Reconciles dispute records against internal order databases and carrier tracking events.
3. Enforces a **deterministic code-level refusal barrier** that strictly blocks unsupported factual claims before submission.
4. Requires explicit **human merchant sign-off** on all evidence packages before dispatching to PayPal.

```
       +--------------------+       +---------------------+
       | PayPal Sandbox API |       | Merchant Data / ERP |
       +---------+----------+       +----------+----------+
                 |                             |
                 +--------------+--------------+
                                |
                                v
               +---------------------------------+
               |       Docket Core Engine        |
               |                                 |
               |  - Multi-Key Reconciliation     |
               |  - PII Redaction & Sanitization |
               |  - Structured Claim Extraction  |
               +----------------+----------------+
                                |
                                v
               +---------------------------------+
               |   DETERMINISTIC REFUSAL BARRIER  |
               |   (Hard-coded rule verification |
               |    Unverified claims = REFUSED) |
               +----------------+----------------+
                                |
                                v
               +---------------------------------+
               |  Human-in-the-Loop Review UI    |
               |  (FastHTML + HTMX + AG Grid)    |
               +----------------+----------------+
                                | Merchant Sign-off
                                v
               +---------------------------------+
               | PayPal Evidence Dispatcher      |
               | (POST provide_evidence)         |
               +---------------------------------+
```

---

## 2. Core Invariants

- **Ground-Truth Traceability:** Every factual assertion submitted to PayPal must point directly to a verifiable source record (carrier tracking checkpoint, warehouse scan timestamp, or order ledger).
- **Deterministic Refusal Barrier:** If evidence is missing or contradictory (e.g., carrier tracking shows "In Transit" but the merchant wants to claim "Delivered"), Docket strictly refuses to claim delivery. Code-level rules override any AI model output.
- **Human-in-the-Loop Sign-off:** Docket never automatically submits dispute responses without explicit merchant review and verification of the evidence package.
- **PII Protection:** All buyer personal identifying information (emails, names, phone numbers) is redacted in logs and diagnostic outputs.

---

## 3. Project Structure

```text
Docket/
├── .agents/                      # Agent rules, workflows, and skills
├── docs/                         # Architecture, product specs, and roadmaps
│   ├── ARCHITECTURE.md           # System design & component contracts
│   ├── DECISIONS.md              # Architectural Decision Records (ADRs)
│   ├── PRODUCT_BRIEF.md          # Product definition & problem statement
│   ├── PROJECT_STATUS.md         # Milestone status & live evidence ledger
│   ├── ROADMAP.md                # 5-phase engineering roadmap
│   ├── sandbox-spike.md          # Technical documentation of the PayPal API spike
│   └── fixtures/
│       └── real_sandbox_dispute_inr.json  # Sanitized live PayPal Sandbox INR dispute
├── scripts/
│   ├── spike_paypal_dispute.py   # Standalone read-only diagnostic utility
│   └── create_test_order.py      # Automated sandbox order creation & capture
├── tests/
│   └── test_paypal_dispute.py    # 51 unit tests with 99% test coverage
├── .env.example                  # Template for PayPal credentials
├── .gitignore                    # Air-tight security & secrets exclusion
├── pytest.ini                    # Test runner configuration
├── requirements-dev.txt          # Python dependencies
└── README.md                     # Project overview & documentation
```

---

## 4. Quickstart

### Prerequisites
- Python 3.12+ (tested through Python 3.14)
- PayPal Developer Sandbox Account (US Business & Personal accounts)

### Setup

```bash
# Clone the repository
git clone https://github.com/OmkarD09/Docket.git
cd Docket

# Create and activate virtual environment
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install development dependencies
pip install -r requirements-dev.txt

# Configure environment variables
cp .env.example .env
```

Edit `.env` with your PayPal Sandbox credentials:
```ini
PAYPAL_CLIENT_ID=your_sandbox_client_id
PAYPAL_CLIENT_SECRET=your_sandbox_client_secret
PAYPAL_DISPUTE_ID=PP-R-NKI-10193390  # Or leave blank to inspect all disputes
```

### Running Tests

```bash
# Run all 51 tests with coverage
pytest --cov=scripts --cov-report=term-missing
```

### Running the Read-Only Diagnostic CLI

```bash
# List available sandbox disputes
python scripts/spike_paypal_dispute.py

# Inspect a specific dispute in detail
python scripts/spike_paypal_dispute.py --dispute-id PP-R-NKI-10193390

# Output raw JSON payload (redacted)
python scripts/spike_paypal_dispute.py --dispute-id PP-R-NKI-10193390 --raw
```

---

## 5. Live Sandbox Verification

Docket has been verified against live PayPal Sandbox infrastructure:
- **Sandbox Order:** Created $25.00 USD order `09P720153W688771J`, approved via buyer sandbox flow, and captured (`4R073105U90937213`).
- **Dispute Lifecycle State:** Filed live INR dispute **`PP-R-NKI-10193390`**, transitioning from `INQUIRY` to `WAITING_FOR_SELLER_RESPONSE`.
- **HATEOAS Invariant:** Live PayPal response confirmed required proof `PROOF_OF_FULFILLMENT` and dynamically exposed the `provide_evidence` action link with a 20-day seller response window.

---

## 6. Technology Stack

| Layer | Technology | Rationale |
|---|---|---|
| **Language** | Python 3.12+ | Clean typing, rich async ecosystem, Pydantic integration |
| **Backend & UI** | FastHTML + HTMX | Single-language stack, hypermedia-driven dynamic UI without heavy build steps |
| **Grid / Table** | AG Grid | Enterprise-grade dispute queue triage, sorting, and multi-key filtering |
| **Data Validation** | Pydantic v2 | Strict schema enforcement for disputes, orders, and evidence claims |
| **AI Extraction** | Gemini 2.5 Flash / Claude 3.5 Sonnet | Fast structured extraction of evidence facts and contradiction detection |
| **Integrations** | PayPal REST APIs | Disputes API (`v1`), Orders API (`v2`) |

---

## 7. License

MIT License. See [LICENSE](LICENSE) for details.
