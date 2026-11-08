"""Semantic Fact Extraction & Policy Verification Workflow for Docket.

Provides the end-to-end vertical slice:
1. Untrusted buyer message sanitization & prompt-injection detection (<untrusted_content>).
2. AI-driven atomic claim extraction (Gemini live / deterministic offline).
3. Verbatim citation verification against source text & whitelist enforcement.
4. Cross-source contradiction detection.
5. Deterministic PolicyEngine evaluation (ALLOW, REVIEW, BLOCK refusal barrier).
6. Recommended operational next step.
"""

from __future__ import annotations

import time
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, ConfigDict, Field

from docket.ai.base import BaseFactExtractor, ExtractionResult
from docket.ai.citation_verifier import CitationVerificationResult, VerbatimCitationVerifier
from docket.ai.contradiction import ContradictionDetector, ContradictionFinding
from docket.ai.factory import get_fact_extractor
from docket.ai.prompt_guard import PromptInjectionGuard, SanitizedInput
from docket.models.dispute import DisputeCase
from docket.models.evidence import ExtractedClaim, SourceType, VerificationStatus
from docket.models.policy import DecisionType, OverallPolicyEvaluation
from docket.models.reconciliation import ReconciledDisputeBundle
from docket.policy.engine import PolicyEngine


class SemanticWorkflowResult(BaseModel):
    """The complete result of an end-to-end semantic extraction workflow."""
    model_config = ConfigDict(arbitrary_types_allowed=True)

    original_message: str
    ai_mode: str
    ai_provider: str
    model_identifier: str
    is_live_call: bool
    sanitized_input: SanitizedInput
    extraction_findings: List[str] = Field(default_factory=list)
    raw_claims: List[ExtractedClaim] = Field(default_factory=list)
    verified_claims: List[ExtractedClaim] = Field(default_factory=list)
    citation_verifications: List[CitationVerificationResult] = Field(default_factory=list)
    contradictions: List[ContradictionFinding] = Field(default_factory=list)
    policy_evaluation: OverallPolicyEvaluation
    final_policy_decision: str
    recommended_next_action: str
    execution_time_ms: float
    error: Optional[str] = None


