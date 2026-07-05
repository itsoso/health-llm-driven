from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def _load_validate_module():
    spec = importlib.util.spec_from_file_location(
        "validate_harness", ROOT / "scripts" / "validate.py"
    )
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_validate_runs_dossier_consistency_as_blocking_gate(monkeypatch):
    validate = _load_validate_module()
    captured = []

    def fake_run(check):
        captured.append(check)
        return "pass", 0.0, ""

    monkeypatch.setattr(validate, "run", fake_run)
    monkeypatch.setattr(sys, "argv", ["validate.py"])

    assert validate.main() == 0

    dossier_checks = [check for check in captured if check.name == "dossier-consistency"]
    assert dossier_checks, "scripts/validate.py must run dossier consistency"
    assert dossier_checks[0].blocking is True
    assert dossier_checks[0].argv[-1] == "backend/scripts/check_dossier_consistency.py"


def test_validate_fails_when_dossier_consistency_fails(monkeypatch):
    validate = _load_validate_module()

    def fake_run(check):
        if check.name == "dossier-consistency":
            return "fail", 0.0, "Dossier consistency failed"
        return "pass", 0.0, ""

    monkeypatch.setattr(validate, "run", fake_run)
    monkeypatch.setattr(sys, "argv", ["validate.py"])

    assert validate.main() == 1


def test_pre_commit_runs_distributed_governance_gates():
    config = (ROOT / ".pre-commit-config.yaml").read_text(encoding="utf-8")

    assert "entry: python3 scripts/check_doc_drift.py" in config
    assert "entry: python3 backend/scripts/check_dossier_consistency.py" in config
    assert config.count("pass_filenames: false") >= 2


def test_ci_runs_dossier_consistency_gate():
    workflow = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")

    assert "Check dossier consistency" in workflow
    assert "python backend/scripts/check_dossier_consistency.py" in workflow


def test_ci_runs_optional_dedao_authority_gate():
    workflow = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")

    assert "dedao-authority-gate" in workflow
    assert "DEDAO_KBASE_BASE_URL" in workflow
    assert "DEDAO_KBASE_TOKEN" in workflow
    assert "enabled=false" in workflow
    assert "scripts/dedao_authority_pull_report.py --gate" in workflow
    assert "--redacted-output artifacts/dedao-authority-gate.json" in workflow


def test_ci_compares_dedao_authority_gate_with_previous_artifact():
    workflow = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")

    assert "Restore previous Dedao authority gate artifact" in workflow
    assert "actions/cache/restore@v4" in workflow
    assert "artifacts/previous-dedao-authority-gate.json" in workflow
    assert "--previous-artifact artifacts/previous-dedao-authority-gate.json" in workflow
    assert "Save Dedao authority gate artifact for next run" in workflow
    assert "actions/cache/save@v4" in workflow
