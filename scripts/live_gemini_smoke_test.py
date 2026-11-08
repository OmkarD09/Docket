"""Docket Live Gemini API Smoke Test Script.

Executes one genuine end-to-end extraction against Google Gemini API using synthetic data.
Ensures zero credential leakage: never prints or exposes the API key.
"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
import json
import os
import sys
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv
load_dotenv()

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
    OrderRecord,
    ShipmentRecord,
    TrackingStatus,
)
from docket.models.reconciliation import ReconciledDisputeBundle, ReconciliationStatus


def run_live_smoke_test():
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        print("[ERROR] GEMINI_API_KEY is not set in environment or .env file.")
        sys.exit(1)

    model_name = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
    masked_key = f"{api_key[:6]}...{api_key[-4:]}" if len(api_key) > 10 else "***"
    print("=" * 78)
    print(" DOCKET — LIVE GEMINI API SMOKE TEST EXECUTION")
    print("=" * 78)
    print(f"Provider:            Google Gemini REST API")
    print(f"Model:               {model_name}")
    print(f"Credential:          Loaded ({masked_key})")
    print(f"Timestamp:           {datetime.now(timezone.utc).isoformat()}")

    # 1. Synthetic test data matching the exact user prompt
    buyer_message = (
        "The tracking page says my package was delivered yesterday, but I never received it. "
        "I contacted the courier, and they told me the parcel may have been left at another address."
    )

    dispute = DisputeCase(
        dispute_id="PP-D-LIVE-2026",
        reason=DisputeReason.MERCHANDISE_OR_SERVICE_NOT_RECEIVED,
        lifecycle_stage=DisputeLifecycleStage.CHARGEBACK,
        status=DisputeStatus.WAITING_FOR_SELLER_RESPONSE,
        dispute_amount=Money(value=Decimal("75.00"), currency_code="USD"),
        requested_evidence_types=["PROOF_OF_DELIVERY"],
        seller_response_due_date=datetime(2026, 12, 5, 12, 0, tzinfo=timezone.utc),
        available_hateoas_actions=[
            HATEOASLink(
                href="https://api-m.sandbox.paypal.com/v1/customer/disputes/PP-D-LIVE-2026/provide-evidence",
                rel="provide_evidence",
                method="POST",
            )
        ],
        disputed_transaction_id="TX-LIVE-7701",
        seller_transaction_id="TX-LIVE-7701",
        buyer_email="buyer.synthetic@example.com",
        buyer_name="Casey Miller",
        dispute_create_time=datetime(2026, 11, 8, 10, 0, tzinfo=timezone.utc),
        raw_messages=[
            {
                "posted_by": "BUYER",
                "time_posted": "2026-11-08T10:00:00Z",
                "content": buyer_message,
            }
        ],
    )

    order = OrderRecord(
        order_id="ORD-LIVE-7701",
        paypal_transaction_id="TX-LIVE-7701",
        order_timestamp=datetime(2026, 10, 30, 14, 0, tzinfo=timezone.utc),
        gross_amount=Money(value=Decimal("75.00"), currency_code="USD"),
        customer_email="buyer.synthetic@example.com",
        customer_name="Casey Miller",
        shipping_address=Address(
            recipient_name="Casey Miller",
            line1="550 S 1st St",
            city="San Jose",
            state_or_province="CA",
            postal_code="95113",
            country_code="US",
        ),
        tracking_numbers=["9400111899223197428490"],
        items=[{"item_name": "Ergonomic Desk Accessory", "quantity": 1}],
    )

    shipment = ShipmentRecord(
        internal_order_id="ORD-LIVE-7701",
        tracking_number="9400111899223197428490",
        carrier_name="USPS",
        tracking_status=TrackingStatus.DELIVERED,
        shipment_timestamp=datetime(2026, 10, 31, 9, 30, tzinfo=timezone.utc),
        delivery_timestamp=datetime(2026, 11, 7, 14, 22, tzinfo=timezone.utc),
        shipment_address=Address(
            recipient_name="Casey Miller",
            line1="550 S 1st St",
            city="San Jose",
            state_or_province="CA",
            postal_code="95113",
            country_code="US",
        ),
        source_identifier="SRC-USPS-TRACKING-API",
        recipient_signature_present=False,
    )

    bundle = ReconciledDisputeBundle(
        dispute_id=dispute.dispute_id,
        status=ReconciliationStatus.RECONCILED,
        matched_order=order,
        matched_shipments=[shipment],
        confidence_score=1.0,
    )

    print("\nExecuting live API request through SemanticExtractionWorkflow...")
    extractor = GeminiFactExtractor(api_key=api_key, model=model_name)
    workflow = SemanticExtractionWorkflow(extractor=extractor)

    try:
        result: SemanticWorkflowResult = workflow.run(
            buyer_message=buyer_message,
            dispute=dispute,
            bundle=bundle,
        )
    except Exception as exc:
        print(f"\n[FATAL] Live extraction request failed: {exc}")
        sys.exit(1)

    print("\n" + "=" * 78)
    print(" LIVE API RESPONSE & PIPELINE VERIFICATION RESULTS")
    print("=" * 78)

    print(f"\n1. Execution Metadata:")
    print(f"   - Provider:             {result.ai_provider.upper()}")
    print(f"   - Model:                {result.model_identifier}")
    print(f"   - Live Network Call:    {result.is_live_call}")
    print(f"   - Latency:              {result.execution_time_ms} ms")
    if result.usage_metadata:
        print(f"   - Usage Metadata:       {json.dumps(result.usage_metadata)}")
    if result.error:
        print(f"   - Error:                {result.error}")

    print(f"\n2. Extracted Structured Claims ({len(result.verified_claims)} claim(s)):")
    for idx, claim in enumerate(result.verified_claims, 1):
        print(f"   Claim #{idx}:")
        print(f"     - ID:                 {claim.claim_id}")
        print(f"     - Type:               {claim.claim_type.value}")
        print(f"     - Assertion:          {claim.factual_assertion}")
        print(f"     - Status:             {claim.claim_status.value}")
        print(f"     - Sources Cited:      {len(claim.supporting_sources)}")

    print(f"\n3. Verbatim Citation Verification:")
    for idx, cv in enumerate(result.citation_verifications, 1):
        cit = cv.citation
        print(f"   Citation #{idx}:")
        print(f"     - Source ID:          {cit.source_identifier} ({cit.source_type.value})")
        print(f"     - Cited Excerpt:      \"{cit.extracted_value}\"")
        print(f"     - Verification:       {'PASS (VERIFIED)' if cv.is_verified else 'FAIL (UNVERIFIED)'}")
        print(f"     - Field Path:         {cit.field_path}")
        print(f"     - Character Offsets:  [{cv.start_offset}:{cv.end_offset}]")
        print(f"     - Flags:              {cv.flags or 'None'}")

    print(f"\n4. Cross-Source Contradictions ({len(result.contradictions)} finding(s)):")
    if result.contradictions:
        for c in result.contradictions:
            print(f"   - [{c.severity}] {c.code}: {c.description}")
    else:
        print("   - No contradictions found.")

    print(f"\n5. Deterministic PolicyEngine Evaluation:")
    print(f"   - Overall Decision:     {result.final_policy_decision}")
    print(f"   - Factual Readiness:    {result.policy_evaluation.factual_readiness.value}")
    print(f"   - Action Readiness:     {result.policy_evaluation.action_readiness.value}")
    print(f"   - Invariant Violations: {result.policy_evaluation.get_violations() or 'None (Compliant)'}")
    print(f"   - Summary:              {result.policy_evaluation.summary}")
    print(f"   - Recommended Action:   {result.recommended_next_action}")

    # Export execution record for verification document
    out_record = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "provider": result.ai_provider,
        "model": result.model_identifier,
        "latency_ms": result.execution_time_ms,
        "usage_metadata": result.usage_metadata,
        "claims_count": len(result.verified_claims),
        "claims": [c.model_dump() for c in result.verified_claims],
        "citations": [cv.model_dump() for cv in result.citation_verifications],
        "contradictions": [c.model_dump() for c in result.contradictions],
        "decision": result.final_policy_decision,
        "recommended_action": result.recommended_next_action,
    }
    out_path = Path("artifacts/live_gemini_smoke_test_result.json")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(out_record, f, indent=2, default=str)
    print(f"\nExecution evidence saved to: {out_path}")
    print("=" * 78)


if __name__ == "__main__":
    run_live_smoke_test()

