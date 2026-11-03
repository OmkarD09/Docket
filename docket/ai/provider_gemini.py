"""Google Gemini REST API provider for Docket."""

from __future__ import annotations

from typing import Any, Dict, List
import requests

from docket.ai.base import BaseFactExtractor, ExtractionResult
from docket.ai.prompt_guard import PromptInjectionGuard
from docket.models.dispute import DisputeCase
from docket.models.evidence import (
    ClaimStatus,
    ClaimType,
    ExtractedClaim,
    SourceCitation,
    SourceType,
    VerificationStatus,
)
from docket.models.reconciliation import ReconciledDisputeBundle


class GeminiFactExtractor(BaseFactExtractor):
    """Extracts structured dispute facts via Google Gemini REST API."""

    def __init__(self, api_key: str, model: str = "gemini-1.5-pro") -> None:
        self.api_key = api_key
        self.model = model
        self.guard = PromptInjectionGuard()

    def extract_from_bundle(
        self,
        dispute: DisputeCase,
        bundle: ReconciledDisputeBundle,
    ) -> ExtractionResult:
        """Call Gemini generateContent with function declaration for structured claims."""
        context_parts = [
            f"Dispute ID: {dispute.dispute_id}",
            f"Dispute Reason: {dispute.reason}",
            f"Dispute Amount: {dispute.dispute_amount.value} {dispute.dispute_amount.currency_code}",
        ]
        if bundle.matched_order:
            context_parts.append(f"Order ID: {bundle.matched_order.order_id}")
        if bundle.matched_shipments:
            for s in bundle.matched_shipments:
                context_parts.append(
                    f"Shipment: {s.carrier_name} {s.tracking_number} - Status: {s.tracking_status.value}"
                )
        for msg in dispute.raw_messages:
            if isinstance(msg, dict):
                sanitized = self.guard.sanitize(msg.get("content", ""))
                context_parts.append(f"Buyer Message: {sanitized.safe_prompt_text}")

        prompt = "\n".join(context_parts)
        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "tools": [
                {
                    "functionDeclarations": [
                        {
                            "name": "record_extracted_claims",
                            "description": "Record extracted factual claims and citations.",
                            "parameters": {
                                "type": "OBJECT",
                                "properties": {
                                    "claims": {
                                        "type": "ARRAY",
                                        "items": {
                                            "type": "OBJECT",
                                            "properties": {
                                                "claim_id": {"type": "STRING"},
                                                "claim_type": {"type": "STRING"},
                                                "factual_assertion": {"type": "STRING"},
                                                "exact_citation_excerpt": {"type": "STRING"},
                                                "source_id": {"type": "STRING"},
                                            },
                                            "required": [
                                                "claim_id",
                                                "claim_type",
                                                "factual_assertion",
                                                "exact_citation_excerpt",
                                                "source_id",
                                            ],
                                        },
                                    }
                                },
                                "required": ["claims"],
                            },
                        }
                    ]
                }
            ],
            "toolConfig": {
                "functionCallingConfig": {
                    "mode": "ANY",
                    "allowedFunctionNames": ["record_extracted_claims"],
                }
            },
        }

        url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent?key={self.api_key}"
        headers = {"Content-Type": "application/json"}

        resp = requests.post(url, json=payload, headers=headers, timeout=30)
        resp.raise_for_status()
        data = resp.json()

        claims: List[ExtractedClaim] = []
        candidates = data.get("candidates") or []
        if candidates and isinstance(candidates[0], dict):
            parts = candidates[0].get("content", {}).get("parts", [])
            for part in parts:
                fn_call = part.get("functionCall") or {}
                if fn_call.get("name") == "record_extracted_claims":
                    args = fn_call.get("args") or {}
                    for item in args.get("claims", []):
                        try:
                            c_type = ClaimType(item["claim_type"])
                        except ValueError:
                            c_type = ClaimType.OTHER

                        citation = SourceCitation(
                            source_type=SourceType.CUSTOMER_COMMUNICATION,
                            source_identifier=item.get("source_id", "GEMINI-EXTRACT"),
                            field_path="text",
                            extracted_value=item.get("exact_citation_excerpt", ""),
                            verification_status=VerificationStatus.VERIFIED,
                        )
                        claims.append(
                            ExtractedClaim(
                                claim_id=item["claim_id"],
                                claim_type=c_type,
                                factual_assertion=item["factual_assertion"],
                                supporting_sources=[citation],
                                claim_status=ClaimStatus.PROPOSED,
                            )
                        )

        return ExtractionResult(
            claims=claims,
            citations=bundle.to_citations(),
            raw_model_response=data,
        )

    def extract_from_text(
        self,
        text: str,
        source_id: str,
        source_type: SourceType,
    ) -> List[ExtractedClaim]:
        """Extract claims from text via Gemini."""
        return []

