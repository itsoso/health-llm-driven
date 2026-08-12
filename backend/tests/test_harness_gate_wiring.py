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

    system_map_checks = [check for check in captured if check.name == "system-map"]
    assert system_map_checks, "scripts/validate.py must run the central System Map gate"
    assert system_map_checks[0].blocking is True
    assert system_map_checks[0].argv[-1] == "scripts/system-map-check.sh"


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

    assert "entry: ./scripts/system-map-check.sh" in config
    assert "entry: python3 scripts/check_doc_drift.py" not in config
    assert "entry: python3 backend/scripts/check_dossier_consistency.py" in config
    assert config.count("pass_filenames: false") >= 2


def test_ci_runs_dossier_consistency_gate():
    workflow = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")

    assert "Check dossier consistency" in workflow
    assert "python backend/scripts/check_dossier_consistency.py" in workflow


def test_ci_runs_central_system_map_gate():
    workflow = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")

    assert "Check System Map and doc drift" in workflow
    assert "python scripts/check_system_map.py" in workflow
    assert "pip install -r ../scripts/system-map-requirements.txt" in workflow
    assert "python scripts/check_doc_drift.py" not in workflow
