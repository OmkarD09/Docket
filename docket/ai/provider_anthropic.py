"""Anthropic Claude tool-calling provider for Docket."""

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


class AnthropicFactExtractor(BaseFactExtractor):
    """Extracts structured dispute facts via Anthropic Claude tool use."""

    ANTHROPIC_API_URL = "https://api.anthropic.com/v1/messages"

    def __init__(self, api_key: str, model: str = "claude-3-5-sonnet-20241022") -> None:
        self.api_key = api_key
        self.model = model
        self.guard = PromptInjectionGuard()

    def extract_from_bundle(
        self,
        dispute: DisputeCase,
        bundle: ReconciledDisputeBundle,
    ) -> ExtractionResult:
        """Call Claude with forced tool use for structured claim extraction."""
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
            "model": self.model,
            "max_tokens": 1024,
            "messages": [{"role": "user", "content": prompt}],
            "tools": [
                {
                    "name": "record_extracted_claims",
                    "description": "Record extracted atomic factual claims and source citations from evidence.",
                    "input_schema": {
                        "type": "object",
                        "properties": {
                            "claims": {
                                "type": "array",
                                "items": {
                                    "type": "object",
                                    "properties": {
                                        "claim_id": {"type": "string"},
                                        "claim_type": {"type": "string"},
                                        "factual_assertion": {"type": "string"},
                                        "exact_citation_excerpt": {"type": "string"},
                                        "source_id": {"type": "string"},
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
            ],
            "tool_choice": {"type": "tool", "name": "record_extracted_claims"},
        }

        headers = {
            "x-api-key": self.api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }

        resp = requests.post(self.ANTHROPIC_API_URL, json=payload, headers=headers, timeout=30)
        resp.raise_for_status()
        data = resp.json()

        claims: List[ExtractedClaim] = []
        for block in data.get("content", []):
            if block.get("type") == "tool_use" and block.get("name") == "record_extracted_claims":
                input_data = block.get("input", {})
                for item in input_data.get("claims", []):
                    try:
                        c_type = ClaimType(item["claim_type"])
                    except ValueError:
                        c_type = ClaimType.OTHER

                    citation = SourceCitation(
                        source_type=SourceType.CUSTOMER_COMMUNICATION,
                        source_identifier=item.get("source_id", "CLAUDE-EXTRACT"),
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
        """Extract claims from text via Claude."""
        return []

