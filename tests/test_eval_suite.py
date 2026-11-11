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
        client.post("/api/auth/demo-session", json={"profile_id": "merchant_admin"})

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


# ---------------------------------------------------------------------------
# Pre-Submission Review Regression Tests (Milestone 5 Data Binding & Safety)
# ---------------------------------------------------------------------------

class TestBenchmarkDataBindingRegression:
    """Regression tests verifying data binding isolation, evidence provenance, and safety."""

    def test_scenario_04_exact_fixture_data_binding(self):
        """Scenario 04 must bind to exact fixture: ORD-04, $850.00 USD, FEDEX TRK-04, DELIVERED."""
        from docket.eval.service import build_enriched_scorecard
        matrix_path = Path("artifacts/docket_evaluation_matrix.json")
        with open(matrix_path, "r", encoding="utf-8") as f:
            raw = json.load(f)
        scorecard = build_enriched_scorecard(raw)

        scen04 = next((r for r in scorecard["results"] if "SCENARIO_04" in r["scenario_id"]), None)
        assert scen04 is not None, "Scenario 04 must exist in scorecard results"

        ev = scen04["input_evidence"]
        # Verify exact fixture attributes
        assert ev["order_id"] == "ORD-04", f"Expected ORD-04, got {ev['order_id']}"
        assert ev["order_amount"] == "$850.00 USD", f"Expected $850.00 USD, got {ev['order_amount']}"
        assert ev["carrier"] == "FEDEX", f"Expected FEDEX, got {ev['carrier']}"
        assert ev["tracking_number"] == "TRK-04", f"Expected TRK-04, got {ev['tracking_number']}"
        assert ev["tracking_status"] == "DELIVERED", f"Expected DELIVERED, got {ev['tracking_status']}"
        assert ev["recipient_signature_present"] is False, "Scenario 04 must explicitly reflect missing signature"
        assert ev["source_provenance"] == "SYNTHETIC_FIXTURE"

        # Explicitly verify absence of cross-contamination from Scenario 20 ($25.00, USPS)
        assert ev["order_amount"] != "$25.00 USD", "Scenario 04 must not inherit $25 amount from Scenario 20"
        assert ev["carrier"] != "USPS", "Scenario 04 must not inherit USPS carrier from Scenario 20"

    def test_all_20_scenarios_have_exact_isolated_evidence(self):
        """Verify all 20 scenario detail objects obtain all fields from exact fixture without leakage."""
        from docket.eval.service import build_enriched_scorecard
        scenarios = load_all_scenarios()
        scenarios_by_id = {s.scenario_id: s for s in scenarios}

        matrix_path = Path("artifacts/docket_evaluation_matrix.json")
        with open(matrix_path, "r", encoding="utf-8") as f:
            raw = json.load(f)
        scorecard = build_enriched_scorecard(raw)

        for r in scorecard["results"]:
            s_id = r["scenario_id"]
            fixture = scenarios_by_id[s_id]
            ev = r["input_evidence"]

            if fixture.orders:
                expected_order_id = fixture.orders[0].order_id
                assert ev["order_id"] == expected_order_id, f"Order ID mismatch in {s_id}"
                expected_amt = f"${fixture.orders[0].gross_amount.value:.2f} {fixture.orders[0].gross_amount.currency_code}"
                assert ev["order_amount"] == expected_amt, f"Amount mismatch in {s_id}"

            if fixture.shipments:
                expected_carrier = fixture.shipments[0].carrier_name
                expected_trk = fixture.shipments[0].tracking_number
                expected_status = fixture.shipments[0].tracking_status.value
                assert ev["carrier"] == expected_carrier, f"Carrier mismatch in {s_id}"
                assert ev["tracking_number"] == expected_trk, f"Tracking number mismatch in {s_id}"
                assert ev["tracking_status"] == expected_status, f"Tracking status mismatch in {s_id}"

    def test_supporting_evidence_provenance_labels(self):
        """Verify OrderRecord and ShipmentRecord default to explicit SYNTHETIC_FIXTURE provenance."""
        from docket.models.evidence import OrderRecord, ShipmentRecord, TrackingStatus
        from decimal import Decimal
        from docket.models.dispute import Money

        order = OrderRecord(
            order_id="ORD-TEST",
            gross_amount=Money(value=Decimal("10.00"), currency_code="USD"),
        )
        assert order.source_provenance == "SYNTHETIC_FIXTURE"

        shipment = ShipmentRecord(
            internal_order_id="ORD-TEST",
            tracking_number="TRK-TEST",
            carrier_name="UPS",
            tracking_status=TrackingStatus.DELIVERED,
            source_identifier="SRC-TEST",
        )
        assert shipment.source_provenance == "SYNTHETIC_FIXTURE"

    def test_address_match_explanation_limits_claims(self):
        """AddressMatchInvariant explanation must not claim physical street-level delivery."""
        from docket.policy.engine import AddressMatchInvariant
        from docket.models.evidence import Address, OrderRecord, ShipmentRecord, TrackingStatus
        from decimal import Decimal
        from docket.models.dispute import Money

        inv = AddressMatchInvariant()
        order = OrderRecord(
            order_id="ORD-1",
            shipping_address=Address(postal_code="95131", country_code="US"),
            gross_amount=Money(value=Decimal("25.00"), currency_code="USD"),
        )
        shipment = ShipmentRecord(
            internal_order_id="ORD-1",
            tracking_number="TRK-1",
            carrier_name="USPS",
            tracking_status=TrackingStatus.DELIVERED,
            shipment_address=Address(postal_code="95131", country_code="US"),
            source_identifier="SRC-USPS",
        )
        res = inv.evaluate(order, shipment)
        assert "postal code and country verified" in res.explanation
        assert "does not verify street-level delivery" in res.explanation

    def test_audit_event_types_semantics(self):
        """AuditEventType enum distinguishes ingestion, synchronization, and duplicate handling."""
        from docket.models.audit import AuditEventType
        assert AuditEventType.DISPUTE_INGESTED.value == "DISPUTE_INGESTED"
        assert AuditEventType.DISPUTE_SYNCHRONIZED.value == "DISPUTE_SYNCHRONIZED"
        assert AuditEventType.DUPLICATE_WEBHOOK_RECEIVED.value == "DUPLICATE_WEBHOOK_RECEIVED"
        assert AuditEventType.DUPLICATE_WEBHOOK_IGNORED.value == "DUPLICATE_WEBHOOK_IGNORED"
