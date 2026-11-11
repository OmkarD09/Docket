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

from datetime import datetime, timedelta, timezone
from decimal import Decimal
import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional
from uuid import uuid4

from fastapi import Cookie, Depends, FastAPI, Header, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from docket.models.auth import (
    AuthenticatedMerchant,
    DemoMerchantProfile,
    DemoSessionRequest,
    LoginRequest,
    AuthSessionResponse,
)
from docket.auth.service import (
    AuthService,
    AuthenticationError,
    InvalidTokenError,
    SessionExpiredError,
    SessionRevokedError,
    InvalidCredentialsError,
)

from docket.models.dispute import (
    DisputeCase,
    DisputeLifecycleStage,
    DisputeReason,
    DisputeStatus,
    Money,
)
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
from docket.models.policy import DecisionType, OverallPolicyEvaluation, PolicyCheckResult
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
from docket.audit.logger import AuditLogger, AuditVerificationError
from docket.database.repository import DocketRepository
from docket.ai.prompt_guard import PromptInjectionGuard
from docket.eval.scenarios import load_all_scenarios
from docket.sync.automation import AutomationService, SyncStatus, AuditStatus


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
    dispute_category: str = "SYNTHETIC_BENCHMARK"
    is_archived: bool = False


class AuthorizeRequest(BaseModel):
    merchant_user_id: Optional[str] = None
    decision: ApprovalDecision = ApprovalDecision.APPROVE
    rejection_reason: Optional[str] = None
    notes: Optional[str] = None


class DispatchRequest(BaseModel):
    merchant_user_id: Optional[str] = None
    idempotency_key: Optional[str] = None
    custom_notes: Optional[str] = None


class WebhookIngestRequest(BaseModel):
    dispute_id: str
    reason: str = "MERCHANDISE_OR_SERVICE_NOT_RECEIVED"
    status: str = "WAITING_FOR_SELLER_RESPONSE"
    amount: str = "25.00"
    currency: str = "USD"
    idempotency_key: Optional[str] = None
    actor: str = "PAYPAL_WEBHOOK"


class WebhookIngestResponse(BaseModel):
    event_id: str
    dispute_id: str
    is_duplicate: bool
    event_type: str
    message: str


class SemanticWorkflowRequest(BaseModel):
    dispute_id: str
    message_text: Optional[str] = None


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
        dispute_category: str = "SYNTHETIC_BENCHMARK",
        is_archived: bool = False,
        archived_at: Optional[str] = None,
        archival_reason: Optional[str] = None,
    ):
        self.dispute = dispute
        self.bundle = bundle
        self.evaluation = evaluation
        self.claims = claims
        self.has_prompt_threat = has_prompt_threat
        self.scenario_id = scenario_id
        self.dispute_category = dispute_category
        self.is_archived = is_archived
        self.archived_at = archived_at
        self.archival_reason = archival_reason
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
            dispute_category="REAL_SANDBOX",
        )
        cases[real_dispute.dispute_id] = real_case
        cases["SCENARIO_20_REAL_SANDBOX_FIXTURE_BASELINE"] = real_case

    # 2. 20 Benchmark Scenarios
    from docket.ai.factory import get_fact_extractor
    fact_extractor = get_fact_extractor()

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
            dispute_category="SYNTHETIC_BENCHMARK",
        )
        if scen.dispute.dispute_id not in cases or cases[scen.dispute.dispute_id].dispute_category != "REAL_SANDBOX":
            cases[scen.dispute.dispute_id] = scen_case
        cases[scen.scenario_id] = scen_case

    return cases


# ============================================================================
# Live PayPal Sandbox Read-Only Retrieval & Ingestion
# ============================================================================

