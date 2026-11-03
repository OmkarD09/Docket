"""Docket FastAPI REST API Backend.

Exposes RESTful endpoints for the Merchant Command Desk UI:
- /api/health: System health and version.
- /api/disputes: High-density dispute summaries for AG Grid triage.
- /api/disputes/{id}: Case deep dive with cross-source graph & policy diagnostics.
- /api/disputes/{id}/ticket: HMAC approval ticket generation.
- /api/disputes/{id}/authorize: Affirmative human merchant approval recording.
- /api/disputes/{id}/dispatch: Controlled evidence submission with idempotency.
- /api/audit-trail: Real-time cryptographically chained audit events.
- /api/eval/scorecard: 20-case evaluation matrix and metrics.
"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional
from uuid import uuid4

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from docket.models.dispute import DisputeCase, Money
from docket.models.evidence import (
    Address,
    ExtractedClaim,
    OrderRecord,
    ShipmentRecord,
    SourceCitation,
    TrackingStatus,
)
from docket.models.dispatch import (
    ApprovalDecision,
    ApprovalRequest,
    DispatchResult,
    MerchantApprovalRecord,
)
from docket.models.audit import AuditEvent, AuditEventType
from docket.models.policy import DecisionType, OverallPolicyEvaluation
from docket.models.reconciliation import ReconciledDisputeBundle
from docket.reconciliation.engine import EvidenceReconciler
from docket.policy.engine import PolicyEngine
from docket.dispatch.approval import ApprovalService
from docket.dispatch.dispatcher import (
    DuplicateSubmissionError,
    EvidenceDispatcher,
    EvidencePayloadFormatter,
    MerchantApprovalRequiredError,
    SubmissionBlockedError,
    SubmissionRejectedError,
)
from docket.audit.logger import AuditLogger
from docket.ai.prompt_guard import PromptInjectionGuard
from docket.eval.scenarios import load_all_scenarios


# ============================================================================
# API Request / Response Schemas
# ============================================================================

class DisputeSummaryResponse(BaseModel):
    dispute_id: str
    scenario_id: Optional[str] = None
    reason: str
    lifecycle_stage: str
    status: str
    amount: str
    currency: str
    due_date: Optional[str] = None
    customer_name: Optional[str] = None
    customer_email: Optional[str] = None
    reconciliation_status: str
    matched_order_id: Optional[str] = None
    tracking_number: Optional[str] = None
    tracking_status: Optional[str] = None
    carrier_name: Optional[str] = None
    factual_readiness: str
    action_readiness: str
    overall_decision: str
    violated_invariants: List[str] = Field(default_factory=list)
    discrepancies: List[str] = Field(default_factory=list)
    is_ready_for_submission: bool
    approval_status: str = "PENDING"  # PENDING, APPROVED, REJECTED
    submission_status: str = "NOT_SUBMITTED"  # NOT_SUBMITTED, SUBMITTED, FAILED
    has_prompt_threat: bool = False


class AuthorizeRequest(BaseModel):
    merchant_user_id: str = "merchant_admin"
    decision: ApprovalDecision = ApprovalDecision.APPROVE
    rejection_reason: Optional[str] = None
    notes: Optional[str] = None


class DispatchRequest(BaseModel):
    idempotency_key: Optional[str] = None
    custom_notes: Optional[str] = None


# ============================================================================
# Dispute Case Store
# ============================================================================

class CaseData:
    """Internal container for a loaded case's reconciled state."""
    def __init__(
        self,
        dispute: DisputeCase,
        bundle: ReconciledDisputeBundle,
        evaluation: OverallPolicyEvaluation,
        claims: List[ExtractedClaim],
        has_prompt_threat: bool = False,
        scenario_id: Optional[str] = None,
    ):
        self.dispute = dispute
        self.bundle = bundle
        self.evaluation = evaluation
        self.claims = claims
        self.has_prompt_threat = has_prompt_threat
        self.scenario_id = scenario_id
        self.approval_request: Optional[ApprovalRequest] = None
        self.approval_record: Optional[MerchantApprovalRecord] = None
        self.dispatch_result: Optional[DispatchResult] = None


