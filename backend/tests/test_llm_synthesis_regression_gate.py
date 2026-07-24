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


def test_agent_trajectory_contract_is_part_of_the_offline_gate():
    module = _load_gate_module()

    report = module.run_agent_trajectory_contract_gate()

    assert report["status"] == "passed"
    assert report["failed_cases"] == []


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