def sync_live_paypal_sandbox_dispute(
    repository: DocketRepository,
    audit_logger: AuditLogger,
    policy_engine: PolicyEngine,
    cases_store: Dict[str, CaseData],
    dispute_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Retrieve genuine dispute from PayPal Sandbox API and persist to SQLite with provenance REAL_SANDBOX.

    Strictly read-only retrieval: no dispute modifications, evidence submissions, or API mutations.
    """
    from docket.paypal.client import PayPalSandboxClient, PayPalDisputeError, ConfigurationError

    target_id = dispute_id or os.getenv("PAYPAL_DISPUTE_ID", "PP-R-NKI-10193390")

    try:
        client = PayPalSandboxClient()
    except ConfigurationError as e:
        return {
            "success": False,
            "status": "BLOCKED",
            "dispute_id": target_id,
            "blocker": str(e),
            "message": "Missing PAYPAL_CLIENT_ID or PAYPAL_CLIENT_SECRET in environment / .env",
        }

    try:
        raw_data = client.get_dispute(target_id)
    except PayPalDisputeError as e:
        return {
            "success": False,
            "status": "API_ERROR",
            "dispute_id": target_id,
            "blocker": str(e),
            "status_code": getattr(e, "status_code", None),
        }
    except Exception as e:
        return {
            "success": False,
            "status": "NETWORK_ERROR",
            "dispute_id": target_id,
            "blocker": f"Unexpected error during PayPal retrieval: {e}",
        }

    if not isinstance(raw_data, dict) or raw_data.get("dispute_id") != target_id:
        return {
            "success": False,
            "status": "INVALID_RESPONSE",
            "dispute_id": target_id,
            "blocker": f"Retrieved payload does not match requested dispute ID {target_id}.",
        }

    # Construct DisputeCase from live PayPal response
    live_dispute = DisputeCase.from_paypal_response(raw_data)

    # Match merchant order and shipment records for reconciliation
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
        source_provenance="SYNTHETIC_FIXTURE",
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
        source_provenance="SYNTHETIC_FIXTURE",
    )

    reconciler = EvidenceReconciler(orders=[real_order], shipments=[real_shipment])
    bundle = reconciler.reconcile_dispute(live_dispute)
    citations = bundle.to_citations()
    claim = ExtractedClaim(
        claim_id=f"CLM-LIVE-{target_id[:8]}",
        claim_type="DELIVERY_COMPLETED",
        factual_assertion=f"Item delivered by USPS on 2026-10-18T14:22:00Z to postal code 95131.",
        supporting_sources=citations,
    )
    sources_dict = {
        "carrier_tracking_usps": real_shipment,
        "merchant_order": real_order,
        "paypal_dispute": live_dispute,
    }
    evaluation = policy_engine.evaluate(
        dispute=live_dispute,
        order=real_order,
        shipment=real_shipment,
        claim=claim,
        available_sources=sources_dict,
    )

    # Contextual safety advisories for real sandbox disputes
    now = datetime.now(timezone.utc)
    if live_dispute.seller_response_due_date and live_dispute.seller_response_due_date < now:
        evaluation.advisories.append(
            PolicyCheckResult(
                decision=DecisionType.BLOCK,
                rule_identifier="RULE_DEADLINE_STATUS",
                explanation=f"Seller response deadline expired on {live_dispute.seller_response_due_date.isoformat()} (OVERDUE). Response window has closed.",
                violated_invariants=["RESPONSE_DEADLINE_EXPIRED"],
                recommended_next_action="Response deadline expired; direct PayPal merchant settlement required.",
                is_advisory=True,
            )
        )
    evaluation.advisories.append(
        PolicyCheckResult(
            decision=DecisionType.REVIEW,
            rule_identifier="RULE_EVIDENCE_PROVENANCE",
            explanation="Merchant order and carrier shipment are synthetic simulation fixtures. Automated submission to live PayPal Sandbox is prohibited.",
            violated_invariants=["SUPPORTING_EVIDENCE_SYNTHETIC"],
            recommended_next_action="Connect live ERP and carrier API before dispatching evidence.",
            is_advisory=True,
        )
    )

    # 1. Persist to SQLite with explicit provenance REAL_SANDBOX
    repository.save_full_case(
        dispute=live_dispute,
        bundle=bundle,
        evaluation=evaluation,
        claims=[claim],
        scenario_id="SCENARIO_20_REAL_SANDBOX_FIXTURE_BASELINE",
        has_prompt_threat=False,
        dispute_category="REAL_SANDBOX",
    )

    # 2. Append event to canonical audit ledger: distinguish initial ingestion vs refresh/synchronization
    is_already_known = (live_dispute.dispute_id in cases_store) or (repository.get_dispute(live_dispute.dispute_id) is not None)
    event_type = AuditEventType.DISPUTE_SYNCHRONIZED if is_already_known else AuditEventType.DISPUTE_INGESTED
    audit_event = audit_logger.log_event(
        event_type=event_type,
        dispute_id=live_dispute.dispute_id,
        actor="PAYPAL_SANDBOX_API",
        payload={
            "provenance": "REAL_SANDBOX",
            "operation": "REFRESH_SYNCHRONIZATION" if is_already_known else "INITIAL_INGESTION",
            "status": live_dispute.status.value,
            "lifecycle_stage": live_dispute.lifecycle_stage.value,
            "amount": str(live_dispute.dispute_amount.value),
            "currency": live_dispute.dispute_amount.currency_code,
            "reason": live_dispute.reason.value,
            "seller_response_due_date": live_dispute.seller_response_due_date.isoformat() if live_dispute.seller_response_due_date else None,
            "retrieval_mode": "LIVE_OAUTH2_CLIENT_CREDENTIALS",
            "endpoint": f"https://api-m.sandbox.paypal.com/v1/customer/disputes/{target_id}",
        },
    )

    # 3. Update memory store
    case_data = CaseData(
        dispute=live_dispute,
        bundle=bundle,
        evaluation=evaluation,
        claims=[claim],
        has_prompt_threat=False,
        scenario_id="SCENARIO_20_REAL_SANDBOX_FIXTURE_BASELINE",
        dispute_category="REAL_SANDBOX",
    )
    cases_store[live_dispute.dispute_id] = case_data
    cases_store["SCENARIO_20_REAL_SANDBOX_FIXTURE_BASELINE"] = case_data

    return {
        "success": True,
        "status": "INGESTED",
        "dispute_id": live_dispute.dispute_id,
        "provenance": "REAL_SANDBOX",
        "amount": str(live_dispute.dispute_amount.value),
        "currency": live_dispute.dispute_amount.currency_code,
        "reason": live_dispute.reason.value,
        "lifecycle_stage": live_dispute.lifecycle_stage.value,
        "status_field": live_dispute.status.value,
        "seller_response_due_date": live_dispute.seller_response_due_date.isoformat() if live_dispute.seller_response_due_date else None,
        "audit_event_id": audit_event.event_id,
        "audit_event_hash": audit_event.event_hash,
    }


# ============================================================================
# FastAPI Application Factory
# ============================================================================

def create_app(
    audit_log_path: Optional[str] = None,
    secret_key: Optional[str] = None,
    db_path: Optional[str] = None,
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

    # Database resolution & initialization
    if db_path is None:
        if audit_log_path:
            db_path = str(Path(audit_log_path).with_suffix(".db"))
        else:
            db_path = os.getenv("DOCKET_DB_PATH", "artifacts/docket.db")

    repository = DocketRepository(db_path=db_path)

    # Dependencies & Services
    audit_logger = AuditLogger(storage_path=audit_log_path, repository=repository)
    approval_service = ApprovalService(secret_key=secret_key, repository=repository)
    auth_service = AuthService(secret_key=secret_key)
    formatter = EvidencePayloadFormatter()
    dispatcher = EvidenceDispatcher(
        approval_service=approval_service,
        audit_logger=audit_logger,
        formatter=formatter,
    )
    policy_engine = PolicyEngine()

    # Load cases from relational SQLite persistence or seed from fixtures
    cases_store: Dict[str, CaseData] = {}
    persisted_cases = repository.load_persisted_cases()

    if persisted_cases:
        for c in persisted_cases:
            case_obj = CaseData(
                dispute=c["dispute"],
                bundle=c["bundle"],
                evaluation=c["evaluation"] or policy_engine.evaluate(
                    dispute=c["dispute"],
                    order=c["bundle"].matched_order,
                    shipment=c["bundle"].get_primary_shipment(),
                    claims=c["claims"],
                ),
                claims=c["claims"],
                has_prompt_threat=c["has_prompt_threat"],
                scenario_id=c["scenario_id"],
                dispute_category=c.get("dispute_category", "SYNTHETIC_BENCHMARK"),
                is_archived=c.get("is_archived", False),
            )
            case_obj.approval_request = c["approval_request"]
            case_obj.approval_record = c["approval_record"]
            case_obj.dispatch_result = c["dispatch_result"]
            cases_store[c["dispute"].dispute_id] = case_obj
            if c["scenario_id"]:
                cases_store[c["scenario_id"]] = case_obj

    # Seed baseline fixtures if not yet persisted
    initial_cases = load_initial_cases(policy_engine)
    for key, initial_case in initial_cases.items():
        if initial_case.dispute.dispute_id not in cases_store:
            cases_store[initial_case.dispute.dispute_id] = initial_case
            if initial_case.scenario_id:
                cases_store[initial_case.scenario_id] = initial_case
            cat = "REAL_SANDBOX" if initial_case.dispute.dispute_id == "PP-R-NKI-10193390" else "SYNTHETIC_BENCHMARK"
            try:
                repository.save_full_case(
                    dispute=initial_case.dispute,
                    bundle=initial_case.bundle,
                    evaluation=initial_case.evaluation,
                    claims=initial_case.claims,
                    scenario_id=initial_case.scenario_id,
                    has_prompt_threat=initial_case.has_prompt_threat,
                    dispute_category=cat,
                    approval_request=initial_case.approval_request,
                    approval_record=initial_case.approval_record,
                    dispatch_result=initial_case.dispatch_result,
                )
            except Exception:
                pass

    # Automated Background State Synchronization & Continuous Audit Verification
    automation_service = AutomationService(
        repository=repository,
        audit_logger=audit_logger,
        policy_engine=policy_engine,
        cases_store=cases_store,
        auto_start=os.getenv("DOCKET_DISABLE_BG_SCHEDULER", "false").lower() not in ("true", "1", "yes"),
    )

    @app.on_event("shutdown")
    def shutdown_automation():
        automation_service.stop()

    # ========================================================================
    # Merchant Authentication Dependency & Route Protection
    # ========================================================================
    def get_current_merchant(
        request: Request,
        authorization: Optional[str] = Header(None),
        docket_session: Optional[str] = Cookie(None),
    ) -> AuthenticatedMerchant:
        """Derive the authenticated merchant principal from HttpOnly cookie or Bearer token."""
        token = None
        if docket_session:
            token = docket_session
        elif authorization and authorization.startswith("Bearer "):
            token = authorization[7:].strip()

        if not token:
            raise HTTPException(
                status_code=401,
                detail="Authentication required. Please sign in or initiate a demo session.",
                headers={"WWW-Authenticate": "Bearer"},
            )

        try:
            return auth_service.validate_token(token)
        except SessionExpiredError as e:
            raise HTTPException(
                status_code=401,
                detail=f"Session expired: {e}",
                headers={"WWW-Authenticate": "Bearer"},
            )
        except SessionRevokedError:
            raise HTTPException(
                status_code=401,
                detail="Session has been revoked.",
                headers={"WWW-Authenticate": "Bearer"},
            )
        except (InvalidTokenError, AuthenticationError) as e:
            raise HTTPException(
                status_code=401,
                detail=f"Invalid authentication token: {e}",
                headers={"WWW-Authenticate": "Bearer"},
            )
        except Exception as e:
            raise HTTPException(
                status_code=401,
                detail=f"Authentication validation failed: {e}",
                headers={"WWW-Authenticate": "Bearer"},
            )

    # ------------------------------------------------------------------------
    # Merchant Authentication & Session Endpoints
    # ------------------------------------------------------------------------
    @app.get("/api/auth/profiles")
    def get_auth_profiles():
        """List available demo personas for instant judge/evaluator access."""
        return [p.model_dump() for p in auth_service.get_available_profiles()]

    @app.post("/api/auth/demo-session", response_model=AuthSessionResponse)
    def issue_demo_session(req: DemoSessionRequest, response: Response):
        """Issue a cryptographic demo session for the selected merchant persona."""
        merchant, token = auth_service.create_session(req.profile_id)
        response.set_cookie(
            key="docket_session",
            value=token,
            httponly=True,
            samesite="lax",
            max_age=auth_service.ttl_seconds,
            secure=False,
            path="/",
        )
        return AuthSessionResponse(
            success=True,
            merchant=merchant,
            token=token,
            expires_at=merchant.expires_at.isoformat(),
            environment="PAYPAL_SANDBOX_REST_V1",
        )

    @app.post("/api/auth/login", response_model=AuthSessionResponse)
    def login(req: LoginRequest, response: Response):
        """Authenticate with demo credentials or direct persona request."""
        try:
            merchant, token = auth_service.authenticate_credentials(
                email=req.email,
                password=req.password,
                profile_id=req.profile_id,
            )
        except InvalidCredentialsError as e:
            raise HTTPException(status_code=401, detail=str(e))
        except AuthenticationError as e:
            raise HTTPException(status_code=401, detail=str(e))

        response.set_cookie(
            key="docket_session",
            value=token,
            httponly=True,
            samesite="lax",
            max_age=auth_service.ttl_seconds,
            secure=False,
            path="/",
        )
        return AuthSessionResponse(
            success=True,
            merchant=merchant,
            token=token,
            expires_at=merchant.expires_at.isoformat(),
            environment="PAYPAL_SANDBOX_REST_V1",
        )

    @app.get("/api/auth/me", response_model=AuthenticatedMerchant)
    def get_current_user_profile(
        current_merchant: AuthenticatedMerchant = Depends(get_current_merchant),
    ):
        """Return the authenticated merchant principal for current valid session."""
        return current_merchant

    @app.post("/api/auth/logout")
    def logout(
        response: Response,
        authorization: Optional[str] = Header(None),
        docket_session: Optional[str] = Cookie(None),
    ):
        """Explicitly revoke the session token and clear browser cookie."""
        token = docket_session
        if not token and authorization and authorization.startswith("Bearer "):
            token = authorization[7:].strip()
        if token and "." in token:
            parts = token.strip().split(".")
            if len(parts) == 4:
                session_id = parts[0]
                auth_service.revoke_session(session_id)
        response.delete_cookie(key="docket_session", path="/")
        return {"success": True, "message": "Signed out successfully."}

    # ------------------------------------------------------------------------
    # Health Endpoint
    # ------------------------------------------------------------------------
    @app.get("/api/health")
    def health():
        from docket.ai.factory import get_fact_extractor
        active_extractor = get_fact_extractor()
        ai_mode = os.getenv("DOCKET_AI_MODE", "offline").strip().lower()
        ai_provider = os.getenv("DOCKET_AI_PROVIDER", "gemini" if ai_mode == "live" else "offline-deterministic")
        ai_model = os.getenv("GEMINI_MODEL", "gemini-2.5-flash") if ai_mode == "live" else None

        unique_cases = len({id(c) for c in cases_store.values()})
        db_counts = repository.get_dispute_counts()

        return {
            "status": "ok",
            "version": "1.0.0",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "total_cases_loaded": unique_cases,
            "case_counts": {
                "total_unique_cases": unique_cases,
                "alias_lookup_keys": len(cases_store),
                "real_sandbox_disputes": db_counts["breakdown"]["real_sandbox"],
                "synthetic_benchmark_scenarios": db_counts["breakdown"]["synthetic_benchmark"],
                "live_webhook_disputes": db_counts["breakdown"]["live_webhook"],
                "archived_disputes": db_counts["archived_disputes"],
            },
            "database": {
                "type": "sqlite",
                "path": str(repository.conn.raw_path),
                **db_counts,
            },
            "ai_mode": ai_mode,
            "ai_extractor": type(active_extractor).__name__,
            "ai_provider": ai_provider,
            "ai_model": ai_model,
            "sync_status": automation_service.get_sync_status(),
            "audit_integrity": automation_service.get_audit_status(),
        }

    # ------------------------------------------------------------------------
    # Automatic Sync & Continuous Audit Integrity Telemetry Endpoints
    # ------------------------------------------------------------------------
    @app.get("/api/sync/status")
    def get_sync_status():
        """Retrieve live PayPal synchronisation status, latency, and telemetry."""
        return automation_service.get_sync_status()

    @app.get("/api/audit-trail/status")
    def get_audit_status():
        """Retrieve live continuous cryptographic audit integrity verification status."""
        return automation_service.get_audit_status()

    @app.post("/api/admin/sync/trigger")
    def admin_trigger_sync(
        current_merchant: AuthenticatedMerchant = Depends(get_current_merchant),
    ):
        """Administrative maintenance endpoint to trigger immediate dispute reconciliation."""
        return automation_service.reconcile_paypal_disputes(force=True)

    @app.post("/api/admin/audit/verify")
    def admin_trigger_audit_verify(
        current_merchant: AuthenticatedMerchant = Depends(get_current_merchant),
    ):
        """Administrative maintenance endpoint to trigger immediate full-chain verification."""
        return automation_service.periodic_audit_verification()

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

            now = datetime.now(timezone.utc)
            is_overdue = bool(d.seller_response_due_date and d.seller_response_due_date < now)
            has_synthetic_evidence = (
                c_data.dispute_category == "REAL_SANDBOX" and (
                    (o0 and getattr(o0, "source_provenance", None) == "SYNTHETIC_FIXTURE")
                    or any(getattr(s, "source_provenance", None) == "SYNTHETIC_FIXTURE" for s in b.matched_shipments)
                )
            )

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
                    dispute_category=c_data.dispute_category,
                    is_archived=c_data.is_archived,
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
        now = datetime.now(timezone.utc)
        d = c_data.dispute
        is_overdue = bool(d.seller_response_due_date and d.seller_response_due_date < now)
        has_synthetic_evidence = (
            c_data.dispute_category == "REAL_SANDBOX" and (
                (c_data.bundle.matched_order and getattr(c_data.bundle.matched_order, "source_provenance", None) == "SYNTHETIC_FIXTURE")
                or any(getattr(s, "source_provenance", None) == "SYNTHETIC_FIXTURE" for s in c_data.bundle.matched_shipments)
            )
        )

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
            "dispute_category": c_data.dispute_category,
            "is_overdue": is_overdue,
            "has_synthetic_evidence": has_synthetic_evidence,
            "action_submittable": (not is_overdue and not has_synthetic_evidence and c_data.evaluation.is_ready_for_submission()),
        }

    # ------------------------------------------------------------------------
    # Generate HMAC Approval Ticket
    # ------------------------------------------------------------------------
    @app.post("/api/disputes/{dispute_id}/ticket")
    def generate_ticket(
        dispute_id: str,
        current_merchant: AuthenticatedMerchant = Depends(get_current_merchant),
    ):
        if dispute_id not in cases_store:
            raise HTTPException(status_code=404, detail=f"Dispute {dispute_id} not found.")

        c_data = cases_store[dispute_id]
        payload = formatter.format_fulfillment_evidence(bundle=c_data.bundle)
        ticket = approval_service.create_approval_request(
            dispute=c_data.dispute,
            policy_evaluation=c_data.evaluation,
            proposed_payload=payload,
            merchant_user_id=current_merchant.merchant_user_id,
            bundle=c_data.bundle,
        )
        c_data.approval_request = ticket
        try:
            repository.update_dispute_status(
                dispute_id=dispute_id,
                status=c_data.dispute.status.value,
                approval_request=ticket,
            )
        except Exception:
            pass

        audit_logger.log_event(
            event_type=AuditEventType.APPROVAL_REQUESTED,
            dispute_id=dispute_id,
            actor=current_merchant.merchant_user_id,
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
    def authorize_dispute(
        dispute_id: str,
        req: AuthorizeRequest,
        current_merchant: AuthenticatedMerchant = Depends(get_current_merchant),
    ):
        if dispute_id not in cases_store:
            raise HTTPException(status_code=404, detail=f"Dispute {dispute_id} not found.")

        # Reject caller impersonation attempts
        if req.merchant_user_id and req.merchant_user_id != current_merchant.merchant_user_id:
            raise HTTPException(
                status_code=403,
                detail=f"Merchant identity mismatch: authenticated principal is '{current_merchant.merchant_user_id}', cannot authorize as '{req.merchant_user_id}'.",
            )

        caller_actor = current_merchant.merchant_user_id
        c_data = cases_store[dispute_id]

        # Sensitive-Operation Integrity Gate: Reject authorization if audit ledger is compromised
        try:
            audit_logger.verify_sensitive_operation_gate(
                dispute_id=dispute_id,
                approval_request=c_data.approval_request,
                approval_record=c_data.approval_record,
            )
        except AuditVerificationError as e:
            raise HTTPException(
                status_code=409,
                detail=f"Sensitive operation blocked: audit ledger integrity failure detected: {e}",
            )

        if not c_data.approval_request:
            # Auto-generate ticket bound to authenticated principal
            payload = formatter.format_fulfillment_evidence(bundle=c_data.bundle)
            c_data.approval_request = approval_service.create_approval_request(
                dispute=c_data.dispute,
                policy_evaluation=c_data.evaluation,
                proposed_payload=payload,
                merchant_user_id=caller_actor,
                bundle=c_data.bundle,
            )

        record = approval_service.record_approval(
            request=c_data.approval_request,
            merchant_user_id=caller_actor,
            decision=req.decision,
            rejection_reason=req.rejection_reason,
            client_ip="127.0.0.1",
        )
        c_data.approval_record = record
        try:
            repository.save_approval_record(record)
            repository.update_dispute_status(
                dispute_id=dispute_id,
                status=c_data.dispute.status.value,
                approval_request=c_data.approval_request,
            )
        except Exception:
            pass

        evt_type = (
            AuditEventType.APPROVAL_GRANTED
            if req.decision == ApprovalDecision.APPROVE
            else AuditEventType.APPROVAL_REJECTED
        )
        audit_logger.log_event(
            event_type=evt_type,
            dispute_id=dispute_id,
            actor=caller_actor,
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
    def dispatch_dispute(
        dispute_id: str,
        req: DispatchRequest,
        current_merchant: AuthenticatedMerchant = Depends(get_current_merchant),
    ):
        if dispute_id not in cases_store:
            raise HTTPException(status_code=404, detail=f"Dispute {dispute_id} not found.")

        # Reject caller impersonation attempts
        if req.merchant_user_id and req.merchant_user_id != current_merchant.merchant_user_id:
            raise HTTPException(
                status_code=403,
                detail=f"Merchant identity mismatch: authenticated principal is '{current_merchant.merchant_user_id}', cannot dispatch as '{req.merchant_user_id}'.",
            )

        caller_actor = current_merchant.merchant_user_id
        c_data = cases_store[dispute_id]

        # Sensitive-Operation Integrity Gate: Reject dispatch if audit ledger is compromised
        try:
            audit_logger.verify_sensitive_operation_gate(
                dispute_id=dispute_id,
                approval_request=c_data.approval_request,
                approval_record=c_data.approval_record,
            )
        except AuditVerificationError as e:
            raise HTTPException(
                status_code=409,
                detail=f"Sensitive operation blocked: audit ledger integrity failure detected: {e}",
            )

        try:
            result = dispatcher.dispatch_evidence(
                dispute=c_data.dispute,
                bundle=c_data.bundle,
                evaluation=c_data.evaluation,
                approval_record=c_data.approval_record,
                caller_merchant_id=caller_actor,
                idempotency_key=req.idempotency_key or f"idemp_{uuid4().hex[:8]}",
                custom_notes=req.custom_notes,
            )
            c_data.dispatch_result = result
            try:
                new_status = "RESOLVED" if result.success else c_data.dispute.status.value
                repository.update_dispute_status(
                    dispute_id=dispute_id,
                    status=new_status,
                    dispatch_result=result,
                )
            except Exception:
                pass
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
    # Archive Dispute (Soft Deletion for Compliance & Audit Retention)
    # ------------------------------------------------------------------------
    @app.post("/api/disputes/{dispute_id}/archive")
    def archive_dispute_endpoint(
        dispute_id: str,
        reason: str = "MERCHANT_ARCHIVED",
        current_merchant: AuthenticatedMerchant = Depends(get_current_merchant),
    ):
        if dispute_id not in cases_store:
            raise HTTPException(status_code=404, detail=f"Dispute {dispute_id} not found.")

        c_data = cases_store[dispute_id]
        c_data.is_archived = True
        c_data.archived_at = datetime.now(timezone.utc).isoformat()
        c_data.archival_reason = reason
        repository.archive_dispute(dispute_id, reason=reason)

        audit_logger.log_event(
            event_type=AuditEventType.DISPUTE_SYNCHRONIZED,
            dispute_id=dispute_id,
            actor=current_merchant.merchant_user_id,
            payload={"action": "ARCHIVE_DISPUTE", "reason": reason, "archived_at": c_data.archived_at},
        )
        return {
            "dispute_id": dispute_id,
            "is_archived": True,
            "archived_at": c_data.archived_at,
            "reason": reason,
        }

    # ------------------------------------------------------------------------
    # Refresh Dispute State (Live Sandbox or Local Store)
    # ------------------------------------------------------------------------
    @app.post("/api/disputes/{dispute_id}/refresh")
    def refresh_dispute_endpoint(
        dispute_id: str,
        current_merchant: AuthenticatedMerchant = Depends(get_current_merchant),
    ):
        """Refresh current dispute state from live PayPal Sandbox API or reload local case."""
        if dispute_id == "PP-R-NKI-10193390" or "REAL_SANDBOX" in dispute_id:
            res = sync_live_paypal_sandbox_dispute(
                repository=repository,
                audit_logger=audit_logger,
                policy_engine=policy_engine,
                cases_store=cases_store,
                dispute_id=dispute_id,
            )
            return res
        if dispute_id not in cases_store:
            raise HTTPException(status_code=404, detail=f"Dispute {dispute_id} not found.")
        c_data = cases_store[dispute_id]
        c_data.evaluation = policy_engine.evaluate(
            dispute=c_data.dispute,
            order=c_data.bundle.matched_order,
            shipment=c_data.bundle.matched_shipments[0] if c_data.bundle.matched_shipments else None,
            claims=c_data.claims,
            available_sources=c_data.bundle.to_sources_dict(),
        )
        return {"success": True, "status": "REFRESHED", "dispute_id": dispute_id}

    # ------------------------------------------------------------------------
    # PayPal Sandbox Live Synchronization (Read-Only)
    # ------------------------------------------------------------------------
    @app.post("/api/disputes/sandbox/sync")
    def sync_sandbox(dispute_id: Optional[str] = None):
        """Perform strictly read-only retrieval of a genuine Sandbox dispute and persist to SQLite."""
        res = sync_live_paypal_sandbox_dispute(
            repository=repository,
            audit_logger=audit_logger,
            policy_engine=policy_engine,
            cases_store=cases_store,
            dispute_id=dispute_id,
        )
        return res

    # ------------------------------------------------------------------------
    # Webhook Ingestion with Idempotency Guard
    # ------------------------------------------------------------------------
    @app.post("/api/webhooks/paypal", response_model=WebhookIngestResponse)
    def ingest_paypal_webhook(req: WebhookIngestRequest):
        """Idempotently ingest an incoming PayPal webhook notification."""
        payload = {
            "reason": req.reason,
            "status": req.status,
            "amount": req.amount,
            "currency": req.currency,
        }
        event, is_duplicate = audit_logger.log_dispute_ingestion(
            dispute_id=req.dispute_id,
            actor=req.actor,
            payload=payload,
            idempotency_key=req.idempotency_key,
            record_duplicate_attempt=True,
        )
        msg = (
            "Duplicate webhook delivery observed; existing dispute ingestion preserved."
            if is_duplicate
            else "New dispute ingested and recorded in cryptographic audit ledger."
        )

        if not is_duplicate:
            try:
                new_dispute = DisputeCase(
                    dispute_id=req.dispute_id,
                    reason=req.reason,
                    lifecycle_stage=DisputeLifecycleStage.INQUIRY,
                    status=DisputeStatus.WAITING_FOR_SELLER_RESPONSE,
                    dispute_amount=Money(value=Decimal(req.amount), currency_code=req.currency),
                    seller_response_due_date=datetime.now(timezone.utc) + timedelta(days=10),
                    dispute_create_time=datetime.now(timezone.utc),
                    raw_messages=[{"sender": req.actor, "content": f"Webhook dispute notification for {req.dispute_id}"}],
                )
                new_reconciler = EvidenceReconciler()
                new_bundle = new_reconciler.reconcile_dispute(new_dispute)
                new_eval = policy_engine.evaluate(
                    dispute=new_dispute,
                    order=None,
                    shipment=None,
                    claims=[],
                )
                new_case = CaseData(
                    dispute=new_dispute,
                    bundle=new_bundle,
                    evaluation=new_eval,
                    claims=[],
                    has_prompt_threat=False,
                    dispute_category="LIVE_WEBHOOK",
                )
                cases_store[req.dispute_id] = new_case
                repository.save_full_case(
                    dispute=new_dispute,
                    bundle=new_bundle,
                    evaluation=new_eval,
                    claims=[],
                    dispute_category="LIVE_WEBHOOK",
                )
            except Exception:
                pass

        return WebhookIngestResponse(
            event_id=event.event_id,
            dispute_id=event.dispute_id,
            is_duplicate=is_duplicate,
            event_type=event.event_type.value,
            message=msg,
        )

    # ------------------------------------------------------------------------
    # Audit Trail Viewer & Dispute Lifecycle
    # ------------------------------------------------------------------------
    @app.get("/api/audit-trail")
    def get_audit_trail(dispute_id: Optional[str] = None):
        details = audit_logger.verify_chain_detailed()
        all_events = audit_logger.get_events()
        global_index_map = {ev.event_id: idx + 1 for idx, ev in enumerate(all_events)}

        events = [e for e in all_events if e.dispute_id == dispute_id] if dispute_id else all_events
        verif_map = {ev["event_id"]: ev["is_valid"] for ev in details.get("event_verifications", [])}
        
        enriched_events = []
        for e in events:
            ed = e.model_dump()
            ed["timestamp"] = e.timestamp.isoformat()
            ed["event_type"] = e.event_type.value
            ed["is_verified"] = verif_map.get(e.event_id, details["is_valid"])
            ed["global_chain_index"] = global_index_map.get(e.event_id)
            
            # Contextual outcome result
            result_str = None
            p = e.payload or {}
            ed["approval_id"] = p.get("approval_id")
            ed["correlation_id"] = p.get("correlation_id")
            
            is_sim = (
                bool(p.get("is_simulated"))
                or p.get("dispatch_mode") == "SIMULATED"
                or p.get("correlation_id") == "pp_corr_live_sandbox_99341"
                or "mock" in str(p.get("correlation_id", "")).lower()
                or "sim" in str(p.get("correlation_id", "")).lower()
            )
            ed["is_simulated"] = is_sim if e.event_type in (
                AuditEventType.DISPATCH_ATTEMPTED,
                AuditEventType.DISPATCH_SUCCEEDED,
                AuditEventType.DISPATCH_FAILED,
            ) else False

            if e.event_type == AuditEventType.DISPUTE_INGESTED:
                if p.get("retrieval_mode") or e.actor == "PAYPAL_SANDBOX_API":
                    result_str = "API Sync (Waiting Response)"
                else:
                    st = p.get("status", "")
                    result_str = "Waiting Response" if st == "WAITING_FOR_SELLER_RESPONSE" else (st.replace("_", " ").title() if st else "Ingested")
            elif e.event_type == AuditEventType.DISPUTE_SYNCHRONIZED:
                st = p.get("status", "")
                result_str = "Synchronized" if not st else f"Sync ({st.replace('_', ' ').title()})"
            elif e.event_type == AuditEventType.DUPLICATE_WEBHOOK_RECEIVED:
                result_str = "Duplicate Delivery"
            elif e.event_type == AuditEventType.DUPLICATE_WEBHOOK_IGNORED:
                result_str = "Duplicate Ignored"
            elif e.event_type == AuditEventType.EVIDENCE_RECONCILED:
                conf = p.get("confidence", "")
                result_str = f"Reconciled ({conf.title()})" if conf else "Reconciled"
            elif e.event_type == AuditEventType.POLICY_EVALUATED:
                result_str = p.get("overall_decision", "EVALUATED")
            elif e.event_type == AuditEventType.APPROVAL_REQUESTED:
                appr_id = p.get("approval_id", "")
                result_str = f"Ticket: {appr_id[:12]}" if appr_id else "Ticket Issued"
            elif e.event_type == AuditEventType.APPROVAL_GRANTED:
                result_str = "Approved"
            elif e.event_type == AuditEventType.APPROVAL_REJECTED:
                result_str = "Rejected"
            elif e.event_type == AuditEventType.APPROVAL_EXPIRED:
                result_str = "Ticket Expired"
            elif e.event_type == AuditEventType.APPROVAL_CONSUMED:
                result_str = "Nonce Consumed"
            elif e.event_type == AuditEventType.DISPATCH_ATTEMPTED:
                result_str = "Simulated Attempt" if is_sim else "Attempted"
            elif e.event_type == AuditEventType.DISPATCH_SUCCEEDED:
                sc = p.get("status_code", 200)
                result_str = f"Simulated {sc} OK" if is_sim else f"Live {sc} OK"
            elif e.event_type == AuditEventType.DISPATCH_FAILED:
                result_str = "Simulated Fail" if is_sim else "Failed"
            
            ed["result"] = result_str
            enriched_events.append(ed)

        return {
            "total_events": details["total_events"],
            "verified_count": details["verified_count"],
            "failed_count": details["failed_count"],
            "chain_intact": details["is_valid"],
            "last_verified_at": details["last_verified_at"],
            "verification_details": {
                "status": "VALID" if details["is_valid"] else "COMPROMISED",
                "verified_events": details["verified_count"],
                "failed_event_id": details["failed_event_id"],
                "error_message": details["error_message"],
            },
            "events": enriched_events,
        }

    @app.get("/api/disputes/{dispute_id}/lifecycle")
    def get_dispute_lifecycle(dispute_id: str):
        """Fetch the complete, isolated chronological lifecycle of a dispute directly from canonical SQLite."""
        res = get_audit_trail(dispute_id=dispute_id)
        return {
            "dispute_id": dispute_id,
            "total_events": len(res["events"]),
            "events": res["events"],
        }

    # ------------------------------------------------------------------------
    # Benchmark Evaluation Scorecard
    # ------------------------------------------------------------------------
    @app.get("/api/eval/scorecard")
    def get_eval_scorecard():
        from docket.eval.service import build_enriched_scorecard, execute_and_persist_benchmark
        matrix_path = Path("artifacts/docket_evaluation_matrix.json")
        if not matrix_path.exists():
            return execute_and_persist_benchmark()

        with open(matrix_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return build_enriched_scorecard(data)

    @app.post("/api/eval/run")
    def run_eval_benchmark(
        current_merchant: AuthenticatedMerchant = Depends(get_current_merchant),
    ):
        from docket.eval.service import execute_and_persist_benchmark
        return execute_and_persist_benchmark()

    # ------------------------------------------------------------------------
    # Semantic Extraction & Policy Verification Workflow Endpoint
    # ------------------------------------------------------------------------
    @app.post("/api/ai/extract-workflow")
    def run_semantic_extraction_workflow_endpoint(payload: SemanticWorkflowRequest):
        from docket.ai.workflow import SemanticExtractionWorkflow
        case_data = cases_store.get(payload.dispute_id)
        if not case_data:
            raise HTTPException(status_code=404, detail=f"Dispute case '{payload.dispute_id}' not found.")

        msg_text = payload.message_text
        if not msg_text:
            for msg in case_data.dispute.raw_messages:
                if isinstance(msg, dict):
                    msg_text = msg.get("content", "")
                    break
        if not msg_text:
            msg_text = "I ordered this merchandise but it never arrived. Tracking shows only label created."

        workflow = SemanticExtractionWorkflow(policy_engine=policy_engine)
        result = workflow.run(
            buyer_message=msg_text,
            dispute=case_data.dispute,
            bundle=case_data.bundle,
        )
        return result.model_dump()

    return app


if __name__ == "__main__":
    import uvicorn
    app = create_app()
    uvicorn.run(app, host="127.0.0.1", port=8000)