def load_initial_cases(policy_engine: PolicyEngine) -> Dict[str, CaseData]:
    """Load both real Sandbox fixture and the 20 benchmark scenarios."""
    cases: Dict[str, CaseData] = {}
    prompt_guard = PromptInjectionGuard()

    # 1. Real Sandbox Dispute Fixture
    fixture_path = Path("docs/fixtures/real_sandbox_dispute_inr.json")
    if fixture_path.exists():
        with open(fixture_path, "r", encoding="utf-8") as f:
            raw_data = json.load(f)
        real_dispute = DisputeCase.from_paypal_response(raw_data)

        # Matched merchant order for real sandbox dispute
        real_order = OrderRecord(
            order_id="ORD-10193390",
            paypal_transaction_id="4R073105U90937213",
            customer_email="sb-6oifq53423350@personal.example.com",
            customer_name="John Doe",
            gross_amount=Money(value=Decimal("25.00"), currency_code="USD"),
            order_timestamp=datetime(2026, 10, 15, 9, 30, 0, tzinfo=timezone.utc),
            shipping_address=Address(
                recipient_name="John Doe",
                line1="123 Main St",
                city="San Jose",
                state_or_province="CA",
                postal_code="95131",
                country_code="US",
            ),
        )

        real_shipment = ShipmentRecord(
            internal_order_id="ORD-10193390",
            tracking_number="9400111899223197428490",
            carrier_name="USPS",
            tracking_status=TrackingStatus.DELIVERED,
            shipment_timestamp=datetime(2026, 10, 15, 10, 0, 0, tzinfo=timezone.utc),
            delivery_timestamp=datetime(2026, 10, 18, 14, 22, 0, tzinfo=timezone.utc),
            shipment_address=Address(
                recipient_name="John Doe",
                line1="123 Main St",
                city="San Jose",
                state_or_province="CA",
                postal_code="95131",
                country_code="US",
            ),
            source_identifier="carrier_tracking_usps",
            recipient_signature_present=True,
        )

        reconciler = EvidenceReconciler(orders=[real_order], shipments=[real_shipment])
        bundle = reconciler.reconcile_dispute(real_dispute)
        citations = bundle.to_citations()
        claim = ExtractedClaim(
            claim_id="CLM-REAL-01",
            claim_type="DELIVERY_COMPLETED",
            factual_assertion="Item delivered by USPS on 2026-10-18T14:22:00Z to postal code 95131.",
            supporting_sources=citations,
        )
        sources_dict = {
            "carrier_tracking_usps": real_shipment,
            "merchant_order": real_order,
            "paypal_dispute": real_dispute,
        }
        evaluation = policy_engine.evaluate(
            dispute=real_dispute,
            order=real_order,
            shipment=real_shipment,
            claim=claim,
            available_sources=sources_dict,
        )
        real_case = CaseData(
            dispute=real_dispute,
            bundle=bundle,
            evaluation=evaluation,
            claims=[claim],
            has_prompt_threat=False,
            scenario_id="SCENARIO_20_REAL_SANDBOX_FIXTURE_BASELINE",
        )
        cases[real_dispute.dispute_id] = real_case
        cases["SCENARIO_20_REAL_SANDBOX_FIXTURE_BASELINE"] = real_case

    # 2. 20 Benchmark Scenarios
    from docket.ai.deterministic import DeterministicFactExtractor
    fact_extractor = DeterministicFactExtractor()

    for scen in load_all_scenarios():
        reconciler = EvidenceReconciler(
            orders=scen.orders,
            shipments=scen.shipments,
            communications=scen.communications,
            refunds=scen.refunds,
        )
        bundle = reconciler.reconcile_dispute(scen.dispute)

        # Check prompt threat
        threat_detected = False
        for msg in scen.dispute.raw_messages:
            if isinstance(msg, dict):
                sanitized = prompt_guard.sanitize(msg.get("content", ""))
                if sanitized.is_suspicious:
                    threat_detected = True

        claims: List[ExtractedClaim] = []
        if scen.proposed_claim:
            c = scen.proposed_claim
            if not c.supporting_sources and bundle.is_reconciled():
                c = c.model_copy(update={"supporting_sources": bundle.to_citations()})
            claims.append(c)
        elif bundle.is_reconciled():
            extract_result = fact_extractor.extract_from_bundle(scen.dispute, bundle)
            claims.extend(extract_result.claims)

        goods_type = "INTANGIBLE" if "INTANGIBLE" in scen.scenario_id else "PHYSICAL_GOODS"
        scen_policy_engine = PolicyEngine(goods_type=goods_type)

        available_sources: Dict[str, Any] = {}
        for s in bundle.matched_shipments:
            available_sources[s.source_identifier] = s
            available_sources[s.tracking_number] = s
        if bundle.matched_order:
            available_sources[bundle.matched_order.order_id] = bundle.matched_order
            if bundle.matched_order.paypal_transaction_id:
                available_sources[bundle.matched_order.paypal_transaction_id] = bundle.matched_order
        available_sources[scen.dispute.dispute_id] = scen.dispute

        evaluation = scen_policy_engine.evaluate(
            dispute=scen.dispute,
            order=bundle.matched_order,
            shipment=bundle.get_primary_shipment(),
            claims=claims,
            available_sources=available_sources,
        )

        scen_case = CaseData(
            dispute=scen.dispute,
            bundle=bundle,
            evaluation=evaluation,
            claims=claims,
            has_prompt_threat=threat_detected,
            scenario_id=scen.scenario_id,
        )
        cases[scen.dispute.dispute_id] = scen_case
        cases[scen.scenario_id] = scen_case

    return cases


