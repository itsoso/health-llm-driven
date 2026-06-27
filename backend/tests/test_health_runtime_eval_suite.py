# -*- coding: utf-8 -*-
"""Health Runtime evaluation objects and release-gate suite."""


def test_health_runtime_eval_service_exposes_first_class_objects():
    from app.services.health_runtime_eval import (
        EVALUATION_SCENARIOS,
        SAFETY_REGRESSION_SUITE,
        SYNTHETIC_USER_TWINS,
        run_health_runtime_evaluation,
    )

    assert {"metabolic_missing_data", "redline_symptom", "device_conflict"}.issubset(SYNTHETIC_USER_TWINS)
    assert {"object_landing", "claim_boundary", "safety_regression"}.issubset(EVALUATION_SCENARIOS)
    assert len(SAFETY_REGRESSION_SUITE["cases"]) >= 3

    report = run_health_runtime_evaluation()

    assert report["suite"] == "health_runtime"
    assert report["passed"] == report["total_cases"]
    assert report["release_gate"]["status"] == "pass"
    assert report["metrics"]["object_landing_rate"] == 1.0
    assert report["metrics"]["claim_boundary_pass_rate"] == 1.0
    assert report["metrics"]["safety_regression_pass_rate"] == 1.0


def test_eval_runner_health_runtime_suite_passes():
    from eval.runner import run_suite

    report = run_suite("health_runtime", baseline="main")

    assert report.suite == "health_runtime"
    assert report.total_cases >= 3
    assert report.failed == 0
    assert report.errored == 0
    assert report.regression == []
    assert all(case.details["output"]["passed"] is True for case in report.cases)
