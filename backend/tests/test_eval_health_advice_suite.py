"""Health advice eval suite contract tests."""

from app.tasks import eval_runner
from eval.runner import load_suite, run_suite


def test_health_advice_suite_loads_required_case_categories():
    cases = load_suite("health_advice")

    assert len(cases) >= 30

    tags = {tag for case in cases for tag in case.tags}
    assert {
        "genetics",
        "supplement",
        "sleep",
        "movement",
        "lab",
        "epigenetic",
        "paid_content",
    }.issubset(tags)


def test_health_advice_suite_has_epigenetic_overclaim_guardrail():
    cases = load_suite("health_advice")

    overclaim_cases = [
        case for case in cases
        if "epigenetic" in case.tags and case.expected.get("reason") == "epigenetic_overclaim"
    ]

    assert overclaim_cases
    assert all(case.expected.get("must_not_include") for case in overclaim_cases)


def test_health_advice_high_risk_cases_define_negative_boundaries():
    cases = load_suite("health_advice")
    high_risk_cases = [case for case in cases if "high_risk" in case.tags]

    assert high_risk_cases
    assert all(case.expected.get("must_not_include") for case in high_risk_cases)


def test_health_advice_suite_runs_against_main_baseline():
    report = run_suite("health_advice", baseline="main")

    assert report.total_cases >= 30
    assert report.failed == 0, [case.case_id for case in report.cases if not case.passed]
    assert report.errored == 0, [case.error for case in report.cases if case.error]
    assert report.regression == []


def test_weekly_eval_runner_registers_health_advice_suite():
    assert ("health_advice", "main") in eval_runner._SUITES
