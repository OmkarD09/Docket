"""Domain models and data structures for the synthetic evaluation benchmark suite."""

from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, ConfigDict, Field

from docket.models.dispute import DisputeCase
from docket.models.evidence import (
    CustomerMessageRecord,
    ExtractedClaim,
    OrderRecord,
    RefundRecord,
    ShipmentRecord,
)
from docket.models.policy import DecisionType
from docket.models.reconciliation import ReconciliationStatus


class EvalExpectation(BaseModel):
    """Ground-truth expected outcome for an evaluation scenario."""
    model_config = ConfigDict(arbitrary_types_allowed=True)

    expected_reconciliation_status: Optional[ReconciliationStatus] = None
    expected_factual_readiness: Optional[DecisionType] = None
    expected_action_readiness: Optional[DecisionType] = None
    expected_overall_decision: Optional[DecisionType] = None
    expected_violated_invariants: List[str] = Field(default_factory=list)
    expected_discrepancies: List[str] = Field(default_factory=list)
    expected_prompt_threat_detected: Optional[bool] = None
    must_refuse: bool = False  # Critical refusal safety requirement


class EvalScenario(BaseModel):
    """A synthetic or fixture-derived e-commerce dispute evaluation scenario."""
    model_config = ConfigDict(arbitrary_types_allowed=True)

    scenario_id: str
    name: str
    description: str
    dispute: DisputeCase
    orders: List[OrderRecord] = Field(default_factory=list)
    shipments: List[ShipmentRecord] = Field(default_factory=list)
    communications: List[CustomerMessageRecord] = Field(default_factory=list)
    refunds: List[RefundRecord] = Field(default_factory=list)
    proposed_claim: Optional[ExtractedClaim] = None
    expectations: EvalExpectation


class EvalResult(BaseModel):
    """Execution outcome for a single scenario against ground truth."""
    model_config = ConfigDict(arbitrary_types_allowed=True)

    scenario_id: str
    passed: bool
    actual_reconciliation_status: str
    actual_factual_readiness: str
    actual_action_readiness: str
    actual_overall_decision: str
    actual_violated_invariants: List[str] = Field(default_factory=list)
    actual_discrepancies: List[str] = Field(default_factory=list)
    prompt_threat_detected: bool = False
    refusal_correct: bool = True
    failure_reasons: List[str] = Field(default_factory=list)


class EvalScorecard(BaseModel):
    """Aggregated scorecard with empirical precision, recall, and accuracy metrics."""
    model_config = ConfigDict(arbitrary_types_allowed=True)

    total_scenarios: int
    passed_scenarios: int
    failed_scenarios: int
    accuracy_rate: float
    refusal_scenarios_count: int
    refusal_precision: float
    refusal_recall: float
    label_created_refusal_rate: float
    prompt_injection_detection_rate: float
    results: List[EvalResult] = Field(default_factory=list)
    evaluated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    def export_json(self, file_path: str) -> None:
        """Export scorecard metrics and itemized results to JSON artifact."""
        path = Path(file_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.model_dump(mode="json"), f, indent=2)

