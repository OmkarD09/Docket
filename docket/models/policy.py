"""Policy evaluation results and decision models for Docket."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import List, Optional
from pydantic import BaseModel, ConfigDict, Field


class DecisionType(str, Enum):
    """Deterministic validation outcomes for claims and dispute actions."""
    ALLOW = "ALLOW"
    REVIEW = "REVIEW"
    BLOCK = "BLOCK"


class PolicyCheckResult(BaseModel):
    """Outcome of an individual deterministic invariant evaluation."""
    model_config = ConfigDict(arbitrary_types_allowed=True)

    decision: DecisionType
    rule_identifier: str
    explanation: str
    supporting_source_references: List[str] = Field(default_factory=list)
    violated_invariants: List[str] = Field(default_factory=list)
    recommended_next_action: Optional[str] = None
    is_advisory: bool = False


class OverallPolicyEvaluation(BaseModel):
    """Aggregated policy assessment distinguishing factual proof from action eligibility."""
    model_config = ConfigDict(arbitrary_types_allowed=True)

    dispute_id: str
    overall_decision: DecisionType
    factual_readiness: DecisionType = DecisionType.ALLOW
    action_readiness: DecisionType = DecisionType.ALLOW
    check_results: List[PolicyCheckResult] = Field(default_factory=list)
    advisories: List[PolicyCheckResult] = Field(default_factory=list)
    summary: str
    evaluated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    def has_blocking_violations(self) -> bool:
        """Returns True if any check produced a hard BLOCK."""
        return self.overall_decision == DecisionType.BLOCK

    def get_violations(self) -> List[str]:
        """Aggregate all violated invariant codes across all check results."""
        violations: List[str] = []
        for check in self.check_results:
            violations.extend(check.violated_invariants)
        for adv in self.advisories:
            violations.extend(adv.violated_invariants)
        return violations

    def is_factually_supported(self) -> bool:
        """Returns True if factual claims are verified and uncontradicted."""
        return self.factual_readiness == DecisionType.ALLOW

    def is_action_eligible(self) -> bool:
        """Returns True if the PayPal dispute state permits executing the requested action."""
        return self.action_readiness == DecisionType.ALLOW

    def has_advisories(self) -> bool:
        """Returns True if any non-blocking advisories exist."""
        return len(self.advisories) > 0

    def is_ready_for_submission(self) -> bool:
        """Returns True if both factual proof and action eligibility are ALLOW."""
        return self.overall_decision == DecisionType.ALLOW
