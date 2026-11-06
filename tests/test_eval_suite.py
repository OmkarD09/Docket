"""Tests for Docket's Synthetic Evaluation Benchmark Suite (Milestone 5).

Following TDD methodology (tdd-workflow):
Evaluates 20 labeled e-commerce dispute scenarios proving system accuracy,
refusal robustness, prompt injection defense, and metric calculation.
"""

from __future__ import annotations

import json
from pathlib import Path
import pytest

from docket.eval.models import (
    EvalExpectation,
    EvalResult,
    EvalScenario,
    EvalScorecard,
)
from docket.eval.runner import BenchmarkRunner
from docket.eval.scenarios import load_all_scenarios


# ---------------------------------------------------------------------------
# Test Scenario Inventory & Metadata
# ---------------------------------------------------------------------------

class TestScenarioInventory:
    """Verify that the synthetic benchmark catalog meets the 15-20 case requirement."""

    def test_scenario_count_meets_target(self):
        scenarios = load_all_scenarios()
        assert len(scenarios) == 20, "Evaluation suite must contain exactly 20 diverse test cases"

    def test_all_scenarios_have_unique_ids(self):
        scenarios = load_all_scenarios()
        ids = [s.scenario_id for s in scenarios]
        assert len(ids) == len(set(ids)), "All scenario IDs must be unique"

    def test_scenarios_cover_mandatory_defining_edge_cases(self):
        scenarios = load_all_scenarios()
        scenario_ids = [s.scenario_id for s in scenarios]

        mandatory_cases = [
            "SCENARIO_01_INR_LABEL_CREATED",
            "SCENARIO_02_INR_DELIVERED_MATCHING_ADDRESS",
            "SCENARIO_03_INR_DELIVERY_WRONG_POSTAL_CODE",
            "SCENARIO_04_INR_HIGH_VALUE_MISSING_SIGNATURE_PRE_2026",
            "SCENARIO_05_INR_HIGH_VALUE_MISSING_SIGNATURE_POST_2026",
            "SCENARIO_06_INR_PRIOR_REFUND_OVERLAP",
            "SCENARIO_07_INR_IN_TRANSIT_UNFINISHED",
            "SCENARIO_08_INR_TIMELINE_PARADOX",
            "SCENARIO_09_INR_CURRENCY_MISMATCH",
            "SCENARIO_10_PROMPT_INJECTION_BUYER_NOTE",
            "SCENARIO_11_INR_ORPHAN_DISPUTE",
            "SCENARIO_12_INR_AMBIGUOUS_MULTIPLE_ORDERS",
            "SCENARIO_13_DISPUTE_PREMATURE_INQUIRY_OPEN",
            "SCENARIO_14_DISPUTE_ALREADY_RESOLVED",
            "SCENARIO_15_UNTRUSTED_HATEOAS_HOST",
            "SCENARIO_16_SNAD_SPLIT_SHIPMENT_PARTIAL",
            "SCENARIO_17_INR_INTANGIBLE_GOODS_EXEMPTION",
            "SCENARIO_18_INR_FABRICATED_CITATION",
            "SCENARIO_19_INR_PARTIAL_AMOUNT_DISPUTE",
            "SCENARIO_20_REAL_SANDBOX_FIXTURE_BASELINE",
        ]

        for m in mandatory_cases:
            assert m in scenario_ids, f"Mandatory scenario '{m}' missing from benchmark suite"


# ---------------------------------------------------------------------------
# Benchmark Runner Execution & Scorecard Metrics
# ---------------------------------------------------------------------------

