from __future__ import annotations

import importlib.util
import json
import re
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[2]


def _load_gate_module():
    path = ROOT / "scripts" / "harness_llm_change_gate.py"
    assert path.exists(), "LLM change gate script must exist"
    spec = importlib.util.spec_from_file_location("harness_llm_change_gate", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_llm_change_gate_passes_for_ordinary_paths(capsys):
    module = _load_gate_module()

    exit_code = module.main(
        ["--json", "--path", "backend/app/api/diet.py", "--path", "docs/plans/ordinary.md"],
        env={},
    )

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "passed"
    assert payload["live_llm_required"] is False
    assert payload["matched_paths"] == []


def test_llm_change_gate_blocks_orchestrator_changes_without_live_confirmation(capsys):
    module = _load_gate_module()

    exit_code = module.main(["--json", "--path", "backend/app/orchestrator/orchestrator.py"], env={})

    assert exit_code == 1
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "failed"
    assert payload["live_llm_required"] is True
    assert payload["confirmed"] is False
    assert payload["matched_paths"] == [
        {
            "path": "backend/app/orchestrator/orchestrator.py",
            "reason": "orchestrator runtime",
        }
    ]
    assert "python scripts/harness_llm_regression_gate.py --include-live-llm" in payload["next_steps"]
    assert "gh variable set HARNESS_LIVE_LLM_EVAL_CONFIRMED" in payload["next_steps"]
    assert "git rev-parse HEAD" in payload["next_steps"]


def test_llm_change_gate_passes_when_live_confirmation_is_explicit(capsys):
    module = _load_gate_module()

    exit_code = module.main(
        ["--json", "--path", "backend/app/services/llm/model_registry.py"],
        env={"HARNESS_LIVE_LLM_EVAL_CONFIRMED": "1"},
    )

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "passed"
    assert payload["live_llm_required"] is True
    assert payload["confirmed"] is True
    assert payload["matched_paths"] == [
        {
            "path": "backend/app/services/llm/model_registry.py",
            "reason": "LLM service/runtime",
        }
    ]


def test_llm_change_gate_rejects_stale_or_boolean_confirmation_in_ci(capsys):
    module = _load_gate_module()
    current_sha = "a" * 40

    exit_code = module.main(
        ["--json", "--path", "backend/app/services/llm/model_registry.py"],
        env={
            "GITHUB_SHA": current_sha,
            "HARNESS_LIVE_LLM_EVAL_CONFIRMED": "1",
        },
    )

    assert exit_code == 1
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "failed"
    assert payload["confirmed"] is False
    assert payload["expected_confirmation"] == current_sha


def test_llm_change_gate_accepts_confirmation_bound_to_current_ci_sha(capsys):
    module = _load_gate_module()
    current_sha = "b" * 40

    exit_code = module.main(
        ["--json", "--path", "backend/app/services/llm/model_registry.py"],
        env={
            "GITHUB_SHA": current_sha,
            "HARNESS_LIVE_LLM_EVAL_CONFIRMED": current_sha,
        },
    )

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "passed"
    assert payload["confirmed"] is True
    assert payload["expected_confirmation"] == current_sha


def test_llm_change_gate_uses_pull_request_head_sha_instead_of_merge_sha(capsys):
    module = _load_gate_module()
    merge_sha = "c" * 40
    head_sha = "d" * 40

    exit_code = module.main(
        ["--json", "--path", "backend/app/services/llm/model_registry.py"],
        env={
            "GITHUB_SHA": merge_sha,
            "HARNESS_LIVE_LLM_EVAL_TARGET_SHA": head_sha,
            "HARNESS_LIVE_LLM_EVAL_CONFIRMED": head_sha,
        },
    )

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["confirmed"] is True
    assert payload["expected_confirmation"] == head_sha


def test_ci_hard_wires_llm_change_gate():
    ci = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    section_match = re.search(
        r"- name: LLM live-change regression gate.*?(?=\n      - name:|\Z)",
        ci,
        flags=re.S,
    )
    assert section_match, "CI must run the LLM live-change regression gate"
    section = section_match.group(0)
    assert "python scripts/harness_llm_change_gate.py" in section
    assert "continue-on-error" not in section, "LLM live-change gate must be blocking"

    gate_step = next(
        step
        for step in yaml.safe_load(ci)["jobs"]["backend-quality"]["steps"]
        if step.get("name") == "LLM live-change regression gate"
    )
    assert gate_step["env"]["HARNESS_LIVE_LLM_EVAL_TARGET_SHA"] == (
        "${{ github.event.pull_request.head.sha || github.sha }}"
    )

    workflow = yaml.safe_load(ci)
    backend_checkout = next(
        step
        for step in workflow["jobs"]["backend-quality"]["steps"]
        if str(step.get("uses") or "").startswith("actions/checkout@")
    )
    assert backend_checkout["with"]["fetch-depth"] == 0, (
        "change detection needs full history"
    )
