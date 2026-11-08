"""Docket AI Semantic Extraction & Verification Live Demonstration.

Demonstrates the 7 required stages:
1. Original unstructured buyer message.
2. Selected AI provider and model.
3. Extracted structured claims.
4. Citation verification results.
5. Cross-source contradictions.
6. Deterministic policy decision.
7. Recommended next step.

If GEMINI_API_KEY is present in environment, executes an authentic live model call.
If absent, demonstrates offline execution and mocked live-provider verification, clearly distinguished.
"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
import json
import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

# Ensure root directory is on sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from docket.ai.citation_verifier import VerbatimCitationVerifier
from docket.ai.contradiction import ContradictionDetector
from docket.ai.deterministic import DeterministicFactExtractor
from docket.ai.factory import get_fact_extractor
from docket.ai.prompt_guard import PromptInjectionGuard
from docket.ai.provider_gemini import GeminiFactExtractor
from docket.ai.workflow import SemanticExtractionWorkflow, SemanticWorkflowResult
from docket.models.dispute import (
    DisputeCase,
    DisputeLifecycleStage,
    DisputeReason,
    DisputeStatus,
    HATEOASLink,
    Money,
)
from docket.models.evidence import (
    Address,
    ClaimType,
    ExtractedClaim,
    OrderRecord,
    ShipmentRecord,
    SourceCitation,
    SourceType,
    TrackingStatus,
    VerificationStatus,
)
from docket.models.reconciliation import ReconciledDisputeBundle, ReconciliationStatus
from docket.policy.engine import PolicyEngine


def build_synthetic_fixture():
    """Create a realistic, synthetic, non-sensitive dispute fixture with carrier & order records."""
    dispute = DisputeCase(
        dispute_id="PP-D-DEMO-2026",
        reason=DisputeReason.MERCHANDISE_OR_SERVICE_NOT_RECEIVED,
        lifecycle_stage=DisputeLifecycleStage.CHARGEBACK,
        status=DisputeStatus.WAITING_FOR_SELLER_RESPONSE,
        dispute_amount=Money(value=Decimal("89.50"), currency_code="USD"),
        requested_evidence_types=["PROOF_OF_DELIVERY"],
        seller_response_due_date=datetime(2026, 12, 1, 12, 0, tzinfo=timezone.utc),
        available_hateoas_actions=[
            HATEOASLink(
                href="https://api-m.sandbox.paypal.com/v1/customer/disputes/PP-D-DEMO-2026/provide-evidence",
                rel="provide_evidence",
                method="POST",
            )
        ],
        disputed_transaction_id="TX-DEMO-7711",
        seller_transaction_id="TX-DEMO-7711",
        buyer_email="customer.demo@example.com",
        buyer_name="Jordan Reed",
        dispute_create_time=datetime(2026, 10, 28, 11, 0, tzinfo=timezone.utc),
        raw_messages=[
            {
                "posted_by": "BUYER",
                "time_posted": "2026-10-28T11:00:00Z",
                "content": "I ordered this merchandise 12 days ago. Tracking only shows label created with USPS, but no package was ever shipped.",
            }
        ],
    )

    order = OrderRecord(
        order_id="ORD-DEMO-9901",
        paypal_transaction_id="TX-DEMO-7711",
        order_timestamp=datetime(2026, 10, 16, 14, 30, tzinfo=timezone.utc),
        gross_amount=Money(value=Decimal("89.50"), currency_code="USD"),
        customer_email="customer.demo@example.com",
        customer_name="Jordan Reed",
        shipping_address=Address(
            recipient_name="Jordan Reed",
            line1="742 Evergreen Terrace",
            city="Springfield",
            state_or_province="IL",
            postal_code="62704",
            country_code="US",
        ),
        tracking_numbers=["9400111899223197000111"],
        items=[{"item_name": "Premium Keyboard Kit", "quantity": 1}],
    )

    shipment = ShipmentRecord(
        internal_order_id="ORD-DEMO-9901",
        tracking_number="9400111899223197000111",
        carrier_name="USPS",
        tracking_status=TrackingStatus.LABEL_CREATED,
        shipment_timestamp=datetime(2026, 10, 17, 8, 0, tzinfo=timezone.utc),
        delivery_timestamp=None,
        shipment_address=Address(
            recipient_name="Jordan Reed",
            line1="742 Evergreen Terrace",
            city="Springfield",
            state_or_province="IL",
            postal_code="62704",
            country_code="US",
        ),
        source_identifier="SRC-USPS-API-CARRIER",
        recipient_signature_present=False,
    )

    bundle = ReconciledDisputeBundle(
        dispute_id=dispute.dispute_id,
        status=ReconciliationStatus.RECONCILED,
        matched_order=order,
        matched_shipments=[shipment],
        confidence_score=1.0,
    )

    return dispute, bundle


def print_section(title: str, content: str):
    print("\n" + "=" * 78)
    print(f" {title.upper()}")
    print("=" * 78)
    print(content)


def display_workflow_result(res: SemanticWorkflowResult, execution_context: str):
    print("\n" + "#" * 78)
    print(f"  DOCKET AI WORKFLOW DEMONSTRATION [{execution_context}]")
    print("#" * 78)

    # 1. Original Unstructured Message
    print_section(
        "1. Original Unstructured Message & Prompt Threat Analysis",
        f"Raw Buyer Message:\n  \"{res.original_message}\"\n\n"
        f"Prompt Threat Analysis:\n"
        f"  - Suspicious Patterns Detected: {res.sanitized_input.is_suspicious}\n"
        f"  - Threat Level: {res.sanitized_input.threat_level.value}\n"
        f"  - Patterns: {res.sanitized_input.detected_patterns or 'None (Clean input)'}\n"
        f"  - Encapsulated Safe Prompt:\n    {res.sanitized_input.safe_prompt_text[:120]}...",
    )

    # 2. Selected AI Provider & Model
    print_section(
        "2. Selected AI Provider & Model Configuration",
        f"  - AI Mode:             {res.ai_mode.upper()}\n"
        f"  - Provider:            {res.ai_provider.upper()}\n"
        f"  - Model Identifier:    {res.model_identifier}\n"
        f"  - Live Network Call:   {res.is_live_call}\n"
        f"  - Latency:             {res.execution_time_ms} ms",
    )

    # 3. Extracted Structured Claims
    claims_text = []
    for c in res.verified_claims:
        claims_text.append(
            f"  - Claim ID:          {c.claim_id}\n"
            f"    Type:              {c.claim_type.value}\n"
            f"    Assertion:         {c.factual_assertion}\n"
            f"    Sources Cited:     {len(c.supporting_sources)}"
        )
    print_section(
        "3. Extracted Structured Claims (AI Output)",
        "\n\n".join(claims_text) if claims_text else "  No claims extracted.",
    )

    # 4. Citation Verification Results
    verif_text = []
    for cv in res.citation_verifications:
        cit = cv.citation
        verif_text.append(
            f"  - Source Identifier: {cit.source_identifier} ({cit.source_type.value})\n"
            f"    Cited Excerpt:     \"{cit.extracted_value}\"\n"
            f"    Verification:      {'PASS (VERIFIED)' if cv.is_verified else 'FAIL (UNVERIFIED)'}\n"
            f"    Character Span:    Offsets [{cv.start_offset}:{cv.end_offset}]\n"
            f"    Flags:             {cv.flags or 'None'}"
        )
    print_section(
        "4. Citation Verification & Verbatim Source Integrity",
        "\n\n".join(verif_text) if verif_text else "  No citations to verify.",
    )

    # 5. Cross-Source Contradictions
    contra_text = []
    for c in res.contradictions:
        contra_text.append(
            f"  - [{c.severity}] {c.code}: {c.description}"
        )
    print_section(
        "5. Cross-Source Contradiction Detection",
        "\n".join(contra_text) if contra_text else "  No factual contradictions or bundle anomalies detected.",
    )

    # 6. Deterministic Policy Decision
    violations = res.policy_evaluation.get_violations()
    print_section(
        "6. Deterministic Policy Decision (Refusal Barrier)",
        f"  - Overall Policy Decision:   {res.final_policy_decision}\n"
        f"  - Factual Readiness:         {res.policy_evaluation.factual_readiness.value}\n"
        f"  - Action Readiness:          {res.policy_evaluation.action_readiness.value}\n"
        f"  - Invariant Violations:      {violations or 'None (Compliant)'}\n"
        f"  - Summary:                   {res.policy_evaluation.summary}",
    )

    # 7. Recommended Next Step
    print_section(
        "7. Recommended Operational Next Step",
        f"  Action: {res.recommended_next_action}\n"
        f"  * Note: The AI semantic extractor does NOT have authority to decide dispute outcomes\n"
        f"    or dispatch evidence to PayPal. Human merchant authorization is strictly required.",
    )


def run_demo():
    dispute, bundle = build_synthetic_fixture()
    buyer_msg = dispute.raw_messages[0]["content"]

    gemini_key = os.getenv("GEMINI_API_KEY")

    if gemini_key:
        print("\n[INFO] Valid GEMINI_API_KEY detected in environment. Running LIVE model smoke test...")
        # Live Gemini Test
        extractor = GeminiFactExtractor(api_key=gemini_key)
        workflow = SemanticExtractionWorkflow(extractor=extractor)
        res = workflow.run(buyer_message=buyer_msg, dispute=dispute, bundle=bundle)
        display_workflow_result(res, execution_context="LIVE GEMINI API NETWORK CALL")
    else:
        print("\n[INFO] GEMINI_API_KEY is not set in environment.")
        print("[INFO] Demonstrating Stage A: Offline Deterministic Fact Extraction ($0 cost, 0 latency)")

        # Stage A: Offline Deterministic Fact Extractor
        workflow_offline = SemanticExtractionWorkflow(extractor=DeterministicFactExtractor())
        res_offline = workflow_offline.run(buyer_message=buyer_msg, dispute=dispute, bundle=bundle)
        display_workflow_result(res_offline, execution_context="OFFLINE DETERMINISTIC ENGINE")

        print("\n" + "-" * 78)
        print("[INFO] Demonstrating Stage B: Mocked Live Gemini REST Provider (Verifying function-calling schema)")

        # Stage B: Mocked Gemini Live Provider Call
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "candidates": [
                {
                    "content": {
                        "parts": [
                            {
                                "functionCall": {
                                    "name": "record_extracted_claims",
                                    "args": {
                                        "claims": [
                                            {
                                                "claim_id": "CLM-GEMINI-01",
                                                "claim_type": "LABEL_CREATED",
                                                "factual_assertion": "USPS shipping label was generated with no subsequent possession scan.",
                                                "exact_citation_excerpt": "Tracking only shows label created with USPS",
                                                "source_id": "MSG-00",
                                            }
                                        ]
                                    },
                                }
                            }
                        ]
                    }
                }
            ]
        }

        with patch("requests.post", return_value=mock_response):
            gemini_mocked = GeminiFactExtractor(api_key="mock-gemini-key")
            workflow_live_mocked = SemanticExtractionWorkflow(extractor=gemini_mocked)
            res_live_mocked = workflow_live_mocked.run(buyer_message=buyer_msg, dispute=dispute, bundle=bundle)
            display_workflow_result(res_live_mocked, execution_context="MOCKED GEMINI LIVE INTEGRATION (gemini-2.5-flash)")


if __name__ == "__main__":
    run_demo()

