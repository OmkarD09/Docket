"""Anthropic Claude tool-calling provider for Docket with citation verification and error boundaries."""

from __future__ import annotations

import json
import os
from typing import Any, Dict, List, Optional
import requests

from docket.ai.base import AIProviderError, BaseFactExtractor, ExtractionResult
from docket.ai.citation_verifier import VerbatimCitationVerifier
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

    def __init__(
        self,
        api_key: str,
        model: Optional[str] = None,
        timeout_seconds: int = 30,
    ) -> None:
        self.api_key = api_key
        self.model = model or os.getenv("ANTHROPIC_MODEL", "claude-3-5-sonnet-20241022")
        self.timeout_seconds = timeout_seconds
        self.guard = PromptInjectionGuard()
        self.verifier = VerbatimCitationVerifier()

    def _build_context_and_sources(
        self,
        dispute: DisputeCase,
        bundle: ReconciledDisputeBundle,
    ) -> tuple[str, Dict[str, tuple[str, SourceType, str]]]:
        context_parts = [
            f"Dispute ID: {dispute.dispute_id}",
            f"Dispute Reason: {dispute.reason}",
            f"Dispute Amount: {dispute.dispute_amount.value} {dispute.dispute_amount.currency_code}",
        ]
        source_map: Dict[str, tuple[str, SourceType, str]] = {}

        if bundle.matched_order:
            order = bundle.matched_order
            order_text = f"Order ID: {order.order_id}, Transaction: {order.paypal_transaction_id or 'N/A'}"
            context_parts.append(f"ORDER RECORD [{order.order_id}]: {order_text}")
            source_map[order.order_id] = (order_text, SourceType.ORDER_INVOICE, "order_id")
            if order.paypal_transaction_id:
                source_map[order.paypal_transaction_id] = (order_text, SourceType.ORDER_INVOICE, "paypal_transaction_id")

        if bundle.matched_shipments:
            for s in bundle.matched_shipments:
                s_id = s.source_identifier or f"TRK-{s.tracking_number}"
                shipment_text = f"Carrier: {s.carrier_name}, Tracking: {s.tracking_number}, Status: {s.tracking_status.value}"
                context_parts.append(f"SHIPMENT RECORD [{s_id}]: {shipment_text}")
                source_map[s_id] = (shipment_text, SourceType.CARRIER_TRACKING, "tracking_status")
                source_map[s.tracking_number] = (shipment_text, SourceType.CARRIER_TRACKING, "tracking_number")
                source_map[s.carrier_name] = (shipment_text, SourceType.CARRIER_TRACKING, "carrier_name")

        for idx, msg in enumerate(dispute.raw_messages):
            if isinstance(msg, dict):
                content = msg.get("content", "")
                sanitized = self.guard.sanitize(content)
                msg_id = f"MSG-{idx:02d}"
                context_parts.append(f"BUYER MESSAGE [{msg_id} - UNTRUSTED EVIDENCE]:\n{sanitized.safe_prompt_text}")
                source_map[msg_id] = (content, SourceType.CUSTOMER_COMMUNICATION, "content")
                source_map[dispute.dispute_id] = (content, SourceType.CUSTOMER_COMMUNICATION, f"raw_messages.{idx}.content")

        valid_ids_str = ", ".join(f"'{k}'" for k in sorted(source_map.keys()))
        context_parts.append(f"\nVALID SOURCE IDENTIFIERS: [{valid_ids_str}]")
        return "\n".join(context_parts), source_map

    def extract_from_bundle(
        self,
        dispute: DisputeCase,
        bundle: ReconciledDisputeBundle,
    ) -> ExtractionResult:
        prompt, source_map = self._build_context_and_sources(dispute, bundle)

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

        try:
            resp = requests.post(self.ANTHROPIC_API_URL, json=payload, headers=headers, timeout=self.timeout_seconds)
            if resp.status_code != 200:
                raise AIProviderError(f"Anthropic API returned HTTP {resp.status_code}: {resp.text[:300]}")
            data = resp.json()
        except requests.Timeout as exc:
            raise AIProviderError(f"Anthropic API request timed out after {self.timeout_seconds}s") from exc
        except requests.RequestException as exc:
            raise AIProviderError(f"Anthropic API request failed: {exc}") from exc

        claims: List[ExtractedClaim] = []
        findings: List[str] = []

        for block in data.get("content", []):
            if block.get("type") == "tool_use" and block.get("name") == "record_extracted_claims":
                input_data = block.get("input", {})
                for item in input_data.get("claims", []):
                    try:
                        c_type = ClaimType(item["claim_type"])
                    except ValueError:
                        c_type = ClaimType.OTHER

                    raw_source_id = str(item.get("source_id", "")).strip()
                    raw_excerpt = str(item.get("exact_citation_excerpt", "")).strip()

                    if raw_source_id in source_map:
                        source_doc_text, source_type, field_path = source_map[raw_source_id]
                        verif_res = self.verifier.verify_citation(
                            document_text=source_doc_text,
                            cited_excerpt=raw_excerpt,
                            document_id=raw_source_id,
                            source_type=source_type,
                            field_path=field_path,
                        )
                        citation = verif_res.citation
                    else:
                        findings.append(f"Invalid source '{raw_source_id}' referenced in claim {item.get('claim_id')}")
                        citation = SourceCitation(
                            source_type=SourceType.CUSTOMER_COMMUNICATION,
                            source_identifier=raw_source_id or "UNKNOWN",
                            field_path="text",
                            extracted_value=raw_excerpt,
                            verification_status=VerificationStatus.REJECTED,
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
            findings=findings,
            raw_model_response=data,
        )

    def extract_from_text(
        self,
        text: str,
        source_id: str,
        source_type: SourceType,
    ) -> List[ExtractedClaim]:
        claims: List[ExtractedClaim] = []
        verif_res = self.verifier.verify_citation(
            document_text=text,
            cited_excerpt=text[:50].strip(),
            document_id=source_id,
            source_type=source_type,
            field_path="text",
        )
        claims.append(
            ExtractedClaim(
                claim_id=f"CLM-{source_id}",
                claim_type=ClaimType.OTHER,
                factual_assertion=f"Extracted excerpt from {source_id}",
                supporting_sources=[verif_res.citation],
                claim_status=ClaimStatus.PROPOSED,
            )
        )
        return claims
