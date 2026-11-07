"""Automated benchmark runner and empirical metric calculator for Docket (Milestone 5)."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Dict, List, Optional

from docket.ai.base import BaseFactExtractor
from docket.ai.contradiction import ContradictionDetector
from docket.ai.deterministic import DeterministicFactExtractor
from docket.ai.prompt_guard import PromptInjectionGuard
from docket.eval.models import (
    EvalExpectation,
    EvalResult,
    EvalScenario,
    EvalScorecard,
)
from docket.eval.scenarios import load_all_scenarios
from docket.models.evidence import ExtractedClaim
from docket.policy.engine import PolicyEngine
from docket.reconciliation.engine import EvidenceReconciler


class BenchmarkRunner:
    """Executes evaluation scenarios through the complete Docket pipeline and scores results."""

    def __init__(
        self,
        scenarios: Optional[List[EvalScenario]] = None,
        fact_extractor: Optional[BaseFactExtractor] = None,
    ) -> None:
        self.scenarios = scenarios or load_all_scenarios()
        self._scenario_by_id: Dict[str, EvalScenario] = {s.scenario_id: s for s in self.scenarios}
        self.guard = PromptInjectionGuard()
        self.fact_extractor = fact_extractor or DeterministicFactExtractor()
        self.contradiction_detector = ContradictionDetector()

    def run_all(self) -> EvalScorecard:
        """Run all loaded scenarios and compile the empirical scorecard."""
        results: List[EvalResult] = []
        for scenario in self.scenarios:
            results.append(self.run_scenario(scenario))

        total = len(results)
        passed = sum(1 for r in results if r.passed)
        failed = total - passed
        accuracy = (passed / total * 100.0) if total > 0 else 0.0

        # Refusal Metrics
        refusal_expected_cases = [s for s in self.scenarios if s.expectations.must_refuse]
        refusal_count = len(refusal_expected_cases)

        # Cases where the system actually blocked
        actually_blocked_ids = [
            r.scenario_id for r in results
            if r.actual_overall_decision == "BLOCK" or r.actual_factual_readiness == "BLOCK" or r.actual_action_readiness == "BLOCK"
        ]
        must_refuse_ids = [s.scenario_id for s in refusal_expected_cases]

        # Recall: of the cases that MUST refuse, how many were blocked?
        correctly_refused = sum(1 for s_id in must_refuse_ids if s_id in actually_blocked_ids)
        refusal_recall = (correctly_refused / len(must_refuse_ids) * 100.0) if must_refuse_ids else 100.0

        # Precision: of the cases blocked by refusal invariant, how many were expected to block?
        # A case is a true refusal if it was expected to block or had a must_refuse requirement
        true_refusal_blocks = 0
        for s_id in actually_blocked_ids:
            exp = self._scenario_by_id[s_id].expectations
            if exp.must_refuse or exp.expected_factual_readiness == "BLOCK" or exp.expected_action_readiness == "BLOCK" or exp.expected_overall_decision == "BLOCK":
                true_refusal_blocks += 1
        refusal_precision = (true_refusal_blocks / len(actually_blocked_ids) * 100.0) if actually_blocked_ids else 100.0

        # Label Created Refusal Rate
        label_cases = [s for s in self.scenarios if "LABEL_CREATED" in s.scenario_id]
        label_blocked = sum(1 for s in label_cases if s.scenario_id in actually_blocked_ids)
        label_rate = (label_blocked / len(label_cases) * 100.0) if label_cases else 100.0

        # Prompt Injection Detection Rate
        injection_cases = [s for s in self.scenarios if s.expectations.expected_prompt_threat_detected]
        injection_detected = sum(
            1 for s in injection_cases
            if next((r for r in results if r.scenario_id == s.scenario_id), None) and next(r for r in results if r.scenario_id == s.scenario_id).prompt_threat_detected
        )
        injection_rate = (injection_detected / len(injection_cases) * 100.0) if injection_cases else 100.0

        return EvalScorecard(
            total_scenarios=total,
            passed_scenarios=passed,
            failed_scenarios=failed,
            accuracy_rate=accuracy,
            refusal_scenarios_count=refusal_count,
            refusal_precision=refusal_precision,
            refusal_recall=refusal_recall,
            label_created_refusal_rate=label_rate,
            prompt_injection_detection_rate=injection_rate,
            results=results,
            evaluated_at=datetime.now(timezone.utc),
        )

    def run_scenario_by_id(self, scenario_id: str) -> EvalResult:
        """Run a single scenario by its unique identifier."""
        if scenario_id not in self._scenario_by_id:
            raise KeyError(f"Scenario ID '{scenario_id}' not found in benchmark catalog.")
        return self.run_scenario(self._scenario_by_id[scenario_id])

    def run_scenario(self, scenario: EvalScenario) -> EvalResult:
        """Execute a scenario through the complete pipeline and verify against expectations."""
        failures: List[str] = []

        # 1. Reconciliation Phase
        reconciler = EvidenceReconciler(
            orders=scenario.orders,
            shipments=scenario.shipments,
            communications=scenario.communications,
            refunds=scenario.refunds,
        )
        bundle = reconciler.reconcile_dispute(scenario.dispute)

        actual_rec_status = bundle.status.value
        if scenario.expectations.expected_reconciliation_status:
            if bundle.status != scenario.expectations.expected_reconciliation_status:
                failures.append(
                    f"Reconciliation status mismatch: expected {scenario.expectations.expected_reconciliation_status.value}, "
                    f"got {bundle.status.value}"
                )

        # 2. Prompt Injection Defense Phase
        prompt_threat_detected = False
        for msg in scenario.dispute.raw_messages:
            if isinstance(msg, dict):
                sanitized = self.guard.sanitize(msg.get("content", ""))
                if sanitized.is_suspicious:
                    prompt_threat_detected = True

        if scenario.expectations.expected_prompt_threat_detected is not None:
            if prompt_threat_detected != scenario.expectations.expected_prompt_threat_detected:
                failures.append(
                    f"Prompt threat detection mismatch: expected {scenario.expectations.expected_prompt_threat_detected}, "
                    f"got {prompt_threat_detected}"
                )

        # 3. Anomaly & Discrepancy Aggregation
        actual_discrepancies = [d.code for d in bundle.discrepancies]
        # Also include bundle anomalies from ContradictionDetector
        anomalies = self.contradiction_detector.check_bundle_anomalies(bundle)
        for anom in anomalies:
            if anom.code not in actual_discrepancies:
                actual_discrepancies.append(anom.code)

        for exp_disc in scenario.expectations.expected_discrepancies:
            if exp_disc not in actual_discrepancies:
                failures.append(f"Expected discrepancy '{exp_disc}' was not detected in bundle.")

        # 4. Claims Assembly Phase
        claims_to_evaluate: List[ExtractedClaim] = []
        if scenario.proposed_claim:
            claim = scenario.proposed_claim
            # If scenario.proposed_claim has no explicit supporting sources, ground with bundle citations
            if not claim.supporting_sources and bundle.is_reconciled():
                claim = claim.model_copy(update={"supporting_sources": bundle.to_citations()})
            claims_to_evaluate.append(claim)
        elif bundle.is_reconciled():
            extract_result = self.fact_extractor.extract_from_bundle(scenario.dispute, bundle)
            claims_to_evaluate.extend(extract_result.claims)

        # 5. Deterministic Policy Evaluation Phase
        goods_type = "INTANGIBLE" if "INTANGIBLE" in scenario.scenario_id else "PHYSICAL_GOODS"
        policy_engine = PolicyEngine(goods_type=goods_type)

        primary_shipment = bundle.get_primary_shipment()
        primary_order = bundle.matched_order

        # Populate available sources from all reconciled records
        available_sources: Dict[str, Any] = {}
        for s in bundle.matched_shipments:
            available_sources[s.source_identifier] = s
            available_sources[s.tracking_number] = s
        if bundle.matched_order:
            available_sources[bundle.matched_order.order_id] = bundle.matched_order
            if bundle.matched_order.paypal_transaction_id:
                available_sources[bundle.matched_order.paypal_transaction_id] = bundle.matched_order
        available_sources[scenario.dispute.dispute_id] = scenario.dispute

        evaluation = policy_engine.evaluate(
            dispute=scenario.dispute,
            order=primary_order,
            shipment=primary_shipment,
            claims=claims_to_evaluate,
            available_sources=available_sources,
        )

        actual_factual_readiness = evaluation.factual_readiness.value
        actual_action_readiness = evaluation.action_readiness.value
        actual_overall_decision = evaluation.overall_decision.value
        actual_violated_invariants = [
            inv for r in evaluation.check_results
            for inv in r.violated_invariants
            if r.decision.value in ("BLOCK", "REVIEW")
        ]
        # Also include rule identifiers from check results and advisories
        for r in evaluation.check_results:
            if r.decision.value in ("BLOCK", "REVIEW") and r.rule_identifier not in actual_violated_invariants:
                actual_violated_invariants.append(r.rule_identifier)
        for adv in evaluation.advisories:
            for inv in adv.violated_invariants:
                if inv not in actual_violated_invariants:
                    actual_violated_invariants.append(inv)
            if adv.rule_identifier not in actual_violated_invariants:
                actual_violated_invariants.append(adv.rule_identifier)

        # 6. Verify Policy Expectations
        if scenario.expectations.expected_factual_readiness:
            if evaluation.factual_readiness != scenario.expectations.expected_factual_readiness:
                failures.append(
                    f"Factual readiness mismatch: expected {scenario.expectations.expected_factual_readiness.value}, "
                    f"got {evaluation.factual_readiness.value}"
                )

        if scenario.expectations.expected_action_readiness:
            if evaluation.action_readiness != scenario.expectations.expected_action_readiness:
                failures.append(
                    f"Action readiness mismatch: expected {scenario.expectations.expected_action_readiness.value}, "
                    f"got {evaluation.action_readiness.value}"
                )

        if scenario.expectations.expected_overall_decision:
            if evaluation.overall_decision != scenario.expectations.expected_overall_decision:
                failures.append(
                    f"Overall decision mismatch: expected {scenario.expectations.expected_overall_decision.value}, "
                    f"got {evaluation.overall_decision.value}"
                )

        for exp_inv in scenario.expectations.expected_violated_invariants:
            if exp_inv not in actual_violated_invariants:
                failures.append(f"Expected violated invariant '{exp_inv}' not found in policy results.")

        # 7. Verify Critical Refusal Requirement
        is_blocked = (
            evaluation.overall_decision.value == "BLOCK"
            or evaluation.factual_readiness.value == "BLOCK"
            or evaluation.action_readiness.value == "BLOCK"
        )
        refusal_correct = True
        if scenario.expectations.must_refuse and not is_blocked:
            refusal_correct = False
            failures.append("CRITICAL SAFETY FAILURE: Scenario required refusal, but claim was not blocked!")

        passed = len(failures) == 0

        return EvalResult(
            scenario_id=scenario.scenario_id,
            passed=passed,
            actual_reconciliation_status=actual_rec_status,
            actual_factual_readiness=actual_factual_readiness,
            actual_action_readiness=actual_action_readiness,
            actual_overall_decision=actual_overall_decision,
            actual_violated_invariants=actual_violated_invariants,
            actual_discrepancies=actual_discrepancies,
            prompt_threat_detected=prompt_threat_detected,
            refusal_correct=refusal_correct,
            failure_reasons=failures,
        )
