"""Health Agent core golden case suite contract tests."""

from app.tasks import eval_runner
from eval.runner import load_suite, run_suite


def test_health_agent_core_suite_loads_phase0_categories():
    cases = load_suite("health_agent_core")

    assert len(cases) >= 50

    tags = {tag for case in cases for tag in case.tags}
    assert {
        "safety_red_flag",
        "meal_water_edit",
        "sleep_recovery",
        "medication_supplement",
        "rokid_watch_capture",
    }.issubset(tags)


def test_health_agent_core_cases_have_routing_and_negative_boundaries():
    cases = load_suite("health_agent_core")

    for case in cases:
        assert case.inputs.get("query")
        assert case.inputs.get("surface") in {
            "mobile",
            "watch",
            "rokid",
            "mac",
            "web",
            "external_agent",
        }
        assert case.expected.get("intent")
        assert case.expected.get("must_route_to")
        assert case.expected.get("required_behaviors")
        assert "must_not_include" in case.expected


def test_health_agent_core_suite_runs_offline_rubric():
    report = run_suite("health_agent_core")

    assert report.total_cases >= 50
    assert report.failed == 0, [case.case_id for case in report.cases if not case.passed]
    assert report.errored == 0, [case.error for case in report.cases if case.error]
    assert report.avg_score == 1.0


def test_weekly_eval_runner_registers_health_agent_core_suite():
    assert ("health_agent_core", "main") in eval_runner._SUITES
