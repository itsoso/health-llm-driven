from __future__ import annotations

import importlib.util
import json
import re
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[2]


class _FakeReport:
    def __init__(self, suite: str, *, failed: int = 0, errored: int = 0, regression: list[str] | None = None):
        self.suite = suite
        self.total_cases = 1
        self.passed = 0 if failed or errored else 1
        self.failed = failed
        self.errored = errored
        self.avg_score = 1.0 if self.passed else 0.0
        self.avg_latency_ms = 0
        self.regression = regression or []

    def summarize(self) -> str:
        return f"{self.suite}: {self.passed}/{self.total_cases} pass"


def _load_gate_module():
    path = ROOT / "scripts" / "harness_llm_regression_gate.py"
    assert path.exists(), "LLM synthesis regression gate script must exist"
    spec = importlib.util.spec_from_file_location("harness_llm_regression_gate", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_llm_regression_gate_defaults_to_offline_synthesis_suites(capsys):
    module = _load_gate_module()
    seen: list[tuple[str, str | None]] = []

    def fake_run_suite(suite: str, baseline: str | None = None):
        seen.append((suite, baseline))
        return _FakeReport(suite)

    exit_code = module.main(["--json"], run_suite_fn=fake_run_suite)

    assert exit_code == 0
    assert seen == [("invariants", None), ("health_agent_core", "main")]
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "passed"
    assert payload["llm_cost"] == "none"
    assert payload["trajectory_contract"]["status"] == "passed"
    assert payload["trajectory_contract"]["total_cases"] >= 5
    assert payload["trajectory_goldens"]["status"] == "passed"
    assert payload["trajectory_goldens"]["total_cases"] >= 9


def test_agent_trajectory_contract_is_part_of_the_offline_gate():
    module = _load_gate_module()

    report = module.run_agent_trajectory_contract_gate()

    assert report["status"] == "passed"
    assert report["failed_cases"] == []


def test_historical_golden_traces_are_part_of_the_offline_gate():
    module = _load_gate_module()

    report = module.run_agent_golden_trace_gate()

    assert report["status"] == "passed"
    assert report["failed_cases"] == []
    assert {
        "simple_water_write",
        "simple_fruit_write",
        "meal_context_reestimate",
        "uncertain_receipt_false_success",
        "duplicate_client_turn_side_effect",
        "idempotent_client_turn_replay",
        "read_only_delete_side_effect",
        "duplicate_same_record_side_effect",
        "missing_identity_receipt",
    }.issubset(report["covered_scenarios"])


def test_historical_golden_trace_can_refine_execution_postconditions(monkeypatch):
    module = _load_gate_module()
    original_score = module._score_golden_trace
    captured_expected: list[dict] = []

    def capture_score(case, trace):
        if trace.get("client_turn_id") == "turn-fruit-peach":
            captured_expected.append(dict(case.get("expected") or {}))
        return original_score(case, trace)

    monkeypatch.setattr(module, "_score_golden_trace", capture_score)

    report = module.run_agent_golden_trace_gate()

    assert report["status"] == "passed"
    assert captured_expected == [
        {
            "goal_kind": "write",
            "domain": "diet",
            "operation": "create",
            "target_date": "2026-07-17",
            "target_meal_types": [],
            "target_record_type": "diet",
            "target_values": {
                "meal_type": "snack",
                "food_items": "一个水蜜桃",
            },
            "requires_lookup": False,
            "requires_verification": True,
            "prohibited_operations": [],
            "clarification": False,
        }
    ]


def test_historical_golden_trace_gate_blocks_an_unexpected_acceptance(monkeypatch):
    module = _load_gate_module()

    monkeypatch.setattr(
        module,
        "_score_golden_trace",
        lambda case, trace: {
            "passed": True,
            "hard_failures": [],
            "dimensions": {},
        },
    )

    report = module.run_agent_golden_trace_gate()

    assert report["status"] == "failed"
    failed_by_scenario = {
        row["scenario"]: row for row in report["failed_cases"]
    }
    assert "uncertain_receipt_false_success" in failed_by_scenario
    assert "duplicate_client_turn_side_effect" in failed_by_scenario


def test_historical_golden_trace_gate_blocks_missing_required_scenario(
    monkeypatch,
    tmp_path,
):
    module = _load_gate_module()
    incomplete_fixture = tmp_path / "agent_trajectory_goldens.yaml"
    incomplete_fixture.write_text(
        """
name: agent_trajectory_goldens
version: 1
cases:
  - scenario: simple_water_write
    history_ref: water_write_clarification_loop
    case_id: water_record_explicit_chinese_amount
    expected:
      passed: true
      hard_failures: []
    trace:
      client_turn_id: turn-water-500
      goal:
        kind: simple_health_record
        domain: water
        operation: create
        target_date: "2026-07-17"
        target_meal_types: []
      tool_calls:
        - args:
            record_type: water
            operation: create
            data: {amount_ml: "500"}
          receipt: {status: verified, record_id: 501}
        - args: {record_type: water, operation: list}
          result: [{id: 501, amount_ml: 500}]
      final: {claims_complete: true}
""",
        encoding="utf-8",
    )
    monkeypatch.setattr(module, "AGENT_TRAJECTORY_GOLDENS", incomplete_fixture)

    report = module.run_agent_golden_trace_gate()

    assert report["status"] == "failed"
    assert any(
        "missing required scenarios" in row.get("mismatch", {}).get("fixture", "")
        for row in report["failed_cases"]
    )


def test_historical_golden_trace_gate_rejects_private_fixture_data(
    monkeypatch,
    tmp_path,
):
    module = _load_gate_module()
    private_fixture = tmp_path / "agent_trajectory_goldens.yaml"
    private_fixture.write_text(
        """
name: agent_trajectory_goldens
version: 1
fixture_origin: synthetic
cases:
  - scenario: simple_water_write
    history_ref: water_write_clarification_loop
    case_id: water_record_explicit_chinese_amount
    user_id: 123
    trace:
      client_turn_id: turn-water-500
      source_url: https://example.invalid/private.jpg
    expected: {passed: false, hard_failures: []}
""",
        encoding="utf-8",
    )
    monkeypatch.setattr(module, "AGENT_TRAJECTORY_GOLDENS", private_fixture)

    report = module.run_agent_golden_trace_gate()

    assert report["status"] == "failed"
    fixture_errors = [
        row.get("mismatch", {}).get("fixture", "")
        for row in report["failed_cases"]
    ]
    assert any("forbidden fixture key: user_id" in error for error in fixture_errors)
    assert any("forbidden URI value" in error for error in fixture_errors)


def test_historical_golden_trace_gate_scans_fixture_root_and_embedded_uri(
    monkeypatch,
    tmp_path,
):
    module = _load_gate_module()
    private_fixture = tmp_path / "agent_trajectory_goldens.yaml"
    private_fixture.write_text(
        """
name: agent_trajectory_goldens
version: 1
fixture_origin: synthetic
user_id: 123
note: "synthetic trace copied from https://example.invalid/private.jpg"
cases: []
""",
        encoding="utf-8",
    )
    monkeypatch.setattr(module, "AGENT_TRAJECTORY_GOLDENS", private_fixture)

    report = module.run_agent_golden_trace_gate()
    fixture_errors = [
        row.get("mismatch", {}).get("fixture", "")
        for row in report["failed_cases"]
    ]

    assert any("forbidden fixture key: user_id at $.user_id" in error for error in fixture_errors)
    assert any("forbidden URI value at $.note" in error for error in fixture_errors)


def test_historical_golden_trace_gate_rejects_sensitive_key_variants(
    monkeypatch,
    tmp_path,
):
    module = _load_gate_module()
    private_fixture = tmp_path / "agent_trajectory_goldens.yaml"
    private_fixture.write_text(
        """
name: agent_trajectory_goldens
version: 1
fixture_origin: synthetic
patient_id: real-patient
authorization: Bearer private-secret
message_body: private health text
cases: []
""",
        encoding="utf-8",
    )
    monkeypatch.setattr(module, "AGENT_TRAJECTORY_GOLDENS", private_fixture)

    report = module.run_agent_golden_trace_gate()
    fixture_errors = [
        row.get("mismatch", {}).get("fixture", "")
        for row in report["failed_cases"]
    ]

    assert any("forbidden fixture key: patient_id" in error for error in fixture_errors)
    assert any("forbidden fixture key: authorization" in error for error in fixture_errors)
    assert any("forbidden fixture key: message_body" in error for error in fixture_errors)


def test_historical_golden_trace_gate_scans_dataset_privacy(
    monkeypatch,
    tmp_path,
):
    module = _load_gate_module()
    private_dataset = tmp_path / "agent_trajectories.yaml"
    private_dataset.write_text(
        """
name: agent_trajectories
version: 1
fixture_origin: synthetic
cases:
  - id: private-case
    patient_id: real-patient
    user: "synthetic prompt"
    expected: {}
""",
        encoding="utf-8",
    )
    monkeypatch.setattr(module, "AGENT_TRAJECTORY_DATASET", private_dataset)

    report = module.run_agent_golden_trace_gate()
    fixture_errors = [
        row.get("mismatch", {}).get("fixture", "")
        for row in report["failed_cases"]
    ]

    assert any(
        "forbidden fixture key: patient_id at $dataset.cases[0].patient_id" in error
        for error in fixture_errors
    )


def test_historical_golden_trace_gate_requires_synthetic_origin(
    monkeypatch,
    tmp_path,
):
    module = _load_gate_module()
    fixture_without_origin = tmp_path / "agent_trajectory_goldens.yaml"
    fixture_without_origin.write_text(
        """
name: agent_trajectory_goldens
version: 1
cases: []
""",
        encoding="utf-8",
    )
    monkeypatch.setattr(module, "AGENT_TRAJECTORY_GOLDENS", fixture_without_origin)

    report = module.run_agent_golden_trace_gate()

    assert report["status"] == "failed"
    assert any(
        "fixture_origin must be synthetic"
        in row.get("mismatch", {}).get("fixture", "")
        for row in report["failed_cases"]
    )


def test_llm_regression_gate_fails_on_suite_failure():
    module = _load_gate_module()

    def fake_run_suite(suite: str, baseline: str | None = None):
        return _FakeReport(suite, failed=1 if suite == "invariants" else 0)

    assert module.main([], run_suite_fn=fake_run_suite) == 1


def test_ci_hard_wires_llm_synthesis_regression_gate():
    ci = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    m = re.search(
        r"- name: LLM synthesis regression gate.*?(?=\n      - name:|\Z)",
        ci,
        flags=re.S,
    )
    assert m, "CI must run the LLM synthesis regression gate"
    section = m.group(0)
    assert "python scripts/harness_llm_regression_gate.py" in section
    assert "continue-on-error" not in section, "LLM synthesis regression gate must be blocking"


def test_promptfoo_bridge_mirrors_invariants_goldset():
    gold = yaml.safe_load((ROOT / "backend" / "eval" / "datasets" / "invariants.yaml").read_text(encoding="utf-8"))
    bridge_path = ROOT / "backend" / "eval" / "promptfoo" / "synthesis_invariants.promptfooconfig.yaml"
    assert bridge_path.exists(), "promptfoo bridge config must exist for synthesis invariant evals"
    bridge = yaml.safe_load(bridge_path.read_text(encoding="utf-8"))

    gold_ids = {case["id"] for case in gold["cases"]}
    bridge_ids = {case["vars"]["case_id"] for case in bridge["tests"]}

    assert bridge["description"].startswith("Reva Health synthesis invariant")
    assert bridge_ids == gold_ids
    for test_case in bridge["tests"]:
        assert "answer" in test_case["vars"]
        assert "founder_critique" in test_case["vars"]
        assert test_case["assert"][0]["type"] == "python"
