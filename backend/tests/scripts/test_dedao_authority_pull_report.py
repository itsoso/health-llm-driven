from __future__ import annotations

import importlib.util
from pathlib import Path


def _load_script_module():
    script_path = Path(__file__).resolve().parents[3] / "scripts" / "dedao_authority_pull_report.py"
    spec = importlib.util.spec_from_file_location("dedao_authority_pull_report", script_path)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_gate_exit_code_allows_warning_by_default():
    module = _load_script_module()

    assert module._exit_code_for_gate("pass", fail_on_warn=False) == 0
    assert module._exit_code_for_gate("warn", fail_on_warn=False) == 0
    assert module._exit_code_for_gate("fail", fail_on_warn=False) == 1


def test_gate_exit_code_can_fail_on_warning():
    module = _load_script_module()

    assert module._exit_code_for_gate("warn", fail_on_warn=True) == 1