class SemanticExtractionWorkflow:
    """Executes the complete semantic extraction and deterministic policy verification pipeline."""

    def __init__(
        self,
        extractor: Optional[BaseFactExtractor] = None,
        policy_engine: Optional[PolicyEngine] = None,
    ) -> None:
        self.extractor = extractor or get_fact_extractor()
        self.policy_engine = policy_engine or PolicyEngine()
        self.guard = PromptInjectionGuard()
        self.verifier = VerbatimCitationVerifier()
        self.contradiction_detector = ContradictionDetector()

    def run(
        self,
        buyer_message: str,
        dispute: DisputeCase,
        bundle: ReconciledDisputeBundle,
    ) -> SemanticWorkflowResult:
        """Run the full vertical slice pipeline on an unstructured message and associated records."""
        start_time = time.perf_counter()

        # Step 1: Prompt Sanitization & Threat Quarantine
        sanitized = self.guard.sanitize(buyer_message)

        # Inject buyer message into dispute's raw_messages if not already present
        updated_dispute = dispute.model_copy(deep=True)
        message_in_dispute = False
        for msg in updated_dispute.raw_messages:
            if isinstance(msg, dict) and msg.get("content") == buyer_message:
                message_in_dispute = True
                break
        if not message_in_dispute:
            updated_dispute.raw_messages = [
                {"posted_by": "BUYER", "content": buyer_message, "sanitized_threat": sanitized.is_suspicious}
            ] + updated_dispute.raw_messages

        # Step 2: Build Available Sources Dictionary for Policy Invariants
        available_sources: Dict[str, Any] = {}
        if bundle.matched_order:
            available_sources[bundle.matched_order.order_id] = bundle.matched_order
            if bundle.matched_order.paypal_transaction_id:
                available_sources[bundle.matched_order.paypal_transaction_id] = bundle.matched_order
        for s in bundle.matched_shipments:
            s_id = s.source_identifier or f"TRK-{s.tracking_number}"
            available_sources[s_id] = s
            available_sources[s.tracking_number] = s
            available_sources[s.carrier_name] = s
        available_sources[dispute.dispute_id] = updated_dispute
        available_sources["MSG-00"] = {"content": buyer_message, "text": buyer_message}

        # Step 3: Semantic Fact Extraction
        extraction_res: ExtractionResult
        error_msg: Optional[str] = None
        try:
            extraction_res = self.extractor.extract_from_bundle(updated_dispute, bundle)
        except Exception as exc:
            error_msg = f"Extraction failed: {exc}"
            extraction_res = ExtractionResult(claims=[], citations=bundle.to_citations(), findings=[error_msg])

        raw_claims = extraction_res.claims
        verified_claims: List[ExtractedClaim] = []
        citation_verifications: List[CitationVerificationResult] = []
        all_contradictions: List[ContradictionFinding] = []

        # Step 4: Verification & Contradiction Detection
        for claim in raw_claims:
            verified_citations = []
            for cit in claim.supporting_sources:
                # Check source existence
                if cit.source_identifier not in available_sources:
                    c_res = CitationVerificationResult(
                        is_verified=False,
                        start_offset=None,
                        end_offset=None,
                        citation=cit.model_copy(update={"verification_status": VerificationStatus.REJECTED}),
                        flags=["INVALID_SOURCE_REFERENCE"],
                    )
                    citation_verifications.append(c_res)
                    verified_citations.append(c_res.citation)
                    continue

                # Verbatim check on buyer message text if cited
                if cit.source_type == SourceType.CUSTOMER_COMMUNICATION:
                    c_res = self.verifier.verify_citation(
                        document_text=buyer_message,
                        cited_excerpt=cit.extracted_value,
                        document_id=cit.source_identifier,
                        source_type=cit.source_type,
                        field_path=cit.field_path,
                    )
                    citation_verifications.append(c_res)
                    verified_citations.append(c_res.citation)
                else:
                    # Carrier or order citation
                    citation_verifications.append(
                        CitationVerificationResult(
                            is_verified=cit.verification_status == VerificationStatus.VERIFIED,
                            start_offset=None,
                            end_offset=None,
                            citation=cit,
                            flags=[],
                        )
                    )
                    verified_citations.append(cit)

            v_claim = claim.model_copy(update={"supporting_sources": verified_citations})
            verified_claims.append(v_claim)

            # Contradiction check against bundle
            contra = self.contradiction_detector.check_contradictions(v_claim, bundle, dispute.reason)
            all_contradictions.extend(contra)

        # Include bundle-level anomalies (prior refunds, split shipments)
        all_contradictions.extend(self.contradiction_detector.check_bundle_anomalies(bundle))

        # Step 5: Deterministic Policy Evaluation
        eval_claim = verified_claims[0] if verified_claims else None
        policy_eval = self.policy_engine.evaluate(
            dispute=updated_dispute,
            order=bundle.matched_order,
            shipment=bundle.get_primary_shipment(),
            claim=eval_claim,
            claims=verified_claims,
            available_sources=available_sources,
        )

        elapsed_ms = (time.perf_counter() - start_time) * 1000.0

        # Derive recommended next action strictly from deterministic policy checks
        recommended_action = "Review evidence documentation and resolve discrepancies."
        for check in policy_eval.check_results:
            if check.recommended_next_action:
                recommended_action = check.recommended_next_action
                if check.decision in (DecisionType.BLOCK, DecisionType.REVIEW):
                    break
        if policy_eval.overall_decision == DecisionType.ALLOW:
            recommended_action = "Evidence package is factually verified and compliant. Proceed to merchant approval."

        extractor_name = type(self.extractor).__name__
        is_live = extractor_name in ("GeminiFactExtractor", "OpenAIFactExtractor", "AnthropicFactExtractor")
        provider_name = (
            "gemini" if "Gemini" in extractor_name
            else "openai" if "OpenAI" in extractor_name
            else "anthropic" if "Anthropic" in extractor_name
            else "deterministic"
        )
        model_name = getattr(self.extractor, "model", "deterministic-rules-engine")

        return SemanticWorkflowResult(
            original_message=buyer_message,
            ai_mode="live" if is_live else "offline",
            ai_provider=provider_name,
            model_identifier=model_name,
            is_live_call=is_live,
            sanitized_input=sanitized,
            extraction_findings=extraction_res.findings,
            raw_claims=raw_claims,
            verified_claims=verified_claims,
            citation_verifications=citation_verifications,
            contradictions=all_contradictions,
            policy_evaluation=policy_eval,
            final_policy_decision=policy_eval.overall_decision.value,
            recommended_next_action=recommended_action,
            execution_time_ms=round(elapsed_ms, 2),
            error=error_msg,
        )
