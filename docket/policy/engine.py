"""Deterministic Policy Engine and Invariant Rules for Docket.

Core safety and validation layer enforcing:
1. DeliveryProofInvariant: Rejects 'Delivered' assertions when tracking is
   LABEL_CREATED or IN_TRANSIT, while permitting truthful shipment progress claims.
2. AddressMatchInvariant: Compares carrier delivery destination with transaction
   shipping address, distinguishing MISMATCH from INSUFFICIENT_DATA.
3. HATEOASActionInvariant: Validates dispute action eligibility, lifecycle state,
   URL integrity, HTTPS enforcement, and host constraints.
4. SignatureAssessmentInvariant: Contextual advisory distinguishing transactions
   processed before vs. after Jan 26, 2026, over $750 USD or equivalent, without universal hard blocks.
5. CitationIntegrityInvariant: Enforces that claims cite existing, verified sources,
   resolves dotted field paths, and detects factual contradictions.
"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from enum import Enum
import re
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

from docket.models.dispute import DisputeCase, DisputeLifecycleStage, DisputeStatus
from docket.models.evidence import (
    Address,
    ClaimType,
    ExtractedClaim,
    OrderRecord,
    ShipmentRecord,
    SourceType,
    TrackingStatus,
    VerificationStatus,
)
from docket.models.policy import (
    DecisionType,
    OverallPolicyEvaluation,
    PolicyCheckResult,
)


class AddressMatchPolicy(str, Enum):
    """Configuration levels for recipient address matching."""
    DESTINATION_ONLY = "DESTINATION_ONLY"  # Country + postal code
    STANDARD = "STANDARD"                  # Country + postal code + recipient name comparison
    STRICT = "STRICT"                      # Country + postal code + city + strict name comparison


# ============================================================================
# Helper: Dotted Field Path Resolution
# ============================================================================

def resolve_field_path(source: Any, field_path: str) -> tuple[bool, Any]:
    """Traverse a dotted field path across object attributes, dictionaries, or lists.

    Returns (found: bool, value: Any).
    """
    if isinstance(source, str) and field_path in ("text", "content", ""):
        return True, source

    parts = field_path.strip().split(".")
    curr = source
    for part in parts:
        if isinstance(curr, dict):
            if part in curr:
                curr = curr[part]
            else:
                return False, None
        elif isinstance(curr, (list, tuple)):
            if part.isdigit():
                idx = int(part)
                if 0 <= idx < len(curr):
                    curr = curr[idx]
                else:
                    return False, None
            else:
                return False, None
        elif hasattr(curr, part):
            curr = getattr(curr, part)
        else:
            return False, None
    return True, curr


# ============================================================================
# Invariant 1: Delivery Proof Invariant
# ============================================================================

class DeliveryProofInvariant:
    """Validates claims regarding delivery completion vs. shipment progress.

    Docket's defining rule: Rejects asserting 'Delivery Verified' if carrier tracking
    is only 'Label Created' or 'In Transit'. Never confuses shipment in progress
    with completed delivery.
    """

    RULE_ID = "RULE_DELIVERY_PROOF"

    def evaluate(
        self,
        claim: ExtractedClaim,
        shipment: Optional[ShipmentRecord],
        order: Optional[OrderRecord] = None,
    ) -> PolicyCheckResult:
        supporting_refs = [s.source_identifier for s in claim.supporting_sources]

        # Case A: Claim explicitly asserts delivery completed
        if claim.claim_type == ClaimType.DELIVERY_COMPLETED:
            if shipment is None:
                return PolicyCheckResult(
                    decision=DecisionType.BLOCK,
                    rule_identifier=self.RULE_ID,
                    explanation="Cannot assert delivery: No carrier tracking or shipment record was provided.",
                    supporting_source_references=supporting_refs,
                    violated_invariants=["TRACKING_DATA_UNAVAILABLE"],
                    recommended_next_action="Obtain and attach official carrier tracking record before asserting delivery.",
                )

            # Check order correlation
            if order and shipment.internal_order_id != order.order_id:
                return PolicyCheckResult(
                    decision=DecisionType.BLOCK,
                    rule_identifier=self.RULE_ID,
                    explanation=(
                        f"Tracking record #{shipment.tracking_number} is linked to order "
                        f"'{shipment.internal_order_id}', which does not match disputed order '{order.order_id}'."
                    ),
                    supporting_source_references=[shipment.source_identifier],
                    violated_invariants=["TRACKING_ORDER_MISMATCH"],
                    recommended_next_action="Correlate tracking number with the specific disputed order.",
                )

            # Check tracking status: LABEL_CREATED (The defining scenario)
            if shipment.tracking_status == TrackingStatus.LABEL_CREATED:
                return PolicyCheckResult(
                    decision=DecisionType.BLOCK,
                    rule_identifier=self.RULE_ID,
                    explanation=(
                        f"Carrier tracking for {shipment.carrier_name} #{shipment.tracking_number} "
                        "shows status 'Label Created' (awaiting carrier pickup). Physical delivery has not occurred."
                    ),
                    supporting_source_references=[shipment.source_identifier],
                    violated_invariants=["LABEL_CREATED", "DELIVERY_STATUS_LABEL_CREATED"],
                    recommended_next_action=(
                        "Do not assert delivery. Contact carrier to confirm package pickup, "
                        "or report truthful shipment progress to the buyer without claiming delivery."
                    ),
                )

            # Check tracking status: IN_TRANSIT
            if shipment.tracking_status in (TrackingStatus.IN_TRANSIT, TrackingStatus.OUT_FOR_DELIVERY):
                return PolicyCheckResult(
                    decision=DecisionType.BLOCK,
                    rule_identifier=self.RULE_ID,
                    explanation=(
                        f"Carrier tracking shows status '{shipment.tracking_status.value}'; "
                        "package is in transit and delivery is not established."
                    ),
                    supporting_source_references=[shipment.source_identifier],
                    violated_invariants=["IN_TRANSIT", "DELIVERY_STATUS_IN_TRANSIT"],
                    recommended_next_action="Do not claim delivery. Provide tracking link or await final delivery confirmation.",
                )

            # Check tracking status: DELIVERED
            if shipment.tracking_status == TrackingStatus.DELIVERED:
                if not shipment.delivery_timestamp:
                    return PolicyCheckResult(
                        decision=DecisionType.BLOCK,
                        rule_identifier=self.RULE_ID,
                        explanation="Carrier reports delivered status, but exact delivery timestamp is missing from tracking records.",
                        supporting_source_references=[shipment.source_identifier],
                        violated_invariants=["DELIVERY_TIMESTAMP_MISSING"],
                        recommended_next_action="Obtain complete carrier scan history containing official delivery timestamp.",
                    )

                return PolicyCheckResult(
                    decision=DecisionType.ALLOW,
                    rule_identifier=self.RULE_ID,
                    explanation=(
                        f"Verified carrier delivery scan established via {shipment.carrier_name} "
                        f"#{shipment.tracking_number} on {shipment.delivery_timestamp.isoformat()}. "
                        "Confirms carrier completed-delivery tracking status; does not verify street-level recipient delivery."
                    ),
                    supporting_source_references=[shipment.source_identifier],
                    violated_invariants=[],
                    recommended_next_action="Evidence package may proceed with verified carrier tracking scan.",
                )

            # Other invalid statuses (EXCEPTION, RETURNED, UNKNOWN)
            return PolicyCheckResult(
                decision=DecisionType.BLOCK,
                rule_identifier=self.RULE_ID,
                explanation=f"Carrier tracking reports status '{shipment.tracking_status.value}', which does not establish delivery.",
                supporting_source_references=[shipment.source_identifier],
                violated_invariants=["DELIVERY_STATUS_INVALID"],
                recommended_next_action="Inspect carrier exception record and resolve delivery problem.",
            )

        # Case B: Claim truthfully asserts LABEL_CREATED (Shipment label generated)
        elif claim.claim_type == ClaimType.LABEL_CREATED:
            if shipment and shipment.tracking_status == TrackingStatus.LABEL_CREATED:
                return PolicyCheckResult(
                    decision=DecisionType.ALLOW,
                    rule_identifier=self.RULE_ID,
                    explanation=f"Truthful claim: Carrier tracking confirms shipping label was created via {shipment.carrier_name}.",
                    supporting_source_references=[shipment.source_identifier],
                    violated_invariants=[],
                )

        # Case C: Claim truthfully asserts SHIPMENT_IN_PROGRESS
        elif claim.claim_type == ClaimType.SHIPMENT_IN_PROGRESS:
            if shipment and shipment.tracking_status in (TrackingStatus.IN_TRANSIT, TrackingStatus.OUT_FOR_DELIVERY):
                return PolicyCheckResult(
                    decision=DecisionType.ALLOW,
                    rule_identifier=self.RULE_ID,
                    explanation=f"Truthful claim: Carrier tracking confirms package is currently in transit via {shipment.carrier_name}.",
                    supporting_source_references=[shipment.source_identifier],
                    violated_invariants=[],
                )

        # Non-delivery claims pass delivery invariant check
        return PolicyCheckResult(
            decision=DecisionType.ALLOW,
            rule_identifier=self.RULE_ID,
            explanation=f"Claim type '{claim.claim_type.value}' does not assert completed delivery.",
            supporting_source_references=supporting_refs,
            violated_invariants=[],
        )


# ============================================================================
# Invariant 2: Address Match Invariant
# ============================================================================

class AddressMatchInvariant:
    """Verifies recipient delivery address against transaction shipping address.

    Distinguishes MISMATCH from INSUFFICIENT_DATA and supports configurable
    matching depth. Explicitly clarifies destination delivery area correspondence
    without claiming guaranteed Seller Protection eligibility.
    """

    RULE_ID = "RULE_ADDRESS_MATCH"

    def __init__(self, policy: AddressMatchPolicy = AddressMatchPolicy.STANDARD):
        self.policy = policy

    def evaluate(
        self,
        order: Optional[OrderRecord],
        shipment: Optional[ShipmentRecord],
    ) -> PolicyCheckResult:
        if order is None or order.shipping_address is None:
            return PolicyCheckResult(
                decision=DecisionType.REVIEW,
                rule_identifier=self.RULE_ID,
                explanation="Transaction shipping address is missing or unavailable; cannot establish destination match (Insufficient Data).",
                violated_invariants=["TRANSACTION_ADDRESS_MISSING"],
                recommended_next_action="Retrieve transaction shipping address from PayPal order records.",
            )

        if shipment is None or shipment.shipment_address is None:
            return PolicyCheckResult(
                decision=DecisionType.REVIEW,
                rule_identifier=self.RULE_ID,
                explanation="Carrier delivery address is missing or incomplete; destination address cannot be compared (Insufficient Data).",
                violated_invariants=["CARRIER_ADDRESS_MISSING"],
                recommended_next_action="Obtain destination city/postal code from carrier proof of delivery scan.",
            )

        tx_addr = order.shipping_address
        ship_addr = shipment.shipment_address
        refs = [shipment.source_identifier]

        # 1. Country Check
        tx_country = tx_addr.normalized_country()
        ship_country = ship_addr.normalized_country()
        if tx_country and ship_country and tx_country != ship_country:
            return PolicyCheckResult(
                decision=DecisionType.BLOCK,
                rule_identifier=self.RULE_ID,
                explanation=(
                    f"Country mismatch: shipment destination country '{ship_country}' "
                    f"does not match order shipping country '{tx_country}'."
                ),
                supporting_source_references=refs,
                violated_invariants=["ADDRESS_COUNTRY_MISMATCH"],
                recommended_next_action="Verify destination country on carrier tracking record.",
            )

        # 2. Postal Code Check
        tx_zip = tx_addr.normalized_postal_code()
        ship_zip = ship_addr.normalized_postal_code()
        if tx_zip and ship_zip and tx_zip != ship_zip:
            return PolicyCheckResult(
                decision=DecisionType.BLOCK,
                rule_identifier=self.RULE_ID,
                explanation=(
                    f"Postal code mismatch: shipment destination '{ship_zip}' "
                    f"does not match order shipping postal code '{tx_zip}'."
                ),
                supporting_source_references=refs,
                violated_invariants=["ADDRESS_POSTAL_CODE_MISMATCH"],
                recommended_next_action="Confirm carrier delivered to buyer's transaction postal code.",
            )

        # 3. City Check (Required under STRICT policy)
        if self.policy == AddressMatchPolicy.STRICT:
            tx_city = tx_addr.normalized_city()
            ship_city = ship_addr.normalized_city()
            if tx_city and ship_city and tx_city != ship_city:
                return PolicyCheckResult(
                    decision=DecisionType.BLOCK,
                    rule_identifier=self.RULE_ID,
                    explanation=(
                        f"City mismatch under strict policy: shipment city '{ship_addr.city}' "
                        f"does not match order shipping city '{tx_addr.city}'."
                    ),
                    supporting_source_references=refs,
                    violated_invariants=["ADDRESS_CITY_MISMATCH"],
                    recommended_next_action="Verify delivery city matches transaction shipping address.",
                )

        # 4. Recipient Name Check (Where available in both records)
        tx_name = tx_addr.normalized_recipient_name()
        ship_name = ship_addr.normalized_recipient_name()
        if tx_name and ship_name and tx_name != ship_name:
            if self.policy == AddressMatchPolicy.STRICT:
                return PolicyCheckResult(
                    decision=DecisionType.BLOCK,
                    rule_identifier=self.RULE_ID,
                    explanation=(
                        f"Recipient name mismatch under strict policy: shipment recipient '{ship_addr.recipient_name}' "
                        f"does not match order recipient '{tx_addr.recipient_name}'."
                    ),
                    supporting_source_references=refs,
                    violated_invariants=["ADDRESS_RECIPIENT_NAME_MISMATCH"],
                    recommended_next_action="Confirm package was addressed to the buyer specified on PayPal transaction.",
                )
            elif self.policy == AddressMatchPolicy.STANDARD:
                return PolicyCheckResult(
                    decision=DecisionType.REVIEW,
                    rule_identifier=self.RULE_ID,
                    explanation=(
                        f"Recipient name differs between order ('{tx_addr.recipient_name}') and "
                        f"carrier delivery record ('{ship_addr.recipient_name}'). Review for gift recipient or alias."
                    ),
                    supporting_source_references=refs,
                    violated_invariants=["ADDRESS_RECIPIENT_NAME_DIFFERS"],
                    recommended_next_action="Review buyer communications to confirm alternative recipient name.",
                )

        # Successful match with explicit Seller Protection disclaimer
        return PolicyCheckResult(
            decision=DecisionType.ALLOW,
            rule_identifier=self.RULE_ID,
            explanation=(
                "Shipment destination corresponds to buyer transaction delivery area (postal code and country verified). "
                "Disclaimer: This verifies destination delivery area correspondence only and does not verify street-level delivery "
                "or does not guarantee seller protection (including PayPal Seller Protection eligibility)."
            ),
            supporting_source_references=refs,
            violated_invariants=[],
            recommended_next_action="Address match requirement satisfied.",
        )


# ============================================================================
# Invariant 3: HATEOAS Action Invariant
# ============================================================================

class HATEOASActionInvariant:
    """Validates dispute action eligibility, lifecycle state, URL integrity,
    HTTPS enforcement, host constraints, and evidence requirements.
    """

    RULE_ID = "RULE_HATEOAS_ACTION"
    DEFAULT_ALLOWED_HOSTS = (
        "api-m.sandbox.paypal.com",
        "api-m.paypal.com",
        "api.sandbox.paypal.com",
        "api.paypal.com",
    )

    def __init__(
        self,
        target_action: str = "provide_evidence",
        target_evidence_type: Optional[str] = None,
        allow_insecure_http: bool = False,
        allowed_hosts: Optional[List[str]] = None,
    ):
        self.target_action = target_action.strip().lower().replace("-", "_")
        self.target_evidence_type = target_evidence_type
        self.allow_insecure_http = allow_insecure_http
        self.allowed_hosts = [h.lower() for h in (allowed_hosts or self.DEFAULT_ALLOWED_HOSTS)]

    def evaluate(self, dispute: DisputeCase) -> PolicyCheckResult:
        # 1. Closed or resolved dispute check
        if dispute.status == DisputeStatus.RESOLVED:
            return PolicyCheckResult(
                decision=DecisionType.BLOCK,
                rule_identifier=self.RULE_ID,
                explanation=f"Dispute {dispute.dispute_id} is in status 'RESOLVED'. Consequential actions are not permitted.",
                violated_invariants=["DISPUTE_STATE_NOT_ACTIONABLE"],
                recommended_next_action="No action permitted on closed or resolved disputes.",
            )

        # 2. Lifecycle Stage & Status Permissions
        if self.target_action == "provide_evidence":
            # Inquiry + Open: Buyer and seller are in communication; evidence submission is ineligible
            if dispute.lifecycle_stage == DisputeLifecycleStage.INQUIRY and dispute.status == DisputeStatus.OPEN:
                return PolicyCheckResult(
                    decision=DecisionType.BLOCK,
                    rule_identifier=self.RULE_ID,
                    explanation=(
                        f"Dispute {dispute.dispute_id} is in initial Inquiry phase (INQUIRY + OPEN). "
                        "The seller evidence response window is not open; provide-evidence is ineligible."
                    ),
                    violated_invariants=["DISPUTE_INQUIRY_OPEN_SELLER_INELIGIBLE"],
                    recommended_next_action="Communicate with buyer using 'send_message' or make a settlement offer.",
                )

            # Ineligible status states (waiting for buyer response or under review)
            if dispute.status in (DisputeStatus.WAITING_FOR_BUYER_RESPONSE, DisputeStatus.UNDER_REVIEW):
                return PolicyCheckResult(
                    decision=DecisionType.BLOCK,
                    rule_identifier=self.RULE_ID,
                    explanation=(
                        f"Dispute {dispute.dispute_id} is currently in status '{dispute.status.value}'. "
                        "Merchant evidence submission is not permitted in this state."
                    ),
                    violated_invariants=["DISPUTE_STATUS_SELLER_INELIGIBLE"],
                    recommended_next_action="Await buyer response or PayPal dispute resolution review.",
                )

        # 3. Action Link Presence Check
        link = dispute.get_action_link(self.target_action)
        if not link:
            return PolicyCheckResult(
                decision=DecisionType.BLOCK,
                rule_identifier=self.RULE_ID,
                explanation=f"Action '{self.target_action}' is absent from dispute HATEOAS links array.",
                violated_invariants=["HATEOAS_ACTION_ABSENT"],
                recommended_next_action="Verify dispute lifecycle stage allows this operation in the PayPal Resolution Center.",
            )

        # 4. URL Scheme & Host Security Validation
        parsed = urlparse(link.href)
        if parsed.scheme == "http" and not self.allow_insecure_http:
            return PolicyCheckResult(
                decision=DecisionType.BLOCK,
                rule_identifier=self.RULE_ID,
                explanation=f"Insecure HTTP URL scheme '{link.href}' is not permitted; HTTPS required.",
                violated_invariants=["HATEOAS_INSECURE_URL"],
                recommended_next_action="Ensure PayPal API endpoints use secure HTTPS protocol.",
            )

        if parsed.scheme not in ("http", "https") or not parsed.netloc:
            return PolicyCheckResult(
                decision=DecisionType.BLOCK,
                rule_identifier=self.RULE_ID,
                explanation=f"Invalid HATEOAS action URL: '{link.href}'.",
                violated_invariants=["HATEOAS_LINK_INVALID_URL"],
                recommended_next_action="Refresh dispute details to retrieve valid HATEOAS links.",
            )

        hostname = (parsed.hostname or "").lower()
        if hostname not in self.allowed_hosts:
            return PolicyCheckResult(
                decision=DecisionType.BLOCK,
                rule_identifier=self.RULE_ID,
                explanation=(
                    f"Action link destination host '{parsed.netloc}' is not an authorized PayPal API endpoint "
                    f"(Allowed hosts: {', '.join(self.allowed_hosts)})."
                ),
                violated_invariants=["HATEOAS_UNAUTHORIZED_HOST"],
                recommended_next_action="Reject untrusted action endpoints not hosted on official PayPal infrastructure.",
            )

        # 5. Exact Dispute ID Path Validation (Not substring match)
        path_segments = [seg for seg in parsed.path.split("/") if seg]
        if dispute.dispute_id not in path_segments:
            return PolicyCheckResult(
                decision=DecisionType.BLOCK,
                rule_identifier=self.RULE_ID,
                explanation=(
                    f"HATEOAS link path '{parsed.path}' does not contain exact dispute ID '{dispute.dispute_id}' "
                    "(Stale or cross-case action link)."
                ),
                violated_invariants=["HATEOAS_LINK_DISPUTE_MISMATCH"],
                recommended_next_action="Refresh case details to ensure current dispute tokens and links.",
            )

        # 6. Evidence Type Matching (If evidence submission is targeted and requirements exist)
        if self.target_action == "provide_evidence" and self.target_evidence_type:
            if dispute.requested_evidence_types and self.target_evidence_type not in dispute.requested_evidence_types:
                return PolicyCheckResult(
                    decision=DecisionType.REVIEW,
                    rule_identifier=self.RULE_ID,
                    explanation=(
                        f"Target evidence type '{self.target_evidence_type}' was not explicitly requested by PayPal "
                        f"(Requested evidence types: {', '.join(dispute.requested_evidence_types)})."
                    ),
                    supporting_source_references=[link.href],
                    violated_invariants=["EVIDENCE_TYPE_NOT_REQUESTED"],
                    recommended_next_action="Align evidence submission type with PayPal requested requirements.",
                )

        return PolicyCheckResult(
            decision=DecisionType.ALLOW,
            rule_identifier=self.RULE_ID,
            explanation=f"Dispute is actionable and action '{self.target_action}' is available via verified HATEOAS link.",
            supporting_source_references=[link.href],
            violated_invariants=[],
            recommended_next_action=f"Operation '{self.target_action}' is eligible for execution.",
        )


# ============================================================================
# Invariant 4: Signature Requirement Assessment
# ============================================================================

class SignatureAssessmentInvariant:
    """Contextual advisory for signature confirmation requirements.

    Never implements a universal hard block. Evaluates transactions OVER $750 USD
    (or currency equivalent), distinguishing pre-Jan 26, 2026 transactions from
    later transactions where signature confirmation is recommended but not
    universally mandatory.
    """

    RULE_ID = "RULE_SIGNATURE_ASSESSMENT"
    CUTOFF_DATE = datetime(2026, 1, 26, 0, 0, 0, tzinfo=timezone.utc)

    # Official standard PayPal high-value thresholds by currency:
    CURRENCY_THRESHOLDS: Dict[str, Decimal] = {
        "USD": Decimal("750.00"),
        "EUR": Decimal("550.00"),
        "GBP": Decimal("450.00"),
        "CAD": Decimal("850.00"),
        "AUD": Decimal("850.00"),
        "JPY": Decimal("100000.00"),
        "NZD": Decimal("950.00"),
        "CHF": Decimal("700.00"),
        "HKD": Decimal("6000.00"),
        "SGD": Decimal("1000.00"),
        "SEK": Decimal("6000.00"),
        "DKK": Decimal("4500.00"),
        "PLN": Decimal("2300.00"),
        "NOK": Decimal("5500.00"),
        "HUF": Decimal("170000.00"),
        "CZK": Decimal("15000.00"),
        "ILS": Decimal("2700.00"),
        "MXN": Decimal("10000.00"),
        "BRL": Decimal("1750.00"),
        "TWD": Decimal("23000.00"),
        "THB": Decimal("24500.00"),
        "INR": Decimal("60000.00"),
    }

    def __init__(
        self,
        merchant_jurisdiction: str = "US",
        goods_type: str = "PHYSICAL_GOODS",
    ):
        self.merchant_jurisdiction = merchant_jurisdiction.strip().upper()
        self.goods_type = goods_type.strip().upper()

    def evaluate(
        self,
        order: Optional[OrderRecord],
        shipment: Optional[ShipmentRecord],
    ) -> PolicyCheckResult:
        # Physical goods only: Digital goods or services do not require delivery signature
        if self.goods_type != "PHYSICAL_GOODS":
            return PolicyCheckResult(
                decision=DecisionType.ALLOW,
                rule_identifier=self.RULE_ID,
                explanation=f"Signature confirmation only applies to physical goods shipments (Goods type: '{self.goods_type}').",
                is_advisory=True,
                violated_invariants=[],
            )

        if order is None or order.gross_amount is None:
            return PolicyCheckResult(
                decision=DecisionType.REVIEW,
                rule_identifier=self.RULE_ID,
                explanation="Transaction amount is missing; signature requirement cannot be assessed.",
                violated_invariants=["SIGNATURE_DATE_INDETERMINATE"],
                is_advisory=True,
                recommended_next_action="Provide transaction amount to assess signature threshold.",
            )

        curr = order.gross_amount.currency_code
        threshold = self.CURRENCY_THRESHOLDS.get(curr)

        if threshold is None:
            return PolicyCheckResult(
                decision=DecisionType.REVIEW,
                rule_identifier=self.RULE_ID,
                explanation=f"Currency '{curr}' does not have a configured signature threshold; requirement is indeterminate.",
                violated_invariants=["SIGNATURE_CURRENCY_INDETERMINATE"],
                is_advisory=True,
                recommended_next_action="Verify local PayPal Seller Protection high-value threshold for currency.",
            )

        # STRICT BOUNDARY: Guidance specifies OVER $750 USD (or equivalent).
        # $749.99 and $750.00 are NOT over the threshold; $750.01 IS over.
        if order.gross_amount.value <= threshold:
            return PolicyCheckResult(
                decision=DecisionType.ALLOW,
                rule_identifier=self.RULE_ID,
                explanation=(
                    f"Transaction amount ({order.gross_amount.value} {curr}) is not over the "
                    f"high-value threshold ({threshold} {curr}); signature confirmation is not required."
                ),
                is_advisory=True,
                violated_invariants=[],
            )

        # Transaction is strictly OVER the threshold
        if shipment and shipment.recipient_signature_present is True:
            return PolicyCheckResult(
                decision=DecisionType.ALLOW,
                rule_identifier=self.RULE_ID,
                explanation=f"Recipient signature confirmation verified on delivery record for high-value transaction (>{threshold} {curr}).",
                supporting_source_references=[shipment.source_identifier],
                is_advisory=True,
                violated_invariants=[],
            )

        # Missing transaction date
        if order.order_timestamp is None:
            return PolicyCheckResult(
                decision=DecisionType.REVIEW,
                rule_identifier=self.RULE_ID,
                explanation=(
                    f"High-value transaction ({order.gross_amount.value} {curr}) "
                    "lacks an order timestamp; signature confirmation policy cannot be conclusively determined."
                ),
                violated_invariants=["SIGNATURE_DATE_INDETERMINATE"],
                is_advisory=True,
                recommended_next_action="Review transaction timestamp against Seller Protection cutoff guidelines.",
            )

        # Pre-Jan 26, 2026: Traditional requirement (Seller Protection deficiency)
        if order.order_timestamp < self.CUTOFF_DATE:
            return PolicyCheckResult(
                decision=DecisionType.REVIEW,  # Advisory REVIEW, NEVER BLOCK
                rule_identifier=self.RULE_ID,
                explanation=(
                    f"Seller Protection deficiency: For transactions processed before Jan 26, 2026 exceeding {threshold} {curr}, "
                    "signature confirmation was required for full Seller Protection against Item Not Received claims. "
                    "Evidence submission is permitted, but Seller Protection may not apply."
                ),
                violated_invariants=["SIGNATURE_SELLER_PROTECTION_DEFICIENCY", "SIGNATURE_RECOMMENDED_PRE_2026"],
                is_advisory=True,
                recommended_next_action="Obtain recipient signature confirmation from carrier if contesting under Seller Protection.",
            )

        # Post-Jan 26, 2026: Updated guidance (recommended, but not universally mandatory)
        return PolicyCheckResult(
            decision=DecisionType.REVIEW,  # Advisory REVIEW, NEVER BLOCK
            rule_identifier=self.RULE_ID,
            explanation=(
                f"Advisory: Under updated PayPal guidance effective Jan 26, 2026, signature confirmation is recommended "
                f"for high-value transactions (>{threshold} {curr}) but is not universally mandatory. Submission is permitted."
            ),
            violated_invariants=["SIGNATURE_ADVISORY_POST_2026"],
            is_advisory=True,
            recommended_next_action="Submit carrier tracking proof; signature confirmation is recommended if available.",
        )


# ============================================================================
# Invariant 5: Citation Integrity Invariant
# ============================================================================

class CitationIntegrityInvariant:
    """Verifies that every extracted claim references verified, existing source records,
    validates dotted field paths, and detects factual contradictions.
    """

    RULE_ID = "RULE_CITATION_INTEGRITY"

    def evaluate(
        self,
        claim: ExtractedClaim,
        available_sources: Dict[str, Any],
    ) -> PolicyCheckResult:
        if not claim.supporting_sources:
            return PolicyCheckResult(
                decision=DecisionType.BLOCK,
                rule_identifier=self.RULE_ID,
                explanation=f"Claim '{claim.claim_id}' has no supporting source citations (Unsupported Claim).",
                violated_invariants=["CLAIM_WITHOUT_CITATIONS"],
                recommended_next_action="Link claim to an official order, tracking, or document source.",
            )

        refs: List[str] = []
        for citation in claim.supporting_sources:
            refs.append(citation.source_identifier)
            if citation.source_identifier not in available_sources:
                return PolicyCheckResult(
                    decision=DecisionType.BLOCK,
                    rule_identifier=self.RULE_ID,
                    explanation=(
                        f"Claim '{claim.claim_id}' references unknown or unavailable source "
                        f"'{citation.source_identifier}'."
                    ),
                    supporting_source_references=refs,
                    violated_invariants=["CITATION_SOURCE_NONEXISTENT"],
                    recommended_next_action="Verify source record ingestion before submitting claims.",
                )

            # Check verification status of the source citation
            if citation.verification_status == VerificationStatus.REJECTED:
                return PolicyCheckResult(
                    decision=DecisionType.BLOCK,
                    rule_identifier=self.RULE_ID,
                    explanation=f"Citation source '{citation.source_identifier}' is marked as REJECTED.",
                    supporting_source_references=refs,
                    violated_invariants=["CITATION_SOURCE_REJECTED"],
                    recommended_next_action="Remove claims derived from rejected evidence sources.",
                )

            if citation.verification_status == VerificationStatus.UNVERIFIED:
                return PolicyCheckResult(
                    decision=DecisionType.REVIEW,
                    rule_identifier=self.RULE_ID,
                    explanation=f"Citation source '{citation.source_identifier}' is UNVERIFIED.",
                    supporting_source_references=refs,
                    violated_invariants=["CITATION_SOURCE_UNVERIFIED"],
                    recommended_next_action="Authenticate source record with official merchant or carrier channels.",
                )

            if citation.verification_status == VerificationStatus.CONFLICTING:
                return PolicyCheckResult(
                    decision=DecisionType.REVIEW,
                    rule_identifier=self.RULE_ID,
                    explanation=f"Citation source '{citation.source_identifier}' is marked as CONFLICTING.",
                    supporting_source_references=refs,
                    violated_invariants=["CITATION_SOURCE_CONFLICTING"],
                    recommended_next_action="Resolve contradictory evidence between merchant records and customer claims.",
                )

            # Dotted Field Path Resolution & Factual Value Reconciliation
            source_obj = available_sources[citation.source_identifier]
            found, actual_val = resolve_field_path(source_obj, citation.field_path)

            if not found:
                return PolicyCheckResult(
                    decision=DecisionType.BLOCK,
                    rule_identifier=self.RULE_ID,
                    explanation=(
                        f"Source '{citation.source_identifier}' does not contain cited field path '{citation.field_path}'."
                    ),
                    supporting_source_references=refs,
                    violated_invariants=["CITATION_FIELD_PATH_NONEXISTENT"],
                    recommended_next_action="Ensure citation field path points to a valid attribute on the source record.",
                )

            # Reconcile cited value vs actual value in source
            actual_str = str(actual_val.value if hasattr(actual_val, "value") else actual_val).strip()
            cited_str = str(citation.extracted_value).strip()

            values_match = False
            if isinstance(actual_val, datetime):
                try:
                    cited_dt = datetime.fromisoformat(cited_str.replace("Z", "+00:00"))
                    # If actual_val is timezone-aware and cited_dt is timezone-aware
                    if cited_dt.tzinfo is None and actual_val.tzinfo is not None:
                        cited_dt = cited_dt.replace(tzinfo=actual_val.tzinfo)
                    values_match = (cited_dt == actual_val)
                except Exception:
                    values_match = (actual_str.lower() == cited_str.lower())
            elif isinstance(actual_val, Decimal):
                try:
                    cited_dec = Decimal(cited_str)
                    values_match = (cited_dec == actual_val)
                except Exception:
                    values_match = (actual_str.lower() == cited_str.lower())
            else:
                # String comparison: exact match or excerpt containment within text field
                values_match = (
                    actual_str.lower() == cited_str.lower()
                    or cited_str.lower() in actual_str.lower()
                    or actual_str.lower() in cited_str.lower()
                )

            if not values_match:
                return PolicyCheckResult(
                    decision=DecisionType.BLOCK,
                    rule_identifier=self.RULE_ID,
                    explanation=(
                        f"Citation value contradiction: Citation claims '{citation.extracted_value}' at "
                        f"'{citation.field_path}', but source '{citation.source_identifier}' contains '{actual_str}' "
                        "(Factual Contradiction)."
                    ),
                    supporting_source_references=refs,
                    violated_invariants=["CITATION_VALUE_MISMATCH"],
                    recommended_next_action="Reconcile claim assertion with the actual underlying source document.",
                )

        return PolicyCheckResult(
            decision=DecisionType.ALLOW,
            rule_identifier=self.RULE_ID,
            explanation=f"Claim '{claim.claim_id}' citations verified against active source records.",
            supporting_source_references=refs,
            violated_invariants=[],
        )


# ============================================================================
# Invariant 6: Delivery Discrepancy Invariant
# ============================================================================

class DeliveryDiscrepancyInvariant:
    """Evaluates factual discrepancies between buyer communications and carrier tracking.

    Epistemic & Policy Boundaries:
    - Case A: Carrier says DELIVERED, destination matches, buyer disputes receipt.
      -> ALLOW (with standard destination area correspondence disclaimer). Contradiction flags INR.
    - Case B: Carrier says DELIVERED, but destination address cannot be verified.
      -> REVIEW (via AddressMatchInvariant CARRIER_ADDRESS_MISSING).
    - Case C: Carrier tracking records independently confirm delivery exception or misdelivery.
      -> BLOCK (CARRIER_CONFIRMED_MISDELIVERY).
    - Case D: Buyer merely reports that the courier verbally mentioned misdelivery, with no
      independent carrier record.
      -> REVIEW (HEARSAY_MISDELIVERY_ALLEGATION). Docket does not treat a delivery scan as
      infallible conclusive proof of delivery, but does not hard-BLOCK on unverified buyer hearsay.
    - Case E: Carrier tracking reports LABEL_CREATED or IN_TRANSIT.
      -> BLOCK (via DeliveryProofInvariant).
    """

    RULE_ID = "RULE_DELIVERY_DISCREPANCY"

    def evaluate(
        self,
        claims: Optional[List[ExtractedClaim]],
        shipment: Optional[ShipmentRecord],
        available_sources: Optional[Dict[str, Any]] = None,
    ) -> PolicyCheckResult:
        if not shipment:
            return PolicyCheckResult(
                decision=DecisionType.ALLOW,
                rule_identifier=self.RULE_ID,
                explanation="No carrier tracking record to evaluate for discrepancy.",
                violated_invariants=[],
            )

        sources = available_sources or {}

        # 1. Check Case C: Independently recorded carrier source confirms misdelivery/exception
        for src_id, src_obj in sources.items():
            if isinstance(src_obj, ShipmentRecord):
                if src_obj.tracking_status in (TrackingStatus.EXCEPTION, TrackingStatus.RETURNED):
                    return PolicyCheckResult(
                        decision=DecisionType.BLOCK,
                        rule_identifier=self.RULE_ID,
                        explanation=(
                            f"Official carrier tracking record ({src_obj.carrier_name} #{src_obj.tracking_number}) "
                            f"confirms delivery exception/misdelivery status '{src_obj.tracking_status.value}'. "
                            "Proof of delivery to recipient cannot be asserted."
                        ),
                        violated_invariants=["CARRIER_CONFIRMED_MISDELIVERY"],
                        recommended_next_action="Review carrier exception record; issue refund or reship item.",
                    )

        # 2. Check Case D: Buyer reports courier verbally mentioned misdelivery (hearsay)
        # without independent carrier record confirmation
        if claims and shipment.tracking_status == TrackingStatus.DELIVERED:
            for claim in claims:
                assertion_lower = claim.factual_assertion.lower()
                courier_keywords = ["courier", "carrier", "driver", "delivery agent", "postman", "postal worker"]
                misdelivery_keywords = [
                    "another address", "different address", "wrong address",
                    "wrong house", "misdelivered", "left elsewhere", "delivered elsewhere",
                ]

                has_courier = any(kw in assertion_lower for kw in courier_keywords)
                has_misdelivery = any(kw in assertion_lower for kw in misdelivery_keywords)

                if has_courier and has_misdelivery:
                    # Check supporting source is customer communication
                    is_buyer_comm = any(
                        s.source_type == SourceType.CUSTOMER_COMMUNICATION for s in claim.supporting_sources
                    ) or any(s.source_identifier.startswith("MSG-") for s in claim.supporting_sources)
                    if is_buyer_comm:
                        return PolicyCheckResult(
                            decision=DecisionType.REVIEW,
                            rule_identifier=self.RULE_ID,
                            explanation=(
                                "Factual discrepancy (Case D): Buyer reports that the courier verbally stated "
                                "the package may have been left at another address. Carrier tracking indicates DELIVERED. "
                                "Independent carrier proof of misdelivery is not established (buyer hearsay), but Docket "
                                "does not treat a delivery scan as conclusive proof of delivery. Merchant review is "
                                "required to verify carrier GPS delivery coordinates before submitting evidence."
                            ),
                            supporting_source_references=[s.source_identifier for s in claim.supporting_sources],
                            violated_invariants=["HEARSAY_MISDELIVERY_ALLEGATION"],
                            recommended_next_action="Contact carrier to request GPS delivery scan coordinates and delivery confirmation before submitting rebuttal.",
                        )

        # 3. Case A: Standard dispute of receipt without misdelivery allegation
        return PolicyCheckResult(
            decision=DecisionType.ALLOW,
            rule_identifier=self.RULE_ID,
            explanation=(
                "Case A: Verified carrier delivery scan corresponds to transaction delivery area (postal code and country verified). "
                "Scope: Confirms carrier tracking status and destination delivery area correspondence only. "
                "Does NOT establish street-level recipient delivery confirmation or guarantee PayPal Seller Protection eligibility or dispute outcome."
            ),
            violated_invariants=[],
            recommended_next_action="Evidence package satisfies destination area delivery check. Final rebuttal submission requires affirmative merchant authorization.",
        )


# ============================================================================
# Central Policy Engine
# ============================================================================

class PolicyEngine:
    """Central deterministic policy validation coordinator for Docket.

    Executes all applicable independent invariants, separates factual evidence validity
    from PayPal action eligibility, isolates non-blocking advisories, and calculates
    comprehensive overall decisions.
    """

    def __init__(
        self,
        address_policy: AddressMatchPolicy = AddressMatchPolicy.STANDARD,
        merchant_jurisdiction: str = "US",
        goods_type: str = "PHYSICAL_GOODS",
        allow_insecure_http: bool = False,
    ):
        self.delivery_invariant = DeliveryProofInvariant()
        self.delivery_discrepancy_invariant = DeliveryDiscrepancyInvariant()
        self.address_invariant = AddressMatchInvariant(policy=address_policy)
        self.signature_invariant = SignatureAssessmentInvariant(
            merchant_jurisdiction=merchant_jurisdiction,
            goods_type=goods_type,
        )
        self.citation_invariant = CitationIntegrityInvariant()
        self.allow_insecure_http = allow_insecure_http

    def evaluate(
        self,
        dispute: DisputeCase,
        order: Optional[OrderRecord] = None,
        shipment: Optional[ShipmentRecord] = None,
        claims: Optional[List[ExtractedClaim]] = None,
        claim: Optional[ExtractedClaim] = None,
        target_action: str = "provide_evidence",
        target_evidence_type: Optional[str] = None,
        available_sources: Optional[Dict[str, Any]] = None,
    ) -> OverallPolicyEvaluation:
        # Convenience handling for single claim argument
        if claim is not None:
            if claims is None:
                claims = [claim]
            elif claim not in claims:
                claims.append(claim)

        factual_results: List[PolicyCheckResult] = []
        action_results: List[PolicyCheckResult] = []
        advisories: List[PolicyCheckResult] = []

        # Populate default available sources if not explicitly supplied
        sources = dict(available_sources or {})
        if shipment:
            sources[shipment.source_identifier] = shipment
            sources[shipment.tracking_number] = shipment
        if order:
            sources[order.order_id] = order
            if order.paypal_transaction_id:
                sources[order.paypal_transaction_id] = order
        sources[dispute.dispute_id] = dispute

        # --------------------------------------------------------------------
        # 1. Action Eligibility Dimension (HATEOAS & Dispute Lifecycle)
        # --------------------------------------------------------------------
        hateoas_invariant = HATEOASActionInvariant(
            target_action=target_action,
            target_evidence_type=target_evidence_type,
            allow_insecure_http=self.allow_insecure_http,
        )
        action_results.append(hateoas_invariant.evaluate(dispute))

        # --------------------------------------------------------------------
        # 2. Factual Evidence Dimension (Address & Claim Verifications)
        # --------------------------------------------------------------------
        if (order or shipment) and self.signature_invariant.goods_type != "INTANGIBLE":
            factual_results.append(self.address_invariant.evaluate(order, shipment))

        if claims:
            for claim in claims:
                factual_results.append(self.delivery_invariant.evaluate(claim, shipment, order))
                factual_results.append(self.citation_invariant.evaluate(claim, sources))

        if shipment or claims:
            factual_results.append(self.delivery_discrepancy_invariant.evaluate(claims, shipment, sources))

        # --------------------------------------------------------------------
        # 3. Advisory Dimension (Signature & Seller Protection Considerations)
        # --------------------------------------------------------------------
        if order or shipment:
            sig_res = self.signature_invariant.evaluate(order, shipment)
            advisories.append(sig_res)

        # --------------------------------------------------------------------
        # 4. Dimensional Aggregation
        # --------------------------------------------------------------------
        has_factual_block = any(r.decision == DecisionType.BLOCK for r in factual_results)
        has_factual_review = any(r.decision == DecisionType.REVIEW for r in factual_results)
        factual_readiness = (
            DecisionType.BLOCK if has_factual_block
            else DecisionType.REVIEW if has_factual_review
            else DecisionType.ALLOW
        )

        has_action_block = any(r.decision == DecisionType.BLOCK for r in action_results)
        has_action_review = any(r.decision == DecisionType.REVIEW for r in action_results)
        action_readiness = (
            DecisionType.BLOCK if has_action_block
            else DecisionType.REVIEW if has_action_review
            else DecisionType.ALLOW
        )

        has_advisory_review = any(a.decision == DecisionType.REVIEW for a in advisories)

        # Composite overall decision
        if factual_readiness == DecisionType.BLOCK or action_readiness == DecisionType.BLOCK:
            overall_decision = DecisionType.BLOCK
            summary = "Policy checks failed. One or more mandatory invariants were violated."
        elif factual_readiness == DecisionType.REVIEW or action_readiness == DecisionType.REVIEW or has_advisory_review:
            overall_decision = DecisionType.REVIEW
            summary = "Policy checks require merchant review or additional evidence before proceeding."
        else:
            overall_decision = DecisionType.ALLOW
            summary = "All deterministic policy invariants passed. Claims are supported by evidence."

        all_check_results = action_results + factual_results

        return OverallPolicyEvaluation(
            dispute_id=dispute.dispute_id,
            overall_decision=overall_decision,
            factual_readiness=factual_readiness,
            action_readiness=action_readiness,
            check_results=all_check_results,
            advisories=advisories,
            summary=summary,
            evaluated_at=datetime.now(timezone.utc),
        )