class TestBenchmarkRunner:
    """Execute the full evaluation benchmark and verify empirical metrics."""

    def test_run_full_benchmark(self):
        runner = BenchmarkRunner()
        scorecard = runner.run_all()

        assert isinstance(scorecard, EvalScorecard)
        assert scorecard.total_scenarios == 20
        assert scorecard.passed_scenarios == 20
        assert scorecard.failed_scenarios == 0
        assert scorecard.accuracy_rate == 100.0

    def test_refusal_metrics_100_percent_precision_and_recall(self):
        runner = BenchmarkRunner()
        scorecard = runner.run_all()

        # Critical Hackathon Safety Guarantee:
        # Refusal Recall: 100% of cases that MUST be refused are refused.
        # Refusal Precision: 100% of refused cases were supposed to be refused.
        assert scorecard.refusal_recall == 100.0
        assert scorecard.refusal_precision == 100.0
        assert scorecard.label_created_refusal_rate == 100.0
        assert scorecard.prompt_injection_detection_rate == 100.0

    def test_scorecard_json_artifact_export(self, tmp_path):
        runner = BenchmarkRunner()
        scorecard = runner.run_all()

        artifact_file = tmp_path / "docket_evaluation_matrix.json"
        scorecard.export_json(str(artifact_file))

        assert artifact_file.exists()
        with open(artifact_file, "r", encoding="utf-8") as f:
            data = json.load(f)

        assert data["total_scenarios"] == 20
        assert data["accuracy_rate"] == 100.0
        assert len(data["results"]) == 20


# ---------------------------------------------------------------------------
# Individual Scenario Deep Verification
# ---------------------------------------------------------------------------

class TestIndividualScenarios:
    """Verify specific scenario behaviors in isolation."""

    def test_scenario_01_label_created_must_refuse(self):
        runner = BenchmarkRunner()
        result = runner.run_scenario_by_id("SCENARIO_01_INR_LABEL_CREATED")
        assert result.passed
        assert result.refusal_correct
        assert result.actual_factual_readiness == "BLOCK"
        assert "RULE_DELIVERY_PROOF" in result.actual_violated_invariants

    def test_scenario_02_verified_delivery_allows_submission(self):
        runner = BenchmarkRunner()
        result = runner.run_scenario_by_id("SCENARIO_02_INR_DELIVERED_MATCHING_ADDRESS")
        assert result.passed
        assert result.actual_factual_readiness == "ALLOW"
        assert result.actual_action_readiness == "ALLOW"

    def test_scenario_03_wrong_postal_code_blocked(self):
        runner = BenchmarkRunner()
        result = runner.run_scenario_by_id("SCENARIO_03_INR_DELIVERY_WRONG_POSTAL_CODE")
        assert result.passed
        assert result.actual_factual_readiness == "BLOCK"
        assert "RULE_ADDRESS_MATCH" in result.actual_violated_invariants

    def test_scenario_10_prompt_injection_flagged_and_refused(self):
        runner = BenchmarkRunner()
        result = runner.run_scenario_by_id("SCENARIO_10_PROMPT_INJECTION_BUYER_NOTE")
        assert result.passed
        assert result.prompt_threat_detected
        assert result.actual_factual_readiness == "BLOCK"



class TestEnrichedScorecardService:
    """Verify enriched evaluation scorecard data structure and API endpoint."""

    def test_build_enriched_scorecard(self):
        from docket.eval.service import execute_and_persist_benchmark
        data = execute_and_persist_benchmark()
        assert data["total_scenarios"] == 20
        assert data["passed_scenarios"] == 20
        assert data["false_allow"] == 0
        assert data["false_block"] == 0
        assert "confusion_matrix" in data
        assert data["confusion_matrix"]["counts"]["BLOCK"]["BLOCK"] == 8
        assert data["confusion_matrix"]["counts"]["ALLOW"]["ALLOW"] == 6
        assert data["confusion_matrix"]["counts"]["REVIEW"]["REVIEW"] == 6
        assert len(data["rule_performance"]) == 5
        assert len(data["results"]) == 20

    def test_api_eval_scorecard_and_run(self):
        from fastapi.testclient import TestClient
        from docket.api.app import create_app
        client = TestClient(create_app())

        resp = client.get("/api/eval/scorecard")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_scenarios"] == 20
        assert data["passed_scenarios"] == 20
        assert "confusion_matrix" in data
        assert "rule_performance" in data

        run_resp = client.post("/api/eval/run")
        assert run_resp.status_code == 200
        run_data = run_resp.json()
        assert run_data["total_scenarios"] == 20