# ============================================================================
# FastAPI Application Factory
# ============================================================================

def create_app(
    audit_log_path: Optional[str] = None,
    secret_key: Optional[str] = None,
) -> FastAPI:
    """Create and configure the Docket API FastAPI instance."""
    app = FastAPI(
        title="Docket Dispute Command Engine API",
        version="1.0.0",
        description="Evidence-reconciliation, deterministic policy refusal barrier, and controlled PayPal dispute submission.",
    )

    # Enable CORS for local Vite development
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Dependencies & Services
    audit_logger = AuditLogger(storage_path=audit_log_path)
    approval_service = ApprovalService(secret_key=secret_key)
    formatter = EvidencePayloadFormatter()
    dispatcher = EvidenceDispatcher(
        approval_service=approval_service,
        audit_logger=audit_logger,
        formatter=formatter,
    )
    policy_engine = PolicyEngine()

    cases_store: Dict[str, CaseData] = load_initial_cases(policy_engine)

    # ------------------------------------------------------------------------
    # Health Endpoint
    # ------------------------------------------------------------------------
    @app.get("/api/health")
    def health():
        return {
            "status": "ok",
            "version": "1.0.0",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "total_cases_loaded": len(cases_store),
        }

    # ------------------------------------------------------------------------
    # Disputes List Endpoint (AG Grid Triage View)
    # ------------------------------------------------------------------------
    @app.get("/api/disputes", response_model=List[DisputeSummaryResponse])
    def get_disputes():
        summaries: List[DisputeSummaryResponse] = []
        seen = set()
        for d_id, c_data in cases_store.items():
            if id(c_data) in seen:
                continue
            seen.add(id(c_data))

            d = c_data.dispute
            b = c_data.bundle
            ev = c_data.evaluation

            s0 = b.matched_shipments[0] if b.matched_shipments else None
            o0 = b.matched_order

            appr_status = "PENDING"
            if c_data.approval_record:
                appr_status = c_data.approval_record.decision.value

            subm_status = "NOT_SUBMITTED"
            if c_data.dispatch_result:
                subm_status = "SUBMITTED" if c_data.dispatch_result.success else "FAILED"

            summaries.append(
                DisputeSummaryResponse(
                    dispute_id=d.dispute_id,
                    scenario_id=c_data.scenario_id,
                    reason=d.reason,
                    lifecycle_stage=d.lifecycle_stage.value,
                    status=d.status.value,
                    amount=str(d.dispute_amount.value),
                    currency=d.dispute_amount.currency_code,
                    due_date=d.seller_response_due_date.isoformat() if d.seller_response_due_date else None,
                    customer_name=o0.customer_name if o0 else None,
                    customer_email=o0.customer_email if o0 else None,
                    reconciliation_status=b.status.value,
                    matched_order_id=o0.order_id if o0 else None,
                    tracking_number=s0.tracking_number if s0 else None,
                    tracking_status=s0.tracking_status.value if s0 else None,
                    carrier_name=s0.carrier_name if s0 else None,
                    factual_readiness=ev.factual_readiness.value,
                    action_readiness=ev.action_readiness.value,
                    overall_decision=ev.overall_decision.value,
                    violated_invariants=ev.get_violations(),
                    discrepancies=[disc.code for disc in b.discrepancies],
                    is_ready_for_submission=ev.is_ready_for_submission(),
                    approval_status=appr_status,
                    submission_status=subm_status,
                    has_prompt_threat=c_data.has_prompt_threat,
                )
            )
        return summaries

    # ------------------------------------------------------------------------
    # Dispute Case Deep Dive
    # ------------------------------------------------------------------------
    @app.get("/api/disputes/{dispute_id}")
    def get_dispute_detail(dispute_id: str):
        if dispute_id not in cases_store:
            raise HTTPException(status_code=404, detail=f"Dispute {dispute_id} not found.")

        c_data = cases_store[dispute_id]
        payload = formatter.format_fulfillment_evidence(bundle=c_data.bundle)

        return {
            "dispute_id": c_data.dispute.dispute_id,
            "dispute": c_data.dispute.model_dump(),
            "matched_order": c_data.bundle.matched_order.model_dump() if c_data.bundle.matched_order else None,
            "matched_shipments": [s.model_dump() for s in c_data.bundle.matched_shipments],
            "matched_refunds": [r.model_dump() for r in c_data.bundle.matched_refunds],
            "claims": [c.model_dump() for c in c_data.claims],
            "evaluation": {
                "overall_decision": c_data.evaluation.overall_decision.value,
                "factual_readiness": c_data.evaluation.factual_readiness.value,
                "action_readiness": c_data.evaluation.action_readiness.value,
                "summary": c_data.evaluation.summary,
                "is_ready_for_submission": c_data.evaluation.is_ready_for_submission(),
                "check_results": [r.model_dump() for r in c_data.evaluation.check_results],
                "advisories": [a.model_dump() for a in c_data.evaluation.advisories],
            },
            "proposed_payload": payload,
            "approval_request": c_data.approval_request.model_dump() if c_data.approval_request else None,
            "approval_record": c_data.approval_record.model_dump() if c_data.approval_record else None,
            "dispatch_result": c_data.dispatch_result.model_dump() if c_data.dispatch_result else None,
            "has_prompt_threat": c_data.has_prompt_threat,
        }

    # ------------------------------------------------------------------------
    # Generate HMAC Approval Ticket
    # ------------------------------------------------------------------------
    @app.post("/api/disputes/{dispute_id}/ticket")
    def generate_ticket(dispute_id: str):
        if dispute_id not in cases_store:
            raise HTTPException(status_code=404, detail=f"Dispute {dispute_id} not found.")

        c_data = cases_store[dispute_id]
        payload = formatter.format_fulfillment_evidence(bundle=c_data.bundle)
        ticket = approval_service.create_approval_request(
            dispute=c_data.dispute,
            policy_evaluation=c_data.evaluation,
            proposed_payload=payload,
            bundle=c_data.bundle,
        )
        c_data.approval_request = ticket

        audit_logger.log_event(
            event_type=AuditEventType.APPROVAL_REQUESTED,
            dispute_id=dispute_id,
            actor="SYSTEM",
            payload={
                "approval_id": ticket.approval_id,
                "payload_hash": ticket.payload_hash,
                "expires_at": ticket.expires_at.isoformat(),
            },
        )
        return ticket.model_dump()

    # ------------------------------------------------------------------------
    # Authorize Dispute (Approve or Reject)
    # ------------------------------------------------------------------------
    @app.post("/api/disputes/{dispute_id}/authorize")
    def authorize_dispute(dispute_id: str, req: AuthorizeRequest):
        if dispute_id not in cases_store:
            raise HTTPException(status_code=404, detail=f"Dispute {dispute_id} not found.")

        c_data = cases_store[dispute_id]
        if not c_data.approval_request:
            # Auto-generate ticket if not generated yet
            payload = formatter.format_fulfillment_evidence(bundle=c_data.bundle)
            c_data.approval_request = approval_service.create_approval_request(
                dispute=c_data.dispute,
                policy_evaluation=c_data.evaluation,
                proposed_payload=payload,
                bundle=c_data.bundle,
            )

        record = approval_service.record_approval(
            request=c_data.approval_request,
            merchant_user_id=req.merchant_user_id,
            decision=req.decision,
            rejection_reason=req.rejection_reason,
            client_ip="127.0.0.1",
        )
        c_data.approval_record = record

        evt_type = (
            AuditEventType.APPROVAL_GRANTED
            if req.decision == ApprovalDecision.APPROVE
            else AuditEventType.APPROVAL_REJECTED
        )
        audit_logger.log_event(
            event_type=evt_type,
            dispute_id=dispute_id,
            actor=req.merchant_user_id,
            payload={
                "approval_id": record.approval_id,
                "decision": record.decision.value,
                "rejection_reason": record.rejection_reason,
            },
        )
        return record.model_dump()

    # ------------------------------------------------------------------------
    # Controlled Dispatch to PayPal
    # ------------------------------------------------------------------------
    @app.post("/api/disputes/{dispute_id}/dispatch")
    def dispatch_dispute(dispute_id: str, req: DispatchRequest):
        if dispute_id not in cases_store:
            raise HTTPException(status_code=404, detail=f"Dispute {dispute_id} not found.")

        c_data = cases_store[dispute_id]

        try:
            result = dispatcher.dispatch_evidence(
                dispute=c_data.dispute,
                bundle=c_data.bundle,
                evaluation=c_data.evaluation,
                approval_record=c_data.approval_record,
                idempotency_key=req.idempotency_key or f"idemp_{uuid4().hex[:8]}",
                custom_notes=req.custom_notes,
            )
            c_data.dispatch_result = result
            return result.model_dump()

        except SubmissionBlockedError as e:
            raise HTTPException(status_code=400, detail=str(e))
        except MerchantApprovalRequiredError as e:
            raise HTTPException(status_code=400, detail=str(e))
        except SubmissionRejectedError as e:
            raise HTTPException(status_code=400, detail=str(e))
        except DuplicateSubmissionError as e:
            raise HTTPException(status_code=409, detail=str(e))
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Internal dispatch failure: {e}")

    # ------------------------------------------------------------------------
    # Audit Trail Viewer
    # ------------------------------------------------------------------------
    @app.get("/api/audit-trail")
    def get_audit_trail():
        events = audit_logger.get_events()
        chain_intact = audit_logger.verify_chain_integrity()
        return {
            "total_events": len(events),
            "chain_intact": chain_intact,
            "events": [e.model_dump() for e in events],
        }

    # ------------------------------------------------------------------------
    # Benchmark Evaluation Scorecard
    # ------------------------------------------------------------------------
    @app.get("/api/eval/scorecard")
    def get_eval_scorecard():
        matrix_path = Path("artifacts/docket_evaluation_matrix.json")
        if not matrix_path.exists():
            raise HTTPException(status_code=404, detail="Evaluation matrix artifact not found.")

        with open(matrix_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data

    return app


if __name__ == "__main__":
    import uvicorn
    app = create_app()
    uvicorn.run(app, host="127.0.0.1", port=8000)
