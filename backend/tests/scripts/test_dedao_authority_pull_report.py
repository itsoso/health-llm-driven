from __future__ import annotations

import importlib.util
import json
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


def test_write_output_text_creates_parent_directory(tmp_path):
    module = _load_script_module()
    output_path = tmp_path / "reports" / "dedao-gate.json"

    written_path = module._write_output_text("{\"status\":\"pass\"}\n", output_path)

    assert written_path == output_path
    assert output_path.read_text(encoding="utf-8") == "{\"status\":\"pass\"}\n"


def test_main_redacted_output_writes_versioned_artifact(tmp_path, capsys):
    module = _load_script_module()
    output_path = tmp_path / "reports" / "dedao-gate.json"

    exit_code = module.main(["--redacted-output", str(output_path)])
    captured = capsys.readouterr()

    assert exit_code == 1
    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert payload["artifact_schema"] == "dedao_authority_pull_gate_v1"
    assert payload["generated_at"].endswith("Z")
    assert "redacted_output:" in captured.out
