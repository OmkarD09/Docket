"""Deterministic, rule-based fact extractor for offline operation and baseline testing."""

from __future__ import annotations

from typing import List, Optional

from docket.ai.base import BaseFactExtractor, ExtractionResult
from docket.ai.citation_verifier import VerbatimCitationVerifier
from docket.ai.contradiction import ContradictionDetector
from docket.ai.prompt_guard import PromptInjectionGuard
from docket.models.dispute import DisputeCase
from docket.models.evidence import (
    ClaimStatus,
    ClaimType,
    ExtractedClaim,
    SourceCitation,
    SourceType,
    TrackingStatus,
    VerificationStatus,
)
from docket.models.reconciliation import ReconciledDisputeBundle


class DeterministicFactExtractor(BaseFactExtractor):
    """Extracts structured facts deterministically from dispute and bundle records."""

    def __init__(self) -> None:
        self.guard = PromptInjectionGuard()
        self.verifier = VerbatimCitationVerifier()
        self.contradiction_detector = ContradictionDetector()

    def extract_from_bundle(
        self,
        dispute: DisputeCase,
        bundle: ReconciledDisputeBundle,
    ) -> ExtractionResult:
        """Extract atomic claims from buyer messages and carrier tracking events."""
        claims: List[ExtractedClaim] = []
        citations: List[SourceCitation] = bundle.to_citations()
        findings: List[str] = []

        # 1. Extract from buyer messages
        for idx, msg in enumerate(dispute.raw_messages):
            if isinstance(msg, dict):
                content = msg.get("content", "")
                sanitized = self.guard.sanitize(content)
                if sanitized.is_suspicious:
                    findings.append(f"Suspicious prompt pattern in message {idx}: {sanitized.detected_patterns}")

                # Detect if buyer message references 'label created'
                content_lower = content.lower()
                if "label created" in content_lower:
                    cit_res = self.verifier.verify_citation(
                        document_text=content,
                        cited_excerpt="label created",
                        document_id=dispute.dispute_id,
                        source_type=SourceType.CUSTOMER_COMMUNICATION,
                        field_path=f"raw_messages.{idx}.content",
                    )
                    claims.append(
                        ExtractedClaim(
                            claim_id=f"CLM-MSG-{idx}",
                            claim_type=ClaimType.LABEL_CREATED,
                            factual_assertion="Customer acknowledges tracking shows label created without movement.",
                            supporting_sources=[cit_res.citation],
                            claim_status=ClaimStatus.SUPPORTED,
                        )
                    )

        # 2. Extract from primary shipment
        primary_shipment = bundle.get_primary_shipment()
        if primary_shipment:
            s = primary_shipment
            shipment_citations = [
                c for c in citations if c.source_type == SourceType.CARRIER_TRACKING
            ]

            if s.tracking_status == TrackingStatus.LABEL_CREATED:
                claims.append(
                    ExtractedClaim(
                        claim_id=f"CLM-TRK-{s.tracking_number}",
                        claim_type=ClaimType.LABEL_CREATED,
                        factual_assertion=f"Carrier {s.carrier_name} tracking indicates shipping label generated awaiting carrier pickup.",
                        supporting_sources=shipment_citations,
                        claim_status=ClaimStatus.SUPPORTED,
                    )
                )
            elif s.tracking_status == TrackingStatus.DELIVERED:
                claims.append(
                    ExtractedClaim(
                        claim_id=f"CLM-TRK-{s.tracking_number}",
                        claim_type=ClaimType.DELIVERY_COMPLETED,
                        factual_assertion=f"Carrier {s.carrier_name} tracking confirms package was delivered to destination.",
                        supporting_sources=shipment_citations,
                        claim_status=ClaimStatus.SUPPORTED,
                    )
                )
            elif s.tracking_status == TrackingStatus.IN_TRANSIT:
                claims.append(
                    ExtractedClaim(
                        claim_id=f"CLM-TRK-{s.tracking_number}",
                        claim_type=ClaimType.SHIPMENT_IN_PROGRESS,
                        factual_assertion=f"Carrier {s.carrier_name} tracking shows merchandise in physical transit.",
                        supporting_sources=shipment_citations,
                        claim_status=ClaimStatus.SUPPORTED,
                    )
                )

        # 3. Check for anomalies and contradictions
        anomalies = self.contradiction_detector.check_bundle_anomalies(bundle)
        for a in anomalies:
            findings.append(f"[{a.severity}] {a.code}: {a.description}")

        for claim in claims:
            contra = self.contradiction_detector.check_contradictions(claim, bundle, dispute.reason)
            for c in contra:
                findings.append(f"[{c.severity}] {c.code}: {c.description}")

        return ExtractionResult(
            claims=claims,
            citations=citations,
            findings=findings,
        )

    def extract_from_text(
        self,
        text: str,
        source_id: str,
        source_type: SourceType,
    ) -> List[ExtractedClaim]:
        """Extract claims from raw text."""
        sanitized = self.guard.sanitize(text)
        cit_res = self.verifier.verify_citation(
            document_text=text,
            cited_excerpt=text.strip(),
            document_id=source_id,
            source_type=source_type,
        )
        return [
            ExtractedClaim(
                claim_id=f"CLM-{source_id}",
                claim_type=ClaimType.OTHER,
                factual_assertion=text.strip(),
                supporting_sources=[cit_res.citation],
                claim_status=ClaimStatus.PROPOSED,
            )
        ]
